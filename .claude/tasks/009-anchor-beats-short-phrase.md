---
id: 009
slug: anchor-beats-short-phrase
status: done
branch: crew/009-anchor-beats-short-phrase
model: opus
env: laptop
rounds: 1
files:
  - packages/ceist/
gate: pass
gateSha: a120ac3b8f55d0ec085f10eb4413801dcade5114
gateAt: 2026-11-05T14:41:33.095Z
---

# A record name beats a shorter phrase inside it

## Goal
When a record name such as "County Down" matches words that a shorter group, relation or value phrase also matches ("county"), the longer record name wins, so "how many monuments are in County Down?" is not refused because "county" was taken by a group phrase. The rule is applied the same way for hand-written and generated vocabularies. The pipeline also warns about one-word group phrases.

## Why now
Stu, 2026-11-05: "yep sounds good", to the recommendation of fixing this in grounding (longest match wins). From task 006's Worker notes: 7 of the 12 demo answers the generated vocabulary lost come from one-word group phrases (e.g. "county" on `Monument.localities_administrative_areas`). They ground before anchors and eat a word of "County Down". With those removed, the first live run's bundle answers 21/26 rather than 14/26.

## Background
- Ceist already matches relation phrases longest first (`ground.py`), but group phrases (from 005) and value phrases run before anchors. Find where each kind consumes words, and make overlapping spans resolve by length. A full record name or alias beats any shorter phrase it contains; between equal lengths, keep today's order.
- Don't let a long record name swallow a genuine relation in front of it. "Which monuments are in County Down" still grounds "in" to the link. Only words *inside* the record-name span are contested.
- **Test inputs:** the first live run's bundle at `/home/stuart/.cache/tmp-004/demo-run/bundle.json`, run with `bench/demo_compare.py` against the demo. The demo data was regenerated today (type, period and protection tiles), and its README questions are the reference.
- **Related,** handle only if trivial: "related to" on links turning a direct match into a refusal ("what is related to Navan Fort?"), and "How many stories have a translation?" silently dropping "translation". Record what you find; fix only if it's the same mechanism.

## Definition of done
- [ ] Unit tests: a record name containing a group phrase word, a value word, and a relation word, with the record winning each time; a relation in front of the name is not swallowed.
- [ ] `demo_compare` with the first live run's bundle: the before and after scores are in Worker notes, aiming for about 21/26 or more. The demo's hand-tuned answers don't change.
- [ ] HER plans (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. The memory graph's planner tests pass.
- [ ] `ceist vocab pipeline` warns about one-word group phrases in the report.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-009`, never `git add -A` or `git stash`.

## Worker notes

- `ground.py`: `_record_spans` finds each run of words holding a whole record name or alias (via `rank_entities`, `named_by` rule) before any phrase pass. `_phrase_spans` takes those spans for relations, group phrases and values, and skips an occurrence that sits inside a longer record name, trying the next occurrence. Equal length (a one-word record vs a one-word phrase) keeps today's order. Words in front of the name ("in", "on site") are outside the span and still ground.
- `pipeline.py`: `one_word_group_phrases(bundle)`, reported as one `Warning:` line (each group's own phrases only; combo phrases such as "damaged" are deliberate and set values, so not listed).
- Tests: `test_ceist.py` parametrised over group/value/relation "county" inside 'County Down' with "on site" in front (fails on the base code, 3/3), plus "county" outside the name still grounding as a value. `test_pipeline.py` asserts the warning.
- **demo_compare, first live run bundle** (`/home/stuart/.cache/tmp-004/demo-run/bundle.json`): generated answered **14/26 before, 21/26 after** (21/26 the same as hand-tuned). The seven gained: County Down (×2: "in", "located in"), Antrim, Armagh, Tyrone, Fermanagh, Londonderry — each now `Site 'County …'`.
- **Demo hand-tuned answers: none change.** All 26 README questions diffed base vs this branch: identical. (One base run showed "County Nowhere" without its did-you-mean and a rerun of the base with it; that is nondeterminism in the base, not this change.)
- **HER plans** (`bench/her_plans.py`, local clones at the CI-pinned refs: 2.0 `9f6a113`, 1.1 `0a21a46`): 125/125 and 125/125 as reviewed. No re-pin needed.
- **Memory graph**: `tests/test_planner.py` 33 passed. `memory_ask` changes only when a question holds a memory's whole multi-word name and a relation verb form or status word sits inside it; then the memory anchors instead of the shorter phrase.
- Gate: root 520 passed, Ceist 201 passed.
- Related, not fixed (different mechanisms): "what is related to Navan Fort?" grounds 'related to' as the `actor` relation in the generated bundle, then Rós Madair refuses walking it backwards; "How many stories have a translation?" grounds 'translation' as a relation with no second end, which falls back to listing the type ("could not place 'translation'; listing the type instead"), so it silently widens. That second one looks like a never-guess bug in the loose-listing fallback in `ground()` and worth its own task.

## Graph writes proposed

- Pattern (Ceist grounding): record names are found first and guard their words; a relation/group/value phrase strictly inside a longer whole record name gives way to it. Equal lengths keep the phrase. Applied in `_phrase_spans`, so hand-written and generated vocabularies behave the same.

## Review rounds

- Round 1 (a120ac3): **PASS**. Minor, not blocking: a repeated name word ("county county down") widens the protected span, which can only over-protect and refuse; one extra `rank_entities` call per question.
