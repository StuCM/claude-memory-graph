"""The grounding-coverage experiment: measure before building the planner.

Feeds real prompts through the grounder and reports how much of their
vocabulary the graph can account for. Every content word of every prompt is
assigned to exactly one category, in precedence order:

    wh        question word surviving stopwording (why/which/who/where)
    model     names a resource model or concept type ("decisions" -> Decision)
    relation  falls inside a matched relation verb-form phrase ("works on")
    alias     appears in some node's aliases property
    entity    appears in some node's name / concept label
    modifier  the closed filter lexicon (recent, active, superseded, ...)
    leftover  the graph has no idea — THE number that matters

Why this decides the planner go/no-go: planner v0 refuses to compose unless
(nearly) every content word grounds. If real question-shaped prompts mostly
ground, a small grammar suffices; if leftovers dominate, the fix is lexicon
work (aliases, verb forms, maybe a stemmer) BEFORE composer work. The top-
leftover list names the exact missing vocabulary — it is a work order, not
just a metric.

Inputs (see docs/tasks/grounding-coverage-experiment.md for run notes):
- --prompts FILE          one prompt per line (any provenance)
- --transcripts PATH...   Claude Code transcript .jsonl files or directories
                          (~/.claude/projects/...); user prompts extracted,
                          command/meta noise skipped

Read-only against the store; no LLM; deterministic — same inputs, same report.
"""

import json
import re
from pathlib import Path

from claude_hook_kit import terms_pos

from .. import ontology
from .recall import _corpus
from .runtime import store_dir

WH_WORDS = {"what", "which", "who", "why", "when", "how", "where"}
_AUX_START = re.compile(
    r"^(is|are|do|does|did|can|could|will|would|should|have|has|was|were)\b")

MODIFIERS = {
    "recent", "recently", "latest", "last", "newest", "new", "first",
    "active", "open", "closed", "current", "currently",
    "old", "stale", "superseded", "previous", "previously", "former",
    "earlier", "before", "after", "still", "now", "today", "yesterday",
}


def question_shaped(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    first = re.split(r"[\s,']", t, 1)[0]
    return t.endswith("?") or first in WH_WORDS or bool(_AUX_START.match(t))


# ----------------------------------------------------------------
# Vocabulary building (once per run, all read from the graph)
# ----------------------------------------------------------------

def _model_nouns() -> dict[str, str]:
    nouns = {}
    for name in ontology.RESOURCE_MODELS + ontology.CONCEPT_TYPES:
        lower = name.lower()
        nouns[lower] = name
        nouns[lower + "s"] = name
    nouns["people"] = "Person"
    nouns["persons"] = "Person"
    nouns["technologies"] = "Technology"
    nouns["companies"] = "Company"
    return nouns


def _verb_phrases(store) -> list[tuple[re.Pattern, set[str]]]:
    """(compiled word-boundary pattern, its content tokens) per verb form,
    longest phrases first so 'working on' claims its words before 'on'."""
    phrases = set()
    for entry in store.relation_lexicon().values():
        phrases.update(f.lower() for f in entry["verbForms"])
    out = []
    for phrase in sorted(phrases, key=len, reverse=True):
        tokens = {w for _, w in terms_pos(phrase)}
        out.append((re.compile(r"\b" + re.escape(phrase) + r"\b"), tokens))
    return out


def _alias_tokens(store) -> set[str]:
    tokens: set[str] = set()
    for solution in store.query(
            'SELECT ?o WHERE { GRAPH ?g { ?s mem:aliases ?o } }'):
        tokens.update(w for _, w in terms_pos(solution["o"].value))
    return tokens


def _entity_tokens(store) -> set[str]:
    tokens: set[str] = set()
    for d in _corpus(store, include_concepts=True):
        tokens.update(d["name_terms"])
    return tokens


# ----------------------------------------------------------------
# The analysis
# ----------------------------------------------------------------

def analyse(store, prompts: list[str]) -> dict:
    model_nouns = _model_nouns()
    verb_phrases = _verb_phrases(store)
    aliases = _alias_tokens(store)
    entities = _entity_tokens(store)

    results = []
    for prompt in prompts:
        words = [w for _, w in terms_pos(prompt)]
        if not words:
            continue
        lower = prompt.lower()
        relation_words: set[str] = set()
        for pattern, tokens in verb_phrases:
            if pattern.search(lower):
                relation_words |= tokens

        categories: dict[str, str] = {}
        for w in words:
            if w in WH_WORDS:
                categories[w] = "wh"
            elif w in model_nouns:
                categories[w] = "model"
            elif w in relation_words:
                categories[w] = "relation"
            elif w in aliases:
                categories[w] = "alias"
            elif w in entities:
                categories[w] = "entity"
            elif w in MODIFIERS:
                categories[w] = "modifier"
            else:
                categories[w] = "leftover"

        grounded = sum(1 for c in categories.values() if c != "leftover")
        results.append({
            "prompt": prompt.strip(),
            "question": question_shaped(prompt),
            "words": len(categories),
            "coverage": grounded / len(categories),
            "categories": categories,
        })
    return {"prompts": results}


def report(store, prompts: list[str]) -> str:
    data = analyse(store, prompts)["prompts"]
    if not data:
        return "No analysable prompts (all empty or stopwords-only)."

    questions = [r for r in data if r["question"]]
    lines = [f"prompts analysed: {len(data)} · question-shaped: {len(questions)}"]

    def bucket(rs):
        full = sum(1 for r in rs if r["coverage"] >= 0.9)
        part = sum(1 for r in rs if 0.5 <= r["coverage"] < 0.9)
        weak = len(rs) - full - part
        return full, part, weak

    for label, rs in (("question-shaped", questions), ("all prompts", data)):
        if not rs:
            continue
        full, part, weak = bucket(rs)
        pct = 100 * full // len(rs)
        lines.append(
            f"{label}: fully grounded (>=90%): {full} ({pct}%) · "
            f"partial (50-90%): {part} · weak (<50%): {weak}")

    counts: dict[str, int] = {}
    leftovers: dict[str, int] = {}
    for r in data:
        for w, c in r["categories"].items():
            counts[c] = counts.get(c, 0) + 1
            if c == "leftover":
                leftovers[w] = leftovers.get(w, 0) + 1
    lines.append("category hits: " + " · ".join(
        f"{c} {n}" for c, n in sorted(counts.items(), key=lambda x: -x[1])))

    if leftovers:
        top = sorted(leftovers.items(), key=lambda x: -x[1])[:15]
        lines.append("top leftover words (the missing-vocabulary work order): "
                     + "  ".join(f"{w}({n})" for w, n in top))

    ready = [r for r in questions if r["coverage"] >= 0.9]
    if ready:
        lines.append("")
        lines.append("planner-ready questions (fully grounded — v0 could attempt these):")
        for r in ready[:10]:
            lines.append(f"  - {r['prompt'][:100]}")
    return "\n".join(lines)


# ----------------------------------------------------------------
# Prompt sources
# ----------------------------------------------------------------

def prompts_from_file(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def prompts_from_transcripts(paths: list[Path]) -> list[str]:
    """User prompts out of Claude Code transcript .jsonl files. Tolerant:
    unparseable lines are skipped; command/meta noise is filtered."""
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.jsonl")) if p.is_dir() else [p])

    prompts = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "user":
                continue
            if obj.get("isMeta"):
                continue
            content = (obj.get("message") or {}).get("content")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")
            if not isinstance(content, str):
                continue
            text = content.strip()
            # skip slash-command wrappers, injected tags, tool noise
            if not text or text.startswith("<") or text.startswith("/"):
                continue
            prompts.append(text)
    return prompts
