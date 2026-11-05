---
id: 009
slug: anchor-beats-short-phrase
status: approved
branch: crew/009-anchor-beats-short-phrase
model: opus
env: laptop
rounds: 0
files:
  - packages/ceist/
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

## Review rounds
