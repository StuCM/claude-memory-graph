---
id: 056
slug: gate-bisect-and-speed
status: approved
branch: crew/056-gate-bisect-and-speed
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/bench/ontology/
  - packages/ceist/src/ceist/ontology_vocab.py
  - packages/ceist/src/ceist/crm_first.py
  - packages/ceist/tests/
  - packages/ceist/VOCAB-TRAINING.md
---

# The vocabulary gate finds the culprit instead of rejecting everything, and runs faster

## Goal
053's run exposed two problems with `bench/ontology/gate.py` (053's Worker notes):

1. **One bad candidate rejects everything.** In the demo-bank stage, "what is related to Navan Fort?" turned from a refusal into a wrong answer. `holding()` only matches phrases written out in full in the question, so it found none and rejected all 154 passing candidates. The 053 worker bisected by hand and found two culprits (`property E18 P140i E13 P2`, `property E74 P141i E13 P2`). That script, `regate.py`, and its `verdict.json` are in `/home/stuart/.cache/tmp-056/`; read both. Build that bisection into the gate:
   - whenever a "together" stage (bench, demo bank or HER plans) gets worse and `holding()` can't name the culprit, bisect the passing set and reject only the culprits;
   - record each one's reason.

   Re-running the gate on 053's candidates must reproduce 053's accepted set (152 paths). Prove it in Worker notes.
2. **Speed.** 053's gate took several hours on one core: 223 candidates, each run alone over every bench set, re-asking every question that shares a word with it.
   - Measure where the time goes first.
   - Then take the cheap wins: reuse the "before" scores and the built vocabulary across candidates rather than rebuilding them; and run the bench sets in parallel, **at most 2 processes** (Stu's machine-load limit).
   - Report the before and after time on 053's candidate set.
3. **Per-phrase rejection, if cheap.** The gate judges a whole path at once, so one bad phrase rejects every phrase on it (27 paths in 053). If a path is rejected as "worse", try its phrases separately, and keep the ones that don't make anything worse. Do this only if it stays within the time budget; otherwise list it as a follow-up.

## Background
- **Read first:** 053's Worker notes, `gate.py`, `crm_first.py`, and the `gate`/`accept` route in `ontology_vocab.py`.
- **No `claude -p` or live LLM runs.**
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`).

## Definition of done
- [ ] The bisection is tested: one culprit among several candidates, and a stage that `holding()` can't attribute. 053's accepted set is reproduced.
- [ ] The time before and after on 053's candidates is in Worker notes, with at most 2 processes.
- [ ] VOCAB-TRAINING.md describes what the gate now does when a combined stage gets worse.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-056`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
