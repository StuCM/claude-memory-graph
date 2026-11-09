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
- **CRM-first.** The ontology layer is a phrasing's default home: whatever a step proposes (rules, LLM
  fill, a person's review) goes on its CIDOC-CRM path first, so every graph that uses the path gets it.
  A phrasing lands in a graph (base) or client layer only for one of these reasons: the path is
  ambiguous (no CRM path reaches one node per model), the property is not standard CRM, the term is
  site-specific (a value-qualified combo, a local word), or the gate rejected the path form. Step 8 moves
  what an older layer holds and records the reason for each phrasing left behind.

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

## 7. Coverage: `vocab coverage`, then the rules, then the directed fill

```sh
H=/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg
.venv-ceist/bin/ceist vocab coverage $D/data/graphs --client packages/ceist/bench/demo/vocab \
    --reference $D/data/vocabularies -o vocabularies/coverage --name demo
.venv-ceist/bin/ceist vocab coverage $H/graphs/resource_models --reference $H/reference_data -o vocabularies/coverage --name her
.venv-ceist/bin/ceist vocab generate <same graphs and options> -o vocabularies/coverage --name <set>   # rules, no LLM
.venv-ceist/bin/ceist vocab fill <same graphs and options> -o vocabularies/coverage --name <set> --estimate
.venv-ceist/bin/ceist vocab fill <same graphs and options> -o vocabularies/coverage --name <set>       # after the estimate
```

Run it after steps 1, 2 and 4, and again whenever the schema changes. One graph set at a time: the demo
and HER both have a model called Monument.

- **The checklist** (`coverage`, no LLM, seconds). For each element, the items a complete layer holds:
  - ontology: class words from each CRM class's label (a class word names the one model whose root is
    that class), the CRM label of each property into a link, "who" + its inverse's label where the link
    points at an actor, and a phrasing for each CRM path;
  - base: per model its type words, plus its base graph's name when the graph is renamed; per link its
    label, verb, noun and inverse forms; per date its label's other order and its event's verbs;
  - client: per controlled value its plural and its alternative labels.

  Each item is present, missing, or set aside with a reason (no model has that root class; an inverse
  phrasing would read backwards; not a count noun; audit metadata; or what review or the gate decided).
  `<set>.md` and `<set>.json` hold the percentages per layer and the missing items, heaviest first.
- **The rules** (`generate`, no LLM). Missing items a rule can phrase: CRM labels, plurals with an
  irregulars list, agent nouns to verbs ("copyright holder" → "holds copyright"), event nouns to verbs
  ("date of death" → "died"), base graph names, label splitting. Review drops a generic phrase, and one
  that could name two elements (already said of another in the same model, or proposed for two). Then
  the gate (`bench/ontology/gate.py`), as in step 1: alone on the bench, then together on the bench, the
  demo bank and the HER plans. Client value variants are not read by any bench set: they are gated on the
  demo bank only. What passes is written to its layer: ontology `phrases.json` (class words as
  `"kind": "class"`), the base graph's `manifest.json` `type_words` or nodegroup file, the client's group
  combos. `rules-<set>.md` lists what was accepted, rejected and dropped, and why; `rules-<set>.json`
  keeps the reasons, so the next `coverage` counts them as set aside.
- **The directed fill** (`fill`, LLM). Only the items no rule could phrase: CRM paths go through
  `vocab ontology build` (step 1), base and client elements through one prompt per 20 elements (labels
  and the kinds of phrasing they lack; no record data), then the same review and gate. `--estimate`
  prints the calls and dollars and sends nothing.
- **CRM-first in the rules:** a CRM path's base meaning is composed from the labels along it, through the
  event it ends in (`composed`): `P108i E12 P4` gives "made", "date of production", "production date";
  `… E12 P14` "made by"; `… E12 P7` "place of production"; `… E12 P2` "production type". An event class too
  general to say what happened (E5, E7, E13 and the assignments) gives none. When a base node and an
  ontology path that reaches it are proposed the same phrase, review keeps the path's and drops the
  node's ("CRM-first: path … carries it"): a node's own phrasings are only the delta its name adds.
- **Wh-words:** none are generated. "who" is already the model whose root is an E39 Actor
  (`implied_types`), and "where" asks for a Detail of a record's E53 links (`plan._detail`); the grammar
  uses neither as a type word elsewhere.

## 8. CRM-first: `vocab crm-first`, moving what a CRM path can carry

```sh
.venv-ceist/bin/ceist vocab crm-first $H/graphs/resource_models $D/data/graphs \
    <catalina resource_models> <arches-lingo resource_models> \
    --client packages/ceist/bench/demo/vocab -o vocabularies/coverage     # --review-only: classify, no gate
```

The base layer's graphs come first: a base folder is matched to the first graph with its id. Every
set given is one a path must mean one thing in.

- **Model:** none.
- **What it does:** classifies every base and client phrasing (`packages/ceist/CRM-FIRST-CHECK.md` §7):
  *promotable* on the shortest CRM path (from the 3-token key, never shorter) that reaches at most one
  node of its kind in every model of every set, else *ambiguous path*; *non-CRM* (a nodegroup phrase, or
  a property outside standard CRM); *site-specific* (a value-qualified combo, a local term); *clash*
  (generic, already on another path, or promoted on a sibling path that reaches more); *already in
  ontology*. A plain field goes on a `"kind": "field"` path, which a `"property"` path (written for a
  controlled field) never reaches; a date's end is keyed by the path to that end (`… E52 P82b`).
  The promotable ones go to the gate, one candidate per (path, kind). What passes is merged into
  `phrases.json`, and only then removed from its layer; a removal the layered bundles would notice
  (the ontology drops the phrase as fitting two nodes, or the base keeps it for another node) is put back.
- **Look at:** `vocabularies/coverage/crm-first.md` (per layer and graph, and the gate's verdict per path)
  and `crm-first.json` (every phrasing left in a layer with its one-line reason). `vocab coverage` shows
  both: per graph how much of its vocabulary is base meaning (from the ontology) and how much is delta
  (its own layers), and per layer why the rest lives where it does.
- **Cost:** no LLM; the gate takes about as long as step 1's.

## When vocabulary work is done

1. **The checklist is at 100% explained:** every item present, or set aside with a recorded reason.
   It is bounded by the schema, not by English.
2. **Not vocabulary's job:** topics the data doesn't record (refusing them is right), filler words and
   question shapes (the grammar's), misspelt or partial names (name matching's).
3. **Results level off:** stop when a round adds fewer than about 2 right answers on the hold-out set.
4. **Later, live:** a phrase refused in scope 3 or more times in the capture log is a gap; keep those
   under an agreed rate.

After that, builds run only when the schema changes or the capture log repeats a phrase.
