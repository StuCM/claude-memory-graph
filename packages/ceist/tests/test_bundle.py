"""The vocabulary bundle (validate, assemble, stale check), `ceist eval`, and the CLI."""

import json

import pytest
from fakes import FakeEncoder

from ceist import bundle, config
from ceist.cli import main
from ceist.evaluate import evaluate, items_for, judge

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


GROUPS = {"built_start": "construction", "built_end": "construction", "gone_start": "demolition",
          "actor": "actors", "role": "actors", "height": "dimensions"}


def grouped(desc=DESC):
    """DESC as `ceist vocab describe` writes it now: each node with its nodegroup."""
    return dict(desc, nodegroups={g: {"id": f"ng-{g}", "parent": None} for g in set(GROUPS.values())},
                nodes=[dict(n, nodegroup=GROUPS[n["alias"]]) for n in desc["nodes"]])


def test_split_layout_assembles_to_the_same_bundle(tmp_path, capsys):
    p = project(tmp_path)
    (p / "desc" / "Building.json").write_text(json.dumps(grouped()))
    before, _, _ = bundle.assemble(p / "desc", p / "vocab", p / "graphs")
    assert [e["node"] for e in before["models"]["Building"]["entries"]] == [
        "actor", "built_start", "gone_start", "height"]            # ordered by nodegroup
    assert main(["vocab", "split", str(p / "desc"), str(p / "vocab")]) == 0
    assert "4 nodegroup file(s)" in capsys.readouterr().out
    actors = json.loads((p / "vocab" / "Building" / "actors.json").read_text())
    assert actors == {"model": "Building", "nodegroup": "actors", "entries": [VOCAB["entries"][2]]}
    manifest = json.loads((p / "vocab" / "manifest.json").read_text())
    assert manifest["models"]["Building"]["nodegroups"]["actors"]["id"] == "ng-actors"
    (p / "vocab" / "Building" / "dimensions.json").unlink()      # read from the split files, not Building.json
    after, _, warnings = bundle.assemble(p / "desc", p / "vocab", p / "graphs")
    assert [e["node"] for e in after["models"]["Building"]["entries"]] == ["actor", "built_start", "gone_start"]
    assert warnings == ["Building.json not read: manifest.json says the split layout is read"]
    bundle.split(p / "desc", p / "vocab", p / "vocab")
    assert bundle.assemble(p / "desc", p / "vocab", p / "graphs")[0] == before


def test_split_refuses_descriptions_without_nodegroups(tmp_path):
    p = project(tmp_path)
    written, errors = bundle.split(p / "desc", p / "vocab", p / "out")
    assert written == [] and "describe" in errors[0]


def test_check_finds_the_nodegroups_whose_description_changed(tmp_path, capsys):
    p = project(tmp_path)
    (p / "desc" / "Building.json").write_text(json.dumps(grouped()))
    bundle.split(p / "desc", p / "vocab", p / "vocab")
    main(["vocab", "assemble", str(p / "desc"), str(p / "vocab"), "-o", str(p / "b.json"),
          "--graphs", str(p / "graphs")])
    check = ["vocab", "check", str(p / "b.json"), str(p / "graphs"), "--vocab", str(p / "vocab"),
             "--descriptions", str(p / "desc")]
    assert main(check) == 0
    d = grouped()
    d["nodes"][-1]["values"] = ["metres"]                        # height
    d["nodes"].append({"alias": "roof", "name": "Roof", "datatype": "string", "nodegroup": "roofs"})
    d["nodegroups"]["roofs"] = {"id": "ng-roofs", "parent": None}
    (p / "desc" / "Building.json").write_text(json.dumps(d))
    capsys.readouterr()
    assert main(check) == 1
    assert capsys.readouterr().out.splitlines() == ["stale: Building.dimensions: its description changed",
                                                    "stale: Building.roofs: new nodegroup"]


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


BLOCK = {"phrases": ["involved"], "nodes": {"actor": {"role": "actor"}, "role": {"role": "type"}},
         "combos": [{"phrases": ["built by"], "node": "actor", "set": {"role": "Builder"}}],
         "answers": {"who": "actor"}}


def test_group_blocks_are_checked_split_and_assembled(tmp_path):
    d = grouped()
    assert bundle.validate_group(d, "actors", BLOCK) == []
    bad = {"nodes": {"height": {"role": "measure"}, "role": {"role": "boss"}},
           "combos": [{"phrases": ["flown by"], "set": {"role": "Pilot"}}],
           "answers": {"when": "built_start"}}
    errors = bundle.validate_group(d, "actors", bad)
    assert len(errors) == 4, errors
    assert any("'height' is not a node of this group" in e for e in errors)
    assert any("role 'boss'" in e for e in errors)
    assert any("'Pilot' is not a value of role" in e for e in errors)
    assert any("answers.when" in e for e in errors)
    p = project(tmp_path)
    (p / "desc" / "Building.json").write_text(json.dumps(d))
    (p / "vocab" / "Building.json").write_text(json.dumps(dict(VOCAB, groups={"actors": BLOCK})))
    bundle.split(p / "desc", p / "vocab", p / "vocab")
    assert json.loads((p / "vocab" / "Building" / "actors.json").read_text())["group"] == BLOCK
    b, errors, _ = bundle.assemble(p / "desc", p / "vocab", p / "graphs")
    assert not errors and b["format"] == "ceist.vocab/3" and b["built"]["groups"] == 1
    assert b["models"]["Building"]["groups"] == {"actors": BLOCK}
    (p / "vocab" / "Building" / "actors.json").write_text(json.dumps(
        {"model": "Building", "nodegroup": "actors", "entries": [], "group": bad}))
    assert len(bundle.assemble(p / "desc", p / "vocab", p / "graphs")[1]) == 4
    v1 = p / "v1.json"
    v1.write_text(json.dumps({"format": "ceist.vocab/1", "models": {}}))
    assert bundle.load(v1)["models"] == {}


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


def test_a_value_the_case_sets_on_its_own_node_is_scored_as_its_qualifier():
    # "scheduled": a combo setting designation type = Scheduled, the case saying so as a condition
    scheduled = {"node": "designation_type",
                 "conditions": [{"node": "designation_type", "value": "Scheduled"}]}
    assert judge(scheduled, ("designation_type", "Scheduled", None)) == "right"
    assert judge(scheduled, ("designation_type", "Listed", None)) == "dangerous"
    assert judge(scheduled, ("designation_type", None, None)) == "partial"
    assert judge(scheduled, ("protection_grade", "Scheduled", None)) == "dangerous"
    assert judge({"node": "designation_type", "conditions": []},
                 ("designation_type", "Scheduled", None)) == "dangerous"


@pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")
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
    out = capsys.readouterr().out
    assert '"alias":"height"' in out              # the description itself, inline
    assert str(p) not in out                      # never a path into the project
    assert main(["eval", "--bundle", str(p / "b.json"), "--questions", str(p / "cases.json"),
                 "--config", str(_toml(p))]) == 0
    assert "| 2/3 |" in capsys.readouterr().out


def _toml(p):
    t = p / "ceist.toml"
    t.write_text('[matching]\nlayers = ["exact"]\n')
    return t


def test_save_writes_a_reply_as_validated_vocab_files(tmp_path, capsys):
    p = project(tmp_path)
    reply = tmp_path / "reply.json"
    reply.write_text("```json\n" + json.dumps({
        "Building": {"model": "Building", "entries": [
            {"phrases": ["how tall"], "kind": "property", "node": "height"}]},
        "Nowhere": {"entries": []}}) + "\n```")
    out = tmp_path / "vocab2"
    assert main(["vocab", "save", str(reply), str(p / "desc"), str(out)]) == 1   # Nowhere: refused
    assert json.loads((out / "Building.json").read_text())["entries"][0]["node"] == "height"
    assert not (out / "Nowhere.json").exists()
    assert "no description" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"Building": {"entries": [{"phrases": ["x"], "node": "nope"}]}}))
    written, errors, _ = bundle.save(bad.read_text(), p / "desc", tmp_path / "vocab3")
    assert written == [] and "no node 'nope'" in errors[0]


def test_save_reports_a_malformed_reply_instead_of_crashing(tmp_path):
    p = project(tmp_path)
    out = tmp_path / "vocab2"
    written, errors, _ = bundle.save(json.dumps([{"phrases": ["x"]}]), p / "desc", out)
    assert written == [] and "not an object keyed by model" in errors[0]
    written, errors, _ = bundle.save("not json", p / "desc", out)
    assert written == [] and "not JSON" in errors[0]
    reply = {"Building": {"entries": [
        "height",
        {"phrases": ["tall"], "node": "height", "end_node": "built_end"},
        {"phrases": ["by"], "node": "actor", "qualifier": "Architect"},
        {"phrases": ["when"], "node": "built_start", "end_node": ["built_end"]}]}}
    written, errors, _ = bundle.save(json.dumps(reply), p / "desc", out)
    assert written == []
    assert errors == ["Building entry 0: not an object with a node",
                      "Building entry 1 (height): end_node on a node that is not a date",
                      "Building entry 2 (actor): qualifier 'Architect' is not {\"node\", \"value\"}",
                      "Building entry 3 (built_start): end_node ['built_end'] is not a date of this model"]
