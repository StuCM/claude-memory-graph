"""Chains through the graph from free text: the best-matching nodes as entry
points, then at each hop only the edges that score best against the text.
`crew graph chain` prints this."""

import pyoxigraph as ox

from .gate.recall import _bigrams, _corpus, _idf, _score
from .hookcore import terms_pos
from .store import MemoryStore
from .tools.recall import _beam

SEEDS = 6


def _line(model: str, props: dict) -> str:
    project = (props.get("sourceContext") or "").split("__")[0]
    where = " @ ".join(p for p in (project, props.get("anchorPath")) if p)
    name = props.get("name") or props.get("label", "")
    return f'{model} "{name}"' + (f"  [{where}]" if where else "")


def _clip(text: str, n: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _entry_points(store: MemoryStore, text: str) -> list[dict]:
    """The best-matching live nodes, as memory_search ranks them (one matcher
    for the gate, search and chain), Projects left out: a project is the
    neighbourhood, not a place to start."""
    q_pos = terms_pos(text)
    q = {w for _, w in q_pos}
    docs = [d for d in _corpus(store) if d.get("gid") and d["model"] != "Project"]
    if not q or not docs:
        return []
    idf, q_bi = _idf(docs), _bigrams(q_pos)
    ranked = sorted(((_score(q, d, idf, q_bi), d) for d in docs), key=lambda x: x[0],
                    reverse=True)[:SEEDS * 2]
    return [{**d, "score": s} for s, d in ranked if s > 0]


def chain(store: MemoryStore, text: str, depth: int = 2, limit: int = 40) -> list[str]:
    ranked = _entry_points(store, text)
    best = ranked[0]["score"] if ranked else 0
    seeds = [d for d in ranked if d["score"] >= best / 2][:SEEDS]
    if not seeds:
        return [f'graph: nothing matches "{text}"']

    nodes: dict[str, tuple[str, dict, str]] = {}  # iri -> (model, props, edge text)
    children: dict[str, list[str]] = {}
    roots = []
    for d in seeds:
        nodes[d["iri"]] = (d["model"], store.get_resource_properties(
            ox.NamedNode(d["iri"]), d["gid"]), "")
        roots.append(d["iri"])

    left: list[str] = []
    frontier = roots
    for _hop in range(depth):
        if not frontier or len(nodes) >= limit:
            break
        by_node: dict[str, list] = {}
        for me, lr in store._neighbours([ox.NamedNode(i) for i in frontier]):
            if (lr.iri.value not in nodes and lr.model != "Project"
                    and lr.properties.get("invalidated") != "true"):
                by_node.setdefault(me, []).append(lr)
        next_frontier = []
        for me in frontier:
            found = list({lr.iri.value: lr for lr in by_node.get(me, [])}.values())
            chosen = _beam(found, text)
            if len(chosen) < len(found):
                left.append(f"{nodes[me][1].get('name') or nodes[me][1].get('label', '')} "
                            f"({len(found) - len(chosen)} more)")
            for lr in chosen:
                if lr.iri.value in nodes or len(nodes) >= limit:
                    continue
                edge = f"{lr.relation} → " if lr.direction == "outgoing" else f"← {lr.relation} "
                nodes[lr.iri.value] = (lr.model, lr.properties, edge)
                children.setdefault(me, []).append(lr.iri.value)
                next_frontier.append(lr.iri.value)
        frontier = next_frontier

    out: list[str] = []

    def render(iri: str, indent: str) -> None:
        model, props, edge = nodes[iri]
        out.append(f"{indent}{edge}{_line(model, props)}")
        if props.get("description"):
            out.append(f"{indent}    {_clip(props['description'])}")
        for child in children.get(iri, []):
            render(child, indent + "  ")

    for root in roots:
        render(root, "")
    # Each says the chain could have gone further, so the reader can ask for
    # more rather than assume it had everything.
    if left:
        out += ["", f"not followed, ranked below the best edges: {', '.join(left)}"]
    if frontier and len(nodes) < limit:
        names = [nodes[i][1].get("name") or nodes[i][1].get("label", "") for i in frontier[:5]]
        more = f" and {len(frontier) - 5} more" if len(frontier) > 5 else ""
        out += ["", f"not expanded, depth {depth} reached: {', '.join(names)}{more}"]
    if len(nodes) >= limit:
        out += ["", f"stopped at {limit} nodes — narrow the text or pass --limit=N"]
    return out
