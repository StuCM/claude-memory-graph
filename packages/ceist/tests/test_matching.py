"""The matcher chain: layers, the order they decide in, and "did you mean"."""

import numpy as np
import pytest

from ceist import config
from ceist.matching import Ambiguous, Chain, Exact, Item, Match, NoMatch, Vectors


class FakeEncoder:
    """Deterministic vectors: each word a fixed direction; similar words share one."""
    SAME = {"erected": "built", "constructed": "built", "raised": "built",
            "demolished": "destroyed", "flattened": "destroyed"}

    def encode(self, texts):
        out = []
        for t in texts:
            v = np.zeros(64)
            for w in t.lower().split():
                w = self.SAME.get(w, w)
                v[hash(w) % 64] += 1
            out.append(v / (np.linalg.norm(v) or 1))
        return np.array(out)


BUILT = Item("construction", ("built", "construction"), "construction date")
GONE = Item("demolition", ("destroyed", "demolition"), "demolition date")
FROM = Item("departure", ("sailing from", "departed from"), "place of departure")
TO = Item("destination", ("sailing to", "bound for"), "destination")


def test_exact_equal_and_covering():
    ex = Exact()
    assert isinstance(ex.decide("built", [BUILT, GONE]), Match)
    # "metal" must not claim a long phrase it's only a small part of
    metal = Item("material", ("metal",), "material")
    assert isinstance(ex.decide("turned up by metal detectorists", [metal]), NoMatch)
    both = Item("other", ("built",), "other")
    assert isinstance(ex.decide("built", [BUILT, both]), Ambiguous)


def test_exact_roots_and_direction():
    assert isinstance(Exact().decide("builds", [Item("b", ("build",))]), NoMatch)
    assert isinstance(Exact(roots=True).decide("building", [Item("b", ("build",))]), Match)
    m = Exact().decide("sailing from", [FROM, TO])
    assert isinstance(m, Match) and m.item is FROM
    # a "from" phrase never matches a "to" phrasing, even partly
    assert isinstance(Exact().decide("sailing from", [TO]), NoMatch)


def test_vectors_threshold_gap_and_direction():
    v = Vectors(FakeEncoder(), low=0.6, gap=0.08)
    m = v.decide("erected", [BUILT, GONE])
    assert isinstance(m, Match) and m.item is BUILT
    assert isinstance(v.decide("painted", [BUILT, GONE]), NoMatch)
    twin = Item("twin", ("built",), "twin")
    assert isinstance(v.decide("erected", [BUILT, twin]), Ambiguous)


def test_chain_order_and_clarify():
    chain = Chain([Exact(), Vectors(FakeEncoder(), low=0.6)], clarify_top=2, clarify_min=0.0)
    r = chain.resolve("built", [BUILT, GONE])
    assert r.match.layer == "exact"
    r = chain.resolve("erected", [BUILT, GONE])
    assert r.match.layer == "vectors" and r.match.item is BUILT and "vectors" in r.notes[0]
    r = chain.resolve("painted", [BUILT, GONE])
    assert r.match is None and len(r.options) == 2          # did you mean …
    quiet = Chain([Exact(), Vectors(FakeEncoder(), low=0.6)], clarify_top=0)
    assert quiet.resolve("painted", [BUILT, GONE]).options == []


def test_config(tmp_path):
    p = tmp_path / "ceist.toml"
    p.write_text('[vocabulary]\nbundle = "v.json"\n[matching]\nlayers = ["exact"]\n'
                 '[matching.exact]\nroots = true\n[matching.fallback]\nchooser = "none"\n')
    cfg = config.load(p)
    assert cfg.bundle == tmp_path / "v.json" and cfg.layers == ["exact"] and cfg.roots
    ch = config.chain(cfg)
    assert [type(x).__name__ for x in ch.layers] == ["Exact"] and ch.clarify_top == 0
    with pytest.raises(ValueError, match="not built yet"):
        config.load(None, chooser="local-llm")
    with pytest.raises(ValueError, match="unknown matching layers"):
        config.load(None, layers=["exact", "magic"])
    ch = config.chain(config.load(None), encoder=FakeEncoder())
    assert [type(x).__name__ for x in ch.layers] == ["Exact", "Vectors"]
