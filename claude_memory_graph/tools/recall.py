import os
import subprocess

from ..store import MemoryStore, LinkedResource

_NOISE = {"name", "label", "createdAt", "updatedAt",
          "invalidated", "invalidatedAt", "invalidationReason"}


def _props(properties: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in properties.items() if k not in _NOISE)


def _drift(properties: dict[str, str]) -> str:
    """Code-anchor staleness flag: when a memory carries anchorPath +
    anchorCommit and the cwd repo has commits touching that path since,
    append '(code changed since <commit>)'. Fail open on everything —
    no git, no repo, unknown commit -> no flag, never an error."""
    path, commit = properties.get("anchorPath"), properties.get("anchorCommit")
    if not path or not commit:
        return ""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", f"{commit}..HEAD", "--", path],
            cwd=os.getcwd(), capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            return f" (code changed since {commit[:7]})"
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _line(lr: LinkedResource) -> str:
    name = lr.properties.get("name") or lr.properties.get("label") or lr.iri.value
    if lr.direction == "outgoing":
        head = f"{lr.relation} →"
    elif lr.direction == "incoming":
        head = f"← {lr.relation}"
    else:  # "via <name>" (second hop)
        head = f"({lr.direction}) {lr.relation} →"
    rest = _props(lr.properties)
    return (f"- {head} {lr.model} '{name}'" + (f" — {rest}" if rest else "")
            + _drift(lr.properties))


def handle(store: MemoryStore, model: str, name: str, depth: int) -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")

    graph_id, iri = result
    recall = store.recall(iri, graph_id, depth)

    rest = _props(recall.properties)
    lines = [f"{recall.model} '{name}'" + (f" — {rest}" if rest else "")
             + _drift(recall.properties)]
    if recall.linked:
        lines.append(f"Links ({len(recall.linked)}):")
        lines.extend(_line(lr) for lr in recall.linked)
    else:
        lines.append("No links.")
    return "\n".join(lines)
