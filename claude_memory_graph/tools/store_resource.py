from ..store import MemoryStore
from ..ontology import name_property


def handle_resource(store: MemoryStore, model: str, properties: dict[str, str]) -> str:
    name_prop = name_property(model)
    name = properties.get(name_prop)
    if name is None:
        raise ValueError(f"Missing required property: {name_prop}")

    result = store.find_resource(model, name)
    if result is not None:
        graph_id, iri = result
        store.update_resource(iri, graph_id, properties)
        return f"Updated {model} '{name}'"
    else:
        store.create_resource(model, properties)
        return f"Created {model} '{name}'"


def handle_concept(
    store: MemoryStore, concept_type: str, label: str, properties: dict[str, str]
) -> str:
    store.store_concept(concept_type, label, properties)
    return f"Stored {concept_type} concept '{label}'"
