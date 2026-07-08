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
    _, closed = store.create_link(source, target, relation, metadata)
    closure = ""
    if closed:
        closure = (
            f"\n{relation} is single-valued: closed {closed} earlier conflicting "
            "link(s) (worldChange — bounded, kept for history)."
        )
    return (
        f"{defined}"
        f"Linked {source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'"
        f"{closure}"
    )


def handle_amend_relation(
    store: MemoryStore,
    relation: str,
    add_verb_forms: list[str] | None = None,
    remove_verb_forms: list[str] | None = None,
) -> str:
    added, removed = store.amend_relation(
        relation, add_verb_forms or [], remove_verb_forms or []
    )
    parts = []
    if added:
        parts.append(f"added verb form(s): {', '.join(repr(f) for f in added)}")
    if removed:
        parts.append(f"removed: {', '.join(repr(f) for f in removed)}")
    missed = [f for f in (remove_verb_forms or [])
              if f.strip() and f.strip() not in removed]
    if missed:
        parts.append(f"not present (nothing removed): "
                     f"{', '.join(repr(f) for f in missed)}")
    return f"Amended relation '{relation}': " + "; ".join(parts)


def handle_unlink(
    store: MemoryStore,
    source_model: str,
    source_name: str,
    target_model: str,
    target_name: str,
    relation: str,
    mode: str = "worldChange",
) -> str:
    source = _find_any(store, source_model, source_name)
    target = _find_any(store, target_model, target_name)
    edge = f"{source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'"
    if mode == "remove":
        if store.remove_link(source, target, relation):
            return f"Removed link (hard delete): {edge}"
        return "No matching link found to remove."
    if store.close_link(source, target, relation, kind=mode):
        meaning = ("no longer true" if mode == "worldChange"
                   else "never was true — excluded from history queries")
        return f"Closed link ({mode}: {meaning}; edge kept, bounded): {edge}"
    return "No open link found to close (already closed, or never existed)."
