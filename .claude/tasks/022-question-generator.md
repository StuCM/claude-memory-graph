---
id: 022
slug: question-generator
status: done
branch: crew/022-question-generator
model: opus
env: laptop
work: ceist-questions
files:
  - packages/ceist/
gate: pass
gateSha: 6d75d7ef774389f3931f9ffae65f84ed8844df6b
gateAt: 2026-11-06T23:14:09.990Z
rounds: 2
---

# An LLM writes a labelled starting question set for a graph

## Goal
`ceist questions generate <graphs dir> -o <out> [--reference <dir>] [--per-model N]` writes a question set for a graph. It is **separate from vocabulary building**, and is a starting bank that client questions build on.

1. **Offline, from the schema only.** The same describe output and short list labels the vocab pipeline sends today, never records.
   - Questions that need a named record use **typed placeholders**, such as "which monuments are in {Site}?" or "who is associated with {Figure}?".
   - The scorer fills the placeholders locally, from the vocabulary's own record names, at test time.
2. **Each question is labelled with the reading it should get, not a count:**
   - a structured target: the model, whether it's a count, and the conditions (field, value label or target type, negated, same-tile);
   - or `refuse` with a reason: story text, an "or" across fields, an unsupported shape.
3. **Breadth:**
   - for every model, its fields, links, lists and nodegroups;
   - direct, paraphrased and awkward wordings;
   - the question shapes Ceist supports today: values, links, on-tile, negation, or, group-by, near, name match, record detail, chains and backlinks;
   - roughly 15% should-refuse questions.
4. **Independent of the vocabulary:**
   - its own prompts;
   - it never reads the vocabulary;
   - a deterministic split into `train.json` and `holdout.json`;
   - written in the bank format `packages/ceist/bench/demo/questions.json` uses, extended with the structured target.
5. **Scoring:** `run_bank` (or a sibling) scores a generated set by **comparing Ceist's plan with the target**, structurally. It reports right, wrong reading, refused (should answer), right refusal, and wrong (answered a should-refuse).

## Why now
Stu, 2026-11-06: "Should an llm run through a graph and come up with questions? Not make vocab but build a rich question set as a starting base to build on top of?" The demo question bank (87 questions) was written around phrasings we already knew, so it measures regressions, not coverage.

## Background
- **Reuse:**
  - `pipeline.py` describe and LLM plumbing (`claude -p`, the audit log, the cache keyed by prompt);
  - `learn.py` masking;
  - `crm.py` role hints. Use CRM classes to pick which kinds of question a field supports (when, where, who, what kind). Task 023 builds the ontology layer; here only read the classes.
- **The structured target** should match what `Plan` holds, so scoring is a structural compare: model, count, and conditions keyed by field alias. A value is compared by label; a link target by type, or by the placeholder's type.
- **Never run `claude -p` yourself.** Test with a scripted stub. Put the live command for Stu in Worker notes: the demo's six graphs, and HER's.
- **Privacy:** add an audit test that no record name, id or tile value appears in any prompt.

## Out of scope
- Feeding the set into the refine loop (`--questions train.json --holdout holdout.json` should just work; check it does with a stub).
- The CRM ontology layer (023).

## Definition of done
- [ ] Unit tests with a stub LLM:
  - placeholders are filled locally;
  - a structural score is right, wrong and refused correctly;
  - the split is deterministic;
  - the privacy audit passes.
- [ ] A dry run on the demo graphs with a stub writes `train.json` and `holdout.json`, and the scorer runs over them through the demo (`PYTHONPATH=<worktree>/packages/ceist/src`).
- [ ] The live command for Stu is in Worker notes.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- `packages/ceist/src/ceist/questions.py` (new): `PROMPT` (its own; never reads the vocabulary), `payload` (describe output with short list labels + CRM role hints, plus `asks`: when/who/where/what kind/which from the role), `check` (models, nodes, values, tiles, group, detail, placeholders must exist; a capitalised name left after `learn.mask` is rejected: "write {Model}"), `generate` (one call per model through `pipeline.Runner`: cache, audit, retry), `held_out` (sha256 of the normalised text, one in 5), `bank_item`, `fill`, `target_of`, `matches`, `score`.
- `pipeline.py`: `model_roles` factored out of `run()` (behaviour unchanged) and reused.
- `cli.py`: `ceist questions generate <graphs> -o <out> [--reference] [--per-model N] [--llm-cmd] [--model] [--models]`.
- `bench/demo/run_bank.py`: `--set <train.json|holdout.json>` scores a generated set structurally (placeholders filled from the demo's record names), prints the counts and each miss with want/got; exits 0.
- `tests/test_questions.py`: split into bank files with targets; split deterministic by text; privacy audit (record names, dates, resource and tile ids absent from audit.jsonl); placeholders filled locally and deterministically; score right / wrong reading (value, negation, count, extra condition) / refused / right refusal / wrong, through `interpret` on the fixture; bad replies rejected; refine loop takes train/holdout (stub). `test_pipeline.py` FAKE: a branch for the generate prompt. Mutation-checked: dropping the negation flip and the name check each fail a test.
- **Target format** (in bank items, `expect` answer|refuse): `"target": {"model", "count", "group"?, "detail"?, "conditions": [{"node", "value"? (label, or a list for an "or" in one field), "link"?, "near"?, "tile"?, "negated"?}]}` or `"reason"`. `@name` / `@text` stand for a name match and a text mention. A group counts as a count; `detail: []` is the record itself.
- **Decided, spec silent:** conditions must pair off one to one (an extra condition in the plan = wrong reading, unlike `judge_plan`); tile/link/value compared only where the target gives them, negation always; placeholder choice = sorted names of the type, indexed by crc32 of the question; a model with no records → counted "no record to fill".
- **Known simplifications:** a chain's sub-plan conditions are not compared (only the top link and its target type); `run_bank --set` passes no date `ends`, so a date given by its other end reads wrong; placeholders are not filled inside the refine loop (it reads train.json as written, so placeholder questions refuse there; out of scope).
- **Dry run (stub, `/home/stuart/.cache/tmp-022/dry/stub.py`, mechanical questions from the payload)** on the demo's six graphs: 93 questions (6 refuse) → train 80, holdout 13; `grep -c -e Navan -e 'Emain Macha' -e Chulainn audit.jsonl` = 0. `run_bank.py --set`: train right 65, refused 11, wrong 4; holdout right 9, wrong 2, refused 2. Real finds even from the stub: "why were objects made?" answers (should refuse); "associated actor end date" and "update end date" refuse.
- **Question bank:** before = after (no grounding/plan change), exit 0: answer/right 68, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 11. questions.json unchanged.
- **HER plans / memory_ask:** no grounding, plan or vocabulary change; `tests/test_planner.py` passes in the gate. `bench/her_plans.py` not run (needs an arches-her clone). No change for `memory_ask`.
- **Live commands for Stu (not run).** From the worktree (or ceist-foundation after merge):
  ```sh
  D=/home/stuart/git/personal/starches-demo/ask; R=$(mktemp -d); mkdir $R/concepts; ln -s $D/data/vocabularies/smr.xml $R/concepts/
  .venv-ceist/bin/ceist questions generate $D/data/graphs -o ~/.cache/ceist-questions-demo --reference $R --per-model 40 --model opus
  grep -c -e Navan -e 'Emain Macha' -e Chulainn ~/.cache/ceist-questions-demo/audit.jsonl   # expect 0
  cd $D && PYTHONPATH=$OLDPWD/packages/ceist/src uv run python $OLDPWD/packages/ceist/bench/demo/run_bank.py --set ~/.cache/ceist-questions-demo/train.json
  ```
  HER:
  ```sh
  git clone https://github.com/archesproject/arches-her ~/.cache/arches-her; P=~/.cache/arches-her/arches_her/pkg
  .venv-ceist/bin/ceist questions generate $P/graphs/resource_models -o ~/.cache/ceist-questions-her --reference $P/reference_data --per-model 60 --model opus
  ```
  A rerun answers from the cache; delete `cache/` (or change `--per-model`) for a fresh set. Scoring HER's set needs a vocabulary with records (no HER scorer script yet).

## Graph writes proposed
- Decision: `ceist questions generate` writes a schema-only, vocabulary-independent question bank with structured targets (model, count, group, detail, conditions keyed by alias with value label / link type / near / tile / negated) or a refusal reason; `{Model}` placeholders filled locally at score time; split train/holdout by a hash of the text; scored by converting Ceist's plan to the same structure and pairing conditions one to one.
- Pattern: to score a plan without counts or records, turn it into the target shape (`questions.target_of`) and compare structurally; an extra condition counts as a wrong reading.

## Review rounds
- Round 1: CHANGES. Worker notes were empty (live commands, dry-run and bank counts, memory_ask/HER line). Filled; no code change.
- Round 2: PASS.
