"""Golden tests for query planner v0: fixture graph + question table →
expected RESULT ROWS (never SPARQL text), plus the refusal suite —
ungroundable questions must fall back, never guess."""

import pytest

from claude_memory_graph import planner
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import link, store_resource


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    store_resource.handle_resource(s, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_resource(s, "Project", {
        "name": "quartz", "status": "active",
        "description": "Arches-based heritage platform"})
    store_resource.handle_resource(s, "Project", {
        "name": "memory graph", "status": "done",
        "description": "RDF knowledge graph MCP server"})
    store_resource.handle_resource(s, "Technology", {"name": "pyoxigraph"})
    store_resource.handle_resource(s, "Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs"})
    store_resource.handle_resource(s, "Decision", {
        "name": "Serve static via nginx image",
        "rationale": "prod-mode static files need nginx, not runserver"})
    # deliberately shares name words with Project 'memory graph' — the
    # anchor role-fit regression's decoy
    store_resource.handle_resource(s, "Decision", {
        "name": "Rebuild memory graph recall gate",
        "rationale": "gate scoring needed a coordination bonus"})

    def L(sm, sn, tm, tn, rel):
        link.handle_link(s, sm, sn, tm, tn, rel, {})

    L("Person", "Stuart Marshall", "Project", "quartz", "worksOn")
    L("Person", "Stuart Marshall", "Project", "memory graph", "worksOn")
    L("Decision", "Use pyoxigraph over rdflib", "Project", "memory graph", "affects")
    L("Decision", "Serve static via nginx image", "Project", "quartz", "affects")
    L("Decision", "Serve static via nginx image", "Person", "Stuart Marshall", "madeBy")
    L("Project", "memory graph", "Technology", "pyoxigraph", "uses")
    return s


# ── golden: composed queries return the right rows ─────────────────────

def test_one_edge_anchor(store):
    out = planner.handle(store, "What decisions affect quartz?")
    assert "Serve static via nginx image" in out
    assert "pyoxigraph over rdflib" not in out


def test_flagship_two_edge_chain(store):
    out = planner.handle(store, "What decisions affect the projects Stuart works on?")
    assert "Serve static via nginx image" in out
    assert "Use pyoxigraph over rdflib" in out


def test_who_projection(store):
    out = planner.handle(store, "Who works on quartz?")
    assert "Stuart Marshall" in out


def test_anchor_role_fit_beats_lexical_tie(store):
    # "memory graph" name-matches both the Project and the decoy Decision;
    # worksOn's domain/range hints must pick the Project
    out = planner.handle(store, "Who works on memory graph?")
    assert "Stuart Marshall" in out


def test_implicit_variable_from_relation_range(store):
    out = planner.handle(store, "What does memory graph use?")
    assert "pyoxigraph" in out


def test_why_finds_rationale(store):
    out = planner.handle(store, "Why did we choose pyoxigraph?")
    assert "native quad store" in out


def test_direction_from_domain_range(store):
    out = planner.handle(store, "Which decisions were made by Stuart?")
    assert "Serve static via nginx image" in out
    assert "pyoxigraph over rdflib" not in out


def test_contains_leftover_noun(store):
    out = planner.handle(store, "Any recent decisions about static?")
    assert "Serve static via nginx image" in out
    assert "pyoxigraph over rdflib" not in out


def test_status_modifier(store):
    out = planner.handle(store, "Which projects are active?")
    assert "quartz" in out
    assert "memory graph" not in out


def test_rationale_shown_not_just_names(store):
    out = planner.handle(store, "What decisions affect quartz?")
    assert "nginx, not runserver" in out  # the why travels with the answer


def test_invalidated_excluded(store):
    gid, iri = store.find_resource("Decision", "Serve static via nginx image")
    store.forget_resource(iri, gid, "superseded")
    out = planner.handle(store, "What decisions affect quartz?")
    assert "nginx" not in out


# ── refusal suite: fall back, never guess ──────────────────────────────

def test_statement_shaped_refused(store):
    out = planner.handle(store, "Refactor the dispatcher to batch saves")
    assert "Statement-shaped" in out


def test_ungroundable_falls_back(store):
    out = planner.handle(store, "What colour is the bikeshed?")
    assert "fallback" in out
    assert "- Decision" not in out and "- Project" not in out


def test_unknown_entity_never_fabricates(store):
    out = planner.handle(store, "Who maintains kubernetes?")
    assert "fallback" in out or "No matches" in out
    assert "- Person 'Stuart Marshall'" not in out  # no fabricated answer rows


def test_misgrounded_relation_never_self_joins(store):
    # "under" false-grounds to partOf; its only type-fitting endpoint is the
    # node already on the other end — must refuse, not compose ?v partOf ?v
    g = planner.ground(store, "Which projects are under active development?")
    assert g.refuse
    out = planner.handle(store, "Which projects are under active development?")
    assert "fallback" in out


def test_explain_shows_grounding_and_sparql(store):
    out = planner.handle(store, "What decisions affect quartz?", explain=True)
    assert "grounding" in out and "SELECT" in out
    assert "relation affects" in out
