"""The plan: a question's meaning as a small, backend-neutral tree.

    Plan(type, where=[conditions], count, recent)
    conditions:
      LinkTo(relation, EntityRef | Plan, direction)   linked to a record, or to
                                                      records matching a sub-plan
      HasValue(field, value)                          a controlled value
      Mention(terms)                                  its text mentions these words
      Contains(term)                                  its text contains this word

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

from dataclasses import dataclass, field

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


@dataclass
class HasValue:
    field: str
    value: str
    label: str
    kind: str = "concept"             # "concept" (descendants count) | "literal"


@dataclass
class Mention:
    terms: list[str]


@dataclass
class Contains:
    term: str


Condition = LinkTo | HasValue | Mention | Contains


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


def interpret(vocab: Vocabulary, text: str, coverage_min: float = COVERAGE_MIN) -> Interpretation:
    if not is_question(text):
        return Interpretation(Grounding(text=text), statement=True,
                              refused="statement-shaped, not a question")
    g = ground(vocab, text)
    out = Interpretation(g)
    if g.refuse:
        out.refused = f"out of grammar ({g.refuse})"
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
    loose_anchor = not g.edges and g.anchor is not None and g.subject is not g.anchor
    if len(g.anchors) > 1 and not all(_linked(g, a) for a in g.anchors):
        out.plan = None
        out.refused = ("named " + " and ".join(f"{a.type} '{a.name}'" for a in g.anchors)
                       + ", but couldn't tell how each relates to what's asked")
        return out
    if loose_anchor:
        plan.where.append(LinkTo(None, EntityRef(g.anchor.entity), "any"))
    if g.contains:
        plan.where.append(Contains(g.contains))
    out.plan = plan

    if loose_anchor:
        mention = _replace(plan, lambda c: Mention(g.anchor.match_terms)
                           if isinstance(c, LinkTo) and c.relation is None else c)
        out.relaxations.append(Relaxation(
            mention, "(no rows via links — retrying as text mention)", explain_only=True))
    if g.contains:
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
        plan.where.append(LinkTo(edge.relation, target, direction, form=edge.form))
    return plan


def _plans(plan: Plan):
    yield plan
    for c in plan.where:
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
                p.where.append(HasValue(v.field, v.value, v.label, v.kind))
                placed = True
                break
        if not placed:
            g.notes.append(f"'{vm.phrase}' is a value of "
                           f"{', '.join(sorted({c.field for c in vm.candidates}))}, "
                           "which nothing asked for has; ignored")
            g.uncovered.append(vm.phrase)


def _replace(plan: Plan, fn) -> Plan:
    where = []
    for c in plan.where:
        if isinstance(c, LinkTo) and isinstance(c.target, Plan):
            c = LinkTo(c.relation, _replace(c.target, fn), c.direction, c.form)
        new = fn(c)
        if new is not None:
            where.append(new)
    return Plan(plan.type, where, plan.count, plan.recent, plan.wh)


def describe(value: Value) -> str:
    return f"{value.field} = {value.label}"
