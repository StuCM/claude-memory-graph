"""Plans answered straight from an Arches data_dir — no server, no snapshot.

    from ceist.arches import ArchesVocabulary
    from ceist.alizarin import ask, evaluate
    vocab = ArchesVocabulary.from_data_dir("data")
    print(ask("which listed buildings are on site Leeds Dock?", vocab))

Alizarin reads the thesauri (concept hierarchy, label value ids) and the
vocabulary carries the business data; this module walks the tiles. It is the
reference output: every condition the plan can express is evaluated here,
including links walked backwards, loose links and text — so it is also how a
plan can be checked before it is sent to Rós Madair or Arches Search.

Fine for the data a project keeps on disk; for a large corpus compile to
Rós Madair (`ceist.rosmadair`) instead.
"""

from collections import defaultdict

from . import dates
from .narrate import narrate
from .plan import (Contains, DateRange, EntityRef, HasValue, LinkTo, Mention, Not, Plan,
                   interpret)

__all__ = ["Tiles", "ask", "evaluate"]


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
        return [x.get("resourceId") if isinstance(x, dict) else x for x in value]
    if isinstance(value, dict):
        return [value.get("resourceId")]
    return [value] if isinstance(value, str) else []


class Tiles:
    """The vocabulary's business data, indexed for evaluation."""

    def __init__(self, vocab):
        self.vocab = vocab
        alias = {n["nodeid"]: n.get("alias") for m in vocab.models.values() for n in m.nodes}
        self.type_of: dict[str, str] = {}
        self.values: dict[str, dict[str, list]] = {}       # resource → alias → raw values
        self.out: dict[str, dict[str, set]] = {}            # resource → alias → linked ids
        self.into: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
        self.entries: dict[str, list[dict[str, list]]] = {}  # resource → each tile's alias → values
        for r in vocab.resources:
            ri = r.get("resourceinstance") or {}
            rid = ri.get("resourceinstanceid")
            model = vocab.by_graph.get(ri.get("graph_id"))
            if not rid or model is None:
                continue
            self.type_of[rid] = model.name
            vals, links = defaultdict(list), defaultdict(set)
            entries = []
            for tile in r.get("tiles") or []:
                entry = defaultdict(list)
                for nid, v in (tile.get("data") or {}).items():
                    a = alias.get(nid)
                    if a is None or v is None:
                        continue
                    vals[a].append(v)
                    entry[a].append(v)
                entries.append(dict(entry))
            self.entries[rid] = entries
            for a, vs in vals.items():
                if a in self._link_aliases(model):
                    for v in vs:
                        for target in _links(v):
                            if target:
                                links[a].add(target)
                                self.into[target][a].add(rid)
            self.values[rid], self.out[rid] = dict(vals), dict(links)

    @staticmethod
    def _link_aliases(model) -> set[str]:
        from .arches import LINK_TYPES
        return {n.get("alias") for n in model.nodes if n.get("datatype") in LINK_TYPES}

    def of_type(self, type_name: str) -> set[str]:
        return {r for r, t in self.type_of.items() if t == type_name}

    def text(self, rid: str) -> str:
        words = [self.vocab.names.get(rid, "")]
        for vs in self.values.get(rid, {}).values():
            words += _strings(vs)
        return " ".join(words).lower()


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


def _filter(c, hits: set[str], tiles: Tiles) -> set[str]:
    vocab = tiles.vocab
    if isinstance(c, Not):
        return hits - _filter(c.condition, hits, tiles)
    if isinstance(c, LinkTo) and c.qualifier is not None:
        return _qualified_link(c, hits, tiles)
    if isinstance(c, LinkTo):
        targets = ({c.target.entity.id} if isinstance(c.target, EntityRef)
                   else evaluate(c.target, tiles))
        if c.relation is None:
            return {r for r in hits
                    if any(targets & ids for ids in tiles.out.get(r, {}).values())
                    or any(targets & ids for ids in tiles.into.get(r, {}).values())}
        side = tiles.into if c.direction == "in" else tiles.out
        return {r for r in hits if targets & side.get(r, {}).get(c.relation, set())}
    if isinstance(c, HasValue):
        if c.kind == "concept":
            wanted = {c.value, *vocab.descendants(c.value)}
            return {r for r in hits
                    if any(vocab.concept_of(v) in wanted
                           for raw in tiles.values.get(r, {}).get(c.field, [])
                           for v in (raw if isinstance(raw, list) else [raw])
                           if isinstance(v, str))}
        return {r for r in hits
                if c.value.lower() in " ".join(
                    _strings(tiles.values.get(r, {}).get(c.field, []))).lower()}
    if isinstance(c, DateRange):
        lo = dates.days(c.lo) if c.lo else -dates.OPEN
        hi = dates.days(c.hi) if c.hi else dates.OPEN
        return {r for r in hits
                if any(lo <= k <= hi for raw in tiles.values.get(r, {}).get(c.field, [])
                       for k in _date_keys(raw))}
    if isinstance(c, Mention):
        return {r for r in hits if all(t in tiles.text(r) for t in c.terms)}
    if isinstance(c, Contains):
        return {r for r in hits if c.term.lower() in tiles.text(r)}
    return hits


def _entry_holds(entry: dict, c: LinkTo, targets: set[str], vocab) -> bool:
    """One tile carries both the link and the qualifier value."""
    linked = {x for raw in entry.get(c.relation, []) for x in _links(raw)}
    if not linked & targets:
        return False
    q = c.qualifier
    wanted = {q.value, *vocab.descendants(q.value)}
    return any(vocab.concept_of(v) in wanted
               for raw in entry.get(q.field, [])
               for v in (raw if isinstance(raw, list) else [raw]) if isinstance(v, str))


def _qualified_link(c: LinkTo, hits: set[str], tiles: Tiles) -> set[str]:
    """Linked AND qualified in the SAME entry: "designed by Ada" is a tile
    whose actor is Ada and whose role is Architect — not Ada somewhere and an
    architect somewhere else on the record."""
    vocab = tiles.vocab
    targets = ({c.target.entity.id} if isinstance(c.target, EntityRef)
               else evaluate(c.target, tiles))
    if c.direction == "in":                  # the entry lives on the other record
        return {r for r in hits
                if any(_entry_holds(e, c, {r}, vocab)
                       for s in targets for e in tiles.entries.get(s, []))}
    return {r for r in hits if any(_entry_holds(e, c, targets, vocab)
                                   for e in tiles.entries.get(r, []))}


def evaluate(plan: Plan, tiles: Tiles) -> set[str]:
    """The ids of the records a plan selects."""
    hits = tiles.of_type(plan.type)
    for c in plan.where:
        hits = _filter(c, hits, tiles)
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
