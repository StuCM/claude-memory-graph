---
id: 039
slug: systematic-vocab-coverage
status: approved
branch: crew/039-systematic-vocab-coverage
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
  - vocabularies/
---

# Vocabulary coverage: a checklist per element, a coverage report, and rule-based generators that fill it

## Goal
Workstream A of `packages/ceist/STATUS.md`. Vocabulary building has been ad hoc, with no definition of what a complete layer contains, so gaps only show when a question fails. This task defines completeness, measures it, and fills what rules can fill, with **no LLM**.

1. **The checklist, and a coverage report** (`ceist vocab coverage <graph dirs…> [--base <dir>] [--client <dir>]`). For each layer and element it lists which items are present and which are missing, with a percentage per layer and overall. The items:
   - **Ontology layer:**
     - class words for each CRM class the graphs use, weighted by node count (E21 Person: "person", "people"; E53 Place: "place", "places");
     - both directions of each property used (P14 "carried out by" and P14i "performed");
     - the existing path phrasings.
   - **Graph base layer:**
     - per model: type words, singular and plural, plus the base graph's name when a graph is renamed (the demo's Figure is a renamed HER graph);
     - per link: forward, inverse, verb and noun forms ("copyright holder" → "holds copyright" / "hold copyright"; "part of" → "parts of", "has part");
     - per field: its label's forms.
   - **Client layer:** per controlled value, the plural and the alternative labels ("townland" → "townlands").

   The report is markdown, plus JSON for later steps. It is committed beside the layer it measures.
2. **Rule-based generators** (a `ceist vocab generate` step, or a stage of the existing build; your choice, say which). They fill checklist gaps from:
   - the CRM labels already in `vocabularies/ontology/cidoc-crm/source/` (class `rdfs:label`, property labels and their inverses);
   - morphology: plurals with a small irregulars list, verb and noun forms from labels (agent noun to verb, "date of death" → "died"/"die");
   - base graph names, by graph id;
   - label splitting.

   **Every generated phrase goes through the existing gate:**
   - clash and generic review (033);
   - each proposal alone on the fresh-graph bench, then all of them together on the bench, the demo bank and the HER plans.

   A phrase that could name two elements is dropped, with its reason recorded, never guessed. Wh-words ("who" → actors, "where" → places) are added only where the grammar already uses them; check `ground.py` first and say what you found.
3. **A directed LLM fill command, built but not run.** It takes the gaps the report still lists and sends only those to the existing propose → review → gate route. Test it with a stub LLM. The orchestrator runs it live afterwards, with an estimate first.
4. **The definition of done**, written into `VOCAB-TRAINING.md` as part of the playbook:
   - the checklist is at 100% (or each remaining item has a recorded reason);
   - topics outside the schema, filler words, question shapes and name fragments are not vocabulary's job;
   - stop when a round adds fewer than about 2 right answers on the hold-out set;
   - later: repeated in-scope refusals from the capture log, 3 or more of the same phrase.

   Add the coverage report as a build stage, with its command.

## Why now
Stu, 2026-11-08: "I feel like our vocabulary building is not in depth enough… take a more systematic approach", "what about coverage of the cidoc vocab", and "how do we reach an end to vocab updates". Measured today (STATUS.md §4):
- Neither bge nor loosening can stand in for vocabulary.
- Of the 74 words the awkward set leaves unplaced, 11 already appear in the right field's label. Rules alone can add those.

## Background
- **Read first:**
  - `packages/ceist/STATUS.md`;
  - `packages/ceist/VOCAB-TRAINING.md`;
  - the Worker notes of 023, 025, 027, 033 and 035;
  - `src/ceist/ontology_vocab.py`, `bench/ontology/gate.py`, `src/ceist/bundle.py` (`layered`);
  - `ArchesVocabulary` in `src/ceist/arches.py` (`type_words`, `relations`, `fields`, `field_phrases`).
- **The measurement scripts from today** are in `/home/stuart/.cache/tmp-demo/bgecheck/`: `check.py`, `loosen.py` and `labels.py`. Read only; run them against your worktree's src for before and after numbers.
- **Hold-out hygiene.** The generators read only the schema, the CRM files and the layers. Never the question sets: neither `train.json` nor `holdout.json` in `~/.cache/ceist-questions-demo` may feed a generator.
- **No `claude -p`, live LLM or vocab pipeline runs.**
- **Leave the main checkout alone.** The main foundation checkout has uncommitted changes in `packages/ceist/bench/demo/vocab/` (Stu's live data-layer run). Don't copy or commit them. Work only in your worktree.
- **The demo bank's runner** is `bench/demo/run_bank.py` (`cd /home/stuart/git/personal/starches-demo/ask`, with `PYTHONPATH=<worktree>/packages/ceist/src`, and its `.venv`). The generated sets are scored with `--set <train.json|holdout.json>`.

## Definition of done
- [ ] `ceist vocab coverage` exists and is tested. Its report for the demo graphs and HER, before and after the generators, is in Worker notes, with the percentage per layer.
- [ ] The generators are tested, with one test per rule family. The accepted phrases are committed through the gate, with a build report listing what was accepted, what was rejected and why.
- [ ] The LLM fill command is tested with a stub and has not been run live.
- [ ] Before and after, in Worker notes:
  - the fresh-graph bench;
  - the demo bank (it must exit 0, with no new wrong answers);
  - the generated train and hold-out sets (right / wrong reading / refused);
  - HER plans (every diff is justified and re-pinned deliberately);
  - `labels.py`'s three-way split.

  Wrong readings and wrong answers must not rise anywhere.
- [ ] `VOCAB-TRAINING.md` has the coverage stage and the definition of done.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-039`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
