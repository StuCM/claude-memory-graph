---
id: 021
slug: browser-offline-spike
status: approved
branch: crew/021-browser-offline-spike
model: opus
env: laptop
work: ceist-typescript
files:
  - packages/ceist-web/
---

# Spike: can Ceist's back half run in the browser, offline, fast enough?

## Goal
Measure, before any port, whether the pieces a TypeScript Ceist would sit on work in a browser **offline**, over the demo's data:
1. **ros-madair-wasm** (`crates/ros-madair-wasm`: Query IR + all graphs JSON compiled to DuckDB SQL) plus **duckdb-wasm**, executing over the demo snapshot's Parquet (`/home/stuart/git/personal/starches-demo/ask/snapshot/`, about 19 MB).
2. **bge-small** in **onnxruntime-web**, embedding a phrase. Try the quantised model if one exists.
3. **Offline:** after a first load, the page works with the network off (a service worker, or Playwright `context.setOffline(true)` after warming the cache).

Deliver a Worker-notes table:
- bytes per asset (wasm, model, snapshot, JS);
- cold start (duckdb init plus snapshot registration, ros-madair-wasm init, model load);
- warm query time;
- embedding time;
- a verdict.

This is not production code.

## Why now
Stu, 2026-11-06: "we will want to go typescript as it needs to run in the browser potentially offline", and option 2: TypeScript Ceist next to the Python Ceist as its own npm package. "eventually it will all go into its own repo out of the memory graph". So `packages/ceist-web/` must import nothing from the memory graph or the Python package.

## Background
- **Rós Madair** is the local clone `/home/stuart/.cache/tmp-ask/ros-madair`, branch `ceist-linked` (alpha.33 plus the binding change). It is Phil's repo: build only, never push or commit there.
  - Build the wasm with `wasm-pack build crates/ros-madair-wasm --target web` into the spike folder (a heavy build: run it alone).
  - Read the crate docs for what it needs registered: `has_catalog`, `has_edges`, `has_concept_index`, `has_ordered`.
- **Query fixtures:** don't hand-write IR. Generate it with the Python Ceist (`.venv-ceist`):
  - run `interpret`, then `compile_plan`, for about 5 bank questions (`packages/ceist/bench/demo/questions.json`): a concept count, a link, an on-tile one, a chain or backlink, and a negation;
  - save the IR plus the Python `Reader.resolve` ids as JSON fixtures;
  - the browser results must match those ids exactly.
- **bge-small:** the Python side fetches it with `ceist vectors fetch bge-small-en-v1.5`. Find where it caches it, or fetch the ONNX from Hugging Face (Xenova/bge-small-en-v1.5 has quantised ONNX). Embed one phrase in both Python and the browser, and compare cosine (above 0.99).
- **Running a page:** use a small static server or `vite`, driven headless with Playwright. Chromium with swiftshader has worked before on this machine. **Stop the server when done.**
- npm installs are fine inside `packages/ceist-web/` (its own `package.json`, `node_modules` git-ignored).

## Out of scope
Porting any of Ceist: grounding, planning, narration.

## Definition of done
- [ ] `packages/ceist-web/spike/` contains the page, a script that runs it headless and prints the table, and the fixtures.
- [ ] Browser ids equal the Python ids for every fixture query, and the embedding cosine is above 0.99.
- [ ] The offline run passes: the second load runs with the network off.
- [ ] Worker notes give the table and a verdict: what is too big or too slow, and what to change (a quantised model, lazy loading, a snapshot split).
- [ ] The gate passes (no Ceist change is expected). Machine load: heavy builds alone, `TMPDIR=/home/stuart/.cache/tmp-021`, no servers left running, never `git add -A` or `git stash`, no pushes, never `claude -p`.

## Worker notes

## Graph writes proposed

## Review rounds
