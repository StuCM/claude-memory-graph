import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import link, store_resource
from claude_memory_graph.namespaces import GRAPH_SCHEMA, RDF_TYPE, mem_node

import pyoxigraph as ox


@pytest.fixture
def store(tmp_path):
    return MemoryStore.open_or_create(tmp_path)


# ----------------------------------------------------------------
# The lexicon
# ----------------------------------------------------------------

def test_base_relations_carry_verb_forms(store):
    lex = store.relation_lexicon()
    assert "works on" in lex["worksOn"]["verbForms"]
    assert "prefers" in lex["hasPreference"]["verbForms"]
    assert all(entry["verbForms"] for entry in lex.values()), \
        "every base relation must be groundable from language"


def test_domain_range_hints_exposed(store):
    lex = store.relation_lexicon()
    assert lex["worksOn"]["domain"] == ["Person"]
    assert lex["worksOn"]["range"] == ["Project"]
    assert sorted(lex["affects"]["range"]) == ["Project", "Task"]  # union hint
    assert lex["relatesTo"]["domain"] == []  # generic relation: no hint


def test_valid_relations_unchanged(store):
    relations = store.valid_relations()
    assert "worksOn" in relations
    assert isinstance(relations["worksOn"], str)


# ----------------------------------------------------------------
# The extension flow requires verb forms
# ----------------------------------------------------------------

def test_add_relation_without_verb_forms_errors(store):
    with pytest.raises(ValueError, match="verb forms"):
        store.add_relation("mentors", "Person mentors another Person", [])


def test_add_relation_with_verb_forms_persists_and_grounds(store):
    store.add_relation("mentors", "Person mentors another Person",
                       ["mentors", "mentored by"])
    lex = store.relation_lexicon()
    assert lex["mentors"]["verbForms"] == ["mentored by", "mentors"]
    assert "mentors" in store.valid_relations()


def test_link_extension_flow_requires_verb_forms(store):
    store_resource.handle_resource(store, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_resource(store, "Person", {"name": "Alice"})
    with pytest.raises(ValueError, match="verb forms"):
        link.handle_link(store, "Person", "Alice", "Person", "Stuart Marshall",
                         "mentors", {}, "Person mentors another Person")
    msg = link.handle_link(store, "Person", "Alice", "Person", "Stuart Marshall",
                           "mentors", {}, "Person mentors another Person",
                           ["mentors", "mentored by"])
    assert "Added new relation 'mentors'" in msg and "Linked" in msg


def test_unknown_relation_error_mentions_verb_forms(store):
    store_resource.handle_resource(store, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_resource(store, "Person", {"name": "Alice"})
    with pytest.raises(ValueError, match="new_relation_verb_forms"):
        link.handle_link(store, "Person", "Alice", "Person", "Stuart Marshall",
                         "mentors", {})


# ----------------------------------------------------------------
# Ontology upgrade path for existing stores
# ----------------------------------------------------------------

def test_pre_upgrade_store_gets_new_ontology_without_losing_llm_relations(tmp_path):
    """A store persisted before verbForms existed must receive the updated
    base.ttl on next open — and keep its LLM-added relations."""
    store = MemoryStore.open_or_create(tmp_path)
    store.add_relation("mentors", "Person mentors another Person", ["mentors"])

    # simulate a pre-upgrade store: strip every verbForms triple, including
    # the marker definition the loader keys on
    schema = ox.NamedNode(GRAPH_SCHEMA)
    vf = mem_node("verbForms")
    for quad in list(store._store.quads_for_pattern(None, vf, None, schema)):
        store._store.remove(quad)
    for quad in list(store._store.quads_for_pattern(vf, None, None, schema)):
        store._store.remove(quad)
    assert store.relation_lexicon()["worksOn"]["verbForms"] == []
    store.save()

    reopened = MemoryStore.open_or_create(tmp_path)
    lex = reopened.relation_lexicon()
    assert "works on" in lex["worksOn"]["verbForms"]  # base upgraded
    assert "mentors" in reopened.valid_relations()    # LLM addition survived
