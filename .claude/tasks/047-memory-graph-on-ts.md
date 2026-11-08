---
id: 047
slug: memory-graph-on-ts
status: approved
branch: crew/047-memory-graph-on-ts
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist-js/
  - claude_memory_graph/
  - packages/ceist/
---

# The memory graph asks through the TypeScript runtime; Python's question-time runtime retires

## Goal
Stu, 2026-11-08: one version of Ceist. `memory_ask` switches to the TypeScript runtime.

1. **A long-lived Node process**, started with the MCP server and stopped with it:
   - the question and the memory vocabulary go in as JSON, and the plan comes out as JSON;
   - the SPARQL compile stays in Python (`claude_memory_graph/planner.py`);
   - keep the glue small, around 100 to 200 lines.
2. **Without Node** (or if the process fails), `memory_ask` says so once and falls back to `memory_search`, as the plugin already does for missing pieces. Never a crash.
3. **The embedding gate** (`claude_memory_graph/gate/semantic.py`) only borrows `ceist.vectors`' ONNX encoder. Move what it needs into `claude_memory_graph`, so it no longer imports `ceist`.
4. **Retire Python's question-time runtime.** Delete `ground`, `plan`, `narrate`, `matching` and the rest of the question-time modules from `packages/ceist` once nothing imports them. The build tools stay: pipeline, bundle, ontology_vocab, questions, cost, learn, cli, `vocab freeze`. The vocabulary gate (`bench/ontology/gate.py`), `run_bank.py` and `her_plans.py` call the TypeScript runtime through the same Node process, or a batch CLI. starches-demo's `ask.py` moves to the TypeScript runtime or is retired; say which.

## Background
- 044 and 045 must be merged first.
- The memory graph's planner tests must pass on the TypeScript runtime.
- **Read first:** `packages/ceist/STATUS.md`, `packages/ceist/PORT-AUDIT.md`, and the Worker notes of the earlier `ceist-port` tasks. Follow Stu's code style rules in `~/.claude/CLAUDE.md`: plainest construct, reuse before writing, the comment test.
- **The port rule:** simplify the code's shape freely, but keep its behaviour identical, proven by the golden fixtures (040, 041). A behaviour change belongs in its own later task, never inside a port step.
- **Run `ponytail-review`** on your diff before opening the review round. Act on its findings and list them in Worker notes.
- **No `claude -p` or live LLM runs.**

## Definition of done
- [ ] `memory_ask` answers the planner test suite through Node, and the fallback without Node is tested.
- [ ] The vocabulary gate, the demo bank and the HER plans all run on the TypeScript runtime with unchanged tallies.
- [ ] The lines deleted from `packages/ceist` are in Worker notes.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-047`, `VITEST_MAX_WORKERS=4` for any vitest run, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
