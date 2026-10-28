"""Meaning-level matching for the gate: static word embeddings.

The lexical gate matches words. It misses a prompt that describes the same
thing in other words ("the map still draws things we removed" for a memory
named "Tile cache poisoning after reindex"). This adds a second channel
that compares meanings.

The model is WordLlama (MIT): static token embeddings, 256 dimensions,
averaged per text (texts are split into words first). The encoder is
ceist.vectors, shared with the question planner.
Unlike a transformer it needs no torch and no GPU, and
a text encodes in under a millisecond. Its weights ship inside the PyPI
package, so nothing is downloaded at runtime. They are converted once to a
float16 .npy in the state home and memory-mapped, so a hook process pays
~1ms for them plus ~100ms to load the tokenizer.

Each memory is embedded field by field — its name, each property value,
each alias — and scores by its best field. A memory's aliases are written
in the words someone uses when they hit the problem again, so the best
field is usually the one that matches a paraphrase; averaging everything
into one vector diluted exactly that signal.

Fail open: if the package or numpy is missing, available() is False and
the gate is lexical-only, as before.
"""

import logging

# the encoder itself lives in ceist (packages/ceist/src/ceist/vectors.py),
# shared with the question planner; the memory graph keeps its cache in the
# state home
from ceist.vectors import Encoder, available  # noqa: F401

log = logging.getLogger(__name__)

_FIELD_CHARS = 300        # a long rationale is embedded by its opening


def encoder() -> Encoder:
    from ceist.vectors import encoder as _shared
    from claude_memory_graph.hookcore import state_home
    return _shared(state_home() / "embeddings")


def doc_fields(doc: dict) -> list[str]:
    """What a memory is embedded as: its name, each property value, and each
    alias on its own (aliases are comma lists of phrasings)."""
    fields = [doc.get("name") or ""]
    for key, value in doc.get("parts", ()):
        value = " ".join(str(value).split())
        if not value:
            continue
        if key == "aliases":
            fields += [a.strip() for a in value.split(",") if a.strip()]
        else:
            fields.append(value[:_FIELD_CHARS])
    return [f for f in dict.fromkeys(fields) if f]


def build_index(docs: list[dict]) -> dict | None:
    """Field vectors for every doc: {"vectors": float16 (fields x 256),
    "owner": doc index per row}. None when embeddings are unavailable."""
    if not docs or not available():
        return None
    np = encoder().np
    texts, owner = [], []
    for i, doc in enumerate(docs):
        for field in doc_fields(doc):
            texts.append(field)
            owner.append(i)
    vectors = encoder().encode(texts).astype(np.float16)
    return {"vectors": vectors, "owner": np.asarray(owner, dtype=np.int32)}


def rank(index: dict, prompt: str, n_docs: int) -> list[tuple[float, int]]:
    """(best-field cosine, doc index) for every doc, best first."""
    np = encoder().np
    query = encoder().encode([prompt])[0]
    sims = index["vectors"].astype(np.float32) @ query
    best = np.full(n_docs, -1.0, dtype=np.float32)
    np.maximum.at(best, index["owner"], sims)
    order = np.argsort(-best)
    return [(float(best[i]), int(i)) for i in order]
