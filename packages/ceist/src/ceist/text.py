"""Tokenizing a question: meaningful words, with their positions."""

import re

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
_WORD = re.compile(r"[a-z0-9]+")


def terms_pos(text: str) -> list[tuple[int, str]]:
    """Meaningful words with their positions in the full token stream: lowercase,
    no stopwords, longer than two letters."""
    return [(i, w) for i, w in enumerate(_WORD.findall(text.lower()))
            if len(w) > 2 and w not in STOP]


def terms(text: str) -> list[str]:
    return [w for _, w in terms_pos(text)]


def plurals(word: str) -> set[str]:
    """A noun and its plural, as people type them ("site" → "sites",
    "property" → "properties")."""
    low = word.lower()
    out = {low, low + "s"}
    if low.endswith("y") and len(low) > 2 and low[-2] not in "aeiou":
        out.add(low[:-1] + "ies")
    if low.endswith(("s", "x", "ch", "sh")):
        out.add(low + "es")
    return out
