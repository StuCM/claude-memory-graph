from ..store import MemoryStore, LinkedResource

_NOISE = {"name", "label", "createdAt", "updatedAt",
          "invalidated", "invalidatedAt", "invalidationReason"}


def _props(properties: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in properties.items() if k not in _NOISE)


def _line(lr: LinkedResource) -> str:
    name = lr.properties.get("name") or lr.properties.get("label") or lr.iri.value
    if lr.direction == "outgoing":
        head = f"{lr.relation} →"
    elif lr.direction == "incoming":
        head = f"← {lr.relation}"
    else:  # "via <name>" (second hop)
        head = f"({lr.direction}) {lr.relation} →"
    rest = _props(lr.properties)
    return f"- {head} {lr.model} '{name}'" + (f" — {rest}" if rest else "")


def handle(store: MemoryStore, model: str, name: str, depth: int) -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")

    graph_id, iri = result
    recall = store.recall(iri, graph_id, depth)

    rest = _props(recall.properties)
    lines = [f"{recall.model} '{name}'" + (f" — {rest}" if rest else "")]
    if recall.linked:
        lines.append(f"Links ({len(recall.linked)}):")
        lines.extend(_line(lr) for lr in recall.linked)
    else:
        lines.append("No links.")
    return "\n".join(lines)
