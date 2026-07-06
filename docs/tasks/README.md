# Task board

One file per task, kept small. Format: `Status: planned | in-progress | done` header,
`[[wiki-links]]` for dependencies. Grouped by the three tools we're building now;
sharing/federation is explicitly **future** work.

## Tool 1 — Retrieval

| Task | Size | Depends on | Status |
|---|---|---|---|
| [[session-start-prime]] — inject recall results at SessionStart | S | — | **done** (RecallExtension.on_session_start) |
| [[prompt-gated-recall]] — ambient analyzer (`gate.py`), deterministic injection | M | — | **done** |
| [[memory-search-tool]] — fuzzy entry-point finder (tool + CLI) | S | — | **done** (tools/search.py — shares the gate's corpus/scoring) |
| [[grounding-coverage-experiment]] — measure grounder vs real transcripts | S | [[prompt-gated-recall]] | **harness ready** (`claude-memory-graph coverage` — run after a few days of real sessions; decision table in the task file) |
| [[recall-miss-detector]] — explicit recalls after silence = auto-labelled misses | S | [[prompt-gated-recall]] | **done** (gate/misses.py, `claude-memory-graph misses`, docs/TUNING.md) |
| [[query-planner-v0]] — compose SPARQL from question shape (`ask` CLI) | L | [[memory-search-tool]] | planned |
| [[temporal-query-modifiers]] — tense → valid-time filters | S | [[query-planner-v0]], [[bitemporal-links]] | planned |

## Tool 2 — Context creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| [[prompt-count-context-trigger]] — deterministic context-write trigger | S | shares hook with [[prompt-gated-recall]] | **done** (escalated: overdue log now blocks `Stop` instead of injecting a nudge) |
| [[flush-hooks]] — PreCompact/SessionEnd flush + distill suggestion | S | [[prompt-count-context-trigger]] | **done** (ContextCounterExtension) |
| [[transcript-telemetry]] — context size/token usage in core state; pressure-aware flush | S | [[flush-hooks]] | planned |
| [[observation-capture]] — mechanical tool-observation lane via PostToolUse (claude-mem learning) | M | — | planned |
| [[private-tags]] — <private> exclusion across capture, distill, and gate (claude-mem learning) | S | — | planned |

## Tool 3 — Distill creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| hard capture rules (name lint, required props, dup guard, provenance) | M | — | **done** (PR #1, `capture_rules.py`, 20 tests) |
| enrichment rules in skills (aliases, concept hubs, anchors) | S | — | **done** (PR #1, docs+skills) |
| [[verb-forms-ontology]] — verbForms + domain/range in base.ttl | S | — | **done** (base.ttl 0.4.0, relation_lexicon(), extension flow requires verb forms) |
| [[structured-context-entries]] — RDF-ready context entries; distill folds instead of re-deriving; phase-2 mechanical (no-LLM) distiller | M | — | **phase 1 done** (protocol + distill skill); parser planned |
| [[distill-two-pass-dedup]] — distill searches before writing | S | [[memory-search-tool]] | planned (absorbed into [[structured-context-entries]] phase 2 for the structured lane) |
| [[bitemporal-links]] — two clocks + contradiction closure | M | — | planned |
| [[code-memory-rules]] — lanes of code knowledge; orientation (storage/layout/wiring) + cost-gated investigation findings (traces) earn Patterns | S | drift flag: [[code-anchors]] | **rules drafted** (protocol + docs wired) |
| [[code-anchors]] — anchor props + drift flag in recall | S | — | planned |
| [[auto-distill]] — headless SessionEnd distillation, gated by hard rules (claude-mem bet, evaluate) | M | [[distill-two-pass-dedup]] | planned |

## Future (not now)

| Task | Doc |
|---|---|
| Share bundles → hosted store → federation gatekeeper | [SHARING.md](../SHARING.md), [FEDERATION.md](../FEDERATION.md) |
| Derived code graph + planner joins | [CODE-GRAPH.md](../CODE-GRAPH.md) |
| Local embeddings behind the matcher | RETRIEVAL.md phase 3 — only if [[grounding-coverage-experiment]] shows misses |

**Suggested order:** session-start-prime → prompt-gated-recall + prompt-count-context-trigger
(one shared hook) → memory-search-tool → flush-hooks → grounding-coverage-experiment →
bitemporal-links → distill-two-pass-dedup → query-planner-v0.
