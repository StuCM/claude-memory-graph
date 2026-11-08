---
id: 043
slug: ts-plan-narrate-readback
status: approved
branch: crew/043-ts-plan-narrate-readback
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
---

# TypeScript plan, narrate and read-back, equal to Python on every golden question

## Goal
Step 4 of the port. Port `plan`, `narrate` and read-back to `packages/ceist-js`, on top of 042's `ground`. Include:
- the refusals and their wording;
- 038's partial match;
- the free-text plan types (`Mention`, `Contains`).

`interpret(vocab, question)` is the public entry point, as in Python.

**Conformance:** for every fixture question, the plan target, narration, read-back verdict, refusal text and partial match must equal Python's.

## Background
- 042 must be merged first.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Every golden question is equal on plan, narration, read-back, refusal and partial. Give the counts in Worker notes.
- [ ] The public API is listed in the package README: what the `interpret` result contains, in one table.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-043`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
