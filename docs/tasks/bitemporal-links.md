# Task: bi-temporal links + contradiction closure

Status: **done (ontology 0.6.0)** · Owner: Stuart · Created: 2026-07-04 · Size: M

## Goal

Links carry two clocks (design: [DISTILL-CREATION.md §8](../DISTILL-CREATION.md)):
`linkValidFrom`/`linkValidUntil` (world) and `linkInvalidatedAt` + `invalidationKind`
(`worldChange` | `correction`) (belief). Write rule: a new link contradicting a
single-valued relation **closes** the old edge instead of deleting/duplicating. Read
rule: recall and `_neighbours` filter to open edges by default.

## As built

- `create_link` stamps `linkValidFrom` (caller-supplied metadata backdates it) and
  runs contradiction closure for relations carrying `mem:singleValued true` in the
  schema — `employedBy` and `assignedTo` in base.ttl 0.6.0; LLM-added relations
  default to multi-valued. Returns the closed-edge count; the tool message surfaces it.
- `memory_unlink` **closes by default**: `mode` = `worldChange` (default; bounds the
  world clock) | `correction` (belief clock only — the fact never was true, so
  point-in-time queries exclude it) | `remove` (hard delete, for noise).
- Read paths filter to open edges (no `linkValidUntil`, no `linkInvalidatedAt`):
  `_neighbours` (recall, ambient injection's link lines) and the gate's
  `_project_neighbourhood` (proximity prior). History stays queryable via SPARQL.
- The base-ontology loader now keys on `owl:versionInfo` — bump the version in
  base.ttl and every existing store upgrades on next open, no loader edits.
- Scalar properties stay current-value (deliberate — see design doc); Decisions keep
  the `supersedes` chain.

## Test

tests/test_bitemporal.py (15 tests): stamping/backdating; second `employedBy` closes
the first (`worldChange`) while same-target and multi-valued (`worksOn`) don't; recall
returns only the open edge; closed edges remain SPARQL-queryable; unlink close /
correction / remove semantics; schema declares the single-valued set.
