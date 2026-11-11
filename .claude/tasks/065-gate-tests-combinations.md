---
id: 065
slug: gate-tests-combinations
status: approved
branch: crew/065-gate-tests-combinations
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/
  - packages/ceist/bench/ontology/
  - packages/ceist/tests/
  - packages/ceist/VOCAB-TRAINING.md
  - packages/ceist/docs/HOW-GROUND-READS.md
---

# `ceist setup`'s gate tests words in combination, probes names for partial binding, and takes a site's own questions

## Goal
Stu, 2026-11-11: "the pipeline should have been catching these things, why are we having to reroll this". The setup gate (059) generates **one-piece** template questions from the schema ("which buildings are hospitals?") and accepts a phrasing if it adds a right answer and breaks none. So it proves each word grounds **alone**, never that words **combine**. A realistic benchmark (Phil's testbed) kept finding what the pipeline should have:
- "keyholders of the hospitals" refuses (the composition bug, fixed in 064);
- "produced by the flood model" bound 'Flood model v1.0' on a partial name (a wrong answer, fixed in 064).

The memory-graph Pattern "ontology gate proves grounding, not usage" recorded this blind spot. This task closes it, so that a new site's first `ceist setup` reports such problems itself.

1. **Composition templates.** From the schema, generate questions that combine pieces as real questions do, each from a **known plan**, so the gate checks it exactly:
   - type word + link + value ("keyholders of hospitals", "shelters run by organisations in the health sector");
   - type word + link + type word;
   - type word + value + number comparison (060);
   - two links in a chain.

   Use every phrasing family the layers give (type words, value-as-type words, role nouns from 064, link phrasings both ways). Cap the count per site so setup stays in minutes (report the count and time). Add them to the site gate: a candidate is accepted only if it makes no composition worse. Report how many compositions answer, refuse or read wrong, by family.
2. **Name-safety probes.** For every record whose name has more than one word (especially numbers, versions or a generic lead word), probe with its **partial names**: each proper subset of its name terms. A probe must **never bind that record**. A partial bind is reported as a **wrong-answer risk** and **fails the gate** for whatever caused it (a phrase, an alias). Also probe that the whole name binds. This would have caught "the flood model" → 'Flood model v1.0'.
3. **The site's own questions:** `ceist setup --questions <file>`. A site's practice questions (the same JSON shape as the testbed or responder sets, with expected counts if known) join the gate, as "must not get worse", and as "must not read wrong" where an expected count exists. **Never the frozen exam.** Document that rule in `VOCAB-TRAINING.md`.
4. **A loud report header.** `setup.md` opens with a status block:
   - compositions that should answer but refuse, by family, with counts and examples;
   - any wrong readings;
   - any name-probe partial binds;
   - the audit totals.

   If wrong readings or partial binds are above 0, print the summary to stderr and **exit non-zero**, unless `--accept-risks` is given. A site isn't "set up" with known wrong-answer risks.

## Measure
Run `ceist setup` (rules plus the **cached** Sonnet replies, as 064 does: **0 new calls**, `--max-dollars 0.50`; stop if any live call would be made) on:
- Phil's testbed corpus;
- the demo.

Report the composition and probe results.

**Check the gate would have caught 064's two bugs:** run setup against the code from before 064 (the commit before 064's merge), and show that the composition templates flag "keyholders of hospitals"-type refusals, and that the probes flag 'Flood model v1.0'. Then show both clean on current code.

Also run the testbed (93) and the frozen responder set, once each, to show no regression. The demo bank should exit 0, HER plans 125/125, and the golden dump unchanged. **Wrong answers stay at 0.**

## Background
- **Read first:**
  - 059's, 063's and 064's Worker notes;
  - `site.py`, `audit.py`, `paraphrase.py` (its canonical-sentence enumeration is the start for composition templates);
  - `bench/ontology/gate.py` (bisection from 056);
  - `docs/HOW-GROUND-READS.md`.
- The testbed and responder harnesses are in `/home/stuart/git/fat/aonach-responder-assessment.md` §2c and §7.
- **064 must be merged first.**
- **No live LLM calls** (cache only). Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names.

## Definition of done
- [ ] Composition templates, name probes, `--questions` and the status header with its exit code are all tested, including a stub site where a composition refuses and where a partial name binds.
- [ ] Proven that the gate catches 064's two bugs on the old code, and is clean on the new.
- [ ] Setup time, with compositions, on the testbed corpus and the demo is in Worker notes (it must stay in minutes). `VOCAB-TRAINING.md` is updated.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-065`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
