"""Pulse — one screen answering "is memory actually reaching my sessions?"

Every automatic behaviour already logs its decisions; what was missing is
a view a human can read without knowing which jsonl holds what. Pulse
joins them: retrieval (primes, graph and log injections, silences),
capture enforcement (stop blocks, digs, observed writes, stamps),
explicit recalls, the miss report's headline, and the distill backlog —
windowed, with a verdict line per signal so "0" comes with a diagnosis.

Read-only over the hook-kit home logs and the context dir; opens the
store only to count nodes. `claude-memory-graph pulse [--days N]`.
"""

import json
import time
from collections import Counter

from claude_hook_kit import state_home

from . import misses as misses_mod
from .runtime import store_dir


def _read_jsonl(name: str, cutoff: float) -> list[dict]:
    path = state_home() / name
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("ts", 0) >= cutoff:
            entries.append(entry)
    return entries


def _graph_counts() -> tuple[int, int]:
    try:
        from ..store import MemoryStore
        from ..namespaces import GRAPH_LINKS, GRAPH_RESOURCE_BASE
        store = MemoryStore.open_or_create(store_dir())
        nodes = sum(1 for _ in store.query(
            f'SELECT ?n WHERE {{ GRAPH ?g {{ ?n rdf:type ?t }} '
            f'FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}")) }}'))
        links = sum(1 for _ in store.query(
            f'SELECT ?l WHERE {{ GRAPH <{GRAPH_LINKS}> '
            f'{{ ?l rdf:type mem:CrossLink }} }}'))
        return nodes, links
    except Exception:
        return -1, -1


def report(days: int = 7) -> str:
    cutoff = time.time() - days * 86400
    injections = _read_jsonl("injections.jsonl", cutoff)
    recalls = _read_jsonl("explicit-recalls.jsonl", cutoff)
    capture = _read_jsonl("capture.jsonl", cutoff)

    graph_lines = [e for e in injections if "kind" not in e]
    log_lines = [e for e in injections if e.get("kind") == "log"]
    primes = [e for e in injections if e.get("kind") == "prime"]
    fired = [e for e in graph_lines if e.get("fired")]
    log_fired = [e for e in log_lines if e.get("fired")]
    sessions = {e.get("session") for e in injections + recalls + capture} - {None, ""}
    blocks = [e for e in capture if e.get("kind") == "block"]
    writes = [e for e in capture if e.get("kind") == "write"]
    digs = [e for e in blocks if e.get("dig")]
    top_nodes = Counter(n for e in fired for n in e.get("nodes", [])).most_common(3)

    try:
        from ..distill import context_dir
        from ..context_entries import undistilled_files
        undistilled = len(undistilled_files(context_dir()))
    except Exception:
        undistilled = -1
    nodes, links = _graph_counts()
    miss_result = misses_mod.analyse()
    n_miss, n_gap = len(miss_result["misses"]), len(miss_result["gaps"])

    lines = [f"memory pulse — last {days} day(s)",
             f"sessions seen: {len(sessions)} · prompts gated: {len(graph_lines)}"
             + (f" · graph: {nodes} nodes, {links} links" if nodes >= 0 else "")]

    if not injections and not capture:
        lines.append("NO ACTIVITY LOGGED — hooks are not firing. Check /hooks in a "
                     "session, `claude-hooks list`, and HANDBOOK.md §8.")
        return "\n".join(lines)

    lines.append(f"auto-prime:  fired in {len(primes)} session(s)"
                 + ("" if primes else " — the graph doesn't know your projects yet "
                    "(store a Project node or run distill)"))
    rate = f"{len(fired)}/{len(graph_lines)}" if graph_lines else "0/0"
    lines.append(f"graph layer: injected {rate}"
                 + (f" · top: " + ", ".join(f"'{n}' ×{c}" for n, c in top_nodes)
                    if top_nodes else ""))
    if graph_lines and not fired:
        lines.append("  → the gate never spoke. If the graph has nodes, prompts may "
                     "lack distinctive names, or ABS_MIN is too high — check "
                     "`claude-memory-graph misses` and `claude-hooks log`.")
    lines.append(f"log layer:   injected {len(log_fired)} undistilled entr"
                 f"{'y' if len(log_fired) == 1 else 'ies'}")
    lines.append(f"capture:     {len(blocks)} stop block(s) "
                 f"({len(digs)} dig, {sum(1 for b in blocks if b.get('stamped'))} stamped) "
                 f"· {len(writes)} observed context write(s)")
    if blocks and not writes:
        lines.append("  → blocks fire but no writes are ever observed — the model may "
                     "be ignoring them or the context dir is wrong (HANDBOOK §8).")
    distills = [e for e in capture if e.get("kind") == "distill"]
    if distills:
        last = distills[-1]
        lines.append(f"auto-distill: {len(distills)} run(s) · last promoted "
                     f"{last.get('stored', 0)} node(s), {last.get('linked', 0)} link(s), "
                     f"{last.get('residue', 0)} residue")
    found = sum(1 for e in recalls if e.get("found"))
    lines.append(f"explicit:    {len(recalls)} memory tool call(s), {found} found")
    lines.append(f"miss report: {n_miss} miss(es), {n_gap} capture gap(s) (all time)"
                 + (" → `claude-memory-graph misses`" if n_miss or n_gap else ""))
    if undistilled >= 0:
        lines.append(f"distill:     {undistilled} undistilled context file(s)"
                     + (" → run `claude-memory-graph distill`" if undistilled else ""))
    return "\n".join(lines)
