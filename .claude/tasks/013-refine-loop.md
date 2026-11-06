---
id: 013
slug: refine-loop
status: approved
branch: crew/013-refine-loop
model: opus
env: laptop
work: vocab-layers
depends: [012]
files:
  - packages/ceist/
---

# The pipeline refines the vocabulary by running Ceist on its own failures

## Goal
`ceist vocab pipeline … --rounds N` (default 0, meaning off) runs a refine loop after the first build.
1. Run the cases (the generated ones plus `--questions`, and the question bank format) through `interpret`, and collect:
   - refusals, with the words Ceist couldn't place;
   - wrong answers;
   - "did you mean" cases where the right field was a suggestion.
2. Send each failure to the LLM **masked** (record names replaced as at learn time), with the vocabulary entries of the candidate fields, and ask for phrase additions or removals.
3. Apply them and re-score. **Keep the round only if right answers go up and wrong answers do not.** Otherwise roll it back and stop.
4. **Hold-out questions** (`--holdout <file>`, for example `bench/demo/questions.json`) are never sent to the LLM. They are scored every round and reported. A round that makes a hold-out question wrong is rolled back.

The report shows each round's scores, what was added, and what was rolled back.

## Why now
Stu, 2026-11-06: "Is it useful during the training that the llm runs ceist to see what is refused and update as it trains?" Yes: today the pipeline scores once and stops.

## Background
- **Scoring exists:** the pipeline's gate (`pipeline.py`), and since 010 it scores qualified phrases honestly.
- **Masking exists** in learn (`learn.py`).
- **Caching exists:** the `cache/` keyed by prompt. A rolled-back round's calls are still cached.
- **Seeds and base phrases are never deleted by the loop;** removals apply only to phrases the loop itself added. With layers (011/012), the loop writes to the layer being built.
- **No live LLM in tests:** a stub `--llm-cmd` whose replies are scripted per round. Write the live command for Stu in Worker notes.

## Definition of done
- [ ] Unit tests with a scripted stub:
  - a round that fixes a refusal is kept;
  - a round that adds a wrong answer is rolled back;
  - a round that breaks a hold-out question is rolled back;
  - hold-out questions never appear in any prompt (assert on the audit).
- [ ] A dry run of `--rounds 2` against the demo with a stub is in Worker notes, with the report section.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
