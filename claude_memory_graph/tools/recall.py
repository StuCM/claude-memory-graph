import math
import os
import subprocess

from claude_hook_kit import terms

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


HUB_PICKS = 5
# Edges a hop follows onwards: the best-scoring against the focus, not all.
BEAM = 5


def _text(properties: dict[str, str]) -> str:
    return " ".join(v for k, v in properties.items() if k not in _PROVENANCE)


def _relevant(members: list[LinkedResource], focus: str,
              k: int = HUB_PICKS) -> list[LinkedResource]:
    """The members that share the most rare focus words, best first, none
    that share no word: 'arches' has hundreds of neighbours, only a few
    concern this recall."""
    wanted = set(terms(focus))
    bags = [set(terms(_text(lr.properties))) for lr in members]
    df: dict[str, int] = {}
    for bag in bags:
        for w in bag & wanted:
            df[w] = df.get(w, 0) + 1
    scored = []
    for lr, bag in zip(members, bags):
        score = sum(math.log(len(members) / df[w]) for w in bag & wanted)
        if score > 0:
            scored.append((score, lr))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [lr for _score, lr in scored[:k]]


def _beam(fresh: list[LinkedResource], focus: str) -> list[LinkedResource]:
    """The edges a hop follows onwards: all of a few, else the best BEAM
    against the focus. A lone generic edge (a concept) is often the only
    way to what matters, so a small hop is never ranked away."""
    return fresh if len(fresh) <= BEAM else _relevant(fresh, focus, BEAM)


def _newest_first(lr: LinkedResource) -> str:
    return lr.properties.get("updatedAt") or lr.properties.get("createdAt") or ""


def handle(store: MemoryStore, model: str, name: str, depth: int,
           limit: int | None = None, focus: str = "") -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")

    graph_id, iri = result
    props = store.get_resource_properties(iri, graph_id)
    against = f" to '{focus[:60]}'" if focus else " to this node"
    focus = focus or f"{name} {_text(props)}"
    recall = store.recall(iri, graph_id, depth, pick=lambda fresh: _beam(fresh, focus))

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
    for hub, members in recall.hubs.items():
        picks = _relevant(members, focus)
        lines.append(f"Hub '{hub}' ({len(members)} links) — {len(picks)} most relevant{against}:")
        lines.extend(f"  - {lr.model} '{lr.properties.get('name') or lr.properties.get('label', '')}'"
                     + (f" — {_brief({'description': lr.properties['description']})}"
                        if lr.properties.get("description") else "")
                     for lr in picks)
    return "\n".join(lines)
