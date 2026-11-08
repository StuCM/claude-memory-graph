---
id: 024
slug: no-dropped-verbs
status: done
branch: crew/024-no-dropped-verbs
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
gate: pass
gateSha: 6e781a7faf39ac89c791df1d91a98d3b2e717dfa
gateAt: 2026-11-08T10:03:12.400Z
rounds: 1
---

# A content verb is never dropped as filler

## Goal
"when was the Gáe Bulg made?" answers today with the Gáe Bulg record itself, because "made" is treated as a filler word and dropped. The question silently widens from "when was it made" to "show it". Fix it at the source:
- A verb that carries meaning (made, built, found, discovered, written, painted, died, born…) is never in the filler list. Either it grounds (through the vocabulary or the CIDOC-CRM ontology layer from task 023: "made" → the production event's date or actor), or the question refuses with "couldn't place 'made'".
- Sweep for the same failure: find every word the grounder throws away as filler (`ground.py`'s stopword or filler lists, plus anything that `meaning.direct` or `detail` accepts with leftover content words) and check that none of them carries meaning a question could depend on.

## Why now
Found by task 023's worker (2026-11-08): it predates 023, but 023's "when"/"who" handling makes it visible. It breaks the never-guess rule in `.claude/crew/project.md`.

## Background
- Task 023 added the ontology layer (`vocabularies/ontology/cidoc-crm/phrases.json`, `crm.py` paths) and "when was X built?" → the record's date field (a `Detail` answer from task 016). Read 016's and 023's Worker notes.
- `ground.py` coverage: content words must all be placed or the question refuses. Filler words are exempt. That exemption is where the widening comes from.
- The memory graph also runs on Ceist: check `tests/test_planner.py`, and say in Worker notes what changes for `memory_ask` (its questions use verbs like "decided" and "fixed").

## Definition of done
- [ ] Unit tests: "when was X made?" either answers with the production date (if the graph has one through the ontology path) or refuses naming 'made'; it never answers with the bare record. Plus one test per filler word removed by the sweep.
- [ ] Worker notes list every word removed from the filler list and why.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json`. Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Add "when was the Gáe Bulg made?" to the bank with the right expectation, using `--write`. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`, clone at `/home/stuart/.cache/tmp-003/arches-her`): every diff is justified and re-pinned deliberately.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-024`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` or the vocab pipeline.

## Worker notes

### What changed
- `ground.py`: `made`, `make`, `got`, `keep`, `kept` and `currently` are no longer in `FILLER`. A new set, `MEANINGFUL` (`make`, `use`, `get`, `set`, `need`, `want`, `know`, `before`, `after`), adds back to the coverage terms some words that `text.STOP` drops. I left `text.STOP` alone: it is kept in step with hookcore and used for search scoring, where these words are noise. A word in either set now grounds (as a relation, date or value phrase, or through the matcher) or is uncovered, and then the question refuses with "couldn't place '<word>'".
- `plan.py` `interpret`: a direct answer (the bare record) now refuses if the grounding also placed a value, date, group or text filter. Before, "is Navan Fort scheduled?" grounded 'scheduled' as a value and then answered with the record alone. It now says "asks whether Monument 'Navan Fort, Navan' is 'scheduled'; a yes/no question about one record isn't supported yet". This is the "direct accepts leftovers" half of the sweep.
- `plan.py` `_detail`: the words it matches field names against now include `g.uncovered`. Without that, a verb that only `MEANINGFUL` counts left the word set empty, and every field matched it: "'' could be any of 8 fields". `test_a_dropped_verb_beside_a_record_with_fields_is_named` fails without this line.
- `bench/demo/run_bank.py`: an optional `want` on an answer question. If the answer narrates differently from it, the question counts as wrong. A field Detail and the bare record both total 1, so a count alone could not catch a fall back to the record.
- Tests: `test_ceist.py` has one parametrised case per removed or restored word (14 cases) and one yes/no case. `test_ontology.py` has "when was the Clock Tower made?" both ways: with a `P108i E12 P4` "made" phrase it is the production-date Detail, and without one it refuses naming 'made'. It also has the empty-word-set case above. All of these fail on the base code (I ran them against a `git archive` of HEAD~ src). In `test_a_value_only_one_model_holds_implies_that_model`, "what's the raths made of?" still refuses, but it now names 'made' instead of "no queryable subject".

### Words removed from the filler list, and why
- `made`, `make`: making is a production event. In the demo, "when was the Gáe Bulg made?" now answers with Object `from_date`, which is the production date: the base and ontology forms "made", "date made" and "produced" both point at it. That gives "Show the from date of Object 'Gáe Bulg'." The record holds no value, so the field reads empty. Before, the answer was the bare record.
- `got`: acquisition ("when was X got?"). It also covers "what has X got?", which now refuses instead of showing X. In "which objects has Cú Chulainn got?" it also refuses, where it used to give the generic "linked to or from". That is narrower, but it no longer guesses.
- `keep`, `kept`: custody or location ("where is X kept?"). `keep` is also a name word, as in Coney Keep, Coney Island. Because the filler pass ran before anchors, the old list took it out of the name.
- `currently`: time restriction ("currently scheduled" is not "ever scheduled"). Dropping it widened the question.
- Added back from `text.STOP` (MEANINGFUL): `make`, `use`, `get`, `set` ("where is the tale set?"), `need`, `want`, `know` ("who did X know?"), `before`, `after` ("what is after Navan Fort?"). Before, all of these gave the bare record. Date phrases ("built before 1900") still work, because the date span consumes the word.
- Kept as filler, deliberately: `have` (possession is the generic link, "which objects did X have?", by design), `ever` and `exist(s)` (dropping them never widens a question), `been`, the pronouns, `me`, `all`, `every`, `please`, `there` and `about` (shape only; the ABOUT_RE phrasing consumes "know" there itself). The rest of `text.STOP` is function words, prepositions that relation phrases match on the raw text, or `no` (handled as a negator on raw words).

### Checks
- **Bank** (`CEIST_BASE=<worktree>/vocabularies/base`, `PYTHONPATH=<worktree>/packages/ceist/src`). Before: answer/right 68, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 11, 0 wrong. After: answer/right 69 (the new Gáe Bulg question), and the rest unchanged, exit 0. Base src against the new bank entry: `right -> wrong`, so the `want` check catches the regression. `--write` also refreshed a stale refusal text on "which monuments lie within County Down?". Base src gives the same new text, so the change came from earlier vocab, not from this task.
- **HER plans** (2.0 at 9f6a113 and 1.1 at 0a21a46, archived from the local clone, describe + assemble with `bench/her/vocab`): 125/125 each and no diffs, so nothing was re-pinned.
- **Gate**: passed on 6e781a7. Root 602 passed (51 skipped, 1 deselected); Ceist 298 passed.
- **memory_ask**: `tests/test_planner.py` passes (33). The memory vocabulary has `free_text`, so a removed filler word that is the only leftover becomes a text filter instead of vanishing. "what decisions were made recently?" now narrates "Find Decisions mentioning 'made', most recent first". The memory planner then says "(ignored 'made' — it matched nothing)" and lists them as before. A memory whose text does contain "made" would narrow the list. That is visible in the narration, and the fix belongs in the memory vocabulary: "made"/"decided" next to "recently" is the creation date, and recent ordering uses `updatedAt`. That is outside `files:`. "which decisions did we make?" now does the same with 'make'. A memory question that is only a record plus a free-text word ("is pyoxigraph fast?") now refuses as a yes/no question instead of returning the record.

## Graph writes proposed
- Pattern: in Ceist, a word in `ground.FILLER` (or `text.STOP`, which sets the coverage terms) is consumed before anchors and never counts for coverage. Any meaning it carries is dropped silently, and a "<wh> was X <verb>?" question becomes a direct answer with the bare record. Never add a content verb or a time word there. Leave it uncovered so the question refuses.
- Decision (024): a direct answer refuses if the grounding also placed a value, date, group or text filter ("is Navan Fort scheduled?"). Yes/no questions about one record are not supported yet. Showing the record would drop the condition.
- Gotcha: the demo bank scores only by total. A field Detail and the bare record both total 1. Use `want` (the expected narration) on any question where that difference matters.

## Review rounds
- Round 1 (6e781a7): PASS. All DoD items met; the reviewer ran test_ceist.py and test_ontology.py (85 passed). Non-blocking: the memory_ask text-filter change on 'made'/'make' and the yes/no refusal ("is pyoxigraph fast?"). A follow-up task in the memory vocabulary should map "made recently" to the creation date.
