---
name: reflect
description: Introspect the memory graph - find missing links, orphaned nodes, stale knowledge, and redundant relations, then strengthen connections. Use when the user says "reflect on memory", "find missing links", "tidy the graph", or "review the memory graph".
---

# Reflect on the Memory Graph — Find Missing Links and Patterns

You are a graph introspection agent: examine the memory graph, find patterns, and strengthen connections between knowledge.

## Steps

### 1. Current state
Call `memory_reflect` — counts by model, concepts, links by relation, available relations, recent additions.

### 2. Explore
Architecture: each resource lives in its own named graph (`https://memory.claude.local/graph/resource/<uuid>`); concepts in `…/graph/concepts`; links are reified CrossLink nodes in `…/graph/links`; the ontology in `…/graph/schema`. Useful `memory_query` queries:

**All nodes with types and names:**
```sparql
SELECT ?type ?name WHERE {
  GRAPH ?g {
    ?node rdf:type ?type .
    OPTIONAL { ?node mem:name ?n } OPTIONAL { ?node mem:label ?l }
    BIND(COALESCE(?n, ?l) AS ?name)
  }
  FILTER(STRSTARTS(STR(?g), "https://memory.claude.local/graph/resource/") || STR(?g) = "https://memory.claude.local/graph/concepts")
} ORDER BY ?type ?name
```

**Orphans (no links at all):** add to the query above:
```sparql
  FILTER NOT EXISTS {
    GRAPH <https://memory.claude.local/graph/links> {
      { ?link mem:linkSource ?node } UNION { ?link mem:linkTarget ?node }
    }
  }
```

**LLM-added relations (base ontology relations lack definedAt):**
```sparql
SELECT ?rel ?desc ?added WHERE {
  GRAPH <https://memory.claude.local/graph/schema> {
    ?rel rdf:type mem:RelationType .
    OPTIONAL { ?rel rdfs:comment ?desc }
    OPTIONAL { ?rel mem:definedAt ?added }
    FILTER EXISTS { ?rel mem:definedAt ?t }
  }
}
```

Use `memory_recall` (depth 2) on hub nodes (the user, active projects) to see actual neighbourhoods.

### 3. Find missing links
- **Co-occurring topics:** two nodes repeatedly relevant together but unconnected
- **Implicit chains:** a Person works on a Project that uses a Technology, but the Person↔Technology skill link is missing
- **Decision chains:** Decisions affecting the same Project that supersede or relate to each other
- **Shared concepts:** Constraints/Patterns that apply to more projects than they're linked to

### 4. Create them
`memory_link` for each identified relationship — prefer existing relations; only extend the ontology (`new_relation_description`) when nothing fits. Put rationale in link `metadata` for important ones.

### 5. Staleness and redundancy
- Nodes with old `createdAt` and superseding activity → confirm with the user, then `memory_forget` (soft delete, kept for provenance)
- Overlapping LLM-added relations (e.g. a new relation duplicating `relatesTo`) → suggest consolidation

### 6. Verb-form lexicon health (query planner)
Run `claude-memory-graph asks` (read-only CLI). It joins the planner's telemetry log into two curation signals:
- **Misgrounding suspects** — a verb form that fires but its asks always end with no rows (e.g. a prose word like "under" colliding with a relation). Remove it with `memory_amend_relation` if the relation is LLM-added; for base-ontology relations suggest the base.ttl edit (+ version bump) to the user.
- **Vocabulary gaps** — terms that repeatedly ground to nothing in failed asks. If a gap term is a phrasing of an existing relation, `memory_amend_relation` with `add_verb_forms`; if it's an alternate name of an existing node, add it to that node's `aliases`; if it names something real and absent, capture the node.

### 7. Report
Terse: graph state, links created and why, orphans/stale nodes found, suggested missing knowledge.
