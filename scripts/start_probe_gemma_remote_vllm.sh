#!/usr/bin/env bash
set -euo pipefail

# Run this on the development machine that hosts the Probe backend.
# GEMMA_API_BASE should point to the remote vLLM server, for example:
#   http://10.241.115.108:8000/v1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ -x ".venv/bin/python" ]]; then
  source .venv/bin/activate
fi
export PYTHONPATH="$ROOT_DIR"

export GEMMA_BACKEND=${GEMMA_BACKEND:-remote_vllm}
export REQUIRE_REAL_GEMMA=${REQUIRE_REAL_GEMMA:-1}
export GEMMA_MODEL=${GEMMA_MODEL:-gemma4_e4b_tuned}
if [[ "$GEMMA_MODEL" == *"gemma-3"* || "$GEMMA_MODEL" == *"12b"* || "$GEMMA_MODEL" == *"google-gemma"* ]]; then
  echo "Detected stale GEMMA_MODEL=${GEMMA_MODEL}; using E4B default instead."
  export GEMMA_MODEL="gemma4_e4b_tuned"
fi
export GEMMA_API_BASE=${GEMMA_API_BASE:?Set GEMMA_API_BASE to your vLLM base URL, for example http://10.241.115.108:8000/v1}
export GEMMA_API_KEY=${GEMMA_API_KEY:-}
export GEMMA_TEMPERATURE=${GEMMA_TEMPERATURE:-0.2}
export GEMMA_MAX_TOKENS=${GEMMA_MAX_TOKENS:-768}

PROBE_HOST=${PROBE_HOST:-127.0.0.1}
PROBE_PORT=${PROBE_PORT:-8010}

echo "Starting DeepRepair Probe backend"
echo "  Probe API:    http://${PROBE_HOST}:${PROBE_PORT}"
echo "  E4B API:      ${GEMMA_API_BASE}"
echo "  E4B model:    ${GEMMA_MODEL}"
echo

python -m uvicorn pi_probe.main:app --host "$PROBE_HOST" --port "$PROBE_PORT" --log-level info
