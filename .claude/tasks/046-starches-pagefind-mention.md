---
id: 046
slug: starches-pagefind-mention
status: draft
branch: crew/046-starches-pagefind-mention
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
  - packages/ceist-web/
---

> Held (Stu, 2026-11-09) until the schema-assembly prototype (049) is measured: if it wins, this spec is rewritten for the new design.

# In Starches, leftover words become a labelled Pagefind mention on top of the structured answer

## Goal
With `fallbacks.mention` on (045), a refused question whose structured part grounded is answered as a suggestion:
- run the structured part through Rós Madair;
- send the words that couldn't be placed to Pagefind as a text search;
- keep the records in both.

For example, "which people hold copyright on images of Conand?" becomes "Figures linked to Conand whose text mentions 'copyright', 'images'" (045's notice and block).

1. **Words never sent as mentions:** filler and grammar words ("their", "same", "through", "someone"), from a small, documented stopword list. If nothing is left after removing them, there is no mention suggestion.
2. **Never a mention:** a negated question, a count (a count must not be narrowed silently), or a question with no grounded structured part.
3. **Measure it** on the generated train and hold-out sets, with the demo's Pagefind index. Of the refusals:
   - how many become mention suggestions;
   - how many of those contain the target records (judged against each question's target plan, run without the unplaced words);
   - how many return nothing.

   Run the demo bank's must-refuse questions too: list each that now gets a suggestion, and say whether its notice makes clear it isn't an answer.

## Background
- 045 must be merged first.
- The demo site's Pagefind index is built by Starches. Find it in `/home/stuart/git/personal/starches-demo` (read only). Use Pagefind's JS API in the browser or Node.
- Stu ruled earlier that answering what a story is about is out of scope. A mention says "text mentions 'love'", never "is about love". Keep the wording that way.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] The rules in 1 and 2 are tested. The measurements are in Worker notes.
- [ ] With `mention` off, the result is unchanged (the fixtures still pass).
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-046`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
