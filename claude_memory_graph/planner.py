"""Query planner v0 — compose SPARQL from a question's shape. No LLM, no parser.

The graph's own vocabulary is the lexicon: relation verb forms and
domain/range hints come from the schema graph (store.relation_lexicon),
entity names from the gate's corpus (same matcher as memory_search),
model nouns from the ontology, plus a small closed modifier lexicon.

Pipeline: shape check → ground → compose one SPARQL query → execute,
with a confidence gate: weak grounding or zero rows degrades to
neighbourhood recall / search — the floor is exactly today's behaviour,
and the planner never guesses.

v0 grammar (docs/QUERY-PLANNING.md, docs/tasks/query-planner-v0.md):
1–2 typed variables · ≤2 relation edges · ≤1 entity anchor ·
recency/status modifiers · CONTAINS for one ungrounded noun.
Tense modifiers (currently/previously) are the temporal-query-modifiers
task; reads here keep the open-edges-only default like every other read.
"""

import re
from dataclasses import dataclass, field

from claude_hook_kit import terms_pos

from .gate.recall import _corpus, _idf, _score
from .namespaces import GRAPH_CONCEPTS, GRAPH_LINKS
from .ontology import CONCEPT_TYPES, RESOURCE_MODELS
from .store import MemoryStore

# ponytail: hardcoded thresholds; promote to gate config when the coverage
# experiment yields real numbers to tune against.
COVERAGE_MIN = 0.6
RECENT_LIMIT = 5
ROW_LIMIT = 25

WH = {"what", "which", "who", "whom", "whose", "why", "when", "how", "where"}
_AUX = {"is", "are", "was", "were", "do", "does", "did", "has", "have", "had",
        "can", "could", "should", "would", "any"}
# question verbs that shape intent but name nothing in the graph
_HINTS = {"choose": "Decision", "chose": "Decision", "chosen": "Decision",
          "decide": "Decision", "decided": "Decision"}
_RECENT = {"recent", "recently", "latest", "newest"}
_STATUS = {"active": "active", "open": "active", "ongoing": "active",
           "done": "done", "completed": "done", "finished": "done",
           "blocked": "blocked"}
_SALIENT = {"Decision": ["rationale", "outcome"], "Pattern": ["description"],
            "Task": ["status", "description"]}
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")


def _salient(model: str, wh: str = "") -> list[str]:
    props = _SALIENT.get(model, ["description", "status"])
    return (["date"] + props) if wh == "when" else props


def _model_nouns() -> dict[str, str]:
    nouns: dict[str, str] = {}
    for t in RESOURCE_MODELS + CONCEPT_TYPES:
        low = t.lower()
        nouns[low] = t
        nouns[low + "s"] = t
        if low.endswith("y"):
            nouns[low[:-1] + "ies"] = t
    nouns["people"] = nouns["persons"] = "Person"
    return nouns


@dataclass
class Node:
    kind: str                 # "var" | "anchor"
    type: str                 # model or concept type
    pos: float                # word index, for word-order rules
    var: str = ""             # SPARQL variable (vars)
    iri: str = ""             # bound IRI (anchors)
    name: str = ""            # display name (anchors)
    gid: str | None = None    # resource graph id (anchors; None = concept)
    match_terms: list[str] = field(default_factory=list)

    def ref(self) -> str:
        return self.var if self.kind == "var" else f"<{self.iri}>"


@dataclass
class Edge:
    relation: str
    pos: float
    form: str = ""            # the verb form that grounded it (telemetry)
    source: Node | None = None
    target: Node | None = None


@dataclass
class Grounding:
    wh: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    recent: bool = False
    status: str | None = None
    contains: str | None = None
    subject: Node | None = None
    anchor: Node | None = None
    coverage: float = 0.0
    uncovered: list[str] = field(default_factory=list)
    refuse: str = ""                              # out-of-grammar reason
    notes: list[str] = field(default_factory=list)  # --explain lines

    def vars(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "var"]


def is_question(text: str) -> bool:
    stripped = text.strip()
    words = _WORD_RE.findall(stripped.lower())
    return bool(stripped.endswith("?")
                or (words and (words[0] in WH or words[0] in _AUX)))


def ground(store: MemoryStore, text: str) -> Grounding:
    g = Grounding()
    raw = text.lower()
    words = [(i, m.start(), m.end(), m.group())
             for i, m in enumerate(_WORD_RE.finditer(raw))]
    terms = {w for _, w in terms_pos(text)}
    consumed: set[int] = set()          # word indices grounded to something

    def parts_of(word: str) -> set[str]:
        # raw words like "memory-graph" must meet terms ("memory","graph")
        return {p for p in re.split(r"[^a-z0-9]+", word) if p} & terms

    if words and (words[0][3] in WH or words[0][3] in _AUX):
        if words[0][3] in WH:
            g.wh = words[0][3]
        consumed.add(0)

    # ── relations: longest verb-form first, matched on the RAW text
    # (verb forms contain stopwords the tokenizer drops: "works on")
    lexicon = store.relation_lexicon()
    forms = sorted(((f, rel) for rel, e in lexicon.items() for f in e["verbForms"]),
                   key=lambda x: -len(x[0]))
    taken_spans: list[tuple[int, int]] = []
    matched_rels: set[str] = set()
    for form, rel in forms:
        if rel in matched_rels:
            continue
        m = re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", raw)
        if not m or any(m.start() < e and m.end() > s for s, e in taken_spans):
            continue
        matched_rels.add(rel)
        taken_spans.append((m.start(), m.end()))
        first_word = None
        for i, s, e, _w in words:
            if s >= m.start() and e <= m.end():
                consumed.add(i)
                first_word = i if first_word is None else first_word
        g.edges.append(Edge(rel, float(first_word if first_word is not None else 0),
                            form=form))
        g.notes.append(f"'{form}' → relation {rel}")
    g.edges.sort(key=lambda e: e.pos)

    # ── model nouns, modifiers, hints
    nouns = _model_nouns()
    seen_types: dict[str, Node] = {}
    for i, _s, _e, w in words:
        if i in consumed:
            continue
        if w in nouns:
            t = nouns[w]
            if t not in seen_types:
                node = Node("var", t, float(i), var=f"?v{len(seen_types)}")
                seen_types[t] = node
                g.nodes.append(node)
                g.notes.append(f"'{w}' → typed variable {node.var} : {t}")
            consumed.add(i)
        elif w in _RECENT:
            g.recent = True
            consumed.add(i)
            g.notes.append(f"'{w}' → ORDER BY DESC(updatedAt) LIMIT {RECENT_LIMIT}")
        elif w in _STATUS:
            g.status = _STATUS[w]
            consumed.add(i)
            g.notes.append(f"'{w}' → status filter '{_STATUS[w]}'")
        elif w in _HINTS:
            consumed.add(i)
            if _HINTS[w] not in seen_types:
                node = Node("var", _HINTS[w], float(i), var=f"?v{len(seen_types)}")
                seen_types[_HINTS[w]] = node
                g.nodes.append(node)
                g.notes.append(f"'{w}' → implies {_HINTS[w]} variable {node.var}")
        elif w in _AUX:
            consumed.add(i)

    # wh-words that imply a typed subject
    for wh_word, implied in (("who", "Person"), ("why", "Decision"), ("how", "Pattern")):
        if g.wh == wh_word and implied not in seen_types:
            node = Node("var", implied, 0.0, var=f"?v{len(seen_types)}")
            seen_types[implied] = node
            g.nodes.append(node)
            g.notes.append(f"'{wh_word}' → implies {implied} variable {node.var}")

    # ── entity anchor: leftover terms against the gate's corpus (fuzzy,
    # alias-aware) — but only a NAME-term hit may bind, never guess
    leftovers = [(i, w) for i, _s, _e, w in words
                 if i not in consumed and parts_of(w)]
    if leftovers:
        left_terms = set().union(*(parts_of(w) for _i, w in leftovers))
        docs = _corpus(store, include_concepts=True)
        if docs:
            idf = _idf(docs)
            ranked = sorted(((_score(left_terms, d, idf), d) for d in docs),
                            key=lambda x: x[0], reverse=True)
            score, top = ranked[0]
            # role fit: grounded relations say what TYPE the anchor should be
            # (worksOn wants Person/Project) — a near-tied candidate of the
            # expected type beats a lexically-equal one of the wrong type,
            # e.g. the Project 'memory graph' over a Decision that merely
            # mentions memory-graph in its name
            expected = {t for e in g.edges if e.relation in lexicon
                        for t in (lexicon[e.relation]["domain"]
                                  + lexicon[e.relation]["range"])}
            if expected and top["model"] not in expected:
                for s, d in ranked[1:]:
                    if (s >= 0.75 * score and d["model"] in expected
                            and left_terms & d["name_terms"]):
                        g.notes.append(
                            f"anchor role fit: {d['model']} '{d['name']}' "
                            f"preferred over {top['model']} '{top['name']}'")
                        score, top = s, d
                        break
            if score > 0 and left_terms & top["name_terms"]:
                hit = left_terms & top["terms"]
                pos = min(i for i, w in leftovers if parts_of(w) & hit)
                g.anchor = Node("anchor", top["model"], float(pos),
                                iri=top["iri"], name=top["name"], gid=top["gid"],
                                match_terms=sorted(left_terms & top["name_terms"]))
                g.nodes.append(g.anchor)
                consumed.update(i for i, w in leftovers if parts_of(w) <= hit)
                g.notes.append(
                    f"{'/'.join(g.anchor.match_terms)} → anchor "
                    f"{top['model'] or 'Concept'} '{top['name']}'")

    # ── one leftover noun → CONTAINS; more than one stays uncovered
    remaining = [(i, w) for i, _s, _e, w in words
                 if i not in consumed and parts_of(w)]
    if len(remaining) == 1:
        i, w = remaining[0]
        g.contains = sorted(parts_of(w))[0]
        consumed.add(i)
        g.notes.append(f"'{w}' → CONTAINS filter")

    covered = set().union(set(), *(parts_of(w) for i, _s, _e, w in words if i in consumed))
    g.coverage = len(covered & terms) / len(terms) if terms else 0.0
    g.uncovered = sorted(terms - covered)

    # ── grammar caps + edge endpoint assignment
    if len(g.edges) > 2:
        g.refuse = f"{len(g.edges)} relations — v0 grammar caps at 2"
        return g
    _assign_edges(g, lexicon, seen_types)
    if len(g.vars()) > 2:
        g.refuse = f"{len(g.vars())} typed variables — v0 grammar caps at 2"
        return g

    # subject = what the question projects
    for wh_word, implied in (("who", "Person"), ("why", "Decision"), ("how", "Pattern")):
        if g.wh == wh_word:
            g.subject = seen_types.get(implied)
    if g.subject is None:
        explicit = sorted(g.vars(), key=lambda n: n.pos)
        g.subject = explicit[0] if explicit else None
    return g


def _assign_edges(g: Grounding, lexicon: dict, seen_types: dict) -> None:
    """Word order picks each edge's neighbours; domain/range hints orient it
    and fill a missing side (spawning an implicit typed variable if needed)."""
    for edge in g.edges:
        entry = lexicon.get(edge.relation, {})
        dom, rng = entry.get("domain", set()), entry.get("range", set())
        parts = sorted(g.nodes, key=lambda n: n.pos)
        left = next((n for n in reversed(parts) if n.pos < edge.pos), None)
        right = next((n for n in parts if n.pos > edge.pos), None)

        def fill(missing_hints: set, present: Node | None) -> Node | None:
            cand = next((n for n in parts
                         if n is not present and n.type in missing_hints), None)
            if cand is None and missing_hints:
                t = sorted(missing_hints)[0]
                if t in seen_types:
                    # never join an edge to itself — a relation whose only
                    # type-fitting candidate is its OTHER end is misgrounded
                    existing = seen_types[t]
                    return existing if existing is not present else None
                cand = Node("var", t, edge.pos + 0.5, var=f"?v{len(seen_types)}")
                seen_types[t] = cand
                g.nodes.append(cand)
                g.notes.append(
                    f"relation {edge.relation} → implicit {t} variable {cand.var}")
            return cand

        if left is None:
            left = fill(dom, right)
        if right is None:
            right = fill(rng, left)
        if left is None or right is None:
            g.refuse = f"cannot resolve both ends of relation {edge.relation}"
            return
        straight = (left.type in dom) + (right.type in rng)
        swapped = (right.type in dom) + (left.type in rng)
        edge.source, edge.target = ((right, left) if swapped > straight
                                    else (left, right))


def _lit(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def compose(g: Grounding, anchor_attach: str = "link",
            drop_contains: bool = False) -> str:
    """One SPARQL query from the grounding. anchor_attach applies only when
    an anchor grounded but no relation did: 'link' joins subject↔anchor
    through any open CrossLink; 'contains' falls back to text mention.
    drop_contains omits the leftover-word CONTAINS filter — the last retry
    rung when that word was probably a relation verb that failed to ground
    ("involved in") rather than a content noun, and is poisoning an
    otherwise-correct link query."""
    subject = g.subject
    salient = _salient(subject.type, g.wh)
    select = ["?name"] + [f"?p_{p}" for p in salient]
    where: list[str] = []
    top_filters: list[str] = []

    for k, node in enumerate(g.vars()):
        inner = []
        name_prop = "label" if node.type in CONCEPT_TYPES else "name"
        if node is subject:
            inner.append(f"{node.var} a mem:{node.type} ; mem:{name_prop} ?name .")
            inner.extend(f"OPTIONAL {{ {node.var} mem:{p} ?p_{p} }}" for p in salient)
            if g.recent:
                inner.append(f"OPTIONAL {{ {node.var} mem:updatedAt ?upd }}")
            if g.status:
                inner.append(f"{node.var} mem:status ?st .")
                inner.append(f'FILTER(LCASE(STR(?st)) = "{g.status}")')
        else:
            inner.append(f"{node.var} a mem:{node.type} .")
        inner.append(f"FILTER NOT EXISTS {{ {node.var} mem:invalidated ?dead{k} }}")
        graph = (f"<{GRAPH_CONCEPTS}>" if node.type in CONCEPT_TYPES else f"?g{k}")
        where.append("GRAPH " + graph + " {\n    " + "\n    ".join(inner) + "\n  }")

    link_inner: list[str] = []
    for j, e in enumerate(g.edges):
        link_inner += [
            f'?l{j} a mem:CrossLink ; mem:linkSource {e.source.ref()} ; '
            f'mem:linkTarget {e.target.ref()} ; mem:linkRelation "{e.relation}" .',
            f"FILTER NOT EXISTS {{ ?l{j} mem:linkValidUntil ?end{j} }}",
            f"FILTER NOT EXISTS {{ ?l{j} mem:linkInvalidatedAt ?inv{j} }}",
        ]
    if not g.edges and g.anchor is not None and subject is not g.anchor:
        if anchor_attach == "link":
            link_inner += [
                "?la a mem:CrossLink ; mem:linkSource ?las ; mem:linkTarget ?lat .",
                "FILTER NOT EXISTS { ?la mem:linkValidUntil ?enda }",
                "FILTER NOT EXISTS { ?la mem:linkInvalidatedAt ?inva }",
            ]
            # scope gotcha: this FILTER joins vars from two GRAPH groups,
            # so it must sit at the top level, not inside the links group
            top_filters.append(
                f"FILTER((?las = {subject.var} && ?lat = <{g.anchor.iri}>) || "
                f"(?las = <{g.anchor.iri}> && ?lat = {subject.var}))")
        else:  # contains: the subject's text mentions the anchor
            blob = "LCASE(CONCAT(?name" + "".join(
                f', " ", COALESCE(?p_{p}, "")' for p in salient) + "))"
            top_filters.extend(
                f'FILTER(CONTAINS({blob}, "{_lit(t)}"))' for t in g.anchor.match_terms)
    if link_inner:
        where.append(f"GRAPH <{GRAPH_LINKS}> {{\n    "
                     + "\n    ".join(link_inner) + "\n  }")

    if g.contains and not drop_contains:
        blob = "LCASE(CONCAT(?name" + "".join(
            f', " ", COALESCE(?p_{p}, "")' for p in salient) + "))"
        top_filters.append(f'FILTER(CONTAINS({blob}, "{_lit(g.contains)}"))')

    tail = ""
    if g.recent:
        tail = f"\nORDER BY DESC(?upd)\nLIMIT {RECENT_LIMIT}"
    else:
        tail = f"\nLIMIT {ROW_LIMIT}"
    return (f"SELECT DISTINCT {' '.join(select)} WHERE {{\n  "
            + "\n  ".join(where + top_filters) + "\n}" + tail)


def _run_rows(store: MemoryStore, sparql: str, g: Grounding) -> list[str]:
    salient = _salient(g.subject.type, g.wh)
    lines = []
    for sol in store.query(sparql):
        name = sol["name"].value if sol["name"] is not None else "?"
        parts = [f"{p}: {sol[f'p_{p}'].value}" for p in salient
                 if sol[f"p_{p}"] is not None]
        lines.append(f"- {g.subject.type} '{name}'"
                     + (f" — {'; '.join(parts)}" if parts else ""))
    return lines


def _fallback(store: MemoryStore, text: str, g: Grounding, why: str) -> str:
    from .tools import recall, search
    if g.anchor is not None and g.anchor.gid is not None:
        head = (f"(fallback: {why} — neighbourhood recall of "
                f"{g.anchor.type} '{g.anchor.name}')\n")
        return head + recall.handle(store, g.anchor.type, g.anchor.name, 1)
    return f"(fallback: {why} — entry-point search)\n" + search.handle(store, text)


def _log(text: str, g: Grounding | None, outcome: str, rows: int = 0) -> None:
    """One line per ask into <hook-kit home>/ask-decisions.jsonl — the
    planner's tuning dataset, mirroring the gate's injections.jsonl. The
    `asks` CLI report joins it into misgrounding suspects (verb forms that
    fire but never produce rows) and vocabulary gaps (uncovered terms)."""
    from claude_hook_kit import append_jsonl
    entry: dict = {"q": text[:200], "outcome": outcome, "rows": rows}
    if g is not None:
        entry.update({
            "wh": g.wh,
            "relations": [{"rel": e.relation, "form": e.form} for e in g.edges],
            "types": sorted({n.type for n in g.vars()}),
            "anchor": g.anchor.name if g.anchor else None,
            "coverage": round(g.coverage, 2),
            "uncovered": g.uncovered,
            "contains": g.contains,
        })
    append_jsonl("ask-decisions.jsonl", entry)


def handle(store: MemoryStore, text: str, explain: bool = False) -> str:
    if not is_question(text):
        _log(text, None, "statement")
        return ("Statement-shaped — the ambient gate handles working prose. "
                "Ask a question, or use `search` for entry points.")
    g = ground(store, text)

    prefix = ""
    if explain:
        prefix = ("── grounding ──\n"
                  + "\n".join(f"  {n}" for n in g.notes or ["  (nothing grounded)"])
                  + f"\n  coverage: {g.coverage:.0%}"
                  + (f"\n  refused: {g.refuse}" if g.refuse else "") + "\n")

    if g.refuse:
        _log(text, g, "refused")
        return prefix + _fallback(store, text, g, f"out of grammar ({g.refuse})")
    if g.coverage < COVERAGE_MIN:
        _log(text, g, "low-coverage")
        return prefix + _fallback(
            store, text, g, f"grounding coverage {g.coverage:.0%} below "
            f"{COVERAGE_MIN:.0%}")

    # degenerate but correct: entity-only question, or "why" landing on the
    # very Decision it asks about → the anchor IS the answer
    from .tools import recall as recall_tool
    if g.anchor is not None and g.anchor.gid is not None and (
            g.subject is None
            or (not g.edges and g.subject.type == g.anchor.type)):
        _log(text, g, "direct", 1)
        return (prefix + "(direct match)\n"
                + recall_tool.handle(store, g.anchor.type, g.anchor.name, 1))
    if g.subject is None:
        _log(text, g, "no-subject")
        return prefix + _fallback(store, text, g, "no queryable subject")

    sparql = compose(g)
    if explain:
        prefix += "── sparql ──\n" + sparql + "\n── answer ──\n"
    lines = _run_rows(store, sparql, g)
    if not lines and not g.edges and g.anchor is not None:
        # loose link attach found nothing — retry as a text mention
        sparql2 = compose(g, anchor_attach="contains")
        if explain:
            prefix += "(no rows via links — retrying as text mention)\n"
        lines = _run_rows(store, sparql2, g)
        if not lines and g.contains:
            # last rung: the leftover was probably a relation verb that
            # failed to ground, not a content noun — its CONTAINS filter is
            # poisoning a link query that answers the question on its own
            lines = _run_rows(store, compose(g, drop_contains=True), g)
            if lines:
                prefix += (f"(ignored ungrounded '{g.contains}' — the link "
                           f"structure answered without it)\n")
                g.uncovered.append(g.contains)  # count it as a vocabulary gap
                _log(text, g, "dropped-contains", len(lines))
                if len(lines) > 10:
                    lines = lines[:10] + [f"(+{len(lines) - 10} more)"]
                return prefix + "\n".join(lines)
    if not lines:
        _log(text, g, "no-rows")
        return prefix + _fallback(store, text, g, "composed query returned no rows")
    _log(text, g, "answered", len(lines))
    if len(lines) > 10:
        lines = lines[:10] + [f"(+{len(lines) - 10} more)"]
    return prefix + "\n".join(lines)


def asks_report() -> str:
    """Join ask-decisions.jsonl into the two curation signals: misgrounding
    suspects (verb forms that fire in asks that end with no rows) and
    vocabulary gaps (terms nothing grounded). Read-only; run any time."""
    import json
    from collections import Counter

    from claude_hook_kit import state_home

    path = state_home() / "ask-decisions.jsonl"
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    if not entries:
        return ("No ask decisions logged yet — use `claude-memory-graph ask` "
                "for a while, then rerun.")

    outcomes = Counter(e.get("outcome", "?") for e in entries)
    report = [f"{len(entries)} asks: "
              + ", ".join(f"{k} {v}" for k, v in outcomes.most_common())]

    fired = Counter()
    dry = Counter()
    for e in entries:
        for r in e.get("relations", []):
            key = (r.get("rel", "?"), r.get("form", "?"))
            fired[key] += 1
            if e.get("outcome") in ("no-rows", "refused"):
                dry[key] += 1
    suspects = [(k, n, fired[k]) for k, n in dry.most_common() if n == fired[k]]
    if suspects:
        report.append("\nMisgrounding suspects (verb form fired, NEVER produced rows):")
        for (rel, form), n, total in suspects[:10]:
            report.append(f"- '{form}' → {rel}: {n}/{total} asks ended dry "
                          f"→ memory_amend_relation (LLM-added) or edit base.ttl")

    gaps = Counter(t for e in entries
                   if e.get("outcome") in ("low-coverage", "no-subject",
                                           "dropped-contains")
                   for t in e.get("uncovered", []))
    # a CONTAINS word in a dry ask is the failure's likeliest cause — it was
    # "covered", so it never reaches `uncovered`, but it belongs in this list
    gaps.update(e["contains"] for e in entries
                if e.get("outcome") == "no-rows" and e.get("contains"))
    if gaps:
        report.append("\nVocabulary gaps (ungrounded terms in failed asks):")
        for term, n in gaps.most_common(10):
            report.append(f"- '{term}' ×{n} → a verb form, node alias, or new "
                          f"node if it names something real")
    if len(report) == 1:
        report.append("No misgrounding suspects or vocabulary gaps — lexicon looks healthy.")
    return "\n".join(report)
