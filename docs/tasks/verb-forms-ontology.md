# Task: verb forms + domain/range in the ontology

Status: **done — base.ttl 0.4.0 annotates all 16 relations with verbForms + domainIncludes/rangeIncludes (schema.org-style union hints); store.relation_lexicon() exposes the planner lexicon; add_relation/memory_link require verb forms for new relations; _ensure_base_ontology keys on verbForms so pre-upgrade stores reload the base without losing LLM additions** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Each relation in [base.ttl](../../claude_memory_graph/base.ttl) gains `mem:verbForms`
("works on", "working on") and domain/range hints; `add_relation` requires verb forms for
LLM-added relations. The schema graph becomes the query planner's verb lexicon — new
relations are instantly groundable with zero code changes.

## Notes

- ~16 relations to annotate by hand; `memory_link`'s extension flow gains one parameter.
- Domain/range are *hints* for edge direction in the planner, not validation constraints.

## Test

pytest: `valid_relations()` exposes verb forms; `add_relation` without them errors.
