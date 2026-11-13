"""The site gate's checks of words in combination, beyond one-piece templates: composition questions
from the schema, each with the plan it must read as; name probes, which must never bind a record by
part of its name; and the site's own practice questions (`ceist setup --questions`).

    type + link + type      which organisations occupy buildings?
    type + link + value     keyholders of hospitals, which persons are keyholder of coastal buildings?
    type + value + number   hospitals with occupant capacity over 10
    two links               which persons are keyholder of buildings that are occupied by organisations?
"""

import json
from itertools import combinations
from pathlib import Path

from .plan import AnyOf, EntityRef, HasValue, LinkTo, Near, Not, NumberRange, OnTile, Plan
from .questions import _AT, _VERBS, _link_question, _plural
from .text import _WORD, marks, plural, terms
from .vocab_rules import word_like

SHAPES = ("composition", "name probe", "site question")
FAMILIES = ("type + link + type", "type + link + value", "type + value + number", "two links")
COMPOSITIONS = 600
NAMES = 150                # records whose names are probed
WHOLE_WORDS = 4            # names up to this many words are probed by every proper subset
NUMBER = 10


# ── reading a plan back as a comparable shape ────────────────────────────────
def signature(plan: Plan) -> tuple:
    """What a plan asks, order and wording aside: two plans with the same signature find the same records."""
    return (plan.type, plan.count, tuple(sorted(_condition(c) for c in plan.where)))


def _condition(c) -> str:
    if isinstance(c, Not):
        return f"not {_condition(c.condition)}"
    if isinstance(c, OnTile):
        return " and ".join(sorted(_condition(x) for x in c.conditions))
    if isinstance(c, AnyOf):
        return "any of " + " | ".join(sorted(_condition(x) for x in c.conditions))
    if isinstance(c, HasValue):
        return f"{c.field} = {c.label.lower()}"
    if isinstance(c, NumberRange):
        lo = f"{'>=' if c.lo_inclusive else '>'} {c.lo:g}" if c.lo is not None else ""
        hi = f"{'<=' if c.hi_inclusive else '<'} {c.hi:g}" if c.hi is not None else ""
        return f"{c.field} {lo} {hi}".strip()
    if isinstance(c, LinkTo):
        far = f"record {c.target.entity.id}" if isinstance(c.target, EntityRef) else repr(signature(c.target))
        qualifier = f" ({_condition(c.qualifier)})" if c.qualifier is not None else ""
        return f"{(c.relation or '').split('#')[0]} {c.direction} {far}{qualifier}"
    return repr(c)


def bound(m) -> set[str]:
    """The ids of every record an interpretation names."""
    out = set()
    if m.direct is not None:
        out.add(m.direct.id)
    if m.detail is not None:
        out.add(m.detail.entity.id)

    def walk(conditions):
        for c in conditions:
            if isinstance(c, Not):
                walk([c.condition])
            elif isinstance(c, (OnTile, AnyOf)):
                walk(c.conditions)
            elif isinstance(c, Near):
                out.add(c.entity.id)
            elif isinstance(c, LinkTo) and isinstance(c.target, EntityRef):
                out.add(c.target.entity.id)
            elif isinstance(c, LinkTo):
                walk(c.target.where)
    if m.plan is not None:
        walk(m.plan.where)
    return out


# ── compositions ─────────────────────────────────────────────────────────────
def _nouns(vocab, model: str) -> tuple[list[tuple[str, list]], list[tuple[str, list]]]:
    """(type nouns, value nouns) saying a model's records, each with the conditions it sets: its plural
    type words; its value plurals ("hospitals") and value phrases before its plural ("coastal buildings")."""
    many = _plural(model)
    said = {w for w, m in vocab.type_words().items() if m == model}
    types = [(many, [])] + [(w, []) for w in sorted(said) if w != many and any(w == plural(s) for s in said)]
    values = []
    for g in vocab.groups():
        if g.model == model:
            values += [(p, [HasValue(x.field, x.value, x.label) for x in preset])
                       for p, preset in g.forms if p in g.type_forms]
    own = [x for x in vocab.values() if model in x.owners]
    fields = {}
    for x in own:
        fields.setdefault(x.phrase, set()).add(x.field)
    for x in sorted(own, key=lambda x: (x.field, x.label)):
        # a phrase two of its fields hold is "did you mean" by design
        if x.phrase == x.label.lower() and word_like(x.label) and len(fields[x.phrase]) == 1:
            values.append((f"{x.phrase} {many}", [HasValue(x.field, x.value, x.label)]))
    return types, values


def _uses(vocab, tiles) -> dict[tuple[str, str, str, str], list[str]]:
    """{(subject model, far model, link, direction): its forms}, for each link the records hold: every form
    from the record holding it, and from its far end each form ending in "by" ("occupied by")."""
    from .paraphrase import link_targets
    relations = {r.name: r for r in vocab.relations()}
    out = {}
    for (holder, alias), targets in sorted(link_targets(vocab, from_records=tiles is not None).items()):
        r = relations.get(alias)
        if r is None:
            continue
        forms = sorted(f for f in r.forms if f not in r.roles and holder in r.said_as(f).domain
                       and f.split()[0] not in ("which", "who", "what"))
        for far in targets:
            out[(holder, far, alias, "out")] = forms
            back = [f for f in forms if f.endswith(" by")]
            if far != holder and back:
                out[(far, holder, alias, "in")] = back
    return out


def _say(form: str, subject: str, far: str, relative: bool = False) -> str:
    """"<subject> <link> <far>", or with `relative` "<subject> that <link> <far>"."""
    if form.split()[0] in ("are", "were", "is"):
        said = f"{subject} are {form.partition(' ')[2]} {far}"
    else:
        said = _link_question(form, subject, "X")[len("which "):-1].replace("{X}", far)
    return said.replace(subject, f"{subject} that", 1) if relative else said


def _plain(form: str) -> bool:
    """Said without "have <far> as <form>", which nests badly in a chain."""
    return form.split()[-1] in _AT + ("by",) or form in _VERBS or form.split()[0] in ("are", "were", "is")


def _apart(form: str, subject: tuple, far: tuple) -> bool:
    """No word said twice: "architect buildings have makers as architect" can't say which is which."""
    return not set(form.split()) & (set(subject[0].split()) | set(far[0].split()))


def _cycle(*lists) -> list[tuple]:
    """Every item of each list at least once, in step: the i-th tuple takes item i of each, wrapping."""
    if not all(lists):
        return []
    return [tuple(x[i % len(x)] for x in lists) for i in range(max(len(x) for x in lists))]


def compositions(vocab, tiles=None, most: int = COMPOSITIONS) -> list[dict]:
    """Questions combining two or three pieces, each with its plan: every link, value and number field
    in turn before any is asked twice, at most `most`. A text two plans could mean is left out."""
    pools: dict[str, list[list[tuple[str, Plan]]]] = {f: [] for f in FAMILIES}
    nouns = {m: _nouns(vocab, m) for m in vocab.models}
    uses = _uses(vocab, tiles)
    for (subject, far, alias, direction), forms in uses.items():
        (s_types, s_values), (f_types, f_values) = nouns[subject], nouns[far]

        def said(form, s, f):
            return (f"which {_say(form, s[0], f[0])}?",
                    Plan(subject, s[1] + [LinkTo(alias, Plan(far, f[1]), direction)]))
        pools["type + link + type"].append([said(*x) for x in _cycle(forms, s_types, f_types) if _apart(*x)])
        pools["type + link + value"].append([said(*x) for x in _cycle(forms, s_types, f_values) if _apart(*x)]
                                            + [said(*x) for x in _cycle(forms, s_values, f_types) if _apart(*x)])
    for r in vocab.relations():
        for role in sorted(r.roles):
            for holder, ends in sorted(r.ends):
                for far in sorted(ends & set(nouns)):
                    for family, fars in zip(FAMILIES, nouns[far]):
                        pools[family].append([(f"{role} of {f[0]}", Plan(holder, [LinkTo(r.name, Plan(far, f[1]), "out")]))
                                              for f in fars])
    for n in vocab.number_fields():
        for model in sorted(n.owners):
            pools["type + value + number"].append([
                (f"{s[0]} with {form} over {NUMBER}",
                 Plan(model, s[1] + [NumberRange(n.field, NUMBER, None, lo_inclusive=False)]))
                for s, form in _cycle(nouns[model][1], list(n.forms))])
    for (a, b, first, way), forms in uses.items():
        for (b2, c, second, way2), forms2 in uses.items():
            if b2 != b or len({a, b, c}) < 3:      # a link within one model reads either way
                continue
            plan = Plan(a, [LinkTo(first, Plan(b, [LinkTo(second, Plan(c), way2)]), way)])
            plain, plain2 = [f for f in forms if _plain(f)], [f for f in forms2 if _plain(f)]
            pools["two links"].append([
                (f"which {_say(f1, _plural(a), _say(f2, _plural(b), _plural(c), relative=True))}?", plan)
                for f1, f2 in _cycle(plain, plain2)])
    return _take(pools, most)


def _take(pools: dict, most: int) -> list[dict]:
    """Each family's pools in turn, then the families in turn, until `most`; texts with two plans dropped."""
    plans: dict[str, set] = {}
    for lists in pools.values():
        for items in lists:
            for q, plan in items:
                plans.setdefault(q, set()).add(signature(plan))
    rounds = max((len(items) for lists in pools.values() for items in lists), default=0)
    seen, by = set(), {}
    for family, lists in pools.items():
        mine = by.setdefault(family, [])
        for i in range(rounds):
            for items in lists:
                if i < len(items) and items[i][0] not in seen and len(plans[items[i][0]]) == 1:
                    seen.add(items[i][0])
                    mine.append(items[i])
    order = [(family, *xs[i]) for i in range(max(map(len, by.values()), default=0))
             for family, xs in by.items() if i < len(xs)]
    return [{"q": q, "plan": plan, "family": family, "shape": "composition"} for family, q, plan in order[:most]]


# ── name probes ──────────────────────────────────────────────────────────────
def name_probes(vocab, generic: set[str] = frozenset(), most: int = NAMES) -> list[dict]:
    """For up to `most` records whose names have more than one word (numbered or versioned names, then names
    leading with a generic or vocabulary word, then the rest; each model in turn): each part of the name, which must never bind the record, and the
    whole name, which should. A part several names share is one probe, which must bind none of them."""
    said = set(vocab.type_words()) | {x.phrase for x in vocab.values()} | set(generic)
    named = []
    for e in vocab._index.entities:
        words = list(dict.fromkeys(w for w in _WORD.findall(e.name.lower()) if terms(w) or marks(w)))
        if len(words) < 2:
            continue
        rank = 0 if marks(e.name) else 1 if words[0] in said or _plural(words[0]) in said else 2
        named.append((rank, e.type, e.name, e, words))
    # each model's names in turn within a rank, so one model's many numbered names can't fill the cap
    turn, nth = {}, []
    for rank, model, name, e, words in sorted(named, key=lambda x: x[:3]):
        turn[(rank, model)] = turn.get((rank, model), -1) + 1
        nth.append((rank, turn[(rank, model)], name, e, words))
    chosen = [x[3:] for x in sorted(nth, key=lambda x: x[:3])[:most]]
    whole = {e.name.lower() for e, _ in chosen}
    parts: dict[str, dict] = {}
    for e, words in chosen:
        # ponytail: every proper subset only up to WHOLE_WORDS words (2^n); longer names get each word and
        # each name less one word
        sizes = range(1, len(words)) if len(words) <= WHOLE_WORDS else (1, len(words) - 1)
        for k in sizes:
            for part in map(" ".join, combinations(words, k)):
                if part not in whole:
                    probe = parts.setdefault(part, {"q": part, "records": {}, "bind": False, "shape": "name probe"})
                    probe["records"][e.id] = e.name
    return list(parts.values()) + [{"q": e.name, "records": {e.id: e.name}, "bind": True, "shape": "name probe"}
                                   for e, _ in chosen]


# ── the site's own questions ─────────────────────────────────────────────────
def site_questions(path) -> list[dict]:
    """A practice set ({"questions": [...]}, as the testbed or responder sets): each question with its
    expected counts ("accept": [n, …] or "count": n) and whether it should be refused."""
    out = []
    for o in json.loads(Path(path).read_text())["questions"]:
        counts = o.get("accept") or ([o["count"]] if o.get("count") is not None else [])
        refuse = "refuse" in (o.get("expect"), o.get("group"))
        out.append({"q": o["q"], "counts": [] if refuse else counts, "refuse": refuse, "shape": "site question"})
    return out


def score(item: dict, m, tiles=None) -> str:
    """right / refused / wrong reading for a composition; right refusal / wrong for a partial name (wrong:
    it binds the record); right / refused for a whole name; for a site question, right / wrong on its
    expected count, right refusal / wrong when it should be refused, answered / refused with neither."""
    refused = bool(m.refused or m.statement)
    shape = item["shape"]
    if shape == "composition":
        if refused or m.plan is None:
            return "refused"
        return "right" if signature(m.plan) == signature(item["plan"]) else "wrong reading"
    if shape == "name probe":
        hit = not refused and bool(bound(m) & set(item["records"]))
        if item["bind"]:
            return "right" if hit else "refused"
        return "wrong" if hit else "right refusal"
    if item["refuse"]:
        return "right refusal" if refused else "wrong"
    if refused:
        return "refused"
    if not item["counts"]:
        return "answered"
    return "right" if _count(m, tiles) in item["counts"] else "wrong"


def _count(m, tiles) -> int | None:
    """Records found, as `ceist ask` answers: a record question is one, a relaxation counts when it finds any."""
    from .alizarin import evaluate
    if m.direct is not None or m.detail is not None:
        return 1
    if m.plan is None or m.plan.group is not None:
        return None
    for plan, note in [(m.plan, "")] + [(r.plan, r.note) for r in m.relaxations]:
        ids = evaluate(plan, tiles)
        if ids or not note:
            return len(ids)
    return 0

