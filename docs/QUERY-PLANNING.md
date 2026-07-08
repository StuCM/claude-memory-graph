# Query planning — composing SPARQL from language, without an LLM

Status: **v0 implemented** (`planner.py`, `claude-memory-graph ask "…" [--explain]`;
tasks [query-planner-v0](tasks/query-planner-v0.md) and
[planner-telemetry](tasks/planner-telemetry.md)). Part of track B
([RETRIEVAL.md](RETRIEVAL.md)); this is the component that makes retrieval more than RAG.
§"v0 field notes" below records what real usage taught us.

## The problem with what we have

Every SPARQL query in the codebase today is a **hardcoded template**: `find_resource` (exact
model+name), `_neighbours` (everything within one hop), `resource_names`. Whatever the question,
retrieval answers with the same shape — a neighbourhood dump around an entity anchor. That *is*
structurally RAG: match something, return its surroundings. The graph's real power — answering
*differently-shaped questions with differently-shaped queries* — is only reachable today if the
LLM hand-writes SPARQL through `memory_query`.

The goal: a **query planner** that analyses the language of a prompt — nouns, verbs, adjectives,
question words — and *composes* a SPARQL query from building blocks, rather than selecting a
canned one. "What decisions affect the projects Stuart works on?" should produce a two-edge
chain query, not a similarity lookup; that's a question RAG cannot represent, let alone answer.

This is the (pre-LLM) research field of natural-language interfaces to databases — template and
grammar-based text-to-SPARQL (AquaLog, TBSL, quepy). Those systems struggled on open-domain
knowledge bases with huge vocabularies. We're in the easy corner of the problem: a **small,
known, self-describing vocabulary** (seven models, four concept types, ~16 relations with
descriptions, a few hundred node names) — which is exactly the regime where grammar-based
parsing works.

## Why the ontology makes this feasible

The schema graph is the planner's lexicon, and it's already machine-readable:

- **Model names are nouns people actually use.** "decisions", "projects", "people" map to
  `rdf:type mem:Decision/Project/Person` by simple singularisation. A noun that names a model
  becomes a *type constraint on a variable* — the difference between finding node "decision"
  (RAG-think) and binding `?d rdf:type mem:Decision` (query-think).
- **Relations are verbs.** `worksOn`, `uses`, `affects`, `supersedes`, `resolves` — the ontology
  already stores each with an `rdfs:comment`. Add a `mem:verbForms` property to each relation
  ("works on", "working on", "assigned to"…) and the lexicon lives *in the schema graph*: when
  the LLM extends the ontology with a new relation, it supplies verb forms at the same moment —
  the same spend-intelligence-at-write-time move as node aliases, and it makes LLM-added
  relations automatically queryable by the planner with zero code changes.
- **Node names and concept labels are proper nouns** — grounded exactly as the ambient
  analyzer's matcher already does (normalized, alias-aware, rarity-weighted).
- **Question words select the projection.** *who* → Person variable; *what/which X* → type-X
  variable; *why* → the `rationale` property of matched Decisions; *when* → date properties;
  *how* → Pattern's `description`.
- **Adjectives and modifiers become filters and solution modifiers** from a small closed
  lexicon: *recent/latest* → `ORDER BY DESC(?updatedAt) LIMIT n`; *active/open/superseded* →
  `?x mem:status "…"`; *forgotten/old* → invalidation flags; *"about auth"* →
  `CONTAINS(LCASE(?text), "auth")` over property values.
- **Temporal words become valid-time filters** once links carry the two-clock model
  (DISTILL-CREATION.md §8): *currently* → open edges only (`linkValidUntil` unbound — also the
  default); *used to / previously / former* → closed edges (`linkValidUntil` bound, kind
  `worldChange`); *last year / in February / before the rewrite* → valid-time overlap
  `FILTER(?from <= <end> && (!BOUND(?until) || ?until >= <start>))`. "Who used to work on
  quartz?" becomes mechanically answerable — tense is just another modifier lexicon.

**Lexicon entries map phrases to *path templates*, not single predicates.** Our reified
CrossLinks already mean "X affects Y" compiles to a multi-triple pattern through a link node —
so the composer is path-native from day one. That generalisation is exactly what larger
ontologies need: in CIDOC CRM, "painted by" is not a property but a path
(`?work ← P108i_was_produced_by → E12_Production → P14_carried_out_by → E39_Actor`), i.e. a
longer template through typed intermediates. Same machinery, longer templates.

## Scaling to large ontologies (CIDOC CRM, Arches)

The lexicon-first design survives scale because big ontologies are *more* self-describing, not
less: CIDOC ships natural-language labels and scope notes for every class and property — the
verb-form lexicon pre-built by a standards committee. What scale actually changes:

- **Ground against the projection layer, compose against the ontology.** Nobody speaks in E/P
  numbers. Arches already builds the needed mapping: resource models and cards are
  human-vocabulary projections ("Artist", "Production date") over CIDOC paths, and its SKOS
  thesauri are our concepts graph at industrial strength. The planner grounds user language in
  that layer and emits CIDOC-path SPARQL underneath. Our seven-model ontology is a degenerate
  case of the same pattern — path templates harvested from resource-model definitions instead of
  hand-written.
- **Entity grounding needs a real index** — millions of resources means a text index (FTS side
  index, or the hosted store's) behind the same matching contract.
- **Ambiguity becomes normal** — many resources share labels; disambiguate by the question's
  type constraints and graph proximity to context anchors, and below confidence, refuse rather
  than guess (unchanged discipline, higher stakes).
- **Class hierarchies need expansion** — "actors" must match E21 Person and E74 Group:
  `rdfs:subClassOf*` property paths, which SPARQL evaluates natively.

## Pipeline

```
prompt ─► shape check ─► ground words in vocabulary ─► compose BGPs ─► execute
             │                (lexicon-first,               │             │
             │                 POS for leftovers)           │        empty/low-conf?
             ▼                                              ▼             ▼
       statement-shaped ──────────────────────► ambient injector    fall back to
       (not a question)                          (entity anchor +   neighbourhood
                                                  neighbourhood)        recall
```

1. **Shape check** — is this a question (wh-word, auxiliary inversion, trailing `?`) or working
   prose? Statements route to the ambient injector (RETRIEVAL.md) unchanged; the planner handles
   question-shaped prompts. Rule-based, cheap.
2. **Ground** — *lexicon-first, parser-second*: because the vocabulary is known and small, most
   content words ground by direct match (model nouns, relation verb-forms, entity names/aliases,
   modifier lexicon) without any linguistic analysis. A POS tagger earns its place only for the
   leftovers — deciding whether an unmatched word is a noun worth fuzzy-matching against entity
   names or an adjective worth checking against the modifier lexicon. Options, in order of
   weight: pure rule-based tagging over the closed lexicons (zero dependencies), a classical
   tagger (NLTK perceptron), spaCy's small pipeline (~ms, local, brings noun-chunking and
   lemmatisation). All deterministic, none an LLM.
3. **Compose** — assemble basic graph patterns from grounded pieces. The builder knows one
   non-obvious thing: edges are **reified CrossLinks**, so "X affects Y" emits the
   link-node pattern, not a direct triple:

   ```sparql
   GRAPH <…/links> { ?l1 a mem:CrossLink ; mem:linkSource ?d ; mem:linkTarget ?p ;
                     mem:linkRelation "affects" . }
   ```

   Composition rules: each grounded entity → a bound anchor; each model noun → a typed variable;
   each relation verb → a CrossLink pattern joining two of them (direction from word order and
   the relation's domain/range, both in the schema); each modifier → FILTER / ORDER / LIMIT;
   the wh-word picks the SELECT projection. Unbound combinations join through shared variables —
   chains fall out naturally.
4. **Execute with confidence gating** — run the composed query only when grounding coverage is
   high (most content words grounded, all relations resolved). Low coverage or an empty result
   degrades to entity-anchored neighbourhood recall — the planner's floor is exactly today's
   behaviour, never worse.

## Does the planner iterate — use one query's output to build the next?

Mostly **no**, and the reason is the most SPARQL-ish idea in the whole design. What *looks* like
it needs two searches — "first find the projects Stuart works on, then find decisions affecting
those projects" — is **one query with a shared variable**:

```sparql
?l1: stuart —worksOn→ ?p        # "output" of step one...
?l2: ?d —affects→ ?p            # ...is just ?p, joined declaratively
```

The chaining happens *inside* the database engine via the join on `?p` — the intermediate
result never surfaces, no second search is composed, and the engine optimises the whole chain
at once. Composing one structurally-rich query beats iterating shallow ones wherever the next
step doesn't depend on *judgement* about the previous step's results.

What the planner consumes to build a query is therefore not prior *results* but the prior
*vocabulary*: the ontology, verb forms, entity names and aliases — all read from the graph.
The graph shapes the query; the query then runs once.

That said, three places where output genuinely does feed a next query:

1. **The gate already does it** (implemented): scoring picks winners, then a *second, targeted*
   query fetches each winner's links so the injection carries the neighbourhood. Cheap
   two-step, no judgement in between — just "now zoom in on what won".
2. **The planner's fallback** (designed): an empty or low-confidence result degrades to
   entity-anchored neighbourhood recall — a different *strategy*, chosen by the first
   attempt's outcome.
3. **Conversational drill-down** (future, and it's the model's job, not the planner's): "what
   decisions affect quartz?" → answer → user: "why the second one?" The follow-up needs
   judgement about which result mattered — exactly where an LLM belongs, using `memory_recall`
   /`memory_query` on the answer it can already see. The planner stays a one-shot translator;
   iteration-with-judgement lives above it.

## Worked examples

**"What decisions affect the projects Stuart works on?"**
Ground: *decisions* → type Decision · *affect* → `affects` · *projects* → type Project ·
*Stuart* → Person "Stuart Marshall" · *works on* → `worksOn`. Compose:

```sparql
SELECT ?dName ?rationale WHERE {
  GRAPH ?g1 { ?d a mem:Decision ; mem:name ?dName .
              OPTIONAL { ?d mem:rationale ?rationale } }
  GRAPH ?g2 { ?p a mem:Project . }
  GRAPH <…/links> {
    ?l1 a mem:CrossLink ; mem:linkSource ?d ; mem:linkTarget ?p ; mem:linkRelation "affects" .
    ?l2 a mem:CrossLink ; mem:linkSource <stuart-iri> ; mem:linkTarget ?p ;
        mem:linkRelation "worksOn" .
  }
}
```

A two-hop *structural* answer — the README's flagship question, currently unreachable without
the LLM hand-writing SPARQL.

**"Why did we choose pyoxigraph?"**
*why* → project `rationale` · *choose* → Decision prior · *pyoxigraph* → grounded entity.
Compose: Decisions whose name/properties mention pyoxigraph, or linked to Technology
"pyoxigraph"; project name + rationale. The answer is the why itself, not a neighbourhood dump.

**"Any recent decisions about auth?"**
*decisions* → type · *recent* → `ORDER BY DESC(?updatedAt) LIMIT 5` · *auth* (ungrounded
leftover noun) → `CONTAINS` filter over name + property text.

## Why the planner does NOT replace the gate

The obvious question: once the planner exists, what's the point of the gate? Answer: **they
accept different inputs and do different jobs — and the gate's input is far more common.**
Watch two real prompts:

**"Refactor the dispatcher to batch saves instead of saving per mutation"** — a statement of
work, not a question. There is nothing for a planner to translate: no wh-word, no relation
expressed, no answer requested. But it's exactly where the gate earns its keep: "saves per
mutation" matches `Decision "Save after every mutating tool call"` and its rationale arrives
*unasked* — the difference between the model preserving the atomic-rename behaviour and
breaking it. Background knowledge, surfaced while you work on something else.

**"What decisions affect the projects Stuart works on?"** — where the gate is structurally
weak: bag-of-words similarity cannot express the join. The planner's territory: an actual
answer to an actual question.

| | Gate (ambient injector) | Query planner |
|---|---|---|
| Input shape | any prompt — mostly statements of work | question-shaped prompts only |
| Question it answers | *does this work touch anything we know?* | *what is the answer to what you asked?* |
| Output | neighbourhood context, unasked | answer rows |
| Frequency | every prompt, hundreds a day | the handful of genuine graph-questions a day |

The desk analogy: the gate is a colleague who overhears what you're working on and silently
slides a relevant note across the desk; the planner is the archivist you walk up to with a
precise question. You don't fire the colleague because the archivist exists — they're useful
at different moments, and the colleague is useful far more often.

Two structural reasons this isn't duplication:

- **They share parts, not jobs.** The planner's entity-grounding step *is* the gate's matcher —
  same lexicon (names, aliases), same normalization, same scoring signals. The planner adds
  relation/type/modifier grounding and composition on top; building it reuses the gate rather
  than reimplementing it. And the planner *falls back to the gate* on weak grounding or empty
  results — the gate is the planner's floor.
- **Dropping the gate resurrects the original problem.** If retrieval only happened through
  question-answering, memory would only surface when someone asks — the "model must remember to
  ask" failure the entire ambient design exists to kill. The gate is what makes this a *memory*
  (experience surfacing unbidden) rather than a database with a nice query interface. The
  planner makes the database half excellent; the gate makes it memory.

And versus RAG: RAG's only primitive is *similarity* — "what stored text resembles the prompt?"
The planner's primitive is *structure* — joins, chains, aggregation, projection. Similarity
remains one grounding signal (finding the anchors); the question's *shape* drives the query.

Federation note: composed queries run against the local store plus imported shared graphs. They
do **not** cross the network — remote stores still expose only the per-hop `expand` gatekeeper
(FEDERATION.md); the planner treats remote knowledge as reachable through cached/shared graphs,
not as a federated SPARQL target. Arbitrary remote queries remain deliberately impossible.

## v0 field notes — failure modes real questions exposed

Three lessons from the first day of live asks, each now encoded in the planner:

- **Anchor shadowing.** Two nodes sharing name words tie lexically: "memory graph"
  matched both the Project and a Decision *about* memory-graph, sending `worksOn` at a
  Decision (zero rows). Fix: **anchor role fit** — the grounded relations'
  domain/range hints prefer a near-tied (≥0.75×top) name-hit candidate of the type the
  relation expects.
- **CONTAINS poisoning.** The one-leftover-noun CONTAINS escape hatch assumes the
  leftover is a content noun ("auth"). When it's a relation verb that failed to ground
  ("involved", or the typo "commited"), the text filter kills an otherwise-correct
  loose-link query. Fix: a final **retry rung** — in the anchor + typed-variable +
  no-grounded-relation shape, drop the CONTAINS and answer from links alone, labelled
  `(ignored ungrounded '<word>' — the link structure answered without it)` so the
  guess is visible. The retry ladder for that shape is now: link-attach with CONTAINS →
  text-mention attach → link-attach without CONTAINS → fallback.
- **Vocabulary gaps converge; don't enumerate up front.** Every ask logs to
  `ask-decisions.jsonl`; `claude-memory-graph asks` joins the log into *misgrounding
  suspects* (a verb form that fires but never produces rows) and *vocabulary gaps*
  (ungrounded terms in failed asks, including dropped-CONTAINS words). Each gap is
  fixed once, permanently — `memory_amend_relation` for LLM-added relations, base.ttl
  (+ version bump) for built-ins; the reflect skill's step 6 runs this loop. Phrasings
  are Zipf-distributed: curate the head from evidence rather than guessing the tail.
  Only if gaps prove synonym-shaped does the embeddings tier (RETRIEVAL.md phase 3)
  earn its dependency.

## Phasing (extends RETRIEVAL.md's)

1. **Planner v0** — shape check + lexicon-first grounding + composition for the core grammar:
   one or two typed variables, one or two relation edges, entity anchors, recency/status
   modifiers, CONTAINS fallback. No parser dependency; measure grounding coverage on real
   prompts from the injection log.
2. **Planner v1** — `mem:verbForms` on relations (base.ttl + extension flow), alias-aware
   grounding shared with the ambient injector, domain/range-informed edge direction, POS tagging
   for leftover-word handling if v0's rules prove insufficient.
3. **Planner v2** — aggregation (*how many*), negation (*which projects don't use…*),
   comparative modifiers, and planner-composed queries offered to the LLM as a starting point in
   `memory_query` errors ("did you mean this query?").
