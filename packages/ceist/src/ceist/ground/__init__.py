"""Grounding: which words of a question name which parts of the vocabulary.

Pipeline: shape → relations (longest phrase first, on the raw text, so
"works on" keeps its stopword) → group phrases ("burnt down": a tile of a
nodegroup) → controlled values ("listed", "active") →
dates ("before 1900", with the word that picks the field: "built") → numbers
("capacity over 200", with the field word or unit that picks the field) → type
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

from ..vocabulary import Vocabulary
from .leftovers import _coverage, _fill_groups, _match_leftovers, _text_filter
from .model import (
    DateGround,
    Edge,
    Grounding,
    GroupGround,
    NameGround,
    NearGround,
    Node,
    NumberGround,
    ValueMatch,
)
from .nodes import _anchors, _fit_relations, _imply_model, _words
from .phrases import (
    _dates,
    _field_phrases,
    _group_by,
    _near,
    _numbers,
    _relations,
    _shape,
    _tile_phrases,
    _values,
)
from .scan import (
    AUX,
    DATE_WORDS,
    IMPERATIVE,
    MILE_KM,
    NEG,
    PREPS,
    WH,
    WORD_RE,
    Scan,
    _scan,
    is_question,
)
from .wire import _or, _scope_negations, _subject, _wire

__all__ = ["AUX", "DATE_WORDS", "IMPERATIVE", "MILE_KM", "NEG", "PREPS", "WH", "WORD_RE",
           "DateGround", "Edge", "GroupGround", "Grounding", "NameGround", "NearGround", "Node",
           "NumberGround", "ValueMatch", "ground", "is_question", "pieces"]


def ground(vocab: Vocabulary, text: str, today=None, matcher=None) -> Grounding:
    s = pieces(vocab, text, today, matcher)
    if _or(s) or _wire(s):             # each says whether it refused
        return s.g
    _subject(s)
    _scope_negations(s)   # after subject: a negator never targets the subject
    return s.g


def pieces(vocab: Vocabulary, text: str, today=None, matcher=None, fit: bool = True,
           filler: frozenset[str] = frozenset()) -> Scan:
    """Every pass up to coverage. Without `fit`, each link phrase keeps all its relations
    unchosen (schema assembly chooses); `filler` words are ignored, never placed."""
    s = _scan(vocab, text, filler)
    _shape(s)             # first: "Find" is no value, "how many" no group, "about X" no relation
    _relations(s)         # a longer group or value phrase beats a relation inside it, "bronze age"
    _group_by(s)          # before anchors: it removes the "by county" edge the anchor cap counts
    _tile_phrases(s)      # record name > longer phrase > relation > tile phrase > value
    _values(s)
    _field_phrases(s)     # after values: a field phrase holds the value after it
    _near(s)              # before dates: "within 2000 miles of" is no year
    _dates(s, today)      # after relations: "built by" beats the date-field word "built"
    _numbers(s)           # after near and dates: "within 20 km" stays a distance, "before 1900" a date
    _words(s)             # after dates: a date word is shape only once a date grounded
    _anchors(s)           # after words: ranks leftovers only; edges and near set its role and cap
    if fit:
        _fit_relations(s)  # after anchors: fitting needs both ends named
    _imply_model(s)
    if matcher is not None and not s.about:
        _match_leftovers(s, matcher)   # after fit (edges removed) and imply model (types it adds)
    _fill_groups(s)       # after the matcher: it fills the groups the matcher adds
    _text_filter(s)       # after fill groups: words held in a group's clause stay out
    _coverage(s)          # after every pass that consumes
    return s
