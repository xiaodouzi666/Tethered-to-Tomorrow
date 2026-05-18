#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ -x ".venv/bin/python" ]]; then
  source .venv/bin/activate
fi
export PYTHONPATH="$ROOT_DIR"
export GEMMA_BACKEND=mock
export REQUIRE_REAL_GEMMA=0
export PROBE_HOST=${PROBE_HOST:-127.0.0.1}
export PROBE_PORT=${PROBE_PORT:-8010}
echo "Starting DeepRepair Probe backend in mock mode"
echo "  Probe API: http://${PROBE_HOST}:${PROBE_PORT}"
echo

python -m uvicorn pi_probe.main:app --host "$PROBE_HOST" --port "$PROBE_PORT" --log-level info
