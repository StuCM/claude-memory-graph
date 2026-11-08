---
id: 025
slug: ontology-where-kind-material
status: done
branch: crew/025-ontology-where-kind-material
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: 29887d6c41d455166970f353467af5410ee90073
gateAt: 2026-11-08T12:30:13.847Z
rounds: 1
---

# Ontology layer, part 2: "where", "what kind of" and "made of", and phrases on list (property) nodes

## Goal
1. **Ontology phrases on property (concept and reference) nodes.** Today bundle entries carry only link and date phrases, so the ontology layer can't phrase a CRM path that ends at a list value. 027's dry run found **199 such paths** across HER, Catalina, arches-lingo and the demo (its `property_nodes` list).
   - Let an ontology entry target a property node by its CRM path, with kind `property`.
   - Its phrases name the *field* ("type", "kind", "material", "condition"), so a value of that field grounds with it, as graph-layer property phrases already do.
2. **"what kind of {X} is …" / P2 has type → E55:** "what kind of monument is Navan Fort?" answers with the record's type field (a Detail, task 016). "which kinds of objects …" groups by type where 017's group-by applies.
3. **"made of" / P45 consists of → E57 Material:** "what is the Gáe Bulg made of?" answers with the material field. "which objects are made of bronze?" filters on it.
4. **"where" → an E53 Place link:**
   - "where is Navan Fort?" answers with the record's place links (named location, as a Detail, or via the 015 link read);
   - "which monuments are where Navan Fort is?" isn't needed.
   - "where" with no place link refuses.
5. **027's tool covers property paths:** `ceist vocab ontology` stops skipping property-node paths (027 lists them separately), so the live run can propose phrasings for them too, through the same gate.

## Why now
Stu, 2026-11-08: "I want to have this fleshed as best we can to answer a large chunk of questions." The 199 property-node paths are the largest block of CRM paths the ontology layer can't reach.

## Background
- **Read first:** 023's, 026's, 027's and 029's Worker notes. 029 narrowed P107 and keyed "construction date" in code, because `vocabularies/` wasn't in its files. This task has `vocabularies/`, so move those rules into the data if it's clean.
- **Code:** `bundle.layered` (ontology layer under the base), `crm.ontology_entries` / `crm.chains`, `ground.py` value grounding, and `plan._detail`.
- **The memory graph runs on Ceist:** check `tests/test_planner.py`, and say what changes for `memory_ask`.
- **No `claude -p`, live LLM or vocab pipeline runs.** Write the property phrases for the top paths by hand, as 023 did. 027's tool proposes the rest in Stu's live run.

## Definition of done
- [ ] Unit tests, each failing on the base code:
  - an ontology phrase on a property path grounds a value of that field;
  - "what kind of X is Y?" gives the type Detail;
  - "what is X made of?" gives the material Detail, or refuses naming 'made of' when there's no P45 path;
  - "where is X?" gives the place links, or refuses;
  - 027's tool now proposes property paths (stub).
- [ ] 026's bench, before and after (ontology mode, all sets). Wrong readings and wrongs must not rise.
- [ ] The demo question bank exits 0 (`run_bank.py`, as in earlier tasks). Add "what kind of monument is Navan Fort?" and "where is Navan Fort?" with hand-checked expectations, using `--write`.
- [ ] HER plans (clone at `/home/stuart/.cache/tmp-003/arches-her`): every diff is justified and re-pinned deliberately.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-025`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

### What changed
- `crm.py`: `ontology_entries` now gives entries for controlled (concept/reference) nodes as kind `property` (`is_controlled`). A path starting with `^` starts at the record's root. 029's `_ON_ROOT` code rule is now data: `^ P107` and `^ P107i` in phrases.json.
- `bundle._add_ontology`: ontology entries are marked `"layer": "ontology"`. If the base already uses an ontology phrase with the same meaning, it is now kept rather than dropped. That is how "made of" still reaches the demo Object's material, which the base also phrases.
- `arches.py`: ontology property entries become field phrasings (`field_phrases()`). `place_fields(type)` gives the links whose CRM range is an E53 Place. The base's own property entries (1714 in HER) stay unused, as before. Trying them gave a wrong Detail on the bank: "what is related to Navan Fort?" became association type.
- `ground._field_phrases`: a field phrase holds the value right after it to that field ("made of bronze" → material). With no such value after it, it places nothing, so the matcher and refusals see those words as before.
- `plan._detail`: "what kind of {X} is Y" matches a field phrase with or without the record's type word, giving the type Detail. "what is Y made of" gives the material Detail. Where the model has no such path, it refuses with "couldn't place 'made'". "where is Y" gives a Detail of its E53 links, or refuses with "'where': a <Type> has no link to a place to answer it from". It no longer gives the bare record.
- `questions.templated`: a property phrase gives "what is the <p> of {M}?" (a Detail target), so 027's gate can score property proposals.
- `ontology_vocab.collect`: property-node paths are now candidates (kind `property`), not a separate `property_nodes` list. The prompt explains property paths and `^`. The live run grows from 113 paths to roughly 113 + 199, about 32 calls instead of 12, roughly $2.5.
- `phrases.json`: type (`O18i E11 P41i E17 P42`, `P108i E12 P41i E17 P42`), function (`P12i E5 P41i E17 P42`) and material (`^ P45`, `P108i E12 P126`), hand-written. Most material nodes in these graphs are P126 E57, not P45. `O18i E11 P126` is left out because it fits both the main and the covering material. Root `P2 E55` is left out because in HER it is `resource_model_type`.
- Not done: "which kinds of objects …". 017's GroupBy only counts per link, not per concept field. The demo can't show "which objects are made of X?", because its material lists hold no values. The fixture test covers it.

### Checks
- Tests: 5 new or updated in `test_ontology.py` and 2 updated in `test_ontology_vocab.py`. All fail on base src (`git archive` of 09e29f1).
- 026 bench, ontology mode (right / wrong reading / refused / right refusal / wrong):

| set | before | after |
|---|---|---|
| lingo (24 q) | 22 / 0 / 0 / 2 / 0 | 22 / 0 / 0 / 2 / 0 |
| Catalina (339 → 362 q) | 275 / 0 / 39 / 25 / 0 | 298 / 0 / 39 / 25 / 0 |
| HER (268 → 291 q) | 234 / 0 / 8 / 26 / 0 | 257 / 0 / 8 / 26 / 0 |
| HER, ontology + base | 230 / 0 / 12 / 26 / 0 | 253 / 0 / 12 / 26 / 0 |

  The new questions are the property templates, and all of them are right. Wrong readings and wrongs did not rise.
- Demo bank: before 69 / 1 / 7 / 11, 0 wrong. After 71 / 1 / 7 / 11, exit 0. Added "what kind of monument is Navan Fort?" (monument type: Settlement, Ritual Site) and "where is Navan Fort?" (named location: Emain Macha, County Armagh), both checked against the tiles, written with `--write`. The refusal text for "who killed Cú Chulainn?" changed in questions.json, but it was stale: base src gives the same text.
- HER plans 2.0 and 1.1 (029's archives): 125/125 each, no diffs, nothing re-pinned. HER uses the assembled bundle, which has no ontology-layer entries.
- memory_ask: `MemoryVocabulary` has no `fields`/`field_phrases`, so `_detail` returns None before "where", and nothing changes. `tests/test_planner.py` passes in the gate.
- Gate passed on 29887d6: root 620 passed, 51 skipped, 1 deselected; Ceist 316 passed.

## Graph writes proposed
- Decision: Ceist turns only the ontology layer's property entries (`"layer": "ontology"`) into field phrases. A field phrase holds the value after it, or names a field for a Detail. The base's LLM property entries stay unused: they are too loose ("related to" → association type).
- Pattern: in HER-derived Arches graphs, type is `… P41i E17 P42 E55` and material is `… P126 E57`, not P2 or P45. Root `P2 E55` is `resource_model_type`.
- Decision: ontology paths starting with `^` are anchored at the record's root (`^ P107` for own members, `^ P45` for what the thing consists of).

## Review rounds
- Round 1: PASS (crew-reviewer). It ran the ontology tests (24 passed); for the gate, bench, bank and HER plans it relied on the numbers above.
