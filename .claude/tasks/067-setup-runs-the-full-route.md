---
id: 067
slug: setup-runs-the-full-route
status: approved
branch: crew/067-setup-runs-the-full-route
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/
  - packages/ceist/bench/ontology/
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
  - packages/ceist/VOCAB-TRAINING.md
  - packages/ceist/docs/HOW-GROUND-READS.md
---

# `ceist setup --llm` runs the whole training route we used for HER and the demo, including the controlled lists, then two grammar gaps

## Goal
Stu, 2026-11-11: "we need to build on the lists as well, happy for this to run through the api. I want to replicate what we previously did to get the best results possible without the llm" (that is, no LLM at question time; the LLM is used only at build time).

The ceiling experiment (`/home/stuart/.cache/tmp-aonach/ceiling/`) and a check of the Sonnet build showed that `ceist setup` (059) runs only part of the route in `VOCAB-TRAINING.md`:
- the graph base, a small directed fill, and paraphrases;
- **no list-item stage** (step 4, `vocab pipeline --layer data`);
- **no generated question set** (step 3);
- **no refine rounds** (step 5).

So Phil's controlled lists never got everyday forms. The sector values are "q — human health and social work" and "p — education"; the service role is "water / pumping station"; severity is "high"/"very high". "which organisations are in the health sector" fails because no value is called "health", and "severe" never maps to high or very high.

**Codes may or may not be present, and could be in any format** (Stu), so **no code-pattern rules**. The LLM reads each label whole.

1. **`ceist setup --llm` runs the full route, in order, each step gated** with 065's compositions and name probes and 066's per-phrase judgement, on the site's own questions only:
   1. shared layers as they are; then the graph base for graphs with none (as today);
   2. **the list-item stage:** every controlled list, each item → everyday forms, synonyms, short forms and plurals ("health", "healthcare"; "severe" → high, very high; "pumping stations", "water stations"). This is the data layer's route (012/032: each list sent once, batched). Reuse that code rather than writing a second version;
   3. **a generated training question set** (`questions generate`), from the schema only;
   4. **refine rounds** (`--rounds`, default 2) on that training set, with a hold-out split **of the generated set**;
   5. the directed fill for whatever the coverage checklist still lists, then paraphrases (as today).

   Print the estimate for the whole route first; stop if it is over `--max-dollars`.
2. **The coverage checklist flags every list item with no everyday form** (or records why none is needed), and the status block in `setup.md` counts them.
3. **Grammar gap A: a field name after its value.** "health **sector**", "heritage **status**", "**severity** band": the field's phrasing *after* a value narrows that value to the field, as `_field_phrases` does when it comes before.
4. **Grammar gap B: a link through an intermediate record.** "buildings **covered by** a policy" means Building ← Insurance coverage → Insurance policy. Where a link phrase names two types that only one intermediate model joins, read it as that two-hop path, but only if exactly one such path exists. Otherwise ask "did you mean", never guess.
5. **The compositions (065) also use everyday forms,** so a missing one shows up in `setup.md`.

## Running it
- **Build and test with stub LLMs only** (`--llm-cmd`). Every new stage needs a stub test.
- **Then one live run** on Phil's testbed corpus (`/home/stuart/.cache/tmp-aonach/testbed/corpus`), with **`--llm ant --model sonnet --max-dollars 10`**. Stu has approved API spend for this, with that cap. Reuse the existing cache for the base layer (copy `/home/stuart/.cache/tmp-062/sonnet-site/llm/cache` into your output dir). Use the same six Building defaults as `run.sh`, plus any role defaults setup asks for (list them). **If the printed estimate is over $10, stop and report** instead of running.
- **Record the real spend** from the ledger in Worker notes.

## Measure (tables in Worker notes)
- **Phil's testbed with the half-swap** (Stu, 2026-11-11):
  - split the 93 scorable questions into halves A and B, balanced by tier, with a fixed seed;
  - build with A as `--questions` and score B; build with B and score A;
  - report each half and the combined score. This tells us what learning from real questions adds, honestly;
  - **also score the plain build (no `--questions`)** on all 93, with the harness `/home/stuart/.cache/tmp-aonach/testbed/run.sh` logic;
  - **read every new right** and record it in `testbed/reviews.json`.
- Phil's frozen responder set **once** (`/home/stuart/.cache/tmp-aonach/responder.json`, sha `ad2e6bba`), plus the practice set.
- The demo bank (exit 0), HER plans 125/125, the generated and reorder sets, and the golden dump (every change explained).
- **Wrong answers at 0 everywhere.**

## Background
- **Read first:**
  - `VOCAB-TRAINING.md` (the route, steps 0–8);
  - the Worker notes of 012/032 (the data layer), 059, 062 (`--llm ant`), 064, 065 and 066;
  - `site.py`, `pipeline.py`, `questions.py`, `compose.py`, `ground/phrases.py`;
  - `docs/HOW-GROUND-READS.md`.
- The ceiling experiment's findings are in `/home/stuart/.cache/tmp-aonach/ceiling/results.json`.
- **No LLM at question time.**
- Machine load: at most 2 processes. **Stop any `claude_memory_graph serve` process your session starts.**
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names. Update `VOCAB-TRAINING.md` (setup now runs the full route) and `HOW-GROUND-READS.md` (the two grammar rules).

## Definition of done
- [ ] The full route in setup is tested with stubs: list items, questions, rounds, and the checklist flag.
- [ ] Both grammar rules are tested, including an intermediate link with two possible paths asking "did you mean".
- [ ] One live run under the $10 cap, with the real spend recorded.
- [ ] The half-swap and plain-build scores, the responder set and the regression sets are in Worker notes. Wrong answers are at 0; every new right is read.
- [ ] The gate passes. `TMPDIR=/home/stuart/.cache/tmp-067`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
