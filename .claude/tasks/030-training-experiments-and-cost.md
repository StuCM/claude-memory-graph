---
id: 030
slug: training-experiments-and-cost
status: approved
branch: crew/030-training-experiments-and-cost
model: opus
env: laptop
work: vocab-training
depends: [027]
files:
  - packages/ceist/
---

# Measure the vocabulary training route, and estimate its cost before running

## Goal
1. **A cost ledger on every LLM call.** The pipeline calls `claude -p --output-format json`, whose result carries `usage` (input, output, cache-read and cache-write tokens) and `total_cost_usd`. Record those per call in the audit log, along with the stage (ontology, base, data, questions, refine round), the model and the cache hit. Cached replies record zero cost and are flagged as cached. Every run's report ends with a cost summary per stage: calls, tokens, dollars.
2. **A size profile for each input:** `ceist vocab profile <graphs dir> [--reference <dir>]` prints the measures that drive cost. Per graph:
   - models and nodegroups;
   - link, date and property nodes;
   - distinct CRM paths;
   - list (collection) count and total labels;
   - long lists over the batch size.
   For an ontology: the classes, properties and paths in use.
3. **An estimate before training:** `ceist vocab estimate <graphs dir> --stages base,data,questions,ontology --model … [--rounds N]` predicts calls, tokens and dollars per stage.
   - It counts the calls exactly, from the same planning code each stage uses (one per nodegroup, batches of labels, and so on).
   - It sizes the prompts from the actual rendered prompt text, using `messages.count_tokens` if an API key is set, otherwise characters divided by 4, and says which.
   - It sizes replies and thinking from the ledger's observed output per call, per stage and model, with a stated default when there's no history yet.
   - **It shows its error once real runs exist:** the estimate against the ledger's actuals for every past run in the ledger.
4. **An experiment harness:** `bench/training/matrix.toml` defines runs that each vary one choice: the model per stage (Opus or Sonnet), seeds or none, refine rounds (0, 1, 2 or 3), and ontology layer first or not.
   - `bench/training/run.py --estimate` prints the matrix with each run's estimated cost and the total. **This is what Stu approves before spending anything.**
   - `run.py --run <names>` runs the chosen runs, using the cache so a shared prefix isn't paid twice. Each run is scored on one fixed benchmark: 026's fresh-graph bench, the demo question bank, the HER plans, and a held-out question set from 022. Results go to `bench/training/results.jsonl`, with scores, calls, tokens and dollars.
   - `run.py --report` writes a table: score against cost per run, plus cost against size (calls and dollars per nodegroup, per CRM path, per 100 labels), so later graphs can be estimated from their profile alone.

## Why now
Stu, 2026-11-08: "keep tracking if costs is great and also in relation to the size of graphs and ontologies so we can estimate costs before training." And earlier: "fully understand the optimum training route for vocab so we can replicate the process." The only cost figures today are guesses from prompt sizes (the HER base run: about 485 calls, a rough $20–50 at API prices). No usage has been recorded.

## Background
- **Read first:** the pipeline's LLM plumbing (`pipeline.py`: the `claude -p` runner, the audit log, the cache keyed by prompt) and 012's, 013's, 022's, 026's and 027's Worker notes.
- **Existing evidence to back-fill as "estimated, not measured":** `/home/stuart/.cache/tmp-live/base-her/` (audit log of a partial HER base run: prompts only, no usage), `/home/stuart/.cache/tmp-live/data-demo/`, and `/home/stuart/.cache/tmp-006/*` (the earlier demo runs).
- **Prices** live in one table, `packages/ceist/src/ceist/prices.py` (Opus 5.5 $4 / $20 per MTok and $0.20 cache read; Sonnet 5.5 $2 / $10 and $0.20 cache read). `total_cost_usd` from `claude -p` is preferred when present. On Stu's subscription it's an API-equivalent figure, not a bill; say so in the report.
- **Never run `claude -p` or a live LLM yourself.** Test with stubs that return the JSON shape `claude -p --output-format json` prints, with made-up usage. Write the exact live commands for Stu in Worker notes.

## Definition of done
- [ ] Unit tests:
  - the ledger records usage and cost from a stub reply, and zero for cached ones;
  - the estimate's call counts equal the calls a stub run actually makes, for each stage;
  - the profile counts on a fixture graph;
  - the matrix estimate sums;
  - the report runs over a stub `results.jsonl`.
- [ ] `ceist vocab profile` and `ceist vocab estimate` run on the demo graphs, HER (clone at `/home/stuart/.cache/tmp-003/arches-her`), Catalina and arches-lingo (read only, schema only). Paste the output in Worker notes.
- [ ] `bench/training/run.py --estimate` prints the matrix and total cost; paste it in Worker notes. That's the budget Stu approves.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-030`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
