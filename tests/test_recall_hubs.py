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


def test_second_hop_follows_only_the_best_edges(tmp_path):
    store = MemoryStore.open_or_create(tmp_path / "store")
    handle_resource(store, "Project", {"name": "proj", "description": "p"})
    for i in range(recall.BEAM + 3):
        name = "webpack build" if i == 0 else f"other {i}"
        handle_resource(store, "Pattern", {"name": name, "description": "d"})
        handle_link(store, "Pattern", name, "Project", "proj", "appliesTo", {})
        handle_resource(store, "Pattern", {"name": f"child {i}", "description": "d"})
        handle_link(store, "Pattern", f"child {i}", "Pattern", name, "relatesTo", {})
    out = recall.handle(store, "Project", "proj", 2, focus="webpack")
    assert "via webpack build" in out
    assert "child 0" in out and "child 1" not in out


def test_chain_follows_the_best_edge_from_free_text(tmp_path):
    from claude_memory_graph.chain import chain
    store = MemoryStore.open_or_create(tmp_path / "store")
    handle_resource(store, "Decision", {"name": "Use pyoxigraph over rdflib",
                                        "rationale": "rdflib too slow"})
    handle_resource(store, "Pattern", {"name": "rdf store fix", "description": "pyoxigraph load"})
    handle_resource(store, "Pattern", {"name": "unrelated css tweak", "description": "colours"})
    handle_link(store, "Pattern", "rdf store fix", "Decision", "Use pyoxigraph over rdflib",
                "manifestsIn", {})
    lines = chain(store, "pyoxigraph rdflib")
    assert lines[0] == 'Decision "Use pyoxigraph over rdflib"'
    assert any('Pattern "rdf store fix"' in line for line in lines)
    assert not any("css" in line for line in lines)
    assert chain(store, "zzz nothing") == ['graph: nothing matches "zzz nothing"']


def test_ask_queries_answer_true_or_false(tmp_path):
    from claude_memory_graph.tools import query
    store = MemoryStore.open_or_create(tmp_path / "store")
    handle_resource(store, "Project", {"name": "proj", "description": "p"})
    assert query.handle(store, 'ASK { GRAPH ?g { ?p mem:name "proj" } }') == "true"
    assert query.handle(store, 'ASK { GRAPH ?g { ?p mem:name "nope" } }') == "false"
