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

### 1. Describe: every source read as an Alizarin graph

> **Superseded (2026-11-04):** the intermediate shape is an **Alizarin graph**, not
> a new `ceist.schema/1` format. Non-Arches sources are mapped into one
> (`build_graph_from_instructions` / `json_tree_to_tiles`), and the description is
> produced from it. See [[ceist-alizarin-layer]] ("Beyond Arches"), which also
> covers where queries run for non-Arches sources. The group table below still
> describes what each source's mapping must produce. The JSON sketch is kept only
> as the list of fields the description must carry. Controlled lists are the
> primary value kind, and "private" is enforced by Alizarin's permitted nodegroups.

`ceist vocab describe` today is Arches-only (Alizarin). Originally proposed: an
intermediate format the rest of the pipeline reads, with one adapter per source:

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

### Layout: one file per nodegroup (built)

A graph's vocabulary is built once, for the whole graph, and kept as one file per
nodegroup:

```
vocab/manifest.json                    {"format": "ceist.vocab-groups/1", "models": {"Monument":
                                         {"graphid": …, "nodegroups": {"construction_phases":
                                           {"id": …, "parent": null, "description_sha256": …}}}}}
vocab/Monument/construction_phases.json   {"model", "nodegroup", "entries": [...]}
```

- A group file's `group` key is reserved for the group's own block ([[ceist-group-grounding]]).
- `ceist vocab describe` gives each node its `nodegroup` (the alias of the group's top
  node) and each description a `nodegroups` table, so `ceist vocab split <descriptions>
  <vocab dir>` turns the old one-file-per-model layout into this one.
- `assemble` reads either layout. With `manifest.json` present, it reads the split one and
  warns about each old file it ignores. Both give the same bundle: a model's entries are
  ordered by nodegroup.
- `ceist vocab check <bundle> <graphs> --vocab <dir> --descriptions <dir>` lists the groups
  whose description changed, appeared or went. Those groups are the ones to rebuild.
- `bench/her/vocab` holds both layouts for now. The demo's `ask.py` reads the old files,
  and `learn`/`merge` still write them. Re-run `split` after a merge, until the old files go.

### Slice: only what a dataset uses (built)

```
ceist vocab slice <bundle.json | vocab dir> --data <business_data dir> --graphs <graphs dir> \
                  -o <out> [--reference <reference_data dir>]
```

This reads the business data on the machine it runs on, and nothing goes to an LLM. It keeps:
- the nodegroups that hold tiles, plus their ancestors;
- links whose target model has records (a target that isn't among the graphs leaves the
  link open, as `ArchesVocabulary.relations()` reads it);
- with `--reference`, the qualified entries whose value occurs in the data, or is broader
  than a value that does ("listed" covers "Grade II").

It prints the size before and after, and what it dropped. The cuts are recorded under
`sliced` (`models`, `groups`, `links`, `values`), in the bundle or in the sliced manifest,
so a refusal can later say "this dataset holds no construction phases". Nothing reads that
record yet. On the demo, Monument keeps 7 of its 38 nodegroups, and the bundle goes from
145 KB to 17 KB with every demo answer unchanged.

### Pipeline: the scripted LLM build (built, Arches)

```
ceist vocab pipeline <graphs dir> -o <out> [--reference <reference_data>] [--questions real.txt]
                     [--seed <bundle | vocab dir | phrasings.json>]
                     [--llm-cmd CMD] [--model M] [--models A,B] [--config ceist.toml]
                     [--min-right N] [--max-dangerous N] [--jobs N]
```

It runs describe → CRM roles → one analysis per nodegroup → type words and link wording per
model → a collision pass per model →
questions → assemble → gate → coverage report, and exits 1 when the gate fails.
`<out>` holds `descriptions/`, `vocab/` (split layout), `cases.json`, `bundle.json`,
`report.md`, `collisions.json`, `audit.jsonl` and `cache/`.

- **The LLM.** By default each prompt is piped to Claude Code headless, over the user's
  subscription: `claude -p --output-format json --tools "" --strict-mcp-config
  --setting-sources project --no-session-persistence --system-prompt …`, run from an empty
  temporary directory. `--tools ""` removes every built-in tool, `--strict-mcp-config`
  every MCP server, and `--setting-sources project` (an empty directory has none) drops the
  user's hooks and plugins. `--model` goes to `claude`. `--llm-cmd` replaces it with any
  command that reads the prompt on stdin and prints the reply. There is no API-key path.
  On 2026-11-05, `claude -p` run from inside a Claude Code desktop session failed with
  "OAuth session expired and could not be refreshed": the CLI's stored login there is the
  app's to refresh. Run the pipeline from a terminal where `claude` is logged in.
- **The cache.** A nodegroup's reply is kept under a hash of the prompt version, `--model`,
  the model's name, the group's name and its described nodes (with their CRM roles). Change
  one group and only that group, plus its model's collision pass, is asked again. The
  outline and the prompt text aren't in the key: bump `PROMPT_VERSION` when a prompt changes.
- **Failures.** A reply that fails its check twice, or a call that errs or times out
  (30 minutes), is recorded and not cached, and the run goes on. The report lists the failed
  calls at the end, and a rerun asks only those again.
- **The audit.** Every call appends `{kind, model, group, ts, sha256, prompt}` to
  `audit.jsonl`. Cache hits aren't calls, so they aren't logged again.
- **CRM roles,** a deterministic pre-pass over the graph (`pipeline.crm_roles`). A node's
  role comes from its own class, then the property into it, and for a literal from the class
  of the node it describes: `E52`/`E61` or `P82a`/`P82b` → date (a `P82a` node names its
  `P82b` sibling as `pairs_with`), `E39`/`E21`/`E74` or `P14` → actor, `E53` or `P53`/`P7`/`P89`
  → place, `E41` or `P1` → name, `E42` → identifier, `E55` via `P2` → type, a `P3` note →
  description. The inverse property goes in `reverse` (`P14` → "performed"), for reverse
  phrasings. The roles go to the LLM as `hint`s to confirm or correct. They aren't written
  into the descriptions, so the manifest hashes don't move.
- **One analysis per nodegroup,** with the model's outline in context. The reply is checked
  against the description (`pipeline.check_group`), and a reply that fails is asked once
  more, with the errors. A group that fails twice is reported, not written:

  ```json
  {"purpose": "…", "skip": null | {"reason": "…"}, "phrases": ["…"],
   "nodes": {"<alias>": {"role": "date|actor|place|type|name|…", "phrases": [], "end_node": "…"}},
   "combos": [{"phrases": [], "node": "<alias>", "set": {"<alias>": "<value>"}}],
   "intents": [{"intent": "filter|list|count|when|who|where|which kind", "with": [], "wordings": []}]}
  ```

  Each node with phrases becomes an entry, and so does each combo that sets one value (a
  qualified entry). The group file also gets the reply as its `group` block, in the shape of
  [[ceist-group-grounding]] §2: `phrases`, `nodes` (role, end node), `combos` (`phrases`,
  `set`), `answers` (when/who/where, from the roles), plus `purpose`, `skip` and `intents`.
  Combos that set several values live only there, until 005 reads them.
- **Units.** A `E58`/`P91` node gets the role `unit`. `check_group` rejects phrasings on a unit
  (the first run gave "in grams" to the unit, so "weight in grams" answered with it): people
  ask about the measured value, and a unit only describes it.
- **Type words and link wording** (round two, 006). One more call per model
  (`pipeline.name_model`) asks for the everyday nouns for its records ("stories", "tales" for
  Tale) and, for each link to a model in the build, short phrasings for the pair it joins
  ("in", "located in" for Monument→Site `named_location`), with reverse phrasings from the CRM
  inverse. A link back to its own model gets no reverse phrasings, since the types can't tell
  the direction. A type word that names another model is refused, and one two models claim is
  dropped from both (`settle_type_words`). The words go in the manifest, then the bundle's
  `extra_type_words`, which `ArchesVocabulary` reads. Its own `extra_type_words` argument wins.
  The link phrasings join each link's entry in its group file.
- **Seeds** (`--seed`, repeatable): phrasings already in use, as a bundle, a vocab directory,
  or a JSON file shaped like `ArchesVocabulary`'s arguments (`extra_type_words`,
  `relation_forms`, `date_forms`, the latter two keyed by alias in every model). Node seeds go
  to the group call and link seeds and type words to the model call. The LLM may add to them
  and list doubts, but it can't remove them: they stay in the vocabulary, and the collision
  pass never strips one. The report lists the doubts. Qualified entries aren't seeds.
- **Collisions.** `bundle.shared_phrases` (what `validate` warns about) goes back to the
  LLM once per model. It keeps each phrase on one entry, or leaves it on all of them as
  deliberately ambiguous. The decisions are in `collisions.json`. A phrase that only
  unqualified links share, with no target model in common, isn't sent: the grounder picks
  between them by the types a question names (`ground._fit_relations`), so "in" stays on
  both `named_location` (→ Site) and `parent_monument_or_area` (→ Monument).
- **Questions.** A separate prompt per model, given the description but never the
  vocabulary, writes 8–12 cases. Two of them expect a refusal. Each case says what the whole
  question means, as `expect.conditions` (`{node, value?, tile?, link?}`, `link` being the
  target model; empty for the type alone), besides the phrase and node the phrase level scores.
  `--questions` lines are masked (`learn.mask`), and one call labels them, with conditions;
  a label may name no phrase, and that case is scored at the planner level only. The case
  keeps the raw text locally.
  `cases.json` is frozen: when it's already in `<out>`, it's reused. When a question call
  failed, the cases go to `cases.unfrozen.json` instead, so a rerun asks again.
- **The gate.** `ceist eval` at the phrase level, plus every case through `interpret`
  (graphs and reference data loaded, no records). A plan is right when it's of the case's
  model and holds every expected condition (a date by either end), or, for a case without
  conditions, uses the expected node and qualifier value. One missing is partial. It's
  dangerous when it answers a case that expects a refusal, or answers with another type,
  node, value, tile or link target. `--min-right` applies to the phrase level, and `--max-dangerous` to both levels. With
  no cases at all, the gate fails when either threshold is given, and warns otherwise.
- **Against the hand-tuned vocabulary:** `bench/demo_compare.py <starches-demo>/ask <out>/bundle.json`
  runs the demo README's questions through the demo's `ask.answer` with both, and prints the
  answers that differ.
- **Coverage** (`report.md`): per model, the nodegroups built, skipped on purpose (with a
  reason), missed (no phrasings, no reason) and failed, and the nodes with no phrasings,
  split the same way.

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
ceist vocab pipeline <source>        # all of the above, stops at the gate (built for Arches)
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

[[ceist-alizarin-layer]] (the data layer every source is read through) ·
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
