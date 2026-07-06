# Task: automatic session-end distillation (evaluating claude-mem's bet)

Status: **planned — decide after distill-two-pass-dedup** · Owner: Stuart · Created: 2026-07-05 · Size: M

## Goal

claude-mem compresses *every* session automatically at SessionEnd (agent-sdk summarisation).
Ours is human-invoked (`/memory-graph:distill`) — a deliberate quality gate. Evaluate the
middle ground: a SessionEnd hook that runs distill **headlessly** (`claude -p` against the
distill skill) when undistilled files pile up.

## Why maybe

The context-file backlog is real friction; claude-mem proves users want zero-effort capture.
And our position differs from theirs in one key way: **the hard capture rules make headless
distillation safer** — required properties, name lint, duplicate guard, and provenance are
enforced server-side no matter who invokes distill.

## Why maybe not

- Cost: an LLM run per session, unconditionally.
- Quality: hindsight-based promotion benefits from the human noticing what mattered; the
  reflect skill would need to carry more retroactive cleanup weight.
- Ordering: [[distill-two-pass-dedup]] should land first — auto-distill without write-time
  search-before-create would accumulate near-duplicates unattended.

## Decision gate

Try it behind a config flag once two-pass dedup exists; compare a week of auto-distilled graph
growth against hand-invoked quality (reflect skill audit + duplicate rate).
