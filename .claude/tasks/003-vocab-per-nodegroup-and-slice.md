---
id: 003
slug: vocab-per-nodegroup-and-slice
status: done
branch: crew/003-vocab-per-nodegroup-and-slice
model: opus
env: laptop
rounds: 1
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
gate: pass
gateSha: 3cc8d39fc4c45261949dc41e6a4d4c65e88e051b
gateAt: 2026-11-05T09:41:32.674Z
---

# One vocabulary per graph, one file per nodegroup, cut down to what a dataset uses

## Goal
A graph's vocabulary is stored as one file per nodegroup, plus a manifest, and built once per graph. `ceist vocab slice` cuts it down to the nodegroups, links and values that a given dataset actually uses. That makes the bundle smaller and leaves fewer wrong fields to match against.

## Why now
Stu, 2026-11-05: "structure the vocab that would allow us to reduce the file in size. So we have a full vocab for the entire graph but say only 5 nodegroups are used, we can remove what is not needed for that data set." The demo's Monument graph has **38 nodegroups, of which the data uses 7**; Tale has 27. Mistakes like "county" binding to `creator_name` came from matching fields the dataset never fills.

## Approach
1. **The layout.** `vocab/<Model>/<nodegroup alias>.json` holds the entries for that nodegroup's nodes. Its future `group` block comes in 005; reserve the key. Add `vocab/manifest.json` with the format, models, and for each nodegroup its id, alias, parent and a hash of its description, so a stale group is detected (extend `ceist vocab check`).
   - `assemble` reads the old one-file-per-model layout and the new one.
   - Add `ceist vocab split` to convert the old layout to the new one. Use the graphs to map each node to its nodegroup, and convert `bench/her/vocab` with it, keeping the old files until the gate passes on both.
2. **`ceist vocab slice <bundle-or-vocab> --data <business_data dir> --graphs <dir> -o <out>`.** Read the business data **locally** (it never goes to an LLM), through Alizarin where it can, and count tiles per nodegroup. Keep:
   - nodegroups with tiles, plus their ancestors;
   - links whose target model has records;
   - controlled values that occur in the data, plus their ancestors, so hierarchy matching ("listed" covers "Grade II") still works.

   Report before and after sizes, and what was dropped.
3. Record the sliced-away groups in the bundle, so a refusal can say "this dataset holds no construction phases" rather than "couldn't place".
4. Update `docs/tasks/ceist-vocab-pipeline.md` with the layout and slicing.

## Out of scope
The LLM build (004) and group grounding (005).

## Definition of done
- [ ] On the demo (`/home/stuart/git/personal/starches-demo/ask/data` and the HER-derived bundle that `ask.py` builds), the sliced bundle answers every demo question identically. Sizes before and after are in Worker notes.
- [ ] On HER, assembling from the split layout gives an identical bundle (and identical gate numbers) to the old layout.
- [ ] Tests for split, slice (groups, links, values with ancestors kept) and stale-group detection.
## Definition of done (common)
- [ ] The gate (`crew.config.json` `verify`) passes; test counts before and after are in Worker notes.
- [ ] The HER questions (`packages/ceist/bench/her/cases.json`) run through `interpret` before and after. The table of changed answers is in Worker notes, with every change justified. If you can't get the HER graphs locally, say so.
- [ ] The Friday demo questions in `/home/stuart/git/personal/starches-demo/ask/README.md` run with `PYTHONPATH=<worktree>/packages/ceist/src` and give the same answers, or each difference is explained.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, no servers left running, never `git add -A` or `git stash`.

## Worker notes

**What changed**
- `ceist/bundle.py`: `nodegroups()` (graph → groups by alias, node → group), `group_hash`, `read_vocab` (either layout; manifest.json present → split one, with a warning per ignored old file), `split`, `manifest`, `stale_groups`. `assemble` orders a model's entries by nodegroup so both layouts give the same bundle. `save` untouched.
- `ceist/arches_describe.py`: each node gets `nodegroup` (alias); each description a `nodegroups` table `{alias: {id, parent}}`.
- `ceist/arches.py`: `read_resources()` factored out of `from_data_dir`, reused by slicing.
- `ceist/slicing.py` (new): `Usage` (records, tiles per nodegroup, controlled values via Alizarin's RDM when `--reference` is given), `slice_bundle`, `slice_vocab`. Cuts recorded under `sliced` {models, groups, links, values}.
- `ceist/cli.py`: `vocab split`, `vocab slice`, `vocab check --vocab --descriptions`.
- `bench/her/vocab`: split in place (408 group files + manifest); the old `<Model>.json` files stay (ask.py and learn/merge read/write them).
- `docs/tasks/ceist-vocab-pipeline.md`: layout and slicing sections.
- Tests: 3 in `test_bundle.py` (split → same bundle, refusal without nodegroups, stale groups via CLI), 3 in new `test_slicing.py` (groups + ancestors + links, split-dir slicing, values kept with ancestors). Each slicing rule mutation-checked: removing the ancestor walk, the descendants check or the link rule fails a test.

**Where the spec bent**
- Split maps nodes to nodegroups from the descriptions, which `describe` now fills from the graphs; the manifest hash is over the group's described nodes, so the descriptions are needed anyway.
- `slice` takes an extra `--reference <reference_data dir>`: without the RDM, values can't be resolved, so qualified entries are kept and the report says "values not checked".
- Link rule: a link whose configured target graph isn't among `--graphs` is kept (open to any target, as `ArchesVocabulary.relations()` reads it). The demo's Monument `named_location` points at HER's Place graphid, not the demo Site graph; the literal rule would have dropped the county link phrasings.
- Step 3: the cuts are recorded (bundle `sliced`, or the sliced manifest). Nothing reads them yet; the refusal wording is left for 005.
- `learn.merge` still writes the old layout. While both coexist, re-run `split` after a merge.

**Gate**: `crew gate` passed, stamped on 3cc8d39, run with `PYTEST_ADDOPTS` deselecting the two known `tests/test_planner.py::test_did_you_mean_*` failures (owned by 001; without that, verify fails on the base too). Root: 479 passed, 26 skipped, 3 deselected (2 + the configured search one). Ceist: 147 → 153 passed.

**HER (arches-her dev/2.0.x cloned locally)**: the bundle assembled from the split layout is byte-identical to the one from the old layout. Against the base bundle it has the same models, nodes and entries; only the entry order differs (now by nodegroup). `ceist eval`: exact+vectors config 67/102 right, 2 dangerous, before and after (wordllama isn't installed in `.venv-ceist`, so vectors were off); bge config 90/102, 2 dangerous, before and after. All 102+18 cases through `interpret` (narrated plan, refusal, suggestions): identical before and after. No answers changed, so there's no changed-answer table.

**Demo** (`starches-demo/ask`, run through `.venv-ceist/bin/python` with `CEIST_HER` = this worktree; the demo's own venv imports main's Ceist, which has no Alizarin): 26 questions (README tables, extras, known gaps). They give identical answers on the base, on this branch, and on this branch with the sliced bundle. Sizes: 145 KB → 17 KB. Entries: Monument 145 → 12, Figure 64 → 17, Tale 65 → 16, Group 47 → 3, Object 105 → 2, Site 40 → 0. Nodegroups kept: Monument 7/38, Tale 5/27, Figure 3/18, Group 2/17, Object 2/37, Site 3/13. Nothing dropped by the link rule; values weren't checked (the demo has no reference data).

**Memory graph**: no planner, grounding or `interpret` code changed, so `memory_ask` is unaffected.

## Graph writes proposed
- Pattern: an Arches link's `config.graphs` can name a graph that isn't loaded (the demo re-used HER's Monument graph, whose `named_location` targets HER Place's graphid). Treat an unknown target as "any", as `ArchesVocabulary.relations()` does, not as "no records".
- Decision: the split vocab layout is selected by `vocab/manifest.json`. Entries are ordered by nodegroup alias in `assemble`, so both layouts give byte-identical bundles.

## Review rounds

- Round 1: PASS. The reviewer reran test_bundle.py and test_slicing.py (11 passed) and accepted the HER and demo evidence. It judged the gate deselect acceptable (001's known failures, and no planner code touched). Two minor notes, not blocking: `split` leaves a model that errors out of the manifest, so `stale_groups` doesn't check it; and `learn.merge` still writes the old layout (documented).
