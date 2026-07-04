# Task: code anchors + drift flag

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Memories about code carry `anchorPath`/`anchorSymbol`/`anchorCommit` (distill writes
them); recall appends `(code changed since)` when the anchored file has commits past
`anchorCommit`. Design: [CODE-GRAPH.md](../CODE-GRAPH.md). The derived code graph itself
is **future** — this task needs only git.

## Notes

- Drift check = `git log --oneline <commit>.. -- <path>` non-empty; only when a cwd repo
  matches the anchored project; fail open if git/repo unavailable.
- Skill-side: distill SKILL.md gains the anchor instruction (already hinted in
  DISTILL-CREATION.md §4).

## Test

pytest with a throwaway git repo: unchanged anchor → no flag; commit touching the file →
flag; missing repo → no flag, no error.
