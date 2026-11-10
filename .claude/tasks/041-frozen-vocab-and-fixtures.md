---
id: 041
slug: frozen-vocab-and-fixtures
status: draft
branch: crew/041-frozen-vocab-and-fixtures
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/
  - packages/ceist-js/fixtures/
---

> Rewritten for schema assembly (2026-11-09). Draft until Stu has reviewed the code after 053 and 055; he approves it then.

# Python writes the vocabulary and the golden fixtures as JSON; TypeScript will only read them

## Goal
Step 2 of the TypeScript port. PORT-AUDIT.md §1 found the biggest cut: the TypeScript runtime does not port the Arches vocabulary loader (`arches.py`, `crm.py`, `bundle.py`, `slicing.py`). Python builds the vocabulary at build time and writes it out. TypeScript reads it.

1. **`ceist vocab freeze <graph dirs…> --base <dir> --client <dir> -o vocab.json`.** It writes everything the question-time runtime reads from `ArchesVocabulary` and the memory graph's `MemoryVocabulary`:
   - models, type words, fields, relations with their forms, domains and ranges;
   - values, groups, date fields and forms, place and geometry fields, hint words;
   - the flags `free_text` and `any_of`;
   - the record names index, or a pointer to the file it already lives in, whichever the runtime needs.

   The format is plain JSON with a `format: "ceist.vocab/1"` field and a JSON Schema beside it. Find every attribute the runtime reads with grep; don't guess the list. Record it in Worker notes.
2. **A loader round trip in Python:** `FrozenVocabulary.from_json` gives the same groundings as the live `ArchesVocabulary`. Prove it by running 040's golden dump through the frozen vocabulary; it must be byte for byte identical.
3. **The conformance fixtures** for the TypeScript tasks, in `packages/ceist-js/fixtures/`:
   - the frozen vocabulary for the demo, HER and the memory-graph test graph;
   - the golden groundings and `pieces()`, plus each question's "did you mean" readings, plan, narration, read-back and compiled Rós Madair query (and the SPARQL plan input, for the memory graph).

   Add one script that regenerates all of them.

## Background
- 040, 051, 053 and 055 must be merged first. The golden dump (`bench/golden/`, assembly as default) is the source of truth; regenerate it only if a later merge changed it, and say so.
- The fixtures are produced in **assembly mode only**: TypeScript ports only assembly.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **Descriptive names** (Stu, 2026-11-10): no single-letter or cryptic variables (`s`, `g`, `c`, `d`). Name things for what they are (`scan`, `grounding`, `candidate`), so the code explains itself. The Python uses short names; the TypeScript must not copy them.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] `vocab freeze` is tested. The frozen-vocabulary golden is byte for byte identical to 040's.
- [ ] The fixtures and the regenerate script are committed. Give the counts per set in Worker notes.
- [ ] HER plans are 125/125, the demo bank exits 0, and the test suites pass.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-041`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
