---
id: 015
slug: ros-madair-links-both-ways
status: done
branch: crew/015-ros-madair-links-both-ways
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
gate: pass
gateSha: 83e5dcb1b8a622c7c6222d1887a13cff7a04f343
gateAt: 2026-11-06T15:51:50.871Z
rounds: 1
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
- **Binding** (Rós Madair clone, local branch `ceist-linked` = `v0.1.0-alpha.33` + commit 9e4bc78, not pushed): `Reader.resolve` and `Reader.count` take an optional `linked: list[Graph]` and call the existing `DuckReader::resolve_ids_linked` / `count_records_linked` (both already existed; no Rust beyond the binding). Diff for Phil: `/home/stuart/.cache/tmp-015/ros-madair-linked.diff` (`git -C /home/stuart/.cache/tmp-ask/ros-madair diff v0.1.0-alpha.33 ceist-linked`).
- **Wheel:** `/home/stuart/.cache/tmp-ask/ros-madair/target/wheels/ros_madair-0.1.0a33-cp39-abi3-manylinux_2_39_x86_64.whl`, installed only in this worktree's `.venv-ceist`.
- **crew.config.json `prepare` still installs `ros-madair==0.1.0a30`** from PyPI. After merge, a fresh worktree's gate fails the new tests (`linked` kwarg) until prepare installs the wheel above instead; the foundation `.venv-ceist` and the demo venv need it too (`uv pip install -p <venv> <wheel>`).
- **Emitter / snapshot:** alpha.31–33 only add columns to the snapshot (`render_fields`, `descriptor_description` on the resources table). The a33 reader reads a30 snapshots fine (tests and the demo snapshot both pass), so the emitter was **not** rebuilt and the demo snapshot doesn't need re-emitting. If wanted later: `cd /home/stuart/.cache/tmp-ask/ros-madair && cargo build --release -p ros-madair-emit`, then re-emit the demo snapshot with `target/release/ros-madair-emit <data dir> starches-demo/ask/snapshot`.
- `packages/ceist/src/ceist/rosmadair.py`: a reverse `LinkTo` (direction `in`) with a Plan target compiles to `on_backlink`. It still refuses a reverse link from one named record or with a qualifier, because `on_backlink` takes a filter on the other model, not a record id. Read-back maps `on_backlink` to a reverse link. New `linked_models(query)` returns the other models' graph ids; `ask` passes their Graphs as `linked`. `on_backlink` counts as unscoped (the compiler returns `target_resource` with no model filter), so its ids are intersected with the type's ids.
- **`linked_from` kept:** it covers a loose link to one named record ("which site is Navan Fort at?"), and `on_backlink` can't express that because it needs a named path and has no record-id predicate.
- `tests/test_arches.py`: the backwards-refusal test now checks the `on_backlink` IR and read-back. New tests: a refusal from one record; end-to-end reverse link (positive and negated); end-to-end chain Building→Site→Building, which needs `linked` (fails without it) and also checks `count`; the qualified-link equivalence now runs the Site case too. `_resolve` passes `linked`.
- `ROS-MADAIR.md` #3 rewritten (mostly resolved by alpha.31) and README backends row updated.
- **Demo `ask.py` patch** (Graph/linked part only; applies on top of the layered-vocab version): `/home/stuart/.cache/tmp-015/ask-linked.patch`. It imports `linked_models`, adds `def linked(query, vocab): return [ros_madair.Graph(json.dumps(vocab.by_graph[m].doc)) for m in linked_models(query)]`, and passes `linked=linked(query, vocab)` / `linked=linked(m, vocab)` to both `reader.resolve` calls.
- **Question bank** (run through a patched copy of ask.py with the new wheel on PYTHONPATH): before `answer right 58, answer refused 1, refuse right 6, refuse wrong 1, answer-later wrong 2, answer-later refused-should-answer 19`; after `answer right 60, answer refused 1, refuse right 6, refuse wrong 1, answer-later wrong 2, answer-later refused-should-answer 17`, exit 0. The two questions changed to `expect: answer`, with hand counts: Ulster Cycle figures **17** (actor links in tale.json on tales whose parent_story is Ulster Cycle), scheduled-monument chain **0** (the only Tale link on that node points at Object 'Gáe Bulg'). Until the orchestrator installs the wheel and applies the patch, the bank in the demo venv shows these two as regressions.
- **Goal examples not reached:** "what is related to Navan Fort?" and "which tales have figures associated with Conchobar mac Nessa?" are refused at grounding, before Rós Madair. This task doesn't change that.
- **memory_ask / HER plans:** no planner or grounding change; `tests/test_planner.py` passes in the root suite. `her_plans.py` needs the HER clone and wasn't run (plans unaffected: rosmadair only compiles).

## Graph writes proposed
- Pattern: Rós Madair `on_backlink` returns target ids unscoped to the query model (no graph filter in the compile), so a client must intersect with the asked-for type's ids, the same as for `backlink`.
- Decision: hops across models need every named model's Graph passed as `linked` (binding branch `ceist-linked`, offered to Phil); ceist derives them from the IR with `linked_models`.

## Review rounds
- Round 1: PASS. No code defects. It flagged that the Worker notes were empty at review time; they are filled in above.
