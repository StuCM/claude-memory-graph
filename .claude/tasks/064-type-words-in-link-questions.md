---
id: 064
slug: type-words-in-link-questions
status: approved
branch: crew/064-type-words-in-link-questions
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/golden/
  - packages/ceist/bench/demo/questions.json
  - packages/ceist/docs/HOW-GROUND-READS.md
---

# Type words like "hospitals" and "keyholders" work inside link questions; record names keep their version numbers

## Goal
The Sonnet vocabulary run (2026-11-11, `/home/stuart/.cache/tmp-062/sonnet-site/`, $0.84) helped questions that name a record (Phil's frozen responder set: 10 → 13 right, 0 wrong). It left Phil's 100-question testbed at 15 right, and **added one wrong answer**. Most of the testbed's remaining refusals are **"couldn't place"**:
- hospitals ×7, keyholders ×6, run ×5, health/sector ×4, shelters ×3, and others.

The words are in the bundle, but they don't combine:
- "list the hospitals" ✓ and "which buildings are hospitals" ✓;
- **"who are the keyholders of the hospitals" ✗:** "couldn't place 'hospitals', 'keyholders'".

1. **Value-as-type words inside link questions.** 059 made "hospitals" a type word meaning *Buildings whose service role is Hospital*, via `--default hospital=Building`. Find why it grounds alone but not once a link phrase joins it ("keyholders **of** the hospitals", "hospitals **maintained by** …", "shelters **run by** …"), and fix it at the root, in both the readers and assembly. The preset value must ride on the variable the type word creates, wherever that variable ends up in the reading.
2. **Role nouns as type words.** "keyholders", "wardens", "staff" name *people with a role* (a value on a Person field, or the person end of a role link like `keyholder_for`). In `ceist setup`, generate these the same way as value plurals: the plural of a role value, or of a role link's noun form, becomes a type word for the model holding it, with the role preset. Where two models could hold it, use a site default (`--default keyholder=Person`), as 059 does. Make no guess without one.
3. **Version numbers are part of a name.** "Hazard footprints produced by the flood model" bound HazardModel **'Flood model v1.0'**, because the version token isn't a name term, so a partial name passed as whole. This is a **wrong answer**. A record name's numbers and version tokens ("v1.0", "2", "II") count as name terms. "the flood model" must then not bind 'Flood model v1.0'. It should find the type word or values, or refuse with "did you mean 'Flood model v1.0'".
4. **Narration of link phrases read from the far end.** "Find Buildings that are the occupies of Organisation X" should read "Buildings occupied by Organisation X". Use the link's passive or noun phrasing when the variable is the link's target.

## Measure (tables in Worker notes)
- **Re-run `ceist setup` reusing the cached Sonnet replies.** The LLM cache is under `/home/stuart/.cache/tmp-062/sonnet-site/llm/cache`. Copy it into your own output dir, and pass `--llm ant --model sonnet --max-dollars 0.50`. The setup must report **0 new calls**. **If it would make any live call, stop and report instead.** Use the same six Building defaults as 059, plus any new role defaults you add (list them).
- **Phil's testbed, the 93 scorable questions:**
  - `/home/stuart/.cache/tmp-aonach/testbed/h/score.py` with `baseline/expected.json` and your bundle (see `run.sh`);
  - report per tier;
  - **read every new right** (the scorer lists unread count-matches), and record each reading in Worker notes.
- Phil's frozen responder set (`/home/stuart/.cache/tmp-aonach/responder.json`, sha `ad2e6bba`), **once**, at the end: `/home/stuart/.cache/tmp-059/h/score_setup.py` on `/home/stuart/.cache/tmp-aonach/aonach-ceist`.
- The practice set for any checking along the way.
- The demo bank (exit 0), the generated sets, the reorder set, HER plans (125/125), and the golden dump (every change explained).
- **Wrong answers at 0 everywhere.** The flood-model one must be gone.

## Background
- **Read first:**
  - `docs/HOW-GROUND-READS.md` (`_words`, `_values`, `_imply_model`, `assemble.py`);
  - 059's Worker notes (value-as-type words, `--default`, the manifest);
  - the graph Patterns "same-type links need word order for direction", "vector score can't weigh none of these" and "bare county names fail at record spans".
- The testbed harness and Phil's corpus are described in `/home/stuart/git/fat/aonach-responder-assessment.md` §2c and §7.
- **No live LLM calls** (cache only, as above). Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names. Update `docs/HOW-GROUND-READS.md` where the readers change.

## Definition of done
- [ ] Each of the four is fixed and tested:
  - a type word inside a link question, both as subject and as object;
  - a role noun with and without a default;
  - a version-numbered name not bound by its partial name;
  - the passive narration.
- [ ] The measurements are in Worker notes, every new testbed right read, wrong answers at 0, and 0 new LLM calls.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-064`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
