---
id: 018
slug: near
status: done
branch: crew/018-near
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
gate: pass
gateSha: f507437404d84f51f7587da8bb0ea2ff8fbc4ac9
gateAt: 2026-11-06T19:50:20.121Z
rounds: 1
---

# "near" and "within N km" of a named record

## Goal
- "which monuments are near Armagh?" and "which raths are within 5 km of Navan Fort?" answer using the records' geometry.
- "near" has a stated default distance (say 5 km), shown in the narration: "within 5 km of Site '…'". A number with km or miles overrides it.
- The named record's geometry comes from its tiles. If it has none, refuse: "'Armagh' has no location to measure from".

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned".

## Background
- Rós Madair indexes geometry (grid and FlatGeobuf in the snapshot). Look for a spatial predicate in `crates/ros-madair-query` (`/home/stuart/.cache/tmp-ask/ros-madair`). If there is one, compile to it.
- If there isn't, do **not** add one in Rós Madair here. Instead, filter by distance in Ceist over the candidates' geometry, with a `ponytail:` comment naming the cost ceiling, and note the Rós Madair predicate as follow-up work.
- Check whether "Armagh" alone matches County Armagh or the city. Never guess: ask "did you mean" when two records fit.

## Definition of done
- [ ] Unit tests: near with the default, within N km, and a named record with no geometry refusing.
- [ ] In the question bank, the "near Armagh" question answers or gives a clear "did you mean". Check one distance by hand, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- **Rós Madair has a spatial predicate, but no distance one.** `crates/ros-madair-query` has `bbox` (and `grid_box`): geometry bbox overlaps a lng/lat box, a superset. So `Near` compiles to `{"bbox": {"path", …}}` around the named record's geometry widened by N km, and Ceist then keeps only candidates whose geometry is within N km (`geo.keep_within`, with a `ponytail:` comment on the O(candidates × vertices) cost). Follow-up for Phil: a distance predicate (ST_DWithin) in the IR would make this exact in the substrate.
- `geo.py` (new): GeoJSON geometries from a tile value, the widened box, and a flat-projected least distance (points, lines, polygons; inside a polygon = 0). Ceiling, marked: two lines that cross with no vertex near the other read as apart.
- `arches.py`: `geometry_fields(type)` (geojson nodes) and `geometry(id)` (a record's geometries, read once from the vocabulary's resource tiles).
- `ground.py`: `NearGround`. "near" (5 km, `NEAR_KM`) or "within N km|kilometres|miles of", only where the vocabulary has `geometry_fields` (so `memory_ask` never sees it), and never inside a whole record name or a phrase the vocabulary already placed (a bundle's "near" link still wins). The first anchor after the phrase becomes `near.entity` and is taken out of `anchors`/`nodes`, so it isn't a direct answer, a loose link or a stray. A negator can reach it.
- `plan.py`: `Near(entity, km, field, unit)` joins the subject's plan. Refusals: "'X' has no location to measure from", "Person records have no location" (or more than one location field: not guessed), "'not near' isn't supported yet", and no record after the phrase.
- `narrate.py`: "within 5 km of Monument 'Armagh, Armagh'" ("within 2 miles of …" as asked; canonical form is km).
- `rosmadair.py`: `Compiled.near` holds `{"record", "km", "path"}`; read-back turns it back into `Near` only if the query holds exactly the bbox that distance implies, otherwise it's a mismatch. `keep_near(ids, compiled, vocab)` for runners; `ask` uses it (and explains it). The anchor itself is left out of the answer.
- `alizarin.py` measures `Near` directly. It now raises on a condition it doesn't know, where before it silently passed every record through. `arches_search.py` refuses `Near` (`Unsupported`) instead of dropping it.
- **"Armagh" alone** matches only Monument 'Armagh, Armagh' (Armagh city centre, -6.6567, 54.3480). County Armagh's whole name needs "county", and an anchor binds only on a whole name, so no "did you mean" is needed. The narration says which record it measured from.
- **Hand check** (haversine over every Point in demo `monument.json`, independently of `geo.py`): within 5 km of Armagh, Armagh = **161**; within 5 km of Navan Fort = 164; within 2 miles of Navan Fort = 98. The demo gives the same three.
- **Demo `ask.py` patch, needed:** `/home/stuart/.cache/tmp-018/ask-near.patch`. It imports `keep_near` and adds `ids = keep_near(ids, compiled, vocab)` after `ids |= linked_from(...)`. **Merge with the patch.** Without it, the demo answers the bbox superset (184 for near Armagh, not 161), and the bank flags that as wrong.
- **Bank** (patched copy of ask.py, this src): before: answer/right 62, answer/refused 1, refuse/right 7, answer-later/refused 17, 0 wrong. After: answer/right **63**, answer/refused 1, refuse/right 7, answer-later/refused **16**, 0 wrong, exit 0. "which monuments are near Armagh?" is now `expect: answer`, count 161, and `--write` was run.
- Tests (`test_arches.py`, fixture `places=True` in `arches_fixture.py`): default near, within 10 km, within 1 mile, inside a site polygon, three refusals, the bbox compile and read-back (and a wider box caught), and Rós Madair end-to-end (list and count). All fail on the base, where "near"/"within" go unplaced.
- **Rebased onto ceist-foundation after 017** (now f507437). Conflicts in alizarin.py, narrate.py, plan.py, rosmadair.py and test_arches.py, resolved so both features stay:
  - `Compiled` carries both `group`/`values` and `near`.
  - `read_back` adds `Near` and keeps `group`.
  - **Near with a group-by refuses** in `compile_plan`: "counting by site within a distance: group_counts doesn't measure it". `group_counts` has no vocabulary to measure with, so it would otherwise count the bbox superset. There is a new test for this.
- **Demo patch, rebased** onto the live ask.py (016 + 017 applied): `/home/stuart/.cache/tmp-018/ask-near.patch`. It adds `keep_near` to the import and `ids = keep_near(ids, compiled, vocab)` after `ids |= linked_from(...)`.
- **Bank after the rebase** (patched copy): answer/right 65, answer/refused 1, refuse/right 7, answer-later/refused 14, 0 wrong, exit 0. That is the post-017 baseline of 64/1/7/15 plus near Armagh. `--write` left the file unchanged.
- HER plans (2.0 and 1.1, from 016's archives of the CI-pinned refs, with the bundle rebuilt from this branch's vocab): 125/125 each, no diffs, nothing re-pinned.
- **memory_ask:** the memory vocabulary has no `geometry_fields`, so near detection never runs there. `tests/test_planner.py` passes, and the root suite has 557 passed.

## Graph writes proposed
- Decision: "near" means within 5 km (`NEAR_KM`), and the narration always states the distance. In Rós Madair it compiles to a `bbox` superset, and Ceist measures exact distance (`geo.keep_within`) because the IR has no distance predicate. Follow-up: ST_DWithin in Rós Madair.
- Pattern: a runner that resolves `compiled.query` and subtracts `compiled.minus` must also apply `keep_near(ids, compiled, vocab)`. If it doesn't, a near question silently gets the bbox superset. This covers rosmadair.ask and the starches-demo ask.py.

## Review rounds
- Round 1: PASS. Minor note, not blocking: in "near a church in Armagh" the first record named after "near" is what gets measured from, and the narration shows it.
- After the rebase onto 017: no new review round. The only new logic is the near+group-by refusal, which has a test. Gate re-stamped on f507437 (root 563 passed, Ceist 254 passed); HER plans 125/125 on both 2.0 and 1.1.
- Round 2 (after the rebase onto 017/020): PASS, no findings.
