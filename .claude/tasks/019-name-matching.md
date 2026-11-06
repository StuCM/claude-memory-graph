---
id: 019
slug: name-matching
status: approved
branch: crew/019-name-matching
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
---

# Match part of a record's name

## Goal
- "show all monuments whose name starts with Cat", "which monuments have fort in the name?" and "which monuments are called Lismahon?" answer by matching record names. Names are already held locally: `vocab.names`, 18,820 in the demo.
- It narrates as "Find Monuments whose name starts with 'Cat'", and combines with other conditions: Rós Madair resolves the rest, then the name filter intersects.
- Case-insensitive, matching words or prefixes.

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned". Proposed on 2026-11-05 as the name half of text matching. Text inside descriptions stays out of scope.

## Background
- `ground.py` has no text condition today. The `Contains` and `Mention` plan nodes exist for the memory graph's free text, behind `free_text` (010). **Don't re-open free text for Arches vocabularies.** Add a name-only condition that is explicit in the grammar ("name starts with", "in the name", "called").
- The quoted word is the only free text allowed, and only in that slot.

## Definition of done
- [ ] Unit tests: starts with, contains, called, combined with a county, and a bare unknown word still refusing.
- [ ] In the question bank, the Cat question answers. Check the count by hand against `vocab.names`, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
