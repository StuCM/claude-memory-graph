"""Plans → an Arches Search advanced-search payload (arches-search's GroupPayload),
and read back.

    from ceist.arches import ArchesVocabulary
    from ceist.arches_search import compile_checked, to_payload
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
    DateRange(node, lo, hi)          clause: BETWEEN [lo, hi] / GREATER_THAN_OR_EQUALS [lo] /
                                     LESS_THAN_OR_EQUALS [hi]   (ISO dates)
    Not(clause)                      the clause with quantifier NONE
    Not(link to a sub-plan)          the child group's traversal_quantifier NONE
    LinkTo(…, qualifier)             a TILE-scoped group: the link clause and the value clause
                                     must hold in one tile — the whole search when it's the
                                     only condition, otherwise a nested group (ARCHES-SEARCH.md)

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

`read_back(payload, vocab)` turns a payload back into a plan; `compile_checked`
compiles and refuses if the payload reads back differently from the plan.
"""

from .plan import Contains, DateRange, EntityRef, HasValue, LinkTo, Mention, Not, Plan
from .readback import Check, check
from .rosmadair import Unsupported

__all__ = ["Unsupported", "compile_checked", "read_back", "to_payload"]


def _clause(slug: str, alias: str, operator: str, values: list, negated: bool,
            display: str = "") -> dict:
    operands = [{"type": "LITERAL", "value": v} for v in values]
    if display and operands:
        operands[0]["display_value"] = display
    return {"type": "LITERAL", "quantifier": "NONE" if negated else "ANY",
            "subject": {"type": "NODE", "graph_slug": slug, "node_alias": alias,
                        "search_models": []},
            "operator": operator, "operands": operands}


def _relationship(slug: str, alias: str, inverse: bool, negated: bool) -> dict:
    return {"path": {"type": "NODE", "graph_slug": slug, "node_alias": alias},
            "is_inverse": inverse, "traversal_quantifier": "NONE" if negated else "ANY"}


def _group(plan: Plan, vocab, relationship: dict | None, concept_operator: str | None) -> dict:
    slug = vocab.model(plan.type).slug
    clauses, groups = [], []
    for c in plan.where:
        negated = isinstance(c, Not)
        c = c.condition if negated else c
        if isinstance(c, LinkTo) and c.qualifier is not None:
            tile = _tile_group(c, negated, vocab, slug, concept_operator)
            if len(plan.where) == 1 and relationship is None:
                return tile              # the whole search is one entry: TILE at the top
            groups.append(tile)          # alongside other conditions: a nested TILE group
            continue
        if isinstance(c, LinkTo):
            if c.relation is None:
                raise Unsupported(f"a link by any field to '{c.target.entity.name}': "
                                  "an Arches Search clause names the node it filters")
            if isinstance(c.target, EntityRef):
                if c.direction != "out":
                    raise Unsupported(f"walking '{c.relation}' backwards to one record "
                                      f"('{c.target.entity.name}')")
                e = c.target.entity
                clauses.append(_clause(slug, c.relation, "REFERENCES_ANY", [[e.id]], negated,
                                       e.name))
            elif c.direction == "out":
                groups.append(_group(c.target, vocab,
                                     _relationship(slug, c.relation, False, negated),
                                     concept_operator))
            else:
                child = vocab.model(c.target.type).slug
                groups.append(_group(c.target, vocab,
                                     _relationship(child, c.relation, True, negated),
                                     concept_operator))
        elif isinstance(c, HasValue):
            if c.kind != "concept":
                raise Unsupported(f"the literal value {c.label}")
            if not concept_operator:
                raise Unsupported(f"the concept {c.label}: arches-search seeds no facets for "
                                  "concept nodes; pass concept_operator= for the one your "
                                  "deployment adds")
            ids = [c.value] + vocab.descendants(c.value)
            clauses.append(_clause(slug, c.field, concept_operator, [ids], negated, c.label))
        elif isinstance(c, DateRange):
            if c.lo and c.hi:
                op, values = "BETWEEN", [c.lo, c.hi]
            elif c.lo:
                op, values = "GREATER_THAN_OR_EQUALS", [c.lo]
            else:
                op, values = "LESS_THAN_OR_EQUALS", [c.hi]
            clauses.append(_clause(slug, c.field, op, values, negated))
        elif isinstance(c, (Mention, Contains)):
            term = c.term if isinstance(c, Contains) else " ".join(c.terms)
            raise Unsupported(f"a free-text condition ('{term}'): use Arches Search's "
                              "term search for words")
    return {"graph_slug": slug, "scope": "RESOURCE", "logic": "AND", "clauses": clauses,
            "groups": groups, "aggregations": [], "relationship": relationship}


def _tile_group(c: LinkTo, negated: bool, vocab, slug: str, concept_operator) -> dict:
    """A link with a qualifier ("actor Ada with role Architect") must hold in
    one tile: a TILE-scoped group holding the link clause and the value clause.
    On its own it is the whole search; alongside other conditions it nests
    under the resource group (see ARCHES-SEARCH.md on how the plugin evaluates
    a nested TILE group)."""
    if negated:
        raise Unsupported("a negated same-entry condition")
    if not isinstance(c.target, EntityRef) or c.direction != "out":
        raise Unsupported("a same-entry condition on a link to a set of records")
    if not concept_operator:
        raise Unsupported(f"the value {c.qualifier.label}: arches-search seeds no facets for "
                          "concept nodes; pass concept_operator=")
    e, q = c.target.entity, c.qualifier
    ids = [q.value] + vocab.descendants(q.value)
    return {"graph_slug": slug, "scope": "TILE", "logic": "AND",
            "clauses": [_clause(slug, c.relation, "REFERENCES_ANY", [[e.id]], False, e.name),
                        _clause(slug, q.field, concept_operator, [ids], False, q.label)],
            "groups": [], "aggregations": [], "relationship": None}


def to_payload(plan: Plan, vocab, concept_operator: str | None = None) -> dict:
    """The arches-search GroupPayload for a plan (raises Unsupported)."""
    if plan.recent:
        raise Unsupported("'most recent': order the search results instead")
    return _group(plan, vocab, None, concept_operator)


# ── read-back: a payload → a plan again ──────────────────────────────────

def _read_clause(clause: dict, type_name: str, vocab, concept_operator: str | None):
    s = clause["subject"]
    alias, op = s["node_alias"], clause["operator"]
    values = [o["value"] for o in clause["operands"]]
    node = vocab.node(type_name, alias) or {}
    datatype = node.get("datatype", "")
    cond = None
    if op == "REFERENCES_ANY" and "resource-instance" in datatype and len(values) == 1 \
            and len(values[0]) == 1:
        e = vocab.entity(values[0][0])
        cond = LinkTo(alias, EntityRef(e), "out", style="field") if e else None
    elif op == concept_operator and datatype.startswith("concept") and len(values) == 1:
        ids = values[0]
        # the first id is the concept; the rest must be exactly its narrower concepts
        if ids and sorted(ids[1:]) == sorted(vocab.descendants(ids[0])):
            cond = HasValue(alias, ids[0], vocab.concept_label(ids[0]))
    elif datatype == "date":
        label = vocab.date_label(type_name, alias)
        if op == "BETWEEN" and len(values) == 2:
            cond = DateRange(alias, values[0], values[1], label)
        elif op == "GREATER_THAN_OR_EQUALS" and len(values) == 1:
            cond = DateRange(alias, values[0], None, label)
        elif op == "LESS_THAN_OR_EQUALS" and len(values) == 1:
            cond = DateRange(alias, None, values[0], label)
    if cond is None:
        return f"{alias} {op} {values}"           # unknown to read-back: reads as a mismatch
    return Not(cond) if clause["quantifier"] == "NONE" else cond


def _read_group(group: dict, vocab, concept_operator: str | None) -> Plan:
    model = vocab.model_by_slug(group["graph_slug"])
    type_name = model.name if model else group["graph_slug"]
    where = [_read_clause(c, type_name, vocab, concept_operator) for c in group["clauses"]]
    for child in group["groups"]:
        sub = _read_group(child, vocab, concept_operator)
        rel = child.get("relationship")
        if rel is None:
            # a nested TILE group on the same model reads back as its qualified link
            if child.get("scope") == "TILE" and sub.type == type_name and len(sub.where) == 1:
                where += sub.where
            else:
                where.append(f"an unlinked group on {sub.type}")
            continue
        link = LinkTo(rel["path"]["node_alias"], sub, "in" if rel["is_inverse"] else "out",
                      style="field")
        where.append(Not(link) if rel["traversal_quantifier"] == "NONE" else link)
    if group["logic"] != "AND":
        where.append(f"logic {group['logic']}")
    if group.get("scope") == "TILE":
        links = [c for c in where if isinstance(c, LinkTo)]
        quals = [c for c in where if isinstance(c, HasValue)]
        if len(links) == 1 and len(quals) == 1 and len(where) == 2:
            from dataclasses import replace
            where = [replace(links[0], qualifier=quals[0])]
        else:
            where.append("tile scope over more than one link and value")
    return Plan(type_name, where)


def read_back(payload: dict, vocab, concept_operator: str | None = None) -> Plan:
    """What a payload selects, as a plan."""
    return _read_group(payload, vocab, concept_operator)


def compile_checked(plan: Plan, vocab, concept_operator: str | None = None
                    ) -> tuple[dict, Check]:
    """The payload, and its read-back check against the plan. Raises
    Unsupported if it can't compile, or if the payload says something else."""
    payload = to_payload(plan, vocab, concept_operator)
    said = read_back(payload, vocab, concept_operator)
    said.count = plan.count                     # the response carries the count
    verdict = check(plan, said)
    if not verdict.ok:
        raise Unsupported("the payload reads back differently from the question:\n"
                          + "\n".join(verdict.lines()))
    return payload, verdict
