# Task: session-start auto-prime

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Sessions start already primed: the SessionStart hook runs the existing read-only CLI —
`claude-memory-graph recall Project <cwd-basename> --depth 2` plus the user's Person node —
and injects the *results* (not instructions) into session context.

## Notes

- Simplest case of ambient retrieval: the "prompt" is cwd + user.
- Inject nothing if the Project node doesn't exist (silence, not noise).
- Needs a small `--budget` cap on recall output so hub projects don't flood context.
- Extends [hooks/session-start.sh](../../hooks/session-start.sh); no new deps.

## Test

Fixture store + hook run → expected injected text; empty store → empty output; exit 0 always.
