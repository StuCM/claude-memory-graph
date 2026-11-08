---
id: 038
slug: partial-match-fallback
status: approved
branch: crew/038-partial-match-fallback
model: opus
env: laptop
work: ceist-fallback
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
