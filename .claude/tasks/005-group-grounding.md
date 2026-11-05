---
id: 005
slug: group-grounding
status: done
branch: crew/005-group-grounding
model: opus
env: laptop
rounds: 1
depends: [002, 003]
files:
  - packages/ceist/
  - docs/tasks/ceist-group-grounding.md
gate: pass
gateSha: 9d6c52879e0866c66e428bcb77869f144f4e7253
gateAt: 2026-11-05T12:39:04.883Z
---

# Ground phrases to a nodegroup first, then fill its nodes

## Goal
Questions like "monuments damaged in a fire" or "burnt down before 1950" become one `OnTile` condition on the right nodegroup, with its type, cause and date filled from the words. A phrase is accepted only if the group places every content word; otherwise Ceist offers "did you mean" or refuses. These are steps 2–4 of `docs/tasks/ceist-group-grounding.md`.

## Why now
Stu's nodegroup approach (2026-11-05). It builds on `OnTile` (002) and the per-nodegroup vocabulary (003).

## Approach
Follow the design doc §2–§3:
1. **`ceist.vocab/2`.** Add a `group` block in each nodegroup file: phrases, node roles, combos, answers. Migrate today's qualified entries to combos; the 44 skipped qualified date and property entries now load. `validate` checks every node, value and role.
2. **The grounder.** Each leftover chunk is a group candidate:
   - match it to groups (exact, then vectors over the whole chunk), restricted to the subject's model, keeping the top 2–3;
   - fill each candidate's nodes from the remaining words, taking values from that node's own list only;
   - apply the absorb gate;
   - a date or anchor in the same clause attaches to that group.
3. **Emit `OnTile`,** and narrate and read it back.
4. **Hand-write group blocks** for the fixture and for the demo's Monument and Tale models, so it's testable before 004 generates them.

## Out of scope
Typed names (§4), chains (§5), and the LLM generation of groups (004 extends to it).

## Definition of done
- [ ] Fixture tests:
  - "listed buildings damaged in a fire" no longer returns every listed building;
  - "burnt down before 1950" becomes `OnTile(phase, [Destruction, Fire, before 1950])` and reads back;
  - Destruction and Fire on different tiles do not match.
- [ ] End-to-end case format (question → expected conditions) extended, as in the design doc's Test section.
## Definition of done (common)
- [ ] The gate (`crew.config.json` `verify`) passes; test counts before and after are in Worker notes.
- [ ] The HER questions (`packages/ceist/bench/her/cases.json`) run through `interpret` before and after. The table of changed answers is in Worker notes, with every change justified. If you can't get the HER graphs locally, say so.
- [ ] The Friday demo questions in `/home/stuart/git/personal/starches-demo/ask/README.md` run with `PYTHONPATH=<worktree>/packages/ceist/src` and give the same answers, or each difference is explained.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, no servers left running, never `git add -A` or `git stash`.

## Worker notes

**Gate counts.** Before (clean `ceist-foundation`): root 501 passed / 34 skipped, Ceist 180 passed.
After: root 509 passed / 36 skipped (2 snapshot tests in `test_groups.py` skip without the emitter),
Ceist 190 passed (+8 group grounding, +1 group blocks in bundles, +1 judge by conditions).

**What changed, per file**
- `bundle.py`: `ceist.vocab/2` (v1 still loads); `groups` per model; split files carry `group`;
  `validate_group` checks nodes on the tile, roles, combo values, `answers`; `built.groups`.
- `vocabulary.py`: `Group` (nodegroup, model, phrase → preset values, fillable fields, date field).
- `arches.py`: group blocks and v1 qualified entries become combos (deduplicated); `_load_groups`
  makes link combos qualified relations (as before) and others `Group`s; `groups()`.
- `ground.py`: exact group phrases (after relations, before values; never over shape words such as
  "how many"); with a matcher, leftover runs against the combos of the named types (not bare group
  names); `_fill_groups` picks the group by named type and fills values (own nodes only, exactly one
  field) and a date (unless another word picked its field) from the clause; leftover clause words are
  held back from the text filter, so they refuse; negators scope over a group.
- `plan.py`: `_attach_groups` → `OnTile(group, [...])`, a lone condition bare.
- `evaluate.py`: combos count as qualified items; planner-only cases skipped. `pipeline.py`:
  `judge_plan` takes `expect.conditions` (node, value, tile); `group_block` keeps a combo's `node`.
- `slicing.py`: group blocks go with their nodegroup; combos cut like qualified entries.
- `learn.py`, `bench/her_compare.py`: skip cases without a phrase. `cli.py`: prints group count.
- `tests/arches_fixture.py`: `write(phases=True)` adds a phase group (type, cause, date) — opt-in,
  because a second Building date makes undated questions ambiguous in every other test.
- `bench/her/vocab/*/*.json`: 181 qualified entries → combos (137 links, 16 dates, 28 properties);
  hand-written blocks for Monument `construction_phases`, `associated_actors`, Heritage Story
  `associated_actors`, `audience_type`. Flat `<Model>.json` files untouched (the demo reads them).
- `bench/her/cases.json`: 5 end-to-end cases (`"source": "e2e"`, `expect.conditions`).

**HER questions** (2.0 at 9f6a113, local clone; 1.1 at 0a21a46, fetched): the 120 reviewed answers
are identical on both. `ceist eval` per-row identical (67/102 locally: no wordllama weights here, so
the CI vectors numbers can't be reproduced). The re-pin only adds the five new cases:

| question | before (base code) | after |
|---|---|---|
| Which monuments were demolished before 1900? | refused: date could be any of 27 fields | one construction phases tile: Destruction, start date before 1900 |
| Which monuments were restored after 1950? | refused (same) | one tile: Repairs, after 1950 |
| Which monuments were altered in the 1960s? | refused (same) | one tile: Alteration, in the 1960s |
| Which monuments were destroyed by fire? | refused | refused: 'fire' is only a broad/HLC type; HER records no cause |
| Which heritage stories are for children? | audience type is Children | same (the combo collapses to one value) |

planner_run on the five: 4 right, 1 refused correctly.

**Demo check** (worktree `.venv-ceist`, `CEIST_HER` = worktree `bench/her`): all 22 README questions
give the same answers as the base code. Some differ from the README table (e.g. "feature" now reads
as `actor`, counties as `named location`); base does the same, so that predates this task.

**Demo data and tile questions** (scratch run with the HER group blocks re-keyed onto the demo):
none can be answered. Monument fills 7/38 nodegroups and no construction phase or actor tile; Tale's
26 `associated_actors` tiles hold only `actor`, no `role_type`. And `ask/data` has no
`vocabularies/`, so no value loads and every combo is skipped. The next step needs reference data
in `ask/data` and tiles with two filled nodes. Recorded in the design doc.

**Memory graph:** its vocabulary has no `groups()`, so grounding is unchanged; `tests/test_planner.py` passes.

**Spec notes.** The design's §2 combo has no `node`; it is needed to tell a link combo (a
qualified relation) from a value/date combo, so combos keep an optional `node` (004's reply
already requires it; `group_block` now keeps it). A link combo setting more than one value is
skipped with a reason (Relation.qualifier holds one). "by X" into a non-link group's actor node is
not done: neither the fixture nor HER has a group with both an actor and value combos.

## Review rounds

### Round 1 — PASS
crew-reviewer: DoD met (three fixture tests assert real outcomes; the loose plan matching both buildings proves the tile matters); `her.sh` reproduced 125/125 on HER 2.0 and 1.1, pins add only the 5 e2e cases; absorb gate refuses rather than drops; nothing from §4/§5/LLM generation. No findings.

## Graph writes proposed
- Decision: a group phrase matched by vectors may only land on a combo (a phrase with preset values), never on a group's bare name — otherwise "demolished" read as "construction phase" keeps the date and silently drops the Destruction type (seen on the demo data, where no values load).
- Decision: a lone condition from a group stands bare, not in `OnTile`: it holds on any tile, and this keeps every existing HER plan unchanged.
- Pattern: a group step must skip spans already consumed by the question's shape ("how many" is an Artefact Quantity combo in HER); `taken` spans don't cover shape words.
- Finding: the starches demo can't show the nodegroup pattern yet — `ask/data` has no `vocabularies/` (no values load, every combo is skipped) and no demo tile fills two group nodes.
