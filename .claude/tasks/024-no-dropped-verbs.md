---
id: 024
slug: no-dropped-verbs
status: approved
branch: crew/024-no-dropped-verbs
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
