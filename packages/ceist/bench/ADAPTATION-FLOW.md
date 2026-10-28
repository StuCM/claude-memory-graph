# Adapting ceist to a project: a repeatable flow

A **project** is a set of Arches models and thesauri: a HER, a resilience dataset like aonach_mor, a museum catalogue. Adapting ceist to it produces small, static files. Questions are then answered in the browser with no model and no backend, which is how Rós Madair is deployed. The expensive intelligence is spent once, at build time, as in the memory graph.

Every step below has been run end to end on the real Arches HER package (16 models, 2,327 searchable nodes). The numbers come from `README.md` in this folder.

## The pipeline

| # | Step | Input | Output | Who / what | Effort on HER |
| --- | --- | --- | --- | --- | --- |
| 1 | **Read the models** (`ceist vocab describe`) | graphs + reference_data (SKOS) | one description per model: node, card, tree path, UI label, link targets, small collections' labels | Alizarin; automatic | seconds |
| 2 | **Build the vocabulary** (`ceist vocab prompt` → an LLM or agent → `ceist vocab assemble`) | step 1 | `vocab/<Model>.json`: entries of phrasings mapped to a node (+ a qualifier value, + the end of a date range) | a strong LLM, one agent per ~4 models | ~4 min, 7,392 phrasings, 276 KB |
| 3 | **Write the acceptance questions** | step 1 only (never the vocabulary) | `cases.json`: questions with the expected node, including ones that should be refused | a separate LLM agent, **plus real questions from the client** | ~3 min for 120 |
| 4 | **Review** | steps 2–3 | corrected expectations; a list of disputed cases | a domain expert (heritage officer), ~1 hour | — |
| 5 | **Evaluate** (`ceist eval`, with `--min-right` / `--max-dangerous` as the gate) | steps 2–4 | right / partial / dangerous / missed / refused, with a threshold sweep | automatic | seconds |
| 6 | **Adapt (optional)** (`adapt.py`) | step 2, or better, real questions | a 118 KB adapter or a token patch | automatic (JAX, CPU) | minutes; **on HER it didn't beat the baseline**, so ship it only if step 7 says so |
| 7 | **Gate** | steps 5–6 | ship only if dangerous answers don't rise and right answers do, on step 3's questions | rule | — |
| 8 | **Package** (the bundle and `ceist.toml`; `ceist vocab check` catches a stale bundle) | steps 2, 6, 7 | `vocab.json`, the WordLlama table (16 MB, or about 4 MB as int8), any adapter, thresholds, and the report | automatic | — |
| 9 | **Loop** (`ceist vocab try` / `learn.record` → `ceist vocab learn` → review → `ceist vocab merge` → assemble → eval) | the learning log: phrases nothing placed, and "did you mean" picks | picks become confirmed phrasings; the rest an LLM assigns to a node or "none"; a person approves; re-evaluate on step 3's questions | the app logs; LLM plus a person, monthly or per release | small |

## Rules that keep it honest

- **The acceptance questions never feed the vocabulary or the adapter.** If they did, the scores would only measure memorisation. Keep a frozen set per release, and add new real questions to the *next* release's set.
- **Count dangerous answers separately from right ones.** A wrong node answers a different question; a refusal only costs a rephrase. A change that adds right answers but also dangerous ones fails the gate.
- **Real questions beat generated ones.** Agent-written questions share the vocabulary writer's habits. Ask the client for 50–100 questions their users actually asked: search logs, enquiry emails, help-desk tickets.
- **Agree the expected answers before measuring.** On HER, several "failures" were disputable expectations ("captain": crew member or actor + role?). Step 4 settles them once.

## Where the gains actually come from (HER evidence)

| change | blind questions right |
| --- | --- |
| node names only | 20/102 |
| + LLM-built vocabulary (step 2) | 81/102 |
| + domain adapter trained on that vocabulary (step 6) | 79–81/102: no gain |
| + "did you mean" from the top three (UI) | 94/102 within one click |

So the money is in steps 2–4 and 9 (vocabulary, real questions, review, the loop), plus a UI that offers choices when unsure. Training is the last resort, and only on real questions.

## What a client gets (the deliverable)

- **The phrase vocabulary,** reviewed and versioned with the data. A stale-graph check flags when the models change.
- **An acceptance report:** the scores, every dangerous answer explained, and the threshold chosen with its trade-off.
- **A browser bundle** for Rós Madair: the vocabulary, the vector table, any adapter, and thresholds. No model and no backend.
- **The loop:** a log of misses and refusals, and a scheduled re-run of steps 2, 5 and 7.

## Where the effort (and so the price) goes

Steps 1, 5, 6 and 8 are automatic. Step 2 is minutes of LLM time per project. The paid human time is:
- step 3: collecting real questions;
- step 4: expert review;
- step 9: approving new phrasings.

Those scale with how many questions matter, not how many nodes exist, and they're what makes the result trustworthy.

**New domains** (a museum collection, an infrastructure asset register) reuse the whole pipeline. Only step 1 changes if the data isn't Arches: anything that implements ceist's vocabulary interface works.
