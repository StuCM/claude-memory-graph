---
id: 010
slug: never-widen-and-honest-scoring
status: approved
branch: crew/010-never-widen-and-honest-scoring
model: opus
env: laptop
files:
  - packages/ceist/
---

# Never widen, fit links by CIDOC-CRM, and score honestly

## Goal
A generated vocabulary is judged on right answers with zero wrong ones, and Ceist can't produce the wrong ones the live runs showed:
- Ceist refuses instead of turning an unplaced word into a text search or a listing of the whole type.
- Ceist refuses a link whose far end can't be that model.
- The pipeline scorer stops marking right answers as dangerous.

## Why now
Stu, 2026-11-05: "yes … Lets spec this". The live runs on the regenerated demo data, with the full hand-tuned seed, answer 20/26 with both Sonnet and Opus (hand-tuned: 22, one of them wrong). The misses and wrong answers trace to the mechanisms below, not to the vocabulary. Runs to use: `/home/stuart/.cache/tmp-006/{live-noseed,live-seed,full-seed-sonnet,full-seed-opus}/` (each with `report.md`, `cases.json`, `bundle.json`, `cache/`, `demo-compare.md`).

## Background
1. **The scorer.** The report lists "dangerous" rows that show the same node on both sides, for example `"scheduled": expected designation_or_protection_type, got designation_or_protection_type`, and likewise "Bronze Age" and "in state care". These phrases are qualified or combo entries that set a value, and the case carries `expect.conditions`. Find where the phrase-level scorer compares the two and make a matching node plus matching value count as right. Separately, check the planner-level verdicts: "how many monuments are there? → Count Monuments" is marked dangerous but is right. Either fix the case judging or report that the generated case is mislabelled. Don't loosen what counts as dangerous for a genuinely different node or value.
2. **Never widen.** These plans go through when they should be refused:
   - plans ending "… and mentioning 'begin'" / 'kind' / 'each' / 'discovered';
   - "Show me Bronze Age sites → Find Objects mentioning 'bronze'";
   - task 009's "How many stories have a translation?", which falls back to "listing the type instead".

   When a content word can't be placed, refuse (with "did you mean" where there is one). Free text is only allowed where the vocabulary explicitly says it is. Check whether "mentioning" exists on purpose for the memory graph (`claude_memory_graph/planner.py`, `tests/test_planner.py`). If it does, keep it there behind an explicit setting and say so; don't break `memory_ask`.
3. **Fitting links with CIDOC-CRM.** Seeded run: "which tales mention the Gáe Bulg?" → "Tales whose actor is Object 'Gáe Bulg'" → 0. `_fit_relations` checks a link's target models, but some links have no target-model list (or an empty one), so anything fits.
   - When a link's targets are unknown, fall back to its CIDOC-CRM range. `actor` comes in via P14/P11 (→ E39 Actor), and an Object root is E22 Human-Made Object, so it can't fit. The model root classes and each node's class and property are already in the graph JSON, and `crm_roles` / `CRM_PROPERTIES` in `pipeline.py` already decode them. Move what both need into one shared place rather than copying it.
   - Keep the rule narrow: only a known clash rejects (Actor vs Physical Thing, Place vs Actor, and so on). If either side is unknown, fit as today.
4. **The `repository_owner` crash.** No-seed run: "which monuments are at Emain Macha?" → "Rós Madair couldn't run it (compile: unknown path alias 'repository_owner')". The bundle has `repository_owner` as a link whose node isn't in the model given to the compiler. Find out whether the pipeline wrote an entry for a node from another model, or the compiler's alias map is missing it. Fix it at the source, and have the pipeline gate reject a bundle entry whose node isn't in its model.
5. **Walking actor backwards** (investigate; fix only if Ceist-side). "which figures are in Táin Bó Cúailnge?" (Opus run) and "what is related to Navan Fort?" are refused with "walking 'actor' backwards … Rós Madair walks links forward". Rós Madair v2 has `backlink` → `edges_rev`. Find out why Ceist refuses before asking it, for example the link sits in a nested nodegroup, or the plan shape has no backlink form. If Ceist can emit a backlink, do it. If Rós Madair genuinely can't run it, write the exact case into Worker notes for a Rós Madair task.

## Definition of done
- [ ] Unit tests, one per item: a qualified phrase scored right; an unplaced word refused (no "mentioning", no type listing); Actor link to an Object refused while unknown CRM still fits; a bundle entry for a missing node rejected by the gate; the backlink plan, or the recorded reason it can't be done.
- [ ] Re-score all four runs from their cache, with **no new LLM calls**: the report must say every call came from the cache. If a prompt changed and the cache misses, stop and say so, don't call `claude -p`. Put before and after for each in Worker notes: gate counts plus `demo_compare` right and wrong answers.
- [ ] Target for the Opus run: at least as many right demo answers as hand-tuned (21), with 0 wrong.
- [ ] The demo's hand-tuned answers: run every README question through the demo (`/home/stuart/git/personal/starches-demo/ask`, which imports this branch once merged; use `PYTHONPATH=<worktree>/packages/ceist/src` before that). List every change. "how many monuments are in Down?" turning into a refusal is expected and wanted. Anything else that changes needs a reason.
- [ ] HER plans (`bench/her_plans.py`): every diff justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-010`, never `git add -A` or `git stash`, no servers left running.

## Worker notes

## Graph writes proposed

## Review rounds
