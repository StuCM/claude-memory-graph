---
id: 011
slug: vocab-layers
status: approved
branch: crew/011-vocab-layers
model: opus
env: laptop
work: vocab-layers
files:
  - packages/ceist/
  - vocabularies/
---

# Vocabularies in two layers: a base per graph, and a client layer on top

## Goal
Ceist loads a vocabulary as a **base layer per graph** plus an optional **client layer**:
- **The base layer** lives in its own place, keyed by graph id: `vocabularies/base/<graph-id>/` at the repo root. It holds what comes from the graph or schema alone: type words, field and link phrasings, nodegroup groups.
- **The client layer** is a folder the site owns, for example `starches-demo/ask/vocab/`. It holds what comes from that client: value-label variants and synonyms, value combos (such as the period combos), record-name aliases, and the client's own phrasings.

Ceist merges the two. The client layer may **add** phrases and entries. Anything that would change or remove a base phrase is listed in a merge report and is never applied silently. The demo then runs on the HER base (re-keyed by graph id) plus a client layer that holds what `ask.py` hard-codes today (`EXTRA_TYPE_WORDS`, `RELATION_FORMS`, `PERIODS`/`GROUPS` combos).

## Why now
Stu, 2026-11-06: "split vocab to what is very much the graph or schema and what is additional vocab based on the data and values. This means we could invest larger time on building the base graph vocab and a smaller time adjusting for client data". On where the base lives: "in its own place keyed by graph id".

## Background
- **Today:**
  - A bundle is per model, `ceist.vocab/2`, written per nodegroup with a `manifest.json` (task 003, `slicing.py`, `bundle.py`).
  - The HER bundle is in `packages/ceist/bench/her/vocab/*.json`, keyed by model *name*.
  - The demo re-keys it to its own model names in `starches-demo/ask/ask.py` `her_bundle()`, because its graphs are the HER graphs renamed (`HER_NAMES`). Keying by graph id makes renames free.
- **The demo graphs keep HER's graph ids?** Check this first: compare `starches-demo/prebuild/graphs/resource_models/*.json` graphids with the HER graphs the bench uses. If they differ, write down the mapping you need and how the demo supplies it, in one place.
- **Keep the existing loaders working.** Today's single bundle and a vocab folder load as before; layering is opt-in.
- **Move the HER bundle's schema-only content into `vocabularies/base/<graph-id>/`.** Keep `bench/her/vocab` as it is (the HER gate depends on it) unless you can point the gate at the new place with no plan diffs.
- **Do not edit `starches-demo`.** In Worker notes, give the exact `ask.py` change for the orchestrator to apply: load the base by graph id plus `ask/vocab/` as the client layer, and drop the hard-coded dicts. Also give the client-layer files themselves, written under `<worktree>/bench-demo-client/` (or a path you choose inside `files:`), for the orchestrator to copy.

## Out of scope
The pipeline (task 012) and the refine loop (013).

## Definition of done
- [ ] Unit tests:
  - a base plus a client layer merge;
  - a client phrase that is added appears;
  - a client entry that would override a base phrase is reported and not applied;
  - loading by graph id finds the base whatever the model is named.
- [ ] With the patched `ask.py` (applied in a temp copy of the demo's `ask/`, not in place), the question bank exits 0 and its counts are unchanged.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
