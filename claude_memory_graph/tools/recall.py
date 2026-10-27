import math
import os
import subprocess

from claude_memory_graph.hookcore import terms

from ..store import MemoryStore, LinkedResource

_NOISE = {"name", "label", "createdAt", "updatedAt",
          "invalidated", "invalidatedAt", "invalidationReason"}


# Provenance tells the reader where a memory came from, not what it says.
_PROVENANCE = {"sourceContext", "sourceDocument", "sourceKind", "capturedBy", "anchorCommit"}
# Matching and bookkeeping data: aliases exist for the gate's matcher, status
# is almost always "active", anchorPath only matters via the drift flag.
# None of it helps the model read a neighbour.
_MATCH_ONLY = {"aliases", "status", "anchorPath"}
_DISPLAY_SKIP = _NOISE | _PROVENANCE | _MATCH_ONLY
_BRIEF = 200
# The properties that say what a memory IS, best first.
_CONTENT_KEYS = ("rationale", "description", "outcome", "example")


def _props(properties: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in properties.items() if k not in _NOISE)


def _brief(properties: dict[str, str]) -> str:
    """A neighbour as a line, not a dump: content properties, each clipped."""
    parts = []
    for k, v in properties.items():
        if k in _DISPLAY_SKIP:
            continue
        parts.append(f"{k}: {v[:_BRIEF]}" + ("…" if len(v) > _BRIEF else ""))
    return "; ".join(parts)


def gist(properties: dict[str, str], width: int) -> str:
    """One clipped sentence saying what a memory is: its rationale or
    description if it has one, otherwise its first readable property."""
    value = next((properties[k] for k in _CONTENT_KEYS if properties.get(k)), "")
    if not value:
        value = next((v for k, v in properties.items()
                      if k not in _DISPLAY_SKIP and v), "")
    value = " ".join(value.split())
    return value[:width] + ("…" if len(value) > width else "")


def _drift_flags(props_list) -> dict[tuple[str, str], str]:
    """Code-anchor staleness flags for many memories at once, keyed by
    (anchorPath, anchorCommit): '(code changed since <commit>)' when the cwd
    repo has commits touching that path since the anchor commit.

    One `git rev-parse` plus one `git log` per DISTINCT anchor commit — a
    prime of 20 anchored memories used to spawn 40 git processes. anchorPath
    is repo-relative, so the check runs from the repo ROOT; a directory
    anchor is flagged when any file under it changed. Fail open on
    everything — no git, no repo, unknown commit -> no flag, never an error."""
    by_commit: dict[str, set[str]] = {}
    for props in props_list:
        path, commit = props.get("anchorPath"), props.get("anchorCommit")
        if path and commit:
            by_commit.setdefault(commit, set()).add(path)
    if not by_commit:
        return {}
    flags: dict[tuple[str, str], str] = {}
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.getcwd(), capture_output=True, text=True, timeout=2)
        if top.returncode != 0:
            return {}
        root = top.stdout.strip()
        for commit, paths in by_commit.items():
            result = subprocess.run(
                ["git", "log", "--name-only", "--format=", f"{commit}..HEAD",
                 "--", *sorted(paths)],
                cwd=root, capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                continue
            changed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
            for path in paths:
                prefix = path.rstrip("/") + "/"
                if path in changed or any(c.startswith(prefix) for c in changed):
                    flags[(path, commit)] = f" (code changed since {commit[:7]})"
    except (OSError, subprocess.SubprocessError):
        pass
    return flags


def _drift(properties: dict[str, str], flags: dict | None = None) -> str:
    if flags is None:
        flags = _drift_flags([properties])
    return flags.get((properties.get("anchorPath"), properties.get("anchorCommit")), "")


def _line(lr: LinkedResource, flags: dict | None = None) -> str:
    name = lr.properties.get("name") or lr.properties.get("label") or lr.iri.value
    if lr.direction == "outgoing":
        head = f"{lr.relation} →"
    elif lr.direction == "incoming":
        head = f"← {lr.relation}"
    else:  # "via <name>" (second hop): name only, the first hop carries the detail
        return f"- ({lr.direction}) {lr.relation} → {lr.model} '{name}'"
    rest = _brief(lr.properties)
    return (f"- {head} {lr.model} '{name}'" + (f" — {rest}" if rest else "")
            + _drift(lr.properties, flags))


HUB_PICKS = 5


def _text(properties: dict[str, str]) -> str:
    return " ".join(v for k, v in properties.items() if k not in _PROVENANCE)


def _relevant(members: list[LinkedResource], focus: str) -> list[LinkedResource]:
    """The hub members that share the most rare focus words, best first:
    'arches' has hundreds of neighbours, only a few concern this recall."""
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
    return [lr for _score, lr in scored[:HUB_PICKS]]


def _newest_first(lr: LinkedResource) -> str:
    return lr.properties.get("updatedAt") or lr.properties.get("createdAt") or ""


def handle(store: MemoryStore, model: str, name: str, depth: int,
           limit: int | None = None, focus: str = "") -> str:
    result = store.find_resource(model, name)
    if result is None:
        raise ValueError(f"{model} '{name}' not found")

    graph_id, iri = result
    recall = store.recall(iri, graph_id, depth)

    first = sorted((lr for lr in recall.linked if not lr.direction.startswith("via ")),
                   key=_newest_first, reverse=True)
    second = [lr for lr in recall.linked if lr.direction.startswith("via ")]
    shown = (first + second)[:limit] if limit else first + second
    flags = _drift_flags([recall.properties] + [lr.properties for lr in shown])

    rest = _props(recall.properties)
    lines = [f"{recall.model} '{name}'" + (f" — {rest}" if rest else "")
             + _drift(recall.properties, flags)]
    if shown:
        lines.append(f"Links ({len(recall.linked)}, newest first):")
        lines.extend(_line(lr, flags) for lr in shown)
        if len(shown) < len(recall.linked):
            lines.append(f"- +{len(recall.linked) - len(shown)} more — memory_search to find one")
    else:
        lines.append("No links.")
    against = f" to '{focus[:60]}'" if focus else " to this node"
    focus = focus or f"{name} {_text(recall.properties)}"
    for hub, members in recall.hubs.items():
        picks = _relevant(members, focus)
        lines.append(f"Hub '{hub}' ({len(members)} links) — {len(picks)} most relevant{against}:")
        lines.extend(f"  - {lr.model} '{lr.properties.get('name') or lr.properties.get('label', '')}'"
                     + (f" — {_brief({'description': lr.properties['description']})}"
                        if lr.properties.get("description") else "")
                     for lr in picks)
    return "\n".join(lines)


# Session-start prime ordering: the kinds of memory that change what you do
# come first; reference nodes (technologies, people) last.
_PRIME_PRIORITY = {"Decision": 0, "Pattern": 0, "Constraint": 0,
                   "Preference": 1, "Task": 2}
_PRIME_GIST = 140


def prime(store: MemoryStore, model: str, name: str,
          max_links: int, max_chars: int) -> str | None:
    """The session-start view of a node: a table of contents, not a dump.

    Direct neighbours only, ranked by kind (decisions, patterns, constraints
    first) then recency, one line each — name plus a clipped gist, no
    aliases or bookkeeping. Stops at max_links lines or max_chars, whichever
    comes first, and says how many were left out so nothing is unreachable:
    the per-prompt gate brings in detail when a prompt is about something."""
    result = store.find_resource(model, name)
    if result is None:
        return None
    graph_id, iri = result
    recall = store.recall(iri, graph_id, 1)
    links = sorted((lr for lr in recall.linked if not lr.direction.startswith("via ")),
                   key=_newest_first, reverse=True)
    links.sort(key=lambda lr: _PRIME_PRIORITY.get(lr.model, 3))

    head_gist = gist(recall.properties, _PRIME_GIST)
    lines = [f"{model} '{name}'" + (f" — {head_gist}" if head_gist else "")]
    flags = _drift_flags([lr.properties for lr in links[:max_links]])
    used = len(lines[0])
    shown = 0
    for lr in links[:max_links]:
        node = lr.properties.get("name") or lr.properties.get("label") or lr.iri.value
        g = gist(lr.properties, _PRIME_GIST)
        line = (f"- {lr.model} '{node}'" + (f" — {g}" if g else "")
                + _drift(lr.properties, flags))
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1
    if shown < len(links):
        lines.append(f"- +{len(links) - shown} more — memory_search(\"<topic>\") or "
                     f"memory_recall(model=\"{model}\", name=\"{name}\", depth=2, "
                     f"focus=\"<topic>\")")
    return "\n".join(lines)
