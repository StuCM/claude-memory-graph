"""Gap detection (mechanical candidates for reflection) and the pulse report."""

import json
import time

import pytest

import claude_hook_kit.state as kit_state
from claude_hook_kit import HookContext, state_home
from claude_memory_graph import gaps as gaps_mod
from claude_memory_graph.gate.nudge import ContextCounterExtension
from claude_memory_graph.gate.pulse import report as pulse_report
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import reflect as reflect_tool


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "ctx"))
    (tmp_path / "ctx").mkdir()
    return tmp_path / "kit"


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "store")
    s.create_resource("Project", {"name": "charcoal"})
    s.create_resource("Decision", {
        "name": "Use pinia stores",
        "rationale": "pinia gives strict store layout and devtools",
    })
    s.create_resource("Pattern", {
        "name": "charcoal store layout",
        "description": "pinia stores live under src/stores, one per domain",
    })
    return s


# ================= gaps =================

def test_unlinked_pair_sharing_rare_terms_suggested(store):
    g = gaps_mod.analyse(store)
    pairs = {frozenset((a["name"], b["name"])) for _, a, b, _ in g.suggestions}
    assert frozenset(("Use pinia stores", "charcoal store layout")) in pairs
    # the evidence travels with the suggestion
    (_, a, b, shared), = [s for s in g.suggestions
                          if {s[1]["name"], s[2]["name"]}
                          == {"Use pinia stores", "charcoal store layout"}]
    assert "pinia" in shared


def test_linked_pair_not_resuggested(store):
    _, d = store.find_resource("Decision", "Use pinia stores")
    _, p = store.find_resource("Pattern", "charcoal store layout")
    store.create_link(d, p, "manifestsIn", {})
    g = gaps_mod.analyse(store)
    pairs = {frozenset((a["name"], b["name"])) for _, a, b, _ in g.suggestions}
    assert frozenset(("Use pinia stores", "charcoal store layout")) not in pairs


def test_orphans_and_conceptless_reported(store):
    _, d = store.find_resource("Decision", "Use pinia stores")
    _, proj = store.find_resource("Project", "charcoal")
    store.create_link(d, proj, "affects", {})
    g = gaps_mod.analyse(store)
    assert ("Pattern", "charcoal store layout") in g.orphans      # no links at all
    assert ("Decision", "Use pinia stores") in g.conceptless      # linked, no concept
    concept = store.store_concept("Concept", "state management", {})
    store.create_link(d, concept, "hasConcept", {})
    g = gaps_mod.analyse(store)
    assert ("Decision", "Use pinia stores") not in g.conceptless


def test_reflect_carries_gaps_section(store):
    out = reflect_tool.handle(store, None)
    assert "## Gaps" in out and "Orphans" in out


def test_empty_graph_gaps_clean(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "empty")
    assert gaps_mod.analyse(s).empty


# ================= capture logging (pulse's evidence) =================

def stop_ctx(core, state=None):
    core.setdefault("project", "proj")
    core.setdefault("session_id", "s1")
    return HookContext(event="Stop", payload={}, core=core,
                       state=state if state is not None else {})


def _capture_kinds():
    path = state_home() / "capture.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["kind"] for line in path.read_text().splitlines()]


def test_block_and_write_logged_for_pulse(kit_home, tmp_path):
    ext = ContextCounterExtension()
    state = {}
    assert ext.on_stop(stop_ctx({"significant_prompt_count": 5}, state)) is not None
    assert _capture_kinds() == ["block"]
    # the stamped file gets a real append -> next stop observes a write
    files = list((tmp_path / "ctx").glob("proj__*.md"))
    files[0].write_text(files[0].read_text() + "- [10:00] Decision: x\n")
    assert ext.on_stop(stop_ctx({"significant_prompt_count": 5}, state)) is None
    assert _capture_kinds() == ["block", "write"]


# ================= pulse =================

def _seed(name, entries):
    home = state_home()
    home.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    with open(home / name, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps({**e, "ts": now}) + "\n")


def test_pulse_reports_activity(kit_home):
    _seed("injections.jsonl", [
        {"kind": "prime", "fired": True, "session": "s1", "project": "p"},
        {"fired": True, "session": "s1", "nodes": ["Use pinia stores"]},
        {"fired": False, "session": "s1", "top": 1.0, "top_node": "x"},
        {"kind": "log", "fired": True, "session": "s1", "nodes": ["entry"]},
    ])
    _seed("capture.jsonl", [
        {"kind": "block", "cadence": True, "dig": 0, "session": "s1"},
        {"kind": "write", "session": "s1"},
    ])
    _seed("explicit-recalls.jsonl", [
        {"session": "s1", "tool": "memory_recall", "found": True}])
    out = pulse_report(days=1)
    assert "sessions seen: 1" in out
    assert "auto-prime:  fired in 1 session(s)" in out
    assert "graph layer: injected 1/2" in out and "'Use pinia stores' ×1" in out
    assert "log layer:   injected 1" in out
    assert "1 stop block(s)" in out and "1 observed context write(s)" in out
    assert "1 memory tool call(s), 1 found" in out


def test_pulse_diagnoses_dead_hooks(kit_home):
    out = pulse_report(days=1)
    assert "NO ACTIVITY LOGGED" in out and "hooks are not firing" in out


def test_pulse_flags_ignored_blocks(kit_home):
    _seed("capture.jsonl", [{"kind": "block", "cadence": True, "dig": 0, "session": "s1"}])
    _seed("injections.jsonl", [{"fired": False, "session": "s1"}])
    out = pulse_report(days=1)
    assert "no writes are ever observed" in out