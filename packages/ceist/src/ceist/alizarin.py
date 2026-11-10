"""Plans answered straight from an Arches data_dir — no server, no snapshot.

    from ceist.arches import ArchesVocabulary
    from ceist.alizarin import ask, evaluate
    vocab = ArchesVocabulary.from_data_dir("data")
    print(ask("which listed buildings are on site Leeds Dock?", vocab))

Alizarin reads the data: each resource's tiles become its tree
(`tiles_to_json_tree`), walked with the graph's alias schema, so values are
read by datatype and child tiles stay under their parent tile. This module
evaluates plans over them. It is the reference output: every condition the
plan can express is evaluated here, including links walked backwards, loose
links and text — so it is also how a plan can be checked before it is sent
to Rós Madair or Arches Search.

Fine for the data a project keeps on disk; for a large corpus compile to
Rós Madair (`ceist.rosmadair`) instead.
"""

import json
from collections import defaultdict
from dataclasses import replace

import alizarin

from . import dates, geo
from .narrate import narrate
from .plan import (
    AnyOf,
    Contains,
    DateRange,
    EntityRef,
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

__all__ = ["RecordTiles", "Tiles", "ask", "evaluate"]


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        v = value.get("value")
        return [v] if isinstance(v, str) else [s for x in value.values() for s in _strings(x)]
    if isinstance(value, list):
        return [s for x in value for s in _strings(x)]
    return []


def _links(value) -> list[str]:
    if isinstance(value, list):
        return [x for v in value for x in _links(v)]
    if isinstance(value, dict):
        return [value.get("resourceId")]
    return [value] if isinstance(value, str) else []


def _atoms(value) -> list:
    """A leaf's values, flat: Alizarin wraps a leaf inside a repeated group in
    a list, and list datatypes are lists themselves."""
    if isinstance(value, list):
        return [a for v in value for a in _atoms(v)]
    return [] if value is None else [value]


class RecordTiles:
    """Each record's own tiles from the business data, served as Rós Madair's
    reader serves them (resource_tiles)."""

    def __init__(self, vocab):
        self.by_id = {r["resourceinstance"]["resourceinstanceid"]: r.get("tiles") or []
                      for r in vocab.resources}

    def resource_tiles(self, rid: str) -> str:
        return json.dumps(self.by_id.get(rid, []))


class Tiles:
    """The vocabulary's business data, read through Alizarin, indexed for evaluation."""

    def __init__(self, vocab):
        from .arches import LINK_TYPES
        self.vocab = vocab
        self.type_of: dict[str, str] = {}
        self.values: dict[str, dict[str, list]] = {}       # resource → alias → values
        self.texts: dict[str, list[str]] = {}               # resource → text values
        self.out: dict[str, dict[str, set]] = {}            # resource → alias → linked ids
        self.into: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
        # resource → one entry per tile: (its nodegroup id, its alias → values,
        # with its ancestor tiles' values too: a condition split between a
        # tile and its parent holds; one split across sibling tiles doesn't)
        self.entries: dict[str, list[tuple[str, dict[str, list]]]] = {}
        for r in vocab.resources:
            ri = r.get("resourceinstance") or {}
            rid = ri.get("resourceinstanceid")
            model = vocab.by_graph.get(ri.get("graph_id"))
            if not rid or model is None:
                continue
            self.type_of[rid] = model.name
            tree = alizarin.tiles_to_json_tree(json.dumps(r))
            vals, entries = defaultdict(list), []
            info = {n["alias"]: n for n in model.nodes if n.get("alias")}
            self._walk(tree, model.schema, info, None, {}, vals, entries)
            self.entries[rid] = entries
            links = defaultdict(set)
            text = [vocab.names.get(rid, "")]
            for a, vs in vals.items():
                if (info.get(a) or {}).get("datatype") in LINK_TYPES:
                    for target in _links(vs):
                        if target:
                            links[a].add(target)
                            self.into[target][a].add(rid)
                else:
                    text += _strings(vs)
            self.values[rid], self.out[rid] = dict(vals), dict(links)
            self.texts[rid] = text

    def _walk(self, tree: dict, schema: dict, info: dict, group, inherited: dict,
              vals: dict, entries: list) -> None:
        """One tile of nodegroup `group` (None: the resource root), given as
        its tree and alias schema; `inherited` holds the values of the tiles
        above it. Adds its entry, then walks the tiles below it."""
        own: dict[str, list] = defaultdict(list)
        leaf_tiles: list[tuple[str, list]] = []           # a leaf that is a tile of its own
        subtiles: list[tuple[dict, dict, str]] = []

        def collect(t: dict, sch: dict) -> None:
            for alias, s in sch.items():
                if alias not in t:
                    continue
                ng = (info.get(alias) or {}).get("nodegroup_id")
                inside = group is not None and ng == group
                raw = t[alias]
                if s.get("children"):
                    for inst in (raw if isinstance(raw, list) else [raw]):
                        if not isinstance(inst, dict):
                            continue
                        if inside:
                            collect(inst, s["children"])   # a semantic node within this tile
                        else:
                            subtiles.append((inst, s["children"], ng))
                    continue
                atoms = _atoms(raw)
                vals[alias] += atoms
                if inside:
                    own[alias] += atoms
                else:
                    leaf_tiles.append((alias, atoms))

        collect(tree, schema)
        here = {a: list(v) for a, v in inherited.items()}
        for a, vs in own.items():
            here[a] = here.get(a, []) + vs
        if group is not None:
            entries.append((group, here))
        for alias, atoms in leaf_tiles:
            entries.append(((info.get(alias) or {}).get("nodegroup_id"),
                            dict(here, **{alias: here.get(alias, []) + atoms})))
        for inst, sch, ng in subtiles:
            self._walk(inst, sch, info, ng, here, vals, entries)

    def of_type(self, type_name: str) -> set[str]:
        return {r for r, t in self.type_of.items() if t == type_name}

    def text(self, rid: str) -> str:
        return " ".join(self.texts.get(rid, [])).lower()


def _date_keys(raw) -> list[int]:
    out = []
    for v in (raw if isinstance(raw, list) else [raw]):
        s = v.get("value") if isinstance(v, dict) else v
        if isinstance(s, str):
            try:
                out.append(dates.days(s))
            except ValueError:
                pass
    return out


def _filter(c, hits: set[str], tiles: Tiles, type_name: str) -> set[str]:
    vocab = tiles.vocab
    if isinstance(c, Not):
        return hits - _filter(c.condition, hits, tiles, type_name)
    if isinstance(c, LinkTo) and c.qualifier is not None:
        if c.direction == "in":
            return _qualified_link(c, hits, tiles)
        c = as_tile(c, vocab.group_of(type_name, c.relation))
    if isinstance(c, OnTile):
        return _on_tile(c, hits, tiles, type_name)
    if isinstance(c, AnyOf):
        return set().union(*(_filter(x, hits, tiles, type_name) for x in c.conditions))
    if isinstance(c, LinkTo):
        targets = _targets(c, tiles)
        if c.relation is None:
            return {r for r in hits
                    if any(targets & ids for ids in tiles.out.get(r, {}).values())
                    or any(targets & ids for ids in tiles.into.get(r, {}).values())}
        side = tiles.into if c.direction == "in" else tiles.out
        return {r for r in hits if targets & side.get(r, {}).get(c.relation, set())}
    if isinstance(c, HasValue):
        return {r for r in hits if _value_holds(c, tiles.values.get(r, {}), vocab)}
    if isinstance(c, DateRange):
        return {r for r in hits if _date_holds(c, tiles.values.get(r, {}))}
    if isinstance(c, Mention):
        return {r for r in hits if all(t in tiles.text(r) for t in c.terms)}
    if isinstance(c, Contains):
        return {r for r in hits if c.term.lower() in tiles.text(r)}
    if isinstance(c, NameMatch):
        return {r for r in hits if c.holds(vocab.names.get(r, ""))}
    if isinstance(c, Near):
        return geo.keep_within(vocab, c.entity.id, c.km, hits)
    raise TypeError(f"{c!r} can't be evaluated")


def _targets(c: LinkTo, tiles: Tiles) -> set[str]:
    return ({c.target.entity.id} if isinstance(c.target, EntityRef)
            else evaluate(c.target, tiles))


def _value_holds(c: HasValue, values: dict, vocab) -> bool:
    if c.kind == "concept":
        wanted = {c.value, *vocab.descendants(c.value)}
        return any(vocab.concept_of(v) in wanted for v in _atoms(values.get(c.field, [])))
    return c.value.lower() in " ".join(_strings(values.get(c.field, []))).lower()


def _date_holds(c: DateRange, values: dict) -> bool:
    lo = dates.days(c.lo) if c.lo else -dates.OPEN
    hi = dates.days(c.hi) if c.hi else dates.OPEN
    return any(lo <= k <= hi for raw in values.get(c.field, []) for k in _date_keys(raw))


def _entry_holds(entry: dict, conditions: list, targets: dict, vocab) -> bool:
    """Every condition holds on one entry; `targets` has each link's target ids."""
    for c in conditions:
        negated = isinstance(c, Not)
        inner = c.condition if negated else c
        if isinstance(inner, LinkTo):
            linked = {x for raw in entry.get(inner.relation, []) for x in _links(raw)}
            held = bool(linked & targets[id(inner)])
        elif isinstance(inner, HasValue):
            held = _value_holds(inner, entry, vocab)
        elif isinstance(inner, DateRange):
            held = _date_holds(inner, entry)
        else:
            raise TypeError(f"{inner!r} can't be evaluated on one entry")
        if held == negated:
            return False
    return True


def _on_tile(c: OnTile, hits: set[str], tiles: Tiles, type_name: str) -> set[str]:
    """Records with one tile of the group whose values (with its ancestor
    tiles') meet every condition: "designed by Ada" is a tile whose actor is
    Ada and whose role is Architect — not Ada somewhere and an architect
    somewhere else on the record."""
    targets = {}
    for x in c.conditions:
        x = x.condition if isinstance(x, Not) else x
        if isinstance(x, LinkTo):
            if x.relation is None or x.direction != "out":
                raise TypeError(f"{x!r} isn't a link one entry holds")
            targets[id(x)] = _targets(x, tiles)
    group = (tiles.vocab.node(type_name, c.group) or {}).get("nodegroup_id")
    return {r for r in hits
            if any(g == group and _entry_holds(e, c.conditions, targets, tiles.vocab)
                   for g, e in tiles.entries.get(r, []))}


def _qualified_link(c: LinkTo, hits: set[str], tiles: Tiles) -> set[str]:
    """A qualified link walked backwards: the entry is on the record at the
    other end, and links to this one."""
    link = replace(c, qualifier=None, direction="out")
    found = set()
    for s in _targets(c, tiles):
        for _, e in tiles.entries.get(s, []):
            found |= {r for r in hits - found
                      if _entry_holds(e, [link, c.qualifier], {id(link): {r}}, tiles.vocab)}
    return found


def evaluate(plan: Plan, tiles: Tiles) -> set[str]:
    """The ids of the records a plan selects."""
    hits = tiles.of_type(plan.type)
    for c in plan.where:
        hits = _filter(c, hits, tiles, plan.type)
    return hits


def ask(text: str, vocab, explain: bool = False, limit: int = 25, tiles: Tiles | None = None) -> str:
    """Answer a question from the data_dir the vocabulary was read from."""
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
    if meaning.detail is not None:
        from .rosmadair import compile_detail, detail_lines, read_detail
        q = compile_detail(meaning.detail, vocab)
        if explain:
            lines += ["── understood ──", "  " + narrate(meaning.detail)]
        return "\n".join(lines + detail_lines(meaning.detail,
                                               read_detail(RecordTiles(vocab), q, vocab)))
    if meaning.plan.group is not None:
        return "\n".join(lines + ["(not answered: counting by a field is answered over "
                                   "Rós Madair, not here)"])
    tiles = tiles or Tiles(vocab)
    for plan, note in [(meaning.plan, "")] + [(r.plan, r.note) for r in meaning.relaxations]:
        if explain:
            lines += ["── understood ──", "  " + narrate(plan)]
        ids = evaluate(plan, tiles)
        if plan.count and (ids or not note):
            return "\n".join(lines + ([note] if note else []) + [f"{len(ids)} {plan.type} records"])
        if ids:
            names = sorted(vocab.names.get(i, i) for i in ids)
            body = [f"- {plan.type} '{n}'" for n in names[:limit]]
            if len(names) > limit:
                body.append(f"(+{len(names) - limit} more)")
            return "\n".join(lines + ([note] if note else []) + body)
    return "\n".join(lines + ["(no matching records)"])
