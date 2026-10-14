from claude_memory_graph.store import HUB_DEGREE, MemoryStore
from claude_memory_graph.tools import recall
from claude_memory_graph.tools.link import handle_link
from claude_memory_graph.tools.store_resource import handle_concept, handle_resource


def test_second_hop_skips_hubs_and_names_them(tmp_path):
    store = MemoryStore.open_or_create(tmp_path / "store")
    handle_resource(store, "Pattern", {"name": "root", "description": "x" * 500})
    handle_concept(store, "Concept", "broad", {})
    handle_link(store, "Pattern", "root", "Concept", "broad", "hasConcept", {})
    for i in range(HUB_DEGREE + 1):
        handle_resource(store, "Pattern", {"name": f"leaf {i}", "description": "d"})
        handle_link(store, "Pattern", f"leaf {i}", "Concept", "broad", "hasConcept", {})
    out = recall.handle(store, "Pattern", "root", 2)
    assert "leaf 0" not in out
    assert "'broad' (27 links)" in out
