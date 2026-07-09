# Task: automatic distillation

Status: **done — better than planned: mechanical, at server start, no LLM**
(`distill.auto_distill`, called from `__main__._run`) · Owner: Stuart ·
Created: 2026-07-05 · Size: M

## As built (2026-07-09)

The original plan (below) evaluated claude-mem's bet: an **LLM** run per session at
SessionEnd. The mechanical lane made a strictly better version possible — automatic
promotion with **zero LLM involvement**:

- **When:** every MCP server start (= every new session). The server that holds the
  graph in memory does the promoting, so there is no cross-process clobber race.
- **What:** `distill(store, keep=True)` — **promote-only**. Files are never marked or
  archived headlessly. Upsert-by-name plus idempotent link creation
  (`store.create_link` returns an identical open edge instead of duplicating) make the
  run repeatable; if a concurrent session's save ever clobbers promoted nodes, the
  still-active files simply re-promote them next startup — **self-healing**.
- **Quality:** unchanged — the hard capture rules run, and anything questionable is
  refused to the residue exactly as in the manual lane. The unattended process only ever
  does the boring, safe part; judgment still waits for `/memory-graph:distill`.
- **Observability:** each run logs to `capture.jsonl` (`kind: distill`); `pulse` and the
  dashboard report the runs. SessionEnd's suggestion now frames the skill as
  residue-handling + archiving, not promotion.
- **Off switch:** `MEMORY_GRAPH_AUTO_DISTILL=0`.

What the human still does: run `/memory-graph:distill` occasionally to judge the
narrative residue and archive clean files. Promotion itself needs no one.

## Original framing (kept for the record)

claude-mem compresses *every* session automatically at SessionEnd (agent-sdk
summarisation). Ours was human-invoked as a quality gate; the middle ground evaluated
here was a headless `claude -p` distill run. The cost and quality objections to that
(an LLM run per session; unattended promotion judgment) are exactly what the mechanical
lane eliminated — the ordering dependency on write-time dedup is satisfied by the
duplicate guard refusing to residue rather than creating twins.
