import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph import viz


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    yield s


def test_extract_nodes_edges_and_degree(store):
    _, proj = store.create_resource("Project", {"name": "proj", "description": "a project"})
    _, tech = store.create_resource("Technology", {"name": "tech"})
    concept = store.store_concept("Constraint", "a gotcha", {})
    store.create_link(proj, tech, "uses", {})
    store.create_link(proj, concept, "hasConstraint", {})

    data = viz.extract(store)

    by_label = {n["label"]: n for n in data["nodes"]}
    assert by_label["proj"]["type"] == "Project"
    assert by_label["proj"]["kind"] == "resource"
    assert by_label["proj"]["desc"] == "a project"
    assert by_label["proj"]["deg"] == 2
    assert by_label["a gotcha"]["kind"] == "concept"
    # schema nodes (RelationType etc.) never appear
    assert all(n["type"] not in ("RelationType", "ConceptType") for n in data["nodes"])
    assert {e["rel"] for e in data["edges"]} == {"uses", "hasConstraint"}


def test_closed_edges_excluded(store):
    _, a = store.create_resource("Project", {"name": "a"})
    _, b = store.create_resource("Project", {"name": "b"})
    store.create_link(a, b, "relatesTo", {"linkValidTo": "2026-01-01T00:00:00Z"})
    assert viz.extract(store)["edges"] == []


def test_handle_writes_selfcontained_html(store, tmp_path):
    _, _ = store.create_resource("Project", {"name": "p"})
    out = tmp_path / "viz.html"
    msg = viz.handle(store, out, open_browser=False)
    html = out.read_text()
    assert "1 nodes" in msg
    assert "__GRAPH_DATA__" not in html
    assert '"label": "p"' in html or '"label":"p"' in html
