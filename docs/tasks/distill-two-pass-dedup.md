# Task: distill two-pass dedup

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Distill (and ingest) become two-pass: extract candidates → `memory_search` the graph for
near-matches → update existing nodes instead of creating twins. The duplicate guard
(server-side) stays as the backstop; this pass makes the skills *aim* at the right node
before the guard has to catch them.

## Depends

[[memory-search-tool]].

## Notes

Skill-file change only (distill/ingest SKILL.md step ordering) — no server code.
