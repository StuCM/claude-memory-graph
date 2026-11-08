---
id: 026
slug: ontology-only-fresh-graph
status: done
branch: crew/026-ontology-only-fresh-graph
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
gate: pass
gateSha: 633132830a8eb3562ffbc2542ded9aeb66fb00e0
gateAt: 2026-11-08T10:11:43.756Z
rounds: 1
---

# Test: what does the ontology layer answer on a graph we've never touched?

## Goal
Measure how much the CIDOC-CRM ontology layer (task 023) answers **on its own**, on Arches graphs with no graph-layer or client vocabulary, and write it up as a repeatable bench.

1. **Graphs:** pick at least two that aren't HER or HER renames, read-only, schema only:
   - `/home/stuart/git/fat/arches/arches-lingo/arches_lingo/pkg/graphs/resource_models` (CRM-based, very different from HER);
   - one heritage graph that isn't a HER clone: Quartz (`/home/stuart/git/fat/arches/quartz/arches-quartz/quartz-graphs/output/graphs/resource_models`) or Catalina (`/home/stuart/git/fat/arches/catalina/catalina-graphs/output/graphs/resource_models`).
   Check each against HER's graph ids and node aliases first, and say how independent it really is.
2. **CRM coverage per graph,** reusing 023's audit scripts in `/home/stuart/.cache/tmp-023/audit/`: the share of link and date nodes whose CRM path has an ontology phrasing.
3. **A question set with no LLM:** a deterministic, template-based generator driven by the CRM paths each graph actually has. For each path with an ontology phrasing, write natural questions using it ("who made {X}?", "when was {X} built?", "which {models} were produced by {Actor}?"), plus a few the layer *shouldn't* answer.
   - Label them with the structured target from task 022's scorer (`packages/ceist/src/ceist/questions.py`).
   - Since there are no records, give each placeholder a synthetic record name registered in a test vocabulary, so grounding can anchor.
4. **Score three ways:**
   - ontology layer only;
   - no vocabulary at all (the baseline);
   - for HER only, as a control: ontology + HER base.
   Report right / wrong reading / refused / wrong per graph.
5. **A bench script** (`packages/ceist/bench/ontology/run.py` or similar) that reruns all of this, with the results in Worker notes.

## Why now
Stu, 2026-11-08: "Yeh let's do the test." The ontology layer is the bet against endless per-graph vocabulary work; this is the first measurement on graphs it wasn't written against.

## Background
- 023's Worker notes: the audit, the ontology layer, CRM paths not bare properties, "who"/"when" handling, and the known gaps ("where", P2, P45: task 025).
- 022's Worker notes: the structured target and scorer.
- `bundle.layered` loads the ontology layer under the base. For "ontology only", load an empty base.
- **No LLM, `claude -p` or vocab pipeline runs** (Stu: token cost). Everything here is deterministic.

## Definition of done
- [ ] The bench script runs end to end on the chosen graphs and prints the table.
- [ ] Worker notes: graph independence, CRM coverage, the three-way scores, and the 5–10 most common reasons the ontology layer misses. These feed task 027's priorities.
- [ ] Unit tests for the template generator: deterministic output, and every question carries a target.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-026`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

Bench: `.venv-ceist/bin/python packages/ceist/bench/ontology/run.py [name=<graphs dir> …]` (no args: lingo, catalina, her from the local paths in `SETS`). ~16 s for all three, one process per set (Catalina reuses HER's graph ids, and Alizarin registers by id). Schema only: the other projects' graph folders are read, never written, nothing copied, no LLM.

### What changed
- `src/ceist/questions.py`: `templated(vocab, ontology)`, a deterministic question bank from `crm.ontology_entries` per model. Link phrase → "which {Ms} were/are <p> {L}?" (or "have {L} as <p>?" for a noun) plus a "how many" of the first phrase; "who <p>" → backlink to the "who" model; date → "when was {M} <p>?", "what is the <p> of {M}?" for a noun date, "which {Ms} were <p> before 1900?". Refusals: "why was {M} <p>?" and "who <p> {M}?" when the event has no one P14 actor. A text with two targets is left out (the layer drops that phrase, so the reading rests on labels). Targets in 022's format. `_PLACEHOLDER` now allows any model name (lingo has "Person (system)"); `check` still requires it be a model.
- `bench/ontology/run.py` (new): independence, coverage, unphrased paths, three-way scores, top misses with an example each. Synthetic records: one made-up name per model ("Taldrith"), registered as a resource with no tiles, filled by `questions.fill`.
- `tests/test_ontology.py`: three tests: deterministic output, every item a target xor a reason, exact targets for link / "who" / date / "why"; the no-actor refusal (actor moved off P14); scoring through `interpret` gives "right". Mutation-checked: dropping the "who <p> not already a phrase" guard fails two tests.
- No change to ground.py, plan.py, bundle.py or any vocabulary; no change for `memory_ask`.

### Graph independence
| set | graphs | HER graph id | HER clones (alias Jaccard ≥ 0.9) | independent (own id, < 0.5) |
|---|---|---|---|---|
| arches-lingo | 6 | 0 | 0 | 6 (max overlap 0.02) |
| Catalina | 23 | 16 | 5 | 7: Archive Source, Event, Group, Mātauranga, Registry, Tikanga, Whenua |
| Quartz (checked, not benched) | 19 | 16 | 16 | 3 (Archive Source 0.49, Condition Report, Registry) |

Catalina's 16 HER-id graphs are edited forks (overlap 0.36–0.86 except the 5 clones) and add Catalina's own Z-extension classes (ZE4, ZP75…). Quartz is almost all HER, so Catalina was the second set.

Arches-lingo graphs have `"config": null` on nodes, which Alizarin refuses to parse; the bench reads them with `{}` in memory.

### CRM coverage (link + date nodes)
| set | link+date | with a CRM property | phrased | applied (not dropped as ambiguous) |
|---|---|---|---|---|
| lingo | 49 | 48 | 5 (10%) | 5 (10%) |
| Catalina | 896 | 896 | 123 (14%) | 84 (9%) |
| HER | 399 | 399 | 75 (19%) | 65 (16%) |

Nearly every node has a property (as 023 found), but the 29 hand phrasings reach only 10–19% of them. Most unphrased (HER, Catalina): CRMdig/spatial metadata dates (`D1 L24i D10 P4`, `SP6 P94i D10 P4`, `SP6 P140i E13 P4`: rightly unphrased), sub-activity dates `E7 P9 E7 P4`, attribute-assignment dates `E53 P140i E13 P141`, `E33 P67i E33`, Catalina's `ZE4 … P86i` dates. Lingo: `E13 P14 E39` (attribute-assignment actor), `E13 P16 E33/E70`, `E33 P141i E13 P4`. Catalina's Tikanga, Place, Group, and lingo's four system graphs get nothing.

### Three-way scores (template questions, placeholders filled with synthetic names)
| set | questions (answer/refuse) | mode | right | wrong reading | refused | right refusal | wrong |
|---|---|---|---|---|---|---|---|
| lingo | 24 (22/2) | none | 0 | 0 | 22 | 2 | 0 |
| lingo | | ontology | **18** | 0 | 4 | 2 | 0 |
| Catalina | 345 (320/25) | none | 11 | 16 | 293 | 20 | 5 |
| Catalina | | ontology | **222** | 6 | 92 | 21 | 4 |
| Catalina, 7 independent graphs | 46 (46/0) | none | 0 | 3 | 40 | 0 | 0 |
| Catalina, 7 independent graphs | | ontology | 11 | 0 | 32 | 0 | 0 |
| HER (control) | 277 (251/26) | none | 15 | 13 | 223 | 21 | 5 |
| HER | | ontology | **193** | 7 | 51 | 22 | 4 |
| HER | | ontology + HER base | 189 | 9 | 53 | 22 | 4 |

The question set is built from the layer's own phrasings, so "right" says the layer's phrases ground and read back, not that it covers the graph (coverage above says that). On what it covers, it answers 70–82% where no vocabulary answers 0–5%, with few wrong readings. Adding HER's base costs 4: the base's phrase wins and maps "owned by" on Maritime Vessel to another node (the 023 rule working as designed, but worth a look).

### Why the ontology layer misses (most common first; feeds 027)
1. **"have {X} as <noun>"** ("which areas have Taldrith as copyright holder / author / members / references?"): the largest refusal group (lingo 4, Catalina 47, HER 44: "named Person … and Organization records, but couldn't tell how they relate"; the bench's examples are all this shape). A grammar gap: a noun-phrased link after the name. "copyright owned by X" on the same node answers.
2. **The link's phrase points at another target type**: 19 in Catalina ("archive sources are part of {Registry}" → "Registry isn't a Bibliographic Source, which 'part of' points at"). Bundle phrases are merged per alias across models in `relations()`, so a phrase on `record_or_registry` in one model reaches the same alias with other targets.
3. **Non-ASCII type words**: "mātaurangas" tokenises as "taurangas" (14 refusals; every Mātauranga question).
4. **A dropped verb widens the question** ("when was X made / in use?" → the record itself; "why was X made / in use?" answers instead of refusing: the only "wrong"s, 4 per set). The filler-word bug 023 spotted; task 024's territory.
5. **P107 "member(s)" lands on non-membership nodes** (`rar_approved_by_value`, `planning_body`, `crew_member`): wrong readings on Consultation and "can't join" refusals. P107 needs a narrower path.
6. **A date phrase fits several fields** ("construction date" → did-you-mean over 5 construction-phase dates): a correct refusal, but the layer could key "construction date" to P82a only.
7. **Relation with no target** ("heritage places are part of {Area}" → `LinkTo(relation=None)`): when the phrase was dropped as ambiguous, the planner still links by any relation; a wrong reading in Catalina.
8. **Coverage itself**: 81–90% of link/date nodes have no phrasing; the paths above are the candidates.

### Spec notes
- 023's audit scripts are hard-wired to the 023 worktree; the bench reuses their logic through `crm.chains` / `crm.ontology_entries` instead of the scripts.
- "who written {X}?" comes straight from 023's "who" + date phrase rule; it is ungrammatical but grounds. Left as the layer's phrase.
- HER graphs read from the local clone at `/home/stuart/.cache/tmp-003/arches-her` (no network). `bench/her_plans.py` not run: no grounding, plan or vocabulary change.
- Gate passed on 6331328: root 588 passed (51 skipped, 1 deselected); Ceist 284 passed.

## Graph writes proposed
- Pattern: Catalina's graphs are HER forks (16 of 23 keep HER graph ids, alias overlap mostly 0.6–0.9) with Z-extension classes; 7 are its own. Quartz is 16 of 19 HER ids, all 16 clones. arches-lingo is fully independent (CRM, overlap ≤ 0.02) and its nodes carry `"config": null`, which Alizarin refuses.
- Decision: the ontology layer is measured by `bench/ontology/run.py` with `questions.templated`: deterministic template questions from the layer's own CRM paths, synthetic record names, scored three ways (none / ontology / ontology + base). On 2026-11-08 the layer reaches 10–19% of link/date nodes and answers 70–82% of its own template questions where no vocabulary answers 0–5%.
- Pattern: in Alizarin, graphs register globally by id; load graph sets that reuse ids (HER forks) in separate processes.

## Review rounds
- Round 1 (on 6331328): PASS. Reviewer reran the HER set and the figures matched. Minor notes, none blocking: the `>= 4` in the scoring test is loose, but the two exact assertions before it do the checking; Quartz was checked but not benched (two sets were required); the HER path assumes the local clone.
