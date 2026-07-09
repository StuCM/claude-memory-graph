"""Code-anchor drift flag: recall marks memories whose anchored code moved."""

import subprocess

import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import recall as recall_tool


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "store.py").write_text("v1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v1")
    monkeypatch.chdir(repo)
    return repo


def _anchor_commit(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def store(tmp_path):
    return MemoryStore.open_or_create(tmp_path / "graph")


def _pattern(store, commit):
    store.create_resource("Pattern", {
        "name": "state layout",
        "description": "per-session json",
        "anchorPath": "store.py",
        "anchorCommit": commit,
    })


def test_unchanged_anchor_not_flagged(repo, store):
    _pattern(store, _anchor_commit(repo))
    out = recall_tool.handle(store, "Pattern", "state layout", 1)
    assert "code changed since" not in out


def test_drifted_anchor_flagged(repo, store):
    commit = _anchor_commit(repo)
    _pattern(store, commit)
    (repo / "store.py").write_text("v2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v2")
    out = recall_tool.handle(store, "Pattern", "state layout", 1)
    assert f"(code changed since {commit[:7]})" in out


def test_other_file_change_not_flagged(repo, store):
    _pattern(store, _anchor_commit(repo))
    (repo / "other.py").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "other")
    out = recall_tool.handle(store, "Pattern", "state layout", 1)
    assert "code changed since" not in out


def test_drift_detected_from_subdirectory(repo, store, monkeypatch):
    """anchorPath is repo-relative; a session cwd'd into a subdirectory must
    still resolve the pathspec from the repo root."""
    commit = _anchor_commit(repo)
    _pattern(store, commit)
    (repo / "sub").mkdir()
    (repo / "store.py").write_text("v2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v2")
    monkeypatch.chdir(repo / "sub")
    out = recall_tool.handle(store, "Pattern", "state layout", 1)
    assert f"(code changed since {commit[:7]})" in out


def test_no_repo_fails_open(tmp_path, monkeypatch, store):
    monkeypatch.chdir(tmp_path)  # not a git repo
    _pattern(store, "deadbeef")
    out = recall_tool.handle(store, "Pattern", "state layout", 1)
    assert "state layout" in out and "code changed since" not in out


def test_unanchored_memory_untouched(repo, store):
    store.create_resource("Decision", {"name": "x over y", "rationale": "r"})
    out = recall_tool.handle(store, "Decision", "x over y", 1)
    assert "code changed since" not in out
