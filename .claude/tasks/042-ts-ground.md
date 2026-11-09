---
id: 042
slug: ts-ground
status: draft
branch: crew/042-ts-ground
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
---

> Rewritten for schema assembly (2026-11-09). Draft until Stu has reviewed the code after 053 and 055; he approves it then.

# TypeScript extraction: text, dates, exact matching and ground's passes up to pieces(), equal to Python on every fixture

## Goal
Step 3 of the port. Create `packages/ceist-js/`: an npm package, plain TypeScript, ES modules, vitest, and no runtime dependencies unless one is unavoidable (say why). Port, in order:
- text: terms, plurals, rooting, as 055 left it (no simplemma);
- dates;
- matching, with the exact layer only (vectors are not ported; STATUS.md §4);
- the frozen vocabulary reader (041);
- **`ground`'s extraction passes up to `pieces()`**, in 040's shape: the `Scan` state and the same passes, in the same order, with the same file split. Include the free-text branch, which turns on with the vocabulary's `free_text` flag (Stu: one TypeScript runtime for Starches, the memory graph and Arches Search).

The wiring passes that only strict mode uses are **not** ported. If a pass is shared, port it; if it is strict-only, list it in Worker notes as left behind.

**Conformance:** a vitest suite loads 041's fixtures and checks that `pieces()` equals Python's on every question: the pieces, the notes, the suggestions, the unplaced words and the coverage.

## Background
- 041 must be merged first. Use the fixtures as they are; if one looks wrong, say so in Worker notes and don't edit it.
- `packages/ceist-web/spike` is the earlier proof that the stack runs in a browser. Read it for loading, not as code to keep.
- **Read first:** `packages/ceist/STATUS.md` (§5a, §5b), `packages/ceist/PORT-AUDIT.md`, and the Worker notes of 040, 049, 050, 051 and the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **Port only schema assembly**, the default since 051. Strict mode's wiring is **not ported**; it stays in Python only for comparison until 047 deletes it.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by 041's fixtures. A behaviour change belongs in its own later task.
- **Credit:** a module that implements a borrowed method (PRECISE in assembly) names the source in one docstring line pointing to `packages/ceist/PRIOR-ART.md`.
- **Run `ponytail-review`** on your diff before the review round, and list its findings and what you did about each in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Every fixture's pieces are equal, in every set; counts in Worker notes. Any mismatch fails the task: no allowlist.
- [ ] Unit tests for text, dates and matching, ported from the Python tests where they exist.
- [ ] The package line count against the Python it replaces, in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-042`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
