# Arches Search: things to raise

These are behaviours ceist's Arches Search output depends on, or works around, written so each can be raised with the arches-search maintainers. They come from reading the code of the published `arches_search` 0.1.0a22 wheel (PyPI), **not from running it**: a running instance needs a full Arches install with Postgres. Please confirm on a dev instance before raising.

## 1. A nested TILE group may lose its tile scope when the search has no relationship

**What ceist sends:** "listed buildings designed by Ada" becomes a `RESOURCE` group for Building:
- clause: `heritage_status` = Listed;
- child group: `scope: "TILE"`, no relationship, with clauses `actor` REFERENCES_ANY [Ada] and `actor_role` = Architect.

The payload validator accepts this, and the UI can build it (`setScope` per group, `addChildGroupLikeParent`).

**What the code appears to do** (`utils/advanced_search/clause_evaluation/group_compiler.py`):
- `compile()` sends a group without a relationship to `_compile_resource_scope_without_relationship`.
- When **no group in the tree has a relationship**, that calls `_compose_resource_scope_group_predicate`, which recurses into child groups through itself and **never looks at a child's `scope`**. So the TILE child's clauses would be evaluated per resource: "links to Ada somewhere" and "has an Architect role somewhere". That's a broader result: a building Ada *built* and someone else *designed* would match.
- When the tree **does** contain a relationship, children go through `_compile_children` → `compile()`, which **does** honour `scope: "TILE"` (`_compile_tile_scope_without_relationship`, correlated to the outer resource).

**Suggested fix:** in `_compose_resource_scope_group_predicate`, compile a child group whose scope is `TILE` with `_compile_tile_scope_without_relationship` (or route every child through `compile()`), so a nested TILE group means the same thing with or without a relationship elsewhere.

**What ceist does meanwhile:**
- It sends the payload the plugin's own design calls for.
- When the qualified link is the search's only condition, the whole group is `TILE`, which is the unambiguous path.
- ceist's read-back already treats a nested group that has lost its tile scope as a *different* question.

## 2. No search facets for the `concept` datatype

**Seen:** concept nodes are indexed (concept and value ids in `UUIDSearch`), but the migrations seed no `AdvancedSearchFacet` rows for `concept` / `concept-list`. Only `reference` (controlled lists) has `REFERENCES_ANY` / `DESCENDANT_OF` and the like.

**What ceist does:** it needs `concept_operator=` to say which facet a deployment has added, and it sends the concept plus all its narrower concepts as operands. Without that setting it refuses concept conditions by name.

**Suggested fix:** seed concept facets (equals / any-of / descendant-of) as for `reference`.
