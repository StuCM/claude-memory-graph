"""The site gate's checks of words in combination: compositions with their plans, name probes that must never
bind a record by part of its name, the site's own questions, and setup.md's status with its exit code.

    test_type_words' fixture: Person.keyholder_for → Building, a "candidates" value plural, a Site 'Mill Yard v1.0'
"""

import json

import pytest
from fakes import FakeEncoder
from test_type_words import ROLE, _bundle_of, data  # noqa: F401  (fixture)
from test_vocab_rules import layers_dir

from ceist import compose, interpret, site
from ceist.alizarin import Tiles
from ceist.arches import ArchesVocabulary
from ceist.plan import HasValue, LinkTo, Plan

needs_numpy = pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")


def _scored(vocab, items) -> dict[str, str]:
    return {o["q"]: compose.score(o, interpret(vocab, o["q"]), Tiles(vocab)) for o in items}


def test_a_composition_is_read_against_its_plan_and_refuses_without_its_role_entry(data):  # noqa: F811
    with_role = ArchesVocabulary.from_data_dir(data[0], bundle=_bundle_of([ROLE]))
    items = {o["q"]: o for o in compose.compositions(with_role, Tiles(with_role))}
    keyholders = items["keyholders of candidates"]
    assert keyholders["family"] == "type + link + value"
    assert compose.signature(keyholders["plan"]) == ("Person", False, (
        "keyholder_for out ('Building', False, ('heritage_status = candidate',))",))
    assert _scored(with_role, [keyholders]) == {"keyholders of candidates": "right"}
    assert {o["family"] for o in items.values()} >= {"type + link + type", "type + link + value"}

    without = ArchesVocabulary.from_data_dir(data[0], bundle=_bundle_of())
    got = _scored(without, items.values())
    assert got["keyholders of candidates"] == "refused"
    status, risks = site._status(list(items.values()), {("site", q): s for q, s in got.items()},
                                 {"totals": {"unphrased links": 0}})
    row = next(line for line in status if line.startswith("| type + link + value |"))
    assert "keyholders of candidates" in row and risks == 0


def test_a_reading_that_drops_a_piece_is_a_wrong_reading(data):  # noqa: F811
    v = ArchesVocabulary.from_data_dir(data[0], bundle=_bundle_of([ROLE]))
    candidates = Plan("Building", [HasValue("heritage_status", "x", "Candidate")])
    item = {"q": "keyholders of buildings", "shape": "composition",
            "plan": Plan("Person", [LinkTo("keyholder_for", candidates, "out")])}
    assert compose.score(item, interpret(v, item["q"])) == "wrong reading"


def test_a_partial_name_must_never_bind_its_record(data, monkeypatch):  # noqa: F811
    v = ArchesVocabulary.from_data_dir(data[0])
    probes = [o for o in compose.name_probes(v) if "Mill Yard v1.0" in o["records"].values()]
    assert {o["q"] for o in probes if not o["bind"]} >= {"mill yard", "mill", "yard v1"}
    assert _scored(v, probes)["mill yard"] == "right refusal"
    assert _scored(v, probes)["Mill Yard v1.0"] == "right"
    # a numbered name read without its number (task 064's bug) binds on "mill yard"
    monkeypatch.setattr("ceist.index.marks", lambda text: set())
    stale = ArchesVocabulary.from_data_dir(data[0])
    assert _scored(stale, probes)["mill yard"] == "wrong"


def test_site_questions_read_both_practice_set_shapes(tmp_path):
    path = tmp_path / "practice.json"
    path.write_text(json.dumps({"questions": [
        {"q": "shelters", "group": "answer", "accept": [21, 22]},
        {"q": "substations", "group": "refuse", "accept": []},
        {"q": "hospitals", "expect": "answer", "count": 8},
        {"q": "near me", "group": "device", "accept": []}]}))
    assert [(o["counts"], o["refuse"]) for o in compose.site_questions(path)] == [
        ([21, 22], False), ([], True), ([8], False), ([], False)]


@needs_numpy
def test_setup_exits_1_on_a_partial_name_bind_unless_the_risk_is_accepted(data, tmp_path, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setattr("ceist.index.marks", lambda text: set())
    layers = layers_dir(tmp_path)
    out = tmp_path / "out"
    rc = site.setup(data[0], out, layers / "base", encoder=FakeEncoder(), log=lambda *_: None)
    report = (out / "setup.md").read_text()
    assert rc == 1 and (out / "bundle.json").exists()
    assert report.splitlines()[2] == "## Status" and "**Not set up:" in report
    assert "- 'mill yard' binds one of: Mill Yard v1.0" in report
    assert "- 'mill yard' binds one of: Mill Yard v1.0" in capsys.readouterr().err
    assert site.setup(data[0], out, layers / "base", encoder=FakeEncoder(), accept_risks=True,
                      log=lambda *_: None) == 0


@needs_numpy
def test_setup_gates_on_the_sites_own_questions_and_a_wrong_count_fails_it(data, tmp_path):  # noqa: F811
    data_dir, layers = data[0], layers_dir(tmp_path)
    practice = tmp_path / "practice.json"
    asked = [{"q": "how many listed buildings are there?", "expect": "answer", "count": 2},
             {"q": "which dragons breathe fire?", "expect": "refuse"}]
    practice.write_text(json.dumps({"questions": asked}))
    out = tmp_path / "out"
    assert site.setup(data_dir, out, layers / "base", encoder=FakeEncoder(), questions=practice,
                      log=lambda *_: None) == 0
    report = (out / "setup.md").read_text()
    assert "**Set up: no known wrong-answer risks.**" in report
    assert "The site's own questions: right 1, right refusal 1." in report
    asked[0]["count"] = 3
    practice.write_text(json.dumps({"questions": asked}))
    assert site.setup(data_dir, out, layers / "base", encoder=FakeEncoder(), questions=practice,
                      log=lambda *_: None) == 1
    assert "- how many listed buildings are there?" in (out / "setup.md").read_text()


def test_a_name_saying_a_word_twice_is_not_probed_by_one_copy_of_it_and_a_shared_part_is_one_probe():
    from types import SimpleNamespace

    from ceist.vocabulary import Entity
    names = [Entity("Site", "a", "Ballywillwill 2, Ballywillwill"), Entity("Site", "b", "Ballywillwill 3")]
    vocab = SimpleNamespace(_index=SimpleNamespace(entities=names), type_words=dict, values=list)
    assert [(o["q"], sorted(o["records"]), o["bind"]) for o in compose.name_probes(vocab)] == [
        ("ballywillwill", ["a", "b"], False), ("2", ["a"], False), ("3", ["b"], False),
        ("Ballywillwill 2, Ballywillwill", ["a"], True), ("Ballywillwill 3", ["b"], True)]
