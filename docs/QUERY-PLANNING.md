# Query planning — composing SPARQL from language, without an LLM

Status: **exploration, not yet implemented.** Part of track B ([RETRIEVAL.md](RETRIEVAL.md));
this is the component that makes retrieval more than RAG.

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

## Where this sits relative to RAG — and the ambient injector

The planner is the answer to "isn't this just RAG?": RAG's only primitive is *similarity* —
"what stored text resembles the prompt?" The planner's primitive is *structure* — it represents
joins, chains, aggregation ("how many projects use rust?"), and property projection. Similarity
remains one grounding signal (finding the anchors), but the question's *shape* drives the query.

The two retrieval modes share everything below the surface: the same grounding lexicon (names,
aliases, verb forms), the same provenance-filtered graphs, the same silence-on-low-confidence
discipline. Statement-shaped prompts get neighbourhood injection (ambient working context);
question-shaped prompts get composed queries (answers). Both no-LLM, both falling back
gracefully to the other.

Federation note: composed queries run against the local store plus imported shared graphs. They
do **not** cross the network — remote stores still expose only the per-hop `expand` gatekeeper
(FEDERATION.md); the planner treats remote knowledge as reachable through cached/shared graphs,
not as a federated SPARQL target. Arbitrary remote queries remain deliberately impossible.

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
