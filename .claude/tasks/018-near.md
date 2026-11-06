---
id: 018
slug: near
status: approved
branch: crew/018-near
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
---

# "near" and "within N km" of a named record

## Goal
- "which monuments are near Armagh?" and "which raths are within 5 km of Navan Fort?" answer using the records' geometry.
- "near" has a stated default distance (say 5 km), shown in the narration: "within 5 km of Site '…'". A number with km or miles overrides it.
- The named record's geometry comes from its tiles. If it has none, refuse: "'Armagh' has no location to measure from".

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned".

## Background
- Rós Madair indexes geometry (grid and FlatGeobuf in the snapshot). Look for a spatial predicate in `crates/ros-madair-query` (`/home/stuart/.cache/tmp-ask/ros-madair`). If there is one, compile to it.
- If there isn't, do **not** add one in Rós Madair here. Instead, filter by distance in Ceist over the candidates' geometry, with a `ponytail:` comment naming the cost ceiling, and note the Rós Madair predicate as follow-up work.
- Check whether "Armagh" alone matches County Armagh or the city. Never guess: ask "did you mean" when two records fit.

## Definition of done
- [ ] Unit tests: near with the default, within N km, and a named record with no geometry refusing.
- [ ] In the question bank, the "near Armagh" question answers or gives a clear "did you mean". Check one distance by hand, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
