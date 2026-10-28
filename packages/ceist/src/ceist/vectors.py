"""Static word vectors (WordLlama, MIT): meaning-level matching with no model
at query time.

A text's vector is the average of its words' token rows in a 256-wide table,
normalised. It needs no torch and no GPU, a text encodes in well under a
millisecond, and the same table ships to a browser as a plain array. The
weights come inside the `wordllama` PyPI package (`pip install
ceist[vectors]`); they are converted once to a float16 .npy in `cache_dir`
and memory-mapped, so a process pays ~1 ms for them.

Words are split first and each word's token ids are cached in `cache_dir`,
so the tokenizer (~150 ms to load) is only loaded for words not seen before.

Fail open: available() is False when the package or numpy is missing, and
callers fall back to exact matching.
"""

import json
import os
import re
from pathlib import Path

_WEIGHTS = "l2_supercat_256.safetensors"
_TOKENIZER = "l2_supercat_tokenizer_config.json"
_WORD = re.compile(r"\w+")


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "ceist"


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


class Encoder:
    """Unit vectors for texts. `cache_dir` holds the converted weights and the
    word → token-id cache."""

    def __init__(self, cache_dir: str | Path | None = None):
        import numpy as np

        root = _package_dir()
        if root is None:
            raise RuntimeError("wordllama weights not installed (pip install ceist[vectors])")
        self.np = np
        self.root = root
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self._tokenizer = None
        self.weights = np.load(self._npy(), mmap_mode="r")
        self.cache_path = self._npy().with_name("word-ids.json")
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

    def _npy(self) -> Path:
        """The weights as float16 .npy, made once: memory-mapping it costs
        ~1 ms where parsing the safetensors file costs ~300 ms."""
        import importlib.metadata

        version = importlib.metadata.version("wordllama")
        path = self.cache_dir / f"wordllama-{version}-256.npy"
        if not path.exists():
            import numpy as np
            from safetensors.numpy import load_file
            tensors = load_file(str(self.root / "weights" / _WEIGHTS))
            matrix = next(iter(tensors.values())).astype(np.float16)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + f".{os.getpid()}.tmp.npy")
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


_shared: dict[str, Encoder] = {}


def encoder(cache_dir: str | Path | None = None) -> Encoder:
    """One encoder per cache folder, per process."""
    key = str(cache_dir or default_cache_dir())
    if key not in _shared:
        _shared[key] = Encoder(cache_dir)
    return _shared[key]
