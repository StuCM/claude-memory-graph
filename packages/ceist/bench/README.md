# Matcher comparison: everyday phrases onto Arches nodes

The question this answers: which matcher should turn "built", "pulled down" or "owned by" into the right node ("Construction Date", "Demolition Date", "Owner")? It also asks whether a matcher can run in a browser with no backend, which is how Rós Madair is deployed.

```
uv run python packages/ceist/bench/compare.py                  # what's installed
./packages/ceist/bench/fetch_models.sh                         # fetch the model weights (needs huggingface.co)
pip install onnxruntime tokenizers llama-cpp-python
CEIST_BENCH_MODELS=~/models uv run python packages/ceist/bench/compare.py
```

The script writes `results/report.md` and `results/details.json`, which records each case's pick and its top three scores.

## The cases

There are 57 cases in `cases.json`, over the models in `models.json`:

- 50 cases where a node fits, and 7 where none does ("painted before 1900", "what colour is it?"). For those 7, the right answer is to abstain.
- The models are a hand-written heritage asset and person, in the shape of an Arches HER model with event groups (Construction Phase: date and Constructed By), plus the real `aonach_mor` Building and Organisation nodes from Rós Madair's example.
- **The expected answers are hand-written, so review them**, especially the judgement calls ("recorded" → survey date; "use" → occupies).

Each matcher runs in two conditions:
- **restricted:** the candidates are first narrowed by what the planner already knows. A date phrase gets date nodes, and "by <a Person>" gets links to Person. This is how ceist would use a matcher, with Alizarin supplying each node's datatype, target model and group.
- **all nodes:** the matcher has to manage on its own.

A **dangerous** answer is a wrong node, or a node where none fits. A miss only means the planner asks or refuses, so a dangerous answer is worse.

## Results so far (2026-10-27)

Out of 50 cases where a node fits. In every row below, all 7 "nothing fits" cases were correctly refused.

| matcher | restricted: right | restricted: dangerous | all nodes: right | all nodes: dangerous |
| --- | --- | --- | --- | --- |
| exact words (today's ceist) | 7 | 0 | 5 | 1 |
| WordLlama on node names | 20 | 0 | 13 | 4 |
| **vocabulary + exact words** | **43** | **0** | 42 | 0 |
| **vocabulary + WordLlama** | **48** | **0** | 47 | 1 |

The **vocabulary** is `vocab.json`: 514 phrasings for the 31 nodes. A fresh LLM agent wrote it once, offline, from `models.json` alone. It was told not to open the cases, and it used only two tool calls (read the models, write the file). At question time nothing runs but a word lookup and WordLlama. The thresholds are the gate's defaults (0.40, gap 0.08), not tuned.

What's left:
- **"date from":** every date node scores about 0.8, so the gap rule refuses. Correct: the phrase really is ambiguous.
- **"made by":** 0.40, just at the threshold.
- **The one dangerous pick:** with all nodes and no narrowing, "kind of protection" goes to the designation *date*. With narrowing (a property question excludes dates), it's refused.

**Caveat.** The person who wrote the cases and the agent that wrote the vocabulary are from the same model family, so they may think alike, and these numbers are probably optimistic. The real test is questions from real users, held out from vocabulary building.

For comparison, WordLlama on bare node names is right 44/50 when you take its single best-scoring node (restricted), but only 34/50 once thresholds keep it safe (tuned on these same cases, so an upper bound). The vocabulary gets 48/50 with untuned thresholds.

### The design this points to: spend the LLM at build time, not query time

As in the memory graph, the intelligence goes in when the data is written, not when it's queried:

1. **Build (when the graphs change):** `ceist vocab build <data_dir>`.
   - Read each model through Alizarin: node names, cards and groups, datatypes, link targets, descriptions, concept labels.
   - Ask a strong LLM for each node's everyday phrasings.
   - Write `vocab.json` next to the data. It's reviewed like code, and records a hash of the graphs so a stale file is detected.
2. **Question time (every question, in the browser):**
   - the planner's structure narrows the candidates;
   - an exact match on a phrasing wins;
   - otherwise WordLlama picks the nearest phrasing, with a minimum score and a gap to the runner-up;
   - otherwise ask or refuse.
   This means static files and no model at query time.
3. **Learn from use:** phrases the planner couldn't place get logged, and the next build hands them to the LLM to assign. A person approves the result.

The ONNX and Qwen matchers still run once their weights are reachable. They now have to beat 48/50 *at query time* to be worth their size in the browser.

## At HER scale: the real Arches HER models (2026-10-27)

```
git clone https://github.com/archesproject/arches-her
P=arches-her/arches_her/pkg
python her_models.py "$P/graphs/resource_models" her/models "$P/reference_data"   # needs alizarin
uv run python her_compare.py
```

(`her_models.py` writes one file per model. The extracted descriptions aren't committed: arches-her is AGPL, so regenerate them from a clone.)

- **What was read, through Alizarin:**
  - 16 resource models, 4,571 nodes, 2,327 of them searchable (structural and `*_metatype` nodes dropped);
  - each node with its card, its path through the model tree, its UI label and its link targets;
  - the labels of every small concept collection (roles, phase types; ≤120 terms). The 108 SKOS thesauri and 122 collections load in about 7 s.
- **Vocabulary (`her/vocab/`):** four fresh agents, about 4 minutes in all, writing 1,301 entries and 7,392 phrasings (276 KB). Entries can carry a qualifier value, so "designed by" means actor + role = Architect, and a date entry names both ends of its event's timespan.
- **Questions (`her/cases.json`):** 120, written by a separate agent from the model descriptions alone, which never saw the vocabulary. 102 have a fitting node and 18 have none.

| matcher | right | partial (qualifier missing) | dangerous | missed | "nothing fits" refused | ms/question |
| --- | --- | --- | --- | --- | --- | --- |
| WordLlama on node names + cards | 20/102 | 0 | 0 | 82 | 18/18 | 3 |
| vocabulary + exact words | 61/102 | 2 | 1 | 38 | 18/18 | 0.4 |
| vocabulary + WordLlama (gate threshold 0.40) | 81/102 | 2 | 5 | 17 | 15/18 | 1.5–3 |
| vocabulary + WordLlama, threshold 0.6* | 81/102 | 2 | 3 | 17 | 17/18 | 1.5 |
| vocabulary + WordLlama, threshold 0.7* | 77/102 | 2 | 2 | 21 | 18/18 | 1.7 |

\* Threshold sensitivity, shown on the test set, so not a tuned result.

What the failures show:
- **Static vectors ignore little words.** "sailing from" lands on *destination* (0.98) over *departure* (0.85), and at 0.40, "copies" → copyright, "camera" → file, "read" → audience. A stricter threshold removes most of these.
- **Idioms the vocabulary didn't anticipate:** "turned down" (planning outcome), "put in by" (applicant), "brought out" (publisher), "kick off", "fall under", "thrown on a wheel". These are what a model that reads the whole question should fix, and what the build-time loop (log the misses, have the LLM assign them) is for.
- **Qualifiers the vocabulary left out:** contact point + Email or Telephone.
- **Disputable expected answers:** "captain" (`crew_member` or `actor` + Captain: both exist), and "named location or an address". These need a heritage officer's call.

The HER models also show what the planner has to understand beyond phrase matching:
- **Events are timespans** (start and end, often EDTF), so "built before 1900" needs range semantics.
- **People link through a generic actor plus a role,** so a phrase maps to a node *and* a concept value.
- **"Church" or "mill" is a value in a 5,009-term monument-type thesaurus,** not a model.

### Does training WordLlama on the vocabulary help? (`adapt.py`)

We trained on the vocabulary itself, with 20% of each entry's phrasings held out. The objective puts each phrasing nearer its own entry than its same-model, same-kind siblings, which is exactly the planner's shortlist. JAX on CPU, minutes per run.

| variant | size | held-out phrasings placed right | blind questions right / dangerous (thresholds 0.4, 0.6, 0.7) |
| --- | --- | --- | --- |
| WordLlama as is | — | 67.5% | 81/5, 81/3, 77/2 |
| linear adapter, weak pull to identity | 118 KB | **75.4%** | 80/6, 79/3, 76/2 |
| linear adapter, stronger pull | 118 KB | 72.5% | 81/5, 81/3, 77/2 |
| token fine-tune | 692 KB | 69.6% | 81/5, 81/3, 77/2 |

**It learns the vocabulary writer's style, not the users'.** Held-out phrasings improve by up to 8 points, but the blind questions don't move: the adapters are level or one worse at every threshold. Held-out phrasings come from the same author as the training data, while questions are worded differently, and real users' questions will differ more still.

**What would help instead:**
- More *kinds* of phrasing in the vocabulary: the step-9 loop with real misses.
- A model that reads the whole question, for the idioms.

An adapter is worth retrying once there are a few hundred real questions to train on and a separate set to test on. `adapt.py` and `her_compare.py` (`CEIST_ADAPTERS=a.npz,b.npz`) are ready for that.

## In the browser

| matcher | size | browser runtime |
| --- | --- | --- |
| WordLlama | 16 MB (256-d), ~4 MB as int8 | a lookup table plus an average; trivial in JS or WASM |
| MiniLM / bge-small bi-encoder | ~25–35 MB (int8 ONNX) | transformers.js or onnxruntime-web (WASM; WebGPU where present) |
| MiniLM cross-encoder | ~25 MB (int8 ONNX) | the same |
| Qwen3 0.6B / 1.7B / 4B | ~0.4 / 1.1 / 2.5 GB (Q4_K_M GGUF) | wllama (llama.cpp in WASM, CPU), or WebLLM with WebGPU |

The ONNX files are the quantized ones transformers.js loads, and the GGUF files are what wllama runs, so accuracy here carries over to the browser. Speed doesn't: browser timings need measuring in a browser.

**ceist itself is Python.** In a no-backend Rós Madair page, the planner needs to run in the browser too. There are two options:
- run it under Pyodide: ceist has no dependencies, but this adds about 10 MB of runtime;
- port it to TypeScript or Rust, compiled to WASM next to `ros-madair-wasm`.

Whichever matcher wins has to fit alongside that.
