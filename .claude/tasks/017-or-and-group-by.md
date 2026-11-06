---
id: 017
slug: or-and-group-by
status: done
branch: crew/017-or-and-group-by
model: opus
env: laptop
work: tier1-fixes
depends: [014]
files:
  - packages/ceist/
gate: pass
gateSha: af46dc9b9ec2f767e929e9873736bb508e6b3243
gateAt: 2026-11-06T19:24:18.004Z
rounds: 1
---

# "or" between values or places, and counts grouped by a field

## Goal
- **"or":** "which raths or cairns are in County Down?" and "how many monuments are in County Antrim or County Down?" (expected 9,224 = 5,638 + 3,586) answer with an **or** condition.
  - It narrates as "whose monument type is Rath or Cairn".
  - Rós Madair's IR has `any`. Check `crates/ros-madair-query` in `/home/stuart/.cache/tmp-ask/ros-madair`; if it lacks one, compile to a union of two resolves.
- **Group-by:** "which county has the most raths?" and "list scheduled monuments by county" answer with a count per value of a link or list field, sorted.
  - Narrated as "Count Monuments whose monument type is Rath, by named location".
  - "most" or "fewest" takes the top or bottom one, and says so.
  - If Rós Madair can't group, count per value with one resolve per value. Cap the values at 50, and refuse above the cap.

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned".

## Background
- 014 makes "or" refuse first; replace that refusal with real support where the grammar is clear: two values of the same field, or two records for the same link.
- An "or" across different fields ("raths or scheduled") refuses.
- Read-back must stay exact.

## Definition of done
- [ ] Unit tests for both, plus a refusal for a mixed-field "or".
- [ ] In the question bank, the or and group-by questions answer. Check the raths-by-county top value by hand, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- **Opt-in by vocabulary.** `any_of` and `group_by` are class flags (like `free_text`), set on `ArchesVocabulary` only. The memory graph's SPARQL compiler (`claude_memory_graph/planner.py`, outside `files:`) silently skips conditions it doesn't know, so an AnyOf there would widen an answer. Without the flags, grounding is unchanged and a bare "or" still refuses as in 014.
- `ground.py`: "or" between two whole record names of one type becomes one anchor with `Node.either` (`_either_records`). "or" between two values that share a field becomes one `ValueMatch` with `either` (`_either_values`). Any other "or" refuses, naming why: different fields ("'or' joins 'raths' and 'scheduled', which aren't values of one field"), or not between two values or records. `_group_by` takes "… by <link>" at the end of a question, or "which/what <link> has/have (the) most|fewest|least …", out of the edges into `g.group` / `g.group_order`. `_imply_model` lets a value name the subject after "the most".
- `plan.py`: new `AnyOf(conditions)` and `Plan.group = GroupBy(relation, order)`; a group sets `count`, and it refuses if the subject's type doesn't have the link. A "not" over an "or" refuses (`_Refuse`, formerly `_Cycle`), for values and for records. So does an either-anchor with no link, or one under a Detail (016). `_replace` keeps `group`.
- `narrate.py`: "whose monument type is Rath or Cairn", "whose named location is Site 'County Antrim' or Site 'County Down'", and "Count Monuments whose monument type is Rath, by named location[: the one with the most]." In canonical form the alternatives are sorted.
- `rosmadair.py`: AnyOf compiles to the IR's existing `any` (crates/ros-madair-query has `Expr::Any`) and reads back. The IR can't group, so `compile_plan` for a group returns the base query plus `values`. These are the target types' records, or, when the link's targets are unknown, the records the type links to in the business data. Over `GROUP_CAP` = 50 it raises Unsupported. `group_counts(reader, compiled, graph, linked)` runs one resolve per value (base ∧ has_link), subtracts the negated-link queries, and keeps the top or bottom ones with ties (the most never returns zeros), or every non-zero value. `ask` prints `- <record>: n <Type> records`.
- `alizarin.py`: AnyOf is a union; a group refuses ("answered over Rós Madair"). `arches_search.py`: AnyOf and group raise Unsupported. `pipeline._fields` looks inside AnyOf. `__init__` exports AnyOf and GroupBy. The `vocabulary.py` protocol doc covers both flags.
- Tests (`tests/test_arches.py`): compile and read-back for both kinds of "or", and Arches Search refusing it. Refusals for a mixed-field "or" and a "not" over an "or". Group-by narration, values, read-back, and the cap. End-to-end over the snapshot: the "or" cases (also through Alizarin), by site, most, and fewest with a tie. The Toy test for the unflagged "or" refusal still passes.
- **Spec gap, group-by in the bank:** 'county' is a phrase for `county_value` in the HER base. That node isn't in the demo's Monument graph, but `bundle.layered` still won't let the client layer re-point it ("'county' means county_value in the base, named_location in the client; not applied"). So "which county has the most raths?" and "list scheduled monuments by county" still refuse on 'county'. Changing that merge rule (a base phrase whose node the client graph lacks is free to take) is a decision for the orchestrator, and would also move 'features'. The grammar works with the link's own words. Through the demo, "which named location has the most raths?" gives County Down, 687. I checked that by hand against "how many raths are in County Down?" = 687, and Antrim 613 the same way. "how many raths by settlement?" lists the six counties (687/613/612/463/277/249). "list scheduled monuments by named location" lists Antrim 530 … Armagh 150.
- **Demo `ask.py` patch** (needed before any group-by question reaches the demo, or it would list the base records under a "by …" narration): `/home/stuart/.cache/tmp-017/ask-group.patch`. It imports `group_counts` and, after `graph = …`, returns `{"understood", "total": len(groups), "count": True, "groups": [result(...) + count]}` when `compiled.group` is set.
- **Bank** (`run_bank.py` from the real demo's data and vocab, through a patched copy of ask.py): before (ceist-foundation) answer/right 62, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 17. After: answer/right 64, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 15, exit 0. Updated with `--write`: "which raths or cairns are in County Down?" now expects an answer, 735 (687 + 48), and "how many monuments are in County Antrim or County Down?" expects 9,224. The two group-by questions stay answer-later, with a note on why.
- **HER plans** (2.0 and 1.1, local clones, rebuilt bundles): 125/125 each before and after the rebase; no diffs.
- **memory_ask:** unchanged. MemoryVocabulary sets neither flag, so a bare "or" still refuses and there's no group-by. `tests/test_planner.py` passes in the root suite (gate: 554 passed).
- Environment note: during the task the demo's `ask/vocab` was rewritten for a while (16:32, the live pipeline; raths became group phrases), and base code showed 14 bank regressions. It was back to the committed state when I took the final before and after.
- Rebased onto ceist-foundation after 016 merged (conflicts in imports, alizarin.ask and the rosmadair docstring, resolved by hand).

## Graph writes proposed
- Pattern: ceist backends that don't know a Condition type skip it silently (alizarin `_filter` returns hits, memory graph SPARQL ignores it), so a new plan node widens answers until every compiler handles it. Gate it with a vocabulary flag, or add it to each compiler.
- Pattern: in a layered bundle, the client can't re-point a phrase the HER base gives to a node the client's graph lacks ('county' → county_value). Demo phrasings that collide with base phrases are dropped, and the drop shows only in the startup report.
- Decision: Rós Madair's IR has `any` but no group-by measure, so ceist groups with one resolve per linked record, capped at 50 (GROUP_CAP).

## Review rounds
- Round 1: PASS. Open DoD item: the two "by county" bank questions still refuse because the base owns 'county' (a merge-rule decision, see Worker notes). The ask.py patch is needed before group-by reaches the demo. HER plans re-run after the rebase: 125/125 for both 2.0 and 1.1.
