---
id: 066
slug: gate-judges-each-phrasing
status: approved
branch: crew/066-gate-judges-each-phrasing
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/
  - packages/ceist/bench/ontology/
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
  - packages/ceist/VOCAB-TRAINING.md
---

# The gate keeps the good phrasings when one in a group is bad; "non-listed" binds the "Not listed" value

## Goal
Stu, 2026-11-11: "can we stop the correct phrasings from rejection".

1. **Judge each phrasing, not the whole group.** The gates (`site.py`'s site gate, `bench/ontology/gate.py`, `vocab_rules`/`crm_first` routes) treat a candidate as an element's **whole phrase list**. In 065's run, the LLM's `Insurance policy.insurer` element held one bad phrase, "covered by" (it reads "buildings covered by the policy" as the insurer). The gate rejected the **whole element**, so good phrasings like "insured by" went too, and Phil's frozen responder set fell from 15 to 14 right ("policies insured by Airgeadais Ó Braonáin Teoranta" now refuses).
   - **When an element is rejected,** split it and judge **each phrase alone**: keep every phrase that adds no wrong answer and makes nothing worse (in the alone stage, the compositions, the name probes and `--questions`), and reject only the culprits, each with its own reason.
   - Use 056/065's `culprits()` (halving, then leave-one-out) within the element's phrases, so it stays cheap. Only rejected elements get split.
   - Record per-phrase verdicts in `setup.md` and the coverage ledger.
   - This was deferred from 056 as "per-phrase rejection"; read its Worker notes on the cost.
2. **"Non-listed" is a value phrasing, not a negation.** "non-listed buildings" is read as "heritage status is **not** Listed", which also counts buildings with no status at all (268, against the count for the value "Not listed"). 065's setup flags it as a wrong reading, and exits 1 on Phil's corpus.
   - Where a controlled value's label is itself a negative form ("Not listed", "Unlisted", "Non-designated"), generate its "non-…", "un-…" and "not …" phrasings for that value, so the **longest phrase binds the value** before the negator reader sees "non".
   - Where no such value exists, "non-X" stays a negation, as today.
   - Check what the narration says in both cases.

## Measure
Re-run `ceist setup` on Phil's testbed corpus with the **cached** Sonnet replies only, as 064 and 065 did: `--llm --llm-cmd /bin/false --model sonnet`, with the cache copied from `/home/stuart/.cache/tmp-062/sonnet-site/llm/cache`. **Never `--llm ant`.** Then report:
- **the setup status block: 0 wrong readings and 0 partial binds, so setup exits 0**;
- per-phrase verdicts for the elements that were rejected whole in 065, with how many good phrases are recovered;
- Phil's testbed (93) per tier, with every new right read;
- Phil's frozen responder set **once** (`/home/stuart/.cache/tmp-aonach/responder.json`, sha `ad2e6bba`). "policies insured by …" should be back, with wrong answers at 0;
- the demo setup, the demo bank (exit 0), HER plans 125/125, the generated and reorder sets, and the golden dump (every change explained);
- setup time.

**Wrong answers at 0 everywhere.**

## Background
- **Read first:**
  - the Worker notes of 056 (per-phrase rejection deferred), 064 and 065;
  - `site.py`, `compose.py`, `bench/ontology/gate.py` (`culprits`);
  - `ground/phrases.py` (`_values` and the negator handling in `_words`);
  - `docs/HOW-GROUND-READS.md`.
- **Machine load:** at most 2 processes. **Stop any `claude_memory_graph serve` process your session starts before you finish.**
- No live LLM calls. Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names.

## Definition of done
- [ ] Per-phrase splitting of rejected elements is tested: one bad phrase among good ones keeps the good ones, and an element whose phrases are bad only together is rejected whole, with its reason.
- [ ] "Non-listed" binding the value is tested, as is "non-X" staying a negation when no such value exists.
- [ ] The measurements are in Worker notes; setup exits 0 on Phil's corpus; wrong answers are at 0.
- [ ] The gate passes. `TMPDIR=/home/stuart/.cache/tmp-066`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
