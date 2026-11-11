"""Numeric comparisons: the grammar, the field a number belongs to, units, the plan,
Rós Madair's range, read-back, and the in-memory evaluator."""

import os
import shutil
import subprocess

import arches_fixture as fx
import pytest

from ceist import AnyOf, DateRange, NumberRange, interpret, narrate, numbers
from ceist.alizarin import Tiles, evaluate
from ceist.arches import ArchesVocabulary
from ceist.plan import Near
from ceist.readback import check
from ceist.rosmadair import compile_plan, read_back


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("numbers")
    fx.write(root, places=True, numbers=True)
    return root


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(data, date_forms={"construction_date": ["built"]})


@pytest.fixture(scope="module")
def tiles(vocab):
    return Tiles(vocab)


def names(vocab, tiles, question) -> list[str]:
    m = interpret(vocab, question)
    assert m.plan is not None, m.refused
    return sorted(vocab.names[i] for i in evaluate(m.plan, tiles))


@pytest.mark.parametrize("phrase, lo, hi, lo_inclusive, hi_inclusive", [
    ("over 200", 200, None, False, True),
    ("more than 200", 200, None, False, True),
    ("taller than 30 metres", 30, None, False, True),
    ("exceeding 1,500", 1500, None, False, True),
    ("under 10", None, 10, True, False),
    ("fewer than 10", None, 10, True, False),
    ("at least 200", 200, None, True, True),
    ("no less than 200", 200, None, True, True),
    ("room for 200", 200, None, True, True),
    ("at most 5", None, 5, True, True),
    ("no more than 5", None, 5, True, True),
    ("up to 5", None, 5, True, True),
    ("between 10 and 30 metres", 10, 30, True, True),
    ("exactly 12.5", 12.5, 12.5, True, True),
])
def test_comparison_words_and_their_bounds(phrase, lo, hi, lo_inclusive, hi_inclusive):
    (m,) = numbers.find(f"buildings {phrase}", [])
    assert (m.lo, m.hi, m.lo_inclusive, m.hi_inclusive) == (lo, hi, lo_inclusive, hi_inclusive)


@pytest.mark.parametrize("lo, hi, lo_inclusive, hi_inclusive, unit, said", [
    (200, None, False, True, "", "more than 200"),
    (200, None, True, True, "", "at least 200"),
    (None, 10, True, False, "m", "less than 10 metres"),
    (None, 5, True, True, "", "at most 5"),
    (10, 30, True, True, "m", "between 10 and 30 metres (inclusive)"),
    (30, 30, True, True, "", "exactly 30"),
    (10, 30, False, True, "", "more than 10 and at most 30"),
])
def test_the_narration_says_the_bound(lo, hi, lo_inclusive, hi_inclusive, unit, said):
    assert numbers.label(lo, hi, lo_inclusive, hi_inclusive, unit) == said


@pytest.mark.parametrize("text, unit", [
    ("Height (m)", "m"), ("height m", "m"), ("Length in feet", "ft"), ("Occupant capacity", "count"),
    ("Insured value", "money"), ("Primary Reference Number", ""), ("Area (sq m)", ""),
    ("Price per metre", ""),
])
def test_a_fields_unit_is_read_never_guessed(text, unit):
    assert numbers.field_unit(text) == unit


def test_number_fields_from_the_graph(vocab):
    fields = {f.field: f for f in vocab.number_fields()}
    assert set(fields) == {"height_m", "capacity", "insured_value"}
    assert (fields["height_m"].label, fields["height_m"].unit) == ("height", "m")
    assert "height" in fields["height_m"].forms and "capacity" in fields["capacity"].forms
    assert fields["insured_value"].unit == "money" and fields["capacity"].unit == "count"


def test_strict_bounds_leave_out_the_value_on_the_bound(vocab, tiles):
    # the Clock Tower is exactly 30 m: aonach counted it as taller than 30 m
    assert names(vocab, tiles, "which buildings are taller than 30 metres?") == ["Boat Shed"]
    assert names(vocab, tiles, "buildings at least 30 metres tall") == ["Boat Shed", "Clock Tower"]
    assert names(vocab, tiles, "buildings shorter than 30 metres") == ["Grain Warehouse"]
    assert names(vocab, tiles, "buildings with capacity over 200") == ["Grain Warehouse"]
    assert names(vocab, tiles, "buildings with room for 200") == ["Clock Tower", "Grain Warehouse"]


def test_between_is_inclusive_at_both_ends(vocab, tiles):
    m = interpret(vocab, "buildings with height between 12.5 and 30 metres")
    assert narrate(m.plan) == ("Find Buildings whose height is between 12.5 and 30 metres "
                               "(inclusive).")
    assert names(vocab, tiles, "buildings with height between 12.5 and 30 metres") == [
        "Clock Tower", "Grain Warehouse"]


def test_units_and_money_convert_to_the_fields_unit(vocab, tiles):
    m = interpret(vocab, "buildings taller than 100 feet")
    assert m.plan.where == [NumberRange("height_m", 30.48, None, False, True, "height", "m")]
    assert names(vocab, tiles, "buildings worth at least 5 crore") == ["Clock Tower"]
    assert names(vocab, tiles, "buildings with an insured value of at least 5 crore") == [
        "Clock Tower"]
    assert names(vocab, tiles, "buildings worth more than 5 crore") == []
    assert names(vocab, tiles, "buildings worth more than 20 lakh") == [
        "Clock Tower", "Grain Warehouse"]


def test_negation_is_the_complement(vocab, tiles):
    m = interpret(vocab, "buildings with capacity not more than 200")
    assert narrate(m.plan) == "Find Buildings whose occupant capacity is at most 200."
    assert names(vocab, tiles, "buildings with capacity not more than 200") == [
        "Boat Shed", "Clock Tower"]
    m = interpret(vocab, "buildings with capacity not between 100 and 300")
    assert isinstance(m.plan.where[0], AnyOf)
    assert names(vocab, tiles, "buildings with capacity not between 100 and 300") == [
        "Boat Shed", "Grain Warehouse"]


@pytest.mark.parametrize("question, why", [
    ("buildings with insured value over 30 metres",
     "'over 30 metres' is a length, but the insured value of Building is an amount of money"),
    ("buildings worth over 30 metres", "says both an amount of money and a length"),
    ("buildings with capacity taller than 3", "is a height, and the occupant capacity isn't"),
])
def test_a_unit_that_doesnt_fit_the_field_refuses(vocab, question, why):
    m = interpret(vocab, question)
    assert m.plan is None and why in m.refused


def test_several_number_fields_and_no_cue_ask_which(vocab):
    m = interpret(vocab, "buildings over 200")
    assert m.plan is None
    assert "could be the height or the occupant capacity or the insured value" in m.refused
    assert "did you mean height over 200 or occupant capacity over 200" in m.refused


def test_a_distance_stays_a_distance(vocab):
    m = interpret(vocab, "buildings within 2 km of Clock Tower")
    assert [type(c) for c in m.plan.where] == [Near] and m.plan.where[0].km == 2


def test_a_year_with_a_date_word_stays_a_date(vocab):
    m = interpret(vocab, "buildings built before 1900")
    assert m.plan.where == [DateRange("construction_date", None, "1899-12-31",
                                      "construction date")]


def test_a_year_shaped_number_after_a_comparison_word_is_a_number(vocab):
    m = interpret(vocab, "buildings with capacity over 1900")
    assert m.plan.where == [NumberRange("capacity", 1900, None, False, True,
                                        "occupant capacity", "count")]


def test_a_count_of_linked_records_is_not_a_field(vocab):
    m = interpret(vocab, "buildings with more than 2 sites")
    assert m.plan is None and not m.grounding.numbers


def test_strict_wiring_reads_numbers_too(vocab):
    m = interpret(vocab, "which buildings have a capacity over 200?", assembly="strict")
    assert narrate(m.plan) == "Find Buildings whose occupant capacity is more than 200."


# ── Rós Madair: range is inclusive, fixed point at 6 places ──────────────

@pytest.mark.parametrize("question, lo, hi", [
    ("buildings taller than 30 metres", 30_000_001, 2 ** 63 - 1),
    ("buildings at least 30 metres tall", 30_000_000, 2 ** 63 - 1),
    ("buildings shorter than 30 metres", -2 ** 63, 29_999_999),
    ("buildings with height between 12.5 and 30 metres", 12_500_000, 30_000_000),
    ("buildings with height over 12.5", 12_500_001, 2 ** 63 - 1),
])
def test_strict_bounds_compile_one_step_in(vocab, question, lo, hi):
    m = interpret(vocab, question)
    c = compile_plan(m.plan, vocab)
    assert c.query["where"] == {"range": {"path": "height_m", "lo": lo, "hi": hi}}
    assert check(m.plan, read_back(c, vocab)).ok


def test_read_back_catches_a_strict_bound_compiled_inclusive(vocab, monkeypatch):
    import ceist.rosmadair as rm
    m = interpret(vocab, "buildings taller than 30 metres")
    monkeypatch.setattr(rm, "_quantize", lambda v, scale, real=rm._quantize: real(v, scale) - 1)
    said = check(m.plan, read_back(compile_plan(m.plan, vocab), vocab))
    assert not said.ok and "at least 30" in said.said and "more than 30" in said.meant


@pytest.fixture(scope="module")
def snapshot(data, tmp_path_factory):
    emit = os.environ.get("ROS_MADAIR_EMIT") or shutil.which("ros-madair-emit")
    try:
        import ros_madair  # noqa: F401
    except ImportError:
        emit = None
    if not emit:
        pytest.skip("needs ros_madair bindings and ros-madair-emit (ROS_MADAIR_EMIT)")
    out = tmp_path_factory.mktemp("snapshot")
    subprocess.run([emit, str(data), str(out)], check=True, capture_output=True)
    return out


@pytest.mark.parametrize("question, expect, absent", [
    ("which buildings are taller than 30 metres?", ["Boat Shed"], ["Clock Tower", "Grain"]),
    ("buildings at least 30 metres tall", ["Boat Shed", "Clock Tower"], ["Grain"]),
    ("buildings with room for 200", ["Clock Tower", "Grain Warehouse"], ["Boat Shed"]),
    ("buildings worth at least 5 crore", ["Clock Tower"], ["Grain", "Boat Shed"]),
    ("buildings with capacity not between 100 and 300", ["Boat Shed", "Grain Warehouse"],
     ["Clock Tower"]),
])
def test_end_to_end(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot), explain=True)
    assert "✓ matches" in out, out
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out.split("── query says ──")[1], out
