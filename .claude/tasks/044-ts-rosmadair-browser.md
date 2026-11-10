---
id: 044
slug: ts-rosmadair-browser
status: draft
branch: crew/044-ts-rosmadair-browser
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
  - packages/ceist-web/
---

> Rewritten for schema assembly (2026-11-09). Draft until Stu has reviewed the code after 053 and 055; he approves it then.

# TypeScript compile to Rós Madair, and Ceist answering in the browser from the frozen vocabulary

## Goal
Step 5 of the port. Port the Rós Madair compile path (the structured runner, as in starches-demo's `ask.py`, not `rosmadair.ask`; see PORT-AUDIT.md). Then make a browser page answer questions end to end:
- the frozen vocabulary JSON;
- `ceist-js`;
- Rós Madair WASM over the demo snapshot.

No Python, and **no bge model** (STATUS.md: it changes almost no answers; leave it out of the browser build).

1. **Conformance:** every fixture's compiled query equals Python's.
2. **The demo bank in the browser.** A Playwright run of the demo bank through the page gives the same tally as `run_bank.py` (71 answer/right, 0 wrong, or whatever the current tally is).
3. **Size and speed in Worker notes:** download size (JS, WASM, vocabulary), time to first answer, and median answer time on the demo bank. Compare with the 021 spike, which shipped bge.

Replace `packages/ceist-web/spike` with the real page, or keep the spike only if something still needs it (say what).

## Background
- 043 must be merged first.
- Port only assembly; there is no strict mode in TypeScript.
- The 021 spike's notes cover WASM loading, the wasm-opt problem (`wasm-pack build --no-opt`) and the service worker.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **Descriptive names** (Stu, 2026-11-10): no single-letter or cryptic variables (`s`, `g`, `c`, `d`). Name things for what they are (`scan`, `grounding`, `candidate`), so the code explains itself. The Python uses short names; the TypeScript must not copy them.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] Every compiled query is equal. The browser demo bank tally equals the Python tally.
- [ ] Size and speed are in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-044`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
