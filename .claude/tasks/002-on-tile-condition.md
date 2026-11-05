---
id: 002
slug: on-tile-condition
status: done
branch: crew/002-on-tile-condition
model: opus
env: laptop
rounds: 1
depends: [001]
files:
  - packages/ceist/
  - docs/tasks/ceist-group-grounding.md
gate: pass
gateSha: 1a072138492a43c71364dfad33eef01068b0c2e7
gateAt: 2026-11-05T11:27:43.740Z
---

# Tile-scoped conditions: `OnTile` in the plan and every compiler

## Goal
A plan can say "all of these hold on one tile of this nodegroup". This is step 1 of `docs/tasks/ceist-group-grounding.md`. Every backend compiles it, the narration and read-back understand it, and `LinkTo.qualifier` moves onto it.

## Why now
Stu, 2026-11-05: "lets build on the plan … a new grouping allowing the nodegroup to have phrases with an ontile class". This is the foundation for 005 (group grounding).

## Background
Read `docs/tasks/ceist-group-grounding.md` in full; it's the design. The PR built none of it.
- **First, settle what "same tile" means for nested nodegroups.** HER phases have child tiles. Check how Rós Madair's `on_tile` treats parent and child tiles: read `/home/stuart/.cache/tmp-ask/ros-madair/crates/ros-madair-compile/src/lib.rs` (`Expr::OnTile`) and write a test on a real snapshot. Do the same for the Arches Search `scope: "TILE"` group (`arches_search.py` around line 126, and `packages/ceist/ARCHES-SEARCH.md`).
- Alizarin evaluation (`alizarin.py` `_walk`) already scopes ancestor values down to children, and keeps siblings apart.
- Record what you find in the design doc. If the backends disagree about child tiles, make the plan's meaning explicit (tile plus ancestors, or tile plus descendants), and make each compiler either honour it or raise `Unsupported` by name.

## Approach
1. Add `OnTile(group: str, conditions: list[Condition])` to `plan.py`, beside `LinkTo`, `HasValue` and the others.
2. Compile it:
   - Rós Madair: `{"on_tile": [...]}` in `rosmadair.py` (around line 95);
   - Arches Search: a `scope: "TILE"` group;
   - Alizarin: per-tile evaluation (generalise `_entry_holds`).
3. Teach `narrate` and `read_back` about `OnTile` ("whose construction phase is Destruction, caused by Fire, after 1950"), and make sure `check` compares it exactly.
4. Make `LinkTo(..., qualifier=HasValue)` produce `OnTile(g, [LinkTo, HasValue])`. Keep `qualifier` as a compatibility shim until every caller has moved.
5. Grounding doesn't produce `OnTile` yet (that's 005), so build plans directly in the tests.

## Out of scope
Group vocabulary and grounding (005), typed names, chains.

## Definition of done
- [ ] Tests:
  - an `OnTile` with two conditions compiles on all three backends and reads back exactly;
  - a record whose two values sit on **different** tiles does not match, on Alizarin and on a real Rós Madair snapshot;
  - the child-tile behaviour is pinned by tests.
- [ ] Today's qualified links (`LinkTo.qualifier`) give identical answers through `OnTile`.
- [ ] The design doc's findings section is updated.
## Definition of done (common)
- [ ] The gate (`crew.config.json` `verify`) passes; test counts before and after are in Worker notes.
- [ ] The HER questions (`packages/ceist/bench/her/cases.json`) run through `interpret` before and after. The table of changed answers is in Worker notes, with every change justified. If you can't get the HER graphs locally, say so.
- [ ] The Friday demo questions in `/home/stuart/git/personal/starches-demo/ask/README.md` run with `PYTHONPATH=<worktree>/packages/ceist/src` and give the same answers, or each difference is explained.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, no servers left running, never `git add -A` or `git stash`.

## Worker notes

**What "same tile" means (findings, also in the design doc).**
- Rós Madair `on_tile` (0.1.0a30) requires every child in one nodegroup. A parent or child nodegroup gives a `CompileError`. This is pinned on a real snapshot.
- Arches Search's TILE scope matches each clause on `tileid = OuterRef("tileid")`, so it sees one tile row. A `NONE` clause becomes resource-level, and child groups are skipped. This comes from reading the code; no instance was run.
- Alizarin already reads a tile together with its ancestors.
- Plan meaning: one tile of `group`, read with its ancestor tiles. Alizarin honours it. Rós Madair and Arches Search honour it only when every condition is on the group's own nodegroup; otherwise they raise `Unsupported` naming the condition (`rosmadair.one_tile`). Arches Search also refuses a negated condition or a sub-plan link inside the entry.
- In HER 2.0 and 1.1, all 137 qualified entries have the link and the value in the same nodegroup.

**Per file**
- `plan.py`: adds `OnTile` and `as_tile`. `_build` emits `OnTile` for a qualified link walked forwards. A qualified link walked backwards keeps the `qualifier` shim, because its tile is on the other record. `_plans` and `_replace` descend into `OnTile`.
- `vocabulary.py`, `ground.py`: `Relation.group` and `Edge.group` carry the link's nodegroup.
- `arches.py`: adds `group_of` and `tile_line`. A qualified entry whose value node isn't on the link's tile or a tile above it is skipped at load (none in HER).
- `alizarin.py`: each entry is tagged with its nodegroup. `_on_tile` evaluates every condition per entry, with value and date tests shared with `_filter`. The backwards shim is evaluated through the same `_entry_holds`.
- `rosmadair.py`: `_expr` is split into `_cond`. `OnTile` compiles to `on_tile` (a `Not` is allowed inside, since it is exact per tile). `Not(OnTile)` at the top level is subtracted, like a negated link. Read-back gives an `OnTile`. Shared helpers `tile_fields` and `one_tile` are added.
- `arches_search.py`: `OnTile` compiles to a TILE group, and `_date_clause` is extracted. Read-back of a TILE group gives an `OnTile`.
- `narrate.py`: "with one <group> entry (whose … and whose …)" / "with no …". Inner parts are sorted in canonical form, so `check` compares entries exactly.
- `pipeline.py`: `_fields` (`judge_plan`) reads inside `OnTile`. Without this, qualified cases would score dangerous. The new test fails on the old code.
- Tests (`test_arches.py`, `test_controlled_lists.py`, `test_pipeline.py`):
  - two-condition `OnTile` on all three backends, with exact read-back;
  - different-tiles exclusion on Alizarin and a real snapshot;
  - a qualified-link shim compared with `OnTile` over 6 questions (incl. negated, multi-condition, hop) on Alizarin and a snapshot;
  - child tiles: parent yes, sibling no, child no on Alizarin; RM/AS `Unsupported`; RM's one-nodegroup rule on a real snapshot;
  - `judge_plan` inside `OnTile`.
- Docs: design doc findings; README section; ROS-MADAIR.md #7; ARCHES-SEARCH.md #2 (concept facets renumbered to #3).

**Gate counts.** Base `ceist-foundation`: Ceist 168 passed; root 497 passed, 26 skipped. After: Ceist 180 passed; root 501 passed, 34 skipped. The root run also collects the new Ceist tests, and the ones that need snapshots skip there. `tests/test_planner.py` is unchanged and passes. The memory graph has no qualified relations, so `memory_ask` is unaffected.

**HER questions through `interpret`.** Run locally with `her_plans.py` on arches-her 9f6a113 (2.0) and 0a21a46 (1.1, fetched). Before: 120/120 for both. After: 118/120. Both changes are narration only; the conditions are the same, and `plans-{2.0,1.1}.json` were re-pinned:

| Question | was | now |
|---|---|---|
| Which architects died before 1800? | whose actor is any Organization (role type: Architect) and … | with one associated actors entry (whose actor is any Organization and whose role type is Architect) and … |
| Which areas were surveyed by Historic England? | whose actor is any Organization (role type: Surveyor) and … | with one associated actors entry (whose actor is any Organization and whose role type is Surveyor) and … |

`planner_run` counts are identical before and after on both versions: right 4, dangerous 10, missed 89, refused 17.

**Friday demo.** The demo venv has no `alizarin`, so `PYTHONPATH=<worktree>` alone fails on import, for the base as well. I ran `ask.py` with the worktree's `.venv-ceist` python and `CEIST_HER=<worktree>/bench/her` instead. All 21 README questions gave byte-identical output before and after; none uses a qualified link.

**Spec notes.**
- The spec says `LinkTo(…, qualifier)` → `OnTile`. That can't hold for a link walked backwards (the tile is on the other record), so the shim stays for that case only.
- `OnTile` narration has no vocabulary, so it uses the group alias ("associated actors entry"), not the friendlier "whose construction phase is Destruction".

## Graph writes proposed
- Decision: `OnTile(group, conds)` means one tile of `group` read with its ancestor tiles. Backends that read one tile row (Rós Madair `on_tile`, Arches Search TILE) refuse a condition on an ancestor tile by name; Alizarin answers it. Rationale: Rós Madair and Arches Search both correlate on exactly one tile row, and Arches meaning flows from parent to child.
- Pattern: Arches Search TILE groups apply a `NONE` clause at resource level ("no tile anywhere"), so a negated condition inside one entry can't be sent as a TILE clause.


## Review rounds
- Round 1 (gate on 1a07213): **PASS**. Minor, non-blocking: Alizarin `_on_tile` raises `TypeError`, not `Unsupported`, for a loose or backwards link inside an `OnTile`; grounding can't produce that today.
