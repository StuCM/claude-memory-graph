---
id: 057
slug: near-and-demo-bugs
status: approved
branch: crew/057-near-and-demo-bugs
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/demo/questions.json
  - packages/ceist/bench/golden/
  - packages/ceist/bench/her/plans-2.0.json
  - packages/ceist/bench/her/plans-1.1.json
---

# Fix "within N km of", and seven other questions Stu found on the demo

## Goal
Stu tried the demo on 2026-11-09 (assembly as the default, CRM-first vocabulary). These questions fail; each needs its root cause found and fixed, or a written reason why refusing is right. Every one fails in strict mode too unless noted, so they are older gaps, not regressions. Reproduce each with `/home/stuart/.cache/tmp-demo/tryq.py` (run from `starches-demo/ask` with its `.venv`, questions on stdin).

**Distance:**
1. **`which monuments are within 20 km of Belfast?`** (and `neolithic monuments within 20 km of Belfast`) refuses with "Monument 'Belfast, Belfast' isn't a Site, which 'within' points at". The ontology link phrase "within" (`phrases.json`: `P89i` and `E53 P89 E53`) is grounded by the relations pass, which runs before the near pass, so "within <number> <unit> of X" never reaches the distance pattern.
   - Fix it so that a distance pattern wins over a link phrase on the same words.
   - Make sure "lie within County Down" (demo bank) still reads as named location.
   - "near X" already works, with a 5 km default.
2. **`souterrains within 10 km of Navan Fort`**: a value-only subject ("souterrains", no type word) combined with a distance refuses with "'souterrains' is a value of functional_type, monument_type, which nothing asked for has". Without the distance, the type is implied fine ("how many souterrains are there?").
3. **`neolithic monuments near Belfast that are in state care`**: "cannot resolve both ends of relation named_location". "in" is read as a location link, but "in state care" is a value.

**Others:**
4. **`who was the father of Cú Chulainn?`**: refuses with "Figure 'Cú Chulainn' isn't a Figure or Group, which 'who' points at". The message contradicts itself, so the "who" check is likely testing the wrong node. Likely root cause (from the 2026-11-10 walkthrough): `assemble._in_order` orders the ends of a same-type link (Figure–Figure `father`) by word order alone, but "the father **of** X" means X's father, so "of" turns the direction round. Check `_in_order` and `_after_as` for an "of" rule.
5. **`which tales feature Fionn mac Cumhaill?`** returns 0 results ("Tales whose actor is Figure 'Fionn mac Cumhaill'"). Check the data: is Fionn linked to tales another way? If so, should "feature" reach that link too? This is a vocabulary or data question; say which.
6. **`County Antrim souterrains`** (that word order) is read as a yes/no question about County Antrim, while "souterrains in County Antrim" answers 569. Decide whether a leading named record followed by a value should read as a filter.
7. **`which tales are linked to monuments near Armagh?`**: "'linked to' can't join Monument and Tale". Tales do link to monuments (their associated-monuments link). Find why "linked to" doesn't reach it.
8. **`built before 1800, monuments in County Down`** returns 0. Check whether that's real (few construction dates in the data) or a wrong date field.

**"in" as a phrase with its object** (Stu, 2026-11-10: "anything with in should be looking at the phrase as a whole, as that will more than likely answer the correct meaning"). Items 1 and 3 are both "in"/"within" read as a bare link. Make "in <what follows>" one unit, resolved by what follows:
- a date → the date ("in 1990");
- a distance → near ("within 20 km of");
- a value phrase → the value ("in state care");
- a named place → its location link;
- a named tale → its parent story.

Use the word before it only where the object leaves a choice. Measure it with the same sets; wrong answers must stay at 0.

**Short names for records that have a generic lead word** (Stu, 2026-11-10: he always had to say "County Fermanagh"; "Fermanagh" alone refuses). `_record_spans` binds only a whole name or an alias, so this is solved at build time with aliases, not by loosening:
- give a record an alias with its generic lead word removed ("County", "Townland", "Parish", and others the data shows), **only when** the remainder is unique among the records and is not already a vocabulary phrase or a common word;
- "Fermanagh", "Tyrone" and "Antrim" should then bind;
- "Down" must not ("down" is a word and a value phrase), so it stays "did you mean".

Add the bare-county questions to the demo bank with verified counts, plus "how many monuments are in Down?" staying a must-refuse.

9. **`figures in tales of the Ulster Cycle`** asks with two options that are **both inverted**. "in" is taken as the Tale–Tale `parent_story` link (by word order), and "of" is not understood, so it reads "Tales that are the parent story of Ulster Cycle". Expected: Figures (actor) in Tales whose parent story is Ulster Cycle. Same roots as items 1, 3 and 4: read "in" with what follows, and add an "of" rule to `_in_order`.
10. **`which tales are linked to Cú Chulainn?`** refuses ("'linked to' can't join Figure and Tale"): the phrasing "linked to" exists on `actor` and `associated_actors`, but only on other models' variants (`said_as` keeps phrasings per model), so Tale's `actor` isn't "linked to". "which tales feature Cú Chulainn?" works. This is a vocabulary question (CRM-first: the phrase belongs on the CRM path); fix it, or record why not.

11. **`show me all castles in belfast`** refuses with "Monument 'Belfast, Belfast' isn't a Site or Tale, which 'in' points at". The demo has no Belfast *place* (no city or town Site). "Belfast" binds a **Monument** record named "Belfast, Belfast", and "in" wants a Site. Refusing is right, but the message is unhelpful. When "in X" names a record that has a location but isn't a place, add a **"did you mean near X?"** suggestion (a suggestion, never a silent swap). Record in Worker notes whether the demo data should gain town or city places.

12. **The generated sets' remaining wrong readings** (4 on train, 2 on hold-out). They are identical under exact and bge, before and after 063, so they come from grounding, not the matcher. For example, "what is Slemish part of?" is read as a link, when a detail of Slemish was asked for. List all six with their cause, and fix them. **Wrong readings must reach 0** on both generated sets; for any that can't, record why refusing is right.

## Rules
- **Never guess:** a fix must not turn any must-refuse question into an answer. The demo bank's must-refuse set, the reorder set and the fresh-graph bench must stay at 0 wrong.
- **Add each fixed question to the demo bank** (`bench/demo/questions.json`) with its verified count, so it stays fixed. Where refusing is right, add it as a must-refuse question with the reason.

## Measure
Before and after for the demo bank, the reorder set, the generated train and hold-out sets, HER plans (each diff justified), the fresh-graph bench and the golden dump (every change explained).

## Background
- **Read first:**
  - `packages/ceist/STATUS.md`;
  - the `ground/` passes (040), `assemble.py` (049–051), and 053's and 055's Worker notes;
  - the graph Patterns "same-type links need word order for direction" and "Ceist link phrases have no direction".
- 056 must be merged first (both touch `packages/ceist/src/ceist/`).
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`). No `claude -p` or live LLM runs.

## Definition of done
- [ ] Each of the 8 is fixed, or has a written reason it is right to refuse or return 0, and each is in the demo bank.
- [ ] Wrong answers stay at 0 where listed. The measurements are in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-057`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
