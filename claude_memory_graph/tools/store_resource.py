from ..store import MemoryStore
from ..ontology import name_property
from ..capture_rules import check_name, check_required_properties


def handle_resource(
    store: MemoryStore, model: str, properties: dict[str, str], force: bool = False
) -> str:
    name_prop = name_property(model)
    name = properties.get(name_prop)
    if name is None:
        raise ValueError(f"Missing required property: {name_prop}")

    name = check_name(name)
    properties = {**properties, name_prop: name}

    result = store.find_resource(model, name)
    if result is not None:
        graph_id, iri = result
        store.update_resource(iri, graph_id, properties)
        return f"Updated {model} '{name}'"

    # Creation-only checks: updates can't remove properties, and legacy nodes
    # predating a required property shouldn't block harmless updates.
    check_required_properties(model, properties)
    if not force:
        similar = store.find_similar_resources(model, name)
        if similar:
            listing = "', '".join(similar)
            raise ValueError(
                f"Similar {model} node(s) already exist: '{listing}'. Update "
                f"the existing node by reusing its exact name, or pass "
                f"force=true if '{name}' is genuinely a distinct thing."
            )

    store.create_resource(model, properties)
    return f"Created {model} '{name}'"


def handle_concept(
    store: MemoryStore, concept_type: str, label: str, properties: dict[str, str]
) -> str:
    label = check_name(label, "label")
    store.store_concept(concept_type, label, properties)
    return f"Stored {concept_type} concept '{label}'"
