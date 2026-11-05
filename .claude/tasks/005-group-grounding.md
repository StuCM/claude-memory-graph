---
id: 005
slug: group-grounding
status: approved
branch: crew/005-group-grounding
model: opus
env: laptop
rounds: 0
depends: [002, 003]
files:
  - packages/ceist/
  - docs/tasks/ceist-group-grounding.md
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

## Review rounds
