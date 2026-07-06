"""Shared prompt tokenization for hook extensions.

Lifted from the memory-graph gate: any extension judging "is this prompt
significant?" or matching prompt words against a vocabulary needs the same
tokenizer, so it lives in the framework and HookContext exposes it lazily.
"""

import re

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "are", "this", "that", "it", "be", "can", "could", "would", "how", "what",
    "when", "i", "you", "we", "do", "does", "make", "get", "set", "use",
    "about", "did", "was", "were", "they", "them", "our", "your", "just", "some",
    # acknowledgement words: bare "thanks"/"yes"/"ok" must reduce to no terms
    "thanks", "thank", "yes", "yep", "ok", "okay", "sure", "no", "nope", "please",
}
_WORD = re.compile(r"[a-z0-9]+")


def terms_pos(text: str) -> list[tuple[int, str]]:
    """Meaningful words with their ORIGINAL positions: (index-in-full-token-
    stream, word). Positions let phrase matching tell 'memory graph' (adjacent)
    from 'memory of the whole graph' (four words apart) even after stopwords
    are stripped out of the sequence."""
    return [(i, w) for i, w in enumerate(_WORD.findall(text.lower()))
            if len(w) > 2 and w not in _STOP]


def terms(text: str) -> list[str]:
    """Meaningful words in `text`: lowercase, no stopwords, length > 2."""
    return [w for _, w in terms_pos(text)]


def bigrams(pos_terms: list[tuple[int, str]], gap: int = 2) -> set[tuple[str, str]]:
    """Nearby term pairs — 'memory graph' as a phrase is far stronger evidence
    than the two words scattered across a text. Pairs use ORIGINAL token
    positions, so words that only became neighbours after stopword-stripping
    don't count as a phrase. gap=2 allows one word between."""
    return {(a, b) for (i, a), (j, b) in zip(pos_terms, pos_terms[1:])
            if j - i <= gap}
