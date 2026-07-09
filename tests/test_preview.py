"""Gate preview: the real injection math, zero side effects."""

import pytest

import claude_hook_kit.state as kit_state
from claude_hook_kit import state_home
from claude_memory_graph.gate.preview import preview
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "ctx"))
    (tmp_path / "ctx").mkdir()
    store = MemoryStore.open_or_create(tmp_path / "store")
    store.create_resource("Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs",
    })
    store.create_resource("Person", {"name": "Stuart Marshall", "role": "developer"})
    store.save()
    return tmp_path


def test_preview_shows_inject_verdict_with_scores():
    out = preview("why did we pick pyoxigraph over rdflib?")
    assert "INJECTS 1 node(s)" in out
    assert "Use pyoxigraph over rdflib" in out
    assert "≥ABS_MIN" in out and "IN GROUP" in out


def test_preview_explains_silence():
    out = preview("run the linter again")
    assert "SILENT" in out and "INJECTS" not in out


def test_preview_covers_session_log_layer(env):
    (env / "ctx" / "proj__2026-07-01_10-00.md").write_text(
        "---\ndistilled: false\n---\n\n## Key Points\n\n"
        "- [10:05] Pattern: rocksdb exclusive lock gotcha\n"
        "  description: rocksdb store holds a per-process lock\n")
    out = preview("the rocksdb exclusive lock problem", project="proj")
    assert "SESSION-LOG LAYER (1 undistilled entry" in out
    assert "rocksdb exclusive lock gotcha" in out and "WOULD INJECT" in out


def test_preview_writes_no_logs(env):
    preview("why pyoxigraph over rdflib?")
    assert not (state_home() / "injections.jsonl").exists()


def test_trivial_prompt_short_circuits():
    out = preview("thanks, ok!")
    assert "trivial prompt" in out
