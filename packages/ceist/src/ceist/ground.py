"""Grounding: which words of a question name which parts of the vocabulary.

Pipeline: shape → relations (longest phrase first, on the raw text, so
"works on" keeps its stopword) → controlled values ("listed", "active") →
dates ("before 1900", with the word that picks the field: "built") → type
nouns, modifiers, negators and hints → implied types (who → Person) → up to
two named anchors (only a name-term hit may bind; never a guess) → one
leftover word as a text filter → coverage → wire the relations to their ends
→ scope each negator ("not", "without", "non-") to the next thing named.

With a matcher (ceist.matching.Chain), words the exact pass left over get a
second chance before they become a text filter: a run of leftover words
between two named things is matched against the relations that can join
them, and one before a date against the date fields it could be. A
confident match grounds like an exact one (the note says which layer
decided); otherwise the closest items become suggestions ("did you mean …").

The result says what was understood and how sure (coverage); plan.py turns
it into a query plan, and refuses rather than guesses when it is thin.
"""

import re
from dataclasses import dataclass, field

from . import dates as _dates
from .text import terms_pos
from .vocabulary import DateField, Entity, Relation, Value, Vocabulary

WH = {"what", "which", "who", "whom", "whose", "why", "when", "how", "where"}
AUX = {"is", "are", "was", "were", "do", "does", "did", "has", "have", "had",
       "can", "could", "should", "would", "any"}
RECENT = {"recent", "recently", "latest", "newest"}
# commands that ask a question: "list all decisions", "show me patterns"
IMPERATIVE = {"list", "show", "find", "give", "tell", "name"}
# words that shape a question but name nothing: never a text filter
FILLER = {"me", "all", "every", "please", "made", "make", "been", "exist", "exists",
          "there", "we", "us", "our", "i", "you", "about", "ever", "currently", "have",
          "got", "keep", "kept"}
# "what do we know about X", "tell me about X": the answer is X itself, and the
# verb ("know") must not ground as a relation
ABOUT_RE = re.compile(r"^\s*(?:what\s+(?:do|does|did)\s+(?:we|i|you)\s+(?:know|have|remember)"
                      r"|tell\s+me|what(?:'s| is)\s+(?:known|there))\s+about\s+", re.I)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")
NEG = {"not", "no", "without", "never", "non", "isn't", "aren't", "wasn't", "weren't",
       "don't", "doesn't", "didn't", "hasn't", "haven't", "hadn't", "lacking"}
DATE_WORDS = {"date", "dated", "dates", "dating"}   # shape, once a date is grounded
NEG_REACH = 4             # a negator scopes over the next thing named within this many words
MAX_EDGES = 2
MAX_VARS = 2
MAX_ANCHORS = 2


@dataclass
class Node:
    kind: str                 # "var" | "anchor"
    type: str
    pos: float                # word index, for word-order rules
    var: str = ""             # variable name (vars)
    entity: Entity | None = None
    match_terms: list[str] = field(default_factory=list)

    # conveniences for backends that address anchors directly
    @property
    def name(self) -> str:
        return self.entity.name if self.entity else ""

    @property
    def id(self) -> str:
        return self.entity.id if self.entity else ""


@dataclass
class Edge:
    relation: str
    pos: float
    form: str = ""            # the phrase that grounded it
    source: Node | None = None
    target: Node | None = None
    negated: bool = False
    style: str = "verb"


@dataclass
class ValueMatch:
    phrase: str
    pos: float
    candidates: list[Value]   # every field this phrase can be a value of
    negated: bool = False


@dataclass
class DateGround:
    phrase: str
    pos: float
    lo: str | None
    hi: str | None
    fields: list[DateField]   # the field the words picked, else every candidate
    negated: bool = False


@dataclass
class Grounding:
    text: str = ""
    wh: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    values: list[ValueMatch] = field(default_factory=list)
    dates: list[DateGround] = field(default_factory=list)
    recent: bool = False
    contains: str | None = None
    contains_negated: bool = False
    negation_unplaced: str = ""   # a negator with nothing after it to negate
    subject: Node | None = None
    anchor: Node | None = None            # the first named record
    anchors: list[Node] = field(default_factory=list)
    coverage: float = 0.0
    uncovered: list[str] = field(default_factory=list)
    refuse: str = ""          # out-of-grammar reason
    count: bool = False       # "how many …"
    loose: str = ""           # relation phrases dropped to list a type
    about: bool = False       # "what do we know about X"
    notes: list[str] = field(default_factory=list)
    suggestions: list[tuple[str, list[str]]] = field(default_factory=list)   # (words, did-you-mean)

    def vars(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "var"]


def is_question(text: str) -> bool:
    stripped = text.strip()
    words = WORD_RE.findall(stripped.lower())
    return bool(stripped.endswith("?")
                or (words and (words[0] in WH or words[0] in AUX or words[0] in IMPERATIVE)))


def _phrase_spans(raw: str, phrases: list[tuple[str, object]], taken: list[tuple[int, int]]):
    """Longest phrase first; each match must not overlap an earlier one."""
    for phrase, payload in sorted(phrases, key=lambda x: -len(x[0])):
        m = re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", raw)
        if not m or any(m.start() < e and m.end() > s for s, e in taken):
            continue
        taken.append((m.start(), m.end()))
        yield phrase, payload, m


PREPS = {"by", "on", "in", "at", "to", "from", "with", "for", "of", "into", "under", "up",
         "down", "out", "off", "over", "about"}


def _leftover_runs(words, consumed, parts_of):
    """Maximal runs of unconsumed words, trimmed to start at a meaningful word
    and end at one or at a preposition ("put up", "designed by")."""
    runs, cur = [], []
    for w in words:
        if w[0] in consumed:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(w)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        while r and not parts_of(r[0][3]):
            r = r[1:]
        while r and not parts_of(r[-1][3]) and r[-1][3] not in PREPS:
            r = r[:-1]
        if r:
            out.append(r)
    return out


def ground(vocab: Vocabulary, text: str, today=None, matcher=None) -> Grounding:
    g = Grounding(text=text)
    # same length, so spans stay aligned: "non-listed" → "non listed"
    raw = text.lower().replace("\u2019", "'").replace("non-", "non ")
    words = [(i, m.start(), m.end(), m.group())
             for i, m in enumerate(WORD_RE.finditer(raw))]
    terms = {w for _, w in terms_pos(text)}
    consumed: set[int] = set()

    def parts_of(word: str) -> set[str]:
        # raw words like "memory-graph" must meet terms ("memory", "graph")
        return {p for p in re.split(r"[^a-z0-9]+", word) if p} & terms

    def consume_span(start: int, end: int) -> float:
        first = None
        for i, s, e, _w in words:
            if s >= start and e <= end:
                consumed.add(i)
                first = i if first is None else first
        return float(first if first is not None else 0)

    if words and (words[0][3] in WH or words[0][3] in AUX or words[0][3] in IMPERATIVE):
        if words[0][3] in WH:
            g.wh = words[0][3]
        elif words[0][3] in IMPERATIVE:
            g.wh = "what"                 # "list decisions" = "what decisions"
        consumed.add(0)
    if len(words) > 1 and words[0][3] == "how" and words[1][3] in ("many", "much"):
        g.count, g.wh = True, "what"      # not "how" → its implied type
        consumed.add(1)
        g.notes.append("'how many' → count")
    about = ABOUT_RE.match(text)
    if about:
        g.about = True
        consumed.update(i for i, s, _e, _w in words if s < about.end())
        g.notes.append("'… about X' → X itself")

    # ── relations
    relations = {r.name: r for r in vocab.relations()}
    taken: list[tuple[int, int]] = []
    matched: set[str] = set()
    forms = [(f, r.name) for r in relations.values() for f in r.forms]
    for form, rel, m in ([] if g.about else _phrase_spans(raw, forms, taken)):
        if rel in matched:
            taken.remove((m.start(), m.end()))
            continue
        matched.add(rel)
        g.edges.append(Edge(rel, consume_span(m.start(), m.end()), form=form,
                            style=relations[rel].style))
        g.notes.append(f"'{form}' → relation {rel}")
    g.edges.sort(key=lambda e: e.pos)

    # ── controlled values ("listed", "active")
    by_phrase: dict[str, list[Value]] = {}
    for v in vocab.values():
        by_phrase.setdefault(v.phrase, []).append(v)
    for phrase, cands, m in _phrase_spans(raw, list(by_phrase.items()), taken):
        g.values.append(ValueMatch(phrase, consume_span(m.start(), m.end()), cands))
        g.notes.append(f"'{phrase}' → value of "
                       + " / ".join(sorted({c.field for c in cands})))

    # ── dates ("built before 1900"): only when the vocabulary has date fields
    date_fields = list(getattr(vocab, "date_fields", lambda: [])())
    if date_fields:
        found = _dates.find(raw, taken, today)
        if found:
            picks = []
            forms = [(f, df) for df in date_fields for f in df.forms]
            for form, df, m in _phrase_spans(raw, forms, taken):
                picks.append((consume_span(m.start(), m.end()), df, form))
            for dm in found:
                pos = consume_span(dm.start, dm.end)
                # the field word nearest before the date, else after it
                before = [x for x in picks if x[0] < pos]
                pick = (max(before, key=lambda x: x[0]) if before
                        else min(picks, key=lambda x: x[0]) if picks else None)
                fields = [pick[1]] if pick else date_fields
                g.dates.append(DateGround(dm.phrase, pos, dm.lo, dm.hi, fields))
                g.notes.append(f"'{dm.phrase}' → date {_dates.label(dm.lo, dm.hi)}"
                               + (f" ('{pick[2]}' → {pick[1].label})" if pick else ""))

    # ── type nouns, modifiers, negators, hints
    nouns, hints = vocab.type_words(), vocab.hint_words()
    negs: list[tuple[int, str]] = []
    seen: dict[str, Node] = {}

    def add_var(t: str, pos: float, why: str) -> Node:
        node = Node("var", t, pos, var=f"?v{len(seen)}")
        seen[t] = node
        g.nodes.append(node)
        g.notes.append(f"{why} → typed variable {node.var} : {t}")
        return node

    # multi-word type names first ("insurance policies", "hazard footprint")
    multi = [(w, t) for w, t in nouns.items() if " " in w]
    for phrase, t, m in _phrase_spans(raw, multi, taken):
        pos = consume_span(m.start(), m.end())
        if t not in seen:
            add_var(t, pos, f"'{phrase}'")

    for i, _s, _e, w in words:
        if i in consumed:
            continue
        if w in nouns:
            if nouns[w] not in seen:
                add_var(nouns[w], float(i), f"'{w}'")
            consumed.add(i)
        elif w in NEG:
            negs.append((i, w))
            consumed.add(i)
        elif w in RECENT:
            g.recent = True
            consumed.add(i)
            g.notes.append(f"'{w}' → most recent first")
        elif w in hints:
            consumed.add(i)
            if hints[w] not in seen:
                add_var(hints[w], float(i), f"'{w}' implies")
        elif w in AUX or w in FILLER or (g.dates and w in DATE_WORDS):
            consumed.add(i)

    implied = vocab.implied_types()
    if g.wh in implied and implied[g.wh] not in seen:
        add_var(implied[g.wh], 0.0, f"'{g.wh}' implies")

    # ── anchors: leftover terms against the records — only a NAME-term hit
    # may bind, never a guess. Up to two ("designed by Ada on site Salts Mill").
    expected = {t for e in g.edges if e.relation in relations
                for t in relations[e.relation].domain | relations[e.relation].range}
    for _ in range(MAX_ANCHORS):
        leftovers = [(i, w) for i, _s, _e, w in words if i not in consumed and parts_of(w)]
        if not leftovers:
            break
        left = set().union(*(parts_of(w) for _i, w in leftovers))
        ranked = vocab.rank_entities(left)
        if not ranked:
            break
        score, top = ranked[0]
        # a record NAMED exactly what was asked beats one that mentions it
        exact = next((e for s, e in ranked[1:]
                      if s > 0 and e.name_terms == left and top.name_terms != left), None)
        if exact is not None:
            g.notes.append(f"anchor exact name: {exact.type} '{exact.name}' "
                           f"preferred over {top.type} '{top.name}'")
            score, top = next(s for s, e in ranked if e is exact), exact
        # role fit: the grounded relations say what TYPE an anchor should be;
        # a near-tied candidate of that type beats a lexical tie
        if expected and top.type not in expected:
            for s, e in ranked[1:]:
                if s >= 0.75 * score and e.type in expected and left & e.name_terms:
                    g.notes.append(f"anchor role fit: {e.type} '{e.name}' "
                                   f"preferred over {top.type} '{top.name}'")
                    score, top = s, e
                    break
        if not (score > 0 and left & top.name_terms):
            break
        hit = left & top.terms
        pos = min(i for i, w in leftovers if parts_of(w) & hit)
        node = Node("anchor", top.type, float(pos), entity=top,
                    match_terms=sorted(left & top.name_terms))
        g.anchors.append(node)
        g.nodes.append(node)
        consumed.update(i for i, w in leftovers if parts_of(w) <= hit)
        g.notes.append(f"{'/'.join(node.match_terms)} → anchor "
                       f"{top.type or 'Concept'} '{top.name}'")
        if len(g.anchors) >= len(g.edges):
            break                     # one anchor per relation at most
    g.anchor = g.anchors[0] if g.anchors else None

    if matcher is not None and not g.about:
        _match_leftovers(g, matcher, words, consumed, parts_of, relations)

    # ── one leftover word → a text filter; more stay uncovered
    remaining = [(i, w) for i, _s, _e, w in words if i not in consumed and parts_of(w)]
    contains_pos = None
    if len(remaining) == 1:
        i, w = remaining[0]
        contains_pos = float(i)
        g.contains = sorted(parts_of(w))[0]
        consumed.add(i)
        g.notes.append(f"'{w}' → text filter")

    covered = set().union(set(), *(parts_of(w) for i, _s, _e, w in words if i in consumed))
    g.coverage = len(covered & terms) / len(terms) if terms else 0.0
    g.uncovered = sorted(terms - covered)

    # ── grammar caps + wiring the relations to their ends
    if len(g.edges) > MAX_EDGES:
        g.refuse = f"{len(g.edges)} relations — the grammar caps at {MAX_EDGES}"
        return g
    _assign_edges(g, relations, seen)
    if (g.refuse.startswith("cannot resolve") and g.anchor is None
            and any(n.kind == "var" for n in g.nodes)):
        # "what technologies do we use?": the relation has no second end, but
        # the question still names what it wants — list that
        dropped = ", ".join(f"'{e.form}'" for e in g.edges)
        g.edges, g.refuse = [], ""
        g.notes.append(f"could not place {dropped}; listing the type instead")
        g.loose = dropped
    if len(g.vars()) > MAX_VARS:
        g.refuse = f"{len(g.vars())} typed variables — the grammar caps at {MAX_VARS}"
        return g
    _imply_join(g, relations)

    # the subject = what the question asks for
    if g.wh in implied:
        g.subject = seen.get(implied[g.wh])
    if g.subject is None:
        explicit = sorted(g.vars(), key=lambda n: n.pos)
        g.subject = explicit[0] if explicit else None
    _scope_negations(g, negs, contains_pos)
    return g


def _match_leftovers(g: Grounding, matcher, words, consumed, parts_of, relations) -> None:
    """The second chance: leftover runs, matched by the configured chain
    against what the structure says they could be."""
    from .matching import Item

    def take(run):
        consumed.update(w[0] for w in run)

    runs = _leftover_runs(words, consumed, parts_of)
    # a date with several possible fields: the run just before it picks one
    for dm in g.dates:
        if len(dm.fields) < 2:
            continue
        run = next((r for r in reversed(runs) if r[-1][0] < dm.pos and dm.pos - r[-1][0] <= 3), None)
        if run is None:
            continue
        phrase = " ".join(w[3] for w in run)
        items = [Item(f.field, tuple(f.forms) or (f.label,), f.label, f) for f in dm.fields]
        res = matcher.resolve(phrase, items, g.text)
        g.notes += res.notes
        if res.match:
            dm.fields = [res.match.item.payload]
            take(run)
            runs.remove(run)
        elif res.options:
            g.suggestions.append((phrase, [o.label for o in res.options]))
    # two named things and no relation between them: the run between them
    nodes = sorted(g.nodes, key=lambda n: n.pos)
    if len(nodes) >= 2 and not g.edges:
        a, b = nodes[0], nodes[-1]
        between = [r for r in runs if a.pos < r[0][0] < b.pos or a.pos < r[-1][0] < b.pos]
        types = {a.type, b.type}
        fits = [r for r in relations.values()
                if (not r.domain or r.domain & types) and (not r.range or r.range & types)]
        for run in between[:1]:
            phrase = " ".join(w[3] for w in run)
            items = [Item(r.name, tuple(r.forms), r.name, r) for r in fits]
            res = matcher.resolve(phrase, items, g.text)
            g.notes += res.notes
            if res.match:
                rel = res.match.item.payload
                g.edges.append(Edge(rel.name, float(run[0][0]), form=phrase, style=rel.style))
                take(run)
            elif res.options:
                g.suggestions.append((phrase, [o.label for o in res.options]))


def _scope_negations(g: Grounding, negs: list[tuple[int, str]], contains_pos) -> None:
    """Each negator negates the next thing named after it: a relation, a
    value, a date, the text word — or a type, meaning the relation that
    joins it ("sites with no buildings"). Nothing within reach → unplaced,
    and the planner refuses: a dropped "not" inverts the answer."""
    items: list[tuple[float, str, object]] = []
    items += [(e.pos, "edge", e) for e in g.edges]
    items += [(v.pos, "value", v) for v in g.values]
    items += [(d.pos, "date", d) for d in g.dates]
    if contains_pos is not None:
        items.append((contains_pos, "contains", None))
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
    for i, word in negs:
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
                "date": lambda d: f"date '{d.phrase}'"}[kind](what)
        g.notes.append(f"'{word}' negates {name}")


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
    candidates = [(r, a, b) for r in relations.values() if a.type in r.domain and b.type in r.range]
    candidates += [(r, b, a) for r in relations.values() if b.type in r.domain and a.type in r.range]
    if len(candidates) != 1:
        if candidates:
            g.notes.append(f"{a.type} and {b.type} could be joined by "
                           f"{', '.join(sorted(c[0].name for c in candidates))}; not guessing")
        return
    rel, src, dst = candidates[0]
    g.edges.append(Edge(rel.name, (a.pos + b.pos) / 2, form=rel.forms[0] if rel.forms else "",
                        source=src, target=dst, style=rel.style))
    g.notes.append(f"{src.type} → {dst.type} joined by {rel.name} (the only relation between them)")


def _assign_edges(g: Grounding, relations: dict[str, Relation], seen: dict) -> None:
    """Word order picks each relation's neighbours; domain/range orient it and
    fill a missing end (with an implicit typed variable when needed)."""
    for edge in g.edges:
        rel = relations.get(edge.relation)
        dom = set(rel.domain) if rel else set()
        rng = set(rel.range) if rel else set()
        parts = sorted(g.nodes, key=lambda n: n.pos)
        fits = (dom | rng)

        def nearest(cands):
            # the nearest neighbour whose type fits the relation, else the nearest
            cands = list(cands)
            return next((n for n in cands if not fits or n.type in fits),
                        cands[0] if cands else None)

        left = nearest(n for n in reversed(parts) if n.pos < edge.pos)
        right = nearest(n for n in parts if n.pos > edge.pos)
        if left is not None and right is not None and left is right:
            right = None

        def fill(hints: set, present: Node | None) -> Node | None:
            cand = next((n for n in parts if n is not present and n.type in hints), None)
            if cand is None and hints:
                t = sorted(hints)[0]
                if t in seen:
                    # never join a relation to itself — a relation whose only
                    # type-fitting candidate is its OTHER end is misgrounded
                    existing = seen[t]
                    return existing if existing is not present else None
                cand = Node("var", t, edge.pos + 0.5, var=f"?v{len(seen)}")
                seen[t] = cand
                g.nodes.append(cand)
                g.notes.append(f"relation {edge.relation} → implicit {t} variable {cand.var}")
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
