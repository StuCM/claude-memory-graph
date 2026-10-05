"""Per-node usage, read from the telemetry that already records it.

Nothing writes usage onto the nodes themselves, and nothing should: hooks
run as separate processes while the MCP server holds the graph in memory
and saves after every mutation, so a hook-side write would be clobbered by
the session's next save (the same constraint that keeps `distill` out of a
live session). The counts are derivable anyway — `injections.jsonl` has
carried the injected node names since the gate shipped, and
`explicit-recalls.jsonl` the deliberate ones.

What this answers is whether a memory is DEAD or merely UNFINDABLE, which
is the distinction any future decay or tiering scheme stands on. A node
nobody ever reached is not evidence of staleness: on the live graph, 62%
of nodes had never been injected, and their names were no longer than the
ones that had, so the cause is missing concept links and aliases rather
than age. Demote on that and you punish bad capture while the rarely-
needed-but-critical memory goes first.
"""

import time
from collections import Counter

from .pulse import _read_jsonl


def counts(days: float | None = None) -> tuple[Counter, Counter]:
    """(ambient injections, explicit recalls) per node name."""
    cutoff = 0.0 if days is None else time.time() - days * 86400
    ambient: Counter = Counter()
    for entry in _read_jsonl("injections.jsonl", cutoff):
        for name in entry.get("nodes") or []:
            ambient[str(name)] += 1
    explicit: Counter = Counter()
    for entry in _read_jsonl("explicit-recalls.jsonl", cutoff):
        target = entry.get("target")
        if target:
            # "Decision/Use pyoxigraph over rdflib" -> the name alone, so it
            # joins the ambient counts, which have no model prefix.
            explicit[str(target).split("/", 1)[-1]] += 1
    return ambient, explicit


def report(store, days: float | None = None, show: int = 10) -> str:
    from .recall import _corpus

    ambient, explicit = counts(days)
    used = set(ambient) | set(explicit)
    docs = [d for d in _corpus(store, include_concepts=True) if d["name"]]
    reached = [d for d in docs if d["name"] in used]
    cold = [d for d in docs if d["name"] not in used]

    window = "all time" if days is None else f"last {days:g}d"
    lines = [f"Usage ({window}): {len(reached)}/{len(docs)} nodes reached "
             f"({100 * len(reached) // max(1, len(docs))}%) · "
             f"{len(cold)} never reached"]

    lines.append("\nMost reached:")
    for name, n in (ambient + explicit).most_common(show):
        lines.append(f"  {n:>4}x  {name[:70]}")

    # Cold alone is not a verdict — a node with no concept link never had a
    # chance at ambient recall, and that is a repair, not a demotion. Reuse
    # gaps' own detector rather than guessing from the corpus dict, which
    # carries no link information.
    from ..gaps import _concept_iris, _edge_pairs
    concepts = _concept_iris(store)
    concept_linked = {iri for pair in _edge_pairs(store) if pair & concepts
                      for iri in pair if iri not in concepts}
    conceptless = [d for d in cold if d["iri"] not in concept_linked
                   and d["iri"] not in concepts]
    lines.append(f"\nNever reached: {len(cold)}"
                 + (f" (of which {len(conceptless)} have no concept link — "
                    "repair those before judging them cold)" if conceptless else ""))
    return "\n".join(lines)
