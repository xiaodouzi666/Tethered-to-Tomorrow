#!/usr/bin/env bash
set -euo pipefail

# Run this on the RTX 3090 Ti server after installing vLLM and preparing the fine-tuned E4B checkpoint.

MODEL=${GEMMA_MODEL:-gemma4_e4b_tuned}
HOST=${VLLM_HOST:-0.0.0.0}
PORT=${VLLM_PORT:-8000}
MAX_MODEL_LEN=${VLLM_MAX_MODEL_LEN:-16384}
GPU_MEMORY_UTILIZATION=${VLLM_GPU_MEMORY_UTILIZATION:-0.88}
QUANTIZATION=${VLLM_QUANTIZATION:-bitsandbytes}

ARGS=(
  "$MODEL"
  --host "$HOST"
  --port "$PORT"
  --dtype auto
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --generation-config vllm
)

if [[ -n "$QUANTIZATION" ]]; then
  ARGS+=(--quantization "$QUANTIZATION")
fi

if [[ -n "${VLLM_API_KEY:-}" ]]; then
  ARGS+=(--api-key "$VLLM_API_KEY")
fi

vllm serve "${ARGS[@]}"
