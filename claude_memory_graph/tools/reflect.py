from typing import Optional

import pyoxigraph as ox

from ..store import MemoryStore
from ..namespaces import MEM, GRAPH_RESOURCE_BASE, GRAPH_CONCEPTS, GRAPH_LINKS


def _local(term) -> str:
    v = term.value if isinstance(term, (ox.NamedNode, ox.Literal)) else str(term)
    return v[len(MEM):] if v.startswith(MEM) else v


def handle(store: MemoryStore, model_filter: Optional[str]) -> str:
    report = []

    report.append("## Resources by Model")
    type_filter = f"FILTER(?type = mem:{model_filter})" if model_filter else ""
    sparql = (
        f'SELECT ?type (COUNT(DISTINCT ?node) as ?count) WHERE {{\n'
        f'    GRAPH ?g {{\n'
        f'        ?node rdf:type ?type .\n'
        f'        FILTER NOT EXISTS {{ ?node mem:invalidated ?inv }}\n'
        f'    }}\n'
        f'    FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))\n'
        f'    {type_filter}\n'
        f'}} GROUP BY ?type ORDER BY DESC(?count)'
    )
    for solution in store.query(sparql):
        if solution["type"] is not None and solution["count"] is not None:
            report.append(f"- {_local(solution['type'])}: {_local(solution['count'])}")

    report.append("\n## Concepts")
    sparql = (
        f'SELECT ?type (COUNT(?node) as ?count) WHERE {{\n'
        f'    GRAPH <{GRAPH_CONCEPTS}> {{ ?node rdf:type ?type . }}\n'
        f'}} GROUP BY ?type ORDER BY DESC(?count)'
    )
    any_concepts = False
    for solution in store.query(sparql):
        if solution["type"] is not None and solution["count"] is not None:
            report.append(f"- {_local(solution['type'])}: {_local(solution['count'])}")
            any_concepts = True
    if not any_concepts:
        report.append("None")

    report.append("\n## Cross-Links by Relation")
    sparql = (
        f'SELECT ?rel (COUNT(?link) as ?count) WHERE {{\n'
        f'    GRAPH <{GRAPH_LINKS}> {{\n'
        f'        ?link rdf:type mem:CrossLink .\n'
        f'        ?link mem:linkRelation ?rel .\n'
        f'    }}\n'
        f'}} GROUP BY ?rel ORDER BY DESC(?count)'
    )
    any_links = False
    for solution in store.query(sparql):
        if solution["rel"] is not None and solution["count"] is not None:
            report.append(f"- {_local(solution['rel'])}: {_local(solution['count'])}")
            any_links = True
    if not any_links:
        report.append("None")

    report.append("\n## Available Relations (ontology)")
    for name, desc in sorted(store.valid_relations().items()):
        report.append(f"- {name} — {desc}" if desc else f"- {name}")

    from .. import gaps as gaps_mod
    report.append("")
    report.append(gaps_mod.handle(store, limit=5))

    report.append("\n## Recently Added Resources")
    sparql = (
        f'SELECT ?node ?type ?name ?created WHERE {{\n'
        f'    GRAPH ?g {{\n'
        f'        ?node rdf:type ?type .\n'
        f'        ?node mem:createdAt ?created .\n'
        f'        OPTIONAL {{ ?node mem:name ?n }}\n'
        f'        BIND(COALESCE(?n, "unnamed") AS ?name)\n'
        f'        FILTER NOT EXISTS {{ ?node mem:invalidated ?inv }}\n'
        f'    }}\n'
        f'    FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))\n'
        f'}} ORDER BY DESC(?created) LIMIT 10'
    )
    any_recent = False
    for solution in store.query(sparql):
        if solution["name"] is not None and solution["type"] is not None:
            report.append(f"- {_local(solution['name'])} ({_local(solution['type'])})")
            any_recent = True
    if not any_recent:
        report.append("None")

    return "\n".join(report)
