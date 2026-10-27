"""Per-node usage, derived from telemetry rather than written onto nodes."""

import json

import pytest

import claude_memory_graph.hookcore.state as kit_state
from claude_memory_graph.hookcore import state_home
from claude_memory_graph.gate import usage
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.STATE_HOME_ENV, str(tmp_path / "kit"))
    home = state_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "store")
    s.create_resource("Project", {"name": "quartz"})
    s.create_resource("Pattern", {"name": "never reached", "description": "d"})
    s.save()
    return s


def _log(home, name, rows):
    (home / name).write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_counts_merge_ambient_and_explicit(kit_home):
    _log(kit_home, "injections.jsonl", [{"ts": 9e9, "nodes": ["quartz", "quartz"]}])
    _log(kit_home, "explicit-recalls.jsonl", [{"ts": 9e9, "target": "Project/quartz"}])
    ambient, explicit = usage.counts()
    assert ambient["quartz"] == 2 and explicit["quartz"] == 1


def test_explicit_target_loses_its_model_prefix(kit_home):
    """Ambient counts have no model prefix, so the two must agree on the key
    or the same node shows up twice."""
    _log(kit_home, "explicit-recalls.jsonl", [{"ts": 9e9, "target": "Decision/Use pyoxigraph"}])
    _, explicit = usage.counts()
    assert list(explicit) == ["Use pyoxigraph"]


def test_report_separates_cold_from_unreachable(store, kit_home):
    """A node with no concept link never had a chance at ambient recall —
    that is a repair, not evidence of staleness."""
    _log(kit_home, "injections.jsonl", [{"ts": 9e9, "nodes": ["quartz"]}])
    out = usage.report(store)
    assert "1/2 nodes reached" in out
    assert "no concept link" in out


def test_window_excludes_older_entries(kit_home):
    _log(kit_home, "injections.jsonl", [{"ts": 1.0, "nodes": ["ancient"]}])
    ambient, _ = usage.counts(days=7)
    assert not ambient
