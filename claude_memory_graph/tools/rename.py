"""Rename a node in place.

The obvious move — store the shorter name with memory_store_resource — does
NOT rename: that tool upserts BY NAME, so it creates a second node, leaves
the original in place, and the new one inherits none of the original's
links. That is how a graph acquires twins.

A real rename is small because names were never the identity: links carry
IRIs. Find the node by its current name, swap the name property on that
same IRI, and every edge survives. This exists because 1040 nodes on a real
graph had grown into sentences and there was no safe way to fix even one.
"""

from ..capture_rules import check_name, name_warning
from ..ontology import is_concept_type, name_property
from ..store import MemoryStore


def handle(store: MemoryStore, model: str, old_name: str, new_name: str) -> str:
    new_name = check_name(new_name, "label" if is_concept_type(model) else "name")
    if is_concept_type(model):
        iri = store.find_concept(model, old_name)
        if iri is None:
            raise ValueError(f"{model} '{old_name}' not found")
        if store.find_concept(model, new_name) is not None:
            raise ValueError(
                f"A {model} labelled '{new_name}' already exists — link or merge "
                "into it rather than renaming this one onto its label.")
        store.rename_concept(iri, new_name)
        kind = "label"
    else:
        found = store.find_resource(model, old_name)
        if found is None:
            raise ValueError(f"{model} '{old_name}' not found")
        if store.find_resource(model, new_name) is not None:
            raise ValueError(
                f"A {model} named '{new_name}' already exists — update that node "
                "instead, or pick a name that doesn't collide.")
        graph_id, iri = found
        store.update_resource(iri, graph_id, {name_property(model): new_name})
        kind = "name"
    return (f"Renamed {model} '{old_name}' -> '{new_name}' (links preserved)"
            + (name_warning(model, new_name, kind) or ""))
