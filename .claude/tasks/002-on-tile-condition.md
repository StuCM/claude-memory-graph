---
id: 002
slug: on-tile-condition
status: approved
branch: crew/002-on-tile-condition
model: opus
env: laptop
rounds: 0
depends: [001]
files:
  - packages/ceist/
  - docs/tasks/ceist-group-grounding.md
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

## Review rounds
