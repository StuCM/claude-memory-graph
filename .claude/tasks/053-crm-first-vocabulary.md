---
id: 053
slug: crm-first-vocabulary
status: approved
branch: crew/053-crm-first-vocabulary
model: opus
env: laptop
work: vocab-training
files:
  - vocabularies/
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/demo/vocab/
  - packages/ceist/bench/golden/
  - packages/ceist/VOCAB-TRAINING.md
  - packages/ceist/STATUS.md
---

# CRM-first vocabulary: move graph-layer phrasings to the ontology layer wherever CIDOC-CRM can carry them

## Goal
Stu, 2026-11-09: "I really feel like we should be leaning into cidoc more than we are. We keep agreeing it is a good route and then never implementing it… shouldn't we be pulling out of the graph vocab layer and moving this to the ontology layer."

Make the ontology layer the **default home** for a phrasing, and the graph and client layers the **exceptions**.

1. **Promote** every phrasing that `packages/ceist/CRM-FIRST-CHECK.md` classes as *promotable* or *promotable longer path*:
   - move it from `vocabularies/base/<graph>/` (or the demo client layer) into `vocabularies/ontology/cidoc-crm/phrases.json`, on its CRM path;
   - send it through the **existing gate** (`ceist vocab ontology --accept`, or 039's route): each one alone on the fresh-graph bench, then all together on the bench, the demo bank and HER plans;
   - remove it from the graph or client layer **only once its ontology form is accepted**;
   - a phrasing the gate rejects stays where it is, with the gate's reason recorded.
2. **The exceptions keep a reason.** Every phrasing left in a graph or client layer carries a one-line reason: ambiguous path, non-CRM property, site-specific term, or gate-rejected. Extend 039's coverage report (`ceist vocab coverage`) to show, per layer, how much lives where and why.
3. **Make CRM-first the playbook default.** Update `VOCAB-TRAINING.md` so new vocabulary (rules, LLM fill, review) is proposed on the CRM path first and lands in a graph layer only for the listed reasons. Update STATUS.md §2.
4. **Measure** (tables in Worker notes, before and after):
   - the demo bank (exit 0, no new wrong answers);
   - HER plans (every diff justified);
   - the fresh-graph bench per set, **especially Catalina and lingo**, which have no vocabulary of their own and are where CRM-first should pay off;
   - the generated train and hold-out sets;
   - the coverage per layer;
   - the golden dump (regenerated, with changes explained).

   Wrong readings and wrong answers must not rise anywhere.

## Background
- **Read first:**
  - `packages/ceist/CRM-FIRST-CHECK.md`, which is the analysis this implements: its method and its classification;
  - `CRM-LID-CHECK.md`;
  - the Worker notes of 023, 025, 033, 035 and 039;
  - the graph Patterns "Ceist link phrases have no direction" and "ontology gate proves grounding, not usage".
- Assembly is the default after 051. Run every measurement in the default mode, and note anything that differs in strict mode.
- **No `claude -p` or live LLM runs.**
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`).
- 051 must be merged first; both tasks touch `packages/ceist/src/ceist/`.

## Definition of done
- [ ] The promotions are accepted through the gate. Each phrasing left in a graph or client layer has a reason, and the coverage report shows it.
- [ ] The measurements are in Worker notes; wrong readings and wrong answers have not risen.
- [ ] VOCAB-TRAINING.md and STATUS.md are updated.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-053`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
