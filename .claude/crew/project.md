# Project brief

## Hard constraints

- **Ceist uses no LLM at question time.** An LLM may be used only at build or learn time, offline, and only through the pipeline that inlines what it sends and audits it. A diff that calls a model while answering a question breaks the product.
- **Never guess.** If grounding is unsure, Ceist refuses or offers "did you mean". A change that widens an answer silently, by dropping a word, a negation or an anchor, is a bug even when more tests pass.
- **The read-back must match exactly.** A compiled query that narrates differently from the plan must not run. Don't loosen `ceist.check`.
- **Privacy:** no record data (names, tile values, ids) goes to an LLM. Only the schema description goes at build time, and masked questions at learn time.
- **The memory graph runs on Ceist.** `claude_memory_graph/planner.py` calls `ceist.interpret`, so any planner or grounding change also changes `memory_ask`. Check `tests/test_planner.py` and say what changed for the memory graph.
- **Alizarin is a required dependency** (Stu, 2026-11-05). There is no Linux ARM64 wheel yet, so for now Ceist is used only on x86_64 machines.

## Where a plausible diff does real damage

- `packages/ceist/src/ceist/ground.py` and `plan.py`: grounding order, coverage, refusals and anchors. Small edits change answers across every vocabulary. Run the HER questions (`packages/ceist/bench/her/cases.json`) through `interpret`, not just `ceist eval`, which scores phrase→node only.
- `packages/ceist/src/ceist/rosmadair.py`: Rós Madair has known gaps (see `packages/ceist/ROS-MADAIR.md`). A query must stay scoped to its model, and a negation over a link becomes a subtraction.
- Vocabulary bundles: `bench/her/vocab/*.json` is shared by the HER gate. Demo-only phrasings belong in `/home/stuart/git/personal/starches-demo/ask/ask.py`, not here.

## What this environment cannot prove

- The real HER gate needs a clone of `archesproject/arches-her` (CI does it). Locally it needs network access. If you can't run it, say so; don't claim it.
- Linux ARM64 installs (no Alizarin wheel).

## Baseline

- **The gate** (`crew.config.json` `verify`): the root `uv run pytest` plus the Ceist suite in `.venv-ceist`, with `ros_madair` and the local Rós Madair emitter, so the end-to-end tests run. `prepare` builds `.venv-ceist` once per worktree.
- **Clean `ceist-foundation` scores** (after 001): Ceist 168 passed; root 497 passed. `tests/test_search.py::test_search_finds_a_paraphrase_by_meaning` fails on `main` too (environment) and is deselected. Alizarin is pinned to `2.0.0a141` (ahead of b9, but sorts below it), so after a merge that changes it, refresh `.venv-ceist` with `uv pip install -p .venv-ceist -e './packages/ceist[vectors,onnx,roots]'`. `bench/her_plans.py` with `bench/her/plans-{2.0,1.1}.json` pins every HER plan: an intended change shows up as a diff to review there.
- **Machine load (Stu):** run one heavy suite at a time, set `VITEST_MAX_WORKERS`/`-n` low, and leave no servers running. Use `TMPDIR=/home/stuart/.cache/tmp-<task id>`.
- **Demo check:** `/home/stuart/git/personal/starches-demo/ask` (`uv run python ask.py '<question>'`; quote the question). Its README lists the Friday demo questions, and they must not regress. That venv imports Ceist from the main checkout at `/home/stuart/git/personal/claude-memory-graph`, **not** your worktree. To try your code, put `PYTHONPATH=<worktree>/packages/ceist/src` in front.
