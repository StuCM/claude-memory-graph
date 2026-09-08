"""Doctor: one-shot wiring diagnosis."""

import json
import time

import pytest

import claude_hook_kit.state as kit_state
from claude_hook_kit import state_home
from claude_memory_graph.gate.doctor import report
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "ctx"))
    (tmp_path / "ctx").mkdir()
    return tmp_path


def _log(name, entries):
    home = state_home()
    home.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    with open(home / name, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps({**e, "ts": now}) + "\n")


def test_dead_hooks_and_empty_graph_diagnosed(env):
    MemoryStore.open_or_create(env / "store").save()
    out = report()
    assert "hooks are not firing" in out
    assert "graph is EMPTY" in out
    assert "✗ FAIL" in out
    # it shows the paths so a mismatch is visible
    assert str(env / "store") in out and str(env / "kit") in out


def test_orphan_graph_diagnosed(env):
    store = MemoryStore.open_or_create(env / "store")
    store.create_resource("Decision", {"name": "Use pinia", "rationale": "layout"})
    store.create_resource("Pattern", {"name": "store layout", "description": "x"})
    store.save()
    _log("injections.jsonl", [{"fired": True, "nodes": ["Use pinia"]}])
    _log("capture.jsonl", [{"kind": "block", "cadence": True, "dig": 0}])
    out = report()
    assert "NONE are linked" in out or "no links" in out
    assert "reflect" in out


def test_healthy_reports_clean(env):
    store = MemoryStore.open_or_create(env / "store")
    store.create_resource("Project", {"name": "charcoal"})
    store.create_resource("Decision", {"name": "Use pinia", "rationale": "layout"})
    _, d = store.find_resource("Decision", "Use pinia")
    _, p = store.find_resource("Project", "charcoal")
    store.create_link(d, p, "affects", {})
    store.save()
    _log("injections.jsonl", [{"fired": True, "nodes": ["Use pinia"]}])
    _log("capture.jsonl", [{"kind": "block", "cadence": True, "dig": 0},
                           {"kind": "write"}])
    out = report()
    assert "Everything looks wired" in out
    assert "✗ FAIL" not in out


def test_dig_blocks_without_writes_flagged(env):
    store = MemoryStore.open_or_create(env / "store")
    store.create_resource("Project", {"name": "charcoal"})
    store.save()
    _log("injections.jsonl", [{"fired": False}])
    _log("capture.jsonl", [{"kind": "block", "cadence": False, "dig": 9}])
    out = report()
    assert "not writing them" in out


def test_env_mismatch_surfaced(env, monkeypatch):
    MemoryStore.open_or_create(env / "store").save()
    out = report()
    assert "MEMORY_GRAPH_PATH is set" in out  # doctor warns the shell env must match
