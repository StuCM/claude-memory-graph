---
id: 020
slug: confirmed-overrides
status: approved
branch: crew/020-confirmed-overrides
model: opus
env: laptop
work: vocab-layers
depends: [011]
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
