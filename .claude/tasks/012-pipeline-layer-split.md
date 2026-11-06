---
id: 012
slug: pipeline-layer-split
status: done
branch: crew/012-pipeline-layer-split
model: opus
env: laptop
work: vocab-layers
depends: [011]
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: a2ad6ed2b68fecb2a2668e31ff929babd7aa1838
gateAt: 2026-11-06T16:03:19.438Z
rounds: 1
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
- `packages/ceist/src/ceist/pipeline.py`: `run(..., layer=, base=, client=)`. `--layer base`: the existing pipeline, seeded from `<base>/<graph id>/` (a `base-seed.json` in the work dir), refuses `--questions`, defaults `--model opus`, and only when the gate passes merges each group file into `<base>/<graph id>/` (`merge_group`: phrases and combos only grow) with a per-graph manifest. `--layer data` (`run_data`): describe with every list's labels, `value_variants` (each listed field's labels in batches of `BATCH`=100 → anchor-less one-value combos, plus value combos), `field_phrases` (one call per model, only with `--questions`, masked) → `<client>/<Model>/<nodegroup>.json`, merged; default `--model sonnet`; the merge report from `bundle.layered` when `--base` is given; exit 1 if a call failed.
- `arches_describe.py`: optional `small` (overrides SMALL) on `collection_labels`/`describe_graph`/`describe`.
- `cli.py`: `--layer base|data`, `--base`, `--client`.
- `tests/test_pipeline.py`: base layer (graph-id dirs, client untouched, seeds and old combos kept, long list sent as count only, readable through `layered`); failed gate writes no base; data layer (batches of 2, seed sent and kept, only client folder changes, merge report, a bad label rejected, a variant grounds through `interpret`).
- **Spec reading, decided:** "schema-level" for the base = what the pipeline already produces from the graphs plus the package's small lists. The committed HER base holds 181 combos ("designed by" → Architect); dropping combos would regress it. Client data (questions, long-list labels) stays out of the base.
- **Value variants need no loader change:** an anchor-less group combo `{"phrases": ["portal tombs"], "set": {"monument_type": "Portal Tomb"}}` already grounds as that value.
- **Audit check:** unit test asserts the data payload keys are exactly model/about/node/labels/others/seed/questions and no record name, date or id appears in `audit.jsonl`. Stub run on the demo (`--layer data`, 4 masked questions incl. "which monuments are at Navan Fort?", "what stories tell of Cú Chulainn?"): 14 calls, monument_type in 3 batches of ≤100; `grep -c` in audit.jsonl: Navan 0, Emain Macha 0, Chulainn 0; client layer byte-identical with empty replies.
- **Question bank** (demo venv, `CEIST_BASE=<worktree>/vocabularies/base`, PYTHONPATH=worktree src vs HEAD~ src): identical, exit 0: answer/right 60, answer/refused 1, refuse/right 6, refuse/wrong 1, answer-later/wrong 2, answer-later/refused-should-answer 17. questions.json unchanged (no live vocab was built, so nothing fixed yet).
- **HER plans / memory_ask:** no grounding, plan or ArchesVocabulary change; `tests/test_planner.py` passes in the gate. `bench/her_plans.py` not run (needs an arches-her clone). No change for `memory_ask`.
- **Live commands for Stu (not run).** From the worktree (or ceist-foundation after merge), `W=$PWD`.
  Data layer, against the demo (the demo's SKOS file sits in `data/vocabularies/`, so give `--reference` a dir with `concepts/`):
  ```sh
  D=/home/stuart/git/personal/starches-demo/ask; R=$(mktemp -d); mkdir $R/concepts; ln -s $D/data/vocabularies/smr.xml $R/concepts/
  jq -r '.[].q' $W/packages/ceist/bench/demo/questions.json > $R/questions.txt
  .venv-ceist/bin/ceist vocab pipeline $D/data/graphs -o ~/.cache/ceist-data-demo --reference $R \
    --questions $R/questions.txt --layer data --client packages/ceist/bench/demo/vocab --base vocabularies/base --jobs 2
  grep -c -e Navan -e 'Emain Macha' -e Chulainn ~/.cache/ceist-data-demo/audit.jsonl   # expect 0
  ```
  then copy `packages/ceist/bench/demo/vocab` to `starches-demo/ask/vocab`, run the bank, and `--write` it.
  Base layer: it is keyed by HER graph ids, so it builds from arches-her, not the demo's renamed graphs (those would land under new graph-id dirs):
  ```sh
  git clone https://github.com/archesproject/arches-her ~/.cache/arches-her; P=~/.cache/arches-her/arches_her/pkg
  .venv-ceist/bin/ceist vocab pipeline $P/graphs/resource_models -o ~/.cache/ceist-base-her --reference $P/reference_data \
    --layer base --base vocabularies/base --seed packages/ceist/bench/her/vocab --jobs 2
  ```
  Both default to `claude -p` (opus for base, sonnet for data); `--model` overrides.
- Not done: type words from questions in the data layer ("story"/"stories" stay hand-seeded in the client manifest); no gate on the data layer beyond failed calls (cases/eval over the layered bundle would be the next step, with 013).

## Graph writes proposed
- Decision: `ceist vocab pipeline --layer base|data`. Base = the schema pipeline into `vocabularies/base/<graph id>/`, written only on a passing gate and merged (only grows). Data = a client layer of value variants (anchor-less one-value combos), value combos and masked-question phrasings; long lists go as labels in batches of 100.
- Pattern: a value synonym needs no loader hook: a group combo with no `node` and a one-value `set` grounds as that value.

## Review rounds
- Round 1: PASS (conditional on these Worker notes). Minor, not acted on: run_data keeps partial output when a call fails (deliberate: answered batches and seeds stay); a new client manifest entry gets only `graphid` (layered then uses the client's own graph id as the base id).
