from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pi_probe.config import settings


SYSTEM_PROMPT = """
You are DeepRepair OnboardGemmaDiagnosisAgent running locally on a simulated deep-space probe.
You must produce compact, valid JSON only. Do not output markdown.
You are not allowed to execute commands. You may only recommend actions from the whitelist.
Allowed actions: ENTER_SAFE_MODE, DISABLE_PAYLOAD, LOWER_SAMPLING_RATE, RESTART_COMMS, RESET_THERMAL_CONTROLLER, SWITCH_TO_BACKUP_SENSOR, CLEAR_CACHE.
Prefer conservative safe actions if telemetry is dangerous or uncertain.
""".strip()


@dataclass
class GemmaStatus:
    backend_requested: str
    backend_active: str
    ready: bool
    model_path: str
    model_file: str
    model_repo: str
    hf_repo: str
    require_real_gemma: bool
    message: str


class GemmaAdapter:
    """Small wrapper around a local Gemma 4 LiteRT-LM backend.

    Supports three modes:
    - litert_py: use LiteRT-LM Python API with a local .litertlm model path.
    - litert_cli: call litert-lm CLI, optionally pulling from a model repo.
    - mock: deterministic fallback for frontend/agent plumbing before the model is installed.

    In production/demo mode, set REQUIRE_REAL_GEMMA=1 to disable mock fallback.
    """

    def __init__(self) -> None:
        self._active_backend = "uninitialized"
        self._engine: Optional[Any] = None
        self._py_available = False
        self._cli_available = shutil.which("litert-lm") is not None
        try:
            import litert_lm  # type: ignore
            self._litert_lm = litert_lm
            self._py_available = True
        except Exception:
            self._litert_lm = None
            self._py_available = False

        self._choose_backend()

    def _choose_backend(self) -> None:
        requested = settings.gemma_backend
        model_exists = os.path.exists(settings.gemma_model_path)

        if requested in {"litert_py", "auto"} and self._py_available and model_exists:
            self._active_backend = "litert_py"
            return
        if requested in {"litert_cli", "auto"} and self._cli_available:
            self._active_backend = "litert_cli"
            return
        if requested == "mock" or not settings.require_real_gemma:
            self._active_backend = "mock"
            return
        self._active_backend = "missing"

    def status(self) -> GemmaStatus:
        ready = self._active_backend in {"litert_py", "litert_cli", "mock"} and not (
            settings.require_real_gemma and self._active_backend == "mock"
        )
        if self._active_backend == "mock":
            msg = "Mock backend active. Set REQUIRE_REAL_GEMMA=1 to force a real Gemma backend."
        elif self._active_backend == "litert_py":
            msg = "LiteRT-LM Python API backend active."
        elif self._active_backend == "litert_cli":
            msg = "LiteRT-LM CLI backend active."
        else:
            msg = "No usable Gemma backend found. Install LiteRT-LM and configure GEMMA_MODEL_PATH/GEMMA_MODEL_REPO."
        return GemmaStatus(
            backend_requested=settings.gemma_backend,
            backend_active=self._active_backend,
            ready=ready,
            model_path=settings.gemma_model_path,
            model_file=settings.gemma_model_file,
            model_repo=settings.gemma_model_repo,
            hf_repo=settings.gemma_model_repo,
            require_real_gemma=settings.require_real_gemma,
            message=msg,
        )

    def diagnose(self, telemetry_snapshot: Dict[str, Any], reason: str = "manual") -> Dict[str, Any]:
        if settings.require_real_gemma and self._active_backend == "mock":
            raise RuntimeError("REQUIRE_REAL_GEMMA=1, but real Gemma backend is not available.")
        if self._active_backend == "litert_py":
            raw = self._run_litert_py(telemetry_snapshot, reason)
            return self._parse_or_repair(raw, telemetry_snapshot)
        if self._active_backend == "litert_cli":
            raw = self._run_litert_cli(telemetry_snapshot, reason)
            return self._parse_or_repair(raw, telemetry_snapshot)
        if self._active_backend == "mock":
            return self._mock_diagnosis(telemetry_snapshot, reason)
        raise RuntimeError(self.status().message)

    def _prompt(self, telemetry_snapshot: Dict[str, Any], reason: str) -> str:
        compact = json.dumps(telemetry_snapshot, ensure_ascii=False)
        return f"""{SYSTEM_PROMPT}

Reason: {reason}
Telemetry snapshot JSON:
{compact}

Return exactly this JSON shape:
{{
  "agent": "OnboardGemmaDiagnosisAgent",
  "backend": "gemma-4-local",
  "fault_summary": ["short bullet 1", "short bullet 2"],
  "likely_causes": [{{"cause":"...", "confidence":0.0, "evidence":["..."]}}],
  "immediate_safe_actions": ["ENTER_SAFE_MODE"],
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "uncertainty": "..."
}}
""".strip()

    def _run_litert_py(self, telemetry_snapshot: Dict[str, Any], reason: str) -> str:
        litert_lm = self._litert_lm
        if litert_lm is None:
            raise RuntimeError("litert_lm Python API is not installed.")
        # Lazy-load the model once.
        if self._engine is None:
            self._engine = litert_lm.Engine(settings.gemma_model_path)
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": self._prompt(telemetry_snapshot, reason)}]},
        ]
        with self._engine.create_conversation(messages=messages) as conversation:
            response = conversation.send_message(self._prompt(telemetry_snapshot, reason))
        try:
            return response["content"][0]["text"]
        except Exception:
            return str(response)

    def _run_litert_cli(self, telemetry_snapshot: Dict[str, Any], reason: str) -> str:
        prompt = self._prompt(telemetry_snapshot, reason)
        cmd = [
            "litert-lm",
            "run",
            f"--from-huggingface-repo={settings.gemma_model_repo}",
            settings.gemma_model_file,
            f"--prompt={prompt}",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.gemma_timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"litert-lm failed: {completed.stderr.strip()}")
        return completed.stdout.strip()

    def _parse_or_repair(self, raw: str, telemetry_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            # Try to extract first JSON object from a verbose model response.
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        repaired = self._mock_diagnosis(telemetry_snapshot, "json-repair-fallback")
        repaired["raw_model_output"] = raw[:1500]
        repaired["backend_note"] = "Model returned non-JSON; repaired using deterministic safety fallback."
        return repaired

    def _mock_diagnosis(self, telemetry_snapshot: Dict[str, Any], reason: str) -> Dict[str, Any]:
        subs = telemetry_snapshot.get("subsystems", {})
        thermal = subs.get("thermal", {})
        power = subs.get("power", {})
        comms = subs.get("comms", {})
        computer = subs.get("computer", {})
        fault = telemetry_snapshot.get("active_fault", "none")
        mode = telemetry_snapshot.get("mode", "UNKNOWN")

        temp = float(thermal.get("temp_c", 0))
        battery = float(power.get("battery_voltage", 12.0))
        packet_loss = float(comms.get("packet_loss", 0))
        cpu = float(computer.get("cpu_load", 0))

        actions = []
        causes = []
        summary = []
        risk = "LOW"

        if temp > 70 or fault == "thermal":
            summary.append(f"Thermal trend unsafe: temp={temp:.1f}C, mode={mode}.")
            causes.append({"cause": "Thermal controller degradation or radiator efficiency loss", "confidence": 0.78, "evidence": ["temperature above warning band", f"active_fault={fault}"]})
            actions.extend(["ENTER_SAFE_MODE", "DISABLE_PAYLOAD", "RESET_THERMAL_CONTROLLER"])
            risk = "HIGH" if temp > 82 else "MEDIUM"
        if battery < 11.0 or fault == "power":
            summary.append(f"Power reserve degraded: battery={battery:.2f}V.")
            causes.append({"cause": "Excess payload/compute load causing power drain", "confidence": 0.7, "evidence": ["battery voltage below nominal", f"cpu_load={cpu:.2f}"]})
            actions.extend(["DISABLE_PAYLOAD", "LOWER_SAMPLING_RATE", "ENTER_SAFE_MODE"])
            risk = "HIGH"
        if packet_loss > 0.3 or fault == "comms":
            summary.append(f"Communication link degraded: packet_loss={packet_loss:.2f}.")
            causes.append({"cause": "Comms subsystem instability or thermal/power side effect", "confidence": 0.64, "evidence": ["packet loss over warning threshold"]})
            actions.extend(["LOWER_SAMPLING_RATE", "RESTART_COMMS"])
            risk = "MEDIUM" if risk == "LOW" else risk
        if fault == "sensor":
            summary.append("Primary sensor drift suspected; cross-check with backup sensor recommended.")
            causes.append({"cause": "Primary sensor drift", "confidence": 0.82, "evidence": ["active_fault=sensor"]})
            actions.append("SWITCH_TO_BACKUP_SENSOR")
            risk = "MEDIUM"

        if not summary:
            summary.append("No critical fault signature detected in the current telemetry snapshot.")
            causes.append({"cause": "Nominal telemetry", "confidence": 0.55, "evidence": ["all major metrics within nominal band"]})
            actions.append("LOWER_SAMPLING_RATE")

        # Deduplicate and keep conservative first actions.
        deduped = []
        for action in actions:
            if action not in deduped:
                deduped.append(action)
        return {
            "agent": "OnboardGemmaDiagnosisAgent",
            "backend": "mock-safety-fallback" if self._active_backend == "mock" else self._active_backend,
            "reason": reason,
            "fault_summary": summary[:2],
            "likely_causes": causes[:3],
            "immediate_safe_actions": deduped[:3],
            "risk_level": risk,
            "uncertainty": "This v1 diagnosis is bounded to onboard summary and white-listed safe actions only.",
        }
