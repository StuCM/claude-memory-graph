from ..store import MemoryStore


def handle(store: MemoryStore, model: str, name: str, reason: str) -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")
    graph_id, iri = result
    store.forget_resource(iri, graph_id, reason)
    return f"Invalidated {model} '{name}' — reason: {reason}"
