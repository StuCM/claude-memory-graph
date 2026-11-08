"""`ceist vocab ontology`: CRM paths ranked by use, prompts of CRM text only, proposals
for review, and an accept step that merges only what the gate passes."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_ontology import ONTOLOGY, data  # noqa: F401  (the module fixture)

import ceist
from ceist import ontology_vocab as ov
from ceist.arches import ArchesVocabulary, graph_doc

CRM = "http://www.cidoc-crm.org/cidoc-crm/"
SOURCE = Path(__file__).resolve().parents[3] / "vocabularies" / "ontology" / "cidoc-crm" / "source"
GATE = Path(ceist.__file__).resolve().parents[2] / "bench" / "ontology" / "gate.py"
STUB = '''import json, sys
prompt = sys.stdin.read()
with open(sys.argv[1], "a") as f:
    f.write("call\\n")
paths = json.loads(prompt.split("PATHS:\\n", 1)[1].split("\\n\\nReply", 1)[0])
out = [{"path": p["path"], "skip": "audit metadata"} if p["path"].endswith("P49")
       else {"path": p["path"], "phrases": ["Phrase " + p["path"].split()[-1]], "reason": "r"} for p in paths]
print(json.dumps({"paths": out}))
'''


def _graph(gid: str, name: str, chains: list[tuple[str, str, list[str]]]) -> dict:
    """A graph whose root is an E22; each (alias, datatype, [prop, class, prop, class …])
    hangs off the root by its own chain of semantic nodes, named after the alias."""
    root = {"nodeid": f"{gid}-root", "alias": f"{name.lower()}_root", "name": name, "datatype": "semantic",
            "istopnode": True, "ontologyclass": CRM + "E22_Human-Made_Object"}
    nodes, edges = [root], []
    for alias, datatype, chain in chains:
        up = root
        for i in range(0, len(chain), 2):
            last = i + 2 >= len(chain)
            n = {"nodeid": f"{gid}-{alias}-{i}", "alias": alias if last else f"{alias}_{i}",
                 "name": f"Secret {alias} {i}", "datatype": datatype if last else "semantic",
                 "ontologyclass": CRM + chain[i + 1] if chain[i + 1] != "-" else "",
                 "parentproperty": CRM + chain[i]}
            nodes.append(n)
            edges.append({"domainnode_id": up["nodeid"], "rangenode_id": n["nodeid"]})
            up = n
    return {"graph": [{"graphid": gid, "name": {"en": name}, "nodes": nodes, "edges": edges}]}


MAKER = ["P108i_was_produced_by", "E12_Production", "P14_carried_out_by", "E39_Actor"]
MADE = ["P108i_was_produced_by", "E12_Production", "P4_has_time-span", "E52_Time-Span",
        "P82a_begin_of_the_begin", "E61_Time_Primitive"]


def graphs_dir(tmp_path) -> Path:
    d = tmp_path / "graphs"
    d.mkdir()
    docs = {
        "a": _graph("g-a", "Zorblat Hoard", [
            ("zorb_maker", "resource-instance", MAKER), ("zorb_made", "date", MADE),
            ("zorb_keeper", "resource-instance", ["P49_has_former_or_current_keeper", "E39_Actor"]),
            ("zorb_kind", "concept", ["P2_has_type", "E55_Type"]),
            ("zorb_scan", "resource-instance", ["P129i_is_subject_of", "D1_Digital_Object", "L11i_was_output_of", "-"])]),
        "b": _graph("g-b", "Quillon Cache", [("quil_maker", "resource-instance", MAKER)]),
    }
    for k, doc in docs.items():
        (d / f"{k}.json").write_text(json.dumps(doc))
    return d


def ontology_dir(tmp_path, entries=()) -> Path:
    d = tmp_path / "cidoc-crm"
    d.mkdir()
    (d / "source").symlink_to(SOURCE)
    (d / "phrases.json").write_text(json.dumps({"format": "ceist.ontology/1", "entries": list(entries)}))
    return d


def stub(tmp_path) -> str:
    (tmp_path / "stub.py").write_text(STUB)
    return f"{sys.executable} {tmp_path / 'stub.py'} {tmp_path / 'calls.txt'}"


def test_paths_are_ranked_by_the_nodes_they_reach(tmp_path):
    docs = ov.graph_docs([graphs_dir(tmp_path)])
    cands, skipped = ov.collect(docs, {"entries": []}, ov.definitions(SOURCE))
    assert [(c["path"], c["kind"], c["nodes"], c["graphs"]) for c in cands] == [
        ("P108i E12 P14", "link", 2, 2), ("E22 P2", "property", 1, 1), ("E22 P49", "link", 1, 1),
        ("P108i E12 P4", "date", 1, 1)]
    assert skipped["outside CIDOC-CRM and CRMsci"] == 1
    phrased = {"entries": [{"path": "E22 P49", "kind": "link", "phrases": ["kept by"]},
                           {"path": "P2", "kind": "property", "phrases": ["kind"]}]}
    cands, skipped = ov.collect(docs, phrased, ov.definitions(SOURCE))
    assert [c["path"] for c in cands] == ["P108i E12 P14", "P108i E12 P4"]
    assert skipped["already phrased"] == 2


def test_prompts_hold_only_crm_text_and_seeds(tmp_path):
    seeds = [{"path": "P51", "kind": "link", "phrases": ["owned by", "owner"]}]
    onto = ontology_dir(tmp_path, seeds)
    assert ov.propose([graphs_dir(tmp_path)], onto, tmp_path / "out", stub(tmp_path), log=lambda _: None) == 0
    audit = [json.loads(line) for line in (tmp_path / "out" / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1
    text = audit[0]["prompt"]
    assert "E12 Production: " in text and "carried out by" in text and "owned by, owner" in text
    assert '"path": "P108i E12 P14"' in text
    client = {"Zorblat", "Quillon", "Hoard", "Cache", "Secret", "zorb", "quil", "g-a", "g-b"}
    assert [w for w in client if w.lower() in text.lower()] == []


def test_proposals_are_written_for_review_and_a_rerun_pays_nothing(tmp_path):
    onto = ontology_dir(tmp_path)
    graphs, cmd = graphs_dir(tmp_path), stub(tmp_path)
    ov.propose([graphs], onto, tmp_path / "out", cmd, log=lambda _: None)
    doc = json.loads((onto / "proposed.json").read_text())
    assert [(p["path"], p["kind"], p["phrases"], p["reviewed"]) for p in doc["proposals"]] == [
        ("P108i E12 P14", "link", ["phrase p14"], False), ("E22 P2", "property", ["phrase p2"], False),
        ("P108i E12 P4", "date", ["phrase p4"], False)]
    assert [(s["path"], s["skip"]) for s in doc["skipped"]] == [("E22 P49", "audit metadata")]
    doc["proposals"][0].update(phrases=["made by"], reviewed=True)
    (onto / "proposed.json").write_text(json.dumps(doc))
    ov.propose([graphs], onto, tmp_path / "out", cmd, log=lambda _: None)
    assert (tmp_path / "calls.txt").read_text() == "call\n"
    kept = json.loads((onto / "proposed.json").read_text())["proposals"][0]
    assert (kept["phrases"], kept["reviewed"]) == (["made by"], True)


def test_accept_merges_only_the_reviewed_proposals_the_gate_passes(tmp_path):
    onto = ontology_dir(tmp_path, [{"path": "P51", "kind": "link", "phrases": ["owned by"]}])
    (onto / "proposed.json").write_text(json.dumps({"proposals": [
        {"path": "P108i E12 P14", "kind": "link", "phrases": ["made by"], "reviewed": True},
        {"path": "P51", "kind": "link", "phrases": ["owner"], "reviewed": True},
        {"path": "E22 P49", "kind": "link", "phrases": ["kept by"], "reviewed": True},
        {"path": "P108i E12 P4", "kind": "date", "phrases": ["made"], "reviewed": False}]}))
    (tmp_path / "gate.py").write_text(
        "import json, shutil, sys\nshutil.copy(sys.argv[2], sys.argv[1])\n"
        'print(json.dumps({"accepted": ["link P108i E12 P14", "link P51"], "rejected": {"link E22 P49": "bench: worse"}}))\n')
    sent = tmp_path / "sent.json"
    assert ov.accept(onto, [sys.executable, str(tmp_path / "gate.py"), str(sent)], log=lambda _: None) == 0
    assert [c["path"] for c in json.loads(sent.read_text())] == ["P108i E12 P14", "P51", "E22 P49"]
    assert json.loads((onto / "phrases.json").read_text())["entries"] == [
        {"path": "P51", "kind": "link", "phrases": ["owned by", "owner"]},
        {"path": "P108i E12 P14", "kind": "link", "phrases": ["made by"]}]
    gates = [p.get("gate") for p in json.loads((onto / "proposed.json").read_text())["proposals"]]
    assert gates == ["merged", "merged", "rejected: bench: worse", None]


def _gate():
    spec = importlib.util.spec_from_file_location("ontology_gate", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_gate_rejects_a_proposal_that_adds_a_wrong_reading(data, tmp_path):  # noqa: F811
    gate = _gate()
    graphs = [graph_doc(p) for p in sorted((data[0] / "graphs").glob("*.json"))]
    resources = gate.run.synthetic(graphs)
    vocab = ArchesVocabulary(graphs, resources=resources)
    base = ONTOLOGY["entries"]
    good = {"path": "E22 P14", "kind": "link", "phrases": ["designed by"]}
    # the production date, phrased as the building's other date field
    bad = {"path": "P108i E12 P4", "kind": "date", "phrases": ["construction date"]}
    before = gate.scores("fixture", graphs, resources, vocab, base)
    after = gate.scores("fixture", graphs, resources, vocab, base + [bad])
    assert after[("ontology", "what is the construction date of Keldrith?")] == "wrong reading"
    assert gate.judge(before, after)[1] == ["what is the construction date of Keldrith?"]
    onto = tmp_path / "onto"
    onto.mkdir()
    (onto / "phrases.json").write_text(json.dumps(ONTOLOGY))
    verdict = gate.gate([good, bad], onto, {"fixture": str(data[0] / "graphs")}, None, None)
    assert verdict["accepted"] == ["link E22 P14"]
    assert verdict["rejected"]["date P108i E12 P4"].startswith("bench: worse on 1, e.g. fixture: what is the construction")
    with pytest.raises(RuntimeError, match="no demo checkout"):
        gate.gate([good], onto, {"fixture": str(data[0] / "graphs")}, tmp_path / "nowhere", None)
