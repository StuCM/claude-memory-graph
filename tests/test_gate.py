import io
import json

import pytest

import claude_memory_graph.gate as gate
from claude_memory_graph.store import MemoryStore


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Seeded store + isolated state dir; gate reads via MEMORY_GRAPH_PATH."""
    store_dir = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(store_dir))
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path / "state")
    store = MemoryStore.open_or_create(store_dir)
    store.create_resource("Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs",
    })
    store.create_resource("Person", {"name": "Stuart Marshall", "role": "developer"})
    store.save()
    return store


# ---------------- terms / stopwords ----------------

def test_ack_words_yield_no_terms():
    assert gate._terms("Thanks, yes please — OK!") == []

def test_terms_keep_distinctive_words():
    assert "pyoxigraph" in gate._terms("why did we pick pyoxigraph?")


# ---------------- scoring (Stuart's pinned tests) ----------------

def test_generic_prompt_stays_silent():
    idf = {"dc03": 4.0, "harness": 3.0}
    doc = {"name": "charcoal", "desc": "dc03 harness",
           "name_terms": {"charcoal"}, "terms": {"dc03", "harness"}}
    assert gate._score(set(gate._terms("thanks, run the tests")), doc, idf) == 0.0

def test_specific_prompt_scores():
    idf = {"dc03": 4.0, "harness": 3.0}
    doc = {"name": "charcoal", "desc": "dc03 harness",
           "name_terms": {"charcoal"}, "terms": {"dc03", "harness"}}
    assert gate._score(set(gate._terms("fix the dc03 harness")), doc, idf) >= gate.ABS_MIN


# ---------------- recall gate end-to-end ----------------

def test_gate_fires_on_distinct_entity(graph):
    out = gate.recall_gate("remind me about pyoxigraph vs rdflib quad store", "s1")
    assert out is not None and "Use pyoxigraph over rdflib" in out

def test_gate_silent_on_generic_prompt(graph):
    assert gate.recall_gate("run the linter again", "s1") is None

def test_gate_indexes_rationale_not_just_description(graph):
    # the Decision has no 'description' property — rationale must still match
    out = gate.recall_gate("something about named graphs and the quad store rdflib pyoxigraph", "s1")
    assert out is not None

def test_session_memo_prevents_reinjection(graph):
    assert gate.recall_gate("pyoxigraph rdflib quad store", "s2") is not None
    assert gate.recall_gate("pyoxigraph rdflib quad store", "s2") is None

def test_decisions_logged(graph):
    gate.recall_gate("pyoxigraph rdflib quad store", "s3")
    log = (gate._STATE_DIR / "injections.jsonl").read_text().strip().splitlines()
    assert any(json.loads(line)["fired"] for line in log)


# ---------------- context nudge (Stuart's pinned test) ----------------

def test_nudge_fires_on_third_significant_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path)
    sid = "sess-1"
    assert gate.context_nudge(sid, "design the dc03 harness merge") is None
    assert gate.context_nudge(sid, "fix the csv export path bug") is None
    assert gate.context_nudge(sid, "add the print view route") is not None  # 3rd
    assert gate.context_nudge(sid, "thanks") is None  # trivial, no count

def test_nudge_cadence_resets_after_firing(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path)
    sid = "sess-2"
    for p in ("alpha beta gamma", "delta epsilon", "zeta eta"):
        gate.context_nudge(sid, p)
    assert gate.context_nudge(sid, "theta iota") is None  # 4th: fresh cycle

def test_nudge_and_memo_share_state_file(tmp_path, monkeypatch, graph):
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path / "shared")
    sid = "sess-3"
    gate.recall_gate("pyoxigraph rdflib quad store", sid)
    gate.context_nudge(sid, "some significant prompt about widgets")
    state = json.loads((tmp_path / "shared" / f"{sid}.json").read_text())
    assert state["injected"] and state["significant"] == 1


# ---------------- fail open ----------------

def test_main_swallows_garbage_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    gate.main()  # must not raise
    assert capsys.readouterr().out == ""
