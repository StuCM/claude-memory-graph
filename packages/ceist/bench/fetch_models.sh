#!/usr/bin/env bash
# Fetch the weights compare.py compares, into $CEIST_BENCH_MODELS (default ~/models).
# The ONNX files are the quantized ones transformers.js loads in a browser, and
# the GGUF files are what wllama runs in a browser, so the comparison holds there.
# Needs: pip install -U huggingface_hub   (and network access to huggingface.co)
set -euo pipefail
DEST="${CEIST_BENCH_MODELS:-$HOME/models}"
mkdir -p "$DEST"

onnx() {  # repo folder
  local tmp; tmp="$(mktemp -d)"
  hf download "$1" onnx/model_quantized.onnx tokenizer.json --local-dir "$tmp"
  mkdir -p "$DEST/$2"
  mv "$tmp/onnx/model_quantized.onnx" "$DEST/$2/model.onnx"
  mv "$tmp/tokenizer.json" "$DEST/$2/tokenizer.json"
  rm -rf "$tmp"
}
onnx Xenova/all-MiniLM-L6-v2        minilm
onnx Xenova/bge-small-en-v1.5       bge-small
onnx Xenova/ms-marco-MiniLM-L-6-v2  cross-minilm

gguf() {  # repo file
  local tmp; tmp="$(mktemp -d)"
  hf download "$1" --include "*Q4_K_M.gguf" --local-dir "$tmp"
  mv "$(find "$tmp" -name '*Q4_K_M.gguf' | head -1)" "$DEST/$2"
  rm -rf "$tmp"
}
gguf unsloth/Qwen3-0.6B-GGUF qwen3-0.6b.gguf
gguf unsloth/Qwen3-1.7B-GGUF qwen3-1.7b.gguf
gguf unsloth/Qwen3-4B-GGUF   qwen3-4b.gguf

echo "Weights in $DEST. Then: pip install onnxruntime tokenizers llama-cpp-python"
