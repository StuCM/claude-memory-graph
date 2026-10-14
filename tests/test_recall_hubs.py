from claude_memory_graph.store import HUB_DEGREE, MemoryStore
from claude_memory_graph.tools import recall
from claude_memory_graph.tools.link import handle_link
from claude_memory_graph.tools.store_resource import handle_concept, handle_resource


def test_second_hop_ranks_hub_members_by_focus(tmp_path):
    store = MemoryStore.open_or_create(tmp_path / "store")
    handle_resource(store, "Pattern", {"name": "root", "description": "x" * 500})
    handle_concept(store, "Concept", "broad", {})
    handle_link(store, "Pattern", "root", "Concept", "broad", "hasConcept", {})
    for i in range(HUB_DEGREE + 1):
        handle_resource(store, "Pattern", {"name": f"leaf {i}", "description": "d"})
        handle_link(store, "Pattern", f"leaf {i}", "Concept", "broad", "hasConcept", {})
    handle_resource(store, "Pattern", {"name": "webpack leaf", "description": "webpack build"})
    handle_link(store, "Pattern", "webpack leaf", "Concept", "broad", "hasConcept", {})
    out = recall.handle(store, "Pattern", "root", 2, focus="webpack")
    assert "leaf 0" not in out
    assert "Hub 'broad' (27 links)" in out
    assert "'webpack leaf'" in out
