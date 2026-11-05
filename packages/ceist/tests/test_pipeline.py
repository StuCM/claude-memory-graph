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
elif prompt.startswith("You name the types"):
    key, reply = "model:" + payload["model"], {"type_words": [], "links": {}}
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
         "intent": "filter", "expect": {"node": "construction_date",
                                        "conditions": [{"node": "construction_date"}]}},
        {"q": "which buildings were put up after 1850?", "phrase": "put up", "slot": "date",
         "intent": "filter", "expect": {"node": "construction_date",
                                        "conditions": [{"node": "construction_date"}]}},
        {"q": "which buildings were painted in 1900?", "phrase": "painted", "slot": "date",
         "intent": "filter", "expect": None}]},
    "label": [{"i": 0, "model": "Building", "phrase": "constructed", "slot": "date",
               "expect": {"node": "construction_date", "conditions": [{"node": "construction_date"}]}}],
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
    assert ("Warning: one-word group phrases (each takes its word anywhere outside a record's "
            "name): Building construction_date: construction") in report
    assert "| 3/3 | 0 | **0** | 0 | 1/1 |" in report                     # phrase level
    # planner level: the real question names a person with no record (missed), and
    # "painted in 1900" is refused: no text mention stands in for "painted"
    assert "| 2 | 0 | **0** | 1 | 1 |" in report
    assert "| Building | 6 | 4 | 2 | 0 | 0 | 7 | 2 | 0 |" in report
    assert "| Person | 1 | 0 | 1 | 0 | 0 | 1 | 1 | 0 |" in report

    # privacy: the audit holds every prompt, and no record data
    audit = [json.loads(line) for line in (out / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == len(calls(tmp_path)) == 8 + 3 + 1 + 3 + 1   # groups, models, collisions,
                                                                    # questions, label
    sent = (out / "audit.jsonl").read_text()
    assert "construction_date" in sent and "did <Name> see constructed" in sent
    for secret in ["Ada", "Lovelace", "Isambard", "Clock Tower", "Grain Warehouse", "Boat Shed",
                   "Leeds Dock", "Salts Mill", "1845-06-01", *ids["ids"].values()]:
        assert secret not in sent, secret

    # the cache: nothing is asked again; a changed nodegroup is asked again, alone
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd]) == 0
    assert len(calls(tmp_path)) == 16
    graph = data / "graphs" / f"{fx.BUILDING}.json"
    doc = json.loads(graph.read_text())
    next(n for n in doc["graph"][0]["nodes"] if n["alias"] == "construction_date")["name"] = "Built"
    graph.write_text(json.dumps(doc))
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd]) == 0
    assert calls(tmp_path)[16:] == ["group:construction_date", "collisions"]
    # another --model is another cache
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd, "--model", "other"]) == 0
    assert len(calls(tmp_path)) == 18 + 8 + 3 + 1


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


def test_the_gate_rejects_an_entry_for_a_node_its_model_lacks(tmp_path):
    data, ref, cmd, _ = project(tmp_path)
    out = tmp_path / "out"
    stray = out / "vocab" / "Building" / "repository.json"     # left by a build of another model
    stray.parent.mkdir(parents=True)
    stray.write_text(json.dumps({"model": "Building", "nodegroup": "repository", "entries": [
        {"phrases": ["at"], "kind": "link", "node": "repository_owner"}]}))
    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, models=["Building"],
                        log=lambda _: None) == 1
    report = (out / "report.md").read_text()
    assert "**failed: bundle: Building entry" in report
    assert "(repository_owner): no node 'repository_owner'" in report


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


def test_judge_plan_reads_inside_a_tile_condition():
    from types import SimpleNamespace

    from ceist.plan import EntityRef, HasValue, LinkTo, OnTile, Plan
    from ceist.vocabulary import Entity
    ada = Entity("Person", "ada", "Ada")
    plan = Plan("Building", [OnTile("associated_actor", [
        LinkTo("actor", EntityRef(ada), style="field"),
        HasValue("actor_role", "c-architect", "Architect")])])
    m = SimpleNamespace(plan=plan, refused="")
    case = {"model": "Building", "expect": {"node": "actor",
                                            "qualifier": {"node": "actor_role",
                                                          "value": "Architect"}}}
    assert pipeline.judge_plan(case, m, {}) == "right"
    case["expect"]["qualifier"]["value"] = "Builder"
    assert pipeline.judge_plan(case, m, {}) == "partial"


def test_judge_plan_checks_expected_conditions_and_their_tile():
    from types import SimpleNamespace

    from ceist.plan import DateRange, HasValue, OnTile, Plan
    destroyed = HasValue("phase_type", "c-d", "Destruction")
    before = DateRange("phase_date", None, "1899-12-31")
    want = {"model": "Building", "expect": {"conditions": [
        {"node": "phase_type", "value": "Destruction", "tile": "phase"},
        {"node": "phase_date", "tile": "phase"}]}}

    def judged(*where):
        return pipeline.judge_plan(want, SimpleNamespace(plan=Plan("Building", list(where)),
                                                         refused=""), {})
    assert judged(OnTile("phase", [destroyed, before])) == "right"
    assert judged(OnTile("phase", [destroyed])) == "partial"          # the date dropped
    assert judged(destroyed, before) == "dangerous"                    # not on one tile
    assert judged(OnTile("phase", [HasValue("phase_type", "c-a", "Alteration"), before])) == "dangerous"


def test_a_unit_only_describes_its_value():
    crm = "http://www.cidoc-crm.org/cidoc-crm/"
    graph = {"nodes": [{"nodeid": "dim", "alias": "dim", "datatype": "semantic",
                        "ontologyclass": crm + "E54_Dimension"},
                       {"nodeid": "unit", "alias": "unit", "datatype": "concept",
                        "ontologyclass": crm + "E58_Measurement_Unit", "parentproperty": crm + "P91_has_unit"}],
             "edges": [{"domainnode_id": "dim", "rangenode_id": "unit"}]}
    roles = pipeline.crm_roles(graph)
    assert roles["unit"]["role"] == "unit"
    d = {"name": "Object", "nodegroups": {"dim": {}}, "nodes": [
        {"alias": "unit", "datatype": "concept", "nodegroup": "dim"},
        {"alias": "value", "datatype": "number", "nodegroup": "dim"}]}
    reply = {"purpose": "size", "nodes": {"unit": {"role": "type", "phrases": ["in grams"]},
                                          "value": {"role": "measure", "phrases": ["weight"]}}}
    assert pipeline.check_group(reply, d, "dim") == []                  # nothing says it's a unit
    errors = pipeline.check_group(reply, d, "dim", roles)
    assert len(errors) == 1 and "nodes.unit: a unit only describes" in errors[0]
    reply["nodes"]["unit"] = {"role": "unit", "phrases": ["in grams"]}
    assert len(pipeline.check_group(reply, d, "dim")) == 1
    reply["nodes"]["unit"]["phrases"] = []
    assert pipeline.check_group(reply, d, "dim", roles) == []


def test_type_words_and_link_wording_by_the_types_joined(tmp_path):
    canned = dict(CANNED, **{
        "model:Building": {"type_words": ["Edifices", "sheds"],
                           "links": {"site": {"phrases": ["at"], "reverse": ["holds"]},
                                     "architect": {"phrases": ["at", "by"]},
                                     "actor": {"phrases": ["by"]}}},
        "model:Site": {"type_words": ["sheds", "places"]},
        "collisions": {"built": "construction_date", "by": "actor"}})
    data, ref, cmd, _ = project(tmp_path, canned)
    out = tmp_path / "out"
    assert pipeline.run(data / "graphs", out, ref, llm_cmd=cmd, log=lambda _: None) == 0

    audit = [json.loads(x) for x in (out / "audit.jsonl").read_text().splitlines()]
    sent = next(a["prompt"] for a in audit if a["kind"] == "model" and a["model"] == "Building")
    payload = json.loads(sent.split("INPUT:\n", 1)[1])
    assert {x["alias"]: (x["from"], x["to"]) for x in payload["links"]} == {
        "architect": ("Building", ["Person"]), "actor": ("Building", ["Person"]),
        "site": ("Building", ["Site"])}
    assert payload["other_models"] == ["Person", "Site"]

    def phrases(group, node):
        f = json.loads((out / "vocab" / "Building" / f"{group}.json").read_text())
        return next(e["phrases"] for e in f["entries"] if e["node"] == node and not e.get("qualifier"))

    # "at" joins a Building to a Site or to a Person: both keep it; "by" joins two links
    # to a Person, so the collision pass settles it
    assert phrases("site", "site") == ["at", "holds"]
    assert phrases("architect", "architect") == ["architect", "at"]
    assert phrases("associated_actor", "actor") == ["involved", "by"]
    collisions = json.loads((out / "collisions.json").read_text())
    assert {"model": "Building", "phrase": "at", "keep": "all: links joining different types"} in collisions
    assert {"model": "Building", "phrase": "by", "keep": "associated_actor.actor"} in collisions

    # a type word two models claim names neither
    b = json.loads((out / "bundle.json").read_text())
    assert b["extra_type_words"] == {"edifices": "Building", "places": "Site"}
    report = (out / "report.md").read_text()
    assert "type words two models claimed, dropped: 'sheds' (Building, Site)" in report
    assert "- Building: edifices" in report

    from ceist import config
    counts, rows = pipeline.planner_run(
        data / "graphs", ref, b,
        [{"model": "Building", "q": "how many edifices are there?", "expect": {"conditions": []}},
         {"model": "Site", "q": "which places are there?", "expect": {"conditions": []}}],
        config.load(None))
    assert counts["right"] == 2, rows


def test_type_words_naming_another_model_are_refused_and_a_self_link_has_no_reverse(tmp_path):
    reply = tmp_path / "reply.json"
    script = tmp_path / "llm.py"
    script.write_text(f"import sys\nsys.stdin.read()\nprint(open({str(reply)!r}).read())\n")
    tale = {"name": "Tale", "nodes": [{"alias": "parent_story", "name": "Parent Story",
                                       "datatype": "resource-instance", "targets": ["Tale"],
                                       "nodegroup": "parent_story"}]}
    descriptions = {"Tale": tale, "Figure": {"name": "Figure", "nodes": []}}
    seeds = {"types": {}, "nodes": {}}
    run = pipeline.Runner(tmp_path / "out", f"{sys.executable} {script}")
    reply.write_text(json.dumps({"type_words": ["stories"],
                                 "links": {"parent_story": {"phrases": ["part of"],
                                                            "reverse": ["includes"]}}}))
    words, links, _ = pipeline.name_model(run, tale, {}, descriptions, seeds)
    assert words == ["stories"] and links == {"parent_story": ["part of"]}   # no direction to tell
    reply.write_text(json.dumps({"type_words": ["figures"]}))
    run = pipeline.Runner(tmp_path / "out2", f"{sys.executable} {script}")
    assert pipeline.name_model(run, tale, {}, descriptions, seeds)[0] == []
    assert run.failures[0]["errors"] == ["type word 'figures' names another model"]


def test_seeds_are_extended_never_deleted(tmp_path):
    canned = dict(CANNED, **{
        "group:construction_date": dict(CANNED["group:construction_date"], doubts=[
            {"node": "construction_date", "phrase": "raised", "why": "rare"}])})
    data, ref, cmd, _ = project(tmp_path, canned)
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"extra_type_words": {"Edifice": "Building", "keep": "Castle"},
                                "relation_forms": {"site": ["On"], "architect": ["built"], "nope": ["x"]},
                                "date_forms": {"construction_date": ["raised"]}}))
    out = tmp_path / "out"
    assert main(["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref),
                 "--llm-cmd", cmd, "--seed", str(seed)]) == 0

    audit = [json.loads(x) for x in (out / "audit.jsonl").read_text().splitlines()]
    group = next(a["prompt"] for a in audit if a.get("group") == "construction_date")
    node = json.loads(group.split("INPUT:\n", 1)[1])["nodes"][0]
    assert node["seed"] == ["raised"]
    model = json.loads(next(a["prompt"] for a in audit if a["kind"] == "model"
                            and a["model"] == "Building").split("INPUT:\n", 1)[1])
    assert model["seed_type_words"] == ["edifice"]
    assert next(x for x in model["links"] if x["alias"] == "site")["seed"] == ["on"]

    def phrases(group, node):
        f = json.loads((out / "vocab" / "Building" / f"{group}.json").read_text())
        return next(e["phrases"] for e in f["entries"] if e["node"] == node and not e.get("qualifier"))

    # the LLM left "raised" out and doubted it: it stays, and the doubt is reported
    assert phrases("construction_date", "construction_date") == ["built", "constructed", "put up", "raised"]
    assert phrases("site", "site") == ["on"]
    # the collision pass gives "built" to the construction date, but not the architect's seed
    assert phrases("architect", "architect") == ["architect", "built"]
    assert json.loads((out / "bundle.json").read_text())["extra_type_words"] == {"edifice": "Building"}
    report = (out / "report.md").read_text()
    assert "- Building.construction_date 'raised': rare" in report
    assert "type word 'keep' names Castle, not a model here" in report
    assert "no model has a node 'nope'; not seeded" in report


def test_a_bundle_or_vocab_dir_is_a_seed(tmp_path):
    descriptions = {"Building": {"name": "Building", "nodes": [{"alias": "site"}, {"alias": "actor"}]}}
    bundle = tmp_path / "b.json"
    bundle.write_text(json.dumps({"format": "ceist.vocab/2", "extra_type_words": {"edifices": "Building"},
                                  "models": {"Building": {"entries": [
                                      {"node": "site", "phrases": ["Sited At"]},
                                      {"node": "actor", "phrases": ["designed by"],
                                       "qualifier": {"node": "role", "value": "Architect"}}]},
                                             "Castle": {"entries": []}}}))
    seeds, warnings = pipeline.load_seeds([bundle], descriptions)
    assert seeds == {"types": {"Building": ["edifices"]}, "nodes": {"Building": {"site": ["sited at"]}}}
    assert warnings == [f"{bundle}: Castle is not a model here; not seeded"]
    vocab = tmp_path / "vocab"
    (vocab / "Building").mkdir(parents=True)
    (vocab / "manifest.json").write_text(json.dumps({"models": {"Building": {"type_words": ["edifices"]}}}))
    (vocab / "Building" / "site.json").write_text(json.dumps(
        {"model": "Building", "nodegroup": "site", "entries": [{"node": "site", "phrases": ["at"]}]}))
    assert pipeline.load_seeds([vocab], descriptions)[0] == {
        "types": {"Building": ["edifices"]}, "nodes": {"Building": {"site": ["at"]}}}


def test_cases_say_what_the_whole_question_means():
    d = {"name": "Building", "nodegroups": {"phase": {}}, "nodes": [
        {"alias": "phase_type", "datatype": "concept", "nodegroup": "phase", "values": ["Destruction"]},
        {"alias": "site", "datatype": "resource-instance", "nodegroup": "site"}]}
    descriptions = {"Building": d, "Site": {"name": "Site", "nodes": []}}
    good = {"q": "which buildings were destroyed on a site?", "phrase": "destroyed", "slot": "property",
            "expect": {"node": "phase_type", "conditions": [
                {"node": "phase_type", "value": "Destruction", "tile": "phase"},
                {"node": "site", "link": "Site"}]}}
    assert pipeline._check_cases([good], descriptions, "Building") == []
    bad = dict(good, expect={"node": "phase_type", "conditions": [
        {"node": "phase_type", "value": "Razing"}, {"node": "phase_type", "tile": "nope"},
        {"node": "site", "link": "Castle"}, {"node": "height"}]})
    assert len(pipeline._check_cases([bad], descriptions, "Building")) == 4
    assert pipeline._check_cases([dict(good, expect={"node": "phase_type"})], descriptions,
                                 "Building") == ['case 0: expect needs "conditions", a list (empty '
                                                 'for the type alone)']
    # a labelled real question may pick no field
    real = {"model": "Building", "phrase": None, "expect": {"conditions": []}}
    assert pipeline._check_cases([real], descriptions, need_q=False, need_phrase=False) == []


def test_judge_plan_checks_a_links_target_type_and_either_end_of_a_date():
    from types import SimpleNamespace

    from ceist.plan import DateRange, EntityRef, LinkTo, Plan
    from ceist.vocabulary import Entity
    dock = LinkTo("site", EntityRef(Entity("Site", "s", "Leeds Dock")), style="field")
    to_site = {"model": "Building", "expect": {"conditions": [{"node": "site", "link": "Site"}]}}
    to_person = {"model": "Building", "expect": {"conditions": [{"node": "site", "link": "Person"}]}}

    def judged(case, *where, ends=None):
        return pipeline.judge_plan(case, SimpleNamespace(plan=Plan("Building", list(where)),
                                                         refused=""), ends or {})
    assert judged(to_site, dock) == "right"
    assert judged(to_person, dock) == "dangerous"
    built = {"model": "Building", "expect": {"conditions": [{"node": "built_start"}]}}
    assert judged(built, DateRange("built_end", "1900-01-01", None)) == "partial"
    assert judged(built, DateRange("built_end", "1900-01-01", None),
                  ends={"built_start": "built_end"}) == "right"
