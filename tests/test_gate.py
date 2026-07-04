import io
import json

import pytest

import claude_memory_graph.gate as gate
from claude_memory_graph.gate import Context, nudge, recall
from claude_memory_graph.store import MemoryStore


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Seeded store + isolated state dir; the gate reads via MEMORY_GRAPH_PATH."""
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


# ================= runtime =================

def test_ack_words_yield_no_terms():
    assert gate.terms("Thanks, yes please — OK!") == []

def test_terms_keep_distinctive_words():
    assert "pyoxigraph" in gate.terms("why did we pick pyoxigraph?")

def test_main_swallows_garbage_stdin(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    gate.main()  # must not raise
    assert capsys.readouterr().out == ""

def test_crashing_check_is_isolated(monkeypatch, capsys, tmp_path):
    """One broken check -> errors.log entry; other checks still answer."""
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path)

    def boom(ctx):
        raise RuntimeError("kaput")

    def fine(ctx):
        return "still here"

    monkeypatch.setattr(gate, "CHECKS", [boom, fine])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"prompt": "anything meaningful here", "session_id": "iso"})))
    gate.main()
    assert "still here" in capsys.readouterr().out
    assert "kaput" in (tmp_path / "errors.log").read_text()

def test_runtime_persists_state_between_prompts(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "_STATE_DIR", tmp_path)

    def remember(ctx):
        ctx.state["seen"] = ctx.state.get("seen", 0) + 1
        return None

    monkeypatch.setattr(gate, "CHECKS", [remember])
    for _ in range(2):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
            {"prompt": "hello there world", "session_id": "persist"})))
        gate.main()
    assert json.loads((tmp_path / "persist.json").read_text())["seen"] == 2


# ================= recall check =================

def _doc():
    return {"name": "charcoal", "desc": "dc03 harness",
            "name_terms": {"charcoal"}, "terms": {"dc03", "harness"}}

def test_generic_prompt_stays_silent():
    idf = {"dc03": 4.0, "harness": 3.0}
    assert recall._score(set(gate.terms("thanks, run the tests")), _doc(), idf) == 0.0

def test_specific_prompt_scores():
    idf = {"dc03": 4.0, "harness": 3.0}
    assert recall._score(set(gate.terms("fix the dc03 harness")), _doc(), idf) >= recall.ABS_MIN

def test_gate_fires_on_distinct_entity(graph):
    out = recall.recall_memories(Context("remind me about pyoxigraph vs rdflib quad store", "s1"))
    assert out is not None and "Use pyoxigraph over rdflib" in out

def test_gate_silent_on_generic_prompt(graph):
    assert recall.recall_memories(Context("run the linter again", "s1")) is None

def test_gate_indexes_rationale_not_just_description(graph):
    # the Decision has no 'description' property — rationale must still match
    out = recall.recall_memories(
        Context("something about named graphs and the quad store rdflib pyoxigraph", "s1"))
    assert out is not None

def test_session_memo_prevents_reinjection(graph):
    ctx = Context("pyoxigraph rdflib quad store", "s2")
    assert recall.recall_memories(ctx) is not None
    assert recall.recall_memories(ctx) is None  # same session state -> memo hit

def test_decisions_logged(graph):
    recall.recall_memories(Context("pyoxigraph rdflib quad store", "s3"))
    lines = (gate._STATE_DIR / "injections.jsonl").read_text().strip().splitlines()
    assert any(json.loads(line)["fired"] for line in lines)


# ================= nudge check =================

def test_nudge_fires_on_third_significant_turn():
    ctx = Context("", "sess-1")
    for prompt, expect in [
        ("design the dc03 harness merge", None),
        ("fix the csv export path bug", None),
    ]:
        ctx.prompt = prompt
        assert nudge.context_nudge(ctx) is expect
    ctx.prompt = "add the print view route"
    assert nudge.context_nudge(ctx) is not None  # 3rd -> nudge
    ctx.prompt = "thanks"
    assert nudge.context_nudge(ctx) is None  # trivial, no count

def test_nudge_cadence_resets_after_firing():
    ctx = Context("", "sess-2")
    for p in ("alpha beta gamma", "delta epsilon", "zeta eta"):
        ctx.prompt = p
        nudge.context_nudge(ctx)
    ctx.prompt = "theta iota"
    assert nudge.context_nudge(ctx) is None  # 4th: fresh cycle

def test_nudge_needs_session_id():
    assert nudge.context_nudge(Context("real words here", "")) is None
