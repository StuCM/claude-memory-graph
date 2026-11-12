"""Tokenizing a question: meaningful words, with their positions."""

import re
from functools import lru_cache

STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "are", "this", "that", "it", "be", "can", "could", "would", "how", "what",
    "when", "i", "you", "we", "do", "does", "make", "get", "set", "use",
    "about", "did", "was", "were", "they", "them", "our", "your", "just", "some",
    "thanks", "thank", "yes", "yep", "ok", "okay", "sure", "no", "nope", "please",
    # kept in step with claude_memory_graph/hookcore/text.py
    # function words of conversational prose: scored per sentence, a long
    # prompt's "…before the standup" must not match a memory named "…before
    # migrations" on that word alone
    "before", "after", "also", "anything", "something", "everything", "nothing",
    "else", "need", "needs", "let", "know", "want", "think", "maybe", "might",
    "really", "will", "should", "have", "has", "had", "been", "there", "then",
    "than", "from", "into", "any", "all", "one", "thing", "going",
}
# a letter of any script, diacritics included ("mātauranga", "táin"), or a digit
ALNUM = r"[^\W_]"
NEG = {"not", "no", "without", "never", "non", "isn't", "aren't", "wasn't", "weren't",
       "don't", "doesn't", "didn't", "hasn't", "haven't", "hadn't", "lacking"}
_WORD = re.compile(ALNUM + "+")


def terms_pos(text: str) -> list[tuple[int, str]]:
    """Meaningful words with their positions in the full token stream: lowercase,
    no stopwords, longer than two letters."""
    return [(i, w) for i, w in enumerate(_WORD.findall(text.lower()))
            if len(w) > 2 and w not in STOP]


def terms(text: str) -> list[str]:
    return [w for _, w in terms_pos(text)]


@lru_cache(maxsize=1 << 16)
def marks(text: str) -> frozenset[str]:
    """Its numbers and version tokens, which `terms` drops when short: "Flood model v1.0" →
    {"v1", "0"}, "Grade II" → {"ii"}. Part of a record's name, so a partial name doesn't pass as whole."""
    return frozenset(w for w in _WORD.findall(text.lower()) if any(c.isdigit() for c in w) or _ROMAN.fullmatch(w))


_ROMAN = re.compile(r"[ivx]{2,}")


def overlaps(start: int, end: int, spans) -> bool:
    return any(start < e and end > s for s, e in spans)


def plural(word: str) -> str:
    """A noun's plural, keeping its case ("Site" → "Sites", "property" → "properties")."""
    if word.endswith("y") and len(word) > 2 and word[-2].lower() not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def plurals(word: str) -> set[str]:
    """A noun and its plural, as people type them ("site" → "sites",
    "property" → "properties")."""
    low = word.lower()
    return {low, low + "s", plural(low)}


# irregular past participles: vocab_rules phrases verbs with them, matching roots them back
PAST = {"hold": "held", "make": "made", "build": "built", "write": "written", "find": "found",
        "keep": "kept", "lead": "led", "draw": "drawn", "give": "given", "take": "taken",
        "buy": "bought", "sell": "sold", "teach": "taught", "speak": "spoken", "lend": "lent"}
# other irregular pasts people ask with, to their verb; matching roots by both tables
UNPAST = {"wrote": "write", "drew": "draw", "gave": "give", "took": "take", "spoke": "speak",
          "began": "begin", "begun": "begin", "came": "come", "became": "become", "went": "go",
          "gone": "go", "saw": "see", "seen": "see", "dug": "dig", "fought": "fight", "won": "win",
          "lost": "lose", "sank": "sink", "sunk": "sink", "fell": "fall", "fallen": "fall",
          "stood": "stand", "sent": "send", "laid": "lay", "paid": "pay", "told": "tell",
          "said": "say"}
