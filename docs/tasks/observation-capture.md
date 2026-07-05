# Task: mechanical observation capture (learning from claude-mem)

Status: **planned** · Owner: Stuart · Created: 2026-07-05 · Size: M

## Goal

claude-mem's most load-bearing idea: don't rely on the model to *write down* what happened —
**record it mechanically from PostToolUse**. Our context files are model-written (nudged), which
covers judgement (decisions, rationale) but still loses the factual record when discipline
slips. Add a machine-written lane:

- A hook-kit extension on `PostToolUse` (broadened matcher) records observations: files
  edited/written (paths), commands run, tests passed/failed, errors seen.
- Observations append to a per-session `observations` section of the context file (or a
  sidecar the distill skill reads alongside it).
- Distill consumes both lanes: model-written notes carry the *why*; observations carry the
  reliable *what* — and ground code anchors (`anchorPath` from actual edits, not memory).

## Why (division of labour)

Notes need judgement → model's lane, nudged. Observations are facts → machine's lane, never
missed. claude-mem proves at scale that automatic observation capture is what makes memory
feel dependable; our version keeps the graph-promotion quality gate (rubric, hard rules) that
they lack.

## Notes

- Matcher must stay cheap: Edit/Write/Bash tool names; budget the log line, not the payload.
- Feeds [[code-anchors]] (real paths) and [[transcript-telemetry]] shares the hook.

## Test

pytest: Edit/Write/Bash payloads produce observation lines; memory tools excluded (that's the
miss detector's lane); non-matching tools ignored; fail-open.
