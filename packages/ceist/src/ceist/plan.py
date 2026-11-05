"""The plan: a question's meaning as a small, backend-neutral tree.

    Plan(type, where=[conditions], count, recent)
    conditions:
      LinkTo(relation, EntityRef | Plan, direction)   linked to a record, or to
                                                      records matching a sub-plan —
                                                      (`qualifier`: a shim for OnTile,
                                                      kept for a link walked backwards)
      OnTile(group, [conditions])                     all hold on one tile of that nodegroup,
                                                      read with its ancestor tiles: actor
                                                      Ada with role Architect
      HasValue(field, value)                          a controlled value
      DateRange(field, lo, hi)                        a date in an inclusive range
      Mention(terms)                                  its text mentions these words
      Contains(term)                                  its text contains this word
      Not(condition)                                  the condition does not hold

It maps onto each output: SPARQL (the memory graph), Rós Madair's Query IR
(has_link / on_link / concept), Arches Search's group payload (clauses and
relationship blocks). A backend that can't express a condition says so
rather than dropping it silently.

`interpret()` also returns *relaxations*: the same question asked more
loosely, in order, for a backend to try when the strict plan finds nothing
(the link structure without the leftover word; a text mention instead of a
link). And it refuses — with the reason — when the grounding is too thin to
trust: the planner never guesses.
"""

from dataclasses import dataclass, field, replace

from .ground import Edge, Grounding, Node, ground, is_question
from .vocabulary import Entity, Value, Vocabulary


@dataclass
class EntityRef:
    entity: Entity


@dataclass
class LinkTo:
    relation: str | None              # None: linked by any relation
    target: "EntityRef | Plan"
    direction: str = "out"            # "out": subject → target; "in": target → subject; "any"
    form: str = ""                    # the phrase that named it (for narration)
    style: str = "verb"               # "verb" (affects X) | "field" (whose site is X)
    qualifier: "HasValue | None" = None   # must hold on the same record entry (tile) as
                                          # the link: actor = Ada with role Architect


@dataclass
class HasValue:
    field: str
    value: str
    label: str
    kind: str = "concept"             # "concept" (descendants count) | "literal"


@dataclass
class DateRange:
    field: str
    lo: str | None                    # ISO date, inclusive; None = open
    hi: str | None
    label: str = ""                   # the field as it reads ("construction date")


@dataclass
class Mention:
    terms: list[str]


@dataclass
class Contains:
    term: str


@dataclass
class Not:
    condition: "Condition"


@dataclass
class OnTile:
    group: str                         # the nodegroup alias: one tile of it, with its ancestors
    conditions: list["Condition"]


Condition = LinkTo | HasValue | DateRange | Mention | Contains | Not | OnTile


def as_tile(link: LinkTo, group: str) -> OnTile:
    """A qualified link (the compatibility form) as the tile condition it means."""
    return OnTile(group, [replace(link, qualifier=None), link.qualifier])


@dataclass
class Plan:
    type: str
    where: list = field(default_factory=list)     # conjunction of Conditions
    count: bool = False
    recent: bool = False
    wh: str = ""


@dataclass
class Relaxation:
    plan: Plan
    note: str                          # shown when this relaxation answers
    explain_only: bool = False         # note only in explain mode
    drops: str | None = None           # the word this relaxation ignored (a vocabulary gap)


@dataclass
class Interpretation:
    grounding: Grounding
    plan: Plan | None = None
    relaxations: list[Relaxation] = field(default_factory=list)
    direct: Entity | None = None       # the question is about this record itself
    refused: str = ""                  # why no plan: statement, out of grammar, thin grounding
    statement: bool = False


def interpret(vocab: Vocabulary, text: str, today=None, matcher=None) -> Interpretation:
    if not is_question(text):
        return Interpretation(Grounding(text=text), statement=True,
                              refused="statement-shaped, not a question")
    g = ground(vocab, text, today, matcher)
    out = Interpretation(g)
    if g.refuse:
        out.refused = f"out of grammar ({g.refuse})"
        return out
    if g.negation_unplaced:
        out.refused = (f"'{g.negation_unplaced}' — couldn't tell what it negates "
                       "(ignoring it would invert the answer)")
        return out
    if g.uncovered:
        # words nothing placed would be dropped from the answer: a wider
        # question answered as if it were the one asked. Refuse, naming them.
        out.refused = (f"couldn't place {_quoted(g.uncovered)} — answering without "
                       f"{'it' if len(g.uncovered) == 1 else 'them'} would widen the question"
                       + _did_you_mean(g))
        return out
    if not g.coverage:
        out.refused = "nothing in it names anything this vocabulary knows"
        return out
    # the anchor IS the answer: an entity-only question, or "why" landing on
    # the very record it asks about
    if g.anchor is not None and g.anchor.entity.extra.get("recallable", True) and (
            g.subject is None or (not g.edges and g.subject.type == g.anchor.type)):
        out.direct = g.anchor.entity
        return out
    if g.subject is None:
        out.refused = "no queryable subject" + _did_you_mean(g)
        return out

    try:
        plan = _build(g, g.subject, None)
    except _Cycle as e:
        out.refused = str(e)
        return out
    plan.count, plan.recent, plan.wh = g.count, g.recent, g.wh
    why = _attach_groups(g, plan) or _attach_values(g, plan) or _attach_dates(g, plan)
    if why:
        out.refused = why + _did_you_mean(g)
        return out
    loose_anchor = not g.edges and g.anchor is not None and g.subject is not g.anchor
    if len(g.anchors) > 1 and not all(_linked(g, a) for a in g.anchors):
        out.plan = None
        out.refused = ("named " + " and ".join(f"{a.type} '{a.name}'" for a in g.anchors)
                       + ", but couldn't tell how each relates to what's asked")
        return out
    joined = _reached(g, g.subject)
    stray = [n for n in g.nodes if not any(n is j for j in joined)
             and not (loose_anchor and n is g.anchor)]
    if stray:
        out.plan = None
        out.refused = ("named " + " and ".join(f"{n.type} '{n.name}'" if n.kind == "anchor"
                                               else f"{n.type} records" for n in stray)
                       + f", but couldn't tell how {'it relates' if len(stray) == 1 else 'they relate'}"
                       f" to the {g.subject.type} records asked for")
        return out
    if loose_anchor:
        plan.where.append(LinkTo(None, EntityRef(g.anchor.entity), "any"))
    if g.contains:
        plan.where.append(Not(Contains(g.contains)) if g.contains_negated
                          else Contains(g.contains))
    out.plan = plan

    if loose_anchor and getattr(vocab, "free_text", False):
        mention = _replace(plan, lambda c: Mention(g.anchor.match_terms)
                           if isinstance(c, LinkTo) and c.relation is None else c)
        out.relaxations.append(Relaxation(
            mention, "(no rows via links — retrying as text mention)", explain_only=True))
    if g.contains and not g.contains_negated:
        without = _replace(plan, lambda c: None if isinstance(c, Contains) else c)
        note = (f"(ignored ungrounded '{g.contains}' — the link structure answered without it)"
                if loose_anchor else f"(ignored '{g.contains}' — it matched nothing)")
        out.relaxations.append(Relaxation(without, note, drops=g.contains))
    return out


def _linked(g: Grounding, node: Node) -> bool:
    return any(node is e.source or node is e.target for e in g.edges)


class _Cycle(Exception):
    """Two relations join the same things in a loop: which is meant is a guess."""


def _reached(g: Grounding, start: Node) -> list[Node]:
    """The nodes the edges join to `start`: _build drops any other silently."""
    out, todo = [start], [start]
    while todo:
        n = todo.pop()
        for e in g.edges:
            for a, b in ((e.source, e.target), (e.target, e.source)):
                if a is n and not any(b is x for x in out):
                    out.append(b)
                    todo.append(b)
    return out


def _build(g: Grounding, node: Node, via: Edge | None, path: tuple = ()) -> Plan:
    plan = Plan(node.type)
    path = path + (node,)
    for edge in g.edges:
        if edge is via or node not in (edge.source, edge.target):
            continue
        other = edge.target if edge.source is node else edge.source
        direction = "out" if edge.source is node else "in"
        if other.kind != "anchor" and any(other is n for n in path):
            raise _Cycle(f"'{edge.form or edge.relation}' and "
                         f"'{via.form or via.relation if via else '?'}' both join "
                         f"{node.type} and {other.type}; say which is meant")
        target = (EntityRef(other.entity) if other.kind == "anchor"
                  else _build(g, other, edge, path))
        qual = (HasValue(edge.qualifier[0], edge.qualifier[1], edge.qualifier[2])
                if edge.qualifier else None)
        link = LinkTo(edge.path or edge.relation, target, direction, form=edge.form,
                      style=edge.style, qualifier=qual)
        if qual is not None and direction == "out":
            # a link walked backwards keeps the shim: its tile is on the other record
            link = as_tile(link, edge.group)
        plan.where.append(Not(link) if edge.negated else link)
    return plan


def _plans(plan: Plan):
    yield plan
    todo = list(plan.where)
    while todo:
        c = todo.pop(0)
        c = c.condition if isinstance(c, Not) else c
        if isinstance(c, OnTile):
            todo[:0] = c.conditions
        elif isinstance(c, LinkTo) and isinstance(c.target, Plan):
            yield from _plans(c.target)


def _quoted(words) -> str:
    return ", ".join(f"'{w}'" for w in words)


def _did_you_mean(g: Grounding) -> str:
    return "".join(f"; did you mean {' or '.join(opts)} for '{w}'?" for w, opts in g.suggestions)


def _attach_groups(g: Grounding, plan: Plan) -> str:
    """Each group phrase joins the plan of its model as one tile condition; a
    lone condition is the same on any tile, so it stands alone."""
    for gm in g.groups:
        p = next((p for p in _plans(plan) if p.type == gm.group.model), None)
        if p is None:
            g.uncovered.append(gm.phrase)
            return f"'{gm.phrase}' describes {gm.group.model} records, which nothing asked for is"
        conds = [HasValue(v.field, v.value, v.label, v.kind) for v in gm.values]
        if gm.date is not None:
            f = gm.group.date
            conds.append(DateRange(f.field, gm.date.lo, gm.date.hi, f.label))
        c = conds[0] if len(conds) == 1 else OnTile(gm.group.name, conds)
        p.where.append(Not(c) if gm.negated else c)
    return ""


def _attach_values(g: Grounding, plan: Plan) -> str:
    """Each named value joins the plan whose type has that field: the subject
    first, then any linked sub-plan. A value no type in the plan can hold
    refuses, as a date does: ignoring it would answer a wider question."""
    for vm in g.values:
        placed = False
        for p in _plans(plan):
            fit = [v for v in vm.candidates if not v.owners or p.type in v.owners]
            if fit:
                v = fit[0]
                hv = HasValue(v.field, v.value, v.label, v.kind)
                p.where.append(Not(hv) if vm.negated else hv)
                placed = True
                break
        if not placed:
            g.uncovered.append(vm.phrase)
            return (f"'{vm.phrase}' is a value of "
                    f"{', '.join(sorted({c.field for c in vm.candidates}))}, "
                    "which nothing asked for has")
    return ""


def _attach_dates(g: Grounding, plan: Plan) -> str:
    """Each date joins the first plan with a date field that fits; a date
    nothing can hold, or one that could be either of two dates, refuses —
    a date silently ignored would answer a different question."""
    for dm in g.dates:
        placed = False
        for p in _plans(plan):
            fit = [f for f in dm.fields if not f.owners or p.type in f.owners]
            if len(fit) > 1:
                fit = [f for f in fit if f.default] or fit
            if len(fit) > 1:
                return (f"'{dm.phrase}' could be the {' or the '.join(f.label for f in fit)} "
                        f"of {p.type}; say which (e.g. '{fit[0].forms[0] if fit[0].forms else fit[0].label} "
                        f"{dm.phrase}')")
            if fit:
                f = fit[0]
                g.notes.append(f"'{dm.phrase}' → {f.label} of {p.type}")
                dr = DateRange(f.field, dm.lo, dm.hi, f.label)
                p.where.append(Not(dr) if dm.negated else dr)
                placed = True
                break
        if not placed:
            return f"'{dm.phrase}' names a date, but nothing asked for has one"
    return ""


def _replace(plan: Plan, fn) -> Plan:
    where = []
    for c in plan.where:
        new = fn(_within(c, fn))
        if new is not None:
            where.append(new)
    return Plan(plan.type, where, plan.count, plan.recent, plan.wh)


def _within(c, fn):
    """`c`, with `fn` applied in each sub-plan it links to."""
    if isinstance(c, Not):
        return Not(_within(c.condition, fn))
    if isinstance(c, OnTile):
        return OnTile(c.group, [_within(x, fn) for x in c.conditions])
    if isinstance(c, LinkTo) and isinstance(c.target, Plan):
        return replace(c, target=_replace(c.target, fn))
    return c


def describe(value: Value) -> str:
    return f"{value.field} = {value.label}"
