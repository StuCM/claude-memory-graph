---
id: 016
slug: record-attribute-questions
status: approved
branch: crew/016-record-attribute-questions
model: opus
env: laptop
work: tier1-fixes
depends: [014]
files:
  - packages/ceist/
---

# Answer a question about one named record's field

## Goal
"what period is Navan Fort?" and "what type of monument is Navan Fort?" answer with that record's values: "Navan Fort, Navan: cultural period Iron Age, Prehistoric…".
- The plan is a new shape: one named record plus one or more fields.
- It narrates as "Show the cultural period of Monument 'Navan Fort, Navan'".
- It reads back exactly. Its values come from the record's own tiles (`reader.resource_tiles(id)`, as `linked_from` already reads them).

A field the record leaves empty says so ("no cultural period recorded"). A field word that matches several fields asks "did you mean".

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned". 014 makes these refuse; this makes them answer.

## Background
- `plan.py` (Plan and Interpretation), `narrate.py`, `readback.py` and `rosmadair.py` (`linked_from` reads tiles).
- **Concept values come back as ids.** Label them through the vocabulary's value labels. A resource link value shows the linked record's name.
- **Demo app:** give the `ask.py` patch for the orchestrator. The response needs a field/value list instead of `results`.

## Definition of done
- [ ] Unit tests: the field question answers, an empty field says so, an ambiguous field word gives "did you mean".
- [ ] In the question bank, the two Navan Fort questions answer. Check them by hand against the record in `monument.json`. Set their `expect` to `answer` with a note, and `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
