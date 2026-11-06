---
id: 012
slug: pipeline-layer-split
status: approved
branch: crew/012-pipeline-layer-split
model: opus
env: laptop
work: vocab-layers
depends: [011]
files:
  - packages/ceist/
  - vocabularies/
---

# The vocabulary pipeline builds the base and the client layer separately

## Goal
- **`ceist vocab pipeline --layer base`** builds `vocabularies/base/<graph-id>/` from the graphs alone, with heavy effort: Opus, several rounds once 013 exists. It covers type words, field and link phrasings, and groups.
- **`--layer data`** builds a client layer from the client's reference data and masked questions, quickly: value-label variants and synonyms, value combos, and phrasings.

Long lists (for example the 253 monument types, sent today only as `values_count`) go to the LLM in batches of labels in the data layer. Labels only, never record data.

## Why now
Stu, 2026-11-06 (task 011's quote). The data layer is how "forts", "portal tombs" and "court tombs" (refused today, see the question bank) can be matched to real values.

## Background
- `packages/ceist/src/ceist/pipeline.py` (tasks 004/006/010): describe, then CRM roles, then one analysis per nodegroup, then collisions, questions, assemble, gate and coverage. `arches_describe.py` `collection_labels` sends short lists as labels and long ones as a count.
- Seeds stay as today: the LLM extends them and never deletes. A client layer is seeded from the existing hand-tuned extras.
- **Privacy is unchanged:** no record names, tile values or ids. The audit log must show it, so grep the run's `audit.jsonl` for three record names from the demo and report zero hits.
- Live LLM runs need Stu's `claude -p` login, which you don't have. Build and test with `--llm-cmd` stubs and cached replies. Write the exact live commands for Stu into Worker notes. Don't run them.

## Out of scope
The refine loop (013).

## Definition of done
- [ ] Unit tests with a stub LLM:
  - `--layer base` writes only schema-level entries under `vocabularies/base/<graph-id>/`;
  - `--layer data` writes only value and client entries into the given client folder;
  - long lists are batched (labels only).
- [ ] An audit check proves no record data goes out (test plus Worker note).
- [ ] The exact live commands for Stu (both layers, against the demo) are in Worker notes.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
