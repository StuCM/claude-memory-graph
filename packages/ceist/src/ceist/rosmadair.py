"""Plans → Rós Madair's Query IR, read back, and run over a Rós Madair snapshot.

    from ceist.arches import ArchesVocabulary
    from ceist.rosmadair import ask, compile_plan
    vocab = ArchesVocabulary.from_data_dir("data")
    print(ask("how many listed buildings are on site Leeds Dock?", vocab, "snapshot",
              explain=True))

Mapping (ros-madair-query's serde form; Rós Madair itself is unchanged):

    LinkTo(path, EntityRef, out)     {"has_link": {"path", "target"}}
    LinkTo(path, Plan, out)          {"on_link": {"path", "model", "where"}}  (multi-hop)
    LinkTo(path, Plan, in)           {"on_backlink": {"path", "model", "where"}}  (the other
                                     model's `path` points at the record)
    LinkTo(None, EntityRef, any)     {"backlink": {"target"}}   (linked to it, any field), and
                                     when it is the only condition, the record's own links
                                     read from its tiles (linked_from)
    OnTile(group, [conditions])      {"on_tile": [<each condition>]}   (one tile holds them all:
                                     "designed by Ada" = actor Ada with role Architect).
                                     It reads one tile row, so a condition on a tile above
                                     the group's is refused; so is a link by any field
    LinkTo(…, qualifier=HasValue)    as the OnTile it means
    HasValue(concept)                {"concept": {"path", "op": "descendant_or_self_of", "value"}}
    DateRange(path, lo, hi)          {"range": {"path", "lo", "hi"}}   days since 1970, as
                                     Alizarin's quantize_date (the emitter's own encoding)
    Not(value or date)               {"not": …}
    Not(link)                        a second query, subtracted client-side: Rós Madair
                                     refuses `not` over a link (it is chunk-coarse)
    AnyOf([conditions])              {"any": [<each condition>]}
    Near(record, km, field)          {"bbox": {"path", "min_lng", …}}: the record's box widened
                                     by km, a superset, then each candidate's distance measured
                                     here (geo.keep_within): the IR has no distance predicate
    count / list                     measures ["count_records"] / ["select_ids"]
    group (GroupBy)                  the IR can't group: one query per record the link
                                     can point at, each the plan plus a has_link to it
                                     (group_counts); over GROUP_CAP of them refuses

    NameMatch (top level)            not in the IR: kept beside the query (`names`) and
                                     applied to the records it selects (keep_named)

    Detail(record, fields)           {"record", "nodes"}: the record's own tiles, read for
                                     those nodes (reader.resource_tiles), not a query

A query with nothing that ties it to the model — no filter, or only a
`backlink` or `on_backlink` (whose link may point at other models too) — is
answered by resolving and keeping the model's own records: Rós Madair
doesn't scope a vacuous filter to `model`.

What the IR can't say, the compiler refuses by name (Unsupported), so the
runner moves on to a relaxation or says what it couldn't do: a link walked
backwards to one named record, or with a qualifier, a negated link inside a hop,
free text (the substrate indexes concepts, ranges, geometry and links, not
text), and "most recent".

Every workaround for Rós Madair's current behaviour is written up, ready to
raise upstream, in packages/ceist/ROS-MADAIR.md.

Before a query runs it is read back (`read_back`) into a plan and narrated;
if that differs from what the question was understood to mean, it doesn't run.
"""

import json
from dataclasses import dataclass, field

from . import dates, geo
from .narrate import narrate
from .plan import (
    AnyOf,
    Contains,
    DateRange,
    Detail,
    EntityRef,
    GroupBy,
    HasValue,
    LinkTo,
    Mention,
    NameMatch,
    Near,
    Not,
    OnTile,
    Plan,
    as_tile,
    interpret,
)
from .readback import check

GROUP_CAP = 50


class Unsupported(Exception):
    """A condition Rós Madair's IR can't express (yet)."""


@dataclass
class Compiled:
    """What runs: `query`, minus the records each of `minus` selects, kept to
    those within each `near` ({"record", "km", "path"}) and those whose name
    holds each of `names`; with `group`, counted once per record in `values`
    the group's link points at."""
    query: dict
    minus: list[dict] = field(default_factory=list)
    count: bool = False
    group: GroupBy | None = None
    values: list[str] = field(default_factory=list)
    near: list[dict] = field(default_factory=list)
    names: list = field(default_factory=list)

    def all(self) -> list[dict]:
        return [self.query] + self.minus


def _expr(plan: Plan, vocab) -> dict | None:
    parts = [_cond(c, plan.type, vocab) for c in plan.where]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"all": parts}


def _cond(c, type_name: str, vocab, in_tile: bool = False) -> dict:
    if isinstance(c, Not):
        if isinstance(c.condition, (LinkTo, OnTile)) and not in_tile:
            named = c.condition.group if isinstance(c.condition, OnTile) else c.condition.relation
            raise Unsupported(f"a negated link ('{named}') inside a hop: "
                              "Rós Madair can't negate a link, and only the top level "
                              "can be subtracted")
        return {"not": _cond(c.condition, type_name, vocab, in_tile)}
    if isinstance(c, AnyOf):
        return {"any": [_cond(x, type_name, vocab, in_tile) for x in c.conditions]}
    if isinstance(c, OnTile):
        if in_tile:
            raise Unsupported(f"a {c.group} entry inside another entry")
        one_tile(c, type_name, vocab, "Rós Madair's on_tile")
        return {"on_tile": [_cond(x, type_name, vocab, in_tile=True) for x in c.conditions]}
    if isinstance(c, LinkTo):
        if c.relation is None:
            if not isinstance(c.target, EntityRef):
                raise Unsupported("a loose link to a set of records")
            if in_tile:
                raise Unsupported("a link by any field, on one entry")
            return {"backlink": {"target": c.target.entity.id}}
        if c.direction != "out":
            if c.direction != "in" or c.qualifier is not None or isinstance(c.target, EntityRef):
                raise Unsupported(
                    f"walking '{c.relation}' backwards ({type_name} records that another "
                    f"record's {c.relation} points at) from one named record or with a "
                    f"qualifier: Rós Madair's on_backlink takes a filter on the other "
                    f"model; ask from the other side")
            return {"on_backlink": {"path": c.relation,
                                    "model": vocab.model(c.target.type).graph_id,
                                    "where": _expr(c.target, vocab) or {"all": []}}}
        if c.qualifier is not None:
            return _cond(as_tile(c, vocab.group_of(type_name, c.relation)), type_name, vocab,
                         in_tile)
        if isinstance(c.target, EntityRef):
            return {"has_link": {"path": c.relation, "target": c.target.entity.id}}
        inner = _expr(c.target, vocab) or {"all": []}
        return {"on_link": {"path": c.relation, "model": vocab.model(c.target.type).graph_id,
                            "where": inner}}
    if isinstance(c, HasValue):
        if c.kind != "concept":
            raise Unsupported(f"the literal value {c.label}")
        # controlled lists and legacy concepts alike: Rós Madair interns
        # both through Alizarin's RDM cache (item ids). Not yet run against
        # a snapshot with reference nodes — see ROS-MADAIR.md
        return {"concept": {"path": c.field, "op": "descendant_or_self_of", "value": c.value}}
    if isinstance(c, DateRange):
        return {"range": {"path": c.field,
                          "lo": dates.days(c.lo) if c.lo else -dates.OPEN,
                          "hi": dates.days(c.hi) if c.hi else dates.OPEN}}
    if isinstance(c, Near):
        return {"bbox": _near_box(c.entity.id, c.km, c.field, vocab)}
    if isinstance(c, NameMatch):
        raise Unsupported(f"a name match ('{c.term}') on a linked record: only the records "
                          "asked for are matched by name")
    if isinstance(c, (Mention, Contains)):
        term = c.term if isinstance(c, Contains) else " ".join(c.terms)
        raise Unsupported(f"a free-text condition ('{term}'): the substrate indexes "
                          "concepts, ranges, geometry and links, not text")
    raise Unsupported(f"the condition {c!r}")


def _near_box(record: str, km: float, path: str, vocab) -> dict:
    return {"path": path, **geo.box(vocab.geometry(record), km)}


def tile_fields(conditions) -> list[str]:
    """The nodes an entry's conditions read."""
    out = []
    for c in conditions:
        c = c.condition if isinstance(c, Not) else c
        if isinstance(c, LinkTo) and c.relation:
            out.append(c.relation)
        elif isinstance(c, (HasValue, DateRange)):
            out.append(c.field)
    return out


def one_tile(c: OnTile, type_name: str, vocab, reader: str) -> None:
    """Raise Unsupported unless every condition is on the entry's own tile: a
    backend that reads one tile row can't see the tiles above it."""
    for f in tile_fields(c.conditions):
        g = vocab.group_of(type_name, f)
        if g != c.group:
            raise Unsupported(f"'{f}' is on a {g} tile, not the {c.group} tile itself: "
                              f"{reader} reads one tile, without the tiles above it")


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
    names = [c for c in plan.where
             if isinstance(c.condition if isinstance(c, Not) else c, NameMatch)]
    if names and plan.group:
        raise Unsupported("a name match with a count per linked record")
    values = group_values(plan, vocab) if plan.group else []
    negated = [c for c in plan.where
               if isinstance(c, Not) and isinstance(c.condition, (LinkTo, OnTile))]
    near = [{"record": c.entity.id, "km": c.km, "path": c.field}
            for c in plan.where if isinstance(c, Near)]
    if near and plan.group:
        raise Unsupported(f"counting by {plan.group.relation.replace('_', ' ')} within a distance: "
                          "group_counts doesn't measure it")
    if not negated and not near and not plan.group and not names:
        return Compiled(_query(plan, vocab, "count_records" if plan.count else "select_ids",
                               None if plan.count else limit), count=plan.count)
    base = Plan(plan.type, [c for c in plan.where if c not in negated and c not in names],
                wh=plan.wh)
    return Compiled(_query(base, vocab, "select_ids", None),
                    [_query(Plan(plan.type, [c.condition]), vocab, "select_ids", None)
                     for c in negated], count=plan.count, group=plan.group, values=values,
                    near=near, names=names)


def keep_named(ids, compiled: Compiled, vocab) -> set[str]:
    """The records among `ids` whose names hold every name match of the plan."""
    def holds(c, name):
        return not holds(c.condition, name) if isinstance(c, Not) else c.holds(name)
    return {i for i in ids if all(holds(c, vocab.names.get(i, "")) for c in compiled.names)}


def group_values(plan: Plan, vocab) -> list[str]:
    """The records the group's link can point at: every record of its target
    types, else (targets unknown) every record the plan's type links to by it.
    Raises Unsupported over GROUP_CAP: each is a query of its own."""
    from .alizarin import _links
    path = plan.group.relation
    rel = next(r for r in vocab.relations() if r.name == path)
    ids = set().union(*(vocab.ids_of(t) for t in rel.targets(plan.type)))
    if not ids:
        node = vocab.node(plan.type, path)["nodeid"]
        graph_id = vocab.model(plan.type).graph_id
        for r in vocab.resources:
            if (r.get("resourceinstance") or {}).get("graph_id") != graph_id:
                continue
            for tile in r.get("tiles") or []:
                ids.update(t for t in _links((tile.get("data") or {}).get(node)) if t)
    if len(ids) > GROUP_CAP:
        raise Unsupported(f"counting by {path.replace('_', ' ')}: {len(ids)} records it can "
                          f"point at, over the {GROUP_CAP} a count per record runs")
    return sorted(ids, key=lambda i: vocab.names.get(i, i))


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
    if kind in ("on_link", "on_backlink"):
        sub = vocab.by_graph[body["model"]].name
        return [LinkTo(body["path"], Plan(sub, _conditions(body["where"], sub, vocab)),
                       "out" if kind == "on_link" else "in", style="field")]
    if kind == "backlink":
        e = vocab.entity(body["target"])
        if e is None:
            return [f"a backlink to unknown record {body['target']}"]
        return [LinkTo(None, EntityRef(e), "any")]
    if kind == "any":
        return [AnyOf([c for e in body for c in _conditions(e, type_name, vocab)])]
    if kind == "on_tile":
        parts = [c for e in body for c in _conditions(e, type_name, vocab)]
        first = next(iter(tile_fields(parts)), "")
        return [OnTile(vocab.group_of(type_name, first) if first else "?", parts)]
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
    for n in compiled.near:
        e = vocab.entity(n["record"])
        if e is None:
            where.append(f"near unknown record {n['record']}")
            continue
        # its bbox is the superset this distance is measured within; without it, a mismatch
        box = f"bbox {json.dumps(_near_box(n['record'], n['km'], n['path'], vocab))}"
        if box in where:
            where.remove(box)
        where.append(Near(e, n["km"], n["path"]))
    where += compiled.names
    return Plan(type_name, where, count="count_records" in q["measures"] or compiled.count,
                group=compiled.group)


# ── one record's own fields ──────────────────────────────────────────────

def compile_detail(d: Detail, vocab) -> dict:
    return {"record": d.entity.id,
            "nodes": [vocab.node(d.entity.type, f)["nodeid"] for f, _label in d.fields]}


def read_back_detail(q: dict, vocab) -> Detail:
    e = vocab.entity(q["record"])
    nodes = {n["nodeid"]: n for n in vocab.model(e.type).nodes}
    return Detail(e, [(nodes[i]["alias"], str(nodes[i].get("name") or nodes[i]["alias"]).lower())
                      for i in q["nodes"]])


def _shown(value, datatype: str, vocab) -> list[str]:
    """A tile value as it reads: a concept by its label, a link by the linked record's name."""
    from .alizarin import _atoms, _links
    from .arches import CONTROLLED_TYPES, LINK_TYPES
    if datatype in LINK_TYPES:
        return [vocab.names.get(t, t) for t in _links(value) if t]
    out = []
    for v in _atoms(value):
        if datatype in CONTROLLED_TYPES:
            out.append(vocab.concept_label(vocab.concept_of(v) or v))
        elif isinstance(v, dict):         # a localised string
            text = v.get(vocab.language) or next(iter(v.values()), "")
            out.append(str(text.get("value", "") if isinstance(text, dict) else text))
        else:
            out.append(str(v))
    return [x for x in out if x]


def read_detail(reader, q: dict, vocab) -> list[tuple[str, list[str]]]:
    """Each field the compiled detail names, with the values the record's tiles hold."""
    d = read_back_detail(q, vocab)
    nodes = {n["nodeid"]: n for n in vocab.model(d.entity.type).nodes}
    found: dict[str, list[str]] = {i: [] for i in q["nodes"]}
    for tile in json.loads(reader.resource_tiles(q["record"])):
        for node, value in (tile.get("data") or {}).items():
            if node in found:
                found[node] += [v for v in _shown(value, nodes[node].get("datatype"), vocab)
                                if v not in found[node]]
    return [(label, found[i]) for i, (_f, label) in zip(q["nodes"], d.fields)]


def detail_lines(d: Detail, fields: list[tuple[str, list[str]]]) -> list[str]:
    """"Monument 'Navan Fort, Navan': cultural period Iron Age, Prehistoric"."""
    e = d.entity
    return [f"{e.type} '{e.name}': " + "; ".join(
        f"{label} {', '.join(vs)}" if vs else f"no {label} recorded" for label, vs in fields)]


# ── the runner ───────────────────────────────────────────────────────────

def linked_from(reader, plan: Plan, vocab) -> set[str]:
    """For a plan that is only a loose link to a named record, the records of
    the plan's type that record's own tiles link to. `backlink` finds only
    the records linking to it, and on_backlink needs a named path (ROS-MADAIR.md
    #3), so "which site is Navan Fort at?" reads Navan Fort's tiles instead."""
    from .alizarin import _links
    from .arches import LINK_TYPES
    if not (len(plan.where) == 1 and isinstance(c := plan.where[0], LinkTo)
            and c.relation is None and isinstance(c.target, EntityRef)):
        return set()
    link_nodes = {n["nodeid"] for m in vocab.models.values() for n in m.nodes
                  if n.get("datatype") in LINK_TYPES}
    out = set()
    for tile in json.loads(reader.resource_tiles(c.target.entity.id)):
        for node, value in (tile.get("data") or {}).items():
            if node in link_nodes:
                out.update(t for t in _links(value) if t)
    return out & vocab.ids_of(plan.type)


def group_counts(reader, compiled: Compiled, graph, linked) -> list[tuple[str, int]]:
    """(record, count) for each of the group's values, most first; only the
    top or bottom ones (ties kept) when the group asks for the most or fewest,
    else the ones counted at least once. `linked(query)` gives a query's
    other graphs."""
    minus = set()
    for m in compiled.minus:
        minus |= set(reader.resolve(json.dumps(m), graph, linked=linked(m)))
    base = compiled.query.get("where")
    counts = []
    for value in compiled.values:
        link = {"has_link": {"path": compiled.group.relation, "target": value}}
        query = dict(compiled.query, measures=["select_ids"],
                     where={"all": [base, link]} if base else link)
        query.pop("limit", None)
        ids = set(reader.resolve(json.dumps(query), graph, linked=linked(query)))
        counts.append((value, len(ids - minus)))
    counts.sort(key=lambda x: -x[1])
    if compiled.group.order and counts:
        edge = counts[0 if compiled.group.order == "most" else -1][1]
        return [c for c in counts if c[1] == edge and (edge or compiled.group.order == "fewest")]
    return [c for c in counts if c[1]]


def keep_near(ids, compiled: Compiled, vocab) -> set[str]:
    """The ids within each of the compiled near distances."""
    ids = set(ids)
    for n in compiled.near:
        ids = geo.keep_within(vocab, n["record"], n["km"], ids)
    return ids


def linked_models(query: dict) -> list[str]:
    """The graph ids of the other models a query's hops name: Rós Madair's
    compiler needs their graphs (`linked`) to resolve the paths inside them."""
    found = []

    def walk(expr):
        if isinstance(expr, list):
            for e in expr:
                walk(e)
        elif isinstance(expr, dict):
            for kind, body in expr.items():
                if kind in ("on_link", "on_backlink"):
                    if body["model"] not in found and body["model"] != query["model"]:
                        found.append(body["model"])
                    walk(body["where"])
                else:
                    walk(body)
    walk(query.get("where"))
    return found


def _scoped_by_model(where: dict | None) -> bool:
    """Whether a filter only matches records of the query's model: some
    conjunct names a node of it (a vacuous filter, a backlink or an
    on_backlink doesn't: the link it follows may point at other models)."""
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
    if meaning.detail is not None:
        q = compile_detail(meaning.detail, vocab)
        verdict = check(meaning.detail, read_back_detail(q, vocab))
        if explain:
            lines += ["── understood ──", "  " + narrate(meaning.detail), "── query ──",
                      "  " + json.dumps(q)] + verdict.lines()
        if not verdict.ok:
            return "\n".join(lines + ["(not run: the compiled query reads back differently "
                                      "from the question)"])
        return "\n".join(lines + detail_lines(meaning.detail, read_detail(reader, q, vocab)))
    graphs = {}

    def graph_for(type_name: str):
        # the snapshot doesn't carry the schema; the vocabulary does
        if type_name not in graphs:
            graphs[type_name] = ros_madair.Graph(json.dumps(vocab.model(type_name).doc))
        return graphs[type_name]

    def linked(q: dict) -> list:
        return [graph_for(vocab.by_graph[m].name) for m in linked_models(q)]

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
            lines += [f"  (then only those within {n['km']:g} km of {n['record']}, "
                      "measured on the records' geometry)" for n in compiled.near]
            lines += verdict.lines()
        if not verdict.ok:
            return "\n".join(lines + ["(not run: the compiled query reads back differently "
                                      "from the question)"])
        graph = graph_for(plan.type)
        if compiled.group is not None:
            counts = group_counts(reader, compiled, graph, linked)
            body = [f"- {vocab.names.get(i, i)}: {n} {plan.type} records" for i, n in counts]
            return "\n".join(lines + (body or ["(no matching records)"]))
        scoped = _scoped_by_model(compiled.query.get("where"))
        if compiled.minus or compiled.near or compiled.names or not scoped:
            query = dict(compiled.query, measures=["select_ids"])
            query.pop("limit", None)
            ids = set(reader.resolve(json.dumps(query), graph, linked=linked(query)))
            if not scoped:
                ids &= vocab.ids_of(plan.type)
            ids |= linked_from(reader, plan, vocab)
            for m in compiled.minus:
                ids -= set(reader.resolve(json.dumps(m), graph, linked=linked(m)))
            ids = keep_named(keep_near(ids, compiled, vocab), compiled, vocab)
            ids = sorted(ids, key=lambda i: vocab.names.get(i, i))
            n = len(ids)
        elif plan.count:
            ids, n = [], reader.count(json.dumps(compiled.query), graph,
                                      linked=linked(compiled.query))
        else:
            ids = reader.resolve(json.dumps(compiled.query), graph,
                                 linked=linked(compiled.query))
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
