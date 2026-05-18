from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("PROBE_HOST", "0.0.0.0")
    port: int = int(os.getenv("PROBE_PORT", "8010"))
    cors_allow_origin: str = os.getenv("CORS_ALLOW_ORIGIN", "*")

    gemma_backend: str = os.getenv("GEMMA_BACKEND", "remote_vllm")  # remote_vllm | auto | litert_py | litert_cli | mock
    require_real_gemma: bool = os.getenv("REQUIRE_REAL_GEMMA", "1") == "1"
    gemma_model: str = os.getenv("GEMMA_MODEL", "gemma4_e4b_tuned")
    gemma_api_base: str = os.getenv("GEMMA_API_BASE", "")
    gemma_api_key: str = os.getenv("GEMMA_API_KEY", "")
    gemma_temperature: float = float(os.getenv("GEMMA_TEMPERATURE", "0.2"))
    gemma_max_tokens: int = int(os.getenv("GEMMA_MAX_TOKENS", "768"))
    gemma_model_path: str = os.getenv("GEMMA_MODEL_PATH", "")
    gemma_model_repo: str = os.getenv("GEMMA_MODEL_REPO", "")
    gemma_model_file: str = os.getenv("GEMMA_MODEL_FILE", "")
    gemma_timeout_s: int = int(os.getenv("GEMMA_TIMEOUT_S", "120"))

    telemetry_hz: float = float(os.getenv("TELEMETRY_HZ", "1.0"))
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "1000"))

    brain_mode: str = os.getenv("BRAIN_MODE", "classic_python")
    helm_auto_monitor_enabled: bool = os.getenv("HELM_AUTO_MONITOR_ENABLED", "0") == "1"
    helm_live_execution_enabled: bool = os.getenv("HELM_LIVE_EXECUTION_ENABLED", "0") == "1"
    gemma_runtime_role: str = os.getenv("GEMMA_RUNTIME_ROLE", "assistant")
    canonicalize_strategies: bool = os.getenv("CANONICALIZE_STRATEGIES", "1") == "1"


settings = Settings()
