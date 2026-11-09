"""Passes 12-15: the matcher's second chance at leftover words, each group
phrase's clause, the text filter and coverage."""

from .model import GroupGround, _edge
from .scan import CLAUSE_END, Scan, _leftover_runs


def _match_leftovers(s: Scan, matcher) -> None:
    """The second chance: leftover runs, matched by the configured chain
    against what the structure says they could be."""
    from ..matching import Item
    g = s.g

    def take(run):
        s.consumed.update(w.i for w in run)

    runs = _leftover_runs(s)
    # a date with several possible fields: the run just before it picks one
    for dm in g.dates:
        if len(dm.fields) < 2:
            continue
        run = next((r for r in reversed(runs) if r[-1].i < dm.pos and dm.pos - r[-1].i <= 3), None)
        if run is None:
            continue
        phrase = " ".join(w.text for w in run)
        items = [Item(f.field, tuple(f.forms) or (f.label,), f.label, f) for f in dm.fields]
        res = matcher.resolve(phrase, items)
        g.notes += res.notes
        if res.match:
            dm.fields = [res.match.item.payload]
            take(run)
            runs.remove(run)
        else:
            _offer(g, phrase, res)
            owners = {o for f in dm.fields for o in f.owners}
            model = (next(iter(owners)) if len(owners) == 1 else
                     g.subject.type if g.subject else "")
            _unplaced(g, phrase, "date", model, [(o, o.payload.field, None) for o in res.options])
    # two named things and no relation between them: the run between them
    nodes = sorted(g.nodes, key=lambda n: n.pos)
    if len(nodes) >= 2 and not g.edges:
        a, b = nodes[0], nodes[-1]
        between = [r for r in runs if a.pos < r[0].i < b.pos or a.pos < r[-1].i < b.pos]
        types = {a.type, b.type}
        fits = [r for r in s.relations.values()
                if (not r.domain or r.domain & types) and (not r.range or r.range & types)]
        for run in between[:1]:
            phrase = " ".join(w.text for w in run)
            items = [Item(r.name, tuple(r.forms),
                          (r.path or r.name) + (f" ({r.qualifier[2]})" if r.qualifier else ""), r)
                     for r in fits]
            res = matcher.resolve(phrase, items)
            g.notes += res.notes
            if res.match:
                rel = res.match.item.payload
                g.edges.append(_edge(rel, float(run[0].i), form=phrase))
                take(run)
            else:
                _offer(g, phrase, res)
                domains = {d for r in fits for d in r.domain}
                model = next(iter(domains)) if len(domains) == 1 else a.type
                other = b.type if model == a.type else a.type
                options = []
                for o in res.options:
                    rel = o.payload
                    qualifier = rel.qualifier[1] if rel.qualifier else None
                    options.append((o, rel.path or rel.name, qualifier))
                _unplaced(g, phrase, f"link:{other}", model, options)
    # any other run: the combos of the types named, one item per tile it describes. Not
    # a group's own name: a run near it would be read as naming the group and nothing on it
    named = {n.type for n in g.vars()}
    tiles: dict[tuple, list] = {}
    for grp in s.groups:
        if grp.model in named:
            for phrase, preset in grp.forms:
                if preset:
                    tiles.setdefault((grp, preset), []).append(phrase)
    if not tiles:
        return
    items = [Item((grp.model, grp.name, tuple(v.value for v in preset)), tuple(phrases),
                  f"{phrases[0]} ({grp.name.replace('_', ' ')})", (grp, preset))
             for (grp, preset), phrases in tiles.items()]
    for run in _leftover_runs(s):
        phrase = " ".join(w.text for w in run)
        res = matcher.resolve(phrase, items)
        g.notes += res.notes
        if res.match:
            g.groups.append(GroupGround(phrase, float(run[0].i), [w.i for w in run],
                                        [res.match.item.payload]))
            take(run)
        else:
            _offer(g, phrase, res)


def _offer(g, phrase: str, res) -> None:
    if res.options:
        g.suggestions.append((phrase, [o.label for o in res.options]))


def _unplaced(g, phrase: str, slot: str, model: str, options: list[tuple]) -> None:
    """A phrase the matcher couldn't place, for the learn log; `options` are
    (item, node, qualifier)."""
    g.unplaced.append({"phrase": phrase, "slot": slot, "model": model,
                       "options": [{"node": node, "qualifier": q, "end_node": None,
                                    "label": o.label} for o, node, q in options]})


def _fill_groups(s: Scan) -> None:
    """Each group phrase picks its group among the types named, then takes the
    values (from its group's own nodes) and the date of its clause. Holds back
    from the text filter the words left in a group's clause, and a phrase that
    named a group but nothing on it — a group that doesn't absorb its clause
    refuses rather than drops a word."""
    g, words = s.g, s.words
    named = {n.type for n in g.vars()}
    for gm in list(g.groups):
        cands = [c for c in gm.candidates if not named or c[0].model in named]
        marks = [x.pos for x in (*g.edges, *g.nodes, *g.groups) if x is not gm]
        marks += [i for i, _s, _e, w in words if w in CLAUSE_END]
        start = gm.words[-1]
        stop = min((m for m in marks if m > start), default=len(words))
        if len(cands) == 1:
            grp, preset = cands[0]
            gm.group, gm.values = grp, list(preset)
            for vm in [v for v in g.values if start < v.pos < stop]:
                fit = [v for v in vm.candidates if v.field in grp.fields
                       and (not v.owners or grp.model in v.owners)]
                if len({v.field for v in fit}) == 1:
                    gm.values.append(fit[0])
                    g.values.remove(vm)
            dm = next((d for d in g.dates if start < d.pos < stop
                       and (d.picked is None or d.picked < gm.pos)), None)
            if dm is not None and grp.date is not None:
                gm.date = dm
                g.dates.remove(dm)
        elif len(cands) > 1:
            g.suggestions.append((gm.phrase, [f"{grp.model} {grp.name.replace('_', ' ')}"
                                              for grp, _ in cands]))
        s.held.update(i for i in range(start + 1, int(stop)) if i not in s.consumed)
        if gm.group is None or not (gm.values or gm.date):
            g.groups.remove(gm)
            s.consumed.difference_update(gm.words)
            s.held.update(gm.words)
            continue
        g.notes.append(f"'{gm.phrase}' → one {gm.group.name} entry of {gm.group.model}: "
                       + ", ".join([f"{v.field} = {v.label}" for v in gm.values]
                                   + ([f"{gm.group.date.label} {gm.date.phrase}"] if gm.date else [])))


def _text_filter(s: Scan) -> None:
    """One leftover word → a text filter, where the vocabulary has free text; else uncovered."""
    remaining = [(i, w) for i, _s, _e, w in s.words if i not in s.consumed and s.parts_of(w)]
    if s.free_text and len(remaining) == 1 and remaining[0][0] not in s.held:
        i, w = remaining[0]
        s.contains_pos = float(i)
        s.g.contains = sorted(s.parts_of(w))[0]
        s.consumed.add(i)
        s.g.notes.append(f"'{w}' → text filter")


def _coverage(s: Scan) -> None:
    covered = set().union(set(), *(s.parts_of(w) for i, _s, _e, w in s.words if i in s.consumed))
    s.g.coverage = len(covered & s.terms) / len(s.terms) if s.terms else 0.0
    s.g.uncovered = sorted(s.terms - covered)
