---
id: 020
slug: confirmed-overrides
status: done
branch: crew/020-confirmed-overrides
model: opus
env: laptop
work: vocab-layers
depends: [011]
files:
  - packages/ceist/
gate: pass
gateSha: d92a5425682f3c5b0a94e57df3df54855d1e7adb
gateAt: 2026-11-06T19:41:41.727Z
rounds: 1
---

# A client layer can override the base, but only when it says so

## Goal
- **Flagged, as today.** A client entry that would change or remove a base phrase is still left out and listed in the merge report.
- **The client can confirm the override.** The client layer declares the override explicitly, and it is then applied. Example: Monument "features" means `actor` for this client, not the base's `component_type`.
  - A confirmed override is still listed in the report, as "overridden (confirmed): …", so it is never invisible.
  - An unconfirmed one keeps today's "not applied" line.
- **Nodes changed for a client.** A client's graph may rename, remove or retype a node the base knows (same graph lineage, client-edited).
  - A base entry whose node is missing, or whose datatype differs, in the client's graph is dropped and reported ("base phrase X targets node Y, which this client's graph lacks / has as Z").
  - The client layer can map a renamed node (`renamed: {old_alias: new_alias}`, confirmed the same way), so the base phrases follow it.

## Why now
Stu, 2026-11-06: "there could be a chance that nodes are changed for a client so this should be flagged but also have a way to confirm the overwrite".

## Background
- Task 011 added `bundle.layered(graphs, base_dir, client_dir)` with a merge report. The client manifest has `models.<name>.base`, which maps the client's model to the base graph id. Read 011's Worker notes in this file's sibling `011-vocab-layers.md`.
- **The confirmation shape.** Pick the least that is unambiguous. For example, the client manifest gets `models.<name>.overrides: [{node, phrase, was}]`, where `was` names the base meaning being replaced, so a base change later invalidates the confirmation instead of silently carrying it over.
  - If `was` no longer matches the base, report "confirmation is stale" and don't apply it.
- **The demo case:** `packages/ceist/bench/demo/vocab/` shows today's single conflict (Monument 'features'). Don't confirm it in the demo layer unless the bank shows it's needed. Use a test fixture instead.

## Definition of done
- [ ] Unit tests, each failing on the base code:
  - an unconfirmed override is reported and not applied;
  - a confirmed one is applied and reported as confirmed;
  - a stale confirmation (`was` not matching) is reported and not applied;
  - a base entry for a node missing from the client graph is dropped and reported;
  - a confirmed rename carries the base phrases over.
## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.


## Worker notes
- `packages/ceist/src/ceist/bundle.py`: client manifest `models.<name>.overrides: [{phrase, node, was}]` (`node` is the client's meaning, `was` the base's, both as `_said` prints them). A matching one is applied (`_forget` takes the phrase out of the base entries and group blocks) and reported "overridden (confirmed): …". A `was` that no longer matches reports "confirmation is stale (it was X); not applied". `_fit` drops a base entry whose node the client graph lacks, or holds as another kind, and reports it. `renamed: {old: new}` re-points base entries before that check; a rename whose `old` no base entry uses is reported stale.
- `packages/ceist/tests/test_layers.py`: four new tests, each failing on the base code (checked). The unconfirmed case sits inside the confirmed test ('erected' beside confirmed 'put up'); a standalone one can't fail on base, since that behaviour already existed.
- **Spec gap, decided:** "datatype differs" is checked as kind (date/link/property via `kind_of`), as the base stores only `kind`. Group blocks and combos aren't node-checked (the spec says "base entry").
- **017 was wrong about the demo graph:** its Monument graph *has* `county_value` (string), but no Monument holds a value for it, so the missing-node rule doesn't free 'county'. The demo layer confirms it instead: `overrides: [{phrase: county, node: named_location, was: county_value}]`, and 'county', 'counties' are added to Monument `named_location`. 'features' is left unconfirmed (still "not applied").
- On the demo, the new rule also reports 40 base entries dropped for missing nodes, plus Monument 'period' etc. (base kind link, demo `cultural_period` is concept-list → property). The bank isn't affected by any of them.
- **Copy to the demo:** `packages/ceist/bench/demo/vocab/manifest.json` and `packages/ceist/bench/demo/vocab/Monument/named_locations.json` -> `starches-demo/ask/vocab/`.
- **Bank** (a mirror of the demo at /home/stuart/.cache/tmp-020/demo/ask: symlinked data, snapshot, static, a copy of ask.py, the worktree vocab, CEIST_BASE=worktree base, demo venv python): before answer/right 64, answer/refused 1, refuse/right 7, answer-later refused 15. After: answer/right 66, answer/refused 1, refuse/right 7, answer-later refused 13, exit 0. "which county has the most raths?" gives County Down 687 and now expects an answer, count 1. "list scheduled monuments by county" gives six counties, Antrim 530 the most, count 6. Two "county nowhere" refusals changed wording but still refuse.
- **HER plans / memory_ask:** `layered` isn't used by the HER gate or `bench/her_plans.py` (only by pipeline `--layer` and the demo), so there are no plan diffs; `her_plans.py` was not run. No change for `memory_ask`. Gate passes: root 558, ceist 248.

## Graph writes proposed
- Decision: a client vocabulary layer overrides a base phrase only when its manifest confirms it with `{phrase, node, was}`. `was` pins the base meaning, so a later base change makes the confirmation stale instead of carrying it over. A base entry whose node the client graph lacks, or types differently, is dropped and reported.
- Pattern: a node can exist in a client graph and still be empty (demo Monument `county_value`), so the missing-node rule won't free its phrases. Confirm an override instead.

## Review rounds
- Round 1: PASS. Noted, not findings: group blocks aren't node-checked; on the demo, `_fit` drops 40 base entries and Monument 'period', with no bank regression.
