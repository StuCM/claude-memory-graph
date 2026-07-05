# Retrieval instigation — when and how recall happens

Status: **gate, search, and miss detector implemented; planner designed.** Track B of
[ROADMAP.md](ROADMAP.md).

## The retrieval stack in one table

One matcher (corpus + IDF + phrase/coverage scoring), one graph, five escalating ways in —
automation decreasing and judgement increasing as you go up, with the top layer's behaviour
flowing back down as tuning data (the miss detector, [TUNING.md](TUNING.md)):

| Layer | Trigger | Question it answers | Output |
|---|---|---|---|
| 0 · Session prime | session start, automatic | what do we know about *here*? | project + person neighbourhood |
| 1 · Gate | every prompt, automatic, **threshold-gated** | does this work touch anything we know? | high-confidence memories *with links*, or silence |
| 2 · `memory_search` | on demand, **ungated** | what might match this phrase? | ranked entry points (doors) |
| 3 · `memory_recall` | on demand, exact | what surrounds this known node? | the neighbourhood (rooms) |
| 4 · Query planner *(designed)* | question-shaped prompts | what is the answer, structurally? | answer rows from a composed query |

Gate and search are the **same matcher with different invocation economics**: the gate speaks
uninvited, so it must be precision-biased and silence-default; search was *asked*, so it always
answers with ranked candidates. The gate's injections deliberately include the winner's links —
threads left hanging so the model (the judgement layer above the stack) can pull them with
recall/search; and every explicit pull it makes is telemetry that tunes the gate.

## The target design: ambient retrieval, no LLM in the loop

The guiding decision for this track: **the model should never have to ask for memories.** A
deterministic process — no LLM — reads each prompt, works out whether the memory graph has
something relevant, and if so injects the memories themselves into context alongside the prompt.
From the model's point of view, memories simply *arrive*, the way a person's relevant experience
surfaces unbidden when they read a question. Explicit `memory_recall` remains available for
deliberate deep dives, but it is the fallback, not the mechanism.

Why no LLM in the retrieval decision:

- **Deterministic and debuggable** — the same prompt against the same graph always injects the
  same memories; when retrieval misfires you can trace exactly why.
- **Fast and free** — it runs on *every* prompt, so it must cost milliseconds and no tokens.
  An LLM pre-pass would add latency and per-prompt cost to the entire assistant.
- **Immune to context decay** — instruction-following degrades as sessions grow; a process
  outside the model doesn't. This is the structural fix for the failure modes below.
- **Private** — prompt analysis happens locally against a local file; nothing leaves the machine
  to decide relevance.

## Why instruction-only retrieval isn't enough (current state)

Retrieval today is entirely **instructed**: the SessionStart hook injects the "Recall First"
protocol ([hooks/context-protocol.md](../hooks/context-protocol.md)) and the server
`instructions` say to recall before re-deriving. Failure modes:

- **Mid-session amnesia** — protocol prose injected at session start loses salience as context
  grows; recall happens at the start of a session or not at all.
- **The exact-name cliff** — `memory_recall` is exact-match on model + name; if the model
  guesses "pyoxigraph choice" for a node named `Decision "use pyoxigraph"`, retrieval silently
  fails and the knowledge might as well not exist.
- **Blind cost trade-off** — the model has no cheap signal that the graph holds anything
  relevant, so it must choose between speculative recalls and skipping, blind.

Ambient injection removes the model's discipline, naming, and judgement from the default path
entirely — which is the point.

## The ambient injector

A `UserPromptSubmit` hook runs a small program (the **analyzer**) with a hard latency budget
(~100ms — it sits in front of every prompt). Pipeline:

```
prompt ──► extract ──► match ──► score ──► (below threshold? inject NOTHING)
                                    │
                                    ▼
                        recall top entry points (read-only, depth 1–2)
                                    │
                                    ▼
                  budget + dedup against session memo ──► inject memories
```

1. **Extract** — tokenize the prompt; drop stopwords; keep candidate entities: code identifiers,
   Cased Words, quoted strings, and content n-grams. Purely lexical, language-dumb, fast.
2. **Match** — candidates against a **lexical index** of the graph: node names, concept labels,
   and property text. The NQuads file is plain text, so v1 can scan it directly; a prebuilt
   side index (rebuilt on save, or on mtime change) keeps latency flat as the graph grows.
   Matching is normalized (case, simple stemming) — this sidesteps the exact-name cliff because
   *the analyzer* does the fuzzy matching, not the model.
3. **Score & decide** — this is the "works out if a memory search is needed" step, and it's a
   threshold, not a vibe: match strength (exact name > partial > property text), node type
   weight (Decision/Pattern/Constraint above Task), link degree (hubs are likelier relevant),
   recency. Below threshold, the analyzer injects **nothing** — silence is a feature; a
   retrieval system that always says something trains the reader to ignore it.
4. **Recall** — for the top-scoring entry points, run the existing traversal (read-only CLI
   path, depth 1–2) so what's injected is the *neighbourhood* — the decision with its rationale,
   the project with its constraints — not a bare name match. Search finds doors; traversal
   explores rooms.
5. **Budget & dedup** — a token ceiling per injection (token-lean output makes this a few
   hundred tokens), and a per-session memo of already-injected node IDs so the same memory isn't
   re-injected every prompt. Re-inject only if a node changed or fell out of plausible context.
6. **Inject** — the memories themselves, marked as coming from the memory graph, attributed and
   terse:

   > memory-graph (auto): Decision 'Use pyoxigraph over rdflib' — rationale: … · Pattern
   > 'SPARQL FILTER on VALUES var must be top-level' — …

**Session start is the same mechanism**, not a separate one: the opening "prompt" is the working
directory and user identity, so the hook recalls the Project node (cwd basename) and Person node
and injects those results. The session begins already primed, again with no model involvement.

### How a no-LLM analyzer makes correct decisions

The analyzer never needs to *understand* the prompt — only to answer a far narrower question:
**does this prompt mention anything the graph knows about?** The graph's vocabulary (node names,
concept labels, aliases) is small and known, and matching free text against a known vocabulary
is classic pre-LLM information retrieval (TF-IDF/BM25 territory), not language understanding.
Correctness comes from stacking cheap signals, each mechanical on its own:

- **Distinctive-term weighting** — a hit on "pyoxigraph" is near-certain relevance; a hit on
  "project" is noise. Weight by token rarity against a general English frequency list plus the
  graph's own vocabulary. One rare-term match outweighs many common-word matches.
- **Signal stacking** — independent matches multiply confidence: a technology term *plus* a node
  in the current project's neighbourhood clears the threshold; a lone fuzzy hit stays silent.
- **Structural priors from the graph itself** — the cwd identifies the Project node, and graph
  distance from it is a relevance prior: a Pattern two hops from the active project outranks an
  identical lexical match linked only to a dormant one. The graph supplies the context-awareness
  an LLM judge would otherwise provide.
- **Type, recency, degree priors** — Decisions/Patterns/Constraints over Tasks; recently updated
  and well-linked nodes rank higher.

**Aliases: spend intelligence at write time, not read time.** The lexical gap is paraphrase —
"the database locking issue" won't string-match `Pattern "RocksDB exclusive lock"`. But at
*capture* time an LLM is already in session, so the capture protocol has it store an `aliases`
property: the two or three phrasings a future prompt would plausibly use. The semantic work is
done once, by the model that's already there, and persisted — read-time matching stays dumb,
fast, and deterministic. (This is a capture rule in service of retrieval — the tracks meet here.)

**The analyzer nominates; the model disposes.** The final relevance judgement was never the
analyzer's job — there *is* an LLM in the loop: the main model reading the injection. The
analyzer over-fetches slightly within its precision threshold and token budget; the model, which
knows the conversation and the user's situation, uses or ignores what arrived. The split is
*cheap mechanical recall of candidates* (analyzer) + *free contextual judgement* (the model
that's already there). What we refuse to add is a second LLM whose only job is deciding whether
to look. Corollary: the associations the analyzer surfaces are only as good as what capture
wrote down — names carrying distinctive tokens, aliases, concept-hub links
([DISTILL-CREATION.md](DISTILL-CREATION.md)). Association is precomputed at write time;
retrieval walks it.

**Aliases vs the index — different layers, weight shifts with scale.** The index (lexical now,
FTS + embedding/ANN at scale) is *derived* data, built mechanically from whatever text exists —
rebuildable, stored outside the graph, no authoring. Aliases are *content*: vocabulary that
isn't in the data (no index over "RocksDB exclusive lock" matches "db locking"). Where the
bridging vocabulary comes from depends on corpus shape: in a personal store, instances are
descriptive phrases with a real paraphrase gap, volume is tiny, and the LLM is present at write
time — per-node aliases are cheap and effective. In a large pre-existing corpus (CIDOC/Arches),
instances are mostly proper nouns (their own best token — the index covers them unaided), and
the paraphrase gap lives in the small conceptual vocabulary — where SKOS
`prefLabel`/`altLabel`/`hiddenLabel` and thesauri like Getty AAT already provide curated
aliases. Rule: **index everything mechanically; alias the vocabulary layer always; alias
instances only where they're phrases, low-volume, and an LLM is already present.** The index
indexes aliases along with everything else — they feed it, they don't compete with it.

**The built-in miss detector.** If the model explicitly calls `memory_recall`/`memory_search`
right after the analyzer stayed silent, that is a logged false negative — free training data for
threshold tuning from real transcripts, no labelling effort.

### Precision, and failing quietly

The failure economics are asymmetric. A **miss** costs what the status quo already costs (the
model can still recall explicitly). A **false injection** pollutes every subsequent turn and
erodes trust in the channel. So: tune for precision over recall, start with a conservative
threshold, and log every injection decision (fired/didn't, scores, what was injected) to a local
file so thresholds are tuned against real transcripts rather than guessed.

### Upgrading the matcher without changing the contract

The analyzer is a swappable component behind a stable contract (*prompt in → zero or more scored
memories out*). v1 is lexical. If observed misses justify it, add a local embedding index
(name + property text per node) — still no LLM in the loop, an embedding model is a local
encoder, and the scoring/threshold/budget machinery is unchanged. Federation later slots in the
same way: remote stores' shared subsets contribute index entries; injection attribution
("shared by alice") comes from provenance.

## Beyond neighbourhood injection: the query planner

Entity-anchored neighbourhood injection is the right answer for statement-shaped prompts
(working context), but it answers every question with the same shape — which is RAG's limitation
wearing our clothes. For **question-shaped** prompts, retrieval should instead *compose* a
SPARQL query from the language — nouns → type constraints and entity anchors, verbs → relations,
adjectives → filters and modifiers, wh-words → projections — so "what decisions affect the
projects Stuart works on?" becomes a two-edge chain query, not a similarity lookup. That
component is specified in [QUERY-PLANNING.md](QUERY-PLANNING.md); it shares the grounding
lexicon (names, aliases, verb forms) and the silence-on-low-confidence discipline with the
ambient injector, and degrades to neighbourhood recall when grounding is weak.

## Secondary paths (the model-driven ones)

Ambient injection is the default path, not the only one:

- **`memory_search(text, model?)`** — fuzzy entry-point finder over names/labels/property text.
  Needed even in the ambient world: it's how the *model* does a deliberate dive when the user
  asks "what did we decide about X?", and it's the same primitive capture-side dedup uses
  (CAPTURE.md). Implementation v1: SPARQL `CONTAINS` — and it should share the analyzer's index
  as that materializes.
- **`memory_recall`** — unchanged; the deep-traversal tool for when a door is already known.
- **Tool descriptions carry trigger guidance** — since MCP travels to any client but Claude Code
  hooks don't, the descriptions still say when to search/recall. On clients without an ambient
  adapter, instructed retrieval is the graceful degradation, not the design.

## The multi-model constraint

The federation vision (FEDERATION.md) means retrieval must not be Claude-Code-only. Layering:

- **Core (travels with MCP):** `memory_search`, `memory_recall`, tool descriptions with trigger
  guidance, and — once stores are hosted — the analyzer itself can move server-side, exposed as
  an endpoint any client adapter calls with the prompt text.
- **Adapter (per client):** the `UserPromptSubmit` + SessionStart hooks are the Claude Code
  adapter for the ambient injector. Other clients implement their own thin adapters over the
  same analyzer.

## Phasing

1. **Phase 1:** session-start auto-prime (hook → CLI recall → inject results) — the ambient
   principle with the simplest possible "analyzer" (cwd + user); `memory_search` tool + CLI
   subcommand; trigger guidance into tool descriptions.
2. **Phase 2:** the prompt-time ambient injector — lexical analyzer, scoring threshold, session
   memo, injection log; tune precision on real use.
3. **Phase 3:** local embedding index behind the same contract, once the injection log shows
   lexical misses that matter; analyzer moves server-side with the hosted store (track A).
