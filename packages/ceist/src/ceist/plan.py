"""The plan: a question's meaning as a small, backend-neutral tree.

    Plan(type, where=[conditions], count, recent)
    conditions:
      LinkTo(relation, EntityRef | Plan, direction)   linked to a record, or to
                                                      records matching a sub-plan
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

COVERAGE_MIN = 0.6


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


Condition = LinkTo | HasValue | DateRange | Mention | Contains | Not


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


def interpret(vocab: Vocabulary, text: str, coverage_min: float = COVERAGE_MIN,
              today=None) -> Interpretation:
    if not is_question(text):
        return Interpretation(Grounding(text=text), statement=True,
                              refused="statement-shaped, not a question")
    g = ground(vocab, text, today)
    out = Interpretation(g)
    if g.refuse:
        out.refused = f"out of grammar ({g.refuse})"
        return out
    if g.negation_unplaced:
        out.refused = (f"'{g.negation_unplaced}' — couldn't tell what it negates "
                       "(ignoring it would invert the answer)")
        return out
    if g.coverage < coverage_min:
        out.refused = f"grounding coverage {g.coverage:.0%} below {coverage_min:.0%}"
        return out
    # the anchor IS the answer: an entity-only question, or "why" landing on
    # the very record it asks about
    if g.anchor is not None and g.anchor.entity.extra.get("recallable", True) and (
            g.subject is None or (not g.edges and g.subject.type == g.anchor.type)):
        out.direct = g.anchor.entity
        return out
    if g.subject is None:
        out.refused = "no queryable subject"
        return out

    plan = _build(g, g.subject, None)
    plan.count, plan.recent, plan.wh = g.count, g.recent, g.wh
    _attach_values(g, plan)
    why = _attach_dates(g, plan)
    if why:
        out.refused = why
        return out
    loose_anchor = not g.edges and g.anchor is not None and g.subject is not g.anchor
    if len(g.anchors) > 1 and not all(_linked(g, a) for a in g.anchors):
        out.plan = None
        out.refused = ("named " + " and ".join(f"{a.type} '{a.name}'" for a in g.anchors)
                       + ", but couldn't tell how each relates to what's asked")
        return out
    if loose_anchor:
        plan.where.append(LinkTo(None, EntityRef(g.anchor.entity), "any"))
    if g.contains:
        plan.where.append(Not(Contains(g.contains)) if g.contains_negated
                          else Contains(g.contains))
    out.plan = plan

    if loose_anchor:
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


def _build(g: Grounding, node: Node, via: Edge | None) -> Plan:
    plan = Plan(node.type)
    for edge in g.edges:
        if edge is via or node not in (edge.source, edge.target):
            continue
        other = edge.target if edge.source is node else edge.source
        direction = "out" if edge.source is node else "in"
        target = EntityRef(other.entity) if other.kind == "anchor" else _build(g, other, edge)
        link = LinkTo(edge.relation, target, direction, form=edge.form, style=edge.style)
        plan.where.append(Not(link) if edge.negated else link)
    return plan


def _plans(plan: Plan):
    yield plan
    for c in plan.where:
        c = c.condition if isinstance(c, Not) else c
        if isinstance(c, LinkTo) and isinstance(c.target, Plan):
            yield from _plans(c.target)


def _attach_values(g: Grounding, plan: Plan) -> None:
    """Each named value joins the plan whose type has that field: the subject
    first, then any linked sub-plan. A value no type in the plan can hold
    stays uncovered, and says so."""
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
            g.notes.append(f"'{vm.phrase}' is a value of "
                           f"{', '.join(sorted({c.field for c in vm.candidates}))}, "
                           "which nothing asked for has; ignored")
            g.uncovered.append(vm.phrase)


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
        if isinstance(c, LinkTo) and isinstance(c.target, Plan):
            c = replace(c, target=_replace(c.target, fn))
        elif (isinstance(c, Not) and isinstance(c.condition, LinkTo)
              and isinstance(c.condition.target, Plan)):
            c = Not(replace(c.condition, target=_replace(c.condition.target, fn)))
        new = fn(c)
        if new is not None:
            where.append(new)
    return Plan(plan.type, where, plan.count, plan.recent, plan.wh)


def describe(value: Value) -> str:
    return f"{value.field} = {value.label}"
