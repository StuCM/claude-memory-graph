import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import search, store_resource


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    store_resource.handle_resource(s, "Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs",
    })
    store_resource.handle_resource(s, "Pattern", {
        "name": "RocksDB exclusive lock",
        "description": "RocksDB takes an exclusive per-process lock",
        "aliases": "db locking, database lock",
    })
    store_resource.handle_resource(s, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_concept(s, "Skill", "rust", {})
    return s


def test_exact_name_terms_rank_first(store):
    out = search.handle(store, "pyoxigraph rdflib")
    assert out.splitlines()[0].startswith("- Decision 'Use pyoxigraph over rdflib'")


def test_alias_hit_fixes_exact_name_cliff(store):
    # "db locking" appears nowhere in the node's NAME — only in its aliases
    out = search.handle(store, "the db locking thing")
    assert "RocksDB exclusive lock" in out


def test_property_text_hit(store):
    out = search.handle(store, "named graphs quad store")
    assert "Use pyoxigraph over rdflib" in out


def test_concepts_are_searchable(store):
    out = search.handle(store, "rust experience")
    assert "Skill 'rust'" in out


def test_model_filter(store):
    out = search.handle(store, "pyoxigraph rdflib lock", model="Pattern")
    assert "RocksDB" in out and "Decision" not in out


def test_no_match_and_empty_query(store):
    assert "No matches" in search.handle(store, "kubernetes ingress")
    assert "No searchable terms" in search.handle(store, "thanks ok yes")


def test_invalidated_nodes_excluded(store):
    gid, iri = store.find_resource("Decision", "Use pyoxigraph over rdflib")
    store.forget_resource(iri, gid, "superseded")
    assert "Use pyoxigraph over rdflib" not in search.handle(store, "pyoxigraph rdflib")


def test_output_points_to_recall(store):
    assert "memory_recall" in search.handle(store, "pyoxigraph")
