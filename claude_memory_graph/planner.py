"""memory_ask: plain-English questions over the memory graph, no LLM.

The question is understood by ceist (packages/ceist): grounded against this
graph's own vocabulary — relation verb forms and domain/range from the schema
graph (store.relation_lexicon), node names from the gate's corpus (the same
matcher as memory_search), model nouns from the ontology, a few status words
— and turned into a backend-neutral plan. This module is the memory graph's
side: the Vocabulary adapter, the plan → SPARQL compiler, and the runner that
tries the plan and its relaxations, falling back to a neighbourhood recall or
search when nothing composes. The floor is exactly memory_search: the planner
never guesses.

The same planner answers over Arches data through ceist.arches (Rós Madair,
Arches Search). See docs/QUERY-PLANNING.md.
"""

from ceist import (Contains, DateField, DateRange, Entity, EntityRef, HasValue, LinkTo, Mention,
                   Not, Plan, Relation, Value, interpret, narrate)
from ceist import ground as _ceist_ground

from .gate.recall import _corpus, _idf, _score
from .namespaces import GRAPH_CONCEPTS, GRAPH_LINKS
from .ontology import CONCEPT_TYPES, RESOURCE_MODELS
from .store import MemoryStore

# ponytail: hardcoded thresholds; promote to gate config when the coverage
# experiment yields real numbers to tune against.
COVERAGE_MIN = 0.6
RECENT_LIMIT = 5
ROW_LIMIT = 25

# question verbs that shape intent but name nothing in the graph
_HINTS = {"choose": "Decision", "chose": "Decision", "chosen": "Decision",
          "decide": "Decision", "decided": "Decision"}
_IMPLIED = {"who": "Person", "why": "Decision", "how": "Pattern"}
_STATUS = {"active": "active", "open": "active", "ongoing": "active",
           "done": "done", "completed": "done", "finished": "done",
           "blocked": "blocked"}
_SALIENT = {"Decision": ["rationale", "outcome"], "Pattern": ["description"],
            "Task": ["status", "description"]}
_SYNONYMS = {
    "Pattern": ["problem", "problems", "issue", "issues", "bug", "bugs", "gotcha", "gotchas",
                "pitfall", "pitfalls", "lesson", "lessons", "fix", "fixes", "workaround",
                "workarounds"],
    "Decision": ["choice", "choices", "tradeoff", "tradeoffs"],
    "Technology": ["tool", "tools", "library", "libraries", "framework", "frameworks",
                   "stack", "dependency", "dependencies"],
    "Company": ["client", "clients", "customer", "customers", "organisation",
                "organisations", "organization", "organizations"],
    "Task": ["todo", "todos", "ticket", "tickets"],
}


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
    # everyday words for the models, as people actually ask
    for model, words in _SYNONYMS.items():
        if model in RESOURCE_MODELS + CONCEPT_TYPES:
            for w in words:
                nouns.setdefault(w, model)
    return nouns


class MemoryVocabulary:
    """ceist.Vocabulary over a MemoryStore."""

    def __init__(self, store: MemoryStore):
        self.store = store
        self._docs = None

    def type_words(self) -> dict[str, str]:
        return _model_nouns()

    def relations(self) -> list[Relation]:
        return [Relation(rel, tuple(e["verbForms"]), frozenset(e["domain"]),
                         frozenset(e["range"]))
                for rel, e in self.store.relation_lexicon().items()]

    def values(self) -> list[Value]:
        return [Value(word, "status", status, status, kind="literal")
                for word, status in _STATUS.items()]

    def rank_entities(self, terms: set[str]) -> list[tuple[float, Entity]]:
        if self._docs is None:
            docs = [_with_aliases(d) for d in _corpus(self.store, include_concepts=True)]
            self._docs = (docs, _idf(docs) if docs else {})
        docs, idf = self._docs
        ranked = sorted(((_score(terms, d, idf), d) for d in docs),
                        key=lambda x: x[0], reverse=True)
        return [(s, Entity(d["model"], d["iri"], d["name"], frozenset(d["name_terms"]),
                           frozenset(d["terms"]),
                           extra={"gid": d["gid"], "recallable": d["gid"] is not None}))
                for s, d in ranked if s > 0]

    def date_fields(self) -> list[DateField]:
        # every memory carries both; "decisions in March" means when it was made
        return [DateField("createdAt", "creation date",
                          ("created", "added", "made", "recorded", "written"), default=True),
                DateField("updatedAt", "last update",
                          ("updated", "changed", "modified", "edited", "touched"))]

    def implied_types(self) -> dict[str, str]:
        return _IMPLIED

    def hint_words(self) -> dict[str, str]:
        return _HINTS


def _with_aliases(doc: dict) -> dict:
    """A memory's aliases name it as much as its name does: "who works on the
    heritage platform?" must find the project aliased that way. Alias words
    count as name terms, so they can identify the record a question is about
    (the planner only lets a name pick a record, never a passing mention)."""
    from ceist.text import terms
    alias_terms = {w for key, value in doc.get("parts", ())
                   if key == "aliases" for a in str(value).split(",") for w in terms(a)}
    if not alias_terms:
        return doc
    return dict(doc, name_terms=set(doc["name_terms"]) | alias_terms)


def ground(store: MemoryStore, text: str):
    """The grounding alone (what each word was taken to mean)."""
    return _ceist_ground(MemoryVocabulary(store), text)


# ── plan → SPARQL ────────────────────────────────────────────────────────

def _lit(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def compile_sparql(plan: Plan, limit: int | None = ROW_LIMIT) -> str:
    """One SELECT for the plan. Each (sub-)plan is a variable in its own GRAPH
    group; every link is an open CrossLink in the links graph. A filter that
    joins variables from two GRAPH groups sits at the top level (the scope
    gotcha: inside a group it cannot see the other group's variables). A
    negated condition is a FILTER NOT EXISTS around the same patterns."""
    salient = _salient(plan.type, plan.wh)
    counter = {"var": 0, "link": 0, "n": 0}

    def blob() -> str:
        return "LCASE(CONCAT(?name" + "".join(
            f', " ", COALESCE(?p_{p}, "")' for p in salient) + "))"

    def fresh(stem: str) -> str:
        counter["n"] += 1
        return f"?{stem}{counter['n']}"

    def open_link(src: str, dst: str, relation: str) -> list[str]:
        j = counter["link"]
        counter["link"] += 1
        return [f'?l{j} a mem:CrossLink ; mem:linkSource {src} ; '
                f'mem:linkTarget {dst} ; mem:linkRelation "{relation}" .',
                f"FILTER NOT EXISTS {{ ?l{j} mem:linkValidUntil ?end{j} }}",
                f"FILTER NOT EXISTS {{ ?l{j} mem:linkInvalidatedAt ?inv{j} }}"]

    def value_patterns(c, var: str) -> list[str]:
        """Patterns inside var's own GRAPH group."""
        if isinstance(c, HasValue):
            v = fresh("val")
            return [f"{var} mem:{c.field} {v} .",
                    f'FILTER(LCASE(STR({v})) = "{_lit(c.value.lower())}")']
        v = fresh("d")
        tests = ([f'SUBSTR(STR({v}), 1, 10) >= "{c.lo}"'] if c.lo else []) + \
                ([f'SUBSTR(STR({v}), 1, 10) <= "{c.hi}"'] if c.hi else [])
        return [f"{var} mem:{c.field} {v} ."] + [f"FILTER({' && '.join(tests)})"] * bool(tests)

    def group(where: list[str]) -> str:
        return "{ " + " ".join(where) + " }"

    def visit(p: Plan, var: str, is_subject: bool, out: dict) -> None:
        """Add p's patterns to out (blocks: GRAPH groups, links: CrossLink
        patterns, top: filters across groups)."""
        k = int(var.lstrip("?v"))
        inner = []
        name_prop = "label" if p.type in CONCEPT_TYPES else "name"
        if is_subject:
            inner.append(f"{var} a mem:{p.type} ; mem:{name_prop} ?name .")
            inner.extend(f"OPTIONAL {{ {var} mem:{s} ?p_{s} }}" for s in salient)
            if plan.recent:
                inner.append(f"OPTIONAL {{ {var} mem:updatedAt ?upd }}")
        else:
            inner.append(f"{var} a mem:{p.type} .")
        for c in p.where:
            if isinstance(c, (HasValue, DateRange)):
                inner.extend(value_patterns(c, var))
            elif isinstance(c, Not) and isinstance(c.condition, (HasValue, DateRange)):
                inner.append("FILTER NOT EXISTS " + group(value_patterns(c.condition, var)))
        inner.append(f"FILTER NOT EXISTS {{ {var} mem:invalidated ?dead{k} }}")
        graph = f"<{GRAPH_CONCEPTS}>" if p.type in CONCEPT_TYPES else f"?g{k}"
        out["blocks"].append("GRAPH " + graph + " {\n    " + "\n    ".join(inner) + "\n  }")

        for c in p.where:
            negated = isinstance(c, Not)
            c = c.condition if negated else c
            if isinstance(c, LinkTo):
                # a negated link: the same patterns, collected apart and wrapped
                dest = {"blocks": [], "links": [], "top": []} if negated else out
                if isinstance(c.target, EntityRef):
                    other = f"<{c.target.entity.id}>"
                else:
                    counter["var"] += 1
                    other = f"?v{counter['var']}"
                    visit(c.target, other, False, dest)
                if c.relation is None:
                    # linked by ANY relation, either direction
                    a = fresh("la")
                    dest["links"].extend([
                        f"{a} a mem:CrossLink ; mem:linkSource {a}s ; mem:linkTarget {a}t .",
                        f"FILTER NOT EXISTS {{ {a} mem:linkValidUntil {a}e }}",
                        f"FILTER NOT EXISTS {{ {a} mem:linkInvalidatedAt {a}i }}"])
                    dest["top"].append(f"FILTER(({a}s = {var} && {a}t = {other}) || "
                                       f"({a}s = {other} && {a}t = {var}))")
                else:
                    src, dst = (var, other) if c.direction == "out" else (other, var)
                    dest["links"].extend(open_link(src, dst, c.relation))
                if negated:
                    parts = dest["blocks"] + [f"GRAPH <{GRAPH_LINKS}> " + group(dest["links"])]
                    out["top"].append("FILTER NOT EXISTS " + group(parts + dest["top"]))
            elif isinstance(c, Mention) and is_subject:
                tests = " && ".join(f'CONTAINS({blob()}, "{_lit(t)}")' for t in c.terms)
                out["top"].append(f"FILTER(!({tests}))" if negated else f"FILTER({tests})")
            elif isinstance(c, Contains) and is_subject:
                test = f'CONTAINS({blob()}, "{_lit(c.term)}")'
                out["top"].append(f"FILTER(!{test})" if negated else f"FILTER({test})")

    out = {"blocks": [], "links": [], "top": []}
    visit(plan, "?v0", True, out)
    where = list(out["blocks"])
    if out["links"]:
        where.append(f"GRAPH <{GRAPH_LINKS}> {{\n    " + "\n    ".join(out["links"]) + "\n  }")
    select = ["?name"] + [f"?p_{s}" for s in salient]
    if plan.recent:
        tail = f"\nORDER BY DESC(?upd)\nLIMIT {RECENT_LIMIT}"
    elif limit:
        tail = f"\nLIMIT {limit}"
    else:
        tail = ""
    return (f"SELECT DISTINCT {' '.join(select)} WHERE {{\n  "
            + "\n  ".join(where + out["top"]) + "\n}" + tail)


def _run_rows(store: MemoryStore, sparql: str, plan: Plan) -> list[str]:
    salient = _salient(plan.type, plan.wh)
    lines = []
    for sol in store.query(sparql):
        name = sol["name"].value if sol["name"] is not None else "?"
        parts = [f"{p}: {sol[f'p_{p}'].value}" for p in salient
                 if sol[f"p_{p}"] is not None]
        lines.append(f"- {plan.type} '{name}'"
                     + (f" — {'; '.join(parts)}" if parts else ""))
    return lines


def _fallback(store: MemoryStore, text: str, g, why: str) -> str:
    from .tools import recall, search
    if g.anchor is not None and g.anchor.entity.extra.get("recallable"):
        head = (f"(fallback: {why} — neighbourhood recall of "
                f"{g.anchor.type} '{g.anchor.name}')\n")
        return head + recall.handle(store, g.anchor.type, g.anchor.name, 1)
    return f"(fallback: {why} — entry-point search)\n" + search.handle(store, text)


def _log(text: str, g, outcome: str, rows: int = 0) -> None:
    """One line per ask into <state home>/ask-decisions.jsonl — the planner's
    tuning dataset, mirroring the gate's injections.jsonl. The `asks` CLI
    report joins it into misgrounding suspects (verb forms that fire but never
    produce rows) and vocabulary gaps (uncovered terms)."""
    from claude_memory_graph.hookcore import append_jsonl
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
            "suggestions": [{"words": w, "options": o} for w, o in g.suggestions],
        })
    append_jsonl("ask-decisions.jsonl", entry)


_matcher = None


def matcher():
    """The matching chain for leftover words (ceist.matching): exact, then
    meaning (the gate's WordLlama encoder, when installed). Unsure → "did you
    mean", which memory_ask hands back to its caller — Claude chooses."""
    global _matcher
    if _matcher is None:
        from ceist import config
        from .gate import semantic
        from .gate.runtime import config as gate_config
        cfg = config.load(None)
        enc = semantic.encoder() if gate_config()["SEMANTIC"] and semantic.available() else None
        if enc is None:
            cfg.layers = ["exact"]
        _matcher = config.chain(cfg, encoder=enc)
    return _matcher


def _did_you_mean(g) -> str:
    return "".join(f"(not sure what '{w}' means here — did you mean "
                   f"{', '.join(repr(o) for o in opts)}? Ask again using one of those; if "
                   f"'{w}' should always mean one of them, add it as a phrasing with "
                   f"memory_amend_relation add_verb_forms)\n"
                   for w, opts in g.suggestions)


def handle(store: MemoryStore, text: str, explain: bool = False) -> str:
    meaning = interpret(MemoryVocabulary(store), text, COVERAGE_MIN, matcher=matcher())
    if meaning.statement:
        _log(text, None, "statement")
        return ("Statement-shaped — the ambient gate handles working prose. "
                "Ask a question, or use `search` for entry points.")
    g = meaning.grounding

    prefix = ""
    if explain:
        prefix = ("── grounding ──\n"
                  + "\n".join(f"  {n}" for n in g.notes or ["  (nothing grounded)"])
                  + f"\n  coverage: {g.coverage:.0%}"
                  + (f"\n  refused: {g.refuse}" if g.refuse else "") + "\n")

    prefix += _did_you_mean(g)
    if meaning.refused:
        outcome = ("refused" if g.refuse else
                   "low-coverage" if g.coverage < COVERAGE_MIN else "no-subject")
        _log(text, g, outcome)
        return prefix + _fallback(store, text, g, meaning.refused)

    if meaning.direct is not None:
        from .tools import recall as recall_tool
        _log(text, g, "direct", 1)
        e = meaning.direct
        return prefix + "(direct match)\n" + recall_tool.handle(store, e.type, e.name, 1)

    plan = meaning.plan
    if explain:
        prefix += "── understood ──\n  " + narrate(plan) + "\n"
    if g.loose:
        prefix += (f"(couldn't place {g.loose} in the graph — listing every "
                   f"{plan.type} instead)\n")
    limit = None if plan.count else ROW_LIMIT
    sparql = compile_sparql(plan, limit)
    if explain:
        prefix += "── sparql ──\n" + sparql + "\n── answer ──\n"
    lines = _run_rows(store, sparql, plan)
    outcome = "answered"
    for relax in meaning.relaxations:
        if lines:
            break
        if relax.explain_only and explain:
            prefix += relax.note + "\n"
        lines = _run_rows(store, compile_sparql(relax.plan, limit), relax.plan)
        if lines and not relax.explain_only:
            prefix += relax.note + "\n"
            if relax.drops:
                g.uncovered.append(relax.drops)   # count it as a vocabulary gap
                outcome = "dropped-contains"
    if not lines:
        _log(text, g, "no-rows")
        return prefix + _fallback(store, text, g, "composed query returned no rows")
    _log(text, g, outcome, len(lines))
    if plan.count:
        noun = plan.type + ("" if len(lines) == 1 else "s")
        prefix += f"{len(lines)} {noun}" + (":" if lines else "") + "\n"
    if len(lines) > 10:
        lines = lines[:10] + [f"(+{len(lines) - 10} more)"]
    return prefix + "\n".join(lines)


def asks_report() -> str:
    """Join ask-decisions.jsonl into the two curation signals: misgrounding
    suspects (verb forms that fire in asks that end with no rows) and
    vocabulary gaps (terms nothing grounded). Read-only; run any time."""
    import json
    from collections import Counter

    from claude_memory_graph.hookcore import state_home

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
