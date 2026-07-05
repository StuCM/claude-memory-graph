import pyoxigraph as ox

from ..store import MemoryStore


def _find_any(store: MemoryStore, model: str, name: str) -> ox.NamedNode:
    result = store.find_resource(model, name)
    if result is not None:
        _, iri = result
        return iri
    concept = store.find_concept(model, name)
    if concept is not None:
        return concept
    raise ValueError(
        f"{model} '{name}' not found. "
        "Create it first with memory_store_resource or memory_store_concept."
    )


def handle_link(
    store: MemoryStore,
    source_model: str,
    source_name: str,
    target_model: str,
    target_name: str,
    relation: str,
    metadata: dict[str, str],
    new_relation_description: str | None = None,
    new_relation_verb_forms: list[str] | None = None,
) -> str:
    defined = ""
    if relation not in store.valid_relations():
        if new_relation_description:
            store.add_relation(
                relation, new_relation_description, new_relation_verb_forms or []
            )
            defined = f"Added new relation '{relation}' to the ontology.\n"
        else:
            existing = "\n".join(
                f"  {name} — {desc}" if desc else f"  {name}"
                for name, desc in sorted(store.valid_relations().items())
            )
            raise ValueError(
                f"Unknown relation '{relation}'. Use one of the existing relations:\n"
                f"{existing}\n"
                "Prefer an existing relation even if the fit is loose. Only if none "
                "genuinely matches, call memory_link again with the same relation plus "
                "new_relation_description AND new_relation_verb_forms (the phrasings a "
                "question would use, e.g. ['mentors', 'mentored by']) to add it to the "
                "ontology."
            )

    source = _find_any(store, source_model, source_name)
    target = _find_any(store, target_model, target_name)
    store.create_link(source, target, relation, metadata)
    return (
        f"{defined}"
        f"Linked {source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'"
    )


def handle_unlink(
    store: MemoryStore,
    source_model: str,
    source_name: str,
    target_model: str,
    target_name: str,
    relation: str,
) -> str:
    source = _find_any(store, source_model, source_name)
    target = _find_any(store, target_model, target_name)
    removed = store.remove_link(source, target, relation)
    if removed:
        return f"Removed link: {source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'"
    return "No matching link found to remove."
