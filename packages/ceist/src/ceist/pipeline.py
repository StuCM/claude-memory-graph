"""`ceist vocab pipeline`: a graph's baseline vocabulary written by an LLM at
build time, one nodegroup at a time, then measured.

    describe → CRM roles → one analysis per nodegroup → type words and link wording
    per model → a collision pass per model → acceptance questions (a separate
    prompt) → assemble → gate → coverage report

Out dir:
    descriptions/<Model>.json      ceist vocab describe
    vocab/manifest.json, vocab/<Model>/<nodegroup>.json   entries + the "group" block;
                                   each model's type words in the manifest
    cases.json                     the acceptance questions, frozen: kept if present
    bundle.json, report.md
    audit.jsonl                    every prompt sent, in full and hashed
    cache/<key>.json               replies, by nodegroup description and prompt version

Privacy: the LLM sees the schema description (and the CRM roles derived from
it), never a record. Real questions (`--questions`) are masked with `learn`'s
rules before they are sent; the raw text stays in cases.json, on this machine.
Seeds (`--seed`) are phrasings already in use: the LLM extends them, never deletes.
The default LLM is Claude Code headless (`claude -p`) over the user's
subscription, run with no tools from an empty temporary directory.
"""

import hashlib
import json
import shlex
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import bundle as _bundle
from .crm import crm_roles
from .text import plurals

PROMPT_VERSION = "2"
INTENTS = ("filter", "list", "count", "when", "who", "where", "which kind")
CLAUDE = ["claude", "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
          "--setting-sources", "project", "--no-session-persistence",
          "--system-prompt", "You write JSON for an offline search-vocabulary build. "
                             "Reply with the JSON asked for and nothing else."]


class LLMError(RuntimeError):
    pass


def outline(d: dict) -> dict:
    """A model at a glance: its nodegroups and their nodes, for context."""
    groups: dict[str, list] = {}
    for n in d["nodes"]:
        to = " → " + ", ".join(n["targets"]) if n.get("targets") else ""
        groups.setdefault(n.get("nodegroup") or "", []).append(f"{n['alias']} ({n['datatype']}{to})")
    meta = d.get("nodegroups") or {}
    return {"model": d["name"], "about": d.get("description", ""),
            "groups": [{"group": g, "parent": (meta.get(g) or {}).get("parent"), "nodes": ns}
                       for g, ns in sorted(groups.items())]}


def group_nodes(d: dict, group: str, roles: dict, seeds: dict | None = None) -> list[dict]:
    out = []
    for n in d["nodes"]:
        if n.get("nodegroup") != group:
            continue
        x = {k: v for k, v in n.items() if k != "nodegroup"}
        if n["alias"] in roles:
            x["hint"] = roles[n["alias"]]
        if (seeds or {}).get(n["alias"]):
            x["seed"] = seeds[n["alias"]]
        out.append(x)
    return out


GROUP_PROMPT = """You are the offline vocabulary build for a no-LLM natural-language search over \
Arches heritage data. At question time only exact phrase lookup and static word vectors run, so \
the everyday phrasings people use must be written now. You see the schema only, never records.

Analyse ONE nodegroup of the model "{model}": the nodes stored together in one record entry \
(tile). The whole model's outline is given for context, so keep this group distinguishable from \
its siblings. Each node may carry a "hint": a role derived from its CIDOC-CRM class and property \
("reverse" is the inverse property, for reverse phrasings such as "who built X"). Hints are \
derived mechanically: confirm or correct them.

Think about the questions the public, researchers and officers would ask that this group's data \
answers: filtering (which X were …), listing, counting, when, who, where, which kind, and \
combined with other groups.

Reply with ONLY one JSON object:
{{"purpose": "<one sentence: what this group records>",
 "skip": null | {{"reason": "<why nobody asks about it: record-keeping metadata, audit, …>"}},
 "phrases": ["<phrasings that name the group as a whole>", ...],
 "nodes": {{"<alias>": {{"role": "date|actor|place|type|name|identifier|description|measure|unit|link|other",
                       "phrases": ["<lowercase everyday phrasings for this node>", ...],
                       "end_node": "<alias>"}}}},     // dates only: the END date when this is the start
 "combos": [{{"phrases": [...], "node": "<alias the question means>",
             "set": {{"<alias>": "<a label from that node's values>"}}}}],
 "intents": [{{"intent": "filter|list|count|when|who|where|which kind",
              "with": ["<other group of this model>", ...],
              "wordings": ["<a realistic question>", ...]}}],
 "doubts": [{{"node": "<alias>", "phrase": "<a seed you think is wrong>", "why": "…"}}]}}

Rules:
- "nodes" keys are aliases of THIS group only. 3-15 phrases for each node people ask about; \
none for nodes nobody asks about by name.
- A date pair (start/end of one event) is one node with end_node; give the event's verbs \
(built, erected, put up, …). Don't let two events share a phrase.
- An actor link with a role list, or an event with a type list: write combos for commonly asked \
values (designed by → role Architect, demolished → phase type Demolition). Use only labels listed \
in "values". A combo's "set" holds one or more values.
- A unit node (role unit: grams, metres) only describes its measurement's value: give it no \
phrases, since people ask about the value ("weight in grams" is a weight).
- A node's "seed" lists phrasings already in use. They stay whatever you reply: add to them, \
and list any you think wrong under "doubts" instead of leaving them out.
- Metadata and audit groups: "skip" with the reason, and nothing else needed.
- Intents: 2-6 for a group people ask about, each with 2-4 wordings; no record names in them.
Check that your reply parses as JSON.

INPUT:
{payload}
"""

MODEL_PROMPT = """You name the types and links of the model "{model}" for an offline \
search-vocabulary build over Arches heritage data. At question time only exact phrase lookup runs, \
so the words people use must be written now. You see the schema only, never records.

1. Type words: the everyday nouns for one {model} record, singular and plural ("stories", "tales" \
for a model of tales; "places", "sites" for a model of sites). Not the model's own name, which is \
known already, and never a word for one of the "other_models".
2. Link wording: each link joins a {model} record ("from") to records of the "to" models, with \
its CIDOC-CRM property. Give short phrasings for that pair as questions join them ("in", "located \
in", "at" for a monument in a place; "part of", "belongs to" for a story in a larger story). Short \
shared prepositions are fine: the search tells links apart by the types they join. "reverse" \
reads the other way, from the CRM inverse ("contains"); only when "from" is not among "to".
3. "seed_type_words" and each link's "seed" are words already in use. They stay whatever you \
reply: add to them, and list any you think wrong under "doubts" instead of leaving them out.

Reply with ONLY one JSON object:
{{"type_words": ["<lowercase noun>", ...],
 "links": {{"<alias>": {{"phrases": ["..."], "reverse": ["..."]}}}},
 "doubts": [{{"node": "<alias, or null for a type word>", "phrase": "<seed>", "why": "…"}}]}}
Check that your reply parses as JSON.

INPUT:
{payload}
"""

COLLISION_PROMPT = """You are checking the vocabulary of the model "{model}" in an offline \
search-vocabulary build. Each phrase below belongs to more than one entry, so a question using \
it can't be placed. For each, keep the ONE entry it should mean, or say it is deliberately \
ambiguous (the search then asks "did you mean …"). You see the schema only.

Reply with ONLY a JSON array: [{{"phrase": "<phrase>", "keep": <entry i> | "ambiguous"}}, ...]
Check that your reply parses as JSON.

INPUT:
{payload}
"""

CONDITIONS = """{{"node": "<alias>", "value": "<label from its values, when one is meant>", \
"tile": "<its nodegroup, when conditions must hold on one record entry>", \
"link": "<the model a link's record is, for a link>"}}"""

QUESTIONS_PROMPT = """You write acceptance questions for a natural-language search over the \
Arches model "{model}". You see its schema description only. You have NOT seen its vocabulary, \
and must not guess phrasings to suit one: write what real people would ask.

Write 8-12 questions. Each names one phrase that picks a field of this model, and the field it \
must reach; 2 of them should ask for something the model doesn't hold (expect null, so the \
right answer is a refusal). Avoid record names (no people, places or titles): ask about types, \
values, dates and roles. Say what the whole question means too: "conditions" lists every field \
it constrains, which the answer must hold (empty when it asks for the type alone).

Reply with ONLY one JSON object:
{{"cases": [{{"q": "<question>", "phrase": "<the words in q that pick the field>",
             "slot": "date" | "property" | "link:<target model>",
             "intent": "filter|list|count|when|who|where|which kind",
             "expect": null | {{"node": "<alias>",
                              "qualifier": {{"node": "<alias>", "value": "<label from its values>"}},
                              "conditions": [""" + CONDITIONS + """, ...]}}}}]}}
"qualifier" only when the meaning needs a value too (designed by → role Architect). In a \
condition, "value", "tile" and "link" only when they apply.
Check that your reply parses as JSON.

INPUT:
{payload}
"""

LABEL_PROMPT = """You label real questions asked of a natural-language search over Arches models, \
so they can be used as acceptance questions. Names and numbers are masked (<Name>, <number>); \
don't guess them. You see the models' outlines only.

For each question, give the model it asks about, the phrase in it that picks a field (null when \
it names none), the slot, the field that phrase must reach, and the conditions the whole question \
means (empty when it asks for the type alone); or expect null when the models can't answer it.

Reply with ONLY a JSON array:
[{{"i": <index>, "model": "<model>", "phrase": "<words from the question>" | null,
   "slot": "date" | "property" | "link:<target model>" | null,
   "expect": null | {{"node": "<alias>", "qualifier": {{"node": "<alias>", "value": "<label>"}},
                     "conditions": [""" + CONDITIONS + """, ...]}}}}]
Check that your reply parses as JSON.

INPUT:
{payload}
"""


class Runner:
    """Sends prompts to the LLM: cached by key, every real call audited."""

    def __init__(self, out: Path, llm_cmd: str | None = None, model: str | None = None):
        self.cache = out / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.audit = out / "audit.jsonl"
        self.argv = shlex.split(llm_cmd) if llm_cmd else CLAUDE + (["--model", model] if model else [])
        self.claude = llm_cmd is None
        self.model = model or ""
        self.calls = self.hits = 0
        self.failures: list[dict] = []

    def _send(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory() as cwd:
            p = subprocess.run(self.argv, input=prompt, capture_output=True, text=True, cwd=cwd,
                               timeout=1800)
        if p.returncode and not self.claude:
            raise LLMError(f"{self.argv[0]} exited {p.returncode}: {p.stderr.strip()[-300:]}")
        if not self.claude:
            return p.stdout
        try:
            reply, _ = json.JSONDecoder().raw_decode(p.stdout.strip())
        except ValueError:
            raise LLMError(f"claude -p gave no JSON (exit {p.returncode}): "
                           f"{(p.stderr or p.stdout).strip()[-300:]}") from None
        if reply.get("is_error"):
            raise LLMError(f"claude -p: {reply.get('result')}")
        return reply.get("result") or ""

    def ask(self, key: str, prompt: str, check, what: dict):
        """The reply to `prompt`, parsed and passed by `check` (→ errors); one
        retry with the errors shown. None when it still fails, or the LLM errs
        or times out: that call is recorded in `failures` and the run goes on."""
        hit = self.cache / f"{_key(key, self.model)}.json"
        if hit.exists():
            self.hits += 1
            return json.loads(hit.read_text())
        text = prompt
        for _ in range(2):
            self.calls += 1
            sha = hashlib.sha256(text.encode()).hexdigest()
            with open(self.audit, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(what, ts=int(time.time()), sha256=sha, prompt=text),
                                   ensure_ascii=False) + "\n")
            try:
                raw = self._send(text)
            except (LLMError, subprocess.TimeoutExpired) as e:
                errors = [str(e)]
                break
            try:
                reply = _bundle.parse_reply(raw)
                errors = check(reply)
            except ValueError as e:
                reply, errors = None, [f"not JSON: {e}"]
            if not errors:
                hit.write_text(json.dumps(reply, ensure_ascii=False))
                return reply
            text = (prompt + "\n\nYour previous reply was rejected:\n- " + "\n- ".join(errors[:20])
                    + "\nReply again, in full, with these fixed.")
        what["errors"] = errors
        self.failures.append(what)
        return None


def check_group(reply, d: dict, group: str, roles: dict | None = None) -> list[str]:
    """The schema of a nodegroup analysis, against the model's description."""
    if not isinstance(reply, dict):
        return ["the reply is not a JSON object"]
    nodes = {n["alias"]: n for n in d["nodes"]}
    mine = {a for a, n in nodes.items() if n.get("nodegroup") == group}
    groups = set(d.get("nodegroups") or {})
    errors = []
    if not isinstance(reply.get("purpose"), str):
        errors.append('"purpose" must be a string')
    skip = reply.get("skip")
    if skip is not None and not (isinstance(skip, dict) and isinstance(skip.get("reason"), str)):
        errors.append('"skip" must be null or {"reason": "..."}')
    if not _strings(reply.get("phrases", [])):
        errors.append('"phrases" must be a list of strings')
    if not isinstance(reply.get("nodes", {}), dict):
        return errors + ['"nodes" must be an object keyed by alias']
    for a, n in reply.get("nodes", {}).items():
        if a not in mine:
            errors.append(f"nodes: '{a}' is not a node of the group {group}")
        elif not (isinstance(n, dict) and isinstance(n.get("role"), str)
                  and _strings(n.get("phrases", []))):
            errors.append(f"nodes.{a}: needs a role and a list of phrases")
        elif n.get("end_node") and _bundle.kind_of(nodes.get(n["end_node"]) or
                                                   {"datatype": ""}) != "date":
            errors.append(f"nodes.{a}: end_node '{n['end_node']}' is not a date of this model")
        elif n.get("phrases") and "unit" in (n["role"], ((roles or {}).get(a) or {}).get("role")):
            errors.append(f"nodes.{a}: a unit only describes its measurement's value; give it no "
                          "phrases (\"weight in grams\" asks about the weight)")
    for i, c in enumerate(reply.get("combos") or []):
        if not (isinstance(c, dict) and _strings(c.get("phrases")) and c.get("phrases")
                and c.get("node") in mine and isinstance(c.get("set"), dict) and c["set"]):
            errors.append(f"combos[{i}]: needs phrases, a node of this group and a non-empty set")
            continue
        for a, v in c["set"].items():
            values = (nodes.get(a) or {}).get("values")
            if a not in mine:
                errors.append(f"combos[{i}]: '{a}' is not a node of the group {group}")
            elif isinstance(values, list) and v not in values:
                errors.append(f"combos[{i}]: '{v}' is not a value of {a}")
    for i, t in enumerate(reply.get("intents") or []):
        if not (isinstance(t, dict) and t.get("intent") in INTENTS and _strings(t.get("wordings"))
                and t.get("wordings")):
            errors.append(f"intents[{i}]: needs an intent from {', '.join(INTENTS)} and wordings")
        elif any(w not in groups for w in t.get("with") or []):
            errors.append(f"intents[{i}]: 'with' names a group that isn't in the model")
    return errors + _check_doubts(reply)


def _check_doubts(reply: dict) -> list[str]:
    doubts = reply.get("doubts") or []
    if isinstance(doubts, list) and all(isinstance(x, dict) and isinstance(x.get("phrase"), str)
                                        for x in doubts):
        return []
    return ['"doubts" must be a list of {"node", "phrase", "why"}']


def _strings(x) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) for s in x)


def entries_of(reply: dict, d: dict, seeds: dict | None = None) -> list[dict]:
    """The bundle entries a nodegroup analysis gives: one per node with
    phrases, and one per single-value combo (a qualified entry). A node's
    seeds stay among its phrases, whatever the reply says."""
    kinds = {n["alias"]: _bundle.kind_of(n) for n in d["nodes"]}
    nodes = reply.get("nodes") or {}
    out = []
    for a in list(nodes) + [a for a in seeds or {} if a not in nodes]:
        n = nodes.get(a) or {}
        phrases = _union(n.get("phrases") or [], (seeds or {}).get(a) or [])
        if phrases:
            e = {"phrases": phrases, "kind": kinds[a], "node": a}
            if n.get("end_node"):
                e["end_node"] = n["end_node"]
            out.append(e)
    for c in reply.get("combos") or []:
        if len(c["set"]) == 1:
            (qn, qv), = c["set"].items()
            out.append({"phrases": c["phrases"], "kind": kinds[c["node"]], "node": c["node"],
                        "qualifier": {"node": qn, "value": qv}})
    return out


def _union(*lists) -> list[str]:
    return list(dict.fromkeys(x for xs in lists for x in xs))


def group_block(reply: dict) -> dict:
    """The group's own block, in the shape docs/tasks/ceist-group-grounding.md §2 reads."""
    nodes = {a: {k: v for k, v in (("role", n["role"]), ("end_node", n.get("end_node"))) if v}
             for a, n in (reply.get("nodes") or {}).items()}
    answers = {}
    for want, role in (("when", "date"), ("who", "actor"), ("where", "place")):
        a = next((a for a, n in nodes.items() if n["role"] == role), None)
        if a:
            answers[want] = a
    return {"purpose": reply.get("purpose", ""), "skip": reply.get("skip"),
            "phrases": reply.get("phrases", []), "nodes": nodes,
            "combos": [{"phrases": c["phrases"], "node": c["node"], "set": c["set"]}
                       for c in reply.get("combos") or []],
            "answers": answers, "intents": reply.get("intents", [])}


def _key(*parts: str) -> str:
    return hashlib.sha256("\0".join((PROMPT_VERSION,) + parts).encode()).hexdigest()


def build_model(run: Runner, d: dict, roles: dict, vocab_dir: Path, jobs: int = 1,
                seeds: dict | None = None, doubts: list | None = None) -> dict:
    """One analysis per nodegroup, written to vocab/<Model>/<group>.json; {group: status}.
    `seeds` ({alias: phrases}) go to the LLM and stay; what it doubts goes to `doubts`."""
    ctx = outline(d)
    groups = sorted(d.get("nodegroups") or {})
    seeds = seeds or {}

    def one(g):
        payload = {"model": ctx, "group": g, "nodes": group_nodes(d, g, roles, seeds)}
        prompt = GROUP_PROMPT.format(model=d["name"],
                                     payload=json.dumps(payload, ensure_ascii=False, indent=1))
        key = _key("group", d["name"], g, json.dumps(payload["nodes"], sort_keys=True))
        what = {"kind": "group", "model": d["name"], "group": g}
        return g, run.ask(key, prompt, lambda r: check_group(r, d, g, roles), what), what

    status = {}
    model_dir = vocab_dir / d["name"]
    model_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max(jobs, 1)) as pool:
        for g, reply, what in pool.map(one, groups):
            if reply is None:
                status[g] = "failed: " + "; ".join(what.get("errors", [])[:3])
                continue
            mine = {n["alias"] for n in d["nodes"] if n.get("nodegroup") == g}
            entries = entries_of(reply, d, {a: p for a, p in seeds.items() if a in mine})
            if doubts is not None:
                doubts += [dict(x, model=d["name"]) for x in reply.get("doubts") or []]
            errors, _ = _bundle.validate(d, entries)
            if errors:
                status[g] = "failed: " + "; ".join(errors[:3])
                continue
            (model_dir / f"{g}.json").write_text(json.dumps(
                {"model": d["name"], "nodegroup": g, "entries": entries, "group": group_block(reply)},
                indent=1, ensure_ascii=False) + "\n")
            status[g] = "skipped" if reply.get("skip") else ("built" if entries else "empty")
    return status


def base_type_words(d: dict) -> set[str]:
    """The words `ArchesVocabulary.type_words` gives a model without help."""
    words = set()
    for name in (d["name"], (d.get("slug") or "").replace("_", " ")):
        if name:
            words |= plurals(name)
    return words


def links_of(d: dict, roles: dict, names: set[str], seeds: dict) -> list[dict]:
    """The model's links to models in this build, each with the pair it joins."""
    out = []
    for n in d["nodes"]:
        to = [t for t in n.get("targets") or [] if t in names]
        if _bundle.kind_of(n) != "link" or not to:
            continue
        hint = roles.get(n["alias"]) or {}
        x = {"alias": n["alias"], "name": n.get("label") or n["name"], "group": n.get("nodegroup"),
             "from": d["name"], "to": to, "crm": hint.get("crm", ""), "reverse": hint.get("reverse", "")}
        if seeds.get(n["alias"]):
            x["seed"] = seeds[n["alias"]]
        out.append(x)
    return out


def name_model(run: Runner, d: dict, roles: dict, descriptions: dict,
               seeds: dict) -> tuple[list[str], dict[str, list[str]], list[dict]]:
    """One call for the model's type words and its links' wording by the types
    they join: (type words, {link alias: phrases}, doubts). Seeds stay."""
    others = {n: x for n, x in descriptions.items() if n != d["name"]}
    taken = set().union(*(base_type_words(x) for x in others.values()),
                        *(seeds["types"].get(n, []) for n in others))
    links = links_of(d, roles, set(descriptions), seeds["nodes"].get(d["name"], {}))
    payload = {"model": d["name"], "about": d.get("description", ""), "other_models": sorted(others),
               "seed_type_words": seeds["types"].get(d["name"], []), "links": links}

    def check(r):
        if not isinstance(r, dict):
            return ["the reply is not a JSON object"]
        if _strings(r.get("type_words", [])):
            errors = [f"type word '{w}' names another model" for w in r.get("type_words", [])
                      if w.strip().lower() in taken]
        else:
            errors = ['"type_words" must be a list of strings']
        sent = {x["alias"] for x in links}
        got = r.get("links", {})
        if not isinstance(got, dict):
            return errors + ['"links" must be an object keyed by alias']
        for a, x in got.items():
            if a not in sent:
                errors.append(f"links: '{a}' is not one of the links given")
            elif not (isinstance(x, dict) and _strings(x.get("phrases", []))
                      and _strings(x.get("reverse", []))):
                errors.append(f"links.{a}: needs lists of phrases and reverse")
        return errors + _check_doubts(r)

    prompt = MODEL_PROMPT.format(model=d["name"],
                                 payload=json.dumps(payload, ensure_ascii=False, indent=1))
    reply = run.ask(_key("model", d["name"], json.dumps(payload, sort_keys=True)), prompt, check,
                    {"kind": "model", "model": d["name"]}) or {}
    words = _union(seeds["types"].get(d["name"], []),
                   [w.strip().lower() for w in reply.get("type_words", [])])
    phrases = {}
    for x in links:
        said = reply.get("links", {}).get(x["alias"]) or {}
        reverse = said.get("reverse", []) if d["name"] not in x["to"] else []   # same types: no direction
        phrases[x["alias"]] = _union(x.get("seed", []), said.get("phrases", []), reverse)
    return words, phrases, [dict(x, model=d["name"]) for x in reply.get("doubts") or []]


def settle_type_words(words: dict[str, list[str]], seeds: dict) -> tuple[dict[str, list[str]], list[str]]:
    """A type word two models claim names neither, unless it is one model's
    seed; (each model's words, what was dropped and from which models)."""
    claims: dict[str, set[str]] = {}
    for m, ws in words.items():
        for w in ws:
            claims.setdefault(w, set()).add(m)
    keep, dropped = {}, []
    for w, ms in sorted(claims.items()):
        seeded = {m for m in ms if w in seeds["types"].get(m, [])}
        keep[w] = ms if len(ms) == 1 else seeded if len(seeded) == 1 else set()
        if keep[w] != ms:
            dropped.append(f"'{w}' ({', '.join(sorted(ms - keep[w]))})")
    return {m: [w for w in ws if m in keep[w]] for m, ws in words.items()}, dropped


def add_link_phrases(d: dict, vocab_dir: Path, phrases: dict[str, list[str]]) -> None:
    """Each link's phrases joined to its unqualified entry in its group file."""
    group_of = {n["alias"]: n.get("nodegroup") for n in d["nodes"]}
    for a, ps in phrases.items():
        if not ps:
            continue
        p = vocab_dir / d["name"] / f"{group_of[a]}.json"
        f = (json.loads(p.read_text()) if p.exists()
             else {"model": d["name"], "nodegroup": group_of[a], "entries": []})
        e = next((e for e in f["entries"] if e["node"] == a and not e.get("qualifier")), None)
        if e is None:
            f["entries"].append({"phrases": ps, "kind": "link", "node": a})
        else:
            e["phrases"] = _union(e["phrases"], ps)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(f, indent=1, ensure_ascii=False) + "\n")


def _apart(entries: list[dict], targets: dict) -> bool:
    """Unqualified links whose targets don't overlap: the grounder picks
    between them by the types a question names (ground._fit_relations)."""
    if any(e["kind"] != "link" or e.get("qualifier") for e in entries):
        return False
    seen: set[str] = set()
    for e in entries:
        to = set(targets.get(e["node"]) or [])
        if not to or to & seen:
            return False
        seen |= to
    return True


def resolve_collisions(run: Runner, d: dict, vocab_dir: Path, seeds: dict | None = None) -> list[dict]:
    """`validate`'s shared phrases for one model, back to the LLM: each is kept
    by one entry, or left on all of them as deliberately ambiguous. Links that
    join different types keep a shared phrase, and no entry loses a seed."""
    files = {p: json.loads(p.read_text()) for p in sorted((vocab_dir / d["name"]).glob("*.json"))}
    refs = [(p, e) for p, f in files.items() for e in f["entries"]]
    targets = {n["alias"]: n.get("targets") for n in d["nodes"]}
    shared, done = {}, []
    for ph, owners in sorted(_bundle.shared_phrases([e for _, e in refs]).items()):
        if _apart([refs[i][1] for i in owners], targets):
            done.append({"model": d["name"], "phrase": ph, "keep": "all: links joining different types"})
        else:
            shared[ph] = owners
    if not shared:
        return done
    seeds = seeds or {}
    labels = {n["alias"]: n.get("label") or n["name"] for n in d["nodes"]}
    items = [{"phrase": ph, "entries": [{"i": i, "node": refs[i][1]["node"],
                                         "label": labels.get(refs[i][1]["node"]),
                                         "group": refs[i][0].stem,
                                         "qualifier": refs[i][1].get("qualifier")} for i in owners]}
             for ph, owners in sorted(shared.items())]

    def check(reply):
        if not isinstance(reply, list):
            return ["the reply is not a JSON array"]
        return [f"'{r.get('phrase')}': keep {r.get('keep')!r} is not one of its entries"
                for r in reply if isinstance(r, dict) and r.get("phrase") in shared
                and r.get("keep") != "ambiguous" and r.get("keep") not in shared[r["phrase"]]]

    prompt = COLLISION_PROMPT.format(model=d["name"],
                                     payload=json.dumps(items, ensure_ascii=False, indent=1))
    reply = run.ask(_key("collisions", hashlib.sha256(prompt.encode()).hexdigest()), prompt, check,
                    {"kind": "collisions", "model": d["name"]}) or []
    for r in reply:
        ph, keep = r.get("phrase"), r.get("keep")
        if ph not in shared:
            continue
        done.append({"model": d["name"], "phrase": ph, "keep": keep if keep == "ambiguous"
                     else f"{refs[keep][0].stem}.{refs[keep][1]['node']}"})
        if keep == "ambiguous":
            continue
        for i in shared[ph]:
            e = refs[i][1]
            seeded = not e.get("qualifier") and ph in seeds.get(e["node"], [])
            if i != keep and not seeded:
                e["phrases"] = [x for x in e["phrases"] if x.strip().lower() != ph]
    for p, f in files.items():
        f["entries"] = [e for e in f["entries"] if e["phrases"]]
        p.write_text(json.dumps(f, indent=1, ensure_ascii=False) + "\n")
    return done


def _check_cases(cases, descriptions: dict, model: str | None = None, need_q: bool = True,
                 need_phrase: bool = True) -> list[str]:
    errors = []
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            errors.append(f"case {i}: not an object")
            continue
        d = descriptions.get(model or c.get("model"))
        if d is None:
            errors.append(f"case {i}: no such model")
            continue
        if need_q and not (isinstance(c.get("q"), str) and c["q"].strip()):
            errors.append(f"case {i}: needs the question, \"q\"")
        if "expect" not in c:
            errors.append(f"case {i}: needs \"expect\" (null when the answer is a refusal)")
        nodes = {n["alias"]: n for n in d["nodes"]}
        slot = c.get("slot") or ""
        phrase = c.get("phrase")
        if (need_phrase or phrase is not None) and not (
                isinstance(phrase, str) and phrase
                and (slot in ("date", "property") or slot.startswith("link:"))):
            errors.append(f"case {i}: needs a phrase and a slot of date, property or link:<Model>")
        x = c.get("expect")
        if x is None:
            continue
        if not isinstance(x, dict):
            errors.append(f"case {i}: expect {x!r} is not null or an object")
            continue
        if (phrase or "node" in x) and x.get("node") not in nodes:
            errors.append(f"case {i}: expect.node {x.get('node')!r} is not a node of {d['name']}")
        q = x.get("qualifier")
        if q and (q.get("node") not in nodes or not _a_value(nodes[q["node"]], q.get("value"))):
            errors.append(f"case {i}: qualifier {q!r} is not a node and value of {d['name']}")
        if not isinstance(x.get("conditions"), list):
            errors.append(f"case {i}: expect needs \"conditions\", a list (empty for the type alone)")
            continue
        for w in x["conditions"]:
            n = nodes.get(w.get("node")) if isinstance(w, dict) else None
            if n is None:
                errors.append(f"case {i}: condition {w!r} is not on a node of {d['name']}")
            elif w.get("value") is not None and not _a_value(n, w["value"]):
                errors.append(f"case {i}: '{w['value']}' is not a value of {w['node']}")
            elif w.get("tile") is not None and w["tile"] not in (d.get("nodegroups") or {}):
                errors.append(f"case {i}: tile '{w['tile']}' is not a nodegroup of {d['name']}")
            elif w.get("link") is not None and w["link"] not in descriptions:
                errors.append(f"case {i}: link '{w['link']}' is not a model")
    return errors


def _a_value(node: dict, value) -> bool:
    """A label of the node's values; any string when its list wasn't sent."""
    values = node.get("values")
    return isinstance(value, str) and (not isinstance(values, list) or not values or value in values)


def write_cases(run: Runner, descriptions: dict, roles: dict, real: list[str]) -> list[dict]:
    """Acceptance cases per model, from the descriptions only, never the
    vocabulary; plus the real questions, labelled with their text masked."""
    from .learn import mask
    cases = []
    for name, d in sorted(descriptions.items()):
        payload = {"model": outline(d), "nodes": [dict(n, **({"hint": roles[name][n["alias"]]}
                                                         if n["alias"] in roles[name] else {}))
                                                  for n in d["nodes"]]}
        prompt = QUESTIONS_PROMPT.format(model=name,
                                         payload=json.dumps(payload, ensure_ascii=False, indent=1))
        reply = run.ask(_key("questions", name, json.dumps(payload, sort_keys=True)), prompt,
                        lambda r, n=name: (["no \"cases\" list"] if not isinstance(r, dict)
                                           or not isinstance(r.get("cases"), list)
                                           else _check_cases(r["cases"], descriptions, n)),
                        {"kind": "questions", "model": name})
        for c in (reply or {}).get("cases", []):
            cases.append({"model": name, "q": c["q"], "phrase": c["phrase"], "slot": c["slot"],
                          "expect": c["expect"], "source": "llm"})
    if real:
        masked = [{"i": i, "q": mask(q)} for i, q in enumerate(real)]
        payload = {"models": [outline(d) for _, d in sorted(descriptions.items())],
                   "questions": masked}
        prompt = LABEL_PROMPT.format(payload=json.dumps(payload, ensure_ascii=False, indent=1))

        def check(r):
            if not isinstance(r, list):
                return ["the reply is not a JSON array"]
            bad = [f"item {n}: no question {x.get('i') if isinstance(x, dict) else x!r}"
                   for n, x in enumerate(r) if not isinstance(x, dict)
                   or not isinstance(x.get("i"), int) or not 0 <= x["i"] < len(real)]
            return bad + _check_cases(r, descriptions, need_q=False, need_phrase=False)

        for x in run.ask(_key("label", json.dumps(payload, sort_keys=True)), prompt, check,
                         {"kind": "label"}) or []:
            c = {"model": x["model"], "q": real[x["i"]], "phrase": x.get("phrase"),
                 "slot": x.get("slot"), "expect": x["expect"], "source": "real"}
            cases.append({k: v for k, v in c.items() if v is not None or k == "expect"})
    return cases


def _fields(plan) -> set[tuple[str, str, str | None, str | None]]:
    """(tile, alias, value label, link target type) for each condition on the
    plan's own type; tile is the group of the OnTile it is in, else ""."""
    from .plan import DateRange, HasValue, LinkTo, Not, OnTile
    out = set()
    todo = [("", c) for c in plan.where]
    while todo:
        tile, c = todo.pop()
        while isinstance(c, Not):
            c = c.condition
        if isinstance(c, OnTile):
            todo += [(c.group, x) for x in c.conditions]
        elif isinstance(c, LinkTo) and c.relation:
            target = c.target.entity.type if hasattr(c.target, "entity") else c.target.type
            out.add((tile, c.relation.split("#")[0], None, target))
            if c.qualifier is not None:
                out.add((tile, c.qualifier.field, c.qualifier.label, None))
        elif isinstance(c, HasValue):
            out.add((tile, c.field, c.label, None))
        elif isinstance(c, DateRange):
            out.add((tile, c.field, None, None))
    return out


def _judge_conditions(want: list[dict], fields, ends: dict[str, str]) -> str:
    """Each expected {"node", "value"?, "tile"?, "link"?} in the plan (a date by
    either end): right; one missing (broader than asked): partial; one there
    with another value, tile or target type: dangerous."""
    missing = False
    for w in want:
        names = {w["node"], ends.get(w["node"])}
        here = [(t, label, to) for t, f, label, to in fields if f in names]
        if not here:
            missing = True
        elif not any((w.get("value") is None or (label or "").lower() == w["value"].lower())
                     and (w.get("tile") is None or t == w["tile"])
                     and (w.get("link") is None or to == w["link"]) for t, label, to in here):
            return "dangerous"
    return "partial" if missing else "right"


def judge_plan(case: dict, m, ends: dict[str, str]) -> str:
    """right / partial / dangerous / missed / refused for a whole interpretation:
    the plan must be of the case's model and hold the expected conditions, or,
    without them, use the expected node (either end of a date) and qualifier.
    A plan with the right node and extra conditions counts."""
    answered = m.plan is not None and not m.refused
    x = case["expect"]
    if x is None:
        return "dangerous" if answered else "refused"
    if not answered:
        return "missed"
    if m.plan.type != case["model"]:
        return "dangerous"
    fields = _fields(m.plan)
    if "conditions" in x:
        return _judge_conditions(x["conditions"], fields, ends)
    nodes = {f for _, f, _, _ in fields}
    if x["node"] not in nodes and ends.get(x["node"]) not in nodes:
        return "dangerous"
    want = ((x.get("qualifier") or {}).get("value") or "").lower()
    if want and want not in {(label or "").lower() for _, _, label, _ in fields}:
        return "partial"
    return "right"


def planner_run(graphs_dir: Path, reference: Path | None, bundle: dict, cases: list[dict], cfg):
    """Every case through `interpret`, with no records loaded: (counts, rows)."""
    from . import config
    from .arches import ArchesVocabulary, graph_doc, load_reference_data
    from .arches_describe import reference_files
    from .narrate import narrate
    from .plan import interpret
    rdm, alts = load_reference_data(reference_files(reference)) if reference else (None, {})
    vocab = ArchesVocabulary([graph_doc(p) for p in sorted(graphs_dir.glob("*.json"))], rdm,
                             alt_labels=alts, bundle=bundle)
    chain = config.chain(cfg)
    ends = {e["node"]: e["end_node"] for m in bundle["models"].values() for e in m["entries"]
            if e.get("end_node")}
    counts = dict.fromkeys(["right", "partial", "dangerous", "missed", "refused"], 0)
    rows = []
    for c in cases:
        m = interpret(vocab, c["q"], matcher=chain)
        outcome = judge_plan(c, m, ends)
        counts[outcome] += 1
        rows.append({"q": c["q"], "outcome": outcome, "refused": m.refused,
                     "plan": narrate(m.plan) if m.plan is not None else None})
    return counts, rows


def load_seeds(paths, descriptions: dict) -> tuple[dict, list[str]]:
    """Phrasings already in use, which the LLM extends and never deletes:
    {"types": {Model: [word]}, "nodes": {Model: {alias: [phrase]}}}, and warnings.
    A seed is a bundle, a vocab directory, or a phrasings file in the shape of
    `ArchesVocabulary`'s arguments: {"extra_type_words": {word: Model},
    "relation_forms": {alias: [phrase]}, "date_forms": {alias: [phrase]}}, whose
    forms go to that alias in every model. Qualified entries aren't seeds."""
    seeds: dict = {"types": {}, "nodes": {}}
    warnings = []
    aliases = {m: {n["alias"] for n in d["nodes"]} for m, d in descriptions.items()}

    def add(model, alias, phrases, src):
        if alias not in aliases.get(model, ()):
            warnings.append(f"{src}: no node '{alias}' in {model}; not seeded")
            return
        mine = seeds["nodes"].setdefault(model, {}).setdefault(alias, [])
        mine[:] = _union(mine, [p.strip().lower() for p in phrases if p.strip()])

    for path in map(Path, paths or []):
        if path.is_dir():
            doc = {"models": {v["model"]: v for v in _bundle.read_vocab(path)[0]}}
        else:
            doc = json.loads(path.read_text())
        for w, model in (doc.get("extra_type_words") or {}).items():
            if model in descriptions:
                words = seeds["types"].setdefault(model, [])
                words[:] = _union(words, [w.strip().lower()])
            else:
                warnings.append(f"{path}: type word '{w}' names {model}, not a model here")
        for model, v in (doc.get("models") or {}).items():
            if model not in descriptions:
                warnings.append(f"{path}: {model} is not a model here; not seeded")
                continue
            for w in v.get("type_words") or []:
                words = seeds["types"].setdefault(model, [])
                words[:] = _union(words, [w.strip().lower()])
            for e in v.get("entries") or []:
                if not e.get("qualifier"):
                    add(model, e["node"], e["phrases"], path)
        for key in ("relation_forms", "date_forms"):
            for alias, phrases in (doc.get(key) or {}).items():
                owners = [m for m in descriptions if alias in aliases[m]]
                if not owners:
                    warnings.append(f"{path}: no model has a node '{alias}'; not seeded")
                for m in owners:
                    add(m, alias, phrases, path)
    return seeds, warnings


def coverage(descriptions: dict, vocab_dir: Path, status: dict) -> dict:
    """Per model: nodegroups built / skipped on purpose / missed / failed, and
    the nodes with no phrasings, split into skipped on purpose and missed."""
    out = {}
    for name, d in sorted(descriptions.items()):
        covered, skipped_groups = set(), set()
        for p in (vocab_dir / name).glob("*.json"):
            f = json.loads(p.read_text())
            if (f.get("group") or {}).get("skip"):
                skipped_groups.add(p.stem)
            for e in f["entries"]:
                covered |= {e["node"], e.get("end_node"), (e.get("qualifier") or {}).get("node")}
            covered |= {a for c in (f.get("group") or {}).get("combos", []) for a in c["set"]}
        st = status.get(name, {})
        bare = [n for n in d["nodes"] if n["alias"] not in covered]
        out[name] = {
            "groups": len(d.get("nodegroups") or {}),
            "built": sorted(g for g, s in st.items() if s == "built"),
            "skipped": sorted(skipped_groups),
            "missed": sorted(g for g, s in st.items() if s == "empty"),
            "failed": {g: s for g, s in st.items() if s.startswith("failed")},
            "nodes": len(d["nodes"]),
            "nodes_skipped": sorted(n["alias"] for n in bare if n.get("nodegroup") in skipped_groups),
            "nodes_missed": sorted(n["alias"] for n in bare if n.get("nodegroup") not in skipped_groups),
        }
    return out


def one_word_group_phrases(b: dict) -> list[str]:
    """Each group whose own phrases include a single word ("county"), as "Model group: words"."""
    out = []
    for model, d in sorted(b["models"].items()):
        for name, grp in sorted((d.get("groups") or {}).items()):
            words = [p for p in grp.get("phrases") or [] if len(p.split()) == 1]
            if words:
                out.append(f"{model} {name}: {', '.join(words)}")
    return out


def report(cov: dict, phrase, planner: tuple, gate: list[str], run: Runner,
           warnings: list[str] = (), types: dict | None = None, doubts: list = ()) -> str:
    from .evaluate import report as eval_report
    counts, rows = planner
    lines = ["# ceist vocab pipeline", "",
             f"LLM calls: {run.calls} ({run.hits} answered from the cache).", "",
             "## Gate", "", "**" + ("passed" if not gate else "failed: " + "; ".join(gate)) + "**", "",
             *[f"Warning: {w}" for w in warnings], *([""] if warnings else []),
             eval_report(phrase), "## Planner level (interpret, no records loaded)", "",
             "| right | partial | dangerous | missed | refused correctly |", "| --- | --- | --- | --- | --- |",
             f"| {counts['right']} | {counts['partial']} | **{counts['dangerous']}** | "
             f"{counts['missed']} | {counts['refused']} |", ""]
    bad = [r for r in rows if r["outcome"] == "dangerous"]
    if bad:
        lines += ["Dangerous plans:", ""] + [f"- {r['q']} → {r['plan']}" for r in bad] + [""]
    lines += ["## Coverage", "",
              "| model | nodegroups | built | skipped on purpose | missed | failed | nodes | "
              "nodes skipped | nodes missed |", "| --- " * 9 + "|"]
    for name, c in cov.items():
        lines.append(f"| {name} | {c['groups']} | {len(c['built'])} | {len(c['skipped'])} | "
                     f"{len(c['missed'])} | {len(c['failed'])} | {c['nodes']} | "
                     f"{len(c['nodes_skipped'])} | {len(c['nodes_missed'])} |")
    lines.append("")
    for name, c in cov.items():
        for g, why in c["failed"].items():
            lines.append(f"- {name}.{g} {why}")
        if c["missed"]:
            lines.append(f"- {name}, groups with no phrasings and no reason: {', '.join(c['missed'])}")
        if c["nodes_missed"]:
            lines.append(f"- {name}, nodes missed: {', '.join(c['nodes_missed'])}")
    if types:
        lines += ["", "## Type words", ""] + [f"- {m}: {', '.join(ws) or '(none)'}"
                                              for m, ws in sorted(types.items())]
    if doubts:
        lines += ["", "## Seeds the LLM doubts (kept)", ""] + [
            f"- {x['model']}{'.' + x['node'] if x.get('node') else ''} '{x['phrase']}': "
            f"{x.get('why', '')}" for x in doubts]
    if run.failures:
        lines += ["", "## Failed calls", ""] + [
            f"- {f['kind']} {f.get('model', '')}{'.' + f['group'] if f.get('group') else ''}: "
            + "; ".join(f["errors"][:3]) for f in run.failures]
    return "\n".join(lines) + "\n"


def run(graphs: str | Path, out: str | Path, reference=None, questions=None, llm_cmd=None,
        model=None, models=None, config_path=None, min_right=None, max_dangerous=None,
        jobs: int = 1, log=print, seeds=None) -> int:
    """The whole pipeline; 0 when the gate passes, 1 when it doesn't."""
    from . import config
    from .arches_describe import describe
    from .evaluate import evaluate
    graphs, out = Path(graphs), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    desc_dir, vocab_dir = out / "descriptions", out / "vocab"
    descriptions = describe(graphs, desc_dir, reference)
    if models:
        unknown = set(models) - set(descriptions)
        if unknown:
            raise ValueError(f"no such model: {', '.join(sorted(unknown))}")
        for p in desc_dir.glob("*.json"):
            if p.stem not in models:
                p.unlink()
        descriptions = {k: v for k, v in descriptions.items() if k in models}
    roles = {}
    for p in sorted(graphs.glob("*.json")):
        doc = json.loads(p.read_text())
        g = doc["graph"][0] if "graph" in doc else doc
        name = g["name"].get("en") if isinstance(g["name"], dict) else g["name"]
        if name in descriptions:
            roles[name] = crm_roles(g)
    seeded, warnings = load_seeds(seeds, descriptions)
    llm = Runner(out, llm_cmd, model)
    status, doubts, types = {}, [], {}
    for name, d in sorted(descriptions.items()):
        status[name] = build_model(llm, d, roles[name], vocab_dir, jobs,
                                   seeded["nodes"].get(name), doubts)
        n = sum(1 for s in status[name].values() if s == "built")
        log(f"{name}: {n}/{len(status[name])} nodegroups built")
    for name, d in sorted(descriptions.items()):
        types[name], links, said = name_model(llm, d, roles[name], descriptions, seeded)
        add_link_phrases(d, vocab_dir, links)
        doubts += said
    types, dropped = settle_type_words(types, seeded)
    if dropped:
        warnings.append("type words two models claimed, dropped: " + ", ".join(dropped))
    collisions = []
    for name, d in sorted(descriptions.items()):
        collisions += resolve_collisions(llm, d, vocab_dir, seeded["nodes"].get(name))
    (out / "collisions.json").write_text(json.dumps(collisions, indent=1, ensure_ascii=False) + "\n")
    manifest = _bundle.manifest(descriptions)
    for name, words in types.items():
        manifest["models"][name]["type_words"] = words
    (vocab_dir / _bundle.MANIFEST).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")

    cases_path = out / "cases.json"
    if cases_path.exists():
        log(f"{cases_path}: frozen, reused")
        cases = json.loads(cases_path.read_text())["cases"]
    else:
        real = ([q.strip() for q in Path(questions).read_text().splitlines()
                 if q.strip() and not q.lstrip().startswith("#")] if questions else [])
        cases = write_cases(llm, descriptions, roles, real)
        if any(f["kind"] in ("questions", "label") for f in llm.failures):
            cases_path = out / "cases.unfrozen.json"   # a rerun asks the failed ones again
        cases_path.write_text(json.dumps({"_about": "Written from the descriptions only; frozen.",
                                          "cases": cases}, indent=1, ensure_ascii=False) + "\n")

    b, errors, _ = _bundle.assemble(desc_dir, vocab_dir, graphs)
    bundle_path = out / "bundle.json"
    bundle_path.write_text(json.dumps(b, separators=(",", ":")))
    cfg = config.load(config_path)
    phrase = evaluate(bundle_path, cases_path, cfg)
    planner = planner_run(graphs, Path(reference) if reference else None, b, cases, cfg)
    gate = [f"bundle: {e}" for e in errors]
    if not cases:
        if min_right is not None or max_dangerous is not None:
            gate.append("no acceptance cases")
        else:
            warnings.append("no acceptance cases: nothing was measured")
    if min_right is not None and phrase.counts["right"] < min_right:
        gate.append(f"right {phrase.counts['right']} < {min_right}")
    if max_dangerous is not None:
        for level, n in (("phrase", phrase.counts["dangerous"]), ("planner", planner[0]["dangerous"])):
            if n > max_dangerous:
                gate.append(f"{level} dangerous {n} > {max_dangerous}")
    short = one_word_group_phrases(b)
    if short:
        warnings.append("one-word group phrases (each takes its word anywhere outside a "
                        "record's name): " + "; ".join(short))
    text = report(coverage(descriptions, vocab_dir, status), phrase, planner, gate, llm, warnings,
                  types, doubts)
    (out / "report.md").write_text(text)
    log(text)
    return 1 if gate else 0
