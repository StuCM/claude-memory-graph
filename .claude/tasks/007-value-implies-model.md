---
id: 007
slug: value-implies-model
status: approved
branch: crew/007-value-implies-model
model: opus
env: laptop
files:
  - packages/ceist/
---

# Word order doesn't matter: longer value phrases win, and a value implies its model

## Goal
These questions get the same answer however they're worded. Today the second form of each is refused:

| Works today | Refused today | Expected |
| --- | --- | --- |
| which monuments in County Antrim are bronze age cairns? (43) | which bronze age cairns are in County Antrim? | 43 |
| which bronze age monuments are in County Antrim? | which cairns are bronze age? | the Bronze Age + Cairn construction-phase count |
| how many monuments are raths? (2,902) | how many raths are there? | 2,902 |

## Why now
Stu, 2026-11-05: "Are we able to run the tasks that fix the issue where the sentence in a different order is refused". These are the nodegroup questions he wants to show on Friday.

## Background
Grounding traces from the demo (`/home/stuart/git/personal/starches-demo/ask`, foundation Ceist):

1. **A shorter relation phrase beats a longer value phrase.** In "which bronze age cairns are in County Antrim?", `'age' → relation cultural_period` grounds first and takes "age" out of "bronze age". The relation then builds an implicit Object variable (another model has `cultural_period`), and "bronze" is left unplaced → refused.
   - With "monuments" in the question, 'age' is set aside ("no relation it names joins Monument and Site"), then "bronze age" grounds as the construction-phases combo, and the question works.
   - The fix belongs with 009's rule (`_record_spans` / `_phrase_spans` in `ground.py`): a value or combo phrase (group combo, controlled value label) that strictly contains a shorter relation phrase wins over it. Equal lengths keep today's order. A relation phrase that sits *outside* the longer phrase is untouched.
2. **A value alone doesn't imply its model** (the original 007 stub). "how many raths are there?" → `'raths' → value of functional_type / monument_type`, then "no queryable subject".
   - When no type word is named and every grounded value belongs to nodes of exactly one model, take that model as the subject ("Count Monuments whose monument type is Rath").
   - When the values belong to more than one model, refuse with "did you mean" listing each model. Never pick one silently.
   - Values already grounded together with a relation (as in "which raths are in County Down?", which works today through the relation's implicit variable) must not change.

## Definition of done
- [ ] Unit tests for both items, each failing on the base code:
  - a longer combo or value phrase beats a contained relation phrase;
  - a relation outside the span still grounds;
  - a value implies its single model;
  - a value shared by two models gives "did you mean", not an answer.
- [ ] On the demo, each refused question in the table answers with the same narration and count as its working form.
  - Check the counts against the record files: `prebuild/business_data/monument.json`, where a construction-phases tile holds both values.
  - Also run "how many medieval raths are there?" and "which raths are not medieval?", and report what they say.
- [ ] Every question in the demo README gives the same answer as before (list any change with a reason). Run them through the demo with `PYTHONPATH=<worktree>/packages/ceist/src`.
- [ ] HER plans (`bench/her_plans.py`): every diff justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- [ ] Re-score the Opus run from cache only (`/home/stuart/.cache/tmp-010/rescore.sh` pattern, `--llm-cmd false`, outputs under `/home/stuart/.cache/tmp-007/`). Report demo right/wrong before and after; the wrong count must stay 0.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-007`, never `git add -A` or `git stash`, no servers left running.

## Worker notes

## Graph writes proposed

## Review rounds
