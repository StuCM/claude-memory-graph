---
id: 026
slug: ontology-only-fresh-graph
status: approved
branch: crew/026-ontology-only-fresh-graph
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
