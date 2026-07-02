import json

import pyoxigraph as ox

from ..store import MemoryStore
from ..namespaces import MEM, RDF, RDFS, XSD


_PREFIXES = [(MEM, "mem:"), (RDF, "rdf:"), (RDFS, "rdfs:"), (XSD, "xsd:")]


def _term(term) -> str:
    if isinstance(term, ox.NamedNode):
        for iri, prefix in _PREFIXES:
            if term.value.startswith(iri):
                return prefix + term.value[len(iri):]
        return term.value
    if isinstance(term, ox.Literal):
        return term.value
    return str(term)


def handle(store: MemoryStore, sparql: str) -> str:
    results = store.query(sparql)

    if isinstance(results, ox.QuerySolutions):
        variables = list(results.variables)
        rows = []
        for solution in results:
            row = {}
            for var in variables:
                term = solution[var]
                if term is not None:
                    row[var.value] = _term(term)
            rows.append(row)
        if not rows:
            return "No results."
        return json.dumps(rows, separators=(",", ":"), ensure_ascii=False)

    if isinstance(results, bool):
        return str(results).lower()

    # CONSTRUCT / DESCRIBE → QueryTriples
    lines = []
    for triple in results:
        lines.append(f"{_term(triple.subject)} {_term(triple.predicate)} {_term(triple.object)} .")
    return "\n".join(lines) if lines else "No results."
