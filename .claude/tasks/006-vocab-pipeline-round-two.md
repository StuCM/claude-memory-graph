---
id: 006
slug: vocab-pipeline-round-two
status: done
branch: crew/006-vocab-pipeline-round-two
model: opus
env: laptop
rounds: 1
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
gate: pass
gateSha: 48d8864f372159179ce94a3607d2e7823e862e7b
gateAt: 2026-11-05T13:46:18.488Z
---

# Vocab pipeline round two: type names, type-paired link wording, end-to-end cases, seeds

## Goal
A re-run of `ceist vocab pipeline` on the demo graphs answers at least as many of the 26 demo questions (`bench/demo_compare.py`) as the hand-tuned vocabulary (22/26), with no more dangerous answers. Its own test cases are judged at the whole-question level, not just phrase → field.

## Why now
Stu, 2026-11-05: "yes spec 006". The first live run (outputs in `/home/stuart/.cache/tmp-004/demo-run/`: `report.md`, `cases.json`, `collisions.json`, `audit.jsonl`, `vocab/`; comparison in `/home/stuart/.cache/tmp-004/demo-compare.md`) got:
- phrase level: 37/53 right, 1 dangerous;
- planner level: 0 right and 8 dangerous;
- demo comparison: 14/26 answered against the hand-tuned 22/26.

Read those files first. The cache is there too, so unchanged groups don't need a new LLM call.

## Approach
1. **Type names.** Generate synonyms per model ("stories" and "tales" for Tale; "people" and "figures" for Figure; "organisations" for Group; "places" and "sites" for Site; "objects" and "artefacts" for Object) as `extra_type_words` in the bundle, with `ArchesVocabulary` loading them.
   - Ask for them in the per-model collision call, or in one small per-model call.
   - Validate against the other models, so a type word never names two models.
   - Most of the 8 dangerous plans were unknown type words falling back to text mentions.
2. **Link wording by the types it joins.** For each link node, the prompt gets the source model and the target models, with their CRM property. It asks for short phrasings for that pair ("in", "located in", "at" for Monument→Site `named_location`; "part of", "belongs to", "in" for Tale→Tale `parent_story`), plus reverse phrasings from the CRM inverse.
   - The grounder's type-pair fitting (`ground._fit_relations`) already chooses between relations that share a phrase, so short shared prepositions are safe to emit.
   - The collision pass must not strip a preposition that two links share when their type pairs differ.
3. **End-to-end cases.** The question writer returns expected **conditions**: `expect.conditions`, the `judge_plan` format 005 added (node, value, tile, link targets by model), or an expected refusal. The planner-level score must then be meaningful. Report right, partial, dangerous, missed and refused at both levels.
4. **Seeds.** `--seed <vocab or phrasings file>` and `--questions <file>`:
   - Seeds are existing phrasings the LLM extends, never deletes; it marks any seed it judges wrong instead of removing it.
   - The demo's hand-tuned extras (`EXTRA_TYPE_WORDS` and `RELATION_FORMS` in `/home/stuart/git/personal/starches-demo/ask/ask.py`) and the 26 README questions should work as seed and questions inputs.
   - Bump `PROMPT_VERSION`, since the prompts change.
5. **The dangerous phrase,** "weight in grams" → `dimension_measurement_unit`: the collision or validation pass should catch a unit word matching a field it only describes.

## Definition of done
- [x] Unit tests with a fake `--llm-cmd`: type-word generation and validation, type-paired link phrasings surviving the collision pass, end-to-end case judging, and seed merging.
- [x] Commands for Stu's live re-run are in Worker notes. Agents can't call `claude -p`, because the desktop app holds the login; Stu runs it from a logged-in terminal. Give two variants: without seeds, and with the demo seeds and questions. Outputs go to `/home/stuart/.cache/tmp-006/`. Mark the live-result items pending.
- [x] The gate passes; test counts before and after are in Worker notes. HER plans (`bench/her_plans.py`) are unchanged, since only pipeline code changes. The demo questions are unchanged with the hand-tuned vocabulary.
- [x] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-006`, never `git add -A` or `git stash`.

## Worker notes

**Finding for the orchestrator (goal at risk, outside this spec).** 7 of the 12 demo answers lost on the first run come from one-word group-block phrases, such as `"county"` on `Monument.localities_administrative_areas`. Group phrases ground before anchors, so they take a word of the record name "County Down", and the question is refused. Removing the one-word group phrases from the first run's `bundle.json` gives **21/26** (the rest unchanged), against 14/26 with them. Nothing in this spec touches that. The live re-run will most likely stay well under 22/26 until a decision is made: drop or limit one-word group phrases in the pipeline, or let an anchor win over a bare group phrase in `ground.py`. The other losses: "part of the Ulster Cycle" (Tale `parent_story` lacked "part of"; the type-paired link call targets this one), and "what is related to Navan Fort?" ("related to" on links turns a direct match into a refusal).

What changed:
- `pipeline.py`:
  - One new call per model, `name_model`, asks for type words and for link wording by the pair a link joins (source, targets, CRM property, inverse), plus reverse phrasings. A link back to its own model gets no reverse phrasings.
  - `settle_type_words` drops a word two models claim, unless it is one model's seed.
  - The link phrasings join each link's entry (`add_link_phrases`).
  - The collision pass doesn't send phrases that only unqualified links with disjoint targets share, and it never strips a seed.
  - Questions and labels carry `expect.conditions`, which `_check_cases` validates. `judge_plan` checks the link target type and either end of a date.
  - `load_seeds` reads a bundle, a vocab dir, or `{extra_type_words, relation_forms, date_forms}`. Doubts go to the report.
  - New `unit` role (E58/P91): `check_group` rejects phrasings on a unit.
  - `PROMPT_VERSION` is "2".
- `bundle.py`: the manifest's `type_words` go to the bundle's `extra_type_words`, and two models claiming one word is an error. `unit` is a valid role.
- `arches.py`: `ArchesVocabulary` reads the bundle's `extra_type_words`, and its own argument wins. It copies the argument instead of mutating it.
- `cli.py`: `--seed` (repeatable).
- `test_pipeline.py`: 7 new tests, and the existing pipeline test is updated for the model calls and conditions.
- `docs/tasks/ceist-vocab-pipeline.md`: the round-two design.

Checks:
- **Gate:** passed on 48d8864. Ceist suite 190 → 197; root 509 → 516 (root collects `test_pipeline.py` too).
- **Mutation checks:** disabling the type-pair skip, seed protection, the self-link reverse drop, the link-target judge, or the bundle type-word read each fails a test.
- **HER plans 2.0:** 125/125 as reviewed, on the local clone `/home/stuart/.cache/tmp-003/arches-her` at the pinned 9f6a113. HER eval is 67/102, identical to base (the vectors weights aren't local).
- **HER 1.1 not run:** the pinned ref isn't in any local clone, so it needs network. HER plans unchanged is shown for 2.0 only.
- **Demo, hand-tuned vocabulary** (2026-11-05 13:50 GMT; a parallel job is editing the demo data): all 26 README answers are identical between base code and this branch, 22/26 answered.
- **Dry run with no LLM** (13:55 GMT): a fake `--llm-cmd` replayed the first run's cached group replies and collision decisions, with empty model calls. Outputs are in `/home/stuart/.cache/tmp-006/replay-{noseed,seed}/` (`report.md`, `demo-compare.md`).
  - Phrase level: 24/53 right, **0 dangerous** ("weight in grams" fixed).
  - Demo: 14/26 either way, since the "county" finding is unchanged.
  - Three Monument groups missed the old cache because their descriptions changed with the new reference lists.
- **Planner side note:** "How many stories have a translation? → Count Tales." drops "translation" silently (the grounder's loose listing). That's existing behaviour, worth a look.

**Live re-run (pending; Stu, from a logged-in terminal).** The first run used `--model sonnet` and `--reference`. `PROMPT_VERSION` 2 means no cache hits. The seed and questions files are already written: `/home/stuart/.cache/tmp-006/demo-seed.json` (`EXTRA_TYPE_WORDS` plus place/places, and `RELATION_FORMS`, from ask.py) and `/home/stuart/.cache/tmp-006/demo-questions.txt` (the 26 README questions).

```sh
W=/home/stuart/git/personal/claude-memory-graph-006; T=/home/stuart/.cache/tmp-006; D=/home/stuart/git/personal/starches-demo
export TMPDIR=$T
# 1. without seeds
$W/.venv-ceist/bin/ceist vocab pipeline $D/ask/data/graphs -o $T/live-noseed --reference $D/prebuild/reference_data --model sonnet --jobs 4
# 2. with the demo seeds and questions
$W/.venv-ceist/bin/ceist vocab pipeline $D/ask/data/graphs -o $T/live-seed --reference $D/prebuild/reference_data --model sonnet --jobs 4 \
  --seed $T/demo-seed.json --questions $T/demo-questions.txt
# compare each against the hand-tuned vocabulary
for v in noseed seed; do PYTHONPATH=$W/packages/ceist/src CEIST_HER=$W/packages/ceist/bench/her \
  $W/.venv-ceist/bin/python $W/packages/ceist/bench/demo_compare.py $D/ask $T/live-$v/bundle.json > $T/live-$v/demo-compare.md; done
```

- [ ] (pending live) The demo answers at least 22/26 with no more dangerous answers. Likely blocked by the "county" finding above.
- [ ] (pending live) Phrase and planner dangerous counts are reported for both variants.

**Graph writes proposed:**
- Pattern: a generated vocabulary's one-word group phrases ("county", "address") take words of record names before anchors bind, and refuse questions that name a record ("County Down"). Measure a generated bundle on questions that name records, not only on schema-only cases.
- Pattern: the pipeline cache key includes `--model`, so replaying a run needs the same `--model`. The first demo run used sonnet.
- Decision: reverse link phrasings only between different models, because the grounder picks direction by type alone.
- Decision: shared link phrases survive the collision pass only when the targets are disjoint.

## Review rounds

- Round 1: **PASS** (crew-reviewer). Every design choice was accepted. It asked for the live-run commands and the HER 1.1 gap in these notes, both now added, and agreed the "county" goal risk is a decision for Stu (a ground.py or pipeline follow-up). It noted that reverse phrasings rely on type fitting for direction.
