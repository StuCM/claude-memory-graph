---
id: 025
slug: ontology-where-kind-material
status: approved
branch: crew/025-ontology-where-kind-material
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
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

## Graph writes proposed

## Review rounds
