"""Plans → Rós Madair's Query IR, and a runner over a Rós Madair snapshot.

    from ceist.arches import ArchesVocabulary
    from ceist.rosmadair import ask, to_query
    vocab = ArchesVocabulary.from_data_dir("data")
    print(ask("how many listed buildings are on site Leeds Dock?", vocab, "snapshot"))

Mapping (ros-madair-query's serde form):

    LinkTo(path, EntityRef, out)     {"has_link": {"path", "target"}}
    LinkTo(path, Plan, out)          {"on_link": {"path", "model", "where"}}  (multi-hop)
    LinkTo(None, EntityRef, any)     {"backlink": {"target"}}   (linked to it, any field)
    HasValue(concept)                {"concept": {"path", "op": "descendant_or_self_of", "value"}}
    count / list                     measures ["count_records"] / ["select_ids"]

What the IR can't say yet, the compiler refuses by name (Unsupported), so the
runner moves on to a relaxation or says what it couldn't do: a link walked
backwards ("sites that have buildings…" — Rós Madair walks links forward),
free-text conditions (the substrate indexes concepts, ranges, geometry and
links, not text), and "most recent" (no update-time column).
"""

import json

from .narrate import narrate
from .plan import Contains, EntityRef, HasValue, LinkTo, Mention, Plan, interpret

DEFAULT_LIMIT = 1000


class Unsupported(Exception):
    """A condition Rós Madair's IR can't express (yet)."""


def _expr(plan: Plan, vocab) -> dict | None:
    parts = []
    for c in plan.where:
        if isinstance(c, LinkTo):
            if c.relation is None:
                if not isinstance(c.target, EntityRef):
                    raise Unsupported("a loose link to a set of records")
                parts.append({"backlink": {"target": c.target.entity.id}})
            elif c.direction != "out":
                raise Unsupported(
                    f"walking '{c.relation}' backwards ({plan.type} records that another "
                    f"record's {c.relation} points at): Rós Madair walks links forward; "
                    f"ask from the other side")
            elif isinstance(c.target, EntityRef):
                parts.append({"has_link": {"path": c.relation, "target": c.target.entity.id}})
            else:
                inner = _expr(c.target, vocab) or {"all": []}
                parts.append({"on_link": {"path": c.relation,
                                          "model": vocab.model(c.target.type).graph_id,
                                          "where": inner}})
        elif isinstance(c, HasValue):
            if c.kind != "concept":
                raise Unsupported(f"the literal value {c.label}")
            parts.append({"concept": {"path": c.field, "op": "descendant_or_self_of",
                                      "value": c.value}})
        elif isinstance(c, (Mention, Contains)):
            term = c.term if isinstance(c, Contains) else " ".join(c.terms)
            raise Unsupported(f"a free-text condition ('{term}'): the substrate indexes "
                              "concepts, ranges, geometry and links, not text")
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"all": parts}


def to_query(plan: Plan, vocab, limit: int | None = None) -> dict:
    """The Rós Madair Query for a plan (raises Unsupported)."""
    query = {"model": vocab.model(plan.type).graph_id,
             "measures": ["count_records" if plan.count else "select_ids"]}
    where = _expr(plan, vocab)
    if where is not None:
        query["where"] = where
    if limit and not plan.count:
        query["limit"] = limit
    return query


def ask(text: str, vocab, snapshot_dir: str, explain: bool = False, limit: int = 25) -> str:
    """Answer a question from a Rós Madair snapshot (needs the ros_madair
    Python bindings). `vocab` is the ArchesVocabulary of the data_dir the
    snapshot was emitted from."""
    import ros_madair

    meaning = interpret(vocab, text)
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
            query = to_query(plan, vocab, None if plan.count else limit)
        except Unsupported as why:
            skipped.append(str(why))
            continue
        if explain:
            lines += ["── understood ──", "  " + narrate(plan),
                      "── query ──", "  " + json.dumps(query)]
        ir = json.dumps(query)
        if plan.count:
            n = reader.count(ir, graph_for(plan.type))
            if n or note == "":
                return "\n".join(lines + ([note] if note else []) + [f"{n} {plan.type} records"])
            continue
        ids = reader.resolve(ir, graph_for(plan.type))
        if ids:
            body = [f"- {plan.type} '{vocab.names.get(i, i)}'" for i in ids[:limit]]
            if len(ids) > limit:
                body.append(f"(+{len(ids) - limit} more)")
            return "\n".join(lines + ([note] if note else []) + body)
    if skipped:
        return "\n".join(lines + ["(not answered: " + "; ".join(skipped) + ")"])
    return "\n".join(lines + ["(no matching records)"])
