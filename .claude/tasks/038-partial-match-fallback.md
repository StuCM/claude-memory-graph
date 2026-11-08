---
id: 038
slug: partial-match-fallback
status: done
branch: crew/038-partial-match-fallback
model: opus
env: laptop
work: ceist-fallback
files:
  - packages/ceist/
gate: pass
gateSha: 6ea9f3b4a9d24685ecb751c44919b1dfd6939dc7
gateAt: 2026-11-08T18:15:29.662Z
rounds: 1
---

# When Ceist refuses, offer a clearly labelled partial match from what it did understand

## Goal
A refusal is never a dead end. When Ceist refuses a question, it also returns a **partial match**: a structured query built only from what it grounded confidently, plus the words it couldn't use, so a site can show *"Showing People linked to Tuatha Dé Danann. We couldn't use 'folk', 'somehow'."*

1. **`Interpretation.partial`**, on every refusal where something grounded:
   - a `Plan` built from the confidently grounded pieces only: the type (or the type implied by the anchor's link), named records as links or anchors, values, places and dates;
   - the unused words, listed;
   - a narration that starts "Partial match:" and names what was left out.
   - It must pass the same read-back check as any plan. It is never returned as `meaning.plan`, and the refusal stays the answer, so never-guess holds: the site shows it as a partial match, not the answer.
2. **What it may drop and what it may not:**
   - it may drop unplaced *content* words;
   - it must **never drop a negation, a number or comparison, a date range, or an "or"**: if the refusal is about one of those, offer no partial match, because dropping it would invert or widen the meaning silently;
   - with nothing grounded, there is no partial match.
3. **Rós Madair:** the partial plan compiles and runs like any plan. The demo's `ask.py` patch (give it in Worker notes; don't edit the demo) returns `{"refused": …, "partial": {"understood", "unused", "total", "results"}}`.
4. **Measure it** on the generated demo questions (`/home/stuart/.cache/ceist-questions-demo/train.json` and `holdout.json`, placeholders filled with `ceist.questions.fill`):
   - how many refusals get a partial match;
   - and, using each question's `target`, how often the partial match is a **subset** of the target reading (the right direction, merely wider) against **off-target** (anything else).
   Off-target partial matches must be rare. Report them all.

## Why now
Stu, 2026-11-08: worried that "a lot of work going in to this only for real world questions getting refused", and "the fall back would be a Ros Madair style search." On the generated demo questions, 109 of 124 should-answer questions are refused; most still recognise a record, a type or a value.

## Background
- **Grounding output:** `Grounding` (anchors, typed variables, values, relations, coverage, `uncovered`), and refusals in `plan.py` and `ground.py`. 014, 010 and 024 define the refusals that must never be relaxed. Read their Worker notes.
- **The memory graph runs on Ceist:** `memory_ask` should get the same field, but must not *use* it unless asked. Check `tests/test_planner.py`.
- **Scoring:** reuse `ceist.questions.score` / `target_of` for the subset check.
- No `claude -p`, live LLM or vocab pipeline runs. A live convergence test may be using the foundation checkout; work only in your worktree.

## Definition of done
- [ ] Unit tests:
  - a partial match from an anchor plus a type, with an unused word;
  - no partial match when the refusal is about a negation, a number, a date or an "or";
  - none when nothing grounded;
  - the partial plan reads back exactly;
  - the narration names the unused words.
- [ ] The measurement on the generated demo set in Worker notes: counts, the subset vs off-target split, and every off-target case.
- [ ] The demo question bank exits 0 (answers unchanged; refusals gain `partial`). HER plans: unchanged, since plans only change on refusal.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-038`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

### What changed
- `plan.py`: new `Partial(plan, unused)` on `Interpretation.partial`. `interpret` now wraps `_interpret` (the old body, unchanged) and calls `_partial` on every refusal except a statement. `meaning.plan` stays None and `refused` stays set.
- `_partial` keeps the subject type the question names, its edges when the grounding wired them (`_build`), and otherwise drops the edges (their forms go to `unused`). A named record that no edge reaches becomes `LinkTo(None, record, "any")`. Values and tile phrases go through the existing `_attach_values`/`_attach_groups`, one at a time; one that won't attach is dropped to `unused`. Dates go through `_attach_dates`; a date that won't attach means no partial. It works on a copy of the grounding, because the attach helpers append to `uncovered`/`notes`.
- It offers **no** partial when: there's no subject; the subject is implicit (only a link implied it); there's an unplaced negation, a group-by or a `near`; a typed variable is left unjoined; a named record of the subject's own type is unjoined (that is the record itself); `unused` is empty; or the question holds any word in `_NEVER_DROP` (negators, "or", comparisons, superlatives, number words, distance, aggregates) or a digit, outside a record name or a placed date phrase.
- `narrate(Partial)` gives "Partial match: Find Buildings linked to or from Site 'Leeds Dock'. Couldn't use 'folk'."
- `questions.py`: `plan_target(plan)`, split out of `target_of`, and `wider(target, got)`: the same model and count, with each condition matching a target condition. A loose link matches any target link to the same model.
- `bench/demo/run_bank.py --set`: prints each partial, classed as subset, off-target or should-refuse, plus the counts.
- Tests: in `test_ceist.py`, an anchor plus a type plus a value with an unused word, the exact narration, the never-drop cases (not, more than two, before 1900, before the war, or, oldest), nothing grounded, and an implicit subject. In `test_arches.py`, the partial plan compiles to Rós Madair and reads back exactly through `check`. I mutation-checked the never-drop list: with it emptied, the "more than two" and "oldest" cases fail.

### Where I went against the spec, and why
- **Spec item 1 allows "the type implied by the anchor's link". I don't.** On the demo set, that change took off-target partials from 9 to 1 on train, and from 3 to 1 on holdout. Across both sets, 8 of the 10 partials whose subject was implicit were wrong. "which people hold copyright on images of Conand?" became "Find Monuments whose actor is Figure 'Conand'". "how many people have an association with Finnbhennach…" became "Count Monuments…". "which people are the father of someone?" became "Find Monuments whose actor is any Figure". In each one the real subject word ("people") was the one left unplaced, so the link's end was a guess. Only 2 of the 10 were subsets. Stu: if you want implicit subjects back, it's one condition in `_partial`.
- **Negation: none at all (`ponytail:` in the code).** A negated value that is placed, with the refusal coming from another word, could be kept as `Not(...)`. I bail on any negator instead, which is simpler and can't go wrong. Upgrade path: let `_scope_negations`' targets through when every one of them is attached.
- The spec says "on every refusal where something grounded". A **statement** refuses before grounding runs, so it never gets a partial. That is the largest gap; see the measurement.

### Measurement (generated demo questions, placeholders filled with `ceist.questions.fill`, `PYTHONPATH=<worktree>/packages/ceist/src`)
`run_bank.py --set`. The base scores are unchanged (train: right 7, refused 83, wrong reading 5, right refusal 15; holdout: right 2, refused 26, wrong reading 1, right refusal 5).

| | should-answer refused | with a partial | subset | off-target | partial on a should-refuse |
| --- | --- | --- | --- | --- | --- |
| train | 83 | 6 | 5 | 1 | 1 |
| holdout | 26 | 4 | 3 | 1 | 0 |
| **total** | **109** | **10** | **8** | **2** | **1** |

**Every off-target case** (both have a Detail target, a record's own fields, so no Plan could match it):
1. "who is associated with Aided Muirchertaig meic Erca, and in what role?" → "Find Figures that are the actor of Tale 'Aided Muirchertaig meic Erca'. Couldn't use 'role'." The target is the Tale's actor and role fields. This partial is the actor half, read from the other side, so it's arguably fine.
2. "who wrote the statement about Rathcroghan and when?" → "Find Figures linked to or from Site 'Rathcroghan'. Couldn't use 'statement', 'wrote', 'who'." The grounding refused ('who' can't join), so the edges were dropped. This one is wrong.

The partial on a should-refuse question was "what happens in the life story of Gann mac Dela?" → "Tales linked to or from Figure 'Gann mac Dela'. Couldn't use 'happens', 'life'."

**Caveats on the subsets.** Two of the 8 ("any places called something with bally in it?", "any tale called something with abbey") score as subset only because a `@name` target has no value. The name match reads 'something', which is a grounding bug in `NAME_RES` ("called X") that already exists, not part of this task. Two are type-only ("which sites are townlands?" → Find Sites; "how many sites are counties?" → Count Sites), which are honest but weak.

**Why so few.** Of the 109 refused, 64 are statement-shaped fragments ("people who turn up in stories"), which never ground. Of the other 45 with no partial, 12 had an implicit subject, 9 had a never-drop word (most, close, around, until 1950, 1920s, last updated 2023), 9 had no subject (mostly "or" and grammar caps), 1 was a negation, and the rest were an anchor of the subject's own type, or nothing unused. An unmerged experiment: grounding statements too (`_partial(v, ground(v, q))`) would add 18 partials, 14 subset and 4 off-target (for example, "sites whose statement mentions the famine" → "Sites whose associated monuments … is any Monument"). That is a decision for Stu, not something to slip in here.

### Demo question bank (questions.json)
Unpatched `ask.py` with this src: exit 0, unchanged (answer/right 71, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 11). The patched copy (below, run from `/home/stuart/.cache/tmp-038/askp` with HERE pointed at the demo): exit 0, the same counts. Of 19 refusals, 6 gain `partial`:
- "how many monuments are in Down?" → "Partial match: Count Monuments. Couldn't use 'down'." → 18508. **Stu, look at this one.** It is the old wrong answer from 010, now labelled. A count partial shows a number for a wider question. To decide: drop count partials, or show them as a list.
- "which tales are about love?" → Find Tales (72); "which monuments are in the townland of Navan?" → Find Monuments (18508). "what is the oldest monument?" gets none ('oldest' is in `_NEVER_DROP`).
- "how many tales does Medb appear in?" → Count Tales linked to or from Figure 'Medb' → 6; "which tales mention Emain Macha?" → … → 0; "which monuments lie within County Down?" → Monuments whose named location is Site 'County Down' → 3586.

### ask.py patch (not applied; demo is read-only)
```diff
--- ask.py
+++ ask.py
@@ -9,7 +9,7 @@
 import ros_madair
-from ceist import interpret, narrate
+from ceist import Interpretation, interpret, narrate
@@ -55,7 +55,14 @@
 def _answer(meaning, vocab, reader, records) -> dict:
     if meaning.statement or meaning.refused:
-        return {"refused": meaning.refused}
+        out = {"refused": meaning.refused}
+        if meaning.partial is not None:
+            # shown as a partial match beside the refusal, which stays the answer
+            p = _answer(Interpretation(meaning.grounding, plan=meaning.partial.plan), vocab, reader, records)
+            if "refused" not in p:
+                out["partial"] = {"understood": narrate(meaning.partial), "unused": meaning.partial.unused,
+                                  "total": p["total"], "results": p["results"]}
+        return out
```
The partial runs through the same compile → `check(read_back)` → resolve path as any plan. When that refuses (read-back mismatch, Unsupported), no `partial` is returned.

### Other checks
- **HER plans**, 2.0 (9f6a113) and 1.1 (0a21a46), archived from local clones into TMPDIR: 125/125 each, no diffs, nothing re-pinned.
- **Gate:** passed on 6ea9f3b. Root: 652 passed, 51 skipped, 1 deselected. Ceist: 348 passed.
- **memory_ask:** `tests/test_planner.py` passes in the gate. `planner.py` never reads `partial`, so its answers are unchanged. Its refusals now carry a `partial` it ignores. `_partial` costs one extra plan build per refusal.

## Graph writes proposed
- Decision (038): a refusal carries `Interpretation.partial` (a Plan from what grounded, plus the unused words), and it is never the answer. There is no partial when the subject is implicit, when the question holds a negator, "or", a comparison, a superlative, a number, a distance or an aggregate, or when it's a statement. Measured on the demo set: 8 subset and 2 off-target out of 109 refusals.
- Pattern: in Ceist, a subject that only a relation's end implied (`Node.implicit`) is wrong most of the time when a content word is unplaced. The unplaced word is usually the real type ("people"). Don't trust it in any fallback.

## Review rounds

- **Round 1: PASS.** Points that don't block, left for Stu: the Rathcroghan off-target partial; count partials showing a number for a wider question (Down → 18508); `wider()` is exercised only through `run_bank.py`, with no unit test of its own.
