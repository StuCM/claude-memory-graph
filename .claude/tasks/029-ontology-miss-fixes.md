---
id: 029
slug: ontology-miss-fixes
status: done
branch: crew/029-ontology-miss-fixes
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
gate: pass
gateSha: 2f656b335ae5037993ff8c802b97813d6c9b440a
gateAt: 2026-11-08T12:01:45.495Z
rounds: 1
---

# Fix the grammar and bugs that make the ontology layer miss

## Goal
Fix the misses 026's bench found that are grammar or bugs, not missing vocabulary, and show the gain on the bench:
1. **"which {Ms} have {X} as <noun>?"** ("which areas have Taldrith as copyright holder?") isn't parsed: a noun-phrased link after the name. This is the largest refusal group: lingo 4, Catalina 47, HER 44. Parse it as the link the noun names.
2. **Phrases leak across models:** `relations()` merges bundle phrases per alias across models, so a phrase on `record_or_registry` in one model reaches the same alias in another model with different targets ("Registry isn't a Bibliographic Source, which 'part of' points at"). Keep a phrase on the model that owns it.
3. **Non-ASCII type words:** "mātaurangas" tokenises as "taurangas", so every Mātauranga question refuses. Tokenising and plural handling must keep letters with diacritics (Irish fadas too: "Táin", "Cú").
4. **P107 "member(s)" lands on non-membership nodes** (`rar_approved_by_value`, `planning_body`, `crew_member`). Narrow the ontology path, so it only applies where the graph models membership.
5. **"construction date" fits five construction-phase dates** and asks "did you mean". Key it to the P82a begin date when the path says so; otherwise the "did you mean" stays.
6. **A link with no relation:** when a phrase is dropped as ambiguous, the planner still links by any relation (`LinkTo(relation=None)`), giving a wrong reading ("heritage places are part of {Area}"). It must refuse instead.

## Why now
Stu, 2026-11-08: "Let's continue …". These are from 026's Worker notes (the "Why the ontology layer misses" list). They make the richer vocabulary from task 027 pay off.

## Background
- **Read first:** 026's Worker notes and bench (`packages/ceist/bench/ontology/run.py`), and 023's for the ontology layer.
- **The memory graph runs on Ceist.** Check `tests/test_planner.py`, and say what changes for `memory_ask`, especially for item 6 (`relation=None` links are how the memory graph's generic "linked to" questions work. Does it still need them? If it does, keep them behind a vocabulary setting, as 010 did with `free_text`).
- **Task 027 runs in parallel,** building the vocabulary tool in `pipeline.py` and `vocabularies/`. Stay in grounding, planning and `crm.py` path narrowing, and coordinate through rebases.

## Definition of done
- [ ] One unit test per item, each failing on the base code.
- [ ] 026's bench before and after, in Worker notes: right, wrong reading, refused and wrong per set. Wrong readings and wrongs must not rise.
- [ ] The demo question bank exits 0:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
- [ ] HER plans (`bench/her_plans.py`, clone at `/home/stuart/.cache/tmp-003/arches-her`): every diff is justified and re-pinned deliberately.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-029`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` or the vocab pipeline.

## Worker notes

### What changed
- `text.py`, `ground.py`, `plan.py`, `matching.py`: one letter class, `text.ALNUM = [^\W_]` (a letter of any script with its diacritics, or a digit), replaces every `[a-z0-9]` in tokenising and phrase boundaries. "mātaurangas" stays one word, and so do "táin" and "cú". The underscore still splits words, so "memory_ask" tokenises as it did. `dates.py` and the `arches.py` slug are unchanged.
- `ground._assign_edges`: when a relation phrase has nothing after it and the word before it is "as" ("which areas have X as copyright holder?"), X is the target and the node before X is the source (item 1).
- `vocabulary.Relation.form_owners` and `said_as(form)`: `arches.relations()` records each bundle phrase that only some of the models holding an alias are said with. In `ground` a bound edge uses its relation narrowed to those models; this covers the shared-phrase pick, the type-priority sort and the anchors' expected types (item 2). The memory graph builds Relations without it, so nothing changes there.
- `crm._ON_ROOT`: a P107/P107i path applies only when the property hangs off the root. That keeps it to the record's own members, and off a vessel's crew, a consultation's planning body and the `rar_*` approvers (item 4). `vocabularies/` is outside `files:`, so this is done in code, not in phrases.json.
- `plan._detail`: "what … date …" also takes the one date of the record's type that a date form names exactly. "construction date" is a form only on the P82a begin node (the ontology layer puts date forms only on P82a/P82), so it becomes the construction-phase start date. With no exact form, the "did you mean" stays. "what" needs a date word, so "what was it built from?" still refuses (item 5).
- `ground._fit_relations`: a phrase with a content word that names several relations, none of which can join the things named ("part of"), now refuses. Before, it was set aside and the planner made `LinkTo(relation=None)` (item 6). With `free_text` it is still set aside, as before.
- Tests: six in `tests/test_ontology.py`, one per item. All six fail on base src (`git archive` of b0533c6 on PYTHONPATH), each for its intended reason.

### memory_ask
`MemoryVocabulary` has `free_text = True`, so item 6 does not reach it: its generic set-aside phrases ("under", "in") still link loosely and say so. It has no `form_owners`, and its forms are all ASCII. `tests/test_planner.py`: 33 passed.

### 026 bench, ontology mode (right / wrong reading / refused / right refusal / wrong)
| set | before | after |
|---|---|---|
| lingo (24 q) | 18 / 0 / 4 / 2 / 0 | 22 / 0 / 0 / 2 / 0 |
| Catalina (345 → 339 q) | 224 / 2 / 94 / 25 / 0 | 275 / 0 / 39 / 25 / 0 |
| Catalina, independent graphs | 11 / 0 / 32 / 0 / 0 | 21 / 0 / 22 / 0 / 0 |
| HER (277 → 268 q) | 195 / 3 / 53 / 26 / 0 | 234 / 0 / 8 / 26 / 0 |
| HER, ontology + base | 191 / 5 / 55 / 26 / 0 | 230 / 0 / 12 / 26 / 0 |

The question counts fall because the bank is templated from `ontology_entries`, and P107 no longer gives nested nodes a "members" question. No-vocabulary mode also rises (Catalina 11 → 37, HER 15 → 39), from "have X as" with node names. Wrong readings fell to 0 everywhere, and wrong stayed at 0.

**Biggest remaining miss (Catalina 18, HER 4): not one of the six items.** The ontology relation phrase "sources" (P67i E73) grounds inside the type names "archive sources" and "bibliographic sources", because relations are matched before multi-word type nouns. 026 put these under "phrase points at another target type", but the cross-model leak was not their cause. Worth its own task.

### Demo bank
Exit 0 and unchanged: answer/right 69, answer/refused 1, refuse/right 7, answer-later refused 11, 0 wrong.

### HER plans (local clone, 2.0 at 9f6a113 and 1.1 at 0a21a46)
124/125 each. The one diff is the same in both, and both are re-pinned (2f656b3). "Which buildings in Southwark were put up before 1850?": the implicit subject changed from Application Area to Heritage Story. The bundle phrase "which buildings" on `associated_monuments_areas_and_artefacts` is said of only some models. Before, the implicit variable took the alphabetically first model among all of them. Now it comes from the models said with the phrase. Both readings were already wrong for the question ("buildings" ought to be Monument).

### Gate
Passed on 2f656b3. Root: 611 passed, 51 skipped, 1 deselected. Ceist: 307 passed.

### Spec notes
- Items 4 and 5 are in code because `vocabularies/` is outside `files:`. If task 027 can key a date phrase to `… P4 E52 P82a`, item 5 could move into the data.

## Graph writes proposed
- Pattern: an Arches link alias is one Relation that spans models, so any per-model phrase on it leaks to every model holding that alias. Narrow the relation by the form that bound it (`Relation.said_as`), not by alias.
- Decision: P107 membership phrases apply only to the root group (`crm._ON_ROOT`). A P107 nested in an event or a note is a role, not membership.
- Gotcha: 026's "phrase points at another target type" refusals were mostly "sources" (a relation phrase) grounding inside the type name "archive sources", not phrases leaking across models.

## Review rounds
- Round 1: PASS. The reviewer re-ran the Ceist suite and probed item 1 with odd word orders; all refuse or read right. Notes, none blocking: a two-edge "have X as A and Y as B" refuses (safe); in-place `said_as` narrowing could in theory hit one relation bound under two forms; the `_fit_relations` docstring sentence reads awkwardly.
