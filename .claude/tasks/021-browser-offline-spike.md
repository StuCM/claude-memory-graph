---
id: 021
slug: browser-offline-spike
status: done
branch: crew/021-browser-offline-spike
model: opus
env: laptop
work: ceist-typescript
files:
  - packages/ceist-web/
gate: pass
gateSha: dac10ae993c7ca2746883044ad73bdf54a9832a0
gateAt: 2026-11-06T16:24:05.864Z
rounds: 1
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

Run: `cd packages/ceist-web && npm install && npm run spike` (after `wasm-pack build crates/ros-madair-wasm --target web --release --no-opt --out-dir <worktree>/packages/ceist-web/spike/rm-wasm` in the Rós Madair clone). It bundles `spike/page.js` with esbuild, serves it plus the demo snapshot, graphs and the cached bge-small from a throwaway node server on 127.0.0.1, loads it in headless Chromium three times (cold, warm reload, `context.setOffline(true)` reload), prints the tables and exits; the server and browser close in a `finally`. All three loads must match every fixture and the offline load must hit the server for 0 files, or it prints FAIL.

Measured 2026-11-06 on this laptop, Chromium (Playwright 1.63) headless, everything on localhost, so times exclude real network transfer.

| asset | bytes (MB) | gzip (MB) |
|---|---|---|
| duckdb-wasm (`duckdb-eh.wasm`) | 35.91 | 8.13 |
| bge-small (onnx, quantised) | 34.01 | 23.86 |
| snapshot (parquet, 43 files) | 19.76 | 14.00 |
| onnxruntime-web (wasm) | 14.85 | 3.84 |
| model graphs (json, 6) | 3.39 | 0.22 |
| ros-madair-wasm (unoptimised) | 1.49 | 0.50 |
| JS (page bundle, duckdb worker, glue) | 1.14 | 0.29 |
| tokenizer.json | 0.71 | 0.21 |
| **total** | **111.28** | **51.05** |

| ms | cold | warm reload | offline reload |
|---|---|---|---|
| ros-madair-wasm init (wasm + parse 6 graphs) | 104 | 95 | 61 |
| duckdb init | 511 | 680 | 501 |
| snapshot fetch + register + views | 930 | 296 | 262 |
| ready to query (wall, the two above in parallel) | 1461 | 992 | 775 |
| model load (onnx + tokenizer) | 677 | 424 | 281 |
| first embedding | 45 | 46 | 10 |
| whole page | 3007 | 2287 | 1885 |
| embedding, warm, per phrase (1 thread) | 9.7 | 9.6 | 9.5 |

| fixture query | ids browser/Python | exact match | compile ms | first run ms | warm ms (median of 5) | Python `Reader.resolve` ms |
|---|---|---|---|---|---|---|
| concept count ("how many raths are there?") | 2902/2902 | yes | 4.6 | 66 | 10 | 25 |
| link ("which tales feature Cú Chulainn?") | 11/11 | yes | 1.0 | 4 | 4 | 9 |
| on-tile ("which bronze age cairns are in County Antrim?") | 43/43 | yes | 0.6 | 53 | 35 | 33 |
| chain, on_backlink ("which figures are associated with tales in the Ulster Cycle?") | 17/17 | yes | 0.3 | 6 | 4 | 16 |
| negated value ("…County Antrim are not scheduled?") | 5108/5108 | yes | 0.1 | 26 | 24 | 30 |
| negated link, base ("which monuments are not in County Antrim?") | 18820/18820 | yes | 0.0 | 22 | 19 | 25 |
| negated link, subtracted | 5638/5638 | yes | 0.1 | 8 | 6 | 21 |

Embedding of "bronze age cairns in County Antrim": token ids identical to the Python `tokenizers` ids, cosine 0.99823 to the Python vector. Offline reload: 0 files from the server, page controlled by the service worker, all matches still exact.

**Verdict: it works, and it is fast enough; it is too big for a first load.** Every fixture returns exactly Python's ids, the same Rust compiler emits the SQL (compile under 5 ms), warm queries take 4–35 ms (on par with native DuckDB through Python), ready-to-query is under 1.5 s cold, and a reload with the network off works. The cost is bytes: 111 MB raw, 51 MB gzipped before the first answer. What to change:

1. **Lazy-load bge-small** (24 MB gz model + 3.8 MB gz ort wasm, more than half the transfer). The quantised weights barely compress. The demo notes it changes no answer and only settles leftover words and "did you mean", so load it after the first answer or on demand. A smaller model is a separate measurement.
2. **Split the snapshot by model and by store.** Monument is 19.5 of 19.8 MB; `tiles_*` is 11.7 MB and is needed only for on_tile and the vacuous whole-model query. Fetch the concept, edge and resource stores first and tiles on demand, or online use duckdb-wasm `registerFileURL` range reads and cache the whole snapshot in the background for offline.
3. **duckdb-wasm** is 8 MB gz and fixed; it caches once. Its npm `latest` is a dev tag (1.33.1-dev57.0), worth pinning deliberately.
4. **ros-madair-wasm** is small (0.5 MB gz) even unoptimised. wasm-pack 0.13.1's bundled wasm-opt rejects the module ("error validating input", likely newer wasm features), so it was built with `--no-opt`; a current binaryen would shrink it further.
5. The service worker is a naive cache-first cache with no versioning. A real one needs a versioned precache list, as a new snapshot would otherwise be served stale.

Notes for a port:
- The browser mirrors Python `Reader(dir)`: one view per store over every model's file (`tiles`, `edges`, `edges_rev`, `concept_index`, `ordered_index`, `grid`, `resources`, `concepts`), and capability flags all true except spatial.
- `Reader.resolve` on an unscoped IR returns every record (18820 for the negated-link base, not 18508 monuments). Python `ask` then intersects with `vocab.ids_of` and adds `linked_from`. The TS port has to carry that client-side logic, not just the compiler.
- Fixtures were generated with `.venv-ceist` by a throwaway script (not committed, as `ceist-web` imports nothing from the Python package). For each question it ran `interpret`, then `compile_plan`, then `Reader.resolve` with `select_ids` and no limit for each query in `compiled.all()`. It stores the IR, the count, the sha256 of the sorted ids joined by newlines, and the bge-small vector and token ids from `OnnxEncoder`. The vocab is the demo's `layered(graphs, <worktree>/vocabularies/base, ask/vocab)`.
- Rós Madair clone: built only. `git status` stayed clean, with nothing committed or pushed.

## Graph writes proposed

## Review rounds

- Round 1 (dac10ae): PASS. The reviewer checked the code and the notes and did not re-run anything. Minor points it did not count as findings: the bytes table has no row for fixtures.json, sw.js and index.html (0.01 MB, counted as "other"); the "0 files served offline" check holds anyway once the network is cut, and the real evidence is that every fixture still matches offline; the service worker is naive, as the notes already say.
