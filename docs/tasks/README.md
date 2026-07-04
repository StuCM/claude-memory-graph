# Task board

One file per task, kept small. Format: `Status: planned | in-progress | done` header,
`[[wiki-links]]` for dependencies. Grouped by the three tools we're building now;
sharing/federation is explicitly **future** work.

## Tool 1 — Retrieval

| Task | Size | Depends on | Status |
|---|---|---|---|
| [[session-start-prime]] — inject recall results at SessionStart | S | — | planned |
| [[prompt-gated-recall]] — ambient analyzer (`gate.py`), deterministic injection | M | — | **done** |
| [[memory-search-tool]] — fuzzy entry-point finder (tool + CLI) | S | — | planned |
| [[grounding-coverage-experiment]] — measure grounder vs real transcripts | S | [[prompt-gated-recall]] | planned |
| [[query-planner-v0]] — compose SPARQL from question shape (`ask` CLI) | L | [[memory-search-tool]] | planned |
| [[temporal-query-modifiers]] — tense → valid-time filters | S | [[query-planner-v0]], [[bitemporal-links]] | planned |

## Tool 2 — Context creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| [[prompt-count-context-trigger]] — deterministic context-write nudge | S | shares hook with [[prompt-gated-recall]] | **done** |
| [[flush-hooks]] — PreCompact/SessionEnd flush + distill suggestion | S | [[prompt-count-context-trigger]] | planned |

## Tool 3 — Distill creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| hard capture rules (name lint, required props, dup guard, provenance) | M | — | **done** (PR #1, `capture_rules.py`, 20 tests) |
| enrichment rules in skills (aliases, concept hubs, anchors) | S | — | **done** (PR #1, docs+skills) |
| [[verb-forms-ontology]] — verbForms + domain/range in base.ttl | S | — | planned |
| [[distill-two-pass-dedup]] — distill searches before writing | S | [[memory-search-tool]] | planned |
| [[bitemporal-links]] — two clocks + contradiction closure | M | — | planned |
| [[code-anchors]] — anchor props + drift flag in recall | S | — | planned |

## Future (not now)

| Task | Doc |
|---|---|
| Share bundles → hosted store → federation gatekeeper | [SHARING.md](../SHARING.md), [FEDERATION.md](../FEDERATION.md) |
| Derived code graph + planner joins | [CODE-GRAPH.md](../CODE-GRAPH.md) |
| Local embeddings behind the matcher | RETRIEVAL.md phase 3 — only if [[grounding-coverage-experiment]] shows misses |

**Suggested order:** session-start-prime → prompt-gated-recall + prompt-count-context-trigger
(one shared hook) → memory-search-tool → flush-hooks → grounding-coverage-experiment →
bitemporal-links → distill-two-pass-dedup → query-planner-v0.
