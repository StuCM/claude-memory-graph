"""A plan, read back in English — so a person (or an agent) can check what was
understood before trusting the answer. Every output shares it."""

from .dates import label as date_label
from .plan import Contains, DateRange, EntityRef, HasValue, LinkTo, Mention, Not, Plan


def _plural(t: str) -> str:
    if t.endswith("y") and len(t) > 2 and t[-2].lower() not in "aeiou":
        return t[:-1] + "ies"
    if t.endswith(("s", "x", "ch", "sh")):
        return t + "es"
    return t + "s"


def _target(c: LinkTo, forms: bool, canonical: bool) -> str:
    if isinstance(c.target, EntityRef):
        e = c.target.entity
        return f"{e.type} '{e.name}'"
    return _phrase(c.target, forms, canonical, nested=True)


def _singular(verb: str) -> str:
    """The verb after a singular subject: "affect" → "affects", "work on" →
    "works on". Relation names (camelCase) and forms already inflected stay."""
    first, _, rest = verb.partition(" ")
    if not first.isalpha() or not first.islower() or first.endswith("s"):
        return verb
    first = first[:-1] + "ies" if first.endswith("y") and first[-2:-1] not in "aeiou" else (
        first + "es" if first.endswith(("ch", "sh", "x", "o")) else first + "s")
    return f"{first} {rest}".strip()


def _field(name: str, label: str = "") -> str:
    return label or name.replace("_", " ")


def _link(c: LinkTo, forms: bool, canonical: bool, negated: bool) -> str:
    target = _target(c, forms, canonical)
    if c.relation is None:
        return f"{'not ' if negated else ''}linked to {target}"
    if c.style == "field":
        # a node on a record: "whose site is X" / "that are the site of X"
        name = c.relation.replace("_", " ")
        if c.direction == "in":
            return f"that are {'not ' if negated else ''}the {name} of {target}"
        return f"whose {name} is {'not ' if negated else ''}{target}"
    verb = (c.form if forms else "") or c.relation
    if c.direction == "in":
        if negated and isinstance(c.target, Plan):
            # "that no Decision affects", not "that any Decision does not affect"
            return f"that no {target[len('any '):]} {_singular(verb)}"
        return f"that {target} {'does not ' + verb if negated else _singular(verb)}"
    return f"that {'do not ' if negated else ''}{verb} {target}"


def _condition(c, forms: bool, canonical: bool) -> str:
    negated = isinstance(c, Not)
    inner = c.condition if negated else c
    neg = "not " if negated else ""
    if isinstance(inner, LinkTo):
        return _link(inner, forms, canonical, negated)
    if isinstance(inner, HasValue):
        return f"whose {_field(inner.field)} is {neg}{inner.label}"
    if isinstance(inner, DateRange):
        return (f"whose {_field(inner.field, '' if canonical else inner.label)} is {neg}"
                f"{date_label(inner.lo, inner.hi)}")
    if isinstance(inner, Mention):
        return f"that {'do not ' if negated else ''}mention {' '.join(inner.terms)}"
    if isinstance(inner, Contains):
        return f"{neg}mentioning '{inner.term}'"
    return f"{neg}({inner})"


def _phrase(plan: Plan, forms: bool, canonical: bool, nested: bool = False) -> str:
    head = f"any {plan.type}" if nested else _plural(plan.type)
    parts = [_condition(c, forms, canonical) for c in plan.where]
    if canonical:
        parts.sort()              # order-free: a compiler may reorder conditions
    if not parts:
        return head
    return head + " " + " and ".join(parts)


def narrate(plan: Plan, forms: bool = True, canonical: bool = False) -> str:
    """'Find Decisions that affect Project 'quartz'.' / 'Count Buildings whose
    heritage status is Listed and whose construction date is before 1900.'

    `canonical=True` is the comparable form read-back uses: relation names
    instead of the words the question used, field names instead of labels,
    and conditions in a fixed order."""
    if canonical:
        forms = False
    verb = "Count" if plan.count else "Find"
    tail = ", most recent first" if plan.recent else ""
    return f"{verb} {_phrase(plan, forms, canonical)}{tail}."
