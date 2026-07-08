"""Session-context recall: the log as a per-prompt retrieval source."""

import os
import time

import pytest

from claude_hook_kit import HookContext
import claude_hook_kit.state as kit_state
from claude_memory_graph.gate.recall import RecallExtension
from claude_memory_graph.store import MemoryStore

ENTRY = """---
created: 2026-07-01T10:00
distilled: false
summary: "s"
---

## Key Points

- [10:05] Decision: Use pyoxigraph over rdflib
  rationale: native quad store beats rdflib for named graphs
  aliases: rdf store choice
- [10:20] Pattern: rocksdb exclusive lock gotcha
  description: rocksdb store holds a per-process lock, multi-session breaks
"""


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    return tmp_path / "kit"


@pytest.fixture
def context_dir(tmp_path, monkeypatch):
    d = tmp_path / "context"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(d))
    return d


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    return MemoryStore.open_or_create(tmp_path / "store")


def ctx(prompt, state=None, core=None, project="proj"):
    core = core if core is not None else {}
    core.setdefault("project", project)
    core.setdefault("session_id", "s1")
    core.setdefault("started_at", "2026-07-06T12:00:00Z")  # after the file below
    return HookContext(event="UserPromptSubmit", payload={"prompt": prompt},
                       core=core, state=state if state is not None else {})


def _old_file(context_dir, name="proj__2026-07-01_10-00.md", text=ENTRY):
    path = context_dir / name
    path.write_text(text)
    # another session's file: untouched since before this session started
    old = time.mktime((2026, 7, 1, 10, 30, 0, 0, 0, -1))
    os.utime(path, (old, old))
    return path


def test_other_sessions_entries_inject_on_match(context_dir, empty_store):
    _old_file(context_dir)
    out = RecallExtension().on_user_prompt_submit(
        ctx("why did we pick pyoxigraph over rdflib for the quad store?"))
    assert out is not None
    assert "Session log (undistilled" in out
    assert "Use pyoxigraph over rdflib" in out
    assert "proj__2026-07-01_10-00.md" in out


def test_log_recall_stays_silent_on_generic_prompt(context_dir, empty_store):
    _old_file(context_dir)
    assert RecallExtension().on_user_prompt_submit(ctx("run the linter again")) is None


def test_own_session_file_needs_compaction(context_dir, empty_store):
    path = context_dir / "proj__2026-07-06_12-05.md"
    path.write_text(ENTRY)  # mtime now = written during this session
    base = {"events": {}}
    assert RecallExtension().on_user_prompt_submit(
        ctx("why pyoxigraph over rdflib quad store?", core=dict(base))) is None
    # after a compaction the conversation that wrote it is gone -> eligible
    core = {"events": {"PreCompact": 1}}
    out = RecallExtension().on_user_prompt_submit(
        ctx("why pyoxigraph over rdflib quad store?", core=core))
    assert out is not None and "pyoxigraph" in out


def test_entry_injects_once_per_session(context_dir, empty_store):
    _old_file(context_dir)
    state = {}
    q = "why pyoxigraph over rdflib quad store?"
    assert RecallExtension().on_user_prompt_submit(ctx(q, state=state)) is not None
    assert RecallExtension().on_user_prompt_submit(ctx(q, state=state)) is None


def test_graph_and_log_sections_combine(context_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    store = MemoryStore.open_or_create(tmp_path / "store")
    store.create_resource("Decision", {
        "name": "Save after every mutation",
        "rationale": "pyoxigraph rdflib quad store dies ungracefully",
    })
    store.save()
    _old_file(context_dir)
    out = RecallExtension().on_user_prompt_submit(
        ctx("pyoxigraph rdflib quad store"))
    assert out is not None
    assert "Relevant memory" in out           # graph section
    assert "Session log (undistilled" in out  # log section, shared budget


def test_distilled_files_leave_the_corpus(context_dir, empty_store):
    _old_file(context_dir, text=ENTRY.replace("distilled: false", "distilled: true"))
    assert RecallExtension().on_user_prompt_submit(
        ctx("why pyoxigraph over rdflib quad store?")) is None
