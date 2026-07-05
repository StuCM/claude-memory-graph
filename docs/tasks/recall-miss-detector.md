# Task: recall miss detector — self-tuning gate from explicit recalls

Status: **planned** · Owner: Stuart · Created: 2026-07-05 · Size: S

## Goal

An explicit `memory_recall`/`memory_query` call right after the gate stayed silent is a
**logged false negative** — the model went looking for something the analyzer should have
surfaced. Capture it automatically:

1. Wire `PostToolUse` (matcher: the memory-graph MCP tools) through hook-kit dispatch.
2. A small extension records each explicit recall (tool, args, timestamp) to
   `explicit-recalls.jsonl` in the hook-kit home.
3. Join with `injections.jsonl` offline: silence followed within a turn or two by an explicit
   recall whose target the corpus contained = a miss, with the scores that caused it.

## Why

This makes the gate **self-tuning from real use with zero manual labelling** — the
threshold-tuning dataset (ABS_MIN/MARGIN) accumulates as a by-product of normal work. Ranked
the highest-value small task in the retrieval track.

## Notes

- Needs a `PostToolUse` entry in EVENT_METHODS + hooks.json (hook-kit change, trivial).
- The join is an analysis script (`claude-hooks` subcommand or standalone), not runtime
  behaviour — no per-prompt cost.
- Depends on [[prompt-gated-recall]] (done); complements [[grounding-coverage-experiment]].

## Test

Synthetic injections.jsonl + explicit-recalls.jsonl → join reports the planted miss with its
scores; explicit recall after a *fired* injection is not counted as a miss.
