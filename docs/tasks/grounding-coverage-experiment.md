# Task: grounding-coverage experiment

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Run the gate's term-extraction + matching over real prompts (archived context files /
transcripts) and report: % of prompts with any graph match, % of question-shaped prompts
fully groundable. **This number is the go/no-go** for the query planner's v0 grammar and
the POS-tagger decision — measure before building more.

## Notes

- Depends on [[prompt-gated-recall]]'s `gate._terms` and scoring existing.
- Output: a small script + a markdown report of the numbers; also seeds threshold tuning.
- No new dependencies; read-only against the store.
