import time

import pytest

from claude_hook_kit import HookContext
from claude_memory_graph.hook_extensions import RecallExtension, ContextCounterExtension
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import store_resource


def make_ctx(event, payload=None, core=None, state=None):
    return HookContext(
        event=event,
        payload=payload or {},
        core=core or {},
        state=state if state is not None else {},
        global_state={},
    )


# ----------------------------------------------------------------
# memory-recall
# ----------------------------------------------------------------

@pytest.fixture
def graph_home(tmp_path, monkeypatch):
    store_dir = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(store_dir))
    store = MemoryStore.open_or_create(store_dir)
    store_resource.handle_resource(store, "Project", {"name": "quartz", "status": "active"})
    store.save()
    return store_dir


def test_recall_primes_known_project(graph_home):
    ctx = make_ctx("SessionStart", core={"project": "quartz"})
    out = RecallExtension().on_session_start(ctx)
    assert out is not None and "quartz" in out
    assert ctx.state["primed"] is True


def test_recall_silent_for_unknown_project(graph_home):
    ctx = make_ctx("SessionStart", core={"project": "never-heard-of-it"})
    assert RecallExtension().on_session_start(ctx) is None
    assert "primed" not in ctx.state


def test_recall_primes_once(graph_home):
    ctx = make_ctx("SessionStart", core={"project": "quartz"}, state={"primed": True})
    assert RecallExtension().on_session_start(ctx) is None


# ----------------------------------------------------------------
# context-counter
# ----------------------------------------------------------------

@pytest.fixture
def context_dir(tmp_path, monkeypatch):
    d = tmp_path / "context"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(d))
    monkeypatch.setenv("MEMORY_GRAPH_NUDGE_EVERY", "3")
    return d


def test_nudges_when_no_context_file(context_dir):
    ext = ContextCounterExtension()
    state = {}
    for count in (1, 2):
        ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": count}, state=state)
        assert ext.on_user_prompt_submit(ctx) is None
    ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": 3}, state=state)
    out = ext.on_user_prompt_submit(ctx)
    assert out is not None and "no context file" in out


def test_fresh_write_resets_staleness(context_dir):
    ext = ContextCounterExtension()
    state = {}
    f = context_dir / "quartz__2026-07-02_10-00.md"
    f.write_text("---\ndistilled: false\n---\n")
    ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": 1}, state=state)
    assert ext.on_user_prompt_submit(ctx) is None  # write observed
    for count in (2, 3):
        ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": count}, state=state)
        assert ext.on_user_prompt_submit(ctx) is None
    ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": 4}, state=state)
    out = ext.on_user_prompt_submit(ctx)
    assert out is not None and "3 prompts since" in out
    # an update to the file resets the clock again
    time.sleep(0.01)
    f.write_text("---\ndistilled: false\n---\n- new point\n")
    ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": 5}, state=state)
    assert ext.on_user_prompt_submit(ctx) is None


def test_no_renudge_within_cadence(context_dir):
    ext = ContextCounterExtension()
    state = {"count_at_write": 0, "last_nudge_at": 3}
    ctx = make_ctx("UserPromptSubmit", core={"project": "quartz", "prompt_count": 4}, state=state)
    assert ext.on_user_prompt_submit(ctx) is None  # nudged at 3, cadence 3 -> wait


def test_precompact_always_flushes(context_dir):
    out = ContextCounterExtension().on_pre_compact(make_ctx("PreCompact"))
    assert out is not None and "NOW" in out


def test_session_end_suggests_distill(context_dir):
    for i in range(3):
        (context_dir / f"p__2026-07-0{i + 1}_10-00.md").write_text("---\ndistilled: false\n---\n")
    out = ContextCounterExtension().on_session_end(make_ctx("SessionEnd"))
    assert out is not None and "distill" in out


def test_session_end_quiet_when_distilled(context_dir):
    (context_dir / "p__2026-07-01_10-00.md").write_text("---\ndistilled: true\n---\n")
    assert ContextCounterExtension().on_session_end(make_ctx("SessionEnd")) is None
