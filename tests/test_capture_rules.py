import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.capture_rules import check_name, names_similar
from claude_memory_graph.tools import store_resource, link


@pytest.fixture
def store(tmp_path):
    return MemoryStore.open_or_create(tmp_path)


# ----------------------------------------------------------------
# Name lint
# ----------------------------------------------------------------

def test_check_name_normalizes_whitespace():
    assert check_name("  Use   pyoxigraph\tover rdflib ") == "Use pyoxigraph over rdflib"

def test_check_name_rejects_empty():
    with pytest.raises(ValueError, match="Empty"):
        check_name("   ")

def test_check_name_rejects_placeholders():
    with pytest.raises(ValueError, match="placeholder"):
        check_name("Notes")

def test_check_name_rejects_overlong():
    with pytest.raises(ValueError, match="exceeds"):
        check_name("x" * 121)


# ----------------------------------------------------------------
# Similarity
# ----------------------------------------------------------------

def test_similar_case_insensitive():
    assert names_similar("Use Pyoxigraph over RDFLib", "use pyoxigraph over rdflib")

def test_similar_token_subset():
    assert names_similar("Use pyoxigraph", "Use pyoxigraph over rdflib")

def test_single_token_subset_not_similar():
    assert not names_similar("pyoxigraph", "Use pyoxigraph over rdflib")

def test_distinct_names_not_similar():
    assert not names_similar("Stuart Marshall", "Stuart Smith")
    assert not names_similar("Use RocksDB store", "Use pyoxigraph over rdflib")


# ----------------------------------------------------------------
# Required properties
# ----------------------------------------------------------------

def test_decision_requires_rationale(store):
    with pytest.raises(ValueError, match="rationale"):
        store_resource.handle_resource(
            store, "Decision", {"name": "Use pyoxigraph over rdflib"}
        )

def test_decision_with_rationale_created(store):
    msg = store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    assert msg.startswith("Created Decision")

def test_pattern_requires_description(store):
    with pytest.raises(ValueError, match="description"):
        store_resource.handle_resource(store, "Pattern", {"name": "SPARQL FILTER scope"})

def test_update_does_not_require_required_props(store):
    store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    msg = store_resource.handle_resource(
        store, "Decision", {"name": "Use pyoxigraph over rdflib", "status": "active"}
    )
    assert msg.startswith("Updated Decision")


# ----------------------------------------------------------------
# Duplicate guard
# ----------------------------------------------------------------

def test_near_duplicate_rejected_with_candidates(store):
    store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    with pytest.raises(ValueError, match="Use pyoxigraph over rdflib"):
        store_resource.handle_resource(
            store, "Decision",
            {"name": "use Pyoxigraph over RDFLib", "rationale": "dup"},
        )

def test_force_creates_despite_similar(store):
    store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    msg = store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph in the CLI", "rationale": "distinct decision"},
        force=True,
    )
    assert msg.startswith("Created Decision")

def test_exact_name_still_upserts(store):
    store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    msg = store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "outcome": "worked"},
    )
    assert msg.startswith("Updated Decision")

def test_invalidated_nodes_dont_block_creation(store):
    store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib", "rationale": "native quad store"},
    )
    graph_id, iri = store.find_resource("Decision", "Use pyoxigraph over rdflib")
    store.forget_resource(iri, graph_id, "reversed")
    msg = store_resource.handle_resource(
        store, "Decision",
        {"name": "Use pyoxigraph over rdflib again", "rationale": "still the best fit"},
    )
    assert msg.startswith("Created Decision")


# ----------------------------------------------------------------
# Concept identity is case/whitespace-insensitive
# ----------------------------------------------------------------

def test_concept_case_insensitive_reuse(store):
    store_resource.handle_concept(store, "Skill", "rust", {})
    store_resource.handle_concept(store, "Skill", "Rust", {})
    labels = [
        s["label"].value
        for s in store.query(
            'SELECT ?label WHERE { GRAPH <https://memory.claude.local/graph/concepts> '
            '{ ?n rdf:type mem:Skill ; mem:label ?label } }'
        )
    ]
    assert labels == ["rust"]

def test_link_resolves_concept_case_insensitively(store):
    store_resource.handle_resource(store, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_concept(store, "Skill", "rust", {})
    msg = link.handle_link(
        store, "Person", "Stuart Marshall", "Skill", "Rust", "hasSkill", {}
    )
    assert "Linked" in msg


# ----------------------------------------------------------------
# Provenance
# ----------------------------------------------------------------

def test_captured_by_stamped_when_client_known(store):
    store.capture_client = "claude-code/2.1"
    store_resource.handle_resource(store, "Person", {"name": "Stuart Marshall"})
    graph_id, iri = store.find_resource("Person", "Stuart Marshall")
    props = store.get_resource_properties(iri, graph_id)
    assert props["capturedBy"] == "claude-code/2.1"

def test_no_captured_by_when_client_unknown(store):
    store_resource.handle_resource(store, "Person", {"name": "Stuart Marshall"})
    graph_id, iri = store.find_resource("Person", "Stuart Marshall")
    props = store.get_resource_properties(iri, graph_id)
    assert "capturedBy" not in props
