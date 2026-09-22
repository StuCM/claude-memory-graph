"""Hard capture rules, enforced at the write path.

The capture policy has two layers (see docs/CAPTURE.md): soft rules — what
deserves a node, naming conventions — live in the context/distill/ingest
protocols and are followed by the LLM; this module is the checkable subset
the server refuses to violate regardless of who is writing.
"""

import re

MAX_NAME_LENGTH = 120

# Names that carry no identity. Upsert-by-name makes the name the node's
# identity scheme, so a node called "notes" collides with every other
# unnamed thought and can never be recalled deliberately.
PLACEHOLDER_NAMES = {
    "misc",
    "miscellaneous",
    "note",
    "notes",
    "todo",
    "stuff",
    "temp",
    "tbd",
    "unknown",
    "untitled",
    "n/a",
    "none",
    "general",
    "other",
}

# Properties a node must carry at creation. Kept deliberately minimal: only
# the ones whose absence makes the node dead weight in every future recall.
REQUIRED_PROPERTIES: dict[str, tuple[str, ...]] = {
    "Decision": ("rationale",),
    "Pattern": ("description",),
}

_REQUIRED_HINTS = {
    "Decision": "a Decision without its rationale (the why) is unusable later",
    "Pattern": "a Pattern needs a description of the phenomenon and its fix or approach",
}

# Soft naming ceiling, in WORDS. `check_name`'s 120-character limit is the
# hard rule; it never fired in practice because a sentence fits inside it
# comfortably. Measured on a real 2010-node graph: Concept labels held the
# line at a median of 1 word (the skill gives them a concrete shape —
# "lowercase singular"), while Pattern/Decision/Preference names drifted to
# a median of 11-12 words because their rule was an abstraction ("a short,
# specific, stable title"). The cost is not cosmetic: every word of every
# name enters the retrieval vocabulary, so sentence-shaped names put `add`,
# `check`, `error`, `file`, `fix`, `run` and `test` into it, which is what
# made the grounding-coverage metric unable to tell signal from coincidence
# (docs/tasks/grounding-coverage-experiment.md).
#
# A WARNING, not a refusal: a name that is one word over is fine, and
# refusing a write would lose the knowledge rather than improve the name.
# The write path returns the warning so the writer can rename immediately.
NAME_WORD_SOFT_MAX = 6
CONCEPT_WORD_SOFT_MAX = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_name(name: str) -> str:
    """Collapse internal whitespace and trim."""
    return re.sub(r"\s+", " ", name).strip()


def check_name(name: str, kind: str = "name") -> str:
    """Validate a resource name / concept label; returns the normalized form."""
    norm = normalize_name(name)
    if not norm:
        raise ValueError(f"Empty {kind}")
    if len(norm) > MAX_NAME_LENGTH:
        raise ValueError(
            f"{kind.capitalize()} exceeds {MAX_NAME_LENGTH} characters — use a "
            "short stable title and put the detail in properties"
        )
    if norm.lower() in PLACEHOLDER_NAMES:
        raise ValueError(
            f"'{norm}' is a placeholder {kind} — the {kind} is the node's "
            "identity for upserts and recall, so use a specific, stable one"
        )
    return norm


def check_required_properties(model: str, properties: dict[str, str]) -> None:
    required = REQUIRED_PROPERTIES.get(model, ())
    missing = [k for k in required if not properties.get(k, "").strip()]
    if missing:
        raise ValueError(
            f"{model} requires the '{', '.join(missing)}' property: "
            f"{_REQUIRED_HINTS[model]}"
        )


def name_warning(model: str, name: str, kind: str = "name") -> str | None:
    """A nudge when a name has grown into a sentence, or None when it hasn't.

    Callers append this to their success message — the node is still written.
    """
    limit = CONCEPT_WORD_SOFT_MAX if kind == "label" else NAME_WORD_SOFT_MAX
    words = normalize_name(name).split()
    if len(words) <= limit:
        return None
    return (f" [naming] this {model} {kind} is {len(words)} words; aim for "
            f"{limit} or fewer. The {kind} is an identifier, not a summary — "
            "every word in it joins the retrieval vocabulary, so a sentence "
            "makes recall noisier for every other node. Move the detail into "
            "properties (description/rationale) and the phrasings into "
            "aliases, then rename.")


def _tokens(name: str) -> set[str]:
    return set(_TOKEN_RE.findall(name.lower()))


def names_similar(a: str, b: str) -> bool:
    """Near-duplicate test for node names.

    True on case/whitespace-insensitive equality, on one name's tokens being
    a subset of the other's (two-token minimum, so 'Use pyoxigraph' matches
    'Use pyoxigraph over rdflib' but 'pyoxigraph' alone matches nothing), or
    on strong token overlap.
    """
    if normalize_name(a).lower() == normalize_name(b).lower():
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 2 and small <= large:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.6
