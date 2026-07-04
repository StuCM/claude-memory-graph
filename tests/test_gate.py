import io
import json

import pytest

import claude_memory_graph.gate as gate
from claude_memory_graph.gate import Context, nudge, recall, runtime
from claude_memory_graph.store import MemoryStore


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Seeded store + isolated state dir; the gate reads via MEMORY_GRAPH_PATH."""
    store_dir = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(store_dir))
    monkeypatch.setattr(runtime, "_STATE_DIR", tmp_path / "state")
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
    monkeypatch.setattr(runtime, "_STATE_DIR", tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    gate.main()  # must not raise
    assert capsys.readouterr().out == ""

def test_crashing_check_is_isolated(monkeypatch, capsys, tmp_path):
    """One broken check -> errors.log entry; other checks still answer."""
    monkeypatch.setattr(runtime, "_STATE_DIR", tmp_path)

    def boom(ctx):
        raise RuntimeError("kaput")

    def fine(ctx):
        return "still here"

    monkeypatch.setattr(runtime, "CHECKS", [boom, fine])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"prompt": "anything meaningful here", "session_id": "iso"})))
    gate.main()
    assert "still here" in capsys.readouterr().out
    assert "kaput" in (tmp_path / "errors.log").read_text()

def test_runtime_persists_state_between_prompts(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_STATE_DIR", tmp_path)

    def remember(ctx):
        ctx.state["seen"] = ctx.state.get("seen", 0) + 1
        return None

    monkeypatch.setattr(runtime, "CHECKS", [remember])
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

def test_two_strong_memories_both_inject(graph):
    """Regression for the logged false negative: two near-tied STRONG matches
    are both relevant — the old margin rule read them as noise and went silent."""
    graph.create_resource("Technology", {
        "name": "pyoxigraph",
        "role": "rdflib alternative, quad store bindings",
    })
    graph.save()
    out = recall.recall_memories(Context("pyoxigraph rdflib quad store", "s4"))
    assert out is not None
    assert "Use pyoxigraph over rdflib" in out and "pyoxigraph:" in out

def test_injection_carries_neighbourhood_links(graph):
    graph.create_resource("Project", {"name": "claude-memory-graph"})
    _, decision_iri = graph.find_resource("Decision", "Use pyoxigraph over rdflib")
    _, project_iri = graph.find_resource("Project", "claude-memory-graph")
    graph.create_link(decision_iri, project_iri, "affects", {})
    graph.save()
    out = recall.recall_memories(Context("pyoxigraph rdflib quad store", "s5"))
    assert out is not None and "affects→ Project 'claude-memory-graph'" in out

def test_two_concept_prompt_prefers_memory_covering_both_no_cwd(graph):
    """'arches and the memory graph' must pick the memory that knows BOTH
    concepts — via phrase + coverage evidence, with no cwd relied on."""
    graph.create_resource("Project", {
        "name": "claude-memory-graph",
        "description": "arches inspired memory graph for claude",
    })
    graph.create_resource("Pattern", {
        "name": "arches quartz post_save gotcha",
        "description": "arches graph restore recreates rows, arches signal quirk",
    })
    graph.save()
    out = recall.recall_memories(
        Context("what did we decide about arches and the memory graph?", "s8"))
    assert out is not None and "claude-memory-graph" in out
    assert "quartz" not in out

def test_project_proximity_outranks_other_projects_lexical_match(graph):
    """Regression for the live false positive: 'arches' typed inside the
    memory-graph project injected another project's arches gotcha. A memory
    linked to the CURRENT project must outrank an equally-matching one from
    elsewhere — and shed it from the injection."""
    graph.create_resource("Project", {"name": "claude-memory-graph"})
    graph.create_resource("Pattern", {
        "name": "arches inspired design",
        "description": "arches heritage platform shapes the graph model",
    })
    graph.create_resource("Pattern", {
        "name": "arches quartz gotcha",
        "description": "arches heritage platform post_save quirk elsewhere",
    })
    _, project = graph.find_resource("Project", "claude-memory-graph")
    _, design = graph.find_resource("Pattern", "arches inspired design")
    graph.create_link(design, project, "appliesTo", {})
    graph.save()
    ctx = Context("tell me about the arches heritage platform design",
                  "s6", cwd="claude-memory-graph")
    out = recall.recall_memories(ctx)
    assert out is not None and "arches inspired design" in out
    assert "arches quartz gotcha" not in out

def test_no_project_node_means_no_boost(graph):
    ctx = Context("pyoxigraph rdflib quad store", "s7", cwd="unknown-dir")
    assert recall.recall_memories(ctx) is not None  # prior absent, gate unaffected

def test_decisions_logged(graph):
    recall.recall_memories(Context("pyoxigraph rdflib quad store", "s3"))
    lines = (runtime._STATE_DIR / "injections.jsonl").read_text().strip().splitlines()
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
