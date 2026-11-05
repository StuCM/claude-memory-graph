---
id: 006
slug: vocab-pipeline-round-two
status: approved
branch: crew/006-vocab-pipeline-round-two
model: opus
env: laptop
rounds: 0
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
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
- [ ] Unit tests with a fake `--llm-cmd`: type-word generation and validation, type-paired link phrasings surviving the collision pass, end-to-end case judging, and seed merging.
- [ ] Commands for Stu's live re-run are in Worker notes. Agents can't call `claude -p`, because the desktop app holds the login; Stu runs it from a logged-in terminal. Give two variants: without seeds, and with the demo seeds and questions. Outputs go to `/home/stuart/.cache/tmp-006/`. Mark the live-result items pending.
- [ ] The gate passes; test counts before and after are in Worker notes. HER plans (`bench/her_plans.py`) are unchanged, since only pipeline code changes. The demo questions are unchanged with the hand-tuned vocabulary.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-006`, never `git add -A` or `git stash`.

## Worker notes

## Review rounds
