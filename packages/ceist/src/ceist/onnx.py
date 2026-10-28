"""Small sentence-embedding transformers (ONNX) for the "vectors" layer:
meaning-level matching that reads a phrase as a whole, where WordLlama
averages its words.

    [matching.vectors]
    model = "bge-small-en-v1.5"

On the HER evaluation, bge-small beside the vocabulary is right more often
than WordLlama at the same safety (bench/README.md, "Browser models,
measured"). The weights are the int8 ONNX files transformers.js loads, so a
browser page can run the same model; here onnxruntime runs them
(`pip install ceist[onnx]`).

The weights are fetched once (`ceist vectors fetch bge-small-en-v1.5`, about
34 MB from huggingface.co) into the cache folder. Unlike WordLlama's lookup,
each new text costs a model run (milliseconds), so every vector made is kept
in the same folder and a vocabulary is embedded once:
`ceist vectors embed <bundle>` does it ahead of time.

Fail open: available() is False without the runtime or the weights, and
the vectors layer is left out with a note saying why.
"""

import json
import os
import urllib.request
from pathlib import Path

from .vectors import default_cache_dir

# name → where the weights come from, how a text becomes one vector, and the
# thresholds the HER evaluation supports for it (tuned on half the questions,
# reported on the other half: bench/her_tune.py)
MODELS = {
    # HER: 40/49 right, 1 dangerous on the held-out half; 86/102, 2 on all
    "bge-small-en-v1.5": {"repo": "Xenova/bge-small-en-v1.5", "pooling": "cls",
                          "min": 0.3, "gap": 0.10, "size": "34 MB"},
    # HER: 43/49 right but 3 dangerous held out; 89/102, 4 on all — not the default
    "all-minilm-l6-v2": {"repo": "Xenova/all-MiniLM-L6-v2", "pooling": "mean",
                         "min": 0.3, "gap": 0.10, "size": "23 MB"},
}
_FILES = {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
MAX_TOKENS = 64          # vocabulary phrasings and question phrases are short
BATCH = 64


def model_dir(name: str, cache_dir: str | Path | None = None) -> Path:
    return Path(cache_dir or default_cache_dir()) / "models" / name


def _runtime() -> bool:
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return True


def missing(name: str, cache_dir: str | Path | None = None,
            folder: str | Path | None = None) -> str | None:
    """Why this model can't run here, or None when it can."""
    if name not in MODELS:
        return f"unknown model '{name}' (known: {', '.join(MODELS)})"
    if not _runtime():
        return "onnxruntime/tokenizers not installed (pip install ceist[onnx])"
    root = Path(folder) if folder else model_dir(name, cache_dir)
    if not all((root / f).exists() for f in _FILES):
        return f"weights not fetched (ceist vectors fetch {name})"
    return None


def fetch(name: str, cache_dir: str | Path | None = None) -> Path:
    """Download the model's weights and tokenizer once; returns the folder."""
    spec = MODELS[name]
    root = model_dir(name, cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    for local, remote in _FILES.items():
        dest = root / local
        if dest.exists():
            continue
        url = f"https://huggingface.co/{spec['repo']}/resolve/main/{remote}"
        tmp = dest.with_name(f"{dest.name}.{os.getpid()}.part")
        with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        tmp.replace(dest)
    return root


class OnnxEncoder:
    """Unit vectors for texts, from a small transformer; every vector made is
    kept in `cache_dir` (vectors-<model>.npy + .json), so a text is only ever
    run through the model once."""

    def __init__(self, name: str, cache_dir: str | Path | None = None,
                 folder: str | Path | None = None):
        why = missing(name, cache_dir, folder)
        if why:
            raise RuntimeError(why)
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np, self.name = np, name
        self.pooling = MODELS[name]["pooling"]
        root = Path(folder) if folder else model_dir(name, cache_dir)
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tok.enable_truncation(MAX_TOKENS)
        self.tok.enable_padding()
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.sess = ort.InferenceSession(str(root / "model.onnx"), opts,
                                         providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        base = Path(cache_dir or default_cache_dir())
        self._npy, self._idx = base / f"vectors-{name}.npy", base / f"vectors-{name}.json"
        self._known: dict[str, int] = {}
        self._rows = None
        try:
            texts = json.loads(self._idx.read_text())
            rows = np.load(self._npy)
            if len(texts) == len(rows):
                self._known = {t: i for i, t in enumerate(texts)}
                self._rows = rows.astype(np.float32)
        except (OSError, ValueError):
            pass
        self._new: dict[str, object] = {}

    def _run(self, texts: list[str]):
        np = self.np
        encs = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.array([e.type_ids for e in encs], dtype=np.int64)
        hidden = self.sess.run(None, feed)[0]                  # batch × tokens × dim
        if self.pooling == "cls":
            v = hidden[:, 0]
        else:
            m = mask[:, :, None].astype(np.float32)
            v = (hidden * m).sum(1) / np.maximum(m.sum(1), 1)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def _get(self, text: str):
        if text in self._new:
            return self._new[text]
        i = self._known.get(text)
        return self._rows[i] if i is not None else None

    def encode(self, texts: list[str]):
        """Unit vectors, one row per text (float32)."""
        np = self.np
        texts = [t or "" for t in texts]
        todo = [t for t in dict.fromkeys(texts) if self._get(t) is None]
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            for t, v in zip(chunk, self._run(chunk)):
                self._new[t] = v.astype(np.float32)
        if todo:
            self.save_cache()
        dim = self.sess.get_outputs()[0].shape[-1] or 384
        out = [self._get(t) for t in texts]
        return np.stack(out) if out else np.zeros((0, dim), dtype=np.float32)

    def save_cache(self) -> None:
        """Fold the new vectors into the cache files. Fail open."""
        if not self._new:
            return
        np = self.np
        texts = list(self._known) + list(self._new)
        rows = [self._rows] if self._rows is not None else []
        rows.append(np.stack(list(self._new.values())))
        matrix = np.concatenate(rows)
        try:
            self._npy.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._npy.with_name(f"{self._npy.stem}.{os.getpid()}.tmp.npy")
            np.save(tmp, matrix.astype(np.float16))
            tmp.replace(self._npy)
            tmpj = self._idx.with_name(f"{self._idx.name}.{os.getpid()}.tmp")
            tmpj.write_text(json.dumps(texts, separators=(",", ":")))
            tmpj.replace(self._idx)
        except OSError:
            return
        self._known = {t: i for i, t in enumerate(texts)}
        self._rows, self._new = matrix, {}


_shared: dict[tuple, OnnxEncoder] = {}


def encoder(name: str, cache_dir: str | Path | None = None,
            folder: str | Path | None = None) -> OnnxEncoder:
    """One encoder per model and cache folder, per process."""
    key = (name, str(cache_dir or default_cache_dir()), str(folder or ""))
    if key not in _shared:
        _shared[key] = OnnxEncoder(name, cache_dir, folder)
    return _shared[key]
