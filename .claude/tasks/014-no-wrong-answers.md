---
id: 014
slug: no-wrong-answers
status: approved
branch: crew/014-no-wrong-answers
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
---

# Refuse the three question shapes that give wrong answers today

## Goal
The question bank's three wrong answers become refusals with a clear message:
1. **"which raths or cairns are in County Down?"** gives 0 today. "or" between values is read as "and" ("monument type is Cairn and monument type is Rath"). Refuse any "or" Ceist can't represent: "'or' isn't supported yet; ask one at a time". Task 017 adds real "or".
2. **"what period is Navan Fort?"** gives 0 today, with the nonsense plan "Find Objects whose cultural period is Monument 'Navan Fort, Navan'". A question about one named record's attribute must refuse until task 016 answers it, and must never build a plan that uses the record as a value of its own field.
3. **"which monuments are in Belfast?"** gives 1 today: the monument *named* "Belfast, Belfast", as a direct match. When a question has a type word ("monuments") plus a link word ("in"), and the name matches a record of the **subject's own type** rather than a type the link can point at, refuse. Don't answer with that record.

Then sweep for the same shapes: any plan whose value is a record, or whose link target type can't be what the link points at. Report what you find.

## Why now
Stu, 2026-11-06: "I would like to apply all the fixes we mentioned". These break the never-guess rule.

## Background
- `ground.py`: the direct-match path (`meaning.direct`), the "or" token (currently dropped as a stopword?), and the relation fit (`_fit_relations`, 009/010).
- `plan.py`: the plan assembly.
- Narration and read-back must stay exact.

## Definition of done
- [ ] Unit tests for each shape, failing on the base code.
- [ ] In the question bank, those three questions are no longer wrong. Update their entries with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
