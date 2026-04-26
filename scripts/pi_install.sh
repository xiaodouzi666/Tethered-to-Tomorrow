#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r pi_probe/requirements.txt

echo "[ok] Python dependencies installed."
echo "Run: bash scripts/start_probe_mock.sh"
