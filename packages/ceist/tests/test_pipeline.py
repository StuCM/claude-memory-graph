"""`ceist vocab pipeline` with a fake LLM command returning canned JSON."""

import json
import shutil
import sys

import arches_fixture as fx
from ceist import pipeline
from ceist.cli import main

FAKE = r'''
import json, sys
canned = json.load(open(sys.argv[1]))
prompt = sys.stdin.read()
payload, _ = json.JSONDecoder().raw_decode(prompt.split("INPUT:\n", 1)[1])
if prompt.startswith("You are the offline"):
    key, reply = "group:" + payload["group"], {"purpose": "record keeping",
                                              "skip": {"reason": "metadata"}, "nodes": {}}
elif prompt.startswith("You are checking"):
    keep = canned.pop("collisions", {})
    key, reply = "collisions", [{"phrase": it["phrase"],
                                 "keep": next((e["i"] for e in it["entries"]
                                               if e["node"] == keep.get(it["phrase"])), "ambiguous")}
                                for it in payload]
elif prompt.startswith("You write acceptance"):
    key, reply = "questions:" + payload["model"]["model"], {"cases": []}
else:
    key, reply = "label", []
open(sys.argv[2], "a").write(key + "\n")
if canned.get(key) == "EXIT":
    sys.exit("the fake LLM fell over")
print(json.dumps(canned.get(key, reply)))
'''

CANNED = {
    "group:construction_date": {
        "purpose": "when the building was put up", "skip": None, "phrases": ["construction"],
        "nodes": {"construction_date": {"role": "date", "phrases": ["built", "constructed", "put up"]}},
        "intents": [{"intent": "when", "with": [], "wordings": ["when was it built?"]}]},
    "group:architect": {
        "purpose": "who designed it", "skip": None,
        "nodes": {"architect": {"role": "actor", "phrases": ["architect", "built"]}}},
    "group:associated_actor": {
        "purpose": "people involved, with their role", "skip": None,
        "nodes": {"actor": {"role": "actor", "phrases": ["involved"]},
                  "actor_role": {"role": "type", "phrases": []}},
        "combos": [{"phrases": ["designed by"], "node": "actor", "set": {"actor_role": "Architect"}},
                   {"phrases": ["built and designed by"], "node": "actor",
                    "set": {"actor_role": "Architect", "actor": "Builder"}}]},
    "group:heritage_status": {
        "purpose": "protection", "skip": None,
        "nodes": {"heritage_status": {"role": "type", "phrases": ["status", "protected"]}}},
    "collisions": {"built": "construction_date"},
    "questions:Building": {"cases": [
        {"q": "which buildings were built before 1900?", "phrase": "built", "slot": "date",
         "intent": "filter", "expect": {"node": "construction_date"}},
        {"q": "which buildings were put up after 1850?", "phrase": "put up", "slot": "date",
         "intent": "filter", "expect": {"node": "construction_date"}},
        {"q": "which buildings were painted in 1900?", "phrase": "painted", "slot": "date",
         "intent": "filter", "expect": None}]},
    "label": [{"i": 0, "model": "Building", "phrase": "constructed", "slot": "date",
               "expect": {"node": "construction_date"}}],
}


def project(tmp_path, canned=CANNED):
    data = tmp_path / "data"
    data.mkdir()
    ids = fx.write(data)
    ref = tmp_path / "ref" / "concepts"
    ref.mkdir(parents=True)
    for p in (data / "vocabularies").glob("*.xml"):
        shutil.copy(p, ref)
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "canned.json").write_text(json.dumps(canned))
    cmd = f"{sys.executable} {tmp_path / 'fake.py'} {tmp_path / 'canned.json'} {tmp_path / 'calls.txt'}"
    return data, tmp_path / "ref", cmd, ids


def calls(tmp_path) -> list[str]:
    p = tmp_path / "calls.txt"
    return p.read_text().split() if p.exists() else []


def test_crm_roles_from_classes_and_properties():
    crm = "http://www.cidoc-crm.org/cidoc-crm/"

    def node(alias, datatype, cls, prop):
        return {"nodeid": alias, "alias": alias, "datatype": datatype,
                "ontologyclass": crm + cls, "parentproperty": crm + prop if prop else None}

    nodes = [node("root", "semantic", "E22_Human-Made_Object", None),
             node("timespan", "semantic", "E52_Time-Span", "P4_has_time-span"),
             node("start", "date", "E61_Time_Primitive", "P82a_begin_of_the_begin"),
             node("end", "date", "E61_Time_Primitive", "P82b_end_of_the_end"),
             node("builder", "resource-instance", "E39_Actor", "P14_carried_out_by"),
             node("built_thing", "resource-instance", "E22_Human-Made_Object", "P14i_performed"),
             node("phase_type", "concept", "E55_Type", "P2_has_type"),
             node("appellation", "semantic", "E41_Appellation", "P1_is_identified_by"),
             dict(node("name", "string", "", "P3_has_note"),
                  ontologyclass="http://www.w3.org/2000/01/rdf-schema#Literal"),
             node("location", "resource-instance", "E18_Physical_Thing", "P53_has_former_or_current_location"),
             node("note", "string", "", "P3_has_note")]
    edges = [("root", "timespan"), ("timespan", "start"), ("timespan", "end"), ("root", "builder"),
             ("root", "built_thing"), ("root", "phase_type"), ("root", "appellation"),
             ("appellation", "name"), ("root", "location"), ("root", "note")]
    graph = {"nodes": nodes, "edges": [{"domainnode_id": a, "rangenode_id": b} for a, b in edges]}
    roles = pipeline.crm_roles(graph)
    assert {a: r["role"] for a, r in roles.items()} == {
        "start": "date", "end": "date", "builder": "actor", "built_thing": "actor",
        "phase_type": "type", "name": "name", "location": "place", "note": "description"}
    assert roles["start"]["pairs_with"] == "end"
    assert roles["start"]["crm"] == "E61 via P82a in E52"
    assert roles["builder"]["reverse"] == "performed"
    assert roles["built_thing"]["reverse"] == "carried out by"


def test_a_group_reply_is_checked_against_the_description():
    d = {"name": "Building", "nodegroups": {"phase": {}, "other": {}}, "nodes": [
        {"alias": "phase_type", "datatype": "concept", "nodegroup": "phase", "values": ["Construction"]},
        {"alias": "phase_start", "datatype": "date", "nodegroup": "phase"},
        {"alias": "height", "datatype": "number", "nodegroup": "other"}]}
    good = {"purpose": "phases", "skip": None, "phrases": ["phase"],
            "nodes": {"phase_start": {"role": "date", "phrases": ["built"]}},
            "combos": [{"phrases": ["built"], "node": "phase_start", "set": {"phase_type": "Construction"}}],
            "intents": [{"intent": "when", "with": ["other"], "wordings": ["when was it built?"]}]}
    assert pipeline.check_group(good, d, "phase") == []
    bad = dict(good, nodes={"height": {"role": "measure", "phrases": ["tall"]},
                            "phase_type": {"role": "type", "phrases": "x"}},
               combos=[{"phrases": ["razed"], "node": "phase_start", "set": {"phase_type": "Razing"}}],
               intents=[{"intent": "guess", "wordings": ["?"]}, {"intent": "when", "with": ["nope"],
                                                                  "wordings": ["?"]}])
    errors = pipeline.check_group(bad, d, "phase")
    assert len(errors) == 5, errors
    assert any("'height' is not a node of the group phase" in e for e in errors)
    assert any("'Razing' is not a value of phase_type" in e for e in errors)
    assert pipeline.check_group([], d, "phase") == ["the reply is not a JSON object"]


def test_pipeline_builds_per_nodegroup_resolves_collisions_and_gates(tmp_path, capsys):
    data, ref, cmd, ids = project(tmp_path)
    out = tmp_path / "out"
    real = tmp_path / "real.txt"
    real.write_text("# real questions\nwhich buildings did Ada Lovelace see constructed in 1872?\n")
    code = main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--questions", str(real), "--llm-cmd", cmd, "--min-right", "3",
                 "--max-dangerous", "1"])
    text = capsys.readouterr().out
    assert code == 0, text

    group = json.loads((out / "vocab" / "Building" / "associated_actor.json").read_text())
    assert group["entries"] == [
        {"phrases": ["involved"], "kind": "link", "node": "actor"},
        {"phrases": ["designed by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Architect"}}]
    assert group["group"]["answers"] == {"who": "actor"}
    assert len(group["group"]["combos"]) == 2          # the two-value combo stays in the group block
    assert json.loads((out / "vocab" / "manifest.json").read_text())["format"] == "ceist.vocab-groups/1"

    # the collision pass: "built" stays on the construction date only
    architect = json.loads((out / "vocab" / "Building" / "architect.json").read_text())
    assert architect["entries"][0]["phrases"] == ["architect"]
    assert json.loads((out / "collisions.json").read_text()) == [
        {"model": "Building", "phrase": "built", "keep": "construction_date.construction_date"}]

    cases = json.loads((out / "cases.json").read_text())["cases"]
    assert [c["source"] for c in cases] == ["llm"] * 3 + ["real"]
    assert cases[-1]["q"] == "which buildings did Ada Lovelace see constructed in 1872?"
    report = (out / "report.md").read_text()
    assert "**passed**" in report
    assert "| 3/3 | 0 | **0** | 0 | 1/1 |" in report                     # phrase level
    # planner level: the real question names a person with no record (missed), and the
    # planner reads "painted in 1900" as a construction date plus a text mention
    assert "| 2 | 0 | **1** | 1 | 0 |" in report
    assert "- which buildings were painted in 1900? → Find Buildings whose construction date" in report
    assert "| Building | 6 | 4 | 2 | 0 | 0 | 7 | 2 | 0 |" in report
    assert "| Person | 1 | 0 | 1 | 0 | 0 | 1 | 1 | 0 |" in report

    # privacy: the audit holds every prompt, and no record data
    audit = [json.loads(line) for line in (out / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == len(calls(tmp_path)) == 8 + 1 + 3 + 1   # groups, collisions, questions, label
    sent = (out / "audit.jsonl").read_text()
    assert "construction_date" in sent and "did <Name> see constructed" in sent
    for secret in ["Ada", "Lovelace", "Isambard", "Clock Tower", "Grain Warehouse", "Boat Shed",
                   "Leeds Dock", "Salts Mill", "1845-06-01", *ids["ids"].values()]:
        assert secret not in sent, secret

    # the cache: nothing is asked again; a changed nodegroup is asked again, alone
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd]) == 0
    assert len(calls(tmp_path)) == 13
    graph = data / "graphs" / f"{fx.BUILDING}.json"
    doc = json.loads(graph.read_text())
    next(n for n in doc["graph"][0]["nodes"] if n["alias"] == "construction_date")["name"] = "Built"
    graph.write_text(json.dumps(doc))
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd]) == 0
    assert calls(tmp_path)[13:] == ["group:construction_date", "collisions"]
    # another --model is another cache
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd, "--model", "other"]) == 0
    assert len(calls(tmp_path)) == 15 + 8 + 1


def test_the_gate_fails_on_too_few_right_or_any_dangerous(tmp_path, capsys):
    canned = dict(CANNED, **{"group:construction_date": {
        "purpose": "", "skip": None,
        "nodes": {"construction_date": {"role": "date", "phrases": ["built", "painted"]}}}})
    data, ref, cmd, _ = project(tmp_path, canned)
    out = tmp_path / "out"
    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"],
                        max_dangerous=0, log=lambda _: None) == 1
    report = (out / "report.md").read_text()
    assert "phrase dangerous 1 > 0" in report and "planner dangerous 1 > 0" in report
    assert "which buildings were painted in 1900? → Find Buildings whose construction date" in report
    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"],
                        min_right=3, log=lambda _: None) == 1
    assert "right 1 < 3" in (out / "report.md").read_text()
    assert not (out / "descriptions" / "Person.json").exists()


def test_a_reply_that_fails_its_schema_is_asked_again_then_reported(tmp_path):
    canned = dict(CANNED, **{"group:heritage_status": {"purpose": "x", "nodes": {"nope": {}}}})
    data, ref, cmd, _ = project(tmp_path, canned)
    out = tmp_path / "out"
    pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"], log=lambda _: None)
    assert calls(tmp_path).count("group:heritage_status") == 2
    audit = [json.loads(x) for x in (out / "audit.jsonl").read_text().splitlines()]
    retry = [a for a in audit if a.get("group") == "heritage_status"][1]
    assert "'nope' is not a node of the group heritage_status" in retry["prompt"]
    assert "- Building.heritage_status failed: nodes: 'nope'" in (out / "report.md").read_text()
    assert not (out / "vocab" / "Building" / "heritage_status.json").exists()


def test_the_claude_runner_reads_the_result_envelope(tmp_path):
    script = tmp_path / "claude.py"
    script.write_text('import json, os, sys\nsys.stdin.read()\n'
                      'print(json.dumps({"is_error": False, "result": json.dumps({"cwd": os.getcwd()})}))\n'
                      'print("a hook said something", file=sys.stderr)\n')
    run = pipeline.Runner(tmp_path / "out")
    assert run.claude and run.argv[:2] == ["claude", "-p"] and "--tools" in run.argv
    run.argv = [sys.executable, str(script)]
    reply = run.ask("k", "hello", lambda r: [], {"kind": "test"})
    assert reply["cwd"] != str(tmp_path) and not reply["cwd"].startswith(str(tmp_path / "out"))
    script.write_text('import json\nprint(json.dumps({"is_error": True, "result": "Not logged in"}))\n')
    assert run.ask("k2", "hello", lambda r: [], {"kind": "test"}) is None
    assert run.failures == [{"kind": "test", "errors": ["claude -p: Not logged in"]}]
    assert not list((tmp_path / "out" / "cache").glob("*.json"))[1:]   # only the good reply


def test_malformed_cases_are_rejected_not_cached_and_failed_calls_dont_stop_the_run(tmp_path):
    canned = dict(CANNED, **{"questions:Building": {"cases": [
        {"phrase": "built", "slot": "date"}, "not a case",
        {"q": "which buildings were built?", "phrase": "built", "slot": "date"}]},
        "group:heritage_status": "EXIT"})
    data, ref, cmd, _ = project(tmp_path, canned)
    out = tmp_path / "out"
    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"],
                        log=lambda _: None) == 0
    assert calls(tmp_path).count("questions:Building") == 2
    assert calls(tmp_path).count("group:heritage_status") == 1         # an error isn't retried
    assert (out / "vocab" / "Building" / "construction_date.json").exists()
    assert not (out / "cases.json").exists() and (out / "cases.unfrozen.json").exists()
    report = (out / "report.md").read_text()
    assert "**passed**\n\nWarning: no acceptance cases: nothing was measured" in report
    failed = report.split("## Failed calls\n\n")[1]
    assert "- group Building.heritage_status: " in failed and "fell over" in failed
    assert ('- questions Building: case 0: needs the question, "q"; case 0: needs "expect" '
            '(null when the answer is a refusal); case 1: not an object') in failed
    assert not [p for p in (out / "cache").glob("*.json")
                if "built" in p.read_text() and "cases" in p.read_text()]

    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"],
                        min_right=0, log=lambda _: None) == 1
    assert "failed: no acceptance cases" in (out / "report.md").read_text()
    assert calls(tmp_path).count("questions:Building") == 4             # asked again, not cached
