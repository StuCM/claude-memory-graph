"""Passes 8-11: type words, named records, the relation each phrase means, and
a type the values imply."""

from ..text import terms_pos
from ..vocabulary import Relation
from .model import Node, _edge
from .scan import (
    _SUBJECT_LEAD,
    AUX,
    DATE_WORDS,
    FILLER,
    MAX_ANCHORS,
    NEG,
    RECENT,
    Scan,
    _inside,
    _phrase_spans,
)


def _words(s: Scan) -> None:
    """Type nouns, modifiers, negators and hints; then the type the question word implies."""
    g, nouns, hints = s.g, s.type_words, s.vocab.hint_words()
    # multi-word type names first ("insurance policies", "hazard footprint")
    multi = [(w, t) for w, t in nouns.items() if " " in w]
    for phrase, t, m in _phrase_spans(s.raw, multi, s.taken):
        pos = s.consume_span(m.start(), m.end())
        if t not in s.seen:
            s.add_var(t, pos, f"'{phrase}'")
    for i, _s, _e, w in s.words:
        if i in s.consumed:
            continue
        if w in nouns:
            if nouns[w] not in s.seen:
                s.add_var(nouns[w], float(i), f"'{w}'")
            s.consumed.add(i)
        elif w in NEG:
            s.negs.append((i, w))
            s.consumed.add(i)
        elif w in RECENT:
            g.recent = True
            s.consumed.add(i)
            g.notes.append(f"'{w}' → most recent first")
        elif w in hints:
            s.consumed.add(i)
            if hints[w] not in s.seen:
                s.add_var(hints[w], float(i), f"'{w}' implies")
        elif w in AUX or w in FILLER or (g.dates and w in DATE_WORDS):
            s.consumed.add(i)
    implied = s.vocab.implied_types()
    if g.wh in implied and implied[g.wh] not in s.seen:
        s.add_var(implied[g.wh], 0.0, f"'{g.wh}' implies")


def _anchors(s: Scan) -> None:
    """Leftover terms against the records: only a whole name (or alias) may
    bind, never a guess. Up to two ("designed by Ada on site Salts Mill")."""
    g = s.g
    if s.any_of:
        _either_records(s)
    partial = getattr(s.vocab, "partial_names", False)
    expected = {t for e in g.edges for r in s.sharing.get(e.form, [e.relation]) if r in s.relations
                for t in s.types_of(e.form, r)}
    for _ in range(MAX_ANCHORS):
        leftovers = [(i, w) for i, _s, _e, w in s.words if i not in s.consumed and s.parts_of(w)]
        if not leftovers:
            break
        left = set().union(*(s.parts_of(w) for _i, w in leftovers))
        ranked = [(sc, e) for sc, e in s.vocab.rank_entities(left)
                  if partial or e.named_by(left)]
        if not ranked:
            break
        score, top = ranked[0]
        # a record NAMED exactly what was asked beats one that mentions it
        exact = next((e for sc, e in ranked[1:]
                      if sc > 0 and e.name_terms == left and top.name_terms != left), None)
        if exact is not None:
            g.notes.append(f"anchor exact name: {exact.type} '{exact.name}' "
                           f"preferred over {top.type} '{top.name}'")
            score, top = next(sc for sc, e in ranked if e is exact), exact
        # role fit: the grounded relations say what TYPE an anchor should be;
        # a near-tied candidate of that type beats a lexical tie
        if expected and top.type not in expected:
            for sc, e in ranked[1:]:
                if sc >= 0.75 * score and e.type in expected and left & e.name_terms:
                    g.notes.append(f"anchor role fit: {e.type} '{e.name}' "
                                   f"preferred over {top.type} '{top.name}'")
                    score, top = sc, e
                    break
        if not (score > 0 and left & top.name_terms):
            break
        hit = left & top.terms
        pos = min(i for i, w in leftovers if s.parts_of(w) & hit)
        node = Node("anchor", top.type, float(pos), entity=top,
                    match_terms=sorted(left & top.name_terms))
        g.anchors.append(node)
        g.nodes.append(node)
        s.consumed.update(i for i, w in leftovers if s.parts_of(w) <= hit)
        g.notes.append(f"{'/'.join(node.match_terms)} → anchor "
                       f"{top.type or 'Concept'} '{top.name}'")
        if len(g.anchors) >= len(g.edges) + (g.near is not None):
            break                     # one anchor per relation (or "near") at most
    if g.near is not None:
        # the record measured from: not a node any relation joins
        after = [a for a in g.anchors if a.pos > g.near.pos]
        if after:
            a = min(after, key=lambda n: n.pos)
            g.near.entity = a.entity
            g.anchors = [n for n in g.anchors if n is not a]
            g.nodes = [n for n in g.nodes if n is not a]
            g.notes.append(f"'{g.near.phrase}' → within {g.near.km:g} km of {a.type} '{a.name}'")


def _either_records(s: Scan) -> None:
    """"County Antrim or County Down": a whole name either side of "or", both of
    one type, is one anchor that may be either record."""
    g, words, names = s.g, s.words, s.names
    for i, ws, we, w in words:
        if (w != "or" or i in s.consumed or not 0 < i < len(words) - 1
                or _inside(ws, we, names)):
            continue
        before = [st for st, e in names if e == words[i - 1].end]
        after = [e for st, e in names if st == words[i + 1].start]
        if not before or not after:
            continue
        found = []
        for st, e in ((min(before), words[i - 1].end), (words[i + 1].start, max(after))):
            at = s.words_in(st, e)
            left = set().union(*(s.parts_of(words[j].text) for j in at))
            named = [x for _score, x in s.vocab.rank_entities(left) if x.named_by(left)]
            exact = [x for x in named if x.name_terms == left]
            found.append(((exact or named or [None])[0], at))
        (a, at_a), (b, at_b) = found
        if a is None or b is None or a.type != b.type:
            continue
        node = Node("anchor", a.type, float(at_a[0]), entity=a, either=[b],
                    match_terms=sorted(a.name_terms))
        g.anchors.append(node)
        g.nodes.append(node)
        s.consumed.update(at_a + at_b + [i])
        g.notes.append(f"'{words[at_a[0]].text} … {words[at_b[-1]].text}' → anchor "
                       f"{a.type} '{a.name}' or '{b.name}'")


def _fit_relations(s: Scan) -> None:
    """A phrase binds only a relation that can join two of the things named. A
    shared phrase ("in": a tale's parent story, a monument's named location)
    takes the one of its relations that can; when none can, or a bare
    function word ("at") names one that can't, it is set aside, so the anchor
    is linked loosely as if no phrase were there. The word stays consumed: it
    was understood, as "at" is. A phrase with a content word naming one
    relation is specific ("architect"): it keeps it when it can join two
    things named (a type it implies but nobody named refuses later, in
    plan.py), and refuses when it can't. So does one naming several relations, none of
    which can ("part of"), unless the vocabulary has free text and says what it set aside."""
    g, relations, sharing = s.g, s.relations, s.sharing
    if len(g.nodes) < 2:
        return
    used = {e.relation for e in g.edges}

    def fits(r: Relation) -> bool:
        return any(r.joins(a.type, b.type) for a in g.nodes for b in g.nodes if a is not b)

    for edge in list(g.edges):
        if fits(relations[edge.relation]):
            continue
        types = " and ".join(sorted({n.type for n in g.nodes}))
        if len(sharing.get(edge.form, [])) < 2 and terms_pos(edge.form):
            g.refuse = f"'{edge.form}' ({edge.relation}) can't join {types}"
            return
        pick = next((r for r in sharing.get(edge.form, [])
                     if r not in used and fits(relations[r].said_as(edge.form))), None)
        if pick is None:
            # "which monuments are in Belfast", with Belfast a Monument: set aside,
            # the anchor would be answered as itself, ignoring what "in" asked for
            same = next((a for a in g.anchors for v in g.vars() if a.type == v.type), None)
            if same is not None:
                g.refuse = _wrong_end(same, edge.form, {
                    t for r in sharing.get(edge.form, [edge.relation])
                    for t in relations[r].targets()})
                return
            if terms_pos(edge.form) and not s.free_text:
                g.refuse = f"'{edge.form}' can't join {types}"
                return
            g.edges.remove(edge)
            g.notes.append(f"'{edge.form}' set aside: no relation it names joins {types}")
            continue
        used.add(pick)
        relations[pick] = relations[pick].said_as(edge.form)
        g.edges[g.edges.index(edge)] = _edge(relations[pick], edge.pos, form=edge.form)
        g.notes.append(f"'{edge.form}' → relation {pick} instead: it joins {types}")


def _wrong_end(anchor: Node, form: str, targets: set[str]) -> str:
    what = f"a {' or '.join(sorted(targets))}, which" if targets else "a record"
    return f"{anchor.type} '{anchor.name}' isn't {what} '{form}' points at"


def _imply_model(s: Scan) -> None:
    """No type named ("how many raths are there?"): values that only one model
    holds name it. Values two models hold refuse with "did you mean" each."""
    g = s.g
    if g.nodes or g.edges or s.about:
        return
    named = [(v.phrase, v.pos, {o for c in v.candidates for o in c.owners},
              all(c.owners for c in v.candidates)) for v in g.values]
    named += [(gm.phrase, gm.pos, {grp.model for grp, _ in gm.candidates}, True)
              for gm in g.groups]
    if not named or not all(known for *_, known in named):
        return
    first = min(named, key=lambda x: x[1])
    # "what's the brooch made of?" asks about one brooch, not which brooches
    if not (g.group_order or _SUBJECT_LEAD.search(s.raw[:s.words[int(first[1])].start])):
        return
    models = set().union(*(owners for _p, _pos, owners, _k in named))
    if len(models) == 1:
        s.add_var(models.pop(), first[1], f"'{first[0]}' implies")
    else:
        g.suggestions.append(("', '".join(p for p, *_ in named), sorted(models)))
