"""A plan, read back in English — so a person (or an agent) can check what was
understood before trusting the answer. Every output shares it."""

from .plan import Contains, EntityRef, HasValue, LinkTo, Mention, Plan


def _plural(t: str) -> str:
    if t.endswith("y") and len(t) > 2 and t[-2].lower() not in "aeiou":
        return t[:-1] + "ies"
    if t.endswith(("s", "x", "ch", "sh")):
        return t + "es"
    return t + "s"


def _target(c: LinkTo) -> str:
    if isinstance(c.target, EntityRef):
        e = c.target.entity
        return f"{e.type} '{e.name}'"
    return _phrase(c.target, nested=True)


def _condition(c) -> str:
    if isinstance(c, LinkTo):
        verb = c.form or c.relation or "linked to"
        if c.relation is None:
            return f"linked to {_target(c)}"
        if c.direction == "in":
            return f"that {_target(c)} {verb}"
        return f"that {verb} {_target(c)}"
    if isinstance(c, HasValue):
        return f"whose {c.field.replace('_', ' ')} is {c.label}"
    if isinstance(c, Mention):
        return f"that mention {' '.join(c.terms)}"
    if isinstance(c, Contains):
        return f"mentioning '{c.term}'"
    return str(c)


def _phrase(plan: Plan, nested: bool = False) -> str:
    head = _plural(plan.type)
    if nested:
        head = f"any {plan.type}"
    parts = [_condition(c) for c in plan.where]
    if not parts:
        return head
    return head + " " + " and ".join(parts)


def narrate(plan: Plan) -> str:
    """'Find Decisions that affect Project 'quartz'.' / 'Count Buildings whose
    heritage status is Listed.'"""
    verb = "Count" if plan.count else "Find"
    tail = ", most recent first" if plan.recent else ""
    return f"{verb} {_phrase(plan)}{tail}."
