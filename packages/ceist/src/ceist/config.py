"""A project's matching configuration: which vocabulary, which layers, how sure.

    # ceist.toml
    [vocabulary]
    bundle = "vocab/her.bundle.json"      # built by `ceist vocab assemble`

    [matching]
    layers = ["exact", "vectors"]         # in order; drop one to turn it off

    [matching.exact]
    roots = true                          # built / build / building (simplemma if installed)
    direction = true                      # "from" never matches "to"

    [matching.vectors]
    model = "wordllama-256"               # or "bge-small-en-v1.5" (ceist.onnx): reads a
                                          #   phrase whole; right more often on HER
    min = 0.6                             # default: the model's own (MODEL_THRESHOLDS)
    gap = 0.08
    # model_dir = "models/bge-small"      # weights somewhere other than the cache

    [matching.fallback]
    chooser = "host"                      # host: offer "did you mean" to the caller
                                          #   (a person, or Claude via memory_ask)
                                          # none: refuse when unsure
    clarify_top = 3
    clarify_min = 0.15                    # lower: more "did you mean"; also on unanswerable questions

Every key is optional; the defaults are the ones the HER evaluation supports.
A layer that can't run here (vectors without the wordllama package, or a
transformer whose weights aren't fetched) is left out with a note, never
silently replaced.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .matching import Chain, Exact, Vectors

WORDLLAMA = "wordllama-256"
MODEL_THRESHOLDS = {WORDLLAMA: (0.6, 0.08)}     # transformers: ceist.onnx.MODELS
CHOOSERS = {"host", "none"}
PLANNED_CHOOSERS = {"local-llm", "api"}      # designed for; not built yet


@dataclass
class Config:
    bundle: Path | None = None
    layers: list[str] = field(default_factory=lambda: ["exact", "vectors"])
    roots: bool = False
    direction: bool = True
    model: str = WORDLLAMA
    model_dir: Path | None = None
    low: float | None = None          # None: the model's own threshold
    gap: float | None = None
    chooser: str = "host"
    clarify_top: int = 3
    clarify_min: float = 0.15
    notes: list[str] = field(default_factory=list)


def load(path: str | Path | None = None, **overrides) -> Config:
    cfg = Config()
    if path:
        path = Path(path)
        raw = tomllib.loads(path.read_text())
        voc, m = raw.get("vocabulary", {}), raw.get("matching", {})
        if voc.get("bundle"):
            cfg.bundle = (path.parent / voc["bundle"]).resolve()
        cfg.layers = list(m.get("layers", cfg.layers))
        ex, ve, fb = m.get("exact", {}), m.get("vectors", {}), m.get("fallback", {})
        cfg.roots = bool(ex.get("roots", cfg.roots))
        cfg.direction = bool(ex.get("direction", cfg.direction))
        cfg.model = ve.get("model", cfg.model)
        if ve.get("model_dir"):
            cfg.model_dir = (path.parent / ve["model_dir"]).resolve()
        if "min" in ve:
            cfg.low = float(ve["min"])
        if "gap" in ve:
            cfg.gap = float(ve["gap"])
        cfg.chooser = fb.get("chooser", cfg.chooser)
        cfg.clarify_top = int(fb.get("clarify_top", cfg.clarify_top))
        cfg.clarify_min = float(fb.get("clarify_min", cfg.clarify_min))
    for k, v in overrides.items():
        setattr(cfg, k, v)
    unknown = set(cfg.layers) - {"exact", "vectors"}
    if unknown:
        raise ValueError(f"unknown matching layers: {', '.join(sorted(unknown))}")
    if cfg.chooser in PLANNED_CHOOSERS:
        raise ValueError(f"chooser '{cfg.chooser}' is designed for but not built yet; "
                         f"use one of {', '.join(sorted(CHOOSERS))}")
    if cfg.chooser not in CHOOSERS:
        raise ValueError(f"unknown chooser '{cfg.chooser}'")
    from .onnx import MODELS
    known = {WORDLLAMA: MODEL_THRESHOLDS[WORDLLAMA],
             **{n: (m["min"], m["gap"]) for n, m in MODELS.items()}}
    if cfg.model not in known:
        raise ValueError(f"unknown vectors model '{cfg.model}' (available: {', '.join(known)})")
    low, gap = known[cfg.model]
    cfg.low = low if cfg.low is None else cfg.low
    cfg.gap = gap if cfg.gap is None else cfg.gap
    return cfg


def chain(cfg: Config, cache_dir: str | Path | None = None, encoder=None) -> Chain:
    """The matcher chain a config describes. `encoder` overrides the vectors
    encoder (the memory graph passes its own, cached in its state home)."""
    layers = []
    for name in cfg.layers:
        if name == "exact":
            layers.append(Exact(roots=cfg.roots, direction=cfg.direction))
        elif name == "vectors":
            if encoder is None:
                encoder = _encoder(cfg, cache_dir)
                if encoder is None:
                    continue
            layers.append(Vectors(encoder, cfg.low, cfg.gap, cfg.direction))
    top = cfg.clarify_top if cfg.chooser == "host" else 0
    return Chain(layers, clarify_top=top, clarify_min=cfg.clarify_min)


def _encoder(cfg: Config, cache_dir):
    """The vectors layer's encoder, or None with a note saying why not."""
    if cfg.model == WORDLLAMA:
        from . import vectors
        if not vectors.available():
            cfg.notes.append("vectors layer off: wordllama not installed "
                             "(pip install ceist[vectors])")
            return None
        return vectors.encoder(cache_dir)
    from . import onnx
    why = onnx.missing(cfg.model, cache_dir, cfg.model_dir)
    if why:
        cfg.notes.append(f"vectors layer off: {cfg.model}: {why}")
        return None
    return onnx.encoder(cfg.model, cache_dir, cfg.model_dir)

