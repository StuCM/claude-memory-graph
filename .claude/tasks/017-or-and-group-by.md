---
id: 017
slug: or-and-group-by
status: approved
branch: crew/017-or-and-group-by
model: opus
env: laptop
work: tier1-fixes
depends: [014]
files:
  - packages/ceist/
---

# "or" between values or places, and counts grouped by a field

## Goal
- **"or":** "which raths or cairns are in County Down?" and "how many monuments are in County Antrim or County Down?" (expected 9,224 = 5,638 + 3,586) answer with an **or** condition.
  - It narrates as "whose monument type is Rath or Cairn".
  - Rós Madair's IR has `any`. Check `crates/ros-madair-query` in `/home/stuart/.cache/tmp-ask/ros-madair`; if it lacks one, compile to a union of two resolves.
- **Group-by:** "which county has the most raths?" and "list scheduled monuments by county" answer with a count per value of a link or list field, sorted.
  - Narrated as "Count Monuments whose monument type is Rath, by named location".
  - "most" or "fewest" takes the top or bottom one, and says so.
  - If Rós Madair can't group, count per value with one resolve per value. Cap the values at 50, and refuse above the cap.

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned".

## Background
- 014 makes "or" refuse first; replace that refusal with real support where the grammar is clear: two values of the same field, or two records for the same link.
- An "or" across different fields ("raths or scheduled") refuses.
- Read-back must stay exact.

## Definition of done
- [ ] Unit tests for both, plus a refusal for a mixed-field "or".
- [ ] In the question bank, the or and group-by questions answer. Check the raths-by-county top value by hand, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
