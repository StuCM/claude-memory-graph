---
id: 027
slug: richer-ontology-vocab
status: done
branch: crew/027-richer-ontology-vocab
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: abe720c724d7cfc52687a3619921caef0e4d503c
gateAt: 2026-11-08T12:00:31.263Z
rounds: 2
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

### Live run for Stu (from the worktree root, after merge or here)
```sh
G=/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models
C=/home/stuart/git/fat/arches/catalina/catalina-graphs/output/graphs/resource_models
L=/home/stuart/git/fat/arches/arches-lingo/arches_lingo/pkg/graphs/resource_models
D=/home/stuart/git/personal/starches-demo/ask/data/graphs
.venv-ceist/bin/ceist vocab ontology $G $C $L $D -o /home/stuart/.cache/ceist-ontology-run --model opus
# review vocabularies/ontology/cidoc-crm/proposed.json: edit phrases, set "reviewed": true
.venv-ceist/bin/ceist vocab ontology --accept      # gate → phrases.json; verdict per proposal in proposed.json
# a machine without the demo or HER checkout: --skip demo / --skip her (otherwise the gate fails, merging nothing)
```
- **Calls:** 113 paths (475 nodes) → **12 calls** of 10 paths, at most 24 with retries; `--max-calls 300` default. A re-run pays only for paths not yet answered (cached per path in `-o …/cache`); `audit.jsonl` there holds every prompt.
- **Cost:** a prompt is ~12.6k chars (~3.5k tokens in, ~1–3k out with thinking). At Opus 5.5 API rates ($4/$20 per M) ~$0.08 a call, **~$1 for the run, ~$2 worst case**; Sonnet 5.5 about half. On Stu's subscription it is just usage.
- **Accept** takes ~7 min for a handful of proposals on this machine (bench ~1–2 min, demo bank twice ~30 s, HER describe+assemble+plans ~5 min). Per-proposal bench time scales with the number reviewed.

### What changed
- `src/ceist/ontology_vocab.py` (new): `definitions` (labels + scope notes from the RDFS; an inverse property takes its forward's note; CRMsci has no labels, so the name gives it), `path_of`/`collect` (unphrased link/date paths keyed as phrases.json keys them, ranked by nodes then graphs; codes outside CRM+CRMsci skipped and counted; concept/reference property nodes listed for 025), `prompt`/`check`/`propose` (batches of 10 through `pipeline.Runner`, per-path cache, `proposed.json` keeps a reviewer's edits on re-run), `accept`/`merge`/`write_phrases`.
- `bench/ontology/gate.py` (new): the gate `--accept` runs. Each candidate alone on the bench sets vs phrases.json (must add a right, make nothing worse: no right/right refusal lost, no new wrong reading or wrong); then the passing ones together on the bench and on the demo bank (output compared before/after), dropping those whose phrase is in a changed question; then HER plans 2.0. Verdict JSON on the last line.
- `bench/ontology/run.py`: scoring split into `layer_bundles` and `outcomes` so the gate reuses it; `load_ontology` takes a dir.
- `src/ceist/bundle.py` `layered`: reads `.get("entries", [])` so `proposed.json` beside `phrases.json` isn't read as phrases (it was a KeyError).
- `src/ceist/cli.py`: `ceist vocab ontology`.
- `vocabularies/ontology/cidoc-crm/source/`: `cidoc_crm_v6.2.xml` + `CRMsci_v1.2.3.rdfs.xml`, copied from the local arches-her clone (9f6a113): the exact files the graphs' URIs come from (v6.2 with Arches' "Human-Made" names). No network fetch was needed. README notes version, sha256 and licence (CC BY 4.0 per cidoc-crm.org; the files carry no licence text: worth a check).
- `tests/test_ontology_vocab.py`: the five DoD tests. The wrong-reading test is real: "construction date" on the production path reads the fixture's other date field; mutation-checked by dropping the wrong/wrong-reading clause in `judge` (fails).

### Dry run (stub LLM, real ranked paths)
`ceist vocab ontology <4 dirs> -o … --ontology <copy> --llm-cmd <stub>` printed `113 paths (475 nodes), 0 cached: 12 calls, up to 24 with retries`, wrote 113 proposals; the re-run made 0 calls. Top paths: `P4 E52 P86i` date 44, `P140i E13 P4` date 37, `P140i E13 P141` 23, `P1 E33 P67i` 21, `P9 E7 P4` 20, `P140i E17 P17` 18. Not proposed: 240 nodes already phrased, 380 outside CRM+CRMsci (CRMdig, CRMgeo, Catalina's Z-classes, rdm/aaao). Property-node paths for 025: 199 (top `P2 E55 P2` 2763 nodes, `P1 E41 P2`, `P4 E52 P2`, `P72 E56 P2`, `P141 E55 P2`), all listed in proposed.json `property_nodes`.
A real gate run on 3 hand candidates (temp copy, not merged): `P140i E13 P4` and `E7 P15` passed; `P9 E7 P4` ["took place", "carried out"] was rejected ("when was Keldrith carried out?" worse on HER); demo bank unchanged; HER plans 125/125.

### Spec notes / limits
- Path keys are up to three tokens, matching phrases.json; dates key on the event before the time-span, so `P4 E52 P86i` (a span within a span) is generic: the LLM is asked to skip such paths.
- The per-candidate bench only re-asks questions sharing a word with its phrases (`ponytail:` in gate.py); the together run re-asks all, so nothing is lost.
- The demo-bank and together checks reject by phrase occurrence in the changed questions, else all passing: coarse, but never merges a change.
- HER plans can't change from phrases.json (HER uses the assembled bundle, not `layered`); the check is run because the spec asks.
- No change to ground/plan/crm; nothing reaches `memory_ask`.
- After review round 1: a failed demo-bank run (no tally line, or exit other than 0/1) or a missing demo/HER checkout fails the gate instead of passing vacuously; skipping needs `--skip demo|her`. Verdicts are keyed `"<kind> <path>"`.
- Gate passed on abe720c: root 610 passed (51 skipped, 1 deselected); Ceist 306 passed. Not rebased on 295659f (spec-only commit; the dirty task file blocks a rebase).

## Graph writes proposed
- Decision: CIDOC-CRM scope notes for Ceist's ontology vocab come from `vocabularies/ontology/cidoc-crm/source/` (v6.2 + CRMsci, copied from arches-her: the encoding Arches graphs use). Proposals go to `proposed.json` and reach `phrases.json` only via `ceist vocab ontology --accept`, gated by `bench/ontology/gate.py` (bench alone + together, demo bank, HER plans).
- Pattern: CRMsci's RDFS has no labels or comments and redeclares some CRM properties bare; when merging RDFS files, never let an empty redeclaration overwrite a CRM label/note.

## Review rounds
- Round 1 (abe720c's parent 5e7e3ba): CHANGES. (1) demo bank failure read as "unchanged"; (2) missing demo/HER checkout skipped silently and still merged; (3) verdicts keyed by path not (kind, path). All three fixed in abe720c (amended; a test asserts a missing checkout fails).
- Round 2 (abe720c): PASS. All three findings confirmed fixed; tests 5 passed.
