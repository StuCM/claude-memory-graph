---
id: 007
slug: value-implies-model
status: done
branch: crew/007-value-implies-model
model: opus
env: laptop
files:
  - packages/ceist/
gate: pass
gateSha: 8a3fbca0bcb80ad355759952b89b2613ba456196
gateAt: 2026-11-05T21:25:10.914Z
rounds: 1
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

**Changes**
- `packages/ceist/src/ceist/ground.py`: the group-combo and value phrase tables are built before the relation pass; each place a group/value phrase occurs (outside the question's shape words) is passed to the relation pass alongside record names, so a relation phrase strictly inside a longer one gives way (equal lengths unchanged; an occurrence outside still binds). New `_imply_model`: with no type, anchor or relation, values/groups whose owners are all one model add that model's variable; two or more models add a "did you mean" per model.
- `packages/ceist/src/ceist/plan.py`: "no queryable subject" now carries `_did_you_mean(g)`.
- `packages/ceist/tests/test_ceist.py`: `Ages` toy + 4 tests (5 cases). All 5 fail on the base code.

**Where the spec fell short (decided conservatively, say if wrong):** the HER plans showed "What's the brooch made of?" going from refused to `Find Artefacts whose artefact type is Brooch.` That answers a question nobody asked (it drops "made of"). So the model is implied only when the first value sits where a question names its subject (the existing `_SUBJECT_LEAD`: "which …", "how many …", "list …"). With that guard both HER pins are 125/125, no re-pin. A value with no owners (any type) implies nothing.

**Goal table (demo, `PYTHONPATH=<worktree>/packages/ceist/src`)**

| Question | Before | After |
| --- | --- | --- |
| which bronze age cairns are in County Antrim? | refused ('bronze') | Find Monuments whose named location is Site 'County Antrim' and with one construction phases entry (whose cultural period is Bronze Age and whose monument type is Cairn). → 43 (same narration and count as "which monuments in County Antrim are bronze age cairns?") |
| which cairns are bronze age? | refused ('bronze') | Find Monuments whose cultural period is Bronze Age and whose monument type is Cairn. → 73 |
| how many raths are there? | no queryable subject | Count Monuments whose monument type is Rath. → 2,902 (same as "how many monuments are raths?") |
| how many medieval raths are there? | no queryable subject | Count Monuments with one construction phases entry (whose cultural period is Medieval and whose monument type is Rath). → 10 |
| which raths are not medieval? | no queryable subject | Find Monuments whose cultural period is not Medieval and whose monument type is Rath. → 2,892 |

Record check against `prebuild/business_data/monument.json` (construction-phase tiles, SKOS labels from smr.xml): Bronze Age + Cairn on one tile 73, of them ANT 43; Rath 2,902; Rath + Medieval 10; Rath without Medieval 2,892. All match. "which cairns are bronze age?" narrates as two conditions rather than one tile, because the cairn word comes before the group phrase and a group only takes the values after it; with one construction-phase tile per monument the count is the same.

**Demo README:** all 41 questions run before/after (the README rows, county list, extras, known gaps). 36 unchanged. Changed: the five rows above. Only README-listed change: "how many raths are there? (also "how many medieval raths are there?")" was a **refused** row and now answers (2,902 / 10): intended, and the README row and the note "Avoid 'cairns in County Antrim' with no type word" need updating in the demo repo (outside this task's files). "which raths are in County Down?" unchanged (687).

**HER plans:** 2.0 (9f6a113, local clone) and 1.1 (tmp-010/her11): base 125/125, after 125/125 with the guard. No re-pin.

**memory_ask:** `tests/test_planner.py` 33/33. Its status values have no owners, so `_imply_model` never fires for it, and its one-word status values can't strictly contain a relation phrase. The only reachable change: a "no queryable subject" refusal now appends any matcher "did you mean".

**Opus rescore (cache only, `--llm-cmd false`, `/home/stuart/.cache/tmp-007/full-seed-opus-{base,after}`):** LLM calls 0 (162 from cache) both. Gate 61/82 right, 4 dangerous both. demo_compare identical before/after: 20/26 same, so 20 right / 0 wrong before and after (as task 010). Planner level: dangerous 6 → 5; "How many listed buildings are there?" was `Count Figures whose monument area or artefact is any Monument whose designation … is Listed` and now refuses ("couldn't place 'buildings', 'listed' … did you mean …"): 'buildings' (a relation phrase) gives way to the longer combo "listed buildings".

Gate: passed on 8a3fbca (root 530 passed, Ceist 211 passed).

## Graph writes proposed
- Pattern (Ceist): a value alone implies its model only in subject position ("which/how many/list …"); "what's the X made of?" asks an attribute of one record, and implying X's model there widens the answer. Caught only by the HER plan pins, not by unit tests.
- Decision (Ceist): a group or value phrase strictly containing a relation phrase wins over it (same rule as record names, 009); equal lengths keep relation-first order.

## Review rounds
- Round 1: PASS. Exact-narration tests; subject-position guard justified by the HER "brooch made of" regression; minor (not a finding): "which cairns are bronze age?" narrates as two conditions, same count.
