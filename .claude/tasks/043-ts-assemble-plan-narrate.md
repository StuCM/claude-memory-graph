---
id: 043
slug: ts-assemble-plan-narrate
status: draft
branch: crew/043-ts-assemble-plan-narrate
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
---

> Rewritten for schema assembly (2026-11-09). Draft until Stu has reviewed the code after 053 and 055; he approves it then.

# TypeScript schema assembly, plan, narrate and read-back, equal to Python on every fixture

## Goal
Step 4 of the port. On top of 042's `pieces()`, port:
- **assembly** (`assemble.py`):
  - the PRECISE-style matching;
  - word order for direction on same-type links and bare prepositions;
  - "a value in several fields means any of them";
  - the safety rules (049 and 051);
  - the partial match offered only when every refused reading agrees;
  - the statement label, loose listing (free text only) and strict-worded refusals;
  - "did you mean" with each reading narrated;
- **`plan._finish`**, **`narrate`** and **read-back**, including the free-text plan types (`Mention`, `Contains`).

`interpret(vocab, question)` is the public entry point, as in Python, with no mode switch: TypeScript has only assembly.

**Conformance:** for every fixture question, the plan target, narration, read-back verdict, refusal text, "did you mean" readings and partial match must equal Python's in assembly mode.

## Background
- 042 must be merged first.
- Read the graph Patterns "same-type links need word order for direction", "dataclasses.replace shares list fields" (copy every list a reading appends to) and "memory graph needs strict-only planner behaviours".
- **Read first:** `packages/ceist/STATUS.md` (§5a, §5b), `packages/ceist/PORT-AUDIT.md`, and the Worker notes of 040, 049, 050, 051 and the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **Port only schema assembly**, the default since 051. Strict mode's wiring is **not ported**; it stays in Python only for comparison until 047 deletes it.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by 041's fixtures. A behaviour change belongs in its own later task.
- **Credit:** a module that implements a borrowed method (PRECISE in assembly) names the source in one docstring line pointing to `packages/ceist/PRIOR-ART.md`.
- **Run `ponytail-review`** on your diff before the review round, and list its findings and what you did about each in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Every fixture question is equal on plan, narration, read-back, refusal, "did you mean" and partial; counts in Worker notes.
- [ ] The public API is listed in the package README: what the `interpret` result contains, in one table.
- [ ] Time per question in Node (median and worst) on the demo bank, against Python's.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-043`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
