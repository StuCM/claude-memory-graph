"""Transformer models in the vectors layer (ceist.onnx): chosen by config,
their own thresholds, left out with a note when they can't run, and every
vector made kept on disk."""

import json

import pytest

from ceist import config, onnx
from ceist.evaluate import evaluate
from ceist.matching import Item, Vectors


def test_config_picks_the_model_and_its_thresholds(tmp_path):
    cfg = config.load(None, model="bge-small-en-v1.5")
    assert (cfg.low, cfg.gap) == (onnx.MODELS["bge-small-en-v1.5"]["min"],
                                  onnx.MODELS["bge-small-en-v1.5"]["gap"])
    assert (config.load(None).low, config.load(None).gap) == config.MODEL_THRESHOLDS["wordllama-256"]
    p = tmp_path / "ceist.toml"
    p.write_text('[matching.vectors]\nmodel = "bge-small-en-v1.5"\nmin = 0.5\n'
                 'model_dir = "weights"\n')
    cfg = config.load(p)
    assert cfg.low == 0.5 and cfg.gap == onnx.MODELS["bge-small-en-v1.5"]["gap"]
    assert cfg.model_dir == tmp_path / "weights"
    with pytest.raises(ValueError, match="unknown vectors model"):
        config.load(None, model="gpt-9")


def test_without_weights_the_layer_is_left_out_with_a_note(tmp_path):
    cfg = config.load(None, model="bge-small-en-v1.5")
    chain = config.chain(cfg, cache_dir=tmp_path / "empty-cache")
    assert [type(x).__name__ for x in chain.layers] == ["Exact"]
    assert any("bge-small-en-v1.5" in n and ("fetch" in n or "install" in n) for n in cfg.notes)
    assert "unknown model" in onnx.missing("nope")


def test_eval_halves_split_the_questions(tmp_path):
    from test_bundle import project                  # the tiny project those tests build
    from ceist.cli import main
    p = project(tmp_path)
    assert main(["vocab", "assemble", str(p / "desc"), str(p / "vocab"), "-o", str(p / "b.json"),
                 "--graphs", str(p / "graphs")]) == 0
    b, cases = p / "b.json", p / "cases.json"
    n = len(json.loads(cases.read_text())["cases"])
    exact = config.load(None, layers=["exact"])
    even, odd = (evaluate(b, cases, exact, half=h) for h in ("even", "odd"))
    assert even.n_match + even.n_none + odd.n_match + odd.n_none == n
    assert even.n_match + even.n_none == (n + 1) // 2


weights = onnx.missing("bge-small-en-v1.5")
needs_bge = pytest.mark.skipif(weights is not None, reason=f"bge-small: {weights}")


@needs_bge
def test_bge_reads_a_phrase_whole_and_caches_what_it_made(tmp_path):
    from ceist.vectors import default_cache_dir
    import shutil
    cache = tmp_path / "cache"
    shutil.copytree(onnx.model_dir("bge-small-en-v1.5"), onnx.model_dir("bge-small-en-v1.5", cache))
    enc = onnx.OnnxEncoder("bge-small-en-v1.5", cache)
    v = enc.encode(["pulled down", "demolished", "designed by"])
    assert v.shape == (3, 384) and abs(float((v[0] ** 2).sum()) - 1) < 1e-3
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])         # meaning, not shared words
    again = onnx.OnnxEncoder("bge-small-en-v1.5", cache)    # a new process
    assert again._get("pulled down") is not None             # from the cache, not the model
    layer = Vectors(again, low=0.3, gap=0.1)
    gone = Item("demolition", ("demolished", "knocked down"), "Demolition Date")
    built = Item("construction", ("built", "constructed"), "Construction Date")
    assert layer.decide("pulled down", [gone, built]).item is gone
    assert default_cache_dir() != cache
