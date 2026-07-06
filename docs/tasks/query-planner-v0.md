# Task: query planner v0 (`ask` CLI)

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: L

## Goal

`claude-memory-graph ask "what decisions affect quartz?"` — ground the question's words
(model nouns → type constraints, entity names → anchors, relation verb forms → reified
CrossLink patterns, wh-word → projection), compose SPARQL, execute; fall back to
neighbourhood recall when grounding coverage is low. Design:
[QUERY-PLANNING.md](../QUERY-PLANNING.md).

## Scope (v0 grammar)

1–2 typed variables · ≤2 edges · 1 entity anchor · recency/status modifiers · CONTAINS
for one ungrounded noun. No parser dependency — lexicon-first; leftovers handled by rules.

## Depends

[[memory-search-tool]] (entity grounding) · [[verb-forms-ontology]] (verb lexicon).
CLI-only first; hook/tool wiring is a later task.

## Test

Golden tests: fixture graph + question table → expected **result rows** (not SPARQL text).
Refusal suite: ungroundable questions must fall back, never guess.
