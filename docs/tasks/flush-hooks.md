# Task: flush hooks (PreCompact / SessionEnd)

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Backstops for the context log: `PreCompact` injects "update the context file NOW" (last
chance before the session's memory of itself is summarised away); `SessionEnd` checks the
undistilled-file count and surfaces "run /memory-graph:distill" when ≥3.

## Notes

- Extends the state file from [[prompt-count-context-trigger]]; same fail-open rule
  (missing/corrupt state → do nothing, exit 0).
- SessionEnd can't make the model write (no more turns) — it's for the *user* suggestion
  and final state save; PreCompact is the one that reaches the model in time.

## Test

Hook run with fixture state → expected stdout; corrupt state file → empty output, exit 0.
