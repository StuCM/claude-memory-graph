---
id: 029
slug: ontology-miss-fixes
status: approved
branch: crew/029-ontology-miss-fixes
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
