---
id: 033
slug: ontology-build-automated
status: approved
branch: crew/033-ontology-build-automated
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
  - vocabularies/
---

# The ontology vocabulary build runs end to end without hand review, and is written up as a playbook

## Goal
Stu, 2026-11-08: "make sure all these processes are recorded and becomes part of the pipeline so that I don't have to run through with you on every build."

1. **Automatic review of proposals** (`ceist vocab ontology --review`). It applies the checks the orchestrator did by hand after the first live run, and writes a verdict and a reason on every proposal in `proposed.json`:
   - **Clash:** the phrase already exists in `phrases.json` on a different path. Drop that phrase from the proposal, unless the proposal's path is a strict extension of the existing path with the same meaning (task 025 keeps "same meaning" base phrases; reuse that test).
   - **Too generic:** a list of phrases that can't carry a CRM path on their own ("used", "use", "has", "of", "in", "about", "subject", "motivation", "was at", "involved in", "type", "kind", "classification", "material" as a bare single word…). Keep the list in a data file beside `phrases.json`, so it can grow. Bare single nouns are dropped unless the path ends at a field that is unique in its model.
   - **Shared across sibling paths:** the same phrase proposed on several paths that differ only in the start class (for example "subject of" on 10 `* P129i` paths, "activity type" on 4 `* E7 P2` paths, "object type" on `E24/E18/E22 P2`). Keep it on one path: the one reaching the most nodes. If the start class doesn't matter to the question, propose the path without it, when `crm` can key it that way.
   - **Skipped high-use paths:** the LLM skipped the most-used date paths (`P4 E52 P86i`, `P140i E13 P4`, …) as generic. List them in the review report as "needs a hand phrasing", and don't drop them silently.
   - Everything that survives is marked `"reviewed": "auto"`, with the checks it passed.
2. **One command for the whole build** (`ceist vocab ontology build <graph dirs…> -o <out>`): estimate (print it and stop if over `--max-calls`), generate, auto-review, gate (`bench/ontology/gate.py`: each proposal alone on 026's bench, then together on the bench, the demo question bank and the HER plans), accept the ones that pass into `phrases.json`, and write a **build report**:
   - what was proposed, dropped by review (with reasons), rejected by the gate (with the score that failed), and accepted;
   - the bench and demo bank before and after;
   - calls, tokens and cost from task 030's ledger.
   A person reads the report. Nothing needs editing by hand for the build to finish. `--review-only` stops after the review, for anyone who wants to look first.
3. **Run it for real on the existing proposals.** Copy the untracked `vocabularies/ontology/cidoc-crm/proposed.json` from `/home/stuart/git/personal/claude-memory-graph-foundation` (100 proposals from two live passes, 26 calls already paid; the cache is in `/home/stuart/.cache/ceist-ontology-run`) into the worktree. Run the review, gate and accept steps on it **without new LLM calls** (`--llm-cmd false`, or the cache only). Commit the resulting `phrases.json`, the reviewed `proposed.json` and the build report.
4. **The playbook** (`packages/ceist/VOCAB-TRAINING.md`): the whole vocabulary training route as it exists today, with the exact commands in order:
   - ontology layer: `vocab ontology build`;
   - graph base: `vocab pipeline --layer base`;
   - question set: `questions generate`;
   - client layer: `vocab pipeline --layer data`;
   - refine loop: `--rounds`, with the hold-out;
   - cost first: `vocab profile` / `vocab estimate`;
   - experiments: `bench/training/run.py`.
   For each step say which model, what it costs (from 030's estimates), what gate it must pass, what to look at in its report, and what not to do (never feed the hold-out bank to a prompt; review the merge report; run the estimate first). Link it from `packages/ceist/README.md`.

## Background
- **Read first:** 025's, 027's, 029's and 030's Worker notes, and the two live-run reports (summarised in this task's Why).
- **Live-run findings to encode as review checks:**
  - clashes: "cited in"/"references" (E33 P67i vs P67i E73), "mentions" (vs P129 E18), "forms part of" (vs P46i), "falls within" (vs E53 P89 E53), "used" (vs P12i E5 P4), bare "material" (vs ^ P45 / P108i E12 P126), "type"/"kind"/"classification" on P41i E17 P42 (sub-path of existing O18i/P108i paths);
  - generic: "used", "use", "subject", "motivation", "was at", "involved in", "events held", "activities held";
  - shared across siblings: "subject of" (10 P129i paths), "described in"/"documented in" (7), "written about in"/"the subject of" (6), "took part in" (3), "activity type" (4), "object type"/"type of object"/"kind of object" (3).
- **A small bug:** the tool's summary line printed "from the cache 0" when 117 paths came from the cache. Fix it from the ledger.
- **No new live LLM calls.** The existing proposals and cache are enough.

## Definition of done
- [ ] Unit tests, one per review check, plus the `build` command end to end with a stub LLM.
- [ ] The real run on the existing 100 proposals: review → gate → accept, committed, with the build report in Worker notes (counts per verdict, bench and bank before and after). Wrong readings and wrongs on the bench must not rise, and the demo bank must exit 0.
- [ ] `VOCAB-TRAINING.md` written and linked.
- [ ] The gate passes. Machine load: one heavy suite at a time (the accept gate takes about 7 minutes), `TMPDIR=/home/stuart/.cache/tmp-033`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
