# Task: transcript telemetry — context size & token usage in core state

Status: **done — `_transcript_usage` in hook-kit touch_core (context_tokens, last_output_tokens); PRESSURE_TOKENS escalation in the Stop block** · Owner: Stuart · Created: 2026-07-05 · Size: S

## Goal

The hook payload's `transcript_path` points at the session's JSONL transcript, whose assistant
messages carry `usage` (input/output tokens, cache reads). On each dispatch, read the transcript
**tail** (last assistant message only — milliseconds) and add to hook-kit core state:

- `context_tokens` — last turn's input tokens = current context size
- `output_tokens_total` — cumulative session spend
- `cache_hit_ratio`

## Why

Two existing behaviours become context-pressure-aware:

- **Flush escalation:** PreCompact is a last-moment warning; with `context_tokens` trending
  toward the window, the context-counter can escalate *before* compaction (normal cadence at
  40% full, insist at 80%). Distance-to-compaction becomes measurable, not a surprise.
- **Adaptive injection budget:** recall tightens `TOP_N` / raises `ABS_MIN` when context is fat
  — injected memories compete with 150k tokens of live work (requirement N2).

## Notes

- Derive, don't duplicate: the transcript is authoritative; never mirror it into state.
- Belongs in hook-kit's `touch_core` (framework-maintained), guarded fail-open: unreadable/
  absent transcript → fields simply absent.
- Escalation thresholds go in gate.json alongside N_TURNS.

## Test

Fixture transcript JSONL → expected core fields; missing/garbled transcript → no fields, no
error; escalated nudge text at synthetic high `context_tokens`.
