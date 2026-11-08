---
id: 040
slug: split-ground
status: approved
branch: crew/040-split-ground
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/ground.py
  - packages/ceist/src/ceist/ground/
  - packages/ceist/src/ceist/matching.py
  - packages/ceist/src/ceist/plan.py
  - packages/ceist/src/ceist/narrate.py
  - packages/ceist/src/ceist/rosmadair.py
  - packages/ceist/src/ceist/vocabulary.py
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
---

# Split ground() into ordered passes, with no change in behaviour, proven by a golden dump

## Goal
Stu, 2026-11-08: "Can we break up ground more if possible to make it easier to understand and fix and optimise." This is the first step of the TypeScript port (`packages/ceist/STATUS.md`). It is done in Python first, so the TypeScript port copies a shape that has already been proven.

1. **The golden dump first.** Add a script of about 40 lines, `bench/golden/dump.py`. It writes the **whole grounding** for every question in:
   - the demo bank;
   - the generated train and hold-out sets;
   - the HER plans questions;
   - the fresh-graph bench questions.

   "Whole grounding" means nodes, edges, values, dates, groups, the notes, the suggestions, the unplaced words, the coverage, `refuse`, and the plan target or refusal. Commit its output from the **unchanged** code. Every later step must reproduce it byte for byte. Later tasks reuse it as the TypeScript conformance fixture.
2. **The safe deletions** from `PORT-AUDIT.md` §1 that are marked safe. Re-verify each by grep before deleting:
   - the unused `context` parameter in matching;
   - `plan.describe`, `DEFAULT_LIMIT` and `to_query`, used by tests only (move what the tests need into the tests);
   - `PLANNED_CHOOSERS`;
   - the dead `consumed.add` at ground.py:577.

   Also merge the duplicated span-overlap, containment and words-in-span checks, and the first-word test that repeats `is_question`. Make `ground._targets` a method on `Relation`, which rosmadair imports. Make narrate's plural use `text.plurals`.
3. **Split `ground()` into passes, within the one file.** Follow PORT-AUDIT.md §2:
   - a plain `Scan` dataclass for the shared state;
   - one plain function per pass;
   - `ground()` as a straight list of pass calls with its early returns.

   The order constraints in §2 each get one line at the call site, saying why that pass comes there. That's the comment that passes the delete-and-be-wrong test. No registry and no base class.
4. **Then split the file** into `ground/` (index, model, scan, phrases, nodes, leftovers, wire, or what §2's layout says), keeping `from ceist.ground import …` working for every current importer:
   - starches-demo's `ask.py`;
   - `claude_memory_graph`;
   - the tests and the bench scripts.

   Run the golden dump after each of steps 2, 3 and 4.

## Not in this task
- The behaviour-changing findings in PORT-AUDIT.md. List any you think are worth it in Worker notes, for a later spec.
- The frozen-vocabulary export, the folder regrouping and any TypeScript.

## Background
- **Read first:**
  - `packages/ceist/PORT-AUDIT.md`, which is the plan;
  - `packages/ceist/STATUS.md`;
  - Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **Run `ponytail-review`** on your diff before opening the review round, and act on what it finds.
- **The demo bank's runner:**
  - run it from `/home/stuart/git/personal/starches-demo/ask` with that directory's `.venv/bin/python` and `PYTHONPATH=<worktree>/packages/ceist/src`;
  - the bank itself is `bench/demo/run_bank.py`;
  - the generated sets are `~/.cache/ceist-questions-demo/{train,holdout}.json`, which are fill-in templates (`questions.fill`).
- **No `claude -p` or live LLM runs.**
- 039 may have merged into ceist-foundation before you start. Rebase on it, and re-dump golden if 039 changed the vocabulary. The golden is taken from the code you start from, whatever that is.

## Definition of done
- [ ] The golden dump is committed and unchanged at the end, byte for byte, after every step. Give its question count in Worker notes.
- [ ] HER plans are 125/125 and the demo bank exits 0 with an unchanged tally. The test suites pass.
- [ ] `ground()` reads as a list of passes. Record its length before and after, and the package's line count before and after, in Worker notes.
- [ ] `ponytail-review` has run, with its findings and what you did about each in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-040`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
