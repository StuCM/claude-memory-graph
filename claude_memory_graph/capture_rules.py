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
