"""`claude-memory-graph share`: one project's memories as a separate store.

For a handover — a colleague's Claude querying what you know about a project
while you're away — serve a COPY holding only that project's neighbourhood,
never the live graph. Filtering the live graph per request would leak:
SPARQL reaches every graph, and one shared concept ("arches") bridges into
every other project linked to it. A copy can only ever leak what is in it,
and you can read it before anyone connects (`--dry-run`, or `reflect` on it).

The boundary (reachability is not exposure — docs/future/SHARING.md):
- the Project node, everything linked to it, and one hop further out from
  those memories (a Decision's Technology, a Pattern's Task);
- never expanded THROUGH a concept or another Project/Person/Company: those
  are hubs into unrelated work, so they are included as endpoints only;
  other Projects, People and Companies reached at the second hop are left out;
- Preference concepts are personal and never shared;
- Person nodes keep name and role only;
- provenance (which session or document a memory came from) is stripped;
- forgotten nodes and closed links are left out.

Then: `claude-memory-graph serve --store <out> --read-only --token ...`.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pyoxigraph as ox

from .namespaces import (GRAPH_CONCEPTS, GRAPH_LINKS, GRAPH_RESOURCE_BASE, GRAPH_SCHEMA,
                         MEM, RDF_TYPE)
from .store import MemoryStore

# Nodes that bridge into unrelated work: shared as endpoints, never walked through.
_HUB_MODELS = {"Project", "Person", "Company"}
_PRIVATE_CONCEPTS = {"Preference"}
_PROVENANCE = {"sourceContext", "sourceDocument", "sourceKind", "capturedBy"}
_PERSON_KEEP = {"name", "role", "createdAt", "updatedAt"}


@dataclass
class ShareResult:
    project: str
    nodes: dict[str, list[str]] = field(default_factory=dict)  # model -> names
    links: int = 0
    out: Path | None = None

    def summary(self) -> str:
        total = sum(len(v) for v in self.nodes.values())
        lines = [f"share of project '{self.project}': {total} nodes, {self.links} links"
                 + (f" -> {self.out}" if self.out else " (dry run, nothing written)")]
        for model in sorted(self.nodes):
            names = sorted(self.nodes[model])
            lines.append(f"  {model} ({len(names)}): " + ", ".join(names))
        return "\n".join(lines)


def _local(value: str) -> str:
    return value[len(MEM):] if value.startswith(MEM) else value


def share(store: MemoryStore, project: str, out: Path | None = None,
          depth: int = 2) -> ShareResult:
    found = store.find_resource("Project", project)
    if found is None:
        raise ValueError(f"no Project named '{project}' in this store")
    _, root = found
    raw = store._store

    # What every node is, and whether it is alive.
    model_of: dict[str, str] = {}
    name_of: dict[str, str] = {}
    dead: set[str] = set()
    for q in raw.quads_for_pattern(None, None, None, None):
        g = q.graph_name.value if isinstance(q.graph_name, ox.NamedNode) else ""
        if not (g.startswith(GRAPH_RESOURCE_BASE) or g == GRAPH_CONCEPTS):
            continue
        s, p = q.subject.value, q.predicate.value
        if q.predicate == RDF_TYPE and isinstance(q.object, ox.NamedNode):
            model_of[s] = _local(q.object.value)
        elif p in (f"{MEM}name", f"{MEM}label"):
            name_of[s] = q.object.value
        elif p == f"{MEM}invalidated":
            dead.add(s)

    # Open links only — closed (bi-temporal bound) or invalidated ones are history.
    links: dict[str, tuple[str, str]] = {}
    closed: set[str] = set()
    for q in raw.quads_for_pattern(None, None, None, ox.NamedNode(GRAPH_LINKS)):
        link, p = q.subject.value, q.predicate.value
        if p in (f"{MEM}linkValidUntil", f"{MEM}linkInvalidatedAt"):
            closed.add(link)
        elif p == f"{MEM}linkSource":
            links[link] = (q.object.value, links.get(link, ("", ""))[1])
        elif p == f"{MEM}linkTarget":
            links[link] = (links.get(link, ("", ""))[0], q.object.value)
    adjacency: dict[str, set[str]] = {}
    for link, (s, t) in links.items():
        if link in closed or not s or not t:
            continue
        adjacency.setdefault(s, set()).add(t)
        adjacency.setdefault(t, set()).add(s)

    def shareable(node: str, hop: int) -> bool:
        model = model_of.get(node, "")
        if node in dead or not model or model in _PRIVATE_CONCEPTS:
            return False
        # at the second hop, another project/person/company is someone else's
        return not (hop >= 2 and model in _HUB_MODELS)

    def expandable(node: str) -> bool:
        return model_of.get(node) not in _HUB_MODELS and node not in concepts

    concepts = {n for n, m in model_of.items()
                if any(True for _ in raw.quads_for_pattern(ox.NamedNode(n), RDF_TYPE, None,
                                                           ox.NamedNode(GRAPH_CONCEPTS)))}
    included = {root.value}
    frontier = [root.value]
    for hop in range(1, depth + 1):
        nxt = []
        for node in frontier:
            if hop > 1 and not expandable(node):
                continue
            for other in adjacency.get(node, ()):
                if other not in included and shareable(other, hop):
                    included.add(other)
                    nxt.append(other)
        frontier = nxt

    result = ShareResult(project=project)
    for node in included:
        result.nodes.setdefault(model_of.get(node, "?"), []).append(name_of.get(node, node))
    kept_links = [link for link, (s, t) in links.items()
                  if link not in closed and s in included and t in included]
    result.links = len(kept_links)
    if out is None:
        return result

    subset = ox.Store()
    schema = ox.NamedNode(GRAPH_SCHEMA)
    for q in raw.quads_for_pattern(None, None, None, schema):
        subset.add(q)
    for node in included:
        is_concept = node in concepts
        graph = ox.NamedNode(GRAPH_CONCEPTS if is_concept
                             else GRAPH_RESOURCE_BASE + node.rsplit("/", 1)[-1])
        person = model_of.get(node) == "Person"
        for q in raw.quads_for_pattern(ox.NamedNode(node), None, None, graph):
            key = _local(q.predicate.value)
            if key in _PROVENANCE or (person and q.predicate != RDF_TYPE and key not in _PERSON_KEEP):
                continue
            subset.add(q)
    links_graph = ox.NamedNode(GRAPH_LINKS)
    for link in kept_links:
        for q in raw.quads_for_pattern(ox.NamedNode(link), None, None, links_graph):
            subset.add(q)

    out.mkdir(parents=True, exist_ok=True)
    nq = out / "graph.nq"
    if nq.exists():
        raise FileExistsError(f"{nq} already exists — choose an empty folder")
    with open(nq, "wb") as f:
        subset.dump(f, ox.RdfFormat.N_QUADS)
    # tells a server's chat what this store is (chat.py)
    import json
    from datetime import date
    (out / "share.json").write_text(json.dumps(
        {"project": project, "created": date.today().isoformat(), "depth": depth}))
    result.out = out
    return result
