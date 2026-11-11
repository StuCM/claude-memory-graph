"""The question's words, the state the passes share, and the span tests they use."""

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from ..text import ALNUM, marks, overlaps, terms_pos
from ..vocabulary import Group, Relation, Value, Vocabulary
from .model import Grounding, Node

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


# the only free text a question may hold, and only in this slot
_WORD = rf"(['\"]?)({ALNUM}(?:{ALNUM}|['-])*?)\1(?!{ALNUM}|['-])"
NAME_RES = [
    ("prefix", re.compile(rf"(?<!{ALNUM})(?:whose\s+|with\s+(?:an?|the)\s+)?names?\s+"
                          r"(?:starts?|starting|begins?|beginning)\s+with\s+" + _WORD)),
    ("word", re.compile(rf"(?<!{ALNUM})" + _WORD + r"\s+in\s+(?:the|their|its)\s+names?"
                        rf"(?!{ALNUM})")),
    ("word", re.compile(rf"(?<!{ALNUM})called\s+" + _WORD)),
]


PREPS = {"by", "on", "in", "at", "to", "from", "with", "for", "of", "into", "under", "up",
         "down", "out", "off", "over", "about"}
# question words and determiners a phrasing may lead with ("which monuments")
_LEAD_WORDS = {"which", "what", "who", "whose", "the", "a", "an", "any", "all", "some",
               "show", "list", "find", "me"}
# the text before a phrase ends where a question names its subject
_SUBJECT_LEAD = re.compile(r"(^|\b(which|what|how many|show me|list|find|any|all|are there))"
                           r"(\s+(the|any|all|of the))?\s*$", re.I)
MOST = {"most": "most", "fewest": "fewest", "least": "fewest"}


Span = tuple[int, int]


def is_question(text: str) -> bool:
    stripped = text.strip()
    words = WORD_RE.findall(stripped.lower())
    return bool(stripped.endswith("?") or (words and _opens(words[0])))


def _opens(word: str) -> bool:
    return word in WH or word in AUX or word in IMPERATIVE


def _inside(start: int, end: int, spans) -> bool:
    return any(s <= start and end <= e for s, e in spans)


class Word(NamedTuple):
    i: int
    start: int
    end: int
    text: str


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
    # each bound phrase → every relation it names
    sharing: dict[str, list[str]] = field(default_factory=dict)
    seen: dict[str, Node] = field(default_factory=dict)
    negs: list[tuple[int, str]] = field(default_factory=list)
    held: set[int] = field(default_factory=set)        # words the text filter may not take
    contains_pos: float | None = None
    about: bool = False                                 # "what do we know about X"

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
        node = Node("var", t, pos)
        self.seen[t] = node
        self.g.nodes.append(node)
        self.g.notes.append(f"{why} → typed variable : {t}")
        return node

    def types_of(self, form: str, rel: str) -> frozenset[str]:
        said = self.relations[rel].said_as(form)
        return said.domain | said.range


def _scan(vocab: Vocabulary, text: str, filler: frozenset[str] = frozenset()) -> Scan:
    # same length, so spans stay aligned: "non-listed" → "non listed"
    raw = text.lower().replace("\u2019", "'").replace("non-", "non ")
    words = [Word(i, m.start(), m.end(), m.group()) for i, m in enumerate(WORD_RE.finditer(raw))]
    terms = {w for _, w in terms_pos(text)} | (MEANINGFUL & set(re.findall(ALNUM + "+", raw)))
    # "v1.0" in "Flood model v1.0": only where a record's name has it, so other numbers stay as they were
    terms |= {m for m in marks(text) if vocab.rank_entities({m})}
    terms -= filler
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
        # ~1,400 phrases per question overflow re's 512-pattern cache: test the substring before compiling
        if phrase not in raw:
            continue
        m = next((m for m in re.finditer(rf"(?<!{ALNUM}){re.escape(phrase)}(?!{ALNUM})", raw)
                  if not any(s <= m.start() and m.end() <= e and m.end() - m.start() < e - s
                             for s, e in names)), None)
        if not m or overlaps(m.start(), m.end(), taken):
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
