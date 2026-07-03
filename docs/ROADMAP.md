# Roadmap — the system in four subsystems

The project is one loop — **capture → store → retrieve** — that we eventually want to run across
a network of stores. The loop breaks into four subsystems, worked on independently:

| Subsystem | Question | Doc |
|---|---|---|
| **1. Retrieval** | How do memories reach the context window, unasked? | [RETRIEVAL.md](RETRIEVAL.md) (ambient injector), [QUERY-PLANNING.md](QUERY-PLANNING.md) (dynamic SPARQL) |
| **2a. Context creation** | How is in-session knowledge logged so nothing is lost? | [CONTEXT-CREATION.md](CONTEXT-CREATION.md) |
| **2b. Distill creation** | How is knowledge promoted into the graph so retrieval can be dumb? | [DISTILL-CREATION.md](DISTILL-CREATION.md), [CAPTURE.md](CAPTURE.md) |
| **3. Orchestration** | How do the loops fire reliably — hooks, prompt counting, nudges? | [ORCHESTRATION.md](ORCHESTRATION.md) |

Beyond the loop sit the horizons: **sharing and federation** ([SHARING.md](SHARING.md) →
[FEDERATION.md](FEDERATION.md)) — hosted per-person DBs, cross-model persistence, and a
policy-gated network of stores — and **code knowledge** ([CODE-GRAPH.md](CODE-GRAPH.md)) — the
semantic *why* overlay in memory, joined via code anchors to a mechanically derived,
commit-regenerated structural graph.

Creation is deliberately split in two: **context creation optimises for completeness** (a
lossy-tolerant write-ahead log — losing a decision is the failure) while **distill creation
optimises for quality** (the graph is forever — a junk node is the failure). One blurred
pipeline can't serve both objectives; two subsystems with opposite biases can.

## How the subsystems interlock

- **Creation gates retrieval.** The analyzer is deterministic and cheap *only because* every
  association it needs was precomputed at write time — names carrying distinctive tokens,
  aliases closing paraphrase, concept hubs as the associative index, verb forms grounding the
  query planner. Retrieval is only allowed to be dumb because distillation is smart.
- **Retrieval and distill share primitives.** The fuzzy matcher serves prompt grounding on the
  read side and the duplicate guard on the write side; the grounding lexicon is read from the
  graph itself.
- **Orchestration carries both loops.** The injection loop (analyzer on every prompt) and the
  capture loop (staleness nudges, flush at compaction/session-end) run on the same hook
  adapters, session state, and prompt counting.
- **Creation feeds the horizon.** Provenance stamped at write time (`capturedBy`,
  `sourceContext`, `sourceDocument`) is the attribution and trust substrate sharing/federation
  are built on.

## Sequencing

Validate the loop on one person's store before scaling it to a network — a federation of
low-quality, rarely-recalled memories is just distributed noise.

1. **Now:** orchestration phase 1 (session state, prompt counting, session-start priming) +
   distill-creation rules into the skills and tool descriptions (hard subset already
   implemented) + `memory_search`.
2. **Next:** the ambient injector (lexical analyzer, thresholds, injection log) + context
   nudge loop + measure grounding coverage on real prompts.
3. **Then:** query planner v0; sharing phase 1 (bundles); distill two-pass dedup.
4. **Later, justified by observed pain:** local embeddings; hosted store; federation
   gatekeeper; larger-ontology grounding (CIDOC/Arches path templates).
