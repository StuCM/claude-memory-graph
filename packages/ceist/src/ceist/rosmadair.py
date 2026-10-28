"""Plans → Rós Madair's Query IR, read back, and run over a Rós Madair snapshot.

    from ceist.arches import ArchesVocabulary
    from ceist.rosmadair import ask, compile_plan, to_query
    vocab = ArchesVocabulary.from_data_dir("data")
    print(ask("how many listed buildings are on site Leeds Dock?", vocab, "snapshot",
              explain=True))

Mapping (ros-madair-query's serde form; Rós Madair itself is unchanged):

    LinkTo(path, EntityRef, out)     {"has_link": {"path", "target"}}
    LinkTo(path, Plan, out)          {"on_link": {"path", "model", "where"}}  (multi-hop)
    LinkTo(None, EntityRef, any)     {"backlink": {"target"}}   (linked to it, any field)
    LinkTo(…, qualifier=HasValue)    {"on_tile": [<the link>, {"concept": …}]}   (one tile holds both:
                                     "designed by Ada" = actor Ada with role Architect)
    HasValue(concept)                {"concept": {"path", "op": "descendant_or_self_of", "value"}}
    DateRange(path, lo, hi)          {"range": {"path", "lo", "hi"}}   days since 1970, as
                                     Alizarin's quantize_date (the emitter's own encoding)
    Not(value or date)               {"not": …}
    Not(link)                        a second query, subtracted client-side: Rós Madair
                                     refuses `not` over a link (it is chunk-coarse)
    count / list                     measures ["count_records"] / ["select_ids"]

A query with nothing that ties it to the model — no filter, or only a
`backlink` (a link from any field) — is answered by resolving and keeping the
model's own records: Rós Madair doesn't scope a vacuous filter to `model`.

What the IR can't say, the compiler refuses by name (Unsupported), so the
runner moves on to a relaxation or says what it couldn't do: a link walked
backwards (Rós Madair walks links forward), a negated link inside a hop,
free text (the substrate indexes concepts, ranges, geometry and links, not
text), and "most recent".

Every workaround for Rós Madair's current behaviour is written up, ready to
raise upstream, in packages/ceist/ROS-MADAIR.md.

Before a query runs it is read back (`read_back`) into a plan and narrated;
if that differs from what the question was understood to mean, it doesn't run.
"""

import json
from dataclasses import dataclass, field

from . import dates
from .narrate import narrate
from .plan import (Contains, DateRange, EntityRef, HasValue, LinkTo, Mention, Not, Plan,
                   interpret)
from .readback import check

DEFAULT_LIMIT = 1000


class Unsupported(Exception):
    """A condition Rós Madair's IR can't express (yet)."""


@dataclass
class Compiled:
    """What runs: `query`, minus the records each of `minus` selects."""
    query: dict
    minus: list[dict] = field(default_factory=list)
    count: bool = False

    def all(self) -> list[dict]:
        return [self.query] + self.minus


def _expr(plan: Plan, vocab) -> dict | None:
    parts = []
    for c in plan.where:
        if isinstance(c, Not):
            if isinstance(c.condition, LinkTo):
                raise Unsupported(f"a negated link ('{c.condition.relation}') inside a hop: "
                                  "Rós Madair can't negate a link, and only the top level "
                                  "can be subtracted")
            parts.append({"not": _expr(Plan(plan.type, [c.condition]), vocab)})
        elif isinstance(c, LinkTo):
            if c.relation is None:
                if not isinstance(c.target, EntityRef):
                    raise Unsupported("a loose link to a set of records")
                parts.append({"backlink": {"target": c.target.entity.id}})
            elif c.direction != "out":
                raise Unsupported(
                    f"walking '{c.relation}' backwards ({plan.type} records that another "
                    f"record's {c.relation} points at): Rós Madair walks links forward; "
                    f"ask from the other side")
            else:
                if isinstance(c.target, EntityRef):
                    link = {"has_link": {"path": c.relation, "target": c.target.entity.id}}
                else:
                    inner = _expr(c.target, vocab) or {"all": []}
                    link = {"on_link": {"path": c.relation,
                                        "model": vocab.model(c.target.type).graph_id,
                                        "where": inner}}
                if c.qualifier is not None:
                    # the same tile carries the link and the qualifier value
                    q = c.qualifier
                    link = {"on_tile": [link, {"concept": {
                        "path": q.field, "op": "descendant_or_self_of", "value": q.value}}]}
                parts.append(link)
        elif isinstance(c, HasValue):
            if c.kind != "concept":
                raise Unsupported(f"the literal value {c.label}")
            parts.append({"concept": {"path": c.field, "op": "descendant_or_self_of",
                                      "value": c.value}})
        elif isinstance(c, DateRange):
            parts.append({"range": {"path": c.field,
                                    "lo": dates.days(c.lo) if c.lo else -dates.OPEN,
                                    "hi": dates.days(c.hi) if c.hi else dates.OPEN}})
        elif isinstance(c, (Mention, Contains)):
            term = c.term if isinstance(c, Contains) else " ".join(c.terms)
            raise Unsupported(f"a free-text condition ('{term}'): the substrate indexes "
                              "concepts, ranges, geometry and links, not text")
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"all": parts}


def _query(plan: Plan, vocab, measure: str, limit: int | None) -> dict:
    query = {"model": vocab.model(plan.type).graph_id, "measures": [measure]}
    where = _expr(plan, vocab)
    if where is not None:
        query["where"] = where
    if limit and measure == "select_ids":
        query["limit"] = limit
    return query


def compile_plan(plan: Plan, vocab, limit: int | None = None) -> Compiled:
    """The query (and any queries to subtract) for a plan; raises Unsupported."""
    if plan.recent:
        raise Unsupported("'most recent': the substrate has no update-time column")
    negated = [c for c in plan.where if isinstance(c, Not) and isinstance(c.condition, LinkTo)]
    if not negated:
        return Compiled(_query(plan, vocab, "count_records" if plan.count else "select_ids",
                               None if plan.count else limit), count=plan.count)
    base = Plan(plan.type, [c for c in plan.where if c not in negated], wh=plan.wh)
    return Compiled(_query(base, vocab, "select_ids", None),
                    [_query(Plan(plan.type, [c.condition]), vocab, "select_ids", None)
                     for c in negated], count=plan.count)


def to_query(plan: Plan, vocab, limit: int | None = None) -> dict:
    """The single Rós Madair Query for a plan (raises Unsupported — also for a
    negated link, which needs compile_plan's subtraction)."""
    compiled = compile_plan(plan, vocab, limit)
    if compiled.minus:
        raise Unsupported("a negated link needs a second query to subtract: use compile_plan")
    return compiled.query


# ── read-back: the IR → a plan again ─────────────────────────────────────

def _conditions(expr: dict | None, type_name: str, vocab) -> list:
    if not expr:
        return []
    (kind, body), = expr.items()
    if kind == "all":
        return [c for e in body for c in _conditions(e, type_name, vocab)]
    if kind == "not":
        inner = _conditions(body, type_name, vocab)
        return [Not(inner[0])] if len(inner) == 1 else [Not(Plan(type_name, inner))]
    if kind == "has_link":
        e = vocab.entity(body["target"])
        if e is None:
            return [f"a link to unknown record {body['target']}"]
        return [LinkTo(body["path"], EntityRef(e), "out", style="field")]
    if kind == "on_link":
        sub = vocab.by_graph[body["model"]].name
        return [LinkTo(body["path"], Plan(sub, _conditions(body["where"], sub, vocab)), "out",
                       style="field")]
    if kind == "backlink":
        e = vocab.entity(body["target"])
        if e is None:
            return [f"a backlink to unknown record {body['target']}"]
        return [LinkTo(None, EntityRef(e), "any")]
    if kind == "on_tile":
        parts = [c for e in body for c in _conditions(e, type_name, vocab)]
        links = [c for c in parts if isinstance(c, LinkTo)]
        quals = [c for c in parts if isinstance(c, HasValue)]
        if len(links) == 1 and len(quals) == 1 and len(parts) == 2:
            from dataclasses import replace
            return [replace(links[0], qualifier=quals[0])]
        return [f"on_tile {json.dumps(body)}"]       # read-back can't say it: a mismatch
    if kind == "concept":
        return [HasValue(body["path"], body["value"], vocab.concept_label(body["value"]))]
    if kind == "range":
        return [DateRange(body["path"], dates.from_days(body["lo"]), dates.from_days(body["hi"]),
                          vocab.date_label(type_name, body["path"]))]
    return [f"{kind} {json.dumps(body)}"]       # unknown to read-back: reads as a mismatch


def read_back(compiled: Compiled, vocab) -> Plan:
    """What the compiled queries select, as a plan."""
    q = compiled.query
    type_name = vocab.by_graph[q["model"]].name
    where = _conditions(q.get("where"), type_name, vocab)
    for m in compiled.minus:
        where += [Not(c) for c in _conditions(m.get("where"), type_name, vocab)]
    return Plan(type_name, where, count="count_records" in q["measures"] or compiled.count)


# ── the runner ───────────────────────────────────────────────────────────

def _scoped_by_model(where: dict | None) -> bool:
    """Whether a filter only matches records of the query's model: some
    conjunct names a node of it (a vacuous filter or a backlink doesn't)."""
    if not where:
        return False
    (kind, body), = where.items()
    if kind == "all":
        return any(_scoped_by_model(e) for e in body)
    return kind in ("has_link", "on_link", "concept", "range")


def ask(text: str, vocab, snapshot_dir: str, explain: bool = False, limit: int = 25,
        today=None) -> str:
    """Answer a question from a Rós Madair snapshot (needs the ros_madair
    Python bindings). `vocab` is the ArchesVocabulary of the data_dir the
    snapshot was emitted from."""
    import ros_madair

    meaning = interpret(vocab, text, today=today)
    g = meaning.grounding
    lines: list[str] = []
    if explain:
        lines.append("── grounding ──")
        lines += [f"  {n}" for n in g.notes] + [f"  coverage: {g.coverage:.0%}"]
    if meaning.statement or meaning.refused:
        return "\n".join(lines + [f"(not answered: {meaning.refused})"])
    if meaning.direct is not None:
        e = meaning.direct
        return "\n".join(lines + [f"(direct match) {e.type} '{e.name}' ({e.id})"])

    reader = ros_madair.Reader(snapshot_dir)
    graphs = {}

    def graph_for(type_name: str):
        # the snapshot doesn't carry the schema; the vocabulary does
        if type_name not in graphs:
            graphs[type_name] = ros_madair.Graph(json.dumps(vocab.model(type_name).doc))
        return graphs[type_name]

    skipped: list[str] = []
    for plan, note in [(meaning.plan, "")] + [(r.plan, r.note) for r in meaning.relaxations]:
        try:
            compiled = compile_plan(plan, vocab, None if plan.count else limit)
        except Unsupported as why:
            skipped.append(str(why))
            continue
        verdict = check(plan, read_back(compiled, vocab))
        if explain:
            lines += ["── understood ──", "  " + narrate(plan), "── query ──"]
            lines += ["  " + json.dumps(q) for q in compiled.all()]
            if compiled.minus:
                lines.append("  (the first, minus the records each later one selects)")
            lines += verdict.lines()
        if not verdict.ok:
            return "\n".join(lines + ["(not run: the compiled query reads back differently "
                                      "from the question)"])
        graph = graph_for(plan.type)
        scoped = _scoped_by_model(compiled.query.get("where"))
        if compiled.minus or not scoped:
            query = dict(compiled.query, measures=["select_ids"])
            query.pop("limit", None)
            ids = set(reader.resolve(json.dumps(query), graph))
            if not scoped:
                ids &= vocab.ids_of(plan.type)
            for m in compiled.minus:
                ids -= set(reader.resolve(json.dumps(m), graph))
            ids = sorted(ids, key=lambda i: vocab.names.get(i, i))
            n = len(ids)
        elif plan.count:
            ids, n = [], reader.count(json.dumps(compiled.query), graph)
        else:
            ids = reader.resolve(json.dumps(compiled.query), graph)
            n = len(ids)
        if plan.count:
            if n or note == "":
                return "\n".join(lines + ([note] if note else []) + [f"{n} {plan.type} records"])
            continue
        if ids:
            body = [f"- {plan.type} '{vocab.names.get(i, i)}'" for i in ids[:limit]]
            if len(ids) > limit:
                body.append(f"(+{len(ids) - limit} more)")
            return "\n".join(lines + ([note] if note else []) + body)
    if skipped:
        return "\n".join(lines + ["(not answered: " + "; ".join(skipped) + ")"])
    return "\n".join(lines + ["(no matching records)"])
