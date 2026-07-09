"""Mechanical link-gap detection — reflection's candidate list.

The reflect skill asks an LLM to *find* missing links by exploring with
SPARQL; live use (a graph visualisation full of unconnected nodes that
plainly belonged together) showed that finding is the wrong job for the
LLM. Division of labour, same as everywhere else in this system:
**detection is mechanical, judgment is the LLM's.** This module computes
the candidate list; the reflect skill (or a human reading
`claude-memory-graph gaps`) decides which candidates become edges.

Three detectors, all deterministic:
- **orphans** — nodes with no links at all (violates the reachability
  rule: "a node nobody links to is usually not worth storing");
- **conceptless** — nodes with no edge into the concepts graph
  (invisible to associative recall — concepts are the fan-out index);
- **suggestions** — unlinked node pairs sharing rare vocabulary (IDF-
  weighted, same scorer as the gate). Shared rare words are exactly the
  evidence the analyzer would use at read time, so a high-scoring
  unlinked pair is a traversal the graph is silently missing.
"""

from dataclasses import dataclass, field

from .gate.recall import _corpus, _idf
from .gate.runtime import config
from .namespaces import GRAPH_CONCEPTS, GRAPH_LINKS
from .store import MemoryStore


@dataclass
class Gaps:
    orphans: list = field(default_factory=list)        # (model, name)
    conceptless: list = field(default_factory=list)    # (model, name)
    suggestions: list = field(default_factory=list)    # (score, a, b, shared_terms)

    @property
    def empty(self) -> bool:
        return not (self.orphans or self.conceptless or self.suggestions)


def _edge_pairs(store: MemoryStore) -> set[frozenset]:
    """Every linked IRI pair — open or closed (a closed edge means the
    connection was already considered; don't resuggest it)."""
    pairs: set[frozenset] = set()
    for solution in store.query(
        f'SELECT ?s ?t WHERE {{ GRAPH <{GRAPH_LINKS}> {{\n'
        f'    ?l mem:linkSource ?s ; mem:linkTarget ?t . }} }}'
    ):
        pairs.add(frozenset((solution["s"].value, solution["t"].value)))
    return pairs


def _concept_iris(store: MemoryStore) -> set[str]:
    return {solution["n"].value for solution in store.query(
        f'SELECT ?n WHERE {{ GRAPH <{GRAPH_CONCEPTS}> {{ ?n rdf:type ?t }} }}'
    )}


def analyse(store: MemoryStore, limit: int = 10) -> Gaps:
    docs = _corpus(store)
    idf = _idf(docs)
    pairs = _edge_pairs(store)
    linked_iris = {iri for pair in pairs for iri in pair}
    concepts = _concept_iris(store)
    concept_linked = {iri for pair in pairs if pair & concepts
                      for iri in pair if iri not in concepts}

    gaps = Gaps()
    for d in docs:
        label = (d["model"] or "?", d["name"] or d["iri"])
        if d["iri"] not in linked_iris:
            gaps.orphans.append(label)
        elif d["iri"] not in concept_linked:
            gaps.conceptless.append(label)

    floor = config()["GAP_MIN"]
    for i, a in enumerate(docs):
        for b in docs[i + 1:]:
            if frozenset((a["iri"], b["iri"])) in pairs:
                continue
            shared = a["terms"] & b["terms"]
            if len(shared) < 2:
                continue
            # Same weighting philosophy as the gate: a shared word that sits
            # in a NAME is a much stronger signal than body-text overlap.
            score = sum(
                idf.get(t, 0.0)
                * (3.0 if t in a["name_terms"] or t in b["name_terms"] else 1.0)
                for t in shared)
            if score >= floor:
                gaps.suggestions.append((round(score, 1), a, b, sorted(shared)))
    gaps.suggestions.sort(key=lambda s: s[0], reverse=True)
    gaps.suggestions = gaps.suggestions[:limit]
    return gaps


def render(gaps: Gaps, header: str = "## Gaps (mechanical candidates — judge, then link or dismiss)") -> str:
    if gaps.empty:
        return f"{header}\nNone — every node is linked and concept-indexed."
    lines = [header]
    if gaps.orphans:
        lines.append("Orphans (no links at all — unreachable by traversal):")
        lines += [f"- {m} '{n}'" for m, n in gaps.orphans]
    if gaps.conceptless:
        lines.append("No concept link (invisible to associative recall):")
        lines += [f"- {m} '{n}'" for m, n in gaps.conceptless]
    if gaps.suggestions:
        lines.append("Unlinked pairs sharing rare vocabulary (strongest first):")
        lines += [
            f"- {a['model']} '{a['name']}' ↔ {b['model']} '{b['name']}'"
            f"  (shared: {', '.join(shared[:5])}; {score})"
            for score, a, b, shared in gaps.suggestions
        ]
    return "\n".join(lines)


def handle(store: MemoryStore, limit: int = 10) -> str:
    return render(analyse(store, limit=limit))
