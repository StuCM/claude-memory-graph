---
id: 001
slug: pr38-review-fixes
status: done
branch: crew/001-pr38-review-fixes
model: opus
env: laptop
rounds: 1
files:
  - packages/ceist/
  - claude_memory_graph/planner.py
  - tests/test_planner.py
  - .github/workflows/ci.yml
  - pyproject.toml
  - uv.lock
gate: pass
gateSha: a4974439f16d188c55735bdfcc901ccd350dd8c7
gateAt: 2026-11-05T10:25:27.116Z
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

Rebased onto `ceist-foundation` after task 004 merged (bundle.py `validate`, arches_describe `reference_files`, `pipeline.planner_run` overlapped; resolved by reusing theirs).

**Alizarin.** Pinned `alizarin==2.0.0a141` (2026-10-27). It is b9 plus 16 commits (`git merge-base --is-ancestor v2.0.0-beta.9 v2.0.0-alpha.141`), but PEP 440 sorts a141 *below* b9, so a range like `>=2.0.0a141` would resolve back to b9: hence the exact pin. Every suite runs on it. **No Linux ARM64 wheel**: a141 ships manylinux x86_64, macOS x86_64/arm64, win amd64 and an sdist (ARM64 Linux would need a Rust build from the sdist). `uv lock` also rewrote some unrelated `emscripten` markers (newer uv); no version changes besides alizarin.

**Per file**
- `ground.py`: a value phrase with no content word (`terms_pos` empty: "s", "in") is never matched; a leading imperative ("Find") is the command, its span is taken so no value/relation can claim it.
- `plan.py`: removed the "in"/inch special branch (dead now) and the `coverage_min` knob; a question with no content words at all still refuses ("nothing in it names anything…"), which was the knob's only remaining effect (coverage 0 with no terms).
- `learn.py`: the logged phrase is masked like the question; a capitalised first word that isn't a question/function word is `<Name>`; an anchored record name is masked in any case. `assign` reports non-JSON, a non-array reply, a non-object item and an item with no `candidates`. Docstring now says what isn't caught (an unanchored lowercase name).
- `bundle.py` (`save`/`validate` only): non-JSON / non-object reply, non-list entries, non-object entry, non-string phrases, malformed qualifier, non-string end_node, end_node on a non-date node → errors, not crashes.
- `arches.py`: plain global-RDM-cache loop; `_graph_doc` → `graph_doc` (public; callers in slicing.py, pipeline.py, her_lists.py updated — one-word import changes, may touch task 003's slice code).
- `bench/her_lists.py`: uses `arches_describe.reference_files` + `graph_doc`.
- `bench/her_plans.py` + `bench/her/plans-{2.0,1.1}.json`: planner-level check; reuses `pipeline.planner_run`; each question's narrated plan or "refused", any difference fails. Needs the vectors layer (wordllama) as CI has.
- `ci.yml`: new `her` job, matrix over arches-her `9f6a113f` (dev/2.0.x) and `0a21a468` (dev/1.1.x) via `actions/checkout` by SHA; lists, eval gate (80/3) and planner answers on both; bge gate on 2.0 only (unchanged scope; not measured on 1.1 here).
- `planner.py`: `interpret` calls drop the coverage arg; refusal outcome `uncovered` (unplaced words, coverage ≥ 0.6), counted in vocabulary gaps; `COVERAGE_MIN` kept only to label `low-coverage` logs.
- tests: test_ceist (Fleet toy: "S", "flew in the Lancaster", "Find people with the surname Brunel"; recursion test via `interpret`), test_bundle, test_learn, test_controlled_lists (SKOS altLabels incl. one-letter), test_planner (uncovered outcome); stale `importorskip("alizarin")` removed from test_controlled_lists, test_arches, test_learn.
- README: refusal and value-label rules.

**5a decision: full coverage, knob removed.** After the leftover word becomes a text filter, `coverage < 1` ⇔ `uncovered` is non-empty, so the 60% threshold never changed an answer — on HER 1.1 and 2.0 every one of its refusals (56/57) is also an uncovered refusal; only the message changes, now naming the words with did-you-mean. Option (a) (answer with unplaced words not next to a constraint) widens questions silently, which the project brief forbids.

**did_you_mean tests.** Root cause: local Python is 3.14, where wordllama has no wheel, so `matcher()` is exact-only and offers nothing for "influenced"; CI (3.12) passes. The tests now inject a stand-in meaning layer (`meaning_layer` fixture) so they test the planner's did-you-mean plumbing on every platform; behaviour unchanged.

**Counts.** Root `uv run pytest` (deselect as config): base 486 passed + 2 failed → 497 passed (the 2 fixed, +1 planner test, +8 ceist tests the root run also collects). Ceist suite: base 160 → 168 passed.

**HER through `interpret`** (both clones the orchestrator made, b9→a141 code, Python 3.12 with wordllama; also exact-only on 3.14: same changes). 107 refused before → 106 after on each (the "Find…" question below):

| Question | HER | Before | After | Why |
| --- | --- | --- | --- | --- |
| Which airmen flew in the Lancaster? | both | …and whose dimension measurement unit is inch… | condition gone | "in" is not a content word |
| Which journal did the article appear in? | both | …and whose measurement unit is inch… | condition gone | same |
| What's the place called? | 2.0 | …activity name use type is Statutory… | condition gone | altLabel "S" matched "what's" |
| What's the file called? | 2.0 | …consultation name use type is Statutory… | condition gone | same |
| Is it a named location or an address? | 2.0 | …activity name use type is Alternative | condition gone | altLabel "A" matched the article "a" |
| Is it a PDF or a JPEG? | 2.0 | …activity name use type is Alternative | condition gone | same |
| Find people with the surname Brunel | both | refused: 'find' is a value of …evidence_type | **Find Activities whose actor is any Organization and whose source number type is Surname and mentioning 'brunel'** | see below |

**Spec gap / follow-up: "Find people with the surname Brunel".** The "Find" refusal is gone, but the question now gets the same wrong answer "Which people have the surname Brunel?" already gets on the base: the HER bundle grounds "people" as the `actor` relation, and "surname" as a name-type value. That is a vocabulary problem (tasks 002–005), not grounding; it is recorded as-is in `plans-*.json`, so it will show up as a reviewed diff when the vocabulary fixes it. Flagging because it is a wrong answer where there used to be a (wrongly-reasoned) refusal.

**Demo questions** (`starches-demo/ask`, 27 questions incl. every README one, run with `.venv-ceist` python since the demo venv has no alizarin): identical answers and counts; only "which monuments are in County Nowhere?" changes its refusal text from "grounding coverage 50% below 60%" to "couldn't place 'county', 'nowhere' …". The demo README quotes the old text.

**Not done / outside files:** `docs/tasks/planner-telemetry.md` lists the old outcome set (no `uncovered`); the demo README's County Nowhere message.

### Graph writes proposed
- Pattern: alizarin alpha releases after a beta sort below it under PEP 440 (2.0.0a141 > b9 in content, < in version order); pin exactly, never by range.
- Pattern: a controlled-list label with no content word (SKOS altLabel "S", "A", unit "in") matches letters and function words in every question; ceist drops such phrases at grounding (`terms_pos` empty).
- Decision: ceist requires full coverage (one leftover word may become a text filter); `coverage_min` removed because it never changed an answer once uncovered words refused.
- Gotcha: root venv on Python 3.14 has no wordllama, so memory_ask's matcher is exact-only locally; tests needing the meaning layer must inject one.

## Review rounds

### Round 1 — PASS
Gate stamped on a4974439. Reviewer ran root 497 passed; Ceist 154 passed + 14 skipped (Rós Madair end-to-end skipped in its env; 168 passed here with the emitter). HER bench not rerun by the reviewer (needs the clones). Non-blocking notes, left as is:
- `learn.mask` now masks any capitalised first word that isn't a question/function word, so "Decisions affecting quartz?" logs "<Name> affecting quartz?". Privacy-safe; if learn yield suffers, exempt words the grounding placed (types, relations).
- Stale docs outside `files:`: `docs/tasks/planner-telemetry.md` outcome list, the demo README's County Nowhere message.
- `_graph_doc` → `graph_doc` touches `slicing.py`/`pipeline.py` imports: expect a trivial conflict with task 003.
