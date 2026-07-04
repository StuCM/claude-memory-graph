# Task: bi-temporal links + contradiction closure

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: M

## Goal

Links carry two clocks (design: [DISTILL-CREATION.md §8](../DISTILL-CREATION.md)):
`linkValidFrom`/`linkValidUntil` (world) and `linkInvalidatedAt` + `invalidationKind`
(`worldChange` | `correction`) (belief). Write rule: a new link contradicting a
single-valued relation **closes** the old edge instead of deleting/duplicating. Read
rule: recall and `_neighbours` filter to open edges by default.

## Scope

- `create_link` stamps `linkValidFrom`; closure logic for relations marked
  single-valued in the schema (start with `worksAt`, `employedBy`, `assignedTo`).
- `memory_unlink` gains a "close" semantics option vs hard remove.
- Scalar properties stay current-value (deliberate — see design doc).

## Test

pytest: second `worksAt` closes the first (`worldChange`); recall returns only the open
edge; correction-kind invalidation excluded from "was true then" queries.
