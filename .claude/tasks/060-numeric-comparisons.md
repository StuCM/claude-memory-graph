---
id: 060
slug: numeric-comparisons
status: approved
branch: crew/060-numeric-comparisons
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
  - packages/ceist/bench/demo/questions.json
  - packages/ceist/PRIOR-ART.md
  - packages/ceist/docs/HOW-GROUND-READS.md
---

# Numeric comparisons: "capacity over 200", "taller than 30 metres", "worth more than 5 crore"

## Goal
The reverse test on Phil's responder data (`/home/stuart/git/fat/aonach-responder-assessment.md` §2b) found numbers to be Ceist's biggest gap: about 10 of the 25 answerable questions compare a number field, and Ceist has no reader for them. aonach answers some, but gets the bounds wrong ("taller than 30 m" counted the four buildings at exactly 30 m) or drops the number silently ("coastal shelters with capacity over 200" gave 52 instead of 7). Ceist must answer these **exactly, or refuse**.

## Decisions (settled; don't re-litigate)
1. **Which fields are numbers.** Arches nodes with datatype `number`. Add `number_fields()` to the vocabulary (beside `date_fields()`), giving each field's alias, label, owning models, phrasings (field words) and, where the graph or vocabulary says so, a **unit**: a length in metres, money in a currency, or a count. The unit comes from the node's name, description or config, or from a vocabulary phrasing. **Never guess a unit:** a field with no known unit only accepts unitless numbers.
2. **The comparison words: grammar, in code, beside `NEAR_RE` and the date patterns.**

   | Said | Means | Bound |
   | --- | --- | --- |
   | over, more than, above, greater than, exceeding, taller than, bigger than | > | **strict** |
   | under, less than, below, fewer than, shorter than, smaller than | < | **strict** |
   | at least, no less than, a minimum of, room for, holds, capacity of | ≥ | inclusive |
   | at most, no more than, up to, a maximum of | ≤ | inclusive |
   | between X and Y | X ≤ v ≤ Y | inclusive both ends |
   | exactly N, of N | = | |

   **The narration always says the bound:** "capacity more than 200", "capacity at least 200", "height between 10 and 30 metres (inclusive)".
3. **Which field a number belongs to:** the same rule `_dates` uses. Take the nearest field word or unit before it, else after it ("capacity over 200", "over 30 metres tall", "worth more than 5 crore"). With no cue and **one** number field on the subject's type, use it. With several and no cue, **"did you mean"** each field, never a guess.
4. **Units and money.** These are fixed in code, because they're arithmetic, not vocabulary:
   - length: m/metres, km/kilometres, ft/feet;
   - money: thousand/k, lakh (10^5), crore (10^7), million, billion;
   - counts: people, persons, occupants.

   Convert to the field's unit. **A unit that doesn't fit the field refuses:** "worth over 30 metres" refuses, saying why. Phil's `crates/greasan-ask/src/numbers.rs` (aonach-responder, `chennai-respin`) is the reference for the phrasings and money units. Credit it in `PRIOR-ART.md` and with one docstring line in the module. His site-specific field families (`height_m`, `insured_value`) don't belong in code: those are field phrasings in the vocabulary.
5. **Dates and distance keep their numbers.**
   - "within 20 km of X" stays a distance (`_near`).
   - A year with a date word ("before 1900", "built after 1850", "in the 1920s") stays a date.
   - The numeric reader runs **after** `_near` and `_dates`, and takes only comparisons they left.

   Add one order comment in `pieces()` saying why.
6. **The plan.** A new condition, `NumberRange(field, lo, hi, lo_inclusive, hi_inclusive)` (a sibling of `DateRange`), with negation through `_scope_negations`: "not more than 200" → ≤ 200. Assembly attaches it to a variable whose type holds the field, as `_date_options` does for dates.
7. **Compiling to Rós Madair:** the `range` operator, as dates use (`rosmadair.py`, around line 167).
   - **First, check and record whether Rós Madair's `range` is inclusive at both ends**, and how it treats decimals. Read its source or test it on the snapshot.
   - If it is inclusive only: for an **integer** field, compile a strict bound as ±1; for a **decimal** field, either express it exactly, or **refuse** strict comparisons, saying why. Never compile a strict bound as an inclusive one.
   - Read-back must check the operator, the bound kinds and the values.

## Measure (tables in Worker notes)
- **Phil's responder data:**
  - the **practice set** (`/home/stuart/.cache/tmp-aonach/responder-practice.json`) for checking;
  - the **frozen set** (sha `ad2e6bba`, path in the assessment §7) **once**, at the end, built with `ceist setup` and the six Building defaults as in 059 (`/home/stuart/.cache/tmp-059/h/score_setup.py`).
- The demo bank (exit 0), with the numeric questions added if the demo has number fields, the generated sets, the reorder set, HER plans (125/125) and the golden dump (changes only where a question holds a comparison, each explained).
- **Wrong answers stay at 0 everywhere,** including the strict-bound cases that aonach got wrong.

## Not in this task
- Arithmetic between fields ("taller than it is wide").
- Superlatives beyond the existing "most/fewest" group-by.
- "near me" (no device location).
- Area units (square km) unless a responder field needs them; if so, say so in Worker notes.

## Background
- **Read first:**
  - `docs/HOW-GROUND-READS.md` (the reader order, `_dates`, `_near`, assembly);
  - `plan.py` (`DateRange`, `_finish`);
  - `rosmadair.py`, `readback.py`, `narrate.py`, `assemble.py` (`_date_options`);
  - 059's Worker notes.
- Update `docs/HOW-GROUND-READS.md` with the new reader: what it does, an example, and its weak spots.
- No `claude -p` or live LLM runs. Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names.

## Definition of done
- [ ] Number fields, the comparison reader, units, `NumberRange`, compile and read-back are all tested, including:
  - strict versus inclusive;
  - "between";
  - negation;
  - a unit mismatch refusing;
  - two number fields with no cue asking "did you mean";
  - "within 20 km" staying a distance;
  - "before 1900" staying a date.
- [ ] Rós Madair's `range` semantics are recorded in Worker notes, with how strict bounds compile.
- [ ] The measurements are in Worker notes; wrong answers are at 0; the frozen set is scored once.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-060`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
