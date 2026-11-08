---
id: 035
slug: date-paths-and-033-findings
status: approved
branch: crew/035-date-paths-and-033-findings
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
---

# Hand phrasings for the high-use date paths the LLM skipped, plus 033's small findings

## Goal
1. **Date paths.** The live ontology run's LLM skipped the most-used date paths as "generic". 033's build report lists 6 that need a hand phrasing; the top two are `P4 E52 P86i` (44 nodes) and `P140i E13 P4` (37). For each of the 6:
   - look at which fields it reaches in HER, Catalina, arches-lingo and the demo (read only, schema only), and what those dates mean;
   - write phrasings only where the path's meaning is clear and specific (for example a timespan's "falls within" date, an attribute assignment's "assessed on" / "recorded on");
   - where one path reaches dates that mean different things in different graphs, leave it unphrased and say why.
   Add them to `vocabularies/ontology/cidoc-crm/phrases.json` through the **same gate** (`ceist vocab ontology --accept`, or the `build` command with no LLM calls), so they're accepted only if they add right answers and break nothing.
2. **033's reviewer findings** (non-blocking, listed in `033-ontology-build-automated.md`):
   - re-running `--review` loses earlier drop reasons from `proposed.json`; keep them;
   - the build report's "Generated:" line is taken by position from `propose`'s output; take it from the ledger instead;
   - the cost table shows $0 when everything came from the cache; add a line saying so;
   - `cost.stage_of`'s handling of pre-030 audit lines has no test; add one.

## Why now
Stu, 2026-11-08: "Yeh let's do one". These are the cheap, no-LLM follow-ups to the ontology build.

## Background
- **Read first:** 023's, 025's, 027's and 033's Worker notes, and the build report at `vocabularies/ontology/cidoc-crm/build-report.md`.
- **No `claude -p`, live LLM or vocab pipeline runs.**
- A live experiment run may be using the foundation checkout in parallel; you work only in your worktree.

## Definition of done
- [ ] The phrases are accepted through the gate. Bench before and after (026's `bench/ontology/run.py`) in Worker notes; wrong readings and wrongs must not rise.
- [ ] One test per 033 finding.
- [ ] The demo question bank exits 0. HER plans: every diff is justified and re-pinned deliberately.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-035`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
