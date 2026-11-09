"""Grounding: which words of a question name which parts of the vocabulary.

Pipeline: shape → relations (longest phrase first, on the raw text, so
"works on" keeps its stopword) → group phrases ("burnt down": a tile of a
nodegroup) → controlled values ("listed", "active") →
dates ("before 1900", with the word that picks the field: "built") → type
nouns, modifiers, negators and hints → implied types (who → Person) → up to
two named anchors (only a whole name or alias may bind; never a guess, and a
shorter relation, group or value phrase inside one gives way to it) → each
group phrase takes the values and date of its clause → one leftover word as a
text filter, if the vocabulary has free text → coverage → wire the relations
to their ends → scope each negator ("not", "without", "non-") to the next
thing named.

With a matcher (ceist.matching.Chain), words the exact pass left over get a
second chance before they become a text filter: a run of leftover words
between two named things is matched against the relations that can join
them, one before a date against the date fields it could be, and any other
against the group phrases of the types named. A
confident match grounds like an exact one (the note says which layer
decided); otherwise the closest items become suggestions ("did you mean …").

The result says what was understood and how sure (coverage); plan.py turns
it into a query plan, and refuses rather than guesses when it is thin.
"""

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from . import dates
from .text import ALNUM, terms_pos
from .vocabulary import DateField, Entity, Group, Relation, Value, Vocabulary

WH = {"what", "which", "who", "whom", "whose", "why", "when", "how", "where"}
AUX = {"is", "are", "was", "were", "do", "does", "did", "has", "have", "had",
       "can", "could", "should", "would", "any"}
RECENT = {"recent", "recently", "latest", "newest"}
# commands that ask a question: "list all decisions", "show me patterns"
IMPERATIVE = {"list", "show", "find", "give", "tell", "name"}
# words that shape a question but name nothing: never a text filter
FILLER = {"me", "all", "every", "please", "been", "exist", "exists",
          "there", "we", "us", "our", "i", "you", "about", "ever", "have"}
# stopwords elsewhere, but a question can turn on them: "what did X make?" must not become "X"
MEANINGFUL = {"make", "use", "get", "set", "need", "want", "know", "before", "after"}
# "what do we know about X", "tell me about X": the answer is X itself, and the
# verb ("know") must not ground as a relation
ABOUT_RE = re.compile(r"^\s*(?:what\s+(?:do|does|did)\s+(?:we|i|you)\s+(?:know|have|remember)"
                      r"|tell\s+me|what(?:'s| is)\s+(?:known|there))\s+about\s+", re.I)
WORD_RE = re.compile(rf"{ALNUM}(?:{ALNUM}|['-])*")
NEG = {"not", "no", "without", "never", "non", "isn't", "aren't", "wasn't", "weren't",
       "don't", "doesn't", "didn't", "hasn't", "haven't", "hadn't", "lacking"}
DATE_WORDS = {"date", "dated", "dates", "dating"}   # shape, once a date is grounded
NEG_REACH = 4             # a negator scopes over the next thing named within this many words
CLAUSE_END = {"and", "or", "but", "which", "that", "who", "whose", "where", "while"}
MAX_EDGES = 2
MAX_VARS = 2
MAX_ANCHORS = 2
NEAR_KM = 5.0             # what "near" means, said in the narration
MILE_KM = 1.609344
NEAR_RE = re.compile(rf"(?<!{ALNUM})(?<!-)(?:within\s+(\d+(?:\.\d+)?)\s*(km|kms|kilometres?|kilometers?"
                     r"|miles?)\s+of|near)" rf"(?!{ALNUM}|-)")


@dataclass
class Node:
    kind: str                 # "var" | "anchor"
    type: str
    pos: float                # word index, for word-order rules
    var: str = ""             # variable name (vars)
    entity: Entity | None = None
    match_terms: list[str] = field(default_factory=list)
    implicit: bool = False    # a var only a relation's end implied, not named
    either: list[Entity] = field(default_factory=list)   # anchors: the records "or" adds

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
    path: str = ""                                    # the backend's name for the link
    qualifier: tuple[str, str, str] | None = None     # (field, value, label) on the same tile
    group: str = ""                                   # that tile's nodegroup


def _edge(rel: Relation, pos: float, **kw) -> Edge:
    return Edge(rel.name, pos, style=rel.style, path=rel.path or rel.name,
                qualifier=rel.qualifier, group=rel.group, **kw)


@dataclass
class ValueMatch:
    phrase: str
    pos: float
    candidates: list[Value]   # every field this phrase can be a value of
    negated: bool = False
    words: list[int] = field(default_factory=list)
    either: list["ValueMatch"] = field(default_factory=list)   # the values "or" adds


@dataclass
class DateGround:
    phrase: str
    pos: float
    lo: str | None
    hi: str | None
    fields: list[DateField]   # the field the words picked, else every candidate
    negated: bool = False
    picked: float | None = None   # where the word that picked the field is


@dataclass
class NearGround:
    """"near X" / "within 5 km of X": X is measured from, not linked to."""
    phrase: str
    pos: float
    km: float
    unit: str = "km"                  # as asked: "km" | "miles"
    entity: Entity | None = None      # the named record after the phrase
    negated: bool = False


@dataclass
class GroupGround:
    """A phrase naming one tile of a nodegroup, and what its clause says of it."""
    phrase: str
    pos: float
    words: list[int]                                  # the phrase's word indices
    candidates: list[tuple[Group, tuple[Value, ...]]]  # each group it names, with the values it sets
    group: Group | None = None                        # the one chosen
    values: list[Value] = field(default_factory=list)
    date: DateGround | None = None
    negated: bool = False


@dataclass
class NameGround:
    """A record-name condition the question spells out: "whose name starts with Cat"."""
    term: str                 # as typed
    mode: str                 # "prefix" | "word"
    pos: float
    negated: bool = False


# the only free text a question may hold, and only in this slot
_WORD = rf"(['\"]?)({ALNUM}(?:{ALNUM}|['-])*?)\1(?!{ALNUM}|['-])"
NAME_RES = [
    ("prefix", re.compile(rf"(?<!{ALNUM})(?:whose\s+|with\s+(?:an?|the)\s+)?names?\s+"
                          r"(?:starts?|starting|begins?|beginning)\s+with\s+" + _WORD)),
    ("word", re.compile(rf"(?<!{ALNUM})" + _WORD + r"\s+in\s+(?:the|their|its)\s+names?"
                        rf"(?!{ALNUM})")),
    ("word", re.compile(rf"(?<!{ALNUM})called\s+" + _WORD)),
]


@dataclass
class Grounding:
    text: str = ""
    wh: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    values: list[ValueMatch] = field(default_factory=list)
    dates: list[DateGround] = field(default_factory=list)
    groups: list[GroupGround] = field(default_factory=list)
    near: NearGround | None = None
    recent: bool = False
    contains: str | None = None
    contains_negated: bool = False
    name: NameGround | None = None
    negation_unplaced: str = ""   # a negator with nothing after it to negate
    subject: Node | None = None
    anchor: Node | None = None            # the first named record
    anchors: list[Node] = field(default_factory=list)
    coverage: float = 0.0
    uncovered: list[str] = field(default_factory=list)
    refuse: str = ""          # out-of-grammar reason
    field_of: Edge | None = None   # a link to a named record that can't say what it
                                   # points at: the record's own field may be meant
    count: bool = False       # "how many …"
    group: Edge | None = None # "by county": count per record this link points at
    group_order: str = ""     # "most" | "fewest": only the top or bottom one
    loose: str = ""           # relation phrases dropped to list a type
    about: bool = False       # "what do we know about X"
    notes: list[str] = field(default_factory=list)
    suggestions: list[tuple[str, list[str]]] = field(default_factory=list)   # (words, did-you-mean)
    # phrases no layer placed, for the learning log (ceist.learn.from_grounding):
    # {"phrase", "model", "slot", "options": [{"node", "qualifier", "end_node", "label"}]}
    unplaced: list[dict] = field(default_factory=list)

    def vars(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "var"]


def is_question(text: str) -> bool:
    stripped = text.strip()
    words = WORD_RE.findall(stripped.lower())
    return bool(stripped.endswith("?") or (words and _opens(words[0])))


def _opens(word: str) -> bool:
    return word in WH or word in AUX or word in IMPERATIVE


def _overlaps(start: int, end: int, spans) -> bool:
    return any(start < e and end > s for s, e in spans)


def _inside(start: int, end: int, spans) -> bool:
    return any(s <= start and end <= e for s, e in spans)


PREPS = {"by", "on", "in", "at", "to", "from", "with", "for", "of", "into", "under", "up",
         "down", "out", "off", "over", "about"}


# question words and determiners a phrasing may lead with ("which monuments")
_LEAD_WORDS = {"which", "what", "who", "whose", "the", "a", "an", "any", "all", "some",
               "show", "list", "find", "me"}
# the text before a phrase ends where a question names its subject
_SUBJECT_LEAD = re.compile(r"(^|\b(which|what|how many|show me|list|find|any|all|are there))"
                           r"(\s+(the|any|all|of the))?\s*$", re.I)


MOST = {"most": "most", "fewest": "fewest", "least": "fewest"}


class Word(NamedTuple):
    i: int
    start: int
    end: int
    text: str


Span = tuple[int, int]


@dataclass
class Scan:
    """What the passes share: the question's words, what each pass has claimed, and the output."""
    vocab: Vocabulary
    text: str
    raw: str
    words: list[Word]
    terms: set[str]
    g: Grounding
    type_words: dict[str, str]
    groups: list[Group]
    group_forms: dict[str, list]
    value_forms: dict[str, list[Value]]
    any_of: bool
    free_text: bool
    names: list[Span] = field(default_factory=list)
    consumed: set[int] = field(default_factory=set)
    taken: list[Span] = field(default_factory=list)
    relations: dict[str, Relation] = field(default_factory=dict)
    sharing: dict[str, list[str]] = field(default_factory=dict)   # each bound phrase → every relation it names
    seen: dict[str, Node] = field(default_factory=dict)
    negs: list[tuple[int, str]] = field(default_factory=list)
    held: set[int] = field(default_factory=set)
    contains_pos: float | None = None

    def parts_of(self, word: str) -> set[str]:
        # raw words like "memory-graph" must meet terms ("memory", "graph")
        return {p for p in re.split(r"[\W_]+", word) if p} & self.terms

    def words_in(self, start: int, end: int) -> list[int]:
        return [w.i for w in self.words if w.start >= start and w.end <= end]

    def consume_span(self, start: int, end: int) -> float:
        at = self.words_in(start, end)
        self.consumed.update(at)
        return float(at[0] if at else 0)

    def add_var(self, t: str, pos: float, why: str) -> Node:
        node = Node("var", t, pos, var=f"?v{len(self.seen)}")
        self.seen[t] = node
        self.g.nodes.append(node)
        self.g.notes.append(f"{why} → typed variable {node.var} : {t}")
        return node

    def types_of(self, form: str, rel: str) -> frozenset[str]:
        said = self.relations[rel].said_as(form)
        return said.domain | said.range


def _scan(vocab: Vocabulary, text: str) -> Scan:
    # same length, so spans stay aligned: "non-listed" → "non listed"
    raw = text.lower().replace("\u2019", "'").replace("non-", "non ")
    words = [Word(i, m.start(), m.end(), m.group()) for i, m in enumerate(WORD_RE.finditer(raw))]
    terms = {w for _, w in terms_pos(text)} | (MEANINGFUL & set(re.findall(ALNUM + "+", raw)))
    groups = list(getattr(vocab, "groups", lambda: [])())
    group_forms: dict[str, list] = {}
    for grp in groups:
        for phrase, preset in grp.forms:
            if terms_pos(phrase):
                group_forms.setdefault(phrase, []).append((grp, preset))
    value_forms: dict[str, list[Value]] = {}
    for v in vocab.values():
        # a label with no content word ("S", "in": inch) matches a letter or
        # a function word in every question
        if terms_pos(v.phrase):
            value_forms.setdefault(v.phrase, []).append(v)
    s = Scan(vocab, text, raw, words, terms, Grounding(text=text), vocab.type_words(), groups,
             group_forms, value_forms, getattr(vocab, "any_of", False),
             getattr(vocab, "free_text", False))
    s.names = _record_spans(s)
    return s


def _phrase_spans(raw: str, phrases: list[tuple[str, object]], taken: list[tuple[int, int]],
                  names: list[tuple[int, int]] = ()):
    """Longest phrase first; each match must not overlap an earlier one, nor
    sit inside a longer record name (`names`)."""
    for phrase, payload in sorted(phrases, key=lambda x: -len(x[0])):
        m = next((m for m in re.finditer(rf"(?<!{ALNUM}){re.escape(phrase)}(?!{ALNUM})", raw)
                  if not any(s <= m.start() and m.end() <= e and m.end() - m.start() < e - s
                             for s, e in names)), None)
        if not m or _overlaps(m.start(), m.end(), taken):
            continue
        taken.append((m.start(), m.end()))
        yield phrase, payload, m


def _record_spans(s: Scan) -> list[Span]:
    """Where the question names a record in full ("County Down"): the character
    span of each run of words that holds a whole name or alias."""
    spans = set()
    for _score, e in s.vocab.rank_entities(s.terms):
        for name in (e.name_terms, *e.aliases):
            if not name or not name <= s.terms:
                continue
            start, got = None, set()
            for _i, ws, end, w in s.words:
                part = s.parts_of(w)
                if not part:
                    continue
                if not part <= name:
                    start = None
                    continue
                if start is None:
                    start, got = ws, set()
                got |= part
                if got == name:
                    spans.add((start, end))
                    start = None
    return sorted(spans)


def _leftover_runs(s: Scan) -> list[list[Word]]:
    """Maximal runs of unconsumed words, trimmed to start at a meaningful word
    and end at one or at a preposition ("put up", "designed by")."""
    runs, cur = [], []
    for w in s.words:
        if w.i in s.consumed:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(w)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        while r and not s.parts_of(r[0].text):
            r = r[1:]
        while r and not s.parts_of(r[-1].text) and r[-1].text not in PREPS:
            r = r[:-1]
        if r:
            out.append(r)
    return out


def ground(vocab: Vocabulary, text: str, today=None, matcher=None) -> Grounding:
    s = _scan(vocab, text)
    _shape(s)             # first: "Find" is no value, "how many" no group phrase, "about X" no relation
    _relations(s)         # a longer group or value phrase beats a relation inside it, "bronze age"
    _group_by(s)          # before anchors: it removes the "by county" edge the anchor cap counts
    _tile_phrases(s)      # record name > longer phrase > relation > tile phrase > value
    _values(s)
    _field_phrases(s)     # after values: a field phrase holds the value after it
    _near(s)              # before dates: "within 2000 miles of" is no year
    _dates(s, today)      # after relations: "built by" beats the date-field word "built"
    _words(s)             # after dates: a date word is shape only once a date grounded
    _anchors(s)           # after words, relations and near: leftovers only; edges and near set role and cap
    _fit_relations(s)     # after anchors: fitting needs both ends named
    _imply_model(s)
    if matcher is not None and not s.g.about:
        _match_leftovers(s, matcher)   # after fit (edges removed) and imply model (types it adds)
    _fill_groups(s)       # after the matcher: it fills the groups the matcher adds
    _text_filter(s)       # after fill groups: words held in a group's clause stay out
    _coverage(s)          # after every pass that consumes
    if _or(s) or _wire(s):             # each says whether it refused
        return s.g
    _subject(s)
    _scope_negations(s)   # after subject: a negator never targets the subject
    return s.g


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
        g.about = True
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
    longer = [(m.start(), m.end()) for p in (*s.group_forms, *s.value_forms)
              for m in re.finditer(rf"(?<!{ALNUM}){re.escape(p)}(?!{ALNUM})", raw)
              if not _overlaps(m.start(), m.end(), shape)]
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
             if re.search(rf"(?<!{ALNUM}){re.escape(w)}(?!{ALNUM})", raw)}
    forms = sorted(((f, r.name) for r in s.relations.values() for f in r.forms),
                   key=lambda x: not s.types_of(*x) & named)
    for form, rel, m in ([] if g.about else _phrase_spans(raw, forms, s.taken, s.names + longer)):
        subject = just_a_type(form) and (form.split()[0] in _LEAD_WORDS
                                         or _SUBJECT_LEAD.search(raw[:m.start()]))
        if subject or rel in matched:
            s.taken.remove((m.start(), m.end()))
            continue
        matched.add(rel)
        s.relations[rel] = s.relations[rel].said_as(form)
        g.edges.append(_edge(s.relations[rel], s.consume_span(m.start(), m.end()), form=form))
        g.notes.append(f"'{form}' → relation {rel}")
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
    that follows it to that field. With no such value after it, it places nothing."""
    g = s.g
    by_phrase: dict[str, set] = {}
    for phrase, model, alias in getattr(s.vocab, "field_phrases", lambda: [])():
        by_phrase.setdefault(phrase, set()).add((model, alias))
    for phrase, owners, m in _phrase_spans(s.raw, list(by_phrase.items()), list(s.taken), s.names):
        last = max(s.words_in(m.start(), m.end()))
        vm = min((v for v in g.values if v.pos > last), key=lambda v: v.pos, default=None)
        if vm is None or any(s.parts_of(w) for i, _s, _e, w in s.words if last < i < vm.pos):
            continue
        fit = [v for v in vm.candidates if any(v.field == a and (not v.owners or t in v.owners)
                                               for t, a in owners)]
        if not fit:
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
              if not _overlaps(m.start(), m.end(), s.taken + s.names)), None)
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
    found = dates.find(s.raw, s.taken, today)
    if not found:
        return
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
    g.anchor = g.anchors[0] if g.anchors else None


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
    if g.nodes or g.edges or g.about:
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


def _match_leftovers(s: Scan, matcher) -> None:
    """The second chance: leftover runs, matched by the configured chain
    against what the structure says they could be."""
    from .matching import Item
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
        res = matcher.resolve(phrase, items, g.text)
        g.notes += res.notes
        if res.match:
            dm.fields = [res.match.item.payload]
            take(run)
            runs.remove(run)
        else:
            if res.options:
                g.suggestions.append((phrase, [o.label for o in res.options]))
            owners = {o for f in dm.fields for o in f.owners}
            g.unplaced.append({
                "phrase": phrase, "slot": "date",
                "model": next(iter(owners)) if len(owners) == 1 else
                (g.subject.type if g.subject else ""),
                "options": [{"node": o.payload.field, "qualifier": None, "end_node": None,
                             "label": o.label} for o in res.options]})
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
            res = matcher.resolve(phrase, items, g.text)
            g.notes += res.notes
            if res.match:
                rel = res.match.item.payload
                g.edges.append(_edge(rel, float(run[0].i), form=phrase))
                take(run)
            else:
                if res.options:
                    g.suggestions.append((phrase, [o.label for o in res.options]))
                domains = {d for r in fits for d in r.domain}
                model = next(iter(domains)) if len(domains) == 1 else a.type
                other = b.type if model == a.type else a.type
                g.unplaced.append({
                    "phrase": phrase, "slot": f"link:{other}", "model": model,
                    "options": [{"node": o.payload.path or o.payload.name,
                                 "qualifier": o.payload.qualifier[1] if o.payload.qualifier
                                 else None, "end_node": None, "label": o.label}
                                for o in res.options]})
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
        res = matcher.resolve(phrase, items, g.text)
        g.notes += res.notes
        if res.match:
            g.groups.append(GroupGround(phrase, float(run[0].i), [w.i for w in run],
                                        [res.match.item.payload]))
            take(run)
        elif res.options:
            g.suggestions.append((phrase, [o.label for o in res.options]))


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


def _or(s: Scan) -> bool:
    """A plan is a conjunction: "raths or cairns" would be read as "raths and cairns".
    True when it refused."""
    g = s.g
    for i, ws, we, w in s.words:
        if w != "or" or i in s.consumed or _inside(ws, we, s.names):
            continue
        if not s.any_of:
            g.refuse = "'or' isn't supported yet; ask one at a time"
            return True
        g.refuse = _either_values(g, i)
        if g.refuse:
            return True
    return False


def _either_values(g: Grounding, i: int) -> str:
    """Join the values either side of the "or" at word `i` when one field can
    hold both; otherwise why not."""
    a = next((v for v in g.values if v.words and (v.either or [v])[-1].words[-1] == i - 1),
             None)
    b = next((v for v in g.values if v.words and v.words[0] == i + 1), None)
    if a is None or b is None:
        return ("'or' is supported only between two values of one field or two named "
                "records; ask one at a time")
    fields = {c.field for c in b.candidates}
    for v in [a, *a.either]:
        fields &= {c.field for c in v.candidates}
    if not fields:
        return (f"'or' joins '{a.phrase}' and '{b.phrase}', which aren't values of one "
                "field; ask one at a time")
    a.either.append(b)
    g.values.remove(b)
    g.notes.append(f"'{a.phrase}' or '{b.phrase}' → either value of "
                   + " / ".join(sorted(fields)))
    return ""


def _wire(s: Scan) -> bool:
    """The grammar caps, and each relation wired to its ends. True when it refused."""
    g = s.g
    if len(g.edges) > MAX_EDGES:
        g.refuse = f"{len(g.edges)} relations — the grammar caps at {MAX_EDGES}"
        return True
    _assign_edges(s)
    if not g.refuse:
        _check_anchors(g, s.relations)
    if (g.refuse.startswith("cannot resolve") and g.anchor is None
            and any(n.kind == "var" for n in g.nodes)):
        if s.free_text:
            # "what technologies do we use?": the relation has no second end, but
            # the question still names what it wants — list that
            dropped = ", ".join(f"'{e.form}'" for e in g.edges)
            g.edges, g.refuse = [], ""
            g.notes.append(f"could not place {dropped}; listing the type instead")
            g.loose = dropped
        elif g.uncovered:
            # "in Down": the end it couldn't find is a word nothing placed; plan.py names that
            g.refuse = ""
    if len(g.vars()) > MAX_VARS:
        g.refuse = f"{len(g.vars())} typed variables — the grammar caps at {MAX_VARS}"
        return True
    _imply_join(g, s.relations)
    return False


def _assign_edges(s: Scan) -> None:
    """Word order picks each relation's neighbours; domain/range orient it and
    fill a missing end (with an implicit typed variable when needed)."""
    g, seen = s.g, s.seen
    for edge in g.edges:
        rel = s.relations.get(edge.relation)
        dom = set(rel.domain) if rel else set()
        rng = set(rel.range) if rel else set()
        parts = sorted(g.nodes, key=lambda n: n.pos)
        fits = (dom | rng)

        def nearest(cands):
            # the nearest neighbour whose type fits the relation, else the nearest
            cands = list(cands)
            return next((n for n in cands if not fits or n.type in fits),
                        cands[0] if cands else None)

        # <=: the type "who" implies sits at 0.0, where a phrase that starts with it ("who made") also is
        left = nearest(n for n in reversed(parts) if n.pos <= edge.pos)
        right = nearest(n for n in parts if n.pos > edge.pos)
        if left is not None and right is not None and left is right:
            right = None
        before = s.words[int(edge.pos) - 1].text if edge.pos >= 1 else ""
        if right is None and left is not None and before == "as":
            # "which areas have X as copyright holder": the phrase names X's role
            right = left
            left = nearest(n for n in reversed(parts) if n.pos < right.pos)

        def fill(hints: set, present: Node | None) -> Node | None:
            cand = next((n for n in parts if n is not present and n.type in hints), None)
            if cand is None and hints:
                t = sorted(hints)[0]
                if t in seen:
                    # never join a relation to itself — a relation whose only
                    # type-fitting candidate is its OTHER end is misgrounded
                    existing = seen[t]
                    return existing if existing is not present else None
                cand = Node("var", t, edge.pos + 0.5, var=f"?v{len(seen)}", implicit=True)
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


def _check_anchors(g: Grounding, relations: dict[str, Relation]) -> None:
    """A named record must be one its link can point at: "what is in Navan
    Fort", a Monument where 'in' points at Sites, would match nothing real.
    Where the link can't say what it points at, the record's own field may be
    meant ("what period is Navan Fort"): `field_of`, which plan.py settles."""
    for e in g.edges:
        rel = relations.get(e.relation)
        if rel is None or e.target is None or e.target.kind != "anchor":
            continue
        a = e.target
        if not rel.joins(e.source.type, a.type):
            g.refuse = _wrong_end(a, e.form, rel.targets(e.source.type))
            return
        if not rel.targets(e.source.type):
            g.field_of = e


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
    # a join never implies a role: qualified variants ("actor#Architect") don't count
    plain = [r for r in relations.values() if not r.qualifier]
    candidates = [(r, a, b) for r in plain if a.type in r.domain and b.type in r.range]
    candidates += [(r, b, a) for r in plain if b.type in r.domain and a.type in r.range]
    if len(candidates) != 1:
        if candidates:
            g.notes.append(f"{a.type} and {b.type} could be joined by "
                           f"{', '.join(sorted(c[0].name for c in candidates))}; not guessing")
        return
    rel, src, dst = candidates[0]
    g.edges.append(_edge(rel, (a.pos + b.pos) / 2, form=rel.forms[0] if rel.forms else "",
                         source=src, target=dst))
    g.notes.append(f"{src.type} → {dst.type} joined by {rel.name} (the only relation between them)")


def _subject(s: Scan) -> None:
    """What the question asks for."""
    g = s.g
    implied = s.vocab.implied_types()
    if g.wh in implied:
        g.subject = s.seen.get(implied[g.wh])
    if g.subject is None:
        explicit = sorted(g.vars(), key=lambda n: n.pos)
        g.subject = explicit[0] if explicit else None


def _scope_negations(s: Scan) -> None:
    """Each negator negates the next thing named after it: a relation, a
    value, a date, the text word — or a type, meaning the relation that
    joins it ("sites with no buildings"). Nothing within reach → unplaced,
    and the planner refuses: a dropped "not" inverts the answer."""
    g = s.g
    items: list[tuple[float, str, object]] = []
    items += [(e.pos, "edge", e) for e in g.edges]
    items += [(v.pos, "value", v) for v in g.values]
    items += [(d.pos, "date", d) for d in g.dates]
    items += [(t.pos, "group", t) for t in g.groups]
    if g.near is not None:
        items.append((g.near.pos, "near", g.near))
    if g.name is not None:
        items.append((g.name.pos, "name", g.name))
    if s.contains_pos is not None:
        items.append((s.contains_pos, "contains", None))
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
    for i, word in s.negs:
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
                "date": lambda d: f"date '{d.phrase}'",
                "group": lambda t: f"the '{t.phrase}' entry",
                "near": lambda n: f"'{n.phrase}'",
                "name": lambda n: f"the name match '{n.term}'"}[kind](what)
        g.notes.append(f"'{word}' negates {name}")
