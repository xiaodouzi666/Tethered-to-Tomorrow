from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("PROBE_HOST", "0.0.0.0")
    port: int = int(os.getenv("PROBE_PORT", "8010"))
    cors_allow_origin: str = os.getenv("CORS_ALLOW_ORIGIN", "*")

    gemma_backend: str = os.getenv("GEMMA_BACKEND", "litert_cli")  # auto | litert_py | litert_cli | mock
    require_real_gemma: bool = os.getenv("REQUIRE_REAL_GEMMA", "1") == "1"
    gemma_model_path: str = os.getenv("GEMMA_MODEL_PATH", "/home/pi/models/gemma-4-E2B-it.litertlm")
    gemma_model_repo: str = os.getenv("GEMMA_MODEL_REPO", "litert-community/gemma-4-E2B-it-litert-lm")
    gemma_model_file: str = os.getenv("GEMMA_MODEL_FILE", "gemma-4-E2B-it.litertlm")
    gemma_timeout_s: int = int(os.getenv("GEMMA_TIMEOUT_S", "120"))

    telemetry_hz: float = float(os.getenv("TELEMETRY_HZ", "1.0"))
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "1000"))


settings = Settings()
