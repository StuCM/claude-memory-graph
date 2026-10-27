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

## Baseline (2026-10-27, what runs in this environment)

| | exact words (today's ceist) | WordLlama, gate thresholds | WordLlama, best-scored node (top-1) | WordLlama, tuned* |
| --- | --- | --- | --- | --- |
| restricted | 7/50 right, 0 dangerous | 20/50, 0 dangerous | 44/50 | 34/50, 0 dangerous (≥0.14, gap 0.04) |
| all nodes | 5/50, 1 dangerous | 13/50, 4 dangerous | 28/50 | 15/50, 0 dangerous |

\* Tuned on the same cases it's scored on, so it's an upper bound until checked on held-out questions.

What this shows so far:
- **The structure matters most.** WordLlama's top-scoring node is right 44 of 50 times when the planner narrows the candidates first, and 28 of 50 when it doesn't. That narrowing is what reading the models through Alizarin provides.
- **The gate's thresholds (0.40, gap 0.08) don't suit single words.** They were set for whole prompts against whole memories.
- **WordLlama's misses** are phrasal and idiomatic: "put up", "date from", "kind of protection", "worked for", "based in", "built of". A model that reads the whole question should help with exactly these.

The ONNX and GGUF matchers haven't been run yet. Their weights are on huggingface.co, which this environment's network policy blocks. The adapters in `compare.py` are written but **untested until they run**.

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
