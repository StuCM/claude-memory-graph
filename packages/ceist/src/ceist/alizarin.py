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

from .narrate import narrate
from .plan import Contains, EntityRef, HasValue, LinkTo, Mention, Plan, interpret

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
        for r in vocab.resources:
            ri = r.get("resourceinstance") or {}
            rid = ri.get("resourceinstanceid")
            model = vocab.by_graph.get(ri.get("graph_id"))
            if not rid or model is None:
                continue
            self.type_of[rid] = model.name
            vals, links = defaultdict(list), defaultdict(set)
            for tile in r.get("tiles") or []:
                for nid, v in (tile.get("data") or {}).items():
                    a = alias.get(nid)
                    if a is None or v is None:
                        continue
                    vals[a].append(v)
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


def evaluate(plan: Plan, tiles: Tiles) -> set[str]:
    """The ids of the records a plan selects."""
    vocab = tiles.vocab
    hits = tiles.of_type(plan.type)
    for c in plan.where:
        if isinstance(c, LinkTo):
            if isinstance(c.target, EntityRef):
                targets = {c.target.entity.id}
            else:
                targets = evaluate(c.target, tiles)
            if c.relation is None:
                hits = {r for r in hits
                        if any(targets & ids for ids in tiles.out.get(r, {}).values())
                        or any(targets & ids for ids in tiles.into.get(r, {}).values())}
            elif c.direction == "in":
                hits = {r for r in hits if targets & tiles.into.get(r, {}).get(c.relation, set())}
            else:
                hits = {r for r in hits if targets & tiles.out.get(r, {}).get(c.relation, set())}
        elif isinstance(c, HasValue):
            if c.kind == "concept":
                wanted = {c.value, *vocab.descendants(c.value)}
                hits = {r for r in hits
                        if any(vocab.concept_of(v) in wanted
                               for raw in tiles.values.get(r, {}).get(c.field, [])
                               for v in (raw if isinstance(raw, list) else [raw])
                               if isinstance(v, str))}
            else:
                hits = {r for r in hits
                        if c.value.lower() in " ".join(
                            _strings(tiles.values.get(r, {}).get(c.field, []))).lower()}
        elif isinstance(c, Mention):
            hits = {r for r in hits if all(t in tiles.text(r) for t in c.terms)}
        elif isinstance(c, Contains):
            hits = {r for r in hits if c.term.lower() in tiles.text(r)}
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
