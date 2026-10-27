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
