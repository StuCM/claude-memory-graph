"""Rename in place — the operation that did not exist while 1040 nodes on a
real graph needed it."""

import pytest

from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import rename
from claude_memory_graph.tools.link import handle_link
from claude_memory_graph.tools.recall import handle as recall


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "store")
    s.create_resource("Project", {"name": "quartz"})
    s.create_resource("Decision", {
        "name": "the two failures are independent and fixing one will not clear the other",
        "rationale": "measured"})
    s.store_concept("Concept", "retrieval", {})
    return s


def test_rename_preserves_links(store):
    handle_link(store, "Decision",
                "the two failures are independent and fixing one will not clear the other",
                "Project", "quartz", "affects", {})
    rename.handle(store, "Decision",
                  "the two failures are independent and fixing one will not clear the other",
                  "Separate the tag and stall fixes")
    out = recall(store, "Decision", "Separate the tag and stall fixes", 1)
    assert "quartz" in out


def test_rename_rejects_a_colliding_name(store):
    store.create_resource("Project", {"name": "coral"})
    with pytest.raises(ValueError, match="already exists"):
        rename.handle(store, "Project", "coral", "quartz")


def test_rename_reports_a_missing_node(store):
    with pytest.raises(ValueError, match="not found"):
        rename.handle(store, "Project", "nope", "something")


def test_rename_concept_keeps_its_edges(store):
    handle_link(store, "Project", "quartz", "Concept", "retrieval", "hasConcept", {})
    rename.handle(store, "Concept", "retrieval", "recall")
    assert store.find_concept("Concept", "retrieval") is None
    assert "recall" in recall(store, "Project", "quartz", 1)


def test_rename_still_warns_when_the_new_name_is_long(store):
    out = rename.handle(store, "Project", "quartz",
                        "the quartz arches deployment for the heritage estate")
    assert "[naming]" in out
