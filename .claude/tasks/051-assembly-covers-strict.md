---
id: 051
slug: assembly-covers-strict
status: approved
branch: crew/051-assembly-covers-strict
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/assembly/
  - packages/ceist/bench/golden/
  - packages/ceist/bench/her/plans-2.0.json
  - packages/ceist/bench/her/plans-1.1.json
  - packages/ceist/STATUS.md
  - claude_memory_graph/planner.py
  - tests/test_planner.py
  - tests/test_amend_telemetry.py
---

# Schema assembly does everything strict mode does, then becomes the default

## Goal
Stu, 2026-11-09, option 2. The TypeScript port will port **only** schema assembly, so assembly must cover everything strict mode does before it becomes the default. 050 found, with assembly as the default, that 4 memory-graph tests and 17 Ceist tests fail (050's Worker notes list them):

1. **The partial match (038)** is never set in assembly mode (9 tests). On a refusal, assembly must offer the same partial match strict does, built from what it grounded.
2. **The memory graph's strict-only behaviours** (`tests/test_planner.py`, `tests/test_amend_telemetry.py`):
   - a relation with no second end is dropped and the type is listed ("Which projects are under active development?");
   - the `statement` label;
   - binding a verb that matches nothing, so the asks report can flag it ("picked" → madeBy).

   Port each into assembly. Where one is only right for free-text vocabularies, gate it on `free_text`, as strict does today.
3. **The "Which airmen flew in the Lancaster?" over-refusal**, caused by 049's County Nowhere safety rule. Narrow the rule so it fixes the Lancaster question and County Nowhere still refuses.
4. **Refusal wording** (6 tests). Make assembly's refusals say the same things strict's do, where the meaning is the same. Where assembly gives a better reason, keep it and update the test, saying why.
5. **Make assembly the default**, with strict still reachable through the switch, for comparison, until the port. Re-pin the 3 HER plans that differ, with each justified in Worker notes. 050 found the current pins for "architects died before 1800" and "Southwark buildings" look wrong. Update STATUS.md §3, §4 and §5a.

## Measure (strict against assembly-as-default; tables in Worker notes)
- the demo bank;
- the reorder set;
- the generated train and hold-out sets;
- HER plans;
- the fresh-graph bench, per set;
- the memory-graph planner tests;
- tractable %;
- time per question.

**0 wrong answers** on the demo bank, the reorder set and the fresh-graph bench, and every must-refuse question still refuses.

## Background
- **Read first:**
  - the Worker notes of 038, 049 and 050;
  - `assemble.py`, `plan.py` (`_finish`, `_partial`) and `claude_memory_graph/planner.py`;
  - the graph Patterns "same-type links need word order for direction" and "Ceist free_text gates widening fallbacks".
- 050 must be merged first. It adds the same-type direction rule and the any-field rule, with strict still the default.
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`). No `claude -p` or live LLM runs.

## Definition of done
- [ ] Every test passes with assembly as the default, in both suites. The golden dump is regenerated, with every change explained.
- [ ] The measurements are in Worker notes; wrong answers are at 0 where listed.
- [ ] The HER plans are re-pinned with justification. STATUS.md is updated.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-051`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
