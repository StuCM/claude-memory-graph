---
id: 016
slug: record-attribute-questions
status: done
branch: crew/016-record-attribute-questions
model: opus
env: laptop
work: tier1-fixes
depends: [014]
files:
  - packages/ceist/
gate: pass
gateSha: 862a61c617fe776872b7a0b4a7d950e3ef048bdd
gateAt: 2026-11-06T17:01:31.548Z
rounds: 1
---

# Answer a question about one named record's field

## Goal
"what period is Navan Fort?" and "what type of monument is Navan Fort?" answer with that record's values: "Navan Fort, Navan: cultural period Iron Age, Prehistoric…".
- The plan is a new shape: one named record plus one or more fields.
- It narrates as "Show the cultural period of Monument 'Navan Fort, Navan'".
- It reads back exactly. Its values come from the record's own tiles (`reader.resource_tiles(id)`, as `linked_from` already reads them).

A field the record leaves empty says so ("no cultural period recorded"). A field word that matches several fields asks "did you mean".

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned". 014 makes these refuse; this makes them answer.

## Background
- `plan.py` (Plan and Interpretation), `narrate.py`, `readback.py` and `rosmadair.py` (`linked_from` reads tiles).
- **Concept values come back as ids.** Label them through the vocabulary's value labels. A resource link value shows the linked record's name.
- **Demo app:** give the `ask.py` patch for the orchestrator. The response needs a field/value list instead of `results`.

## Definition of done
- [ ] Unit tests: the field question answers, an empty field says so, an ambiguous field word gives "did you mean".
- [ ] In the question bank, the two Navan Fort questions answer. Check them by hand against the record in `monument.json`. Set their `expect` to `answer` with a note, and `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- `plan.py`: new `Detail(entity, fields)` on `Interpretation.detail`, from `_detail`. It is only tried where the question would otherwise refuse. (a) The grounding's `field_of` link reaches a named record and the anchor's model has a field with that link's alias ("what period is Navan Fort?", "what is the cultural period of Navan Fort?"). (b) Words nothing placed, beside the record's own type, are exactly one field's name ("what type of monument is Navan Fort?", "what monument type is Navan Fort?"). If the words are part of several field names, it refuses with "did you mean" (the 6 shortest labels, and the total). A vocabulary without `fields()` (the memory graph) never gets a Detail.
- `ground.py`: `_check_anchors` no longer refuses the 014 case. It sets `Grounding.field_of` and `plan.py` settles it. Where the anchor's model has no such field, it still refuses ("…itself, which isn't a field a Site has"), as it does when the question says more than which field.
- `arches.py`: `fields(type)` gives (alias, lowercased node name) for every non-semantic node.
- `narrate.py`: a Detail narrates as "Show the cultural period of Monument 'Navan Fort, Navan'." In canonical form it uses aliases, sorted.
- `rosmadair.py`: `compile_detail` gives {"record", "nodes": [nodeid]}. `read_back_detail` turns that back into a Detail, which `check()` compares as usual. `read_detail` reads `reader.resource_tiles`, labelling concepts and references through the vocabulary and showing links as names, localised strings as text, and anything else as `str`. `detail_lines` gives "Monument 'X': cultural period A, B" or "no cultural period recorded". `ask()` answers it.
- `alizarin.py`: `RecordTiles` serves raw business-data tiles in the `resource_tiles` shape, so `alizarin.ask` answers a Detail too. `pipeline.py` (`planner_run`, `judge_bank`) and `cli.py` narrate a Detail, where before they would have shown "not understood" or None.
- Tests (`test_ceist.py`, `test_arches.py`): a field answers through both routes; a field word that matches several fields gives "did you mean"; an empty field reads "no site recorded"; a link value shows the record's name; and one Rós Madair end-to-end test. All of these fail on the base.
- Checked by hand against `monument.json` (Navan Fort, 968cd1bd…): cultural_period = Neolithic, Prehistoric, Iron Age, Bronze Age; monument_type = Settlement, Ritual Site. These match what the answer shows.
- **Bank (before → after, on the vocab as it was at 16:30):** answer/right 60 → 62, answer/refused 1 → 1, refuse/right 7 → 7, answer-later/refused-should-answer 19 → 17. Exit 0, and `--write` was run then. Both Navan questions are now `expect: answer`, `count: 1` (the response's total is the one record), with a note.
- **The bank can't be rerun cleanly now.** At 16:32:57 the demo's `vocab/` was rewritten, apparently by the live vocab pipeline (`designation_and_protection_assignment.json` and `use_phase.json` are new). Since then the bank shows 14 regressions (raths, cairns, County Antrim mottes and others) on the **base** code too. I checked by running HEAD's src through the unpatched demo. With this branch the same 14 appear, plus the two Navan questions now right, and nothing else changes. Those 14 belong to whoever owns the vocab change, not to 016.
- **The bank needs the demo patch.** Without it, the demo's `_answer` reaches `compile_plan(None)` on a Detail and crashes: AttributeError on the two Navan questions, and on any record-field question in the live demo. **Merge this together with the patch.** I ran the bank through a copy of `ask.py` with HERE pointed at the demo. Patch for `/home/stuart/git/personal/starches-demo/ask/ask.py`:

```diff
--- ask.orig.py	2026-11-06 16:29:30.710443823 +0000
+++ ask.py	2026-11-06 16:29:30.729242287 +0000
@@ -14,7 +14,8 @@
 from ceist.bundle import layered
 from ceist.config import chain, load
 from ceist.readback import check
-from ceist.rosmadair import Unsupported, _scoped_by_model, compile_plan, linked_from, linked_models, read_back
+from ceist.rosmadair import (Unsupported, _scoped_by_model, compile_detail, compile_plan, linked_from, linked_models,
+                             read_back, read_back_detail, read_detail)
 
 HERE = Path(__file__).parent
 SITE = HERE.parent
@@ -58,6 +59,13 @@
     if meaning.direct is not None:
         e = meaning.direct
         return {"understood": f"{e.type} '{e.name}'", "total": 1, "results": [result(e.id, records, vocab)]}
+    if meaning.detail is not None:
+        d = meaning.detail
+        q = compile_detail(d, vocab)
+        if not check(d, read_back_detail(q, vocab)).ok:
+            return {"understood": narrate(d), "refused": "the compiled query reads back differently from the question"}
+        return {"understood": narrate(d), "total": 1, "results": [result(d.entity.id, records, vocab)],
+                "fields": [{"field": f, "values": vs} for f, vs in read_detail(reader, q, vocab)]}
     skipped = []
     for plan, note in [(meaning.plan, "")] + [(r.plan, r.note) for r in meaning.relaxations]:
         try:
```

- HER plans (2.0 and 1.1, at the CI-pinned refs, archived from the local clone into TMPDIR): 125/125 each and no diffs, so nothing was re-pinned.
- memory_ask: `tests/test_planner.py` passes, 33. The memory vocabulary has no `fields()`, so it never gets a Detail. The one visible change is a wording change in a refusal that already happened. A link with unknown targets (no range) whose subject only that link implied, ending at a named record, used to say "…itself; a named record's own details can't be answered yet". It now says "…itself, which isn't a field a <Type> has".
- **Sweep ("what objects have period Navan Fort?"):** this now refuses: "'period' could be Monument 'Navan Fort, Navan''s own cultural period, or a link to it from the Object records asked for; the link can't say what it points at, so it isn't guessed". The rule: a named subject, a link whose targets are unknown, and a named record whose own model has a field with that link's alias. I tried a broader rule first (refuse any named record at an unknown-target end), but it broke `test_a_shared_phrase_binds_the_relation_that_joins_the_anchor`, which binds a legitimate unknown-target link, so I narrowed it. Without that field it still plans as before. Not done: refusing by CIDOC-CRM clash, because these links carry no CRM range here.

## Graph writes proposed
- Pattern: a Ceist answer shape that isn't a Plan (Detail) must be handled by every consumer of `Interpretation`: rosmadair.ask, alizarin.ask, pipeline.planner_run/judge_bank, cli, and the starches-demo ask.py. Otherwise they reach `meaning.plan` = None. Grep `meaning.direct` to find them all.
- Gotcha: the starches-demo question bank depends on the demo's live `vocab/` (and on foundation's `vocabularies/base`). A pipeline run in the middle of a task changes its baseline. Confirm a regression on the base src before blaming the diff.

## Review rounds
- Round 1: PASS. The reviewer did not rerun the bank or HER (it relied on the gate). Minor: `field_of` is also set for links whose source is named, which `_detail` handles. The orchestrator must apply the demo ask.py patch with the merge.
