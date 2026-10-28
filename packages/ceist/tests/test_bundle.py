"""The vocabulary bundle (validate, assemble, stale check), `ceist eval`, and the CLI."""

import json

from ceist import bundle, config
from ceist.cli import main
from ceist.evaluate import evaluate, items_for
from test_matching import FakeEncoder

DESC = {"name": "Building", "graphid": "g-b", "nodes": [
    {"alias": "built_start", "name": "Construction Start", "datatype": "edtf"},
    {"alias": "built_end", "name": "Construction End", "datatype": "edtf"},
    {"alias": "gone_start", "name": "Demolition Date", "datatype": "date"},
    {"alias": "actor", "name": "Actor", "datatype": "resource-instance-list", "targets": ["Person"]},
    {"alias": "role", "name": "Role", "datatype": "concept", "values": ["Architect", "Builder"]},
    {"alias": "height", "name": "Height", "datatype": "number"}]}
VOCAB = {"model": "Building", "entries": [
    {"phrases": ["built", "Erected", "put up"], "kind": "date", "node": "built_start",
     "end_node": "built_end"},
    {"phrases": ["demolished", "pulled down"], "kind": "date", "node": "gone_start"},
    {"phrases": ["designed by"], "kind": "link", "node": "actor",
     "qualifier": {"node": "role", "value": "Architect"}},
    {"phrases": ["how tall", "height"], "kind": "property", "node": "height"}]}
CASES = {"cases": [
    {"model": "Building", "q": "which buildings were erected before 1900?", "phrase": "erected",
     "slot": "date", "expect": {"node": "built_start"}},
    {"model": "Building", "q": "which buildings were constructed in 1850?", "phrase": "constructed",
     "slot": "date", "expect": {"node": "built_start"}},
    {"model": "Building", "q": "which buildings were designed by Ada?", "phrase": "designed by",
     "slot": "link:Person", "expect": {"node": "actor",
                                       "qualifier": {"node": "role", "value": "Architect"}}},
    {"model": "Building", "q": "which buildings were painted in 1900?", "phrase": "painted",
     "slot": "date", "expect": None}]}


def project(tmp_path):
    for d in ("desc", "vocab", "graphs"):
        (tmp_path / d).mkdir()
    (tmp_path / "desc" / "Building.json").write_text(json.dumps(DESC))
    (tmp_path / "vocab" / "Building.json").write_text(json.dumps(VOCAB))
    (tmp_path / "graphs" / "b.json").write_text('{"graph": []}')
    (tmp_path / "cases.json").write_text(json.dumps(CASES))
    return tmp_path


def test_validate_catches_bad_entries():
    bad = [{"phrases": ["x"], "node": "nope"},
           {"phrases": ["y"], "node": "built_start", "end_node": "height"},
           {"phrases": ["z"], "node": "actor", "qualifier": {"node": "role", "value": "Pilot"}},
           {"phrases": ["built"], "node": "gone_start"}]
    errors, warnings = bundle.validate(DESC, VOCAB["entries"] + bad)
    assert any("no node 'nope'" in e for e in errors)
    assert any("end_node 'height'" in e for e in errors)
    assert any("'Pilot' is not a value" in e for e in errors)
    assert any("'built' is a phrasing of two entries" in w for w in warnings)


def test_assemble_and_stale(tmp_path):
    p = project(tmp_path)
    b, errors, _ = bundle.assemble(p / "desc", p / "vocab", p / "graphs")
    assert not errors and b["built"]["entries"] == 4 and b["built"]["phrasings"] == 8
    m = b["models"]["Building"]
    assert m["nodes"]["actor"] == {"kind": "link", "label": "Actor", "targets": ["Person"]}
    assert "erected" in m["entries"][0]["phrases"]                  # lowercased
    assert not bundle.stale(b, p / "graphs")
    (p / "graphs" / "b.json").write_text('{"graph": [1]}')
    assert bundle.stale(b, p / "graphs")
    assert [i.key for i in items_for(m, "date")] == [("built_start", None, "built_end"),
                                                     ("gone_start", None, None)]
    assert [i.label for i in items_for(m, "link:Person")] == ["Actor (Architect)"]
    assert items_for(m, "link:Site") == []


def test_eval_scores_with_the_shipped_config(tmp_path):
    p = project(tmp_path)
    b, _, _ = bundle.assemble(p / "desc", p / "vocab")
    (p / "b.json").write_text(json.dumps(b))
    exact_only = evaluate(p / "b.json", p / "cases.json", config.load(None, layers=["exact"]))
    assert exact_only.counts == {"right": 2, "partial": 0, "dangerous": 0, "missed": 1, "refused": 1}
    both = evaluate(p / "b.json", p / "cases.json", config.load(None), encoder=FakeEncoder())
    assert both.counts["right"] == 3                                 # "constructed" by meaning
    assert next(r for r in both.rows if r["phrase"] == "constructed")["layer"] == "vectors"


def test_cli(tmp_path, capsys):
    p = project(tmp_path)
    assert main(["vocab", "assemble", str(p / "desc"), str(p / "vocab"), "-o",
                 str(p / "b.json"), "--graphs", str(p / "graphs")]) == 0
    assert main(["vocab", "check", str(p / "b.json"), str(p / "graphs")]) == 0
    assert "describe" not in capsys.readouterr().err
    assert main(["vocab", "prompt", str(p / "desc"), "Building"]) == 0
    assert "Building.json" in capsys.readouterr().out
    assert main(["eval", "--bundle", str(p / "b.json"), "--questions", str(p / "cases.json"),
                 "--config", str(_toml(p))]) == 0
    assert "| 2/3 |" in capsys.readouterr().out


def _toml(p):
    t = p / "ceist.toml"
    t.write_text('[matching]\nlayers = ["exact"]\n')
    return t
