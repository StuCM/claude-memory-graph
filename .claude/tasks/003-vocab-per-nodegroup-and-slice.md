---
id: 003
slug: vocab-per-nodegroup-and-slice
status: approved
branch: crew/003-vocab-per-nodegroup-and-slice
model: opus
env: laptop
rounds: 0
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
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

## Review rounds
