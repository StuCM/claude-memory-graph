"""Recall reads a cached snapshot instead of opening the store per prompt."""

import re

import pytest

import claude_hook_kit.state as kit_state
from claude_hook_kit import HookContext
from claude_memory_graph.gate import recall
from claude_memory_graph.gate.recall import RecallExtension
from claude_memory_graph.store import MemoryStore


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "empty-context"))


@pytest.fixture
def graph(tmp_path, monkeypatch):
    d = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(d))
    store = MemoryStore.open_or_create(d)
    proj_id, proj = store.create_resource("Project", {"name": "quartzproj"})
    _, dec = store.create_resource("Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs"})
    _, tech = store.create_resource("Technology", {"name": "pyoxigraph", "description": "rdf quad store"})
    _, other = store.create_resource("Pattern", {"name": "zebra stripes", "description": "unrelated zebra pattern"})
    store.create_link(dec, tech, "uses", {})
    store.create_link(proj, dec, "decided", {})
    store.save()
    return store


def run(prompt, project="quartzproj"):
    ctx = HookContext(event="UserPromptSubmit", payload={"prompt": prompt},
                      core={"project": project, "session_id": "s"}, state={})
    return RecallExtension().on_user_prompt_submit(ctx)


PROMPT = "why did we choose pyoxigraph over rdflib for the quad store?"


def snapshot_file(tmp_path):
    return tmp_path / "store" / recall.SNAPSHOT_NAME


def test_snapshot_output_equals_fresh_build(graph, tmp_path):
    first = run(PROMPT)  # builds and writes the snapshot
    assert first and "pyoxigraph" in first
    assert snapshot_file(tmp_path).exists()
    assert run(PROMPT) == first
    snapshot_file(tmp_path).unlink()
    assert run(PROMPT) == first


def test_links_match_store_recall(graph):
    snap = recall._snapshot()
    for d in snap["docs"]:
        result = graph.recall(__import__("pyoxigraph").NamedNode(d["iri"]), d["gid"], depth=1)
        want = sorted(f"{lr.relation}→ {lr.model} '{lr.properties.get('name', '')}'"
                      for lr in result.linked)
        got = sorted(re.findall(r"[^(·]+→ \w+ '[^']*'", snap["links"].get(d["iri"], "")))
        assert [g.strip() for g in got] == want


def test_valid_snapshot_does_not_open_the_store(graph, monkeypatch):
    first = run(PROMPT)

    def boom(*a, **k):
        raise AssertionError("store opened")
    monkeypatch.setattr(MemoryStore, "open_or_create", boom)
    assert run(PROMPT) == first


def test_store_write_invalidates_snapshot(graph, tmp_path):
    run(PROMPT)
    graph.create_resource("Decision", {"name": "Adopt flurbonium", "rationale": "flurbonium rocks"})
    graph.save()
    assert run("tell me about flurbonium") is not None
    assert any(d["name"] == "Adopt flurbonium" for d in recall._read_snapshot(recall._generation())["docs"])


def test_corrupt_snapshot_falls_back(graph, tmp_path):
    first = run(PROMPT)
    snapshot_file(tmp_path).write_text('{"version": 1, "gener')
    assert run(PROMPT) == first
    assert recall._read_snapshot(recall._generation()) is not None  # rewritten


def test_wrong_shape_snapshot_falls_back(graph, tmp_path):
    first = run(PROMPT)
    snapshot_file(tmp_path).write_text("[1, 2]")
    assert run(PROMPT) == first
