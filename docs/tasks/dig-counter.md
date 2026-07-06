# Task: dig counter — mechanical trigger for trace capture

Status: **done — ContextCounterExtension.on_post_tool_use + on_stop in gate/nudge.py** ·
Owner: Stuart · Created: 2026-07-06 · Size: S

## Goal

The investigation-findings lane ([[code-memory-rules]]) originally depended on the model
noticing "that was an expensive dig" and recording the finding — the same
instruction-decay bet the prompt counter lost. Move the *detection* out of the model:
count the dig mechanically, ask for the trace at the moment the dig ends.

## How

- **PostToolUse counts** (matcher `Grep|Glob|Read|Bash` added alongside the memory-tool
  matcher): Grep/Glob/Read always count; Bash counts only when the command is
  search/read-shaped (`rg|grep|find|fd|ag|cat|head|tail|tree|ls`) — builds and test runs
  are not digs. The counter is keyed to `core.prompt_count`, so it resets naturally each
  turn; counting is silent.
- **Stop decides**: a turn whose count crossed `DIG_THRESHOLD` (config, default 8) adds a
  trace-specific reason to the same Stop block the cadence check uses — "record the
  finding as a structured trace entry: kind: trace, path/flow in the description, the
  question phrasings as aliases, anchorPath". Both reasons combine when both apply.
- **One ask per dig turn.** Unlike the write cadence (observable via mtime), "did the
  model record *the trace*" is not observable — so the dig nag never repeats across
  turns; the cadence block is the backstop. An observed context-file write during the
  dig turn clears the ask (trusted to carry the finding).

## Test

tests/test_gate.py: threshold fires / light use silent / per-turn reset / Bash
shape-filter / combined reasons / write clears the ask.

## Tuning

`DIG_THRESHOLD` in `~/.claude/memory-graph/gate.json`. If real sessions show 8 catching
routine multi-file edits (false digs), raise it before weakening the message; if genuine
digs stay under it, remember Read-heavy digs count too — lower with care.
