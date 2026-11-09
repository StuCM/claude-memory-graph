---
id: 049
slug: schema-assembly-prototype
status: approved
branch: crew/049-schema-assembly-prototype
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/assembly/
---

# Prototype: assemble a question from its pieces by the schema, not by sentence shape, and answer only when exactly one reading fits

## Goal
Stu, 2026-11-09: "we are very reliant on this structured question but we can actually pick out the relevant information in ground.py… so that we aren't reliant on a single sentence structure but can have rearranged sentences that we can convert to a query."

The extraction passes already find their pieces anywhere in the sentence. The rigidity is in three places:
- the is-question gate (64 of the 109 refusals on the generated set are fragments, refused before any extraction);
- the rule that every word must be placed;
- positional wiring and the caps.

This is a prototype of PRECISE-style assembly (Popescu, Etzioni and Kautz, 2003: answer only "semantically tractable" questions, where exactly one consistent mapping exists). It sits **behind a switch** (`assembly = "schema"`, off by default), so the default behaviour and 040's golden stay byte for byte unchanged.

1. **Pieces.** From 040's extraction passes, collect the typed pieces, with their positions kept only as hints:
   - type words, wh-words and record names;
   - link phrases (each with its candidate relations);
   - values, dates and "near";
   - negators, and the count and group markers.
2. **Assemble.** Enumerate every reading the schema allows:
   - a subject model;
   - each link phrase bound to a relation whose domain and range fit the pieces it connects (in either direction);
   - each value and date attached to a model that owns that field;
   - every piece used exactly once, and every named record connected to the subject.

   The pieces are few, so a plain bounded search is fine; mark its ceiling with a `ponytail:` comment. Position is only a tie-break hint where the schema allows two subjects (the wh-word's noun, then the first type word). Negation scope stays as it is today.
3. **Decide:**
   - **exactly one reading** → the plan;
   - **several** → refuse, with each reading narrated as a "did you mean";
   - **none** → refuse.

   The question 039 accepted as a wrong reading ("which people are associated with <Monument>") should now find two readings (Monument.actor and Figure.monument_area_or_artefact) and ask. Say whether it does.
4. **Words.**
   - Filler and grammar words ("their", "same", "through", "someone", articles and the like) are ignored, from one small documented list.
   - An unknown content word still refuses, exactly as today. Loosening content words gave 26 wrong answers (STATUS.md §4); this prototype doesn't loosen.
5. **No is-question gate in assembly mode.** A fragment is fine as long as it yields a subject.

## Measure (in Worker notes, as tables: strict against assembly)
- **Demo bank:** every must-refuse question must still refuse; list each change. **0 wrong** is required.
- **Generated train and hold-out sets** (`run_bank.py --set`): right / wrong reading / refused, with the questions that moved in each direction.
- **HER plans:** list every plan that differs in assembly mode, and say whether each is better, worse or the same meaning. Don't re-pin; the default mode is unchanged.
- **Fresh-graph bench** in assembly mode.
- **A reorder set,** `bench/assembly/reorder.json`. Write 30 variants of demo-bank questions that are currently right: clauses moved, fragments ("monuments in Down built before 1900"), and filler added. Write them **from the demo bank only, never from the generated sets**, so the hold-out stays unseen. Score both modes on it.
- **Time per question** in both modes, median and worst.

## Background
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and 040's Worker notes (its passes and the `Scan` state are what you build on).
- The memory-graph Pattern "Ceist link phrases have no direction" is part of why several readings must be found rather than one picked.
- **The demo bank's runner:**
  - run it from `/home/stuart/git/personal/starches-demo/ask` with that directory's `.venv/bin/python` and `PYTHONPATH=<worktree>/packages/ceist/src`;
  - the bank is `bench/demo/run_bank.py`;
  - the generated sets are `~/.cache/ceist-questions-demo/{train,holdout}.json`.
- **Run `ponytail-review`** on your diff before the review round. Follow Stu's code style rules in `~/.claude/CLAUDE.md`.
- **No `claude -p` or live LLM runs.**
- 040 must be merged first.

## Not in this task
- Making assembly the default.
- Fallbacks or mention suggestions (held spec 045).
- TypeScript.

Stu decides from the measurements whether assembly replaces the current wiring. If it does, the held port specs (042 onwards) are rewritten for it.

## Definition of done
- [ ] With the switch off, 040's golden is byte for byte unchanged, HER plans are 125/125, and the demo bank tally is unchanged.
- [ ] Assembly mode is tested: one test each for reorder, fragment, filler word, two readings asking, no reading refusing, and an unknown content word still refusing.
- [ ] The measurements above are in Worker notes, with examples of each kind of change.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-049`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
