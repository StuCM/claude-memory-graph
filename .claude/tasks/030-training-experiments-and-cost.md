---
id: 030
slug: training-experiments-and-cost
status: done
branch: crew/030-training-experiments-and-cost
model: opus
env: laptop
work: vocab-training
depends: [027]
files:
  - packages/ceist/
gate: pass
gateSha: 7f7d56cf94654fa01fe8606400d80fc698145879
gateAt: 2026-11-08T12:38:56.517Z
rounds: 2
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

### What changed
- `src/ceist/prices.py` (new): the one price table (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, cache read $0.20; cache write priced 1.25× input, which the spec didn't give). An unknown model (claude -p's default) prices as Opus.
- `src/ceist/pipeline.py` `Runner`: each call's audit.jsonl line now carries the ledger beside its prompt: `stage` (ontology/base/data/questions/refine, from the call's kind), `round`, `llm` (from claude's `modelUsage`, else `--model`), `cached`, `usage` (input, output, cache read, cache write), `cost_usd` (claude's `total_cost_usd`, else prices.py) and `cost_from`. A cache hit gets a line with no prompt, cost 0, `cached: true`. The line is written after the call now (in a `finally`, so a failed or timed-out call is still audited). A stub `--llm-cmd` that prints the `claude -p --output-format json` envelope (`"type": "result"`) is read as one; a plain stub still works. Field is `llm`, not `model`: `model` is already the Arches model in `what`.
- Reports end with a `## Cost` table per stage (calls, cached, tokens, dollars, and the "API-equivalent, not a bill" line): `vocab pipeline` (both layers, refine included), `questions generate` and `vocab ontology` (logged).
- `src/ceist/cost.py` (new): ledger reading/summary, `profile`, `plan` (the prompts each stage sends, from the stage's own functions with an LLM that answers nothing), `estimate`, `against` (estimate vs actuals per past run).
- `src/ceist/questions.py`: `prompt_for` factored out of `generate` so the estimate renders the same prompt. `ontology_vocab.py`: audit `"step"` → `"kind": "ontology"`.
- `src/ceist/arches_describe.py`: a null node `config` read as `{}` (as 026's bench does in memory), so arches-lingo describes.
- `src/ceist/cli.py`: `ceist vocab profile`, `ceist vocab estimate`.
- `bench/training/matrix.toml`, `bench/training/run.py` (new): `--estimate`, `--run`, `--report`.
- `bench/demo/run_bank.py`: `CEIST_CLIENT` puts a run's client layer in place of the demo's `vocab/` (`CEIST_BASE` already existed). `bench/ontology/run.py`: `CEIST_ONTOLOGY` scores another ontology layer.
- `tests/test_cost.py`: the five DoD tests (ledger + cached; prices fallback; estimate = stub run calls for base, data, questions and ontology; ledger-sized replies and the error table; old prompt-only runs; profile on the CRM fixture; matrix sums with a shared prompt paid once; report over a stub results.jsonl).

### Decided, spec silent
- **Stages:** `base` is the default/base pipeline (group, model, collision, acceptance-question and label calls); `data` is values + phrases; `questions` is 022's `questions generate`; `refine` is any refine round (its own stage, with the round). In the matrix, refine runs on the data layer, so it uses the data model.
- **What the estimate can't count exactly, and says so:** collision passes (only when the LLM's phrases collide; at most one per model), retries (at most one more per call), and refine (N rounds is the most; its prompt holds failures that exist only after a build, so it is sized from the ledger's refine calls, else 8000 tokens). Replies: the ledger's mean output per stage and model family, else 2000 tokens per call (027's "1–3k with thinking").
- **"Its error once real runs exist":** `--ledger <run dir>` re-sizes each past run's own recorded prompts the estimate's way and sets that beside its ledger actuals (calls, input, output, dollars, % error). A run with prompts and no ledger (everything before this task) shows as "estimated, not measured".
- **Matrix:** "ontology first" = propose over HER, mark every proposal reviewed, `--accept` (the gate decides), then the rest; "none" = phrases.json as it is. The base prompts don't read the ontology, so the choice changes the scores and refine, not the base cost. Seeds = base from `vocabularies/base` + `--seed bench/her/vocab`, client from `bench/demo/vocab`; no seeds = both empty. The questions stage runs only when a run refines (train.json is the refine bank; a bank JSON adds no data-layer phrases calls). The ontology is trained on HER only, so lingo and Catalina stay fresh for 026's bench.
- **Scores:** fresh graphs = right + right refusal, ontology mode, summed over 026's sets; demo bank = items whose status is right; HER plans = answers as reviewed in plans-2.0.json, through the run's base + ontology (`layered`); hold-out = `run_bank.py --set` right + right refusal, only when `[paths] holdout` is set (022's holdout.json needs a live `questions generate` first).

### Findings
- **HER base: 469 calls** (437 nodegroups + 16 models + 16 question calls), matching "about 485" once collisions and retries are in. The old base-her audit (356 prompts, partial) re-sizes to ~$20.60 at Opus prices.
- **The data layer is the cost nobody estimated:** on HER it is 1810 calls, ~$41 at Sonnet, because `value_variants` sends every list field, even a two-label one, as its own call (1325 list fields, only 480 distinct lists). Batching small lists per nodegroup, or one call per distinct list, would cut it to a few hundred. On the demo it is 8 calls.
- Per unit (chars/4 input, 2000 out): base ≈ $0.063 per nodegroup at Opus (1.07 calls each); data ≈ $0.022 a call at Sonnet, one call per list field per 100 of its labels (HER: $0.056 per 100 labels); ontology ≈ $0.05 per call of 10 paths.
- Base input sizing check against the old demo runs (tmp-006): estimate 162 calls for the demo base; those runs made 161–174 (collisions, retries, label).
- A base layer run whose every call fails still "passes" the gate (no cases → warning only) and writes the base (unchanged content). Pre-existing; worth a guard later.

### Stub smoke run of `run.py --run`
`run.py --matrix <copy with work in TMPDIR> --run no-ontology --llm-cmd "<python> stub.py"`, the stub printing an `is_error` envelope with made-up usage ($0.036 a call): 7 min (mostly HER plans). Ledger: base 469 calls (= the estimate), data 8 (= the estimate), $17.17 recorded. Scores: fresh graphs 490/646, demo bank 65/88 (1 wrong), HER plans 125/125 (the seeded base, unchanged). `--report` rendered both tables. results.jsonl/report.md from the smoke were deleted, not committed. The ontology/accept and questions stages were not exercised end to end by the smoke (accept is 027's gate, ~7 min; both commands are the documented CLI).

### After 025 merged (rebase onto a4892f1)
- Conflict in `questions.py` imports only; kept both (025's `from .ground import PREPS`, my `cost`). 025's property templates are untouched.
- `ontology_vocab.collect` now proposes controlled list-field paths (kind `property`); the estimate's ontology stage and the profile's "Ontology stage" line count them through `collect`, so no extra code. The profile's own path count now keys a property node by `path_of(tokens, kind)` as 025 does. `test_cost.py`: the ontology stub run is 4 calls (the list field added), the profile fixture now has 025's P2/P53 tags (8 classes, 6 properties, 5 paths, 4 unphrased).
- Ontology stage, per set (`ceist vocab estimate <graphs> --stages ontology`, chars/4, 2000 out, Opus):

| set | unphrased paths (nodes) | calls | input tokens | dollars |
| --- | --- | --- | --- | --- |
| demo | 109 (827) | 11 | 31360 | $0.57 |
| HER | 196 (2546) | 20 | 57800 | $1.03 |
| Catalina | 247 (3517) | 25 | 74226 | $1.30 |
| arches-lingo | 24 (81) | 3 | 7257 | $0.15 |

- 027's four-dir live command (HER, Catalina, lingo, demo together) as `propose` counts it (`--llm-cmd false --max-calls 0`, no call made; the proposed.json that wrote in this worktree was deleted): **257 paths (6971 nodes) → 26 calls**, up to 52 with retries, about $1.35 at the default sizing. 025's "~312 paths, ~32 calls" was 113 + 199 added before overlap and already-phrased paths came out.
- The per-set "Ontology stage" lines in the outputs below are from before 025 and are superseded by this table; the other profile and estimate figures are unchanged by 025.

### Profile and estimate outputs (no API key: input by characters / 4; replies at the 2000-token default)
#### demo
```
| model | nodegroups | link | date | property | CRM paths | list fields | distinct lists | labels | lists over the batch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Figure | 18 | 9 | 8 | 97 | 41 | 0 | 0 | 0 | 0 |
| Group | 17 | 7 | 6 | 80 | 33 | 0 | 0 | 0 | 0 |
| Monument | 38 | 12 | 27 | 185 | 87 | 4 | 3 | 543 | 2 |
| Object | 37 | 11 | 22 | 177 | 71 | 0 | 0 | 0 | 0 |
| Site | 13 | 10 | 4 | 23 | 20 | 0 | 0 | 0 | 0 |
| Tale | 27 | 9 | 12 | 91 | 48 | 0 | 0 | 0 | 0 |
| total (6 models) | 150 | 58 | 79 | 653 | 300 | 4 | 3 | 543 | 2 |

CIDOC-CRM in use: 46 classes, 82 properties, 161 distinct paths across the graphs (up to three tokens, as phrases.json keys them; the table total counts a path once per graph).
Ontology stage: 28 unphrased link/date paths (43 nodes) → 3 calls.

| stage | model | calls | input tokens | output tokens | dollars | output per call from |
| --- | --- | --- | --- | --- | --- | --- |
| ontology | opus | 3 | 8082 | 6000 | $0.15 | default (no history) |
| base | opus | 162 | 630347 | 324000 | $9.00 | default (no history) |
| data | sonnet | 8 | 6148 | 16000 | $0.17 | default (no history) |
| questions | opus | 6 | 99432 | 12000 | $0.64 | default (no history) |
| refine | sonnet | 2 | 16000 | 4000 | $0.07 | default (no history) |
| total | | 181 | 760009 | 362000 | $10.04 | |
```
#### HER
```
| model | nodegroups | link | date | property | CRM paths | list fields | distinct lists | labels | lists over the batch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Activity | 35 | 10 | 18 | 135 | 52 | 91 | 32 | 1817 | 2 |
| Application Area | 25 | 6 | 10 | 100 | 42 | 69 | 24 | 1104 | 0 |
| Area | 37 | 12 | 27 | 185 | 86 | 127 | 43 | 14342 | 6 |
| Artefact | 37 | 11 | 22 | 177 | 71 | 121 | 41 | 4119 | 1 |
| Bibliographic Source | 15 | 3 | 5 | 58 | 29 | 36 | 16 | 1018 | 1 |
| Consultation | 40 | 21 | 20 | 122 | 68 | 84 | 31 | 1662 | 0 |
| Digital Object | 10 | 2 | 6 | 37 | 21 | 24 | 12 | 368 | 0 |
| Heritage Story | 27 | 9 | 12 | 91 | 48 | 65 | 24 | 1102 | 0 |
| Historic Aircraft | 39 | 13 | 29 | 200 | 96 | 143 | 56 | 14327 | 9 |
| Historic Landscape Characterization | 21 | 4 | 12 | 93 | 42 | 68 | 27 | 1460 | 2 |
| Maritime Vessel | 41 | 15 | 34 | 206 | 95 | 145 | 54 | 13315 | 10 |
| Monument | 38 | 13 | 27 | 184 | 87 | 126 | 43 | 14217 | 6 |
| Organization | 17 | 7 | 6 | 80 | 33 | 49 | 18 | 637 | 0 |
| Period | 19 | 2 | 16 | 73 | 30 | 55 | 18 | 1013 | 0 |
| Person | 18 | 9 | 8 | 97 | 41 | 59 | 20 | 1110 | 1 |
| Place | 18 | 0 | 10 | 90 | 32 | 63 | 21 | 940 | 0 |
| total (16 models) | 437 | 137 | 262 | 1928 | 873 | 1325 | 480 | 72551 | 38 |

CIDOC-CRM in use: 51 classes, 110 properties, 272 distinct paths across the graphs (up to three tokens, as phrases.json keys them; the table total counts a path once per graph).
Ontology stage: 74 unphrased link/date paths (144 nodes) → 8 calls.

| stage | model | calls | input tokens | output tokens | dollars | output per call from |
| --- | --- | --- | --- | --- | --- | --- |
| ontology | opus | 8 | 20696 | 16000 | $0.40 | default (no history) |
| base | opus | 469 | 2196808 | 938000 | $27.55 | default (no history) |
| data | sonnet | 1810 | 2258108 | 3620000 | $40.72 | default (no history) |
| questions | opus | 16 | 436728 | 32000 | $2.39 | default (no history) |
| refine | sonnet | 2 | 16000 | 4000 | $0.07 | default (no history) |
| total | | 2305 | 4928340 | 4610000 | $71.13 | |
```
#### Catalina
```
| model | nodegroups | link | date | property | CRM paths | list fields | distinct lists | labels | lists over the batch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Activity | 78 | 34 | 30 | 199 | 103 | 140 | 36 | 2768 | 4 |
| Application Area | 26 | 7 | 10 | 100 | 42 | 69 | 24 | 1225 | 2 |
| Archive Source | 26 | 9 | 10 | 90 | 48 | 54 | 20 | 1675 | 3 |
| Area | 89 | 40 | 43 | 264 | 143 | 187 | 44 | 16108 | 9 |
| Artefact | 91 | 39 | 38 | 256 | 128 | 182 | 44 | 6292 | 4 |
| Bibliographic Source | 22 | 7 | 9 | 74 | 44 | 45 | 17 | 1117 | 2 |
| Digital Object | 19 | 7 | 10 | 53 | 37 | 33 | 14 | 294 | 0 |
| Event | 38 | 23 | 24 | 151 | 79 | 105 | 26 | 1080 | 1 |
| Field Assessment | 48 | 25 | 24 | 140 | 83 | 94 | 33 | 1800 | 2 |
| Group | 4 | 1 | 0 | 4 | 5 | 3 | 3 | 41 | 0 |
| Heritage Place | 84 | 36 | 41 | 253 | 136 | 177 | 45 | 15772 | 9 |
| Heritage Story | 65 | 25 | 20 | 136 | 71 | 102 | 25 | 2145 | 2 |
| Historic Aircraft | 40 | 15 | 29 | 199 | 96 | 143 | 56 | 14729 | 12 |
| Historic Landscape Characterization | 22 | 5 | 12 | 93 | 43 | 68 | 27 | 1576 | 4 |
| Maritime Vessel | 42 | 17 | 34 | 205 | 95 | 145 | 54 | 13602 | 13 |
| Mātauranga | 27 | 18 | 4 | 38 | 46 | 28 | 7 | 111 | 0 |
| Organization | 45 | 20 | 16 | 124 | 68 | 81 | 19 | 1257 | 1 |
| Period | 25 | 6 | 20 | 87 | 45 | 63 | 19 | 1068 | 1 |
| Person | 99 | 72 | 38 | 315 | 134 | 172 | 38 | 4249 | 4 |
| Place | 19 | 1 | 10 | 90 | 33 | 63 | 21 | 988 | 1 |
| Registry | 6 | 1 | 2 | 11 | 10 | 8 | 8 | 168 | 0 |
| Tikanga | 18 | 23 | 8 | 34 | 46 | 25 | 7 | 179 | 0 |
| Whenua | 29 | 33 | 0 | 47 | 68 | 37 | 1 | 0 | 0 |
| total (23 models) | 962 | 464 | 432 | 2963 | 1603 | 2024 | 588 | 88244 | 74 |

CIDOC-CRM in use: 69 classes, 157 properties, 435 distinct paths across the graphs (up to three tokens, as phrases.json keys them; the table total counts a path once per graph).
Ontology stage: 111 unphrased link/date paths (291 nodes) → 12 calls.

| stage | model | calls | input tokens | output tokens | dollars | output per call from |
| --- | --- | --- | --- | --- | --- | --- |
| ontology | opus | 12 | 30359 | 24000 | $0.60 | default (no history) |
| base | opus | 1008 | 5801008 | 2016000 | $63.52 | default (no history) |
| data | sonnet | 2287 | 2742895 | 4574000 | $51.23 | default (no history) |
| questions | opus | 23 | 706552 | 46000 | $3.75 | default (no history) |
| refine | sonnet | 2 | 16000 | 4000 | $0.07 | default (no history) |
| total | | 3332 | 9296814 | 6664000 | $119.17 | |
```
#### arches-lingo
```
| model | nodegroups | link | date | property | CRM paths | list fields | distinct lists | labels | lists over the batch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Concept | 18 | 19 | 14 | 42 | 34 | 22 | 10 | 78 | 0 |
| Digital Object (system) | 5 | 0 | 0 | 13 | 10 | 4 | 4 | 26 | 0 |
| Group (system) | 4 | 0 | 0 | 12 | 9 | 4 | 4 | 40 | 0 |
| Person (system) | 4 | 0 | 0 | 12 | 9 | 4 | 4 | 27 | 0 |
| Scheme | 14 | 10 | 6 | 29 | 25 | 13 | 9 | 52 | 0 |
| Textual Work (system) | 5 | 0 | 0 | 13 | 9 | 5 | 5 | 31 | 0 |
| total (6 models) | 50 | 29 | 20 | 121 | 96 | 52 | 36 | 254 | 0 |

CIDOC-CRM in use: 20 classes, 30 properties, 53 distinct paths across the graphs (up to three tokens, as phrases.json keys them; the table total counts a path once per graph).
Ontology stage: 11 unphrased link/date paths (24 nodes) → 2 calls.

| stage | model | calls | input tokens | output tokens | dollars | output per call from |
| --- | --- | --- | --- | --- | --- | --- |
| ontology | opus | 2 | 3067 | 4000 | $0.09 | default (no history) |
| base | opus | 62 | 129955 | 124000 | $3.00 | default (no history) |
| data | sonnet | 52 | 23617 | 104000 | $1.09 | default (no history) |
| questions | opus | 6 | 27144 | 12000 | $0.35 | default (no history) |
| refine | sonnet | 2 | 16000 | 4000 | $0.07 | default (no history) |
| total | | 124 | 199783 | 248000 | $4.60 | |
```

The base and data figures above are for these graphs as given; HER's data stage is with every list (`--reference`), which a real client layer would slice first.

### Matrix estimate (`run.py --estimate`): the budget to approve
```
| run | varies | ontology | base | questions | data | refine | calls | dollars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | $1.03 | $27.73 |  | $0.17 |  | 497 | $28.94 |
| base-sonnet | base_model sonnet | $1.03 | $13.87 |  | $0.17 |  | 497 | $15.07 |
| data-opus | data_model opus | $1.03 | $27.73 |  | $0.35 |  | 497 | $29.11 |
| no-seeds | seeds False | $1.03 | $27.55 |  | $0.17 |  | 497 | $28.75 |
| no-ontology | ontology none |  | $27.73 |  | $0.17 |  | 477 | $27.91 |
| rounds-1 | rounds 1 | $1.03 | $27.73 | $0.64 | $0.17 | $0.04 | 504 | $29.61 |
| rounds-2 | rounds 2 | $1.03 | $27.73 | $0.64 | $0.17 | $0.07 | 505 | $29.65 |
| rounds-3 | rounds 3 | $1.03 | $27.73 | $0.64 | $0.17 | $0.11 | 506 | $29.68 |

Total, each run on its own: $218.73. With the shared cache (a prompt sent twice is paid once): **$67.72**.
Refine rounds are counted at their most; collision passes and retries are not counted.
Dollars are API list prices; on a Claude subscription they are usage, not a bill.
```
Ontology over HER only (196 unphrased link, date and list-field paths → 20 calls, after 025); base over HER; data and questions over the demo. Every run shares the baseline's base unless it changes the base model or seeds, so the matrix costs ~$68 at API prices, not $219.

### Live commands for Stu (not run)
From the worktree root (or ceist-foundation after merge). Look at the budget first, then run the cheapest useful pair, then the rest:
```sh
.venv-ceist/bin/python packages/ceist/bench/training/run.py --estimate
.venv-ceist/bin/python packages/ceist/bench/training/run.py --run baseline,no-ontology    # ~$28: base paid once
.venv-ceist/bin/python packages/ceist/bench/training/run.py --run base-sonnet,data-opus,no-seeds,rounds-1,rounds-2,rounds-3
.venv-ceist/bin/python packages/ceist/bench/training/run.py --report                       # → bench/training/report.md
```
Runs go to `~/.cache/ceist-training/<run>/` with one shared cache; a re-run of a run pays only for prompts not yet answered. For the hold-out score, generate 022's set once and set `[paths] holdout` in matrix.toml:
```sh
D=/home/stuart/git/personal/starches-demo/ask; R=$(mktemp -d); mkdir $R/concepts; ln -s $D/data/vocabularies/smr.xml $R/concepts/
.venv-ceist/bin/ceist questions generate $D/data/graphs -o ~/.cache/ceist-questions-demo --reference $R --model opus
# then: holdout = "/home/stuart/.cache/ceist-questions-demo/holdout.json"
```
After any live run, the estimate learns from it: `ceist vocab estimate <graphs> --stages base --ledger ~/.cache/ceist-training/baseline/base` sizes replies from the ledger and prints the estimate against the actuals.

### Other checks
- Gate passed on 7f7d56c (rebased on a4892f1, after 025 merged): root 629 passed (51 skipped, 1 deselected); Ceist 325 passed. (Before: 008db11 on 09e29f1, 625 / 321.)
- No change to ground.py, plan.py, rosmadair.py, bundle.py or any vocabulary; nothing reaches `memory_ask` (`tests/test_planner.py` passes in the gate). The audit lines gained fields; the privacy greps on audit.jsonl are unchanged in what they cover (prompt text is the same).

## Graph writes proposed
- Pattern (ceist cost estimate): count an LLM stage's calls by running the stage's own functions with a Runner whose `ask` records the prompt and returns None; a test compares that count to a stub run's ledger per stage, so the estimate cannot drift from the pipeline.
- Decision (ceist ledger): usage and cost live on each call's audit.jsonl line (`stage`, `llm`, `usage`, `cost_usd`, `cost_from`, `cached`); the field is `llm` because `model` is the Arches model. `total_cost_usd` wins over prices.py; on a subscription it is API-equivalent usage.
- Finding (ceist data layer): `value_variants` makes one call per list field per 100 labels, so HER's data layer is ~1810 calls (1325 list fields, 480 distinct lists), the largest cost in the route; batching small lists would cut it.

## Review rounds
- Round 1 (008db11): PASS. Non-blocking: `run.py` `setup()` wipes `<work>/<run>` on a re-run, losing an earlier attempt's ledger (its spend stays in results.jsonl; results.jsonl gets a second row); `modelUsage` with several models prices by the first only when `total_cost_usd` is missing. (Its note that refine runs under-count data calls does not hold: train.json is a bank, which adds no phrases calls.)
- Round 2 (7f7d56c, rebased onto a4892f1 after 025): PASS. The merge keeps both sides; property paths are counted through `collect`; the test changes follow from 025's fixture and are not weaker.
