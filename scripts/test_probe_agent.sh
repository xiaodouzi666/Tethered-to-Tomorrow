#!/usr/bin/env bash
set -euo pipefail
BASE=${1:-http://localhost:8010}

echo "== health =="
curl -s "$BASE/health" | python3 -m json.tool

echo "== inject thermal =="
curl -s -X POST "$BASE/api/faults/inject" -H 'Content-Type: application/json' -d '{"fault":"thermal"}' | python3 -m json.tool
sleep 2

echo "== diagnose =="
curl -s -X POST "$BASE/api/agent/diagnose" -H 'Content-Type: application/json' -d '{"reason":"script-test"}' | python3 -m json.tool

echo "== safe mode =="
curl -s -X POST "$BASE/api/command" -H 'Content-Type: application/json' -d '{"action":"ENTER_SAFE_MODE","source":"script-test"}' | python3 -m json.tool
