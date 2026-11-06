---
id: 022
slug: question-generator
status: approved
branch: crew/022-question-generator
model: opus
env: laptop
work: ceist-questions
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
