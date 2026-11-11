"""Passes 16-18: "or", the grammar caps, each relation wired to its ends, the
subject, and what each negator negates."""

from ..vocabulary import Relation
from .model import Grounding, Node, _edge
from .nodes import _wrong_end
from .scan import MAX_EDGES, MAX_VARS, NEG_REACH, Scan, _inside


def _or(s: Scan) -> bool:
    """A plan is a conjunction: "raths or cairns" would be read as "raths and cairns".
    True when it refused."""
    g = s.g
    for i, ws, we, w in s.words:
        if w != "or" or i in s.consumed or _inside(ws, we, s.names):
            continue
        if not s.any_of:
            g.refuse = "'or' isn't supported yet; ask one at a time"
            return True
        g.refuse = _either_values(g, i)
        if g.refuse:
            return True
    return False


def _either_values(g: Grounding, i: int) -> str:
    """Join the values either side of the "or" at word `i` when one field can
    hold both; otherwise why not."""
    a = next((v for v in g.values if v.words and (v.either or [v])[-1].words[-1] == i - 1),
             None)
    b = next((v for v in g.values if v.words and v.words[0] == i + 1), None)
    if a is None or b is None:
        return ("'or' is supported only between two values of one field or two named "
                "records; ask one at a time")
    fields = {c.field for c in b.candidates}
    for v in [a, *a.either]:
        fields &= {c.field for c in v.candidates}
    if not fields:
        return (f"'or' joins '{a.phrase}' and '{b.phrase}', which aren't values of one "
                "field; ask one at a time")
    a.either.append(b)
    g.values.remove(b)
    g.notes.append(f"'{a.phrase}' or '{b.phrase}' → either value of "
                   + " / ".join(sorted(fields)))
    return ""


def _wire(s: Scan) -> bool:
    """The grammar caps, and each relation wired to its ends. True when it refused."""
    g = s.g
    if len(g.edges) > MAX_EDGES:
        g.refuse = f"{len(g.edges)} relations — the grammar caps at {MAX_EDGES}"
        return True
    _assign_edges(s)
    if not g.refuse:
        _check_anchors(g, s.relations)
    if (g.refuse.startswith("cannot resolve") and g.anchor is None
            and any(n.kind == "var" for n in g.nodes)):
        if s.free_text:
            # "what technologies do we use?": the relation has no second end, but
            # the question still names what it wants — list that
            dropped = ", ".join(f"'{e.form}'" for e in g.edges)
            g.edges, g.refuse = [], ""
            g.notes.append(f"could not place {dropped}; listing the type instead")
            g.loose = dropped
        elif g.uncovered:
            # "in Down": the end it couldn't find is a word nothing placed; plan.py names that
            g.refuse = ""
    if len(g.vars()) > MAX_VARS:
        g.refuse = f"{len(g.vars())} typed variables — the grammar caps at {MAX_VARS}"
        return True
    _imply_join(g, s.relations)
    return False


def _assign_edges(s: Scan) -> None:
    """Word order picks each relation's neighbours; domain/range orient it and
    fill a missing end (with an implicit typed variable when needed)."""
    g, seen = s.g, s.seen
    for edge in g.edges:
        rel = s.relations.get(edge.relation)
        dom = set(rel.domain) if rel else set()
        rng = set(rel.range) if rel else set()
        parts = sorted(g.nodes, key=lambda n: n.pos)
        fits = (dom | rng)

        def nearest(cands):
            # the nearest neighbour whose type fits the relation, else the nearest
            cands = list(cands)
            return next((n for n in cands if not fits or n.type in fits),
                        cands[0] if cands else None)

        # <=: the type "who" implies sits at 0.0, where a phrase that starts with it ("who made") also is
        left = nearest(n for n in reversed(parts) if n.pos <= edge.pos)
        right = nearest(n for n in parts if n.pos > edge.pos)
        if left is not None and right is not None and left is right:
            right = None
        before = s.words[int(edge.pos) - 1].text if edge.pos >= 1 else ""
        if right is None and left is not None and before == "as":
            # "which areas have X as copyright holder": the phrase names X's role
            right = left
            left = nearest(n for n in reversed(parts) if n.pos < right.pos)

        def fill(hints: set, present: Node | None) -> Node | None:
            cand = next((n for n in parts if n is not present and n.type in hints), None)
            if cand is None and hints:
                t = sorted(hints)[0]
                if t in seen:
                    # never join a relation to itself — a relation whose only
                    # type-fitting candidate is its OTHER end is misgrounded
                    existing = seen[t]
                    return existing if existing is not present else None
                cand = Node("var", t, edge.pos + 0.5, implicit=True)
                seen[t] = cand
                g.nodes.append(cand)
                g.notes.append(f"relation {edge.relation} → implicit {t} variable")
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
        edge.source, edge.target = (right, left) if swapped > straight else (left, right)


def _check_anchors(g: Grounding, relations: dict[str, Relation]) -> None:
    """A named record must be one its link can point at: "what is in Navan
    Fort", a Monument where 'in' points at Sites, would match nothing real.
    Where the link can't say what it points at, the record's own field may be
    meant ("what period is Navan Fort"): `field_of`, which plan.py settles."""
    for e in g.edges:
        rel = relations.get(e.relation)
        if rel is None or e.target is None or e.target.kind != "anchor":
            continue
        a = e.target
        if not rel.joins(e.source.type, a.type):
            g.refuse = _wrong_end(a, e.form, rel.targets(e.source.type))
            return
        if not rel.targets(e.source.type):
            g.field_of = e


def _imply_join(g: Grounding, relations: dict[str, Relation]) -> None:
    """Two types named with no phrase joining them ("sites with buildings
    designed by X"): if exactly ONE relation in the vocabulary connects the
    two types, that is the join. Ambiguity (or none) leaves them unjoined —
    never a guess."""
    pair = g.vars()
    if len(pair) != 2:
        return
    a, b = pair
    if any((e.source is a and e.target is b) or (e.source is b and e.target is a)
           for e in g.edges):
        return
    # a join never implies a role: qualified variants ("actor#Architect") don't count
    plain = [r for r in relations.values() if not r.qualifier]
    candidates = [(r, a, b) for r in plain if a.type in r.domain and b.type in r.range]
    candidates += [(r, b, a) for r in plain if b.type in r.domain and a.type in r.range]
    if len(candidates) != 1:
        if candidates:
            g.notes.append(f"{a.type} and {b.type} could be joined by "
                           f"{', '.join(sorted(c[0].name for c in candidates))}; not guessing")
        return
    rel, src, dst = candidates[0]
    g.edges.append(_edge(rel, (a.pos + b.pos) / 2, form=rel.forms[0] if rel.forms else "",
                         source=src, target=dst))
    g.notes.append(f"{src.type} → {dst.type} joined by {rel.name} (the only relation between them)")


def _subject(s: Scan) -> None:
    """What the question asks for."""
    g = s.g
    implied = s.vocab.implied_types()
    if g.wh in implied:
        g.subject = s.seen.get(implied[g.wh])
    if g.subject is None:
        explicit = sorted(g.vars(), key=lambda n: n.pos)
        g.subject = explicit[0] if explicit else None


def _scope_negations(s: Scan) -> None:
    """Each negator negates the next thing named after it: a relation, a
    value, a date, a number, the text word — or a type, meaning the relation that
    joins it ("sites with no buildings"). Nothing within reach → unplaced,
    and the planner refuses: a dropped "not" inverts the answer."""
    g = s.g
    items: list[tuple[float, str, object]] = []
    items += [(e.pos, "edge", e) for e in g.edges]
    items += [(v.pos, "value", v) for v in g.values]
    items += [(d.pos, "date", d) for d in g.dates]
    items += [(n.pos, "number", n) for n in g.numbers]
    items += [(t.pos, "group", t) for t in g.groups]
    if g.near is not None:
        items.append((g.near.pos, "near", g.near))
    if g.name is not None:
        items.append((g.name.pos, "name", g.name))
    if s.contains_pos is not None:
        items.append((s.contains_pos, "contains", None))
    for n in g.vars():
        if n is g.subject:
            continue
        joins = [e for e in g.edges if n is e.source or n is e.target]
        # "sites with no buildings designed by X": the hop toward the subject
        hops = [e for e in joins
                if (e.target if e.source is n else e.source).kind == "var"]
        pick = hops if len(hops) == 1 else joins if len(joins) == 1 else []
        if pick:
            items.append((n.pos, "edge", pick[0]))
    for i, word in s.negs:
        ahead = [it for it in items if i <= it[0] <= i + NEG_REACH]
        if not ahead:
            g.negation_unplaced = word
            return
        _pos, kind, what = min(ahead, key=lambda it: it[0])
        if kind == "contains":
            g.contains_negated = True
            g.notes.append(f"'{word}' negates the text filter '{g.contains}'")
            continue
        what.negated = True
        name = {"edge": lambda e: f"relation {e.relation}",
                "value": lambda v: f"value '{v.phrase}'",
                "date": lambda d: f"date '{d.phrase}'",
                "number": lambda n: f"'{n.phrase}'",
                "group": lambda t: f"the '{t.phrase}' entry",
                "near": lambda n: f"'{n.phrase}'",
                "name": lambda n: f"the name match '{n.term}'"}[kind](what)
        g.notes.append(f"'{word}' negates {name}")
