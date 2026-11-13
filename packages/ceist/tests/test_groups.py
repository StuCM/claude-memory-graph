"""Group grounding: a phrase names one tile of a nodegroup ("burnt down"), its
clause fills the tile's other nodes, and the plan gets one OnTile.

    Clock Tower      Listed     phase: Destruction by Fire 1940
    Grain Warehouse  Grade II   phases: Destruction by Flood 1960 · Damage by Fire 1900
    Boat Shed        Candidate  no phases
"""

import subprocess

import arches_fixture as fx
import pytest
from fakes import FakeEncoder
from test_arches import _resolve, _tools

from ceist import DateRange, HasValue, Not, OnTile, Plan, config, interpret, narrate
from ceist.alizarin import Tiles, evaluate
from ceist.arches import ArchesVocabulary
from ceist.arches_search import compile_checked
from ceist.matching import Chain, Exact, Vectors
from ceist.readback import check
from ceist.rosmadair import compile_plan, read_back

BUNDLE = {"format": "ceist.vocab/2", "models": {"Building": {
    "nodes": {"construction_date": {"kind": "date"}},
    "entries": [{"phrases": ["built"], "kind": "date", "node": "construction_date"}],
    "groups": {"phase": {
        "phrases": ["phase"],
        "nodes": {"phase_type": {"role": "type"}, "phase_cause": {"role": "cause"},
                  "phase_date": {"role": "date"}},
        "combos": [{"phrases": ["burnt down", "destroyed by fire"], "node": "phase_date",
                    "set": {"phase_type": "Destruction", "phase_cause": "Fire"}},
                   {"phrases": ["damaged"], "node": "phase_date", "set": {"phase_type": "Damage"}},
                   {"phrases": ["destroyed"], "node": "phase_date",
                    "set": {"phase_type": "Destruction"}}],
        "answers": {"when": "phase_date"}}}}}}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("phases")
    return root, fx.write(root, phases=True)


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(data[0], bundle=BUNDLE)


@pytest.fixture(scope="module")
def snapshot(data, tmp_path_factory):
    emit = _tools()
    if not emit:
        pytest.skip("needs ros_madair bindings and ros-madair-emit (ROS_MADAIR_EMIT)")
    out = tmp_path_factory.mktemp("snapshot")
    subprocess.run([emit, str(data[0]), str(out)], check=True, capture_output=True)
    return out


def _value(data, field, label):
    return HasValue(field, data[1]["concepts"][label], label)


def _names(vocab, ids):
    return sorted(vocab.names[i] for i in ids)


def test_listed_buildings_damaged_in_a_fire_are_not_every_listed_building(vocab, data):
    m = interpret(vocab, "which listed buildings were damaged in a fire?")
    assert m.plan.where == [
        OnTile("phase", [_value(data, "phase_type", "Damage"), _value(data, "phase_cause", "Fire")]),
        _value(data, "heritage_status", "Listed")]
    # both are listed; only the warehouse has a Damage phase caused by Fire
    assert _names(vocab, evaluate(m.plan, Tiles(vocab))) == ["Grain Warehouse"]


def test_burnt_down_before_1950_is_one_tile_and_reads_back(vocab, data, snapshot):
    m = interpret(vocab, "which buildings were burnt down before 1950?")
    (tile,) = m.plan.where
    assert tile.group == "phase"
    assert tile.conditions[:2] == [_value(data, "phase_cause", "Fire"),
                                   _value(data, "phase_type", "Destruction")]
    date = tile.conditions[2]
    assert isinstance(date, DateRange) and date.field == "phase_date" and date.lo is None
    assert date.hi.startswith("1949")
    assert narrate(m.plan) == ("Find Buildings with one phase entry (whose phase cause is Fire "
                               "and whose phase type is Destruction and whose phase date is "
                               "before 1950).")
    compiled = compile_plan(m.plan, vocab)
    assert check(m.plan, read_back(compiled, vocab)).ok
    payload, verdict = compile_checked(m.plan, vocab, concept_operator="REFERENCES_ANY")
    assert verdict.ok and payload["scope"] == "TILE"
    tower = {data[1]["ids"]["tower"]}
    assert evaluate(m.plan, Tiles(vocab)) == tower
    assert _resolve(snapshot, vocab, compiled.query) == tower


def test_destruction_and_fire_on_different_tiles_do_not_match(vocab, data, snapshot):
    """The warehouse was destroyed (by flood) and damaged by fire: no one
    phase of it is a Destruction by Fire."""
    ids = data[1]["ids"]
    for q in ("which buildings were destroyed by fire?", "which buildings were destroyed in a fire?"):
        plan = interpret(vocab, q).plan
        assert isinstance(plan.where[0], OnTile), q
        assert evaluate(plan, Tiles(vocab)) == {ids["tower"]}, q
        assert _resolve(snapshot, vocab, compile_plan(plan, vocab).query) == {ids["tower"]}, q
    loose = Plan("Building", plan.where[0].conditions)
    assert evaluate(loose, Tiles(vocab)) == {ids["tower"], ids["warehouse"]}


def test_a_word_the_group_cant_place_refuses_rather_than_drops(vocab):
    m = interpret(vocab, "which buildings were damaged by lightning?")
    assert m.plan is None and "couldn't place 'lightning'" in m.refused


def test_one_condition_needs_no_tile(vocab, data):
    m = interpret(vocab, "which buildings were damaged?")
    assert m.plan.where == [_value(data, "phase_type", "Damage")]


def test_a_negated_group_is_no_such_tile(vocab, data):
    m = interpret(vocab, "which buildings were not burnt down?")
    (c,) = m.plan.where
    assert isinstance(c, Not) and isinstance(c.condition, OnTile)
    ids = data[1]["ids"]
    assert evaluate(m.plan, Tiles(vocab)) == {ids["warehouse"], ids["shed"]}


def test_a_date_another_word_picks_stays_out_of_the_tile(vocab):
    m = interpret(vocab, "which buildings damaged by fire were built before 1850?")
    tile, built = m.plan.where
    assert isinstance(tile, OnTile) and len(tile.conditions) == 2
    assert isinstance(built, DateRange) and built.field == "construction_date"


def test_the_matcher_finds_a_group_phrase_the_exact_pass_missed(vocab, data):
    exact = config.chain(config.load(None, layers=["exact"]))
    q = "which buildings were burnt-down before 1950?"
    assert interpret(vocab, q).plan is None                    # exact phrases only: refused
    m = interpret(vocab, q, matcher=exact)
    (tile,) = m.plan.where
    assert tile.group == "phase" and len(tile.conditions) == 3
    assert evaluate(m.plan, Tiles(vocab)) == {data[1]["ids"]["tower"]}


@pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")
def test_a_vector_near_miss_on_a_leftover_run_offers_rather_than_answers(vocab):
    # bge rates a run that names no tile as close to one (the responder set's "flood footprint" → muster points)
    class Loose(FakeEncoder):
        SAME = {**FakeEncoder.SAME, "footprint": "damaged"}
    m = interpret(vocab, "which buildings are in the storm footprint?",
                  matcher=Chain([Exact(), Vectors(Loose(), low=0.6)], clarify_min=0.0))
    assert m.plan is None and "did you mean" in m.refused
    assert m.grounding.suggestions == [("storm footprint", ["damaged (phase)"])]


def test_a_group_phrase_inside_a_hyphenated_word_names_nothing(vocab):
    m = interpret(vocab, "which buildings were half-damaged in 1900?")
    assert m.plan is None and m.refused.startswith("couldn't place 'damaged', 'half'")
