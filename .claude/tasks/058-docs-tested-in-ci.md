---
id: 058
slug: docs-tested-in-ci
status: approved
branch: crew/058-docs-tested-in-ci
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/docs/
  - packages/ceist/tests/test_docs.py
  - packages/ceist/tests/arches_fixture.py
  - .github/workflows/ci.yml
---

# The walkthrough docs are tested, so CI fails when the code and the docs disagree

## Goal
Stu, 2026-11-10: "can we add tests that we can run in CI so that we can see when docs become incorrect based on code changes? That way docs always stay in sync."

`packages/ceist/docs/HOW-GROUND-READS.md` explains each reader in `ground/`, with a small example and the weak spots. It was written during Stu's code review, and finished before this task runs.

1. **Executable examples.** Each example in the doc becomes a fenced block that a test runs:

   ````
   ```ceist-example
   question: which tales are part of the Ulster Cycle?
   notes: 'part of' → relation parent_story
   understood: Find Tales whose parent story is Tale 'Ulster Cycle'.
   ```
   ````

   - **The vocabulary must be in the repo,** because CI has no demo, no HER clone and no `~/.cache`. Use (and extend, if needed) `tests/arches_fixture.py` or the toy vocabulary in `test_ceist.py`. Rewrite the examples so they run on it: same point, the fixture's own names. Where a real-demo figure (such as "5 results") makes the point better, keep it as prose, outside a test block, and say it's from the demo.
   - A block can check `notes` (lines that must appear), `understood` (the narration), `refused` (the refusal reason, or part of it) and `pieces` (the kinds found).
   - **Weak spots are examples too:** a block marked `known-gap: <task id>` asserts the current wrong or refused behaviour. When a fix lands, its test fails, which forces the doc to be updated in the same change.
2. **Symbols the doc names must exist.** Every `` `name` `` the doc gives as a function, class or constant in `ground/` (and `assemble.py`, `plan.py`) is checked to exist under that name. A rename that leaves the doc stale fails.
3. **`tests/test_docs.py`** runs both checks over every `.md` file in `packages/ceist/docs/`, so it runs in CI's existing `ceist` job.
4. **Fix CI's install line.** `.github/workflows/ci.yml` still installs `./packages/ceist[vectors,onnx,roots]` in the `ceist` and `her` jobs, but 055 removed the `roots` extra. Drop it.

## Background
- **Read first:**
  - the doc itself;
  - `tests/arches_fixture.py` and `test_ceist.py` (the toy vocabulary);
  - the 040, 049, 051 and 055 Worker notes.
- **Don't edit `ground/` or `assemble.py` to fit the doc.** If the doc and the code disagree, the doc is wrong, unless the example is a `known-gap`; then say so in Worker notes.
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`). No `claude -p` or live LLM runs.
- This runs after 056 and 057 (shared `packages/ceist/tests/`), and after the walkthrough doc is finished and committed.

## Definition of done
- [ ] Every example in `docs/` is a tested block on an in-repo vocabulary, or prose marked as demo figures.
- [ ] The symbol check covers every code name the doc mentions.
- [ ] A deliberate rename of one documented function makes `test_docs.py` fail; show this in Worker notes, then revert.
- [ ] CI's install line no longer names `roots`.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-058`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
