---
id: 045
slug: fallback-config-and-suggestions
status: draft
branch: crew/045-fallback-config-and-suggestions
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
  - packages/ceist/
---

> Held (Stu, 2026-11-09) until the schema-assembly prototype (049) is measured: if it wins, this spec is rewritten for the new design.

# Fallbacks off by default and switched on per site; every suggestion clearly marked as not a match

## Goal
Stu, 2026-11-08: "Still would like a config to turn it on or off. It needs to be obvious to a user when we didn't match and we are suggesting."

1. **A config, read by the TypeScript runtime and documented:** `fallbacks: { partial: false, mention: false }`.
   - Both are **off by default**, so behaviour is unchanged until a site opts in.
   - `partial` returns 038's partial match.
   - `mention` turns words that couldn't be placed into a labelled text mention (task 046 supplies the Starches text search).
   - The memory graph's free-text vocabulary keeps working as it does today. Decide how its `free_text` flag and `fallbacks.mention` relate (one setting or two), and say which in Worker notes.
2. **One result shape that can't be mistaken for an answer.** On any refusal, the result is:
   - `matched: false`;
   - the refusal;
   - optionally a `suggestion`, containing:
     - `kind`: `partial` or `mention`;
     - `unmatched`: the words not used;
     - `narration`: the reading shown;
     - `notice`: a ready-made sentence that starts with what didn't match ("We couldn't match 'copyright', 'images'. Showing Figures linked to Conand whose text mentions them.").

   A confident answer has `matched: true` and no notice. The field names are the contract; put them in the package README.
3. **The demo page shows the difference:**
   - a suggestion gets its own visibly different block (a heading such as "Not an exact match", the notice, then the results);
   - the matched words are highlighted where a mention was used;
   - it is never styled like an answer.

   Add a Playwright check that a suggestion never renders without its notice.
4. **Python parity.** Make the same change in Python's result. The memory graph still uses Python until 047, and the fixtures must agree.

## Background
- 044 must be merged first.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Tests:
  - with both fallbacks off, the results are identical to before (the fixtures still pass);
  - with each one on, a suggestion always carries `matched: false` and a notice;
  - the Playwright check passes.
- [ ] The config and result shape are documented in the package README.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-045`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
