import os
import subprocess

from ..store import MemoryStore, LinkedResource

_NOISE = {"name", "label", "createdAt", "updatedAt",
          "invalidated", "invalidatedAt", "invalidationReason"}


# Provenance tells the reader where a memory came from, not what it says.
_PROVENANCE = {"sourceContext", "sourceDocument", "sourceKind", "capturedBy", "anchorCommit"}
_BRIEF = 200


def _props(properties: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in properties.items() if k not in _NOISE)


def _brief(properties: dict[str, str]) -> str:
    """A neighbour as a line, not a dump: content properties, each clipped."""
    parts = []
    for k, v in properties.items():
        if k in _NOISE or k in _PROVENANCE:
            continue
        parts.append(f"{k}: {v[:_BRIEF]}" + ("…" if len(v) > _BRIEF else ""))
    return "; ".join(parts)


def _drift(properties: dict[str, str]) -> str:
    """Code-anchor staleness flag: when a memory carries anchorPath +
    anchorCommit and the cwd repo has commits touching that path since,
    append '(code changed since <commit>)'. anchorPath is repo-relative,
    so the check runs from the repo ROOT — a session in a subdirectory
    must not silently miss. Fail open on everything — no git, no repo,
    unknown commit -> no flag, never an error."""
    path, commit = properties.get("anchorPath"), properties.get("anchorCommit")
    if not path or not commit:
        return ""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.getcwd(), capture_output=True, text=True, timeout=2)
        if top.returncode != 0:
            return ""
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", f"{commit}..HEAD", "--", path],
            cwd=top.stdout.strip(), capture_output=True, text=True, timeout=2)
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
    else:  # "via <name>" (second hop): name only, the first hop carries the detail
        return f"- ({lr.direction}) {lr.relation} → {lr.model} '{name}'"
    rest = _brief(lr.properties)
    return (f"- {head} {lr.model} '{name}'" + (f" — {rest}" if rest else "")
            + _drift(lr.properties))


def _newest_first(lr: LinkedResource) -> str:
    return lr.properties.get("updatedAt") or lr.properties.get("createdAt") or ""


def handle(store: MemoryStore, model: str, name: str, depth: int,
           limit: int | None = None) -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")

    graph_id, iri = result
    recall = store.recall(iri, graph_id, depth)

    rest = _props(recall.properties)
    lines = [f"{recall.model} '{name}'" + (f" — {rest}" if rest else "")
             + _drift(recall.properties)]
    first = sorted((lr for lr in recall.linked if not lr.direction.startswith("via ")),
                   key=_newest_first, reverse=True)
    second = [lr for lr in recall.linked if lr.direction.startswith("via ")]
    shown = (first + second)[:limit] if limit else first + second
    if shown:
        lines.append(f"Links ({len(recall.linked)}, newest first):")
        lines.extend(_line(lr) for lr in shown)
        if len(shown) < len(recall.linked):
            lines.append(f"- +{len(recall.linked) - len(shown)} more — memory_search to find one")
    else:
        lines.append("No links.")
    if recall.hubs:
        hubs = ", ".join(f"'{n}' ({c} links)" for n, c in recall.hubs.items())
        lines.append(f"Not expanded (broad hubs, recall one directly): {hubs}")
    return "\n".join(lines)
