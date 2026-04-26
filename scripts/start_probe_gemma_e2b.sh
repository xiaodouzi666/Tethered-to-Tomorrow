#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source .venv/bin/activate 2>/dev/null || true
export PYTHONPATH="$ROOT_DIR"
export GEMMA_BACKEND=${GEMMA_BACKEND:-litert_cli}
export REQUIRE_REAL_GEMMA=${REQUIRE_REAL_GEMMA:-1}
export GEMMA_MODEL_PATH=${GEMMA_MODEL_PATH:-/home/pi/models/gemma-4-E2B-it.litertlm}
export GEMMA_MODEL_FILE=${GEMMA_MODEL_FILE:-gemma-4-E2B-it.litertlm}
export GEMMA_MODEL_REPO=${GEMMA_MODEL_REPO:-litert-community/gemma-4-E2B-it-litert-lm}
export PROBE_HOST=${PROBE_HOST:-0.0.0.0}
export PROBE_PORT=${PROBE_PORT:-8010}
python -m uvicorn pi_probe.main:app --host "$PROBE_HOST" --port "$PROBE_PORT"
