"""Periodic graph self-review: the timer fires, the numbers are real, and a
clean graph stays silent."""

import time

import pytest

from claude_hook_kit import HookContext
import claude_hook_kit.state as kit_state
from claude_memory_graph.gate.review import ReviewExtension
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    """Isolated hook-kit home AND context dir — the capture-shape detector
    reads the context log, so without this the real ~/.claude/context/ leaks
    into every assertion here."""
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    context = tmp_path / "context"
    context.mkdir()
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(context))
    return context


@pytest.fixture
def graph(tmp_path, monkeypatch):
    store_dir = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(store_dir))
    return MemoryStore.open_or_create(store_dir)


def stop_ctx(state=None, global_state=None):
    return HookContext(event="Stop", payload={}, core={"project": "proj"},
                       state=state if state is not None else {},
                       global_state=global_state if global_state is not None else {})


def test_empty_graph_says_nothing(graph):
    graph.save()
    assert ReviewExtension().on_stop(stop_ctx()) is None


def test_sentence_shaped_names_are_reported(graph):
    graph.create_resource("Pattern", {
        "name": "the log layer no longer repeats a memory the graph just injected",
        "description": "d"})
    graph.save()
    reason = ReviewExtension().on_stop(stop_ctx())
    assert reason is not None
    assert "over the word ceiling" in reason and "/memory-graph:reflect" in reason


def test_review_is_silent_until_the_period_elapses(graph):
    graph.create_resource("Pattern", {
        "name": "the log layer no longer repeats a memory the graph just injected",
        "description": "d"})
    graph.save()
    global_state = {}
    assert ReviewExtension().on_stop(stop_ctx({}, global_state)) is not None
    assert global_state["last_review"] > 0
    # a fresh session, same machine: the cross-session clock still holds
    assert ReviewExtension().on_stop(stop_ctx({}, global_state)) is None
    global_state["last_review"] = time.time() - 8 * 86400
    assert ReviewExtension().on_stop(stop_ctx({}, global_state)) is not None


def test_stop_hook_active_never_chains(graph):
    graph.create_resource("Pattern", {"name": "a b c d e f g h", "description": "d"})
    graph.save()
    ctx = HookContext(event="Stop", payload={"stop_hook_active": True},
                      core={"project": "proj"}, state={}, global_state={})
    assert ReviewExtension().on_stop(ctx) is None


def test_narrative_heavy_log_is_reported(graph, kit_home):
    """The capture-quality number: a log the mechanical lane cannot promote
    is the defect that precedes every distill backlog."""
    graph.save()
    (kit_home / "proj__2026-09-09_10-00.md").write_text(
        "---\ncreated: 2026-09-09T10:00\ndistilled: false\n---\n\n"
        "## Key Points\n\n"
        "- [10:00] Problem: one\n- [10:01] Problem: two\n- [10:02] Problem: three\n"
        "- [10:03] Decision: keep it\n  rationale: because\n")
    reason = ReviewExtension().on_stop(stop_ctx())
    assert reason is not None and "structured shape" in reason
