"""Plans → an Arches Search advanced-search payload (arches-search's GroupPayload).

    from ceist.arches import ArchesVocabulary
    from ceist.arches_search import to_payload
    vocab = ArchesVocabulary.from_data_dir("data")
    payload = to_payload(interpret(vocab, "which sites have buildings designed by Ada?").plan, vocab)
    # POST it to the plugin's advanced-search endpoint, or load it into the UI

Mapping:

    Plan(type)                       a group on that model's graph slug, logic AND
    LinkTo(node, EntityRef, out)     clause: NODE (slug, node) REFERENCES_ANY [id]
    LinkTo(node, Plan, out)          child group, relationship {path: (this slug, node),
                                     is_inverse: false} — the node is on this model
    LinkTo(node, Plan, in)           child group, relationship {path: (child slug, node),
                                     is_inverse: true} — the node is on the other model
    HasValue(concept)                clause: NODE (slug, field) <concept_operator>
                                     [the concept and every narrower concept]

Arches Search walks relationships both ways, so — unlike Rós Madair — "sites
that have buildings designed by Ada" compiles. What it can't say, the compiler
refuses by name (Unsupported):

- concept values, unless `concept_operator` is given: arches-search indexes
  concept ids but seeds no search facets for the concept datatype, so the
  operator depends on what a deployment has added;
- a link by any field, or a link to one named record walked backwards
  (a clause names the node it filters, on the model being searched);
- free text and literal values; "count" and "most recent" are the caller's
  (the search response carries the count).
"""

from .plan import Contains, EntityRef, HasValue, LinkTo, Mention, Plan
from .rosmadair import Unsupported

__all__ = ["Unsupported", "to_payload"]


def _clause(slug: str, alias: str, operator: str, values: list, display: str = "") -> dict:
    operand = {"type": "LITERAL", "value": values}
    if display:
        operand["display_value"] = display
    return {"type": "LITERAL", "quantifier": "ANY",
            "subject": {"type": "NODE", "graph_slug": slug, "node_alias": alias,
                        "search_models": []},
            "operator": operator, "operands": [operand]}


def _relationship(slug: str, alias: str, inverse: bool) -> dict:
    return {"path": {"type": "NODE", "graph_slug": slug, "node_alias": alias},
            "is_inverse": inverse, "traversal_quantifier": "ANY"}


def _group(plan: Plan, vocab, relationship: dict | None, concept_operator: str | None) -> dict:
    slug = vocab.model(plan.type).slug
    clauses, groups = [], []
    for c in plan.where:
        if isinstance(c, LinkTo):
            if c.relation is None:
                raise Unsupported(f"a link by any field to '{c.target.entity.name}': "
                                  "an Arches Search clause names the node it filters")
            if isinstance(c.target, EntityRef):
                if c.direction != "out":
                    raise Unsupported(f"walking '{c.relation}' backwards to one record "
                                      f"('{c.target.entity.name}')")
                e = c.target.entity
                clauses.append(_clause(slug, c.relation, "REFERENCES_ANY", [e.id], e.name))
            elif c.direction == "out":
                groups.append(_group(c.target, vocab, _relationship(slug, c.relation, False),
                                     concept_operator))
            else:
                child = vocab.model(c.target.type).slug
                groups.append(_group(c.target, vocab, _relationship(child, c.relation, True),
                                     concept_operator))
        elif isinstance(c, HasValue):
            if c.kind != "concept":
                raise Unsupported(f"the literal value {c.label}")
            if not concept_operator:
                raise Unsupported(f"the concept {c.label}: arches-search seeds no facets for "
                                  "concept nodes; pass concept_operator= for the one your "
                                  "deployment adds")
            ids = [c.value] + vocab.descendants(c.value)
            clauses.append(_clause(slug, c.field, concept_operator, ids, c.label))
        elif isinstance(c, (Mention, Contains)):
            term = c.term if isinstance(c, Contains) else " ".join(c.terms)
            raise Unsupported(f"a free-text condition ('{term}'): use Arches Search's "
                              "term search for words")
    return {"graph_slug": slug, "scope": "RESOURCE", "logic": "AND", "clauses": clauses,
            "groups": groups, "aggregations": [], "relationship": relationship}


def to_payload(plan: Plan, vocab, concept_operator: str | None = None) -> dict:
    """The arches-search GroupPayload for a plan (raises Unsupported)."""
    return _group(plan, vocab, None, concept_operator)
