"""Recall reads a cached snapshot instead of opening the store per prompt."""

import json
import re
import sqlite3

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


def snapshot_docs(db):
    return [json.loads(raw) for (raw,) in db.execute("SELECT doc FROM docs")]


def snapshot_links(db):
    return dict(db.execute("SELECT iri, text FROM links"))


def test_snapshot_output_equals_fresh_build(graph, tmp_path):
    first = run(PROMPT)  # builds and writes the snapshot
    assert first and "pyoxigraph" in first
    assert snapshot_file(tmp_path).exists()
    assert run(PROMPT) == first
    snapshot_file(tmp_path).unlink()
    assert run(PROMPT) == first


def test_links_match_store_recall(graph):
    db = recall._snapshot()
    links = snapshot_links(db)
    for d in snapshot_docs(db):
        result = graph.recall(__import__("pyoxigraph").NamedNode(d["iri"]), d["gid"], depth=1)
        want = sorted(f"{lr.relation}→ {lr.model} '{lr.properties.get('name', '')}'"
                      for lr in result.linked)
        got = sorted(re.findall(r"[^(·]+→ \w+ '[^']*'", links.get(d["iri"], "")))
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
    assert any(d["name"] == "Adopt flurbonium" for d in snapshot_docs(recall._read_snapshot(recall._generation())))


def test_corrupt_snapshot_falls_back(graph, tmp_path):
    first = run(PROMPT)
    snapshot_file(tmp_path).write_text('{"version": 1, "gener')
    assert run(PROMPT) == first
    assert recall._read_snapshot(recall._generation()) is not None  # rewritten


def test_wrong_shape_snapshot_falls_back(graph, tmp_path):
    first = run(PROMPT)
    snapshot_file(tmp_path).write_text("[1, 2]")
    assert run(PROMPT) == first


def test_missing_table_falls_back(graph, tmp_path):
    first = run(PROMPT)
    with sqlite3.connect(snapshot_file(tmp_path)) as db:
        db.execute("DROP TABLE meta")
    assert run(PROMPT) == first


def test_phrase_gap_change_invalidates(graph, monkeypatch):
    before = recall._generation()
    monkeypatch.setitem(recall.config(), "PHRASE_GAP", 5)
    assert recall._generation() != before


def test_link_cap_and_forgotten_targets(graph):
    import pyoxigraph as ox
    hub_id, hub = graph.create_resource("Project", {"name": "hub"})
    for i in range(5):
        _, n = graph.create_resource("Pattern", {"name": f"leaf{i}"})
        graph.create_link(hub, n, "has", {})
    gone_id, gone = graph.create_resource("Pattern", {"name": "gone"})
    graph.create_link(hub, gone, "has", {})
    graph.forget_resource(gone, gone_id, "x")
    graph.save()
    links = snapshot_links(recall._snapshot())[hub.value]
    assert links.count("has→") == 3 and links.endswith("· +2 more)") and "gone" not in links
