#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source .venv/bin/activate 2>/dev/null || true
export PYTHONPATH="$ROOT_DIR"
export GEMMA_BACKEND=mock
export REQUIRE_REAL_GEMMA=0
export PROBE_HOST=${PROBE_HOST:-0.0.0.0}
export PROBE_PORT=${PROBE_PORT:-8010}
python -m uvicorn pi_probe.main:app --host "$PROBE_HOST" --port "$PROBE_PORT"
