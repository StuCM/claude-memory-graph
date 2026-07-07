"""Bi-temporal links: two clocks per edge, contradiction closure on write,
"true now" as the read default (DISTILL-CREATION.md §8, adopted from
Zep/Graphiti)."""

import pyoxigraph as ox
import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.namespaces import GRAPH_LINKS
from claude_memory_graph.tools import link as link_tool


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    s.create_resource("Person", {"name": "Stuart Marshall"})
    s.create_resource("Company", {"name": "Flax and Teal"})
    s.create_resource("Company", {"name": "Acme"})
    s.create_resource("Project", {"name": "charcoal"})
    s.create_resource("Project", {"name": "raspberry"})
    return s


def _iri(store, model, name):
    _, iri = store.find_resource(model, name)
    return iri


def _link_props(store, source, target, relation):
    """All property dicts for edges matching source/target/relation."""
    rows = store.query(
        f'SELECT ?link ?p ?o WHERE {{\n'
        f'    GRAPH <{GRAPH_LINKS}> {{\n'
        f'        ?link mem:linkSource <{source.value}> ;\n'
        f'              mem:linkTarget <{target.value}> ;\n'
        f'              mem:linkRelation "{relation}" .\n'
        f'        ?link ?p ?o .\n'
        f'    }}\n'
        f'}}'
    )
    links: dict[str, dict] = {}
    for r in rows:
        props = links.setdefault(r["link"].value, {})
        key = r["p"].value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if isinstance(r["o"], ox.Literal):
            props[key] = r["o"].value
    return list(links.values())


# ================= the two clocks =================

def test_create_link_stamps_valid_from(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    store.create_link(stuart, flax, "employedBy", {})
    (props,) = _link_props(store, stuart, flax, "employedBy")
    assert "linkValidFrom" in props and "linkCreatedAt" in props
    assert "linkValidUntil" not in props  # open edge


def test_caller_backdates_valid_from(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    store.create_link(stuart, flax, "employedBy", {"linkValidFrom": "2019-01-01"})
    (props,) = _link_props(store, stuart, flax, "employedBy")
    assert props["linkValidFrom"] == "2019-01-01"  # not double-stamped


# ================= contradiction closure =================

def test_new_single_valued_link_closes_conflicting_edge(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    acme = _iri(store, "Company", "Acme")
    store.create_link(stuart, flax, "employedBy", {})
    _, closed = store.create_link(stuart, acme, "employedBy", {})
    assert closed == 1

    (old,) = _link_props(store, stuart, flax, "employedBy")
    assert "linkValidUntil" in old  # bounded, not deleted
    assert old["invalidationKind"] == "worldChange"
    (new,) = _link_props(store, stuart, acme, "employedBy")
    assert "linkValidUntil" not in new  # the current fact stays open


def test_same_target_relink_does_not_close(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    store.create_link(stuart, flax, "employedBy", {})
    _, closed = store.create_link(stuart, flax, "employedBy", {})
    assert closed == 0


def test_multi_valued_relation_never_closes(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    charcoal = _iri(store, "Project", "charcoal")
    raspberry = _iri(store, "Project", "raspberry")
    store.create_link(stuart, charcoal, "worksOn", {})
    _, closed = store.create_link(stuart, raspberry, "worksOn", {})
    assert closed == 0  # people work on many projects — both stay current


# ================= "true now" is the read default =================

def test_recall_returns_only_open_edges(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    acme = _iri(store, "Company", "Acme")
    store.create_link(stuart, flax, "employedBy", {})
    store.create_link(stuart, acme, "employedBy", {})

    gid, iri = store.find_resource("Person", "Stuart Marshall")
    names = {lr.properties.get("name") for lr in store.recall(iri, gid, 1).linked}
    assert "Acme" in names and "Flax and Teal" not in names


def test_closed_edges_stay_queryable_history(store):
    """The closure keeps the fact: point-in-time SPARQL still sees it."""
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    acme = _iri(store, "Company", "Acme")
    store.create_link(stuart, flax, "employedBy", {})
    store.create_link(stuart, acme, "employedBy", {})
    rows = list(store.query(
        f'SELECT ?t WHERE {{ GRAPH <{GRAPH_LINKS}> {{\n'
        f'    ?l mem:linkSource <{stuart.value}> ; mem:linkRelation "employedBy" ;\n'
        f'       mem:linkTarget ?t ; mem:invalidationKind "worldChange" .\n'
        f'}} }}'
    ))
    assert len(rows) == 1 and rows[0]["t"] == flax


# ================= unlink: close by default, remove on request =================

def test_unlink_defaults_to_world_change_close(store):
    msg = link_tool.handle_unlink(
        store_with_link(store), "Person", "Stuart Marshall",
        "Company", "Flax and Teal", "employedBy")
    assert "Closed link" in msg and "worldChange" in msg
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    (props,) = _link_props(store, stuart, flax, "employedBy")
    assert "linkValidUntil" in props  # edge kept, bounded

    gid, iri = store.find_resource("Person", "Stuart Marshall")
    assert store.recall(iri, gid, 1).linked == []  # gone from current recall


def test_unlink_correction_revises_belief_not_world(store):
    """A correction never was true: belief clock set, world clock untouched —
    so 'what was true last spring?' excludes it."""
    link_tool.handle_unlink(
        store_with_link(store), "Person", "Stuart Marshall",
        "Company", "Flax and Teal", "employedBy", mode="correction")
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    (props,) = _link_props(store, stuart, flax, "employedBy")
    assert props["invalidationKind"] == "correction"
    assert "linkInvalidatedAt" in props
    assert "linkValidUntil" not in props

    gid, iri = store.find_resource("Person", "Stuart Marshall")
    assert store.recall(iri, gid, 1).linked == []


def test_unlink_remove_hard_deletes(store):
    msg = link_tool.handle_unlink(
        store_with_link(store), "Person", "Stuart Marshall",
        "Company", "Flax and Teal", "employedBy", mode="remove")
    assert "hard delete" in msg
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    assert _link_props(store, stuart, flax, "employedBy") == []


def test_unlink_close_reports_when_nothing_open(store):
    msg = link_tool.handle_unlink(
        store, "Person", "Stuart Marshall", "Company", "Acme", "employedBy")
    assert "No open link" in msg


def test_close_link_rejects_unknown_kind(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    with pytest.raises(ValueError, match="worldChange"):
        store.close_link(stuart, flax, "employedBy", kind="whoops")


def store_with_link(store):
    stuart = _iri(store, "Person", "Stuart Marshall")
    flax = _iri(store, "Company", "Flax and Teal")
    store.create_link(stuart, flax, "employedBy", {})
    return store


# ================= the tool message surfaces closure =================

def test_link_tool_reports_closure(store):
    link_tool.handle_link(store, "Person", "Stuart Marshall",
                          "Company", "Flax and Teal", "employedBy", {})
    msg = link_tool.handle_link(store, "Person", "Stuart Marshall",
                                "Company", "Acme", "employedBy", {})
    assert "single-valued" in msg and "closed 1" in msg


def test_schema_declares_single_valued_relations(store):
    sv = store.single_valued_relations()
    assert "employedBy" in sv and "assignedTo" in sv
    assert "worksOn" not in sv and "affects" not in sv
