---
id: 055
slug: pre-port-cleanup
status: approved
branch: crew/055-pre-port-cleanup
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
  - packages/ceist/bench/her/plans-2.0.json
  - packages/ceist/bench/her/plans-1.1.json
  - packages/ceist/pyproject.toml
  - packages/ceist/README.md
  - packages/ceist/PORT-AUDIT.md
  - uv.lock
---

# Pre-port clean-up: 040's leftovers, drop simplemma for a small irregulars table, and the small audit items

## Goal
Make the Python runtime the exact shape the TypeScript port copies, so nothing is ported only to be removed. This runs after 053 and before Stu's code review and 041.

1. **040's leftovers** (040's Worker notes; they were outside its `files:`):
   - matching's unused `context` parameter (evaluate.py:117 passes it positionally; fix that call);
   - `PLANNED_CHOOSERS` in config.py: the audit says deleting it changes behaviour, so check what and decide;
   - narrate's plural through text: add `text.plural()` that keeps case, so narrate stops carrying its own copy;
   - the overlap check in `dates.py`: use the shared helper;
   - stale docs: README.md:67,115-116 (`to_query`) and pipeline.py:633 (`ground._fit_relations`).
2. **Drop `simplemma`** (PORT-AUDIT #8). It is a Python-only optional dependency with no TypeScript equivalent, so the two runtimes would disagree wherever it is installed.
   - Replace what it supplies (irregular roots such as built → build, made → make, found → find) with a **small irregulars table** in `text.py`, next to the plural irregulars 039 added in `vocab_rules.py`. Reuse one table if it fits.
   - Remove the `roots` extra from pyproject. `roots = true` keeps meaning "light root plus irregulars".
3. **Small audit items:**
   - #21: dedupe the repeated suggestion and `unplaced` blocks in `_match_leftovers` (safe);
   - #25: `Grounding.anchor` becomes a property of `anchors[0]`, and `about` moves to the scan state (safe; planner.py reads `g.anchor`);
   - #26: drop `Node.var` from the notes (the note text changes).
4. **Strict mode:** leave it in place (047 deletes it after TypeScript parity), but make sure nothing outside `plan.py` and the tests reaches strict-only code. List what is strict-only in Worker notes, so 042 and 043 know what not to port.

## Measure
- The golden dump: regenerate it and explain every change by item. Items 1 and 3 (#21, #25) must change nothing.
- HER plans: every diff from dropping simplemma is justified and re-pinned deliberately.
- The demo bank: exit 0, tally unchanged.
- The reorder set and the fresh-graph bench: 0 wrong.
- Line count of `packages/ceist/src/ceist/` before and after.

## Background
- **Read first:** PORT-AUDIT.md §1, and the Worker notes of 040, 051 and 053.
- **053 must be merged first** (both touch `packages/ceist/src/ceist/`).
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`). No `claude -p` or live LLM runs.

## Definition of done
- [ ] Every item is done or has a recorded reason not to; PORT-AUDIT.md marks each one done.
- [ ] simplemma is gone from the code and pyproject, and the irregulars table is tested.
- [ ] The measurements are in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-055`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
