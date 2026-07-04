# Task: verb forms + domain/range in the ontology

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

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
