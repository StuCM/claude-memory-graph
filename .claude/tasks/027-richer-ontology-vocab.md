---
id: 027
slug: richer-ontology-vocab
status: approved
branch: crew/027-richer-ontology-vocab
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
---

# A tool that builds a much richer CIDOC-CRM vocabulary layer, ready for one live run

## Goal
`ceist vocab ontology` generates phrasings for CIDOC-CRM **paths**, reviewed by a person and merged into `vocabularies/ontology/cidoc-crm/`. It is built and tested with stubs here. Stu runs the single live pass himself, from his terminal (`claude -p` needs his login).

1. **What it covers, ranked by real use, not by the size of CRM.** Collect the CRM paths that real graphs reach:
   - HER (`/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models`);
   - Catalina and arches-lingo (the folders 026 used; read only, schema only);
   - the demo graphs.
   Rank by how many link and date nodes each path reaches across graphs. Skip paths 026 found are rightly unphrased (CRMdig and spatial metadata dates such as `D1 L24i D10 P4` and `SP6 … P4`). Use 026's "unphrased" list (task file Worker notes) as the starting priority.
2. **What goes to the LLM: CRM only.** For each path, send the CRM labels and **scope notes** of the classes and properties along it (the public CIDOC-CRM definitions), plus the existing phrasings as seeds, and ask for the plain-English phrasings people use: verbs, nouns, question words. **No client data:** no graph names, node names, record names or labels from client graphs. A test asserts this on the audit log.
   - The scope notes have to come from somewhere local. Find or fetch the CIDOC-CRM RDF/OWL file (the version the graphs use: check their `ontologyclass` URIs) **once**, save it under `vocabularies/ontology/cidoc-crm/source/` with its licence and version noted, and read the labels and scope notes from it.
3. **Output for review, not auto-merged:** write proposals to `vocabularies/ontology/cidoc-crm/proposed.json`, each with the path, the phrasings and the reason. A `--accept` step merges reviewed proposals into `phrases.json`.
4. **Gated before merging:** a proposal is accepted only if, on 026's bench (`packages/ceist/bench/ontology/run.py`), it adds right answers and adds no wrong readings and no wrongs, and if the HER plans and the demo question bank stay unchanged. Make the gate a script the accept step runs.
5. **Cost guard:** `--max-calls` (default about 300). Print an estimate of calls before running. Use the pipeline's cache, so a re-run only pays for new paths. Batch several paths per call where the paths are short.

## Why now
Stu, 2026-11-08: "Let's continue and run the richer ontology pipeline." Task 026 measured the 29 hand phrasings reaching only 10–19% of link and date nodes, while on what they do cover the layer answers 70–82% with no graph vocabulary.

## Background
- **Read first:** 023's Worker notes (paths not bare properties, why P14 alone is wrong) and 026's Worker notes (coverage, unphrased paths, miss reasons).
- **Reuse:** the pipeline's LLM plumbing (`pipeline.py`: `claude -p`, the audit log, the cache keyed by prompt), `crm.chains` and `crm.ontology_entries`, and 026's bench.
- **Property nodes** (P2/E55 "what kind of", P45 "made of") can't take phrases yet (task 025). Skip paths that end at a property node, and list them in the report for 025.
- **Never run `claude -p` or a live LLM yourself.** Use a scripted stub. Write the exact live command for Stu in Worker notes, with the call estimate.

## Definition of done
- [ ] Unit tests with a stub LLM:
  - paths are ranked by use;
  - prompts contain only CRM text and seeds (the audit test);
  - proposals are written for review;
  - `--accept` merges only gated proposals;
  - a proposal that adds a wrong reading on the bench is rejected.
- [ ] A dry run with a stub over the real ranked paths prints the call estimate and writes `proposed.json`.
- [ ] Worker notes give the live command for Stu, the estimated calls and cost, and where to review the output.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-027`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
