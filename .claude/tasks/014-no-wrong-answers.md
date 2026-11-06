---
id: 014
slug: no-wrong-answers
status: done
branch: crew/014-no-wrong-answers
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
gate: pass
gateSha: b2d029708d49b30ea34227e8ea58367f8513b9f1
gateAt: 2026-11-06T16:23:35.921Z
rounds: 1
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
- `packages/ceist/src/ceist/ground.py`: an uncovered "or" (outside a record name or a phrase) refuses with "'or' isn't supported yet; ask one at a time". A shared link word that is set aside now refuses when the anchor has the type that was asked for (Belfast). A new `_check_anchors`, run after wiring, refuses in two cases. First, an anchor its link can't point at ("what is in Navan Fort?", which used to give Monuments whose named location is Monument 'Navan Fort'). Second, an anchor at the end of a link whose target is unknown when only that link implied the subject ("what period is Navan Fort?"). `Node.implicit` marks those subjects.
- `packages/ceist/tests/test_ceist.py`: one test per shape, plus guards: "Lock or Weir" as a name, and "in Leeds Dock" still plans. All three fail on base.
- Bank, before → after: answer/right 60 → 60, refuse/right 6 → 7, refuse/wrong 1 → 0, answer-later/wrong 2 → 0, answer-later/refused-should-answer 17 → 19, answer/refused 1 → 1. Exit 0. The "County Antrim or County Down" question now refuses on "or" instead of on "down".
- HER plans (2.0 and 1.1, at the CI-pinned refs from a local clone): there are two diffs, and I re-pinned both. "Is it a PDF or a JPEG?" and "Is it a named location or an address?" are now refused. Each used to answer one side of the "or" and drop the other.
- memory_ask: `tests/test_planner.py` passes unchanged (33). Memory questions with a bare "or" now refuse. So does a set-aside link word joining two records of the same type, and an anchor at a link end whose declared range excludes its type.
- Sweep: still open is a named subject plus an unknown-target link plus a record ("what objects have period Navan Fort?" plans Objects whose cultural period is Monument 'Navan Fort'). That needs 016 or a follow-up, which could refuse when the anchor's model is one the link's CRM class clashes with.
- The base moved during the task (011 and 015 merged; the demo imports `ceist.bundle.layered`), so I rebased onto ceist-foundation and refreshed `.venv-ceist` with the a33 Rós Madair wheel that prepare now names.

## Graph writes proposed
- Pattern: Arches links whose target model isn't loaded have empty `ends` targets, so `Relation.joins` accepts any anchor. A record of any type then binds as the value. Check whether targets are known (ground._targets) before trusting joins.

## Review rounds
- Round 1: PASS. Notes: fill in Worker notes (done). The named-subject, unknown-target gap is acceptable under the spec and is flagged for 016.
