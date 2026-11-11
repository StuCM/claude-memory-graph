"""Passes 1-9: the question's shape, then the phrases it says: relations, tile
phrases, values, field phrases, "near", dates and numbers."""

import re
from typing import NamedTuple

from .. import dates, numbers
from ..text import ALNUM, overlaps, terms
from .model import (
    DateGround,
    GroupGround,
    NameGround,
    NearGround,
    NumberGround,
    ValueMatch,
    _edge,
)
from .scan import (
    _LEAD_WORDS,
    _SUBJECT_LEAD,
    ABOUT_RE,
    AUX,
    IMPERATIVE,
    MILE_KM,
    MOST,
    NAME_RES,
    NEAR_KM,
    NEAR_RE,
    WH,
    WORD_RE,
    Scan,
    _opens,
    _phrase_spans,
)


def _shape(s: Scan) -> None:
    g, words = s.g, s.words
    if words and _opens(words[0].text):
        if words[0].text in WH:
            g.wh = words[0].text
        elif words[0].text in IMPERATIVE:
            g.wh = "what"                 # "list decisions" = "what decisions"
            s.taken.append((words[0].start, words[0].end))   # "Find people…": not the value Find
        s.consumed.add(0)
    if len(words) > 1 and words[0].text == "how" and words[1].text in ("many", "much"):
        g.count, g.wh = True, "what"      # not "how" → its implied type
        s.consumed.add(1)
        g.notes.append("'how many' → count")
    about = ABOUT_RE.match(s.text)
    if about:
        s.about = True
        s.consumed.update(w.i for w in words if w.start < about.end())
        g.notes.append("'… about X' → X itself")
    if getattr(s.vocab, "name_match", False) and not about:
        _name_match(s)


def _name_match(s: Scan) -> None:
    """"whose name starts with Cat", "fort in the name", "called Lismahon": one
    word matched against record names, its words consumed so nothing else grounds them."""
    for mode, rx in NAME_RES:
        m = rx.search(s.raw)
        if m is None:
            continue
        term = s.text[m.start(2):m.end(2)]
        s.g.name = NameGround(term, mode, s.consume_span(m.start(), m.end()))
        s.taken.append((m.start(), m.end()))
        s.g.notes.append(f"'{m.group()}' → name {'starts with' if mode == 'prefix' else 'has the word'}"
                         f" '{term}'")
        return


def _relations(s: Scan) -> None:
    g, raw = s.g, s.raw
    # a longer group or value phrase wins over a relation phrase inside it:
    # "bronze age" is a period, not 'age' (cultural_period) and a stray "bronze"
    shape = s.taken + [(w.start, w.end) for w in s.words if w.i in s.consumed]
    longer = [(m.start(), m.end()) for p in (*s.group_forms, *s.value_forms) if p in raw
              for m in re.finditer(rf"(?<!{ALNUM}){re.escape(p)}(?!{ALNUM})", raw)
              if not overlaps(m.start(), m.end(), shape)]
    s.relations = {r.name: r for r in s.vocab.relations()}
    matched: set[str] = set()
    # A phrasing that is just a type's name ("monuments", for a link called
    # "associated monuments") is the type where the question names its
    # subject — "which monuments …", "how many sites …" — not the relation:
    # taking it would leave the question with no subject. Elsewhere ("on site
    # Leeds Dock") it stays the relation.
    def just_a_type(form: str) -> bool:
        words = form.split()
        while words and words[0] in _LEAD_WORDS:
            words = words[1:]
        return " ".join(words) in s.type_words

    # a phrasing two relations share ("part of": a tale's parent story, a
    # group's parent organisation) goes to one that joins the types the question names
    named = {t for w, t in s.type_words.items()
             if w in raw and re.search(rf"(?<!{ALNUM}){re.escape(w)}(?!{ALNUM})", raw)}
    forms = sorted(((f, r.name) for r in s.relations.values() for f in r.forms),
                   key=lambda x: not s.types_of(*x) & named)
    for form, rel, m in ([] if s.about else _phrase_spans(raw, forms, s.taken, s.names + longer)):
        subject = just_a_type(form) and (form.split()[0] in _LEAD_WORDS
                                         or _SUBJECT_LEAD.search(raw[:m.start()]))
        if subject or rel in matched:
            s.taken.remove((m.start(), m.end()))
            continue
        matched.add(rel)
        s.relations[rel] = s.relations[rel].said_as(form)
        g.edges.append(_edge(s.relations[rel], s.consume_span(m.start(), m.end()), form=form))
        g.notes.append(f"'{form}' → relation {rel}")
        holders = sorted(s.relations[rel].domain)
        if form in s.relations[rel].roles and len(holders) == 1 and holders[0] not in s.seen:
            s.add_var(holders[0], g.edges[-1].pos, f"'{form}' names the holder of {rel}")
        s.sharing[form] = [r for f, r in forms if f == form]
    g.edges.sort(key=lambda e: e.pos)


def _group_by(s: Scan) -> None:
    """"… by county" ending the question, or "which county has the most …":
    the link names what to count per record of, not a condition."""
    g = s.g
    if not getattr(s.vocab, "group_by", False):
        return
    w = [x.text for x in s.words]
    for e in g.edges:
        if e.qualifier:
            continue
        start = int(e.pos)
        end = start + len(WORD_RE.findall(e.form)) - 1
        took, order = [], ""
        if start and w[start - 1] == "by" and end == len(w) - 1:
            took = [start - 1]
        elif start == 1 and w[0] in ("which", "what") and w[end + 1:end + 2] in (["has"], ["have"]):
            k = end + 2 + (w[end + 2:end + 3] == ["the"])
            if k < len(w) and w[k] in MOST:
                took, order = list(range(end + 1, k + 1)), MOST[w[k]]
        if took:
            s.consumed.update(took)
            g.edges.remove(e)
            g.group, g.group_order = e, order
            g.notes.append(f"'{e.form}' → count per {e.relation}"
                           + (f", the {order}" if order else ""))
            return


def _tile_phrases(s: Scan) -> None:
    """Group phrases ("burnt down"): filled from their clause by _fill_groups."""
    for phrase, cands, m in _phrase_spans(s.raw, list(s.group_forms.items()), s.taken, s.names):
        at = s.words_in(m.start(), m.end())
        if s.consumed & set(at):                        # "how many": the question's shape
            s.taken.remove((m.start(), m.end()))
            continue
        s.g.groups.append(GroupGround(phrase, s.consume_span(m.start(), m.end()), at, cands))


def _values(s: Scan) -> None:
    """Controlled values ("listed", "active")."""
    for phrase, cands, m in _phrase_spans(s.raw, list(s.value_forms.items()), s.taken, s.names):
        at = s.words_in(m.start(), m.end())
        s.g.values.append(ValueMatch(phrase, s.consume_span(m.start(), m.end()), cands, words=at))
        s.g.notes.append(f"'{phrase}' → value of "
                         + " / ".join(sorted({c.field for c in cands})))


def _field_phrases(s: Scan) -> None:
    """A phrase naming a controlled field ("made of", "monument type") holds the value
    that follows it to that field, else the value just before it ("health sector"). With
    neither, it places nothing."""
    g = s.g
    by_phrase: dict[str, set] = {}
    for phrase, model, alias in getattr(s.vocab, "field_phrases", lambda: [])():
        by_phrase.setdefault(phrase, set()).add((model, alias))
    for phrase, owners, m in _phrase_spans(s.raw, list(by_phrase.items()), list(s.taken), s.names):
        at = s.words_in(m.start(), m.end())
        if not at:       # inside a hyphenated word ("sub-status"): no word of its own
            continue
        after = min((v for v in g.values if v.pos > at[-1]), key=lambda v: v.pos, default=None)
        before = max((v for v in g.values if v.words and v.words[-1] < at[0]), key=lambda v: v.pos, default=None)
        sides = [(after, at[-1], after.pos if after else 0), (before, before.words[-1] if before else 0, at[0])]
        for vm, lo, hi in sides:
            if vm is None or any(s.parts_of(w) for i, _s, _e, w in s.words if lo < i < hi):
                continue
            fit = [v for v in vm.candidates if any(v.field == a and (not v.owners or t in v.owners)
                                                   for t, a in owners)]
            if fit:
                break
        else:
            continue
        vm.candidates = fit
        s.taken.append((m.start(), m.end()))
        s.consume_span(m.start(), m.end())
        g.notes.append(f"'{phrase}' → field {' / '.join(sorted({v.field for v in fit}))} of '{vm.phrase}'")


def _near(s: Scan) -> None:
    """"near X", "within 5 km of X": where the vocabulary has locations."""
    if not getattr(s.vocab, "geometry_fields", None):
        return
    m = next((m for m in NEAR_RE.finditer(s.raw)
              if not overlaps(m.start(), m.end(), s.taken + s.names)), None)
    if m:
        s.taken.append((m.start(), m.end()))
        miles = bool(m[2]) and m[2].startswith("mile")
        km = float(m[1]) * (MILE_KM if miles else 1) if m[1] else NEAR_KM
        s.g.near = NearGround(m[0], s.consume_span(m.start(), m.end()), km,
                              "miles" if miles else "km")


def _dates(s: Scan, today) -> None:
    """"built before 1900": only when the vocabulary has date fields."""
    g = s.g
    date_fields = list(getattr(s.vocab, "date_fields", lambda: [])())
    if not date_fields:
        return
    blocked = list(s.taken)
    if getattr(s.vocab, "number_fields", lambda: [])():
        blocked += numbers.not_dates(s.raw, s.taken)     # "capacity over 1500" is no year
    found = dates.find(s.raw, blocked, today)
    if not found:
        return
    s.taken += [(d.start, d.end) for d in found]
    picks = []
    # a word can pick a date field on several types ("built": a
    # monument's construction, an aircraft's start date); keep them
    # all, and the subject's type chooses (plan._attach_dates)
    date_forms: dict[str, list] = {}
    for df in date_fields:
        for f in df.forms:
            date_forms.setdefault(f, []).append(df)
    for form, dfs, m in _phrase_spans(s.raw, list(date_forms.items()), s.taken):
        picks.append((s.consume_span(m.start(), m.end()), dfs, form))
    for dm in found:
        pos = s.consume_span(dm.start, dm.end)
        # the field word nearest before the date, else after it
        before = [x for x in picks if x[0] < pos]
        pick = (max(before, key=lambda x: x[0]) if before
                else min(picks, key=lambda x: x[0]) if picks else None)
        fields = list(pick[1]) if pick else date_fields
        g.dates.append(DateGround(dm.phrase, pos, dm.lo, dm.hi, fields,
                                  picked=pick[0] if pick else None))
        g.notes.append(f"'{dm.phrase}' → date {dates.label(dm.lo, dm.hi)}"
                       + (f" ('{pick[2]}' → "
                          f"{' / '.join(sorted({d.label for d in pick[1]}))})"
                          if pick else ""))



def _numbers(s: Scan) -> None:
    """"capacity over 200", "taller than 30 metres": only when the vocabulary has number
    fields. Each comparison takes the field its unit or cue says ("30 metres", "room
    for"), with the field word just before it; else the nearest field word before it,
    else after it; else every number field, and the subject's type chooses."""
    fields = list(getattr(s.vocab, "number_fields", lambda: [])())
    if not fields:
        return
    found = [m for m in numbers.find(s.raw, s.taken + s.names) if not _counts_records(s, m)]
    if not found:
        return
    forms: dict[str, list] = {}
    for f in fields:
        for form in f.forms:
            forms.setdefault(form, []).append(f)
    spans = s.taken + [(m.start, m.end) for m in found]
    named = [FieldWord(s.words_in(m.start(), m.end()), fs, m)
             for _form, fs, m in _phrase_spans(s.raw, list(forms.items()), list(spans), s.names)]
    for nm in found:
        at = s.words_in(nm.start, nm.end)
        pos = s.consume_span(nm.start, nm.end)
        s.taken.append((nm.start, nm.end))
        pick = _field_word(s, named, at[0], at[-1], adjacent=bool(nm.unit or nm.cue))
        if pick is not None:
            s.taken.append((pick.match.start(), pick.match.end()))
            s.consume_span(pick.match.start(), pick.match.end())
        fits, clash = _number_fields(nm, pick.fields if pick else fields, picked=pick is not None)
        s.g.numbers.append(NumberGround(nm.phrase, pos, nm.lo, nm.hi, nm.lo_inclusive,
                                        nm.hi_inclusive, nm.unit, fits, clash))
        s.g.notes.append(f"'{nm.phrase}' → number "
                         f"{numbers.label(nm.lo, nm.hi, nm.lo_inclusive, nm.hi_inclusive)}"
                         + (f" ('{pick.match.group()}' → "
                            f"{' / '.join(sorted({f.label for f in pick.fields}))})" if pick else ""))


def _counts_records(s: Scan, nm) -> bool:
    """"more than 3 figures" counts linked records, which no number field holds."""
    after = [w for w in s.words if w.start >= nm.end][:2]
    if not after:
        return False
    valued = {i for v in s.g.values for i in v.words}
    return (after[0].text in s.type_words or " ".join(w.text for w in after) in s.type_words
            or after[0].i in valued)


class FieldWord(NamedTuple):
    words: list[int]
    fields: list
    match: re.Match


def _field_word(s: Scan, named: list[FieldWord], first: int, last: int,
                adjacent: bool) -> FieldWord | None:
    """The field word nearest before the comparison, else after it. With a unit or cue
    of its own, only one just before it counts: "height over 30 metres", "an insured value of
    at least 1 crore"."""
    near = max((x for x in named if x.words[-1] < first), key=lambda x: x.words[-1], default=None)
    if adjacent:
        between = range(near.words[-1] + 1, first) if near else ()
        return near if near and all(s.words[i].text in AUX | {"a", "an", "the", "of"}
                                    for i in between) else None
    return near or min((x for x in named if x.words[0] > last), key=lambda x: x.words[0],
                       default=None)


def _number_fields(nm, candidates: list, picked: bool) -> tuple[list, str]:
    """The candidates the comparison's unit and cue fit, or why none does. A picked field
    word stands even against the unit: plan._attach_numbers refuses that, saying why."""
    said = numbers.kind(nm.unit)
    if isinstance(nm.cue, str) and said and nm.cue != said:
        return [], f"'{nm.phrase}' says both {numbers.KINDS[nm.cue]} and {numbers.KINDS[said]}"

    def fits(f) -> bool:
        if said and not picked and numbers.kind(f.unit) != said:
            return False
        if isinstance(nm.cue, str):
            return numbers.kind(f.unit) == nm.cue
        if nm.cue:
            return bool(nm.cue & {*terms(f.label), *f.field.split("_")})
        return True

    out = [f for f in candidates if fits(f)]
    if out:
        return out, ""
    what = (numbers.KINDS[nm.cue] if isinstance(nm.cue, str) else
            f"a {' or '.join(sorted(nm.cue))}" if nm.cue else numbers.KINDS[said])
    if picked:
        return [], (f"'{nm.phrase}' is {what}, and the "
                    f"{' or the '.join(sorted({f.label for f in candidates}))} isn't")
    return [], f"'{nm.phrase}' is {what}, and no number field holds one"
