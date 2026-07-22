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
| gap finder — mechanical link candidates (orphans, conceptless, unlinked pairs by shared rare vocabulary) feeding the reflect skill's judgment | S | — | **done** (gaps.py, `gaps` CLI, appended to memory_reflect; GAP_MIN knob) |
| pulse — one-screen "is memory reaching sessions?" (injections, capture enforcement via capture.jsonl, misses, backlog, diagnoses) | S | — | **done** (gate/pulse.py, `pulse` CLI) |
| doctor — one-shot wiring diagnosis (dead hooks · path mismatch · empty/orphan graph) with prioritised verdict + fix | S | — | **done** (gate/doctor.py, `doctor` CLI) |
| [[session-context-recall]] — index undistilled context entries; per-prompt scored injection (post-compaction recovery, cheap handoffs) | M | [[structured-context-entries]] | **done** (session_corpus.py + `_log_recall`; log = primary layer, shared TOP_N budget) |
| [[query-planner-v0]] — compose SPARQL from question shape (`ask` CLI) | L | [[memory-search-tool]] | **done** (planner.py, `ask --explain`; golden + refusal tests) |
| [[planner-telemetry]] — ask-decisions log, `asks` report, `memory_amend_relation` | S | [[query-planner-v0]] | **done** (lexicon self-correction loop; reflect skill step 6) |
| segment scoring — long descriptive prompts scored per-sentence, best view wins (whole-prompt coverage drowned embedded questions) | S | — | **done** (query_views/score_views in gate + preview) |
| project identity — git-root resolution + CLAUDE_HOOK_KIT_PROJECT override (subdir sessions fragmented the project; drift check now runs from repo root) | S | — | **done** (hook-kit project_of; HANDBOOK §1) |
| [[temporal-query-modifiers]] — tense → valid-time filters | S | [[query-planner-v0]], [[bitemporal-links]] | planned |

## Tool 2 — Context creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| [[prompt-count-context-trigger]] — deterministic context-write trigger | S | shares hook with [[prompt-gated-recall]] | **done** (escalated: overdue log now blocks `Stop` instead of injecting a nudge) |
| [[flush-hooks]] — PreCompact/SessionEnd flush + distill suggestion | S | [[prompt-count-context-trigger]] | **done** (ContextCounterExtension) |
| [[dig-counter]] — PostToolUse counts file-inspection calls; dig turns get a Stop block asking for the trace entry | S | [[code-memory-rules]] | **done** (ContextCounterExtension) |
| [[transcript-telemetry]] — context size/token usage in core state; pressure-aware flush | S | [[flush-hooks]] | **done** (touch_core reads the transcript tail; PRESSURE_TOKENS escalates the Stop block) |
| [[observation-capture]] — mechanical tool-observation lane via PostToolUse (claude-mem learning) | M | — | planned |
| [[private-tags]] — <private> exclusion across capture, distill, and gate (claude-mem learning) | S | — | planned |

## Tool 3 — Distill creation

| Task | Size | Depends on | Status |
|---|---|---|---|
| hard capture rules (name lint, required props, dup guard, provenance) | M | — | **done** (PR #1, `capture_rules.py`, 20 tests) |
| enrichment rules in skills (aliases, concept hubs, anchors) | S | — | **done** (PR #1, docs+skills) |
| [[verb-forms-ontology]] — verbForms + domain/range in base.ttl | S | — | **done** (base.ttl 0.4.0, relation_lexicon(), extension flow requires verb forms) |
| [[structured-context-entries]] — RDF-ready context entries; distill folds instead of re-deriving; phase-2 mechanical (no-LLM) distiller | M | — | **done** (context_entries.py + distill.py + `claude-memory-graph distill`; residue reported for the skill lane) |
| [[distill-two-pass-dedup]] — distill searches before writing | S | [[memory-search-tool]] | **structured lane done** (mechanical distill refuses near-dups to residue); skill-side search-first for narrative still planned |
| [[bitemporal-links]] — two clocks + contradiction closure | M | — | **done** (ontology 0.6.0; closure on singleValued relations; unlink closes by default; reads filter to open edges) |
| [[code-memory-rules]] — lanes of code knowledge; orientation (storage/layout/wiring) + cost-gated investigation findings (traces) earn Patterns | S | drift flag: [[code-anchors]] | **rules drafted** (protocol + docs wired) |
| [[code-anchors]] — anchor props + drift flag in recall | S | — | **done** (tools/recall.py `_drift`: git-only staleness flag, fail open) |
| [[auto-distill]] — automatic promotion of structured entries | M | — | **done** (mechanical, at server start, no LLM; promote-only + idempotent links = self-healing; MEMORY_GRAPH_AUTO_DISTILL=0 to disable) |
| dashboard — self-contained HTML report over the logs (tiles, per-day activity, top memories, gaps, health notes) | S | pulse | **done** (gate/dashboard.py, `dashboard` CLI) |
| [[remote-server]] — shared memory over streamable HTTP (`serve`, bearer auth); tools travel, hooks stay per-machine (v2: remote gate corpus) | M | — | **v1 done** |

## Future (not now)

| Task | Doc |
|---|---|
| Context-window manager — steer compaction, then a proxy shim enabling API context editing (clear raw tool results; memory keeps the distilled). **Deferred: gated on retrieval proving itself** ([[session-context-recall]] live + coverage/miss numbers) | [CONTEXT-WINDOW.md](../CONTEXT-WINDOW.md) |
| Share bundles → hosted store → federation gatekeeper | [SHARING.md](../SHARING.md), [FEDERATION.md](../FEDERATION.md) |
| Derived code graph + planner joins | [CODE-GRAPH.md](../CODE-GRAPH.md) |
| Local embeddings behind the matcher | RETRIEVAL.md phase 3 — only if [[grounding-coverage-experiment]] shows misses |

**Suggested order:** session-start-prime → prompt-gated-recall + prompt-count-context-trigger
(one shared hook) → memory-search-tool → flush-hooks → grounding-coverage-experiment →
bitemporal-links → distill-two-pass-dedup → query-planner-v0.
