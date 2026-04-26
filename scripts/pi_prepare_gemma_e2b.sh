#!/usr/bin/env bash
set -euo pipefail

# Installs LiteRT-LM and performs a first Gemma 4 E2B model pull/test.
# If HuggingFace requires auth for the Gemma model, run `huggingface-cli login` first.

MODEL_DIR=${GEMMA_MODEL_DIR:-/home/pi/models}
MODEL_FILE=${GEMMA_MODEL_FILE:-gemma-4-E2B-it.litertlm}
MODEL_REPO=${GEMMA_MODEL_REPO:-litert-community/gemma-4-E2B-it-litert-lm}

mkdir -p "$MODEL_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "[info] uv not found. Installing uv via pip user install..."
  python3 -m pip install --user uv
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v litert-lm >/dev/null 2>&1; then
  echo "[info] Installing litert-lm CLI..."
  uv tool install litert-lm
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[info] Testing Gemma 4 E2B LiteRT-LM CLI. This may download the model on first run."
cd "$MODEL_DIR"
litert-lm run --from-huggingface-repo="$MODEL_REPO" "$MODEL_FILE" --prompt="Return JSON only: {\"ok\": true, \"model\": \"gemma-4\"}"

echo "[ok] LiteRT-LM E2B test command completed."
echo "Set GEMMA_MODEL_PATH=$MODEL_DIR/$MODEL_FILE when using Python API backend, or use CLI backend with GEMMA_MODEL_REPO=$MODEL_REPO."
