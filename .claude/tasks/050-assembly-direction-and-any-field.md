---
id: 050
slug: assembly-direction-and-any-field
status: approved
branch: crew/050-assembly-direction-and-any-field
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/assembly/
  - packages/ceist/bench/golden/
  - packages/ceist/STATUS.md
---

# Schema assembly: word order decides same-type link direction; a value in several fields means any of them; then make assembly the default

## Goal
049 measured schema assembly (Worker notes in `.claude/tasks/049-schema-assembly-prototype.md`):
- reordered and fragment questions went from 9 to 28 of 30 right, with 0 wrong;
- but all 10 demo-bank losses, and most of the fresh-graph loss, are links between two records of the same type;
- and strict mode silently picks a value's first field.

Stu, 2026-11-09, chose to adopt assembly with these fixes:

1. **Same-type direction.** When both ends of a link are the same model (Tale parent_story, Figure father, actor between Figures), word order decides which end is which, using the rule strict mode uses today (`_assign_edges`). It applies only there: for links between different types, the schema still decides alone. Then re-measure the 10 demo-bank losses and the two HER plans that now ask ("surveyed by Historic England", "architects died before 1800").
2. **A value in several fields means any of them** (graph Decision "A value in several fields means any of them"). "rath" becomes monument type **or** functional type, and the narration says so ("whose monument type or functional type is rath"). That replaces the silent first-field pick, in **both** modes, so the golden dump changes. Re-dump it deliberately, and in Worker notes list every question whose grounding changed and why.
3. **Make assembly the default** once 1 and 2 hold: no wrong answers on the demo bank, the reorder set or the fresh-graph bench, and every must-refuse question still refusing. Re-pin HER plans deliberately, with each diff justified. Strict mode stays reachable through the switch, for comparison, until the port.
4. **Update STATUS.md §3 and §4** with the new numbers.

## Measure (strict 049 against now), tables in Worker notes
- the demo bank;
- the reorder set;
- the generated train and hold-out sets;
- HER plans;
- the fresh-graph bench (per set, as 049 did);
- tractable %;
- time per question.

## Background
- **Read first:**
  - 049's Worker notes, including its four safety rules;
  - `packages/ceist/src/ceist/assemble.py`;
  - `PORT-AUDIT.md`;
  - the graph Pattern "same-type links need word order for direction".
- 049's runners: `bench/assembly/measure.py`, and `CEIST_ASSEMBLY=schema` for the runners outside these files.
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`). No `claude -p` or live LLM runs.

## Definition of done
- [ ] Tests for the same-type direction (both orders) and for a value held by two fields (narrated as "or").
- [ ] Assembly is the default and the measurements are in Worker notes; wrong answers are at 0 where listed above.
- [ ] The golden dump is regenerated, with every change explained.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-050`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
