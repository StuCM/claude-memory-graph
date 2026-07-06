import json

import pytest

from claude_hook_kit import HookContext, terms, terms_pos, state_home
import claude_hook_kit.state as kit_state
from claude_memory_graph.gate import runtime
from claude_memory_graph.gate.recall import RecallExtension, _bigrams, _score
from claude_memory_graph.gate.nudge import ContextCounterExtension
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    """Isolated hook-kit home (state, injections.jsonl, errors.log)."""
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    return tmp_path / "kit"


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Seeded store; the gate reads via MEMORY_GRAPH_PATH."""
    store_dir = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(store_dir))
    store = MemoryStore.open_or_create(store_dir)
    store.create_resource("Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs",
    })
    store.create_resource("Person", {"name": "Stuart Marshall", "role": "developer"})
    store.save()
    return store


def prompt_ctx(prompt, state=None, project="", event="UserPromptSubmit", core=None):
    """A HookContext the way the dispatcher would build it."""
    core = core if core is not None else {}
    core.setdefault("project", project)
    return HookContext(
        event=event,
        payload={"prompt": prompt, "cwd": f"/home/user/{project}" if project else ""},
        core=core,
        state=state if state is not None else {},
    )


# ================= recall scoring =================

def _doc():
    return {"name": "charcoal", "desc": "dc03 harness",
            "name_terms": {"charcoal"}, "terms": {"dc03", "harness"}}

def test_generic_prompt_stays_silent():
    idf = {"dc03": 4.0, "harness": 3.0}
    assert _score(set(terms("thanks, run the tests")), _doc(), idf) == 0.0

def test_specific_prompt_scores():
    idf = {"dc03": 4.0, "harness": 3.0}
    score = _score(set(terms("fix the dc03 harness")), _doc(), idf)
    assert score >= runtime.config()["ABS_MIN"]

def test_phrase_needs_original_adjacency():
    """'memory graph' is a phrase; 'memory of the whole graph' is not —
    stopword-stripping must not manufacture adjacency."""
    assert ("memory", "graph") in _bigrams(terms_pos("the memory graph"))
    assert ("memory", "graph") not in _bigrams(terms_pos("memory of the whole graph"))

def test_config_file_overrides_defaults(monkeypatch, tmp_path):
    cfg_file = tmp_path / "gate.json"
    cfg_file.write_text('{"N_TURNS": 1, "ABS_MIN": 99}')
    monkeypatch.setattr(runtime, "_CONFIG_PATH", cfg_file)
    monkeypatch.setattr(runtime, "_config", None)  # drop the cache
    assert runtime.config()["N_TURNS"] == 1
    assert runtime.config()["ABS_MIN"] == 99
    assert runtime.config()["MARGIN"] == 1.5  # untouched keys keep defaults


# ================= recall extension =================

def recall_on(prompt, state=None, project=""):
    return RecallExtension().on_user_prompt_submit(prompt_ctx(prompt, state, project))

def test_gate_fires_on_distinct_entity(graph):
    out = recall_on("remind me about pyoxigraph vs rdflib quad store")
    assert out is not None and "Use pyoxigraph over rdflib" in out

def test_gate_silent_on_generic_prompt(graph):
    assert recall_on("run the linter again") is None

def test_gate_indexes_rationale_not_just_description(graph):
    # the Decision has no 'description' property — rationale must still match
    assert recall_on("something about named graphs and the quad store rdflib pyoxigraph") is not None

def test_session_memo_prevents_reinjection(graph):
    state = {}  # same extension state across prompts, as the dispatcher persists it
    assert recall_on("pyoxigraph rdflib quad store", state) is not None
    assert recall_on("pyoxigraph rdflib quad store", state) is None  # memo hit

def test_two_strong_memories_both_inject(graph):
    """Regression for the logged false negative: two near-tied STRONG matches
    are both relevant — the old margin rule read them as noise and went silent."""
    graph.create_resource("Technology", {
        "name": "pyoxigraph",
        "role": "rdflib alternative, quad store bindings",
    })
    graph.save()
    out = recall_on("pyoxigraph rdflib quad store")
    assert out is not None
    assert "Use pyoxigraph over rdflib" in out and "pyoxigraph:" in out

def test_injection_carries_neighbourhood_links(graph):
    graph.create_resource("Project", {"name": "claude-memory-graph"})
    _, decision_iri = graph.find_resource("Decision", "Use pyoxigraph over rdflib")
    _, project_iri = graph.find_resource("Project", "claude-memory-graph")
    graph.create_link(decision_iri, project_iri, "affects", {})
    graph.save()
    out = recall_on("pyoxigraph rdflib quad store")
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
    out = recall_on("what did we decide about arches and the memory graph?")
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
    out = recall_on("tell me about the arches heritage platform design",
                    project="claude-memory-graph")
    assert out is not None and "arches inspired design" in out
    assert "arches quartz gotcha" not in out

def test_no_project_node_means_no_boost(graph):
    out = recall_on("pyoxigraph rdflib quad store", project="unknown-dir")
    assert out is not None  # prior absent, gate unaffected

def test_decisions_logged(graph):
    recall_on("pyoxigraph rdflib quad store")
    lines = (state_home() / "injections.jsonl").read_text().strip().splitlines()
    assert any(json.loads(line)["fired"] for line in lines)


# ================= recall auto-prime (SessionStart) =================

def test_auto_prime_on_known_project(graph):
    graph.create_resource("Project", {"name": "claude-memory-graph", "status": "active"})
    graph.save()
    ctx = prompt_ctx("", event="SessionStart", project="claude-memory-graph")
    out = RecallExtension().on_session_start(ctx)
    assert out is not None and "claude-memory-graph" in out
    assert ctx.state["primed"] is True
    assert RecallExtension().on_session_start(ctx) is None  # primes once

def test_auto_prime_silent_for_unknown_project(graph):
    ctx = prompt_ctx("", event="SessionStart", project="never-heard-of-it")
    assert RecallExtension().on_session_start(ctx) is None


# ================= miss detector: explicit-recall log =================

def tool_ctx(tool_name, tool_input, tool_response, session="s1"):
    return HookContext(
        event="PostToolUse",
        payload={"tool_name": tool_name, "tool_input": tool_input,
                 "tool_response": tool_response},
        core={"session_id": session, "project": "quartz"},
        state={},
    )


def _recall_log():
    path = state_home() / "explicit-recalls.jsonl"
    return [json.loads(line) for line in path.read_text().strip().splitlines()]


def test_explicit_recall_logged_with_target():
    out = RecallExtension().on_post_tool_use(tool_ctx(
        "mcp__memory-graph__memory_recall",
        {"model": "Decision", "name": "Use pyoxigraph over rdflib", "depth": 2},
        "Decision 'Use pyoxigraph over rdflib' — rationale: ...",
    ))
    assert out is None  # telemetry only, never injects
    entry = _recall_log()[-1]
    assert entry["tool"] == "memory_recall"
    assert entry["target"] == "Decision/Use pyoxigraph over rdflib"
    assert entry["found"] is True
    assert entry["session"] == "s1"


def test_explicit_recall_not_found_flagged():
    RecallExtension().on_post_tool_use(tool_ctx(
        "mcp__memory-graph__memory_recall",
        {"model": "Decision", "name": "nonexistent"},
        "Error: Decision 'nonexistent' not found",
    ))
    assert _recall_log()[-1]["found"] is False


def test_query_tool_logs_sparql():
    RecallExtension().on_post_tool_use(tool_ctx(
        "mcp__memory-graph__memory_query",
        {"sparql": "SELECT ?n WHERE { GRAPH ?g { ?n rdf:type mem:Decision } }"},
        '[{"n": "mem:resource/abc"}]',
    ))
    entry = _recall_log()[-1]
    assert entry["tool"] == "memory_query" and entry["sparql"].startswith("SELECT")


def test_non_memory_tools_ignored(kit_home):
    RecallExtension().on_post_tool_use(tool_ctx("Edit", {"file_path": "x"}, "ok"))
    assert not (state_home() / "explicit-recalls.jsonl").exists()


# ================= miss detector: the join =================

from claude_memory_graph.gate import misses as misses_mod
from claude_hook_kit import append_jsonl


def _seed_logs(entries_decisions, entries_recalls):
    for e in entries_decisions:
        append_jsonl("injections.jsonl", dict(e))
    for e in entries_recalls:
        append_jsonl("explicit-recalls.jsonl", dict(e))


def _with_ts(entry, ts):
    # append_jsonl stamps now(); rewrite files with controlled timestamps instead
    return {**entry, "ts": ts}


def _write_jsonl(name, entries):
    path = state_home() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_silence_then_found_recall_is_a_miss():
    _write_jsonl("injections.jsonl", [_with_ts(
        {"fired": False, "top": 2.7, "rest": 1.1, "top_node": "Save after every mutation",
         "session": "s1", "terms": ["save", "mutation"]}, 1000)])
    _write_jsonl("explicit-recalls.jsonl", [_with_ts(
        {"session": "s1", "tool": "memory_recall",
         "target": "Decision/Save after every mutation", "found": True}, 1060)])
    result = misses_mod.analyse()
    assert len(result["misses"]) == 1 and not result["gaps"]
    out = misses_mod.report()
    assert "MISS" in out and "2.7" in out and "Save after every mutation" in out
    assert "threshold miss" in out  # 2.7 is within 70% of ABS_MIN 3.0


def test_low_score_miss_classified_as_vocabulary():
    _write_jsonl("injections.jsonl", [_with_ts(
        {"fired": False, "top": 0.4, "top_node": "x", "session": "s1", "terms": ["db"]}, 1000)])
    _write_jsonl("explicit-recalls.jsonl", [_with_ts(
        {"session": "s1", "tool": "memory_recall",
         "target": "Pattern/RocksDB exclusive lock", "found": True}, 1030)])
    assert "vocabulary miss" in misses_mod.report()


def test_recall_after_fired_injection_is_not_a_miss():
    _write_jsonl("injections.jsonl", [_with_ts(
        {"fired": True, "top": 6.0, "session": "s1",
         "nodes": ["Use pyoxigraph over rdflib"], "terms": ["pyoxigraph"]}, 1000)])
    _write_jsonl("explicit-recalls.jsonl", [_with_ts(
        {"session": "s1", "tool": "memory_recall",
         "target": "Decision/Use pyoxigraph over rdflib", "found": True}, 1030)])
    result = misses_mod.analyse()
    assert not result["misses"] and not result["gaps"]


def test_not_found_recall_is_a_capture_gap_not_a_miss():
    _write_jsonl("injections.jsonl", [_with_ts(
        {"fired": False, "top": 0.0, "top_node": "", "session": "s1", "terms": ["deploy"]}, 1000)])
    _write_jsonl("explicit-recalls.jsonl", [_with_ts(
        {"session": "s1", "tool": "memory_recall",
         "target": "Decision/deploy pipeline choice", "found": False}, 1030)])
    result = misses_mod.analyse()
    assert not result["misses"] and len(result["gaps"]) == 1
    assert "CAPTURE GAP" in misses_mod.report()


def test_recall_outside_window_or_session_not_joined():
    _write_jsonl("injections.jsonl", [
        _with_ts({"fired": False, "top": 2.7, "top_node": "n", "session": "s1",
                  "terms": ["x"]}, 1000)])
    _write_jsonl("explicit-recalls.jsonl", [
        _with_ts({"session": "s1", "tool": "memory_recall", "target": "M/n",
                  "found": True}, 1000 + misses_mod.WINDOW_SECONDS + 60),
        _with_ts({"session": "OTHER", "tool": "memory_recall", "target": "M/n",
                  "found": True}, 1030),
    ])
    result = misses_mod.analyse()
    assert not result["misses"] and not result["gaps"]


# ================= nudge extension =================

@pytest.fixture
def context_dir(tmp_path, monkeypatch):
    d = tmp_path / "context"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(d))
    return d


def nudge_seq(prompts, state, core, project="proj"):
    """Feed prompts through the extension the way the dispatcher would:
    core significant count advances only on significant prompts."""
    ext = ContextCounterExtension()
    results = []
    for p in prompts:
        if terms(p):
            core["significant_prompt_count"] = core.get("significant_prompt_count", 0) + 1
        results.append(ext.on_user_prompt_submit(prompt_ctx(p, state, project, core=core)))
    return results

def test_nudge_fires_on_third_significant_turn(context_dir):
    state, core = {}, {}
    results = nudge_seq([
        "design the dc03 harness merge",
        "fix the csv export path bug",
        "add the print view route",   # 3rd significant -> nudge
        "thanks",                      # trivial, no count, no nudge
    ], state, core)
    assert results[0] is None and results[1] is None
    assert results[2] is not None
    assert results[3] is None

def test_nudge_cadence_resets_after_firing(context_dir):
    state, core = {}, {}
    results = nudge_seq([
        "alpha beta gamma", "delta epsilon", "zeta eta",  # fires on 3rd
        "theta iota",                                      # 4th: fresh cycle
    ], state, core)
    assert results[2] is not None and results[3] is None

def test_context_write_resets_cadence(context_dir):
    """A model that just updated the log isn't overdue — an observed mtime
    change resets the counter baseline."""
    state, core = {}, {}
    nudge_seq(["alpha beta", "gamma delta"], state, core)          # 2 significant
    (context_dir / "proj__2026-07-05_10-00.md").write_text("---\ndistilled: false\n---\n")
    results = nudge_seq(["epsilon zeta"], state, core)             # write observed -> reset
    assert results == [None]
    results = nudge_seq(["eta theta", "iota kappa", "lambda mu"], state, core)
    assert results[-1] is not None  # 3 significant past the write -> nudge again

def test_precompact_always_flushes(context_dir):
    out = ContextCounterExtension().on_pre_compact(prompt_ctx("", event="PreCompact"))
    assert out is not None and "NOW" in out

def test_session_end_suggests_distill(context_dir):
    for i in range(3):
        (context_dir / f"p__2026-07-0{i + 1}_10-00.md").write_text("---\ndistilled: false\n---\n")
    out = ContextCounterExtension().on_session_end(prompt_ctx("", event="SessionEnd"))
    assert out is not None and "distill" in out

def test_session_end_quiet_when_distilled(context_dir):
    (context_dir / "p__2026-07-01_10-00.md").write_text("---\ndistilled: true\n---\n")
    assert ContextCounterExtension().on_session_end(prompt_ctx("", event="SessionEnd")) is None
