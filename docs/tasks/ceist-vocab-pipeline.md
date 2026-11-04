# Task: ceist — an automated, private, schema-agnostic vocabulary pipeline

Status: planned · Owner: Stuart · Created: 2026-11-04 · Size: L

## Goal

Point ceist at **any schema** (Arches graphs, RDF/OWL/SHACL, SQL DDL, JSON
Schema), run one command, and get a reviewed, measured search vocabulary
that answers natural-language questions with **no LLM at query time**. Then
let it improve from use, with **record data never sent to an LLM**.

This automates the manual flow already proven on HER
(`packages/ceist/bench/ADAPTATION-FLOW.md`: 16 models, 2,327 searchable
nodes; node names alone got 20/102 right, the LLM vocabulary 81/102, and
"did you mean" 94/102 within one click). It doesn't replace it.

## Wording: "training"

Nothing is trained in the ML sense, and that is deliberate. The vocabulary is
phrasings per node and per group, written by an LLM and grown from use. The
domain adapter (`bench/adapt.py`) did **not** beat the baseline on HER. It stays
optional, and ships only if the gate says so. This doc says "build" and "learn".

## Privacy model (the constraint everything else serves)

| Stage | What may leave the machine to an LLM | Never |
|---|---|---|
| build | the schema description: types, nodes, groups, datatypes, link targets, small value-list labels | records, tile data, descriptors |
| learn | unplaced phrases, with **record names and literals masked** in the example questions (`<Person>`, `<Place>`) | raw questions, record names |
| query | nothing | — |

Enforcement, not just instruction:
- **Inline the description into the prompt.** The LLM step gets no file paths and no
  filesystem access. Today `bundle.PROMPT` and `learn.PROMPT` hand an agent paths and
  ask it to "read ONLY…". That is a request, not a guarantee.
- **Mask anchors at log time.** `learn.record` / `from_grounding` replace the spans the
  grounder matched to entities, and any quoted literals, before writing. Raw
  questions are never stored. Today the full `q` is logged, and up to 3 questions
  per phrase go to the LLM.
- **Sensitivity flags in the description.** A node or value list marked `private` is
  described by name and datatype only, with no value labels. Small SKOS
  collections are sent today based on size (≤120), not sensitivity.
- **A pluggable LLM.** A hosted API, or a local model for clients who can't send even
  the schema out (`PLANNED_CHOOSERS` already reserves `local-llm`).
- An audit file per build: exactly what was sent, hashed and kept with the bundle.

## Pipeline

```
schema ──describe──▶ ceist.schema/1 ──build (LLM, per group)──▶ vocab/*.json
                                    ──questions (separate LLM)──▶ cases.json (+ real questions)
vocab ──assemble──▶ bundle ──eval (gate)──▶ ship | stop
use ──log (masked)──▶ learn ──LLM proposes──▶ person approves ──merge──▶ assemble ──eval──▶ ship
```

### 1. Describe: one schema format for every source (`ceist.schema/1`)

`ceist vocab describe` today is Arches-only (Alizarin). Define the intermediate
format the rest of the pipeline reads, with one adapter per source:

```json
{"format": "ceist.schema/1", "source": "arches|rdf|sql|jsonschema",
 "models": {"Monument": {
   "groups": {"construction_phase": {"label": "Construction Phase", "parent": null,
                                     "repeats": true, "context": ["production"]}},
   "nodes": {"construction_phase_type": {"group": "construction_phase", "kind": "property",
                                         "datatype": "concept", "values": ["Construction", "Destruction"],
                                         "private": false}}}}}
```

What a "group" (the unit of [[ceist-group-grounding]]) is in each source:

| Source | type | node | group (one tile / one fact) | link |
|---|---|---|---|---|
| Arches | resource model | node | nodegroup / card | resource-instance node |
| RDF / OWL / SHACL | class | property | blank node / reified statement / SHACL node shape | object property |
| SQL | table | column | the row of a child table (1:n) | foreign key |
| JSON Schema | object | property | nested object / array item | `$ref` |

Each source also needs a `Vocabulary` implementation for query time.
`ArchesVocabulary` and the memory graph's `MemoryVocabulary` exist.
RDF and SQL would be new, and are where most of the work for a new
source goes.

### 2. Build (LLM, one call per group, with the model in context)

- One call per **nodegroup**, with the whole model's outline in context, so sibling
  groups stay distinguishable (`creator_name` vs `monument_name`). It writes the group's
  phrasings, a role per node, combos (qualified meanings), and an explicit
  "not asked about" for metadata, so a skipped node is a recorded decision.
- **A collision pass per model:** `validate` already warns when one phrase belongs to two
  entries. Feed those warnings back to the LLM to resolve, or mark each one as
  deliberately ambiguous (then "did you mean").
- Large value lists are **not** sent. They match through their own labels
  (SKOS preferred/alternative labels, enum values, lookup tables).
- Cached per group by hash of its description. A schema change rebuilds only the
  groups that changed. `ceist vocab check` already detects a stale bundle.

### 3. Questions and gate

- A **separate** LLM call writes the acceptance questions from the description only,
  never from the vocabulary. Real client questions are added, masked. Frozen per
  release; questions found later go into the *next* release's set.
- Cases become end-to-end (question → expected conditions), not just phrase → node.
- The gate is `ceist eval --min-right --max-dangerous`. Nothing ships if dangerous rises.
  A coverage report goes with every build: nodes and groups with zero phrasings,
  split into "skipped on purpose" and "missed".

### 4. Learn from use (the loop that makes it improve)

Already built in part (`learn.py`: `record` → `proposals` → LLM assigns → person
approves → `merge`). To add:
- masking (above);
- **auto-accept only what a person already chose:** a "did you mean" pick seen N times
  with no conflicting picks merges without review. Everything an LLM proposes
  still needs a person, because unreviewed LLM proposals compound errors and
  can be poisoned by crafted questions;
- group-level proposals ("damaged in a fire" → construction_phase + combo), not just nodes;
- **always re-run the gate:** a learned phrasing that raises dangerous on the frozen set
  is rejected, however often it was seen;
- scheduled (monthly or per release). The output is a versioned bundle diff a
  person can read.

## Commands (target)

```
ceist vocab describe <source> --kind arches|rdf|sql|jsonschema -o schema.json
ceist vocab build schema.json -o vocab/ [--llm api|local] [--audit audit.jsonl]
ceist vocab questions schema.json -o cases.json [--add real-questions.txt]
ceist vocab assemble … && ceist eval … --min-right … --max-dangerous …
ceist vocab learn <log> … → review → ceist vocab merge … (exists)
ceist vocab pipeline <source>        # all of the above, stops at the gate
```

## Order

1. Privacy fixes on what exists: inline prompts (no file paths), mask the learn log.
2. `ceist.schema/1` plus the Arches adapter (port `arches_describe.py` onto it; groups included).
3. `ceist vocab build`: per-group LLM calls, collision pass, cache, audit. Matches
   [[ceist-group-grounding]] step 3's bundle v2.
4. End-to-end cases and the coverage report; `pipeline` wraps describe → gate.
5. Learn loop: group proposals, auto-accept of repeated picks, gate on merge.
6. A second source (RDF/SHACL is the likeliest) plus its `Vocabulary`, to prove the
   pipeline really is schema-agnostic.

## Depends

[[ceist-group-grounding]] (the group format and the grounder that uses it). The
HER descriptions, as the first real run.

## Test

- A build from the fixture schema sends nothing but the description: assert on the audit file.
  No resource ids, names or tile values appear in any prompt.
- The learn log contains no anchor or literal text from the questions.
- A schema change to one group rebuilds that group only.
- Gate: a vocabulary change that raises dangerous on the frozen set fails `pipeline`.
- The same pipeline, run on a small RDF/SHACL schema, answers its own case set with no
  changes outside its adapter and `Vocabulary`.
