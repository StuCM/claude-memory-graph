---
id: 001
slug: pr38-review-fixes
status: approved
branch: crew/001-pr38-review-fixes
model: opus
env: laptop
rounds: 0
files:
  - packages/ceist/
  - claude_memory_graph/planner.py
  - tests/test_planner.py
  - .github/workflows/ci.yml
  - pyproject.toml
  - uv.lock
---

# Fix the review findings on PR #38 before group grounding builds on it

## Goal
`ceist-foundation` (PR #38 plus this week's demo fixes) no longer adds filters nobody asked for, and handles the words "in" and "Find" correctly. The memory graph's `memory_ask` gets the stricter refusals with an honest outcome. CI gates on planner behaviour, and malformed LLM replies report an error instead of crashing.

## Why now
Stu, 2026-11-05, on the independent review of #38: "1. Alizarin needs to be a dep as it will read arches data. There is a newer version of it I believe in the repo … 2. yes agreed 3. Fix this 4. If we can fix this in the memory graph lets do it as improvements are always good 5. Fix the additional".

## Background
The review report was run over all 120 HER questions on HER 1.x and 2.0. Its evidence is in `/tmp/claude-1000/-home-stuart-git-fat-arches-quartz-starches-starches-next/8d382a9a-c222-45bf-b7c3-0df02ffd80af/scratchpad/exp/` (`r1-main.json`, `r1-br.json`, `r2-br.json`).
1. **Keep Alizarin as a required dependency** (Stu). Check for a newer Alizarin than 2.0.0b9: GitHub `flaxandteal/alizarin` releases, and PyPI `alizarin`. If there is one, move the pin to it (`packages/ceist/pyproject.toml` and `uv.lock`), run everything on it, and record whether it has a Linux ARM64 wheel. **Don't** make it optional.
2. **One-letter controlled-list labels.** HER 2.0's "Name Use Type", "Location Precision" and "Site Survey Condition" have altLabels such as "S" and "A", and these become value phrases:
   - "What's the place called?" → "…name use type is Statutory";
   - "Is it a PDF or a JPEG?" → "…Alternative".

   **Fix:** a value phrase with no content word is never matched. Use the existing `ceist.text.terms`, at `ground.py` around line 253 or in `ArchesVocabulary.values()`, whichever is the single place every value passes through.
3. **"in" and inch.** The special case at `plan.py` around line 243 only half works: "Which airmen flew in the Lancaster?" still adds "dimension measurement unit is inch", and "Find people…" turns into the value Find (evidence type). Fix 2 is the root cause. Then delete the special branch and add tests for both questions.
4. **The memory graph** (Stu: "lets do it"). `claude_memory_graph/planner.py` `handle` (around line 455) now refuses more, and logs those refusals as `"no-subject"`, which skews the asks report (around line 543). Give unplaced-word refusals their own outcome, `"uncovered"`, and report them in the vocabulary-gap counts. Fix the two failing `tests/test_planner.py::test_did_you_mean_*` tests (they fail on the baseline); change the tests only if the new behaviour is better, and say why.
5. **The additional items:**
   - (a) **Coverage threshold.** `plan.py` lines 127–135: `coverage < 1` now means "any unplaced word refuses", so `COVERAGE_MIN` does nothing. Pick one: keep the threshold and refuse only when an unplaced content word sits next to a grounded constraint, or require full coverage and remove the knob. Choose by the HER and demo results, and record why.
   - (b) **CI.** Pin `arches-her` `dev/2.0.x` and 1.x to commit SHAs, and run the gate on both. Add a planner-level check, for example `ceist vocab try` (or a small script) over `cases.json`, that asserts the expected refusals and no conditions nobody asked for.
   - (c) **Masking.** `learn.py` lines 82 and 123 leak more than the docstring claims. Mask the logged `phrase` with the same rules, catch a name at the start of the question and lowercase record names, or narrow the docstring to what's true. Masking is preferred.
   - (d) **Malformed LLM replies.** `bundle.py` around line 206 (`save` given a list) and `learn.py` around lines 285 and 291 (`assign` given a dict, or an item with no `candidates`) crash. Report a clear error instead, and validate `qualifier` and `end_node` at save time.
   - (e) **Smaller items:**
     - the convoluted global RDM cache in `arches.py` lines 97–99;
     - `bench/her_lists.py` duplicates `arches_describe.load_rdm` and imports the private `_graph_doc`: share one helper;
     - `test_controlled_lists.py` has a stale `importorskip`;
     - the recursion test should use `interpret(...)` rather than the private `_build`.

## Out of scope
Group grounding (`OnTile`) and the vocabulary pipeline: those are tasks 002–005.

## Definition of done
- [ ] Tests for: a one-letter label never matching; "flew in the Lancaster"; "Find people with the surname Brunel"; the memory-graph `"uncovered"` outcome; a malformed `save`/`assign` reply; SKOS `altLabel` on controlled lists.
- [ ] Both `test_did_you_mean_*` tests pass, so the gate is green with no deselects beyond the existing `test_search` one.
- [ ] The Alizarin version decision, and whether there's an ARM64 wheel, are in Worker notes.
## Definition of done (common)
- [ ] The gate (`crew.config.json` `verify`) passes; test counts before and after are in Worker notes.
- [ ] The HER questions (`packages/ceist/bench/her/cases.json`) run through `interpret` before and after. The table of changed answers is in Worker notes, with every change justified. If you can't get the HER graphs locally, say so.
- [ ] The Friday demo questions in `/home/stuart/git/personal/starches-demo/ask/README.md` run with `PYTHONPATH=<worktree>/packages/ceist/src` and give the same answers, or each difference is explained.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, no servers left running, never `git add -A` or `git stash`.

## Worker notes

## Review rounds
