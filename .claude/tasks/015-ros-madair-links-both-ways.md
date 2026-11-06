---
id: 015
slug: ros-madair-links-both-ways
status: approved
branch: crew/015-ros-madair-links-both-ways
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
---

# Upgrade Rós Madair, pass every model to it, and answer chains and reverse links

## Goal
- **Chains run:** "which tales mention scheduled monuments?" is understood today but fails, because the binding passes Rós Madair one model only.
- **Reverse links run** through Rós Madair's new `OnBacklink`: "which figures are associated with tales in the Ulster Cycle?", "what is related to Navan Fort?", "which tales have figures associated with Conchobar mac Nessa?".
- **Ceist stops refusing "walking … backwards"** where `OnBacklink` can answer.

## Why now
Stu, 2026-11-06: "there is an updated Ros Madair that does reverse linking", and "apply all the fixes we mentioned".

## Background
- **Rós Madair** (Phil's repo, `flaxandteal/ros-madair`): there is a local clone at `/home/stuart/.cache/tmp-ask/ros-madair` (on 0.1.0-alpha.30; tags fetched up to alpha.33).
  - **alpha.31** added `Expr::OnBacklink { path, model, where }`, the typed reverse hop (commit cbcaba0, `crates/ros-madair-query/src/lib.rs`, plus the compiler).
  - **The Python binding is unchanged.** `crates/ros-madair-python/src/lib.rs` `Reader.resolve/count(ir_json, graph, manifest_json=None)` call `resolve_ids` with one graph. Meanwhile `ros-madair-duck` `DuckReader::resolve_ids_linked(query, graph, linked, registry)` (around `crates/ros-madair-duck/src/lib.rs:832`) already takes the other models. Without them, the compiler fails: "on-link target model … not available to the compiler".
- **The binding change:**
  - Add an optional `linked: list[Graph]` to `resolve` and `count`. Is there a count equivalent of `resolve_ids_linked`? If not, add the smallest one.
  - Make it in a **local branch** of that clone (`ceist-linked`), based on the latest tag. **Never push.** Put the diff in Worker notes so Stu can offer it to Phil.
  - Build the wheel with maturin (`uvx maturin build --release` in `crates/ros-madair-python`).
  - Install it into this worktree's `.venv-ceist` only. Report the wheel path. The orchestrator installs it into the demo venv.
  - The emitter: does the snapshot format change between alpha.30 and alpha.33? If so, rebuild the emitter and note that the demo snapshot needs re-emitting. Give the command.
- **Ceist** (`packages/ceist/src/ceist/rosmadair.py`):
  - pass the other models' graphs (`vocab.model(t).doc`) as `linked` wherever a query has `on_link` or the new `on_backlink`;
  - compile reverse links (`LinkTo` with `direction != "out"`) to `on_backlink` instead of refusing;
  - keep `linked_from` (the tile-read fallback) only where it still adds something, and say which in Worker notes.
- **Demo app:** `starches-demo/ask/ask.py` `_answer` builds `ros_madair.Graph(...)` for the plan's type only. In Worker notes, give the exact patch for the orchestrator (do not edit the demo).

## Definition of done
- [ ] End-to-end tests (the Rós Madair emitter suite): a chain and a reverse link each return the right ids.
- [ ] In the question bank, the chain and backlink questions now answer. Check two counts by hand against `starches-demo/prebuild/business_data/*.json`, and update with `--write`.
- [ ] The binding diff, the wheel path, and any emitter or snapshot steps are in Worker notes.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
