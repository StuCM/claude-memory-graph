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

> Held (Stu, 2026-11-09) until the schema-assembly prototype (049) is measured: if it wins, this spec is rewritten for the new design.

# TypeScript ground: text, dates, exact matching and the ground passes, equal to Python on every golden grounding

## Goal
Step 3 of the port. Create `packages/ceist-js/`: an npm package, plain TypeScript, ES modules, vitest, and no runtime dependencies unless one is unavoidable (say why). Port, in this order:
- text: terms, plurals, rooting;
- dates;
- matching, with the exact layer only (the vectors layer is not ported; STATUS.md §4);
- the frozen vocabulary reader;
- `ground`, in 040's shape (the `Scan` state and the same passes, in the same order, with the same file split).

**The free-text branch is ported too.** It is switched on by the vocabulary's `free_text` flag, exactly as in Python. Stu decided on 2026-11-08 that one TypeScript runtime serves Starches, the memory graph and Arches Search, and all three use it.

**Conformance:** a vitest suite loads 041's fixtures and checks that `ground` equals Python's grounding on every question:
- nodes, edges, values, dates, groups;
- the notes, suggestions and unplaced words;
- the coverage and `refuse`.

## Background
- 041 must be merged first. Use the fixtures as they are; if one looks wrong, say so in Worker notes and don't edit it.
- `packages/ceist-web/spike` is the earlier proof that the stack runs in a browser. Read it for the WASM and Rós Madair loading, not as code to keep.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Every golden grounding is equal, in every set. Give the counts in Worker notes. Any mismatch fails the task: no allowlist.
- [ ] Unit tests for text, dates and matching, ported from the Python tests where they exist.
- [ ] The package line count against the Python modules it replaces, in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-042`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
