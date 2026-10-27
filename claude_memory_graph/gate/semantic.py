"""Meaning-level matching for the gate: static word embeddings.

The lexical gate matches words. It misses a prompt that describes the same
thing in other words ("the map still draws things we removed" for a memory
named "Tile cache poisoning after reindex"). This adds a second channel
that compares meanings.

The model is WordLlama (MIT): static token embeddings, 256 dimensions,
averaged per text (texts are split into words first).
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

import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

_WEIGHTS = "l2_supercat_256.safetensors"
_TOKENIZER = "l2_supercat_tokenizer_config.json"
_FIELD_CHARS = 300        # a long rationale is embedded by its opening

_encoder = None


def _package_dir() -> Path | None:
    try:
        import importlib.util
        spec = importlib.util.find_spec("wordllama")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    root = Path(spec.origin).parent
    if (root / "weights" / _WEIGHTS).exists() and (root / "tokenizers" / _TOKENIZER).exists():
        return root
    return None


def available() -> bool:
    try:
        import numpy  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return _package_dir() is not None


_WORD = re.compile(r"\w+")


class Encoder:
    """Texts are split into words, and each word's token ids are
    looked up in a cache kept in the state home. The tokenizer (~150ms to
    load) is only loaded for words the cache hasn't seen, so once a person's
    vocabulary is cached a prompt never pays for it."""

    def __init__(self):
        import numpy as np

        root = _package_dir()
        if root is None:
            raise RuntimeError("wordllama weights not installed")
        self.np = np
        self.root = root
        self._tokenizer = None
        self.weights = np.load(self._npy(root), mmap_mode="r")
        self.cache_path = self._npy(root).with_name("word-ids.json")
        try:
            self.word_ids: dict[str, list[int]] = json.loads(self.cache_path.read_text())
        except (OSError, ValueError):
            self.word_ids = {}
        self._new = False

    def _ids(self, words: list[str]) -> list[int]:
        missing = [w for w in dict.fromkeys(words) if w not in self.word_ids]
        if missing:
            if self._tokenizer is None:
                from tokenizers import Tokenizer
                self._tokenizer = Tokenizer.from_file(str(self.root / "tokenizers" / _TOKENIZER))
            # a bare word gets the word-initial "▁" pieces it has inside a
            # sentence; " word" would add a stray "▁" token to every word
            for word, enc in zip(missing, self._tokenizer.encode_batch(
                    missing, add_special_tokens=False)):
                self.word_ids[word] = [i for i in enc.ids if i < self.weights.shape[0]]
            self._new = True
        return [i for w in words for i in self.word_ids[w]]

    def save_cache(self) -> None:
        if not self._new:
            return
        try:
            tmp = self.cache_path.with_name(f"{self.cache_path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self.word_ids, separators=(",", ":")))
            tmp.replace(self.cache_path)
            self._new = False
        except OSError:
            pass

    @staticmethod
    def _npy(root: Path) -> Path:
        """The weights as float16 .npy, made once: memory-mapping it costs a
        hook ~1ms where parsing the safetensors file costs ~300ms."""
        import importlib.metadata
        from claude_memory_graph.hookcore import state_home

        version = importlib.metadata.version("wordllama")
        path = state_home() / "embeddings" / f"wordllama-{version}-256.npy"
        if not path.exists():
            import numpy as np
            from safetensors.numpy import load_file
            tensors = load_file(str(root / "weights" / _WEIGHTS))
            matrix = next(iter(tensors.values())).astype(np.float16)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp.npy")
            np.save(tmp, matrix)
            tmp.replace(path)
        return path

    def encode(self, texts: list[str]):
        """Unit vectors, one row per text (float32)."""
        np = self.np
        out = np.zeros((len(texts), self.weights.shape[1]), dtype=np.float32)
        split = [_WORD.findall(t or "") for t in texts]
        self._ids([w for words in split for w in words])     # one tokenizer pass
        for i, words in enumerate(split):
            ids = self._ids(words)
            if not ids:
                continue
            v = np.asarray(self.weights[ids], dtype=np.float32).mean(axis=0)
            norm = float(np.linalg.norm(v))
            if norm:
                out[i] = v / norm
        self.save_cache()
        return out


def encoder() -> Encoder:
    global _encoder
    if _encoder is None:
        _encoder = Encoder()
    return _encoder


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
