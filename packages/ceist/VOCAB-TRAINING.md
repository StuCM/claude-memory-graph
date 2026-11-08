# Vocabulary training: the playbook

How a project's vocabulary is built with an LLM, in order, with the exact commands. Every step runs
offline at build time; nothing here runs when a question is asked. Run them from the repository root,
with the Ceist venv (`.venv-ceist/bin/ceist`).

Placeholders used below:

```sh
G=<arches pkg>/graphs/resource_models      # the client's graphs
R=<arches pkg>/reference_data              # its lists (concepts, collections)
D=/home/stuart/git/personal/starches-demo/ask
```

Prices are API list prices from `prices.py` (Opus 5.5 $4/$20 per M tokens, Sonnet 5.5 $2/$10). On a
Claude subscription they are usage, not a bill. The figures are task 030's estimates; re-run step 0
for the graphs in hand, because they change with the graphs.

## The rules for every step

- **Run the estimate first** (step 0). Every stage that calls an LLM has a `--max-calls`, a gate or
  both, but the estimate is the only thing that tells you the bill before it is paid.
- **Never send the hold-out bank to a prompt.** `holdout.json` (step 3) and the demo bank
  (`bench/demo/questions.json`) are only for scoring. Pass them as `--holdout`, never as
  `--questions` or `--seed`.
- **Read each report before the next step.** Each step writes a report (`report.md` or
  `build-report.md`). The gate decides what merges, but a person reads what it did.
- **No record data goes to an LLM.** The prompts hold the schema, CRM text and masked questions.
  `audit.jsonl` in each out dir holds every prompt that was sent, in full.
- A re-run pays only for prompts not answered yet: each out dir has a `cache/`.

## 0. Cost first: `vocab profile` and `vocab estimate`

```sh
.venv-ceist/bin/ceist vocab profile $G --reference $R
.venv-ceist/bin/ceist vocab estimate $G --stages ontology,base,data,questions --reference $R --rounds 2
```

- **Model:** none; no call is made.
- **Look at:** the per-stage calls and dollars, and "lists over the batch" in the profile (the data
  layer's cost driver). After a live run, `--ledger <run dir>` sizes replies from what that run
  actually used, and prints the estimate against the actuals.
- **Typical (030, data after 032):** HER all stages ~$40 (base $27.55, data $10.15, questions
  $2.39); the demo ~$10; arches-lingo ~$5.

## 1. The ontology layer: `vocab ontology build`

```sh
H=/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models
C=/home/stuart/git/fat/arches/catalina/catalina-graphs/output/graphs/resource_models
L=/home/stuart/git/fat/arches/arches-lingo/arches_lingo/pkg/graphs/resource_models
.venv-ceist/bin/ceist vocab ontology build $H $C $L $D/data/graphs -o ~/.cache/ceist-ontology-run --model opus
```

One command: estimate (it stops and prints the estimate if the calls exceed `--max-calls`, default
300), propose, review, gate, accept, report. `--review-only` stops after the review, for a look
first. Without the demo or HER checkout, add `--skip demo` or `--skip her`. Otherwise a missing
checkout fails the gate, and nothing merges.

- **Model:** Opus. **Cost:** ~$0.05 a call of 10 paths. These four graph sets: 257 paths, 26 calls,
  ~$1.35; HER alone: 20 calls, ~$1.03.
- **Review (automatic):** drops a phrasing that is too generic (`vocabularies/ontology/cidoc-crm/generic.json`,
  which you can add to), that clashes with `phrases.json` on another path, that is shared by sibling
  paths (kept on one, or on the path without its start class for links), or that is a bare noun on a
  path that reaches several fields in a model. Each proposal gets a verdict and reason in
  `proposed.json`. Survivors are marked `"reviewed": "auto"`.
- **Gate:** `bench/ontology/gate.py`. Each proposal alone on 026's bench must add a right answer and
  make nothing worse. Then the passing ones together on the bench, the demo bank (must be unchanged)
  and the HER plans. Takes ~7 min or more, longer with more proposals. Run it on its own.
- **Look at:** `vocabularies/ontology/cidoc-crm/build-report.md`. It lists what review dropped and
  why, what the gate rejected (with the score that failed), what was accepted, and the bench and
  demo bank before and after. It also lists **"Needs a hand phrasing"**: high-use date paths the LLM
  skipped. Phrase those by hand in `phrases.json` if they matter, then run the gate on them.
- **Don't:** hand-edit `phrases.json` to get round a rejection. Commit `phrases.json`,
  `proposed.json` and the report together.

## 2. The graph base: `vocab pipeline --layer base`

```sh
.venv-ceist/bin/ceist vocab pipeline $G -o ~/.cache/ceist-base --reference $R --layer base --base vocabularies/base \
    --seed packages/ceist/bench/her/vocab --model opus --min-right 80 --max-dangerous 3
```

- **Model:** Opus. **Cost:** ~$0.063 per nodegroup (1.07 calls each). HER: 469 calls, ~$27.55.
- **Gate:** the acceptance questions it writes (`cases.json`, frozen on the first run) are scored by
  phrase and through the planner. `--min-right` / `--max-dangerous` set the bar. The base is written
  to `--base` **only when the gate passes**. A run with no acceptance cases measures nothing and
  only warns, so check that `cases.json` is not empty.
- **Look at:** `report.md`: coverage, the gate line, warnings (one-word group phrases), the doubts
  about seeds, and the cost table. Then run the HER plans (`bench/her_plans.py`) if HER changed.
- **Don't:** pass `--questions`. A base takes no client questions, and the command refuses them.

## 3. The question set: `questions generate`

```sh
.venv-ceist/bin/ceist questions generate $D/data/graphs -o ~/.cache/ceist-questions-demo --reference <dir> --model opus
```

- **Model:** Opus. **Cost:** one call per model. The demo: 6 calls, ~$0.64; HER: 16, ~$2.39.
- **Writes:** `train.json` (for the refine loop) and `holdout.json` (only for scoring), each item
  with its target reading or its refusal reason.
- **Gate:** none of its own. `check` rejects a reply naming a model, node, value or placeholder that
  doesn't exist, or writing out a record name, and the call is retried once.
- **Look at:** a sample of the items and their targets. A wrong target teaches the loop a wrong reading.
- **Don't:** ever pass `holdout.json` as `--questions`.

## 4. The client layer: `vocab pipeline --layer data`

```sh
.venv-ceist/bin/ceist vocab pipeline $D/data/graphs -o ~/.cache/ceist-data --reference <reference dir> --layer data \
    --client <client vocab dir> --base vocabularies/base --model sonnet \
    --records $D/data/resources --holdout packages/ceist/bench/demo/questions.json
```

- **Model:** Sonnet. **Cost:** each distinct list is sent once, small ones packed into one call
  (032). The demo: 4 calls, ~$0.09. HER with every list: 403 calls, ~$10 (replies likely
  understated until a real run's ledger sizes them). Slice the reference data to what the client uses first.
- **Gate:** none merges silently. The client files are written, and the **merge report** in `report.md`
  lists every phrase that would override or clash with the base. Nothing in it is applied.
- **Look at:** the merge report, the seeds the LLM doubts, and failed calls.
- **Don't:** skip the merge report. Real questions (`--questions`) are masked before they are sent,
  but they must not include the hold-out (they are dropped and counted if they do).

## 5. The refine loop: `--rounds`, with the hold-out

Add to step 4:

```sh
    --rounds 2 --questions ~/.cache/ceist-questions-demo/train.json \
    --holdout ~/.cache/ceist-questions-demo/holdout.json
```

- **Model:** the data layer's (Sonnet). **Cost:** ~8000 tokens in a round, ~$0.04; a few dollars at
  most with the questions stage.
- **Gate:** each round sends the failed training cases (masked) and is **kept only when right
  answers go up, wrong ones don't, and no hold-out question turns wrong**. Otherwise it is rolled
  back and the loop stops. The hold-out is scored every round, never sent.
- **Look at:** the per-round lines in `report.md`: right/wrong on train and on the hold-out. A gain on
  train with no gain on the hold-out is overfitting, so stop adding rounds.
- **Don't:** use the hold-out as training questions, or raise `--rounds` past where the hold-out stops
  improving.

## 6. Experiments: `bench/training/run.py`

```sh
.venv-ceist/bin/python packages/ceist/bench/training/run.py --estimate     # every run in matrix.toml, priced
.venv-ceist/bin/python packages/ceist/bench/training/run.py --run baseline,no-ontology
.venv-ceist/bin/python packages/ceist/bench/training/run.py --report       # → bench/training/report.md
```

- **What it does:** each run in `bench/training/matrix.toml` changes one choice from the baseline
  (base model, data model, seeds, ontology first or not, refine rounds). It runs steps 1–5 into
  `~/.cache/ceist-training/<run>/` with one shared cache, then scores the fresh graphs (026's bench),
  the demo bank, the HER plans and, if `[paths] holdout` is set, the hold-out.
- **Cost:** the whole matrix ~$68 with the shared cache, $219 if every run paid for its own base. Start
  with `baseline,no-ontology` (~$28, the base paid once).
- **Look at:** `report.md`: the scores per run, and the cost against size.
- **Don't:** run it without `--estimate` first.
