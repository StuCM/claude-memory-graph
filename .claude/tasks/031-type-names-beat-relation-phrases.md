---
id: 031
slug: type-names-beat-relation-phrases
status: approved
branch: crew/031-type-names-beat-relation-phrases
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
---

# A multi-word type name wins over a relation phrase inside it

## Goal
The ontology relation phrase "sources" (P67i E73) grounds inside the type names "archive sources" and "bibliographic sources", because relations are matched before multi-word type nouns. This is the biggest remaining miss on 026's bench after 029 (Catalina 18, HER 4).

Apply the same longest-match rule that 009 (record names) and 007 (value and group phrases) use: a type word or type phrase that strictly contains a relation phrase wins over it. Equal lengths keep today's order, and a relation phrase outside the type name still binds.

## Why now
Found by task 029's worker, 2026-11-08 (see `029-ontology-miss-fixes.md`, Worker notes: "Biggest remaining miss").

## Background
- `ground.py`: `_record_spans` / `_phrase_spans` (009), and 007's group/value spans passed to the relation pass. Type words are resolved separately. Find where they're matched, and pass their spans into the relation pass the same way.
- **The memory graph runs on Ceist:** check `tests/test_planner.py`.
- No `claude -p`, live LLM or vocab pipeline runs.

## Definition of done
- [ ] Unit tests, each failing on the base code: a two-word type name containing a relation phrase wins; a relation phrase outside it still binds.
- [ ] 026's bench before and after (ontology mode). Wrong readings and wrongs must not rise.
- [ ] The demo question bank exits 0. HER plans: every diff is justified and re-pinned deliberately.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-031`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
