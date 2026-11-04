# Task: ceist — Alizarin as the data layer; controlled lists first

Status: planned · Owner: Stuart · Created: 2026-11-04 · Size: M

## Goal

Replace most of ceist's hand-written Arches layer with Alizarin, which was
built to read graph shape, datatypes and the actual data. ceist should keep only
what is specific to search: turning a schema into what a question can name,
and plans into queries. Alizarin becomes a **required** dependency of ceist.

**Controlled lists (`reference` datatype) are the primary kind of controlled
value.** Concepts (`concept`, `concept-list`, SKOS) are legacy. Keep reading
them, but build and test against controlled lists first.

## What ceist rebuilds today that Alizarin already does

Checked against `alizarin` 2.0.0b9 (2026-11-04):

| ceist today | Where | Alizarin instead |
|---|---|---|
| Parses graph JSON by hand: models, nodes, datatypes, aliases, link targets | `arches.py` `ArchesVocabulary.__init__`, `_graph_doc` | `register_graph`, `load_model` → `ResourceModelWrapper` (`get_node_objects_by_alias`, `get_nodegroup_objects`, `get_nodegroup_name`, `get_child_nodes`, `get_collections`) |
| Walks `tiles[].data` flat, ignoring `parenttile_id` | `alizarin.py` `Tiles` | `tiles_to_json_tree` / `batch_tiles_to_trees`: nested per-resource trees, keyed by alias (`get_graph_schema` gives the keys) |
| Guesses localized string shapes | `alizarin.py` `_strings`, `_links` | view models per datatype (`get_view_model`, `StringViewModel`, `ResourceInstanceViewModel`, `DateViewModel`/`EDTFViewModel`, …) |
| Parses SKOS XML for alternative labels, because "Alizarin keeps only preferred labels" | `arches.py` `alt_labels` | `RustRdmConcept.alt_labels`. The workaround looks obsolete: confirm, then delete it |
| Builds label → concept and parent maps by hand | `arches.py` `values`, `concept_of`, `descendants` | `RustRdmCache.lookup_by_label` / `lookup_all_by_label` / `get_concept_id_for_value` / `get_parent_id`, `RustRdmCollection.get_top_concepts`, `RustRdmConcept.narrower`/`broader` |
| Takes record names from precomputed `descriptors` (stale or missing ⇒ UUIDs) | `arches.py` `_entity` | descriptor recompute (`set_descriptor_template`, `batch_merge_resources`/`streamed_merge_from_files` with `recompute_descriptors=True`), or read the name node(s) from the tree directly (typed names: [[ceist-group-grounding]] §4) |
| Concepts only: `CONCEPT_TYPES = {"concept", "concept-list"}` | `arches.py` | `reference` (`StaticNodeConfigReference.controlledList`), `domain-value(-list)` (`DomainValueViewModel`). `resolve_labels`/`get_needed_collections` already treat `concept`, `concept-list` and `reference` alike via `rdmCollection` / `controlledList` |

`arches_describe.py` already uses `register_graph` and `get_graph_schema`. It moves
onto `ResourceModelWrapper` with the rest.

## Also worth taking from Alizarin

- **Permitted nodegroups:** `ResourceModelWrapper.set_permitted_nodegroups` /
  `prune_graph`. Use this for the "private" flag in [[ceist-vocab-pipeline]]. A
  pruned nodegroup is never described to the build LLM, never indexed, and never
  searchable. That's enforced by the data layer, not by a ceist convention.
- **One implementation for Python and the browser:** Alizarin's core is shared
  with WASM/NAPI (`build_tree_from_tiles` docstring). Reading data in the
  browser (the Rós Madair deployment) then matches what ceist evaluates in Python.

## What stays in ceist

- The `Vocabulary` protocol, the grounder, matching, the plan, and narration.
- `ArchesVocabulary` becomes a thin adapter: an Alizarin model plus RDM cache plus
  the bundle → types, relations, values (controlled lists, then concepts, then
  domain values), dates, groups, entities.
- `ceist.alizarin` evaluation runs over Alizarin trees. `OnTile` checks subtrees,
  which gives the parent/child tile semantics [[ceist-group-grounding]] needs.
- The compilers to Rós Madair and Arches Search, unchanged. They take plans, not data.

## Beyond Arches: Alizarin as the shape every source is read into

Alizarin can build graphs from instructions or CSV (`build_graph_from_instructions`,
`build_graph_from_csv`) and turn nested JSON into tiles (`json_tree_to_tiles`).
So a non-Arches source (SQL, RDF, JSON) can be **mapped into an Alizarin graph plus
resources**, and everything above applies unchanged. This replaces the
per-source adapters and the separate `ceist.schema/1` format in
[[ceist-vocab-pipeline]]. The mapping (tables or classes → models, 1:n children →
nodegroups, FKs → resource-instance nodes, enums or lookup tables → controlled
lists) can itself be drafted by the build LLM **from the schema only**, then
reviewed.

What that doesn't solve, to settle per source before promising "any data":
- **Where the query runs.** Rós Madair and Arches Search run Arches-shaped queries.
  A SQL source either gets its data **imported** (a copy: sync, freshness, scale,
  and a second place the sensitive data lives) or needs a compiler from plans to
  native SQL/SPARQL. ceist already has the SPARQL route for the memory graph.
  Decide this per source; don't assume import.
- **Fidelity of the mapping.** Many-to-many joins, polymorphic columns, and
  free-form JSON columns don't map cleanly onto nodegroups. Each mapping needs a
  coverage report: which columns became which nodes, and which were dropped.

## Order

1. Alizarin required (`pyproject.toml`). `ArchesVocabulary` reads models through
   `ResourceModelWrapper`, keeping every current test green.
2. Controlled lists: `reference` nodes become values. Load lists into the RDM cache,
   which needs the format confirmed (controlled-list export vs
   `add_from_skos_json_to_global_cache` / `add_collection_from_json`). `describe` sends
   small lists' labels to the build. Fixture: a `reference` node; concept tests kept
   as the legacy path.
3. `Tiles` → Alizarin trees, so evaluation is datatype-correct and keeps parent/child tiles.
4. Labels and hierarchy via `RustRdmCache` / `RustRdmConcept`; delete the SKOS
   alt-label parser once `alt_labels` is confirmed.
5. Names via the tree (typed names) or recomputed descriptors; warn when a model's
   records are named by UUID.
6. Permitted nodegroups wired to the pipeline's private flag.
7. Domain values.
8. Spike: one small SQL schema mapped into an Alizarin graph, end to end, and the
   query-location decision recorded.

## Depends

None for steps 1–4. [[ceist-group-grounding]] steps 2 (`OnTile`) and 4 (typed
names) build on steps 3 and 5 here. Do this task first.

## Test

- The existing `tests/test_arches.py` passes unchanged after step 1 (same plans, same compiled queries).
- A `reference` node: "listed buildings" grounds to the controlled-list item and
  compiles for Rós Madair and Arches Search. A narrower list item counts.
- Fixture with a child nodegroup: a condition split across a parent and child tile matches;
  one split across two sibling tiles doesn't.
- A pruned nodegroup is absent from the description, the index, and grounding.
- A resource with no descriptors still gets its name, from the name node.
