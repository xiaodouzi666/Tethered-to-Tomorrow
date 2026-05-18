from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import copy
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pi_probe.config import settings


SYSTEM_PROMPT = """
You are DeepRepair OnboardE4BDiagnosisAgent running locally on a simulated deep-space probe.
You must produce compact, valid JSON only. Do not output markdown.
You are not allowed to execute commands. You may only recommend actions from the whitelist.
Allowed actions: ENTER_SAFE_MODE, DISABLE_PAYLOAD, LOWER_SAMPLING_RATE, RESTART_COMMS, RESET_THERMAL_CONTROLLER, SWITCH_TO_BACKUP_SENSOR, SWITCH_TO_BACKUP_THRUSTER, ENABLE_THRUSTER_HEATERS, SHED_NONESSENTIAL_LOAD, DISABLE_INSTRUMENT, REALLOCATE_POWER_BUDGET, CLEAR_CACHE, RELOCATE_FDS_CODE, ISOLATE_TELEMETRY_PATH, VERIFY_TELEMETRY_RECOVERY.
Prefer conservative safe actions if telemetry is dangerous or uncertain.
""".strip()


@dataclass
class E4BStatus:
    backend_requested: str
    backend_active: str
    ready: bool
    model: str
    api_base: str
    model_path: str
    model_file: str
    model_repo: str
    hf_repo: str
    require_real_gemma: bool
    message: str


class E4BAdapter:
    """Small wrapper around local or remote E4B backends.

    Supports three modes:
    - remote_vllm: call an OpenAI-compatible vLLM server.
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

        if requested in {"remote_vllm", "auto"} and settings.gemma_api_base:
            self._active_backend = "remote_vllm"
            return
        if requested in {"litert_py", "auto"} and self._py_available and settings.gemma_model_path and model_exists:
            self._active_backend = "litert_py"
            return
        if requested in {"litert_cli", "auto"} and self._cli_available and settings.gemma_model_repo and settings.gemma_model_file:
            self._active_backend = "litert_cli"
            return
        if requested == "mock" or not settings.require_real_gemma:
            self._active_backend = "mock"
            return
        self._active_backend = "missing"

    def status(self) -> E4BStatus:
        ready = self._active_backend in {"remote_vllm", "litert_py", "litert_cli", "mock"} and not (
            settings.require_real_gemma and self._active_backend == "mock"
        )
        display_model = "E4B"
        if self._active_backend == "mock":
            msg = "Mock backend active. Set REQUIRE_REAL_GEMMA=1 to force a real E4B backend."
        elif self._active_backend == "remote_vllm":
            msg = f"Remote vLLM backend active for {display_model}."
        elif self._active_backend == "litert_py":
            msg = "LiteRT-LM Python API backend active."
        elif self._active_backend == "litert_cli":
            msg = "LiteRT-LM CLI backend active."
        else:
            msg = "No usable E4B backend found. Configure GEMMA_API_BASE for remote vLLM, or install LiteRT-LM and configure GEMMA_MODEL_PATH/GEMMA_MODEL_REPO."
        return E4BStatus(
            backend_requested=settings.gemma_backend,
            backend_active=self._active_backend,
            ready=ready,
            model=display_model,
            api_base=settings.gemma_api_base,
            model_path="",
            model_file="",
            model_repo="",
            hf_repo="",
            require_real_gemma=settings.require_real_gemma,
            message=msg,
        )

    def diagnose(self, telemetry_snapshot: Dict[str, Any], reason: str = "manual") -> Dict[str, Any]:
        if settings.require_real_gemma and self._active_backend == "mock":
            raise RuntimeError("REQUIRE_REAL_GEMMA=1, but real E4B backend is not available.")
        if self._active_backend == "remote_vllm":
            raw = self._run_remote_vllm(telemetry_snapshot, reason)
            return self._parse_or_repair(raw, telemetry_snapshot)
        if self._active_backend == "litert_py":
            raw = self._run_litert_py(telemetry_snapshot, reason)
            return self._parse_or_repair(raw, telemetry_snapshot)
        if self._active_backend == "litert_cli":
            raw = self._run_litert_cli(telemetry_snapshot, reason)
            return self._parse_or_repair(raw, telemetry_snapshot)
        if self._active_backend == "mock":
            return self._mock_diagnosis(telemetry_snapshot, reason)
        raise RuntimeError(self.status().message)

    def rank_candidate_plans(self, telemetry_snapshot: Dict[str, Any], planner_output: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "agent": "OnboardE4BPlanningAgent",
            "source": "rules-fallback",
            "ordered_plan_ids": [plan.get("id") for plan in planner_output.get("plans", [])],
            "plan_annotations": {
                plan.get("id"): {
                    "summary": plan.get("rationale", ""),
                    "mission_tradeoff": plan.get("posture", ""),
                    "debrief": "Plan generated by deterministic onboard rules.",
                }
                for plan in planner_output.get("plans", [])
            },
        }
        system = """
You are DeepRepair OnboardE4BPlanningAgent.
Return compact valid JSON only.
You may rank and explain candidate plans, but you must not invent telemetry values, risk scores, constraints, or numeric simulation results.
You must not add, remove, or modify actions. Only return plan IDs and textual annotations.
""".strip()
        user = f"""
Telemetry snapshot:
{json.dumps(telemetry_snapshot, ensure_ascii=False)}

Rule-generated candidate plans:
{json.dumps(planner_output, ensure_ascii=False)}

Return exactly:
{{
  "agent": "OnboardE4BPlanningAgent",
  "source": "e4b-enhanced",
  "ordered_plan_ids": ["plan-a", "plan-b", "plan-c"],
  "plan_annotations": {{
    "plan-a": {{"summary":"...", "mission_tradeoff":"...", "debrief":"..."}}
  }}
}}
""".strip()
        return self._json_task(system, user, fallback, task_name="rank_candidate_plans")

    def explain_twin_verdict(
        self,
        telemetry_snapshot: Dict[str, Any],
        twin_result: Dict[str, Any],
        rule_explanation: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = copy.deepcopy(rule_explanation)
        system = """
You are DeepRepair TwinDebriefAgent.
Return compact valid JSON only.
You explain TwinEngine results for an operator.
Do not recompute risk, constraints, thresholds, telemetry, or trajectory values.
Use only the supplied TwinEngine result numbers.
""".strip()
        user = f"""
Telemetry snapshot:
{json.dumps(telemetry_snapshot, ensure_ascii=False)}

TwinEngine result:
{json.dumps(twin_result, ensure_ascii=False)}

Rule fallback explanation:
{json.dumps(rule_explanation, ensure_ascii=False)}

Return exactly:
{{
  "agent": "TwinDebriefAgent",
  "source": "e4b-enhanced",
  "summary": "...",
  "operator_debrief": ["short item 1", "short item 2"],
  "why_it_passed_or_failed": "...",
  "next_best_action": "..."
}}
""".strip()
        return self._json_task(system, user, fallback, task_name="explain_twin_verdict")

    def troubleshoot_component(
        self,
        assembly_state: Dict[str, Any],
        session_state: Dict[str, Any],
        rule_troubleshooting: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = copy.deepcopy(rule_troubleshooting)
        fallback["source"] = "rules-fallback"
        system = """
You are DeepRepair E4B ComponentTroubleshootingAgent.
Return compact valid JSON only.
You are given a modular spacecraft digital-twin assembly graph, component fault templates, current ground-testbed session, and a deterministic rule-based troubleshooting draft.
You may propose troubleshooting hypotheses and safe verification steps.
You must not invent telemetry, risk scores, pass rates, or commands outside the whitelist.
Allowed actions: ENTER_SAFE_MODE, DISABLE_PAYLOAD, LOWER_SAMPLING_RATE, RESTART_COMMS, RESET_THERMAL_CONTROLLER, SWITCH_TO_BACKUP_SENSOR, CLEAR_CACHE, REBOOT_COMPUTER.
Mark RESTART_COMMS and REBOOT_COMPUTER as HITL/high-risk if mentioned.
""".strip()
        user = f"""
Modular assembly graph:
{json.dumps(assembly_state, ensure_ascii=False)}

Ground-testbed session:
{json.dumps(session_state, ensure_ascii=False)}

Rule-based troubleshooting draft:
{json.dumps(rule_troubleshooting, ensure_ascii=False)}

Return exactly:
{{
  "agent": "ComponentTroubleshootingAgent",
  "source": "e4b-enhanced",
  "summary": "...",
  "most_likely_component": {{"component_id":"...", "why":"...", "confidence":0.0}},
  "troubleshooting_tree": [{{"step":"...", "observe":"...", "branch_if":"..."}}],
  "candidate_plans": [{{"label":"...", "actions":["LOWER_SAMPLING_RATE"], "risk_notes":"...", "requires_hitl":false}}],
  "operator_questions": ["..."]
}}
""".strip()
        return self._json_task(system, user, fallback, task_name="troubleshoot_component")

    def enhance_scenario(self, prompt: str, rule_scenario: Dict[str, Any]) -> Dict[str, Any]:
        fallback = copy.deepcopy(rule_scenario)
        fallback["llm_brief"] = {
            "source": "rules-fallback",
            "brief": rule_scenario.get("operator_goal", ""),
            "evaluation_focus": ["constraint margin", "payload impact", "recovery time"],
        }
        system = """
You are DeepRepair ScenarioBriefAgent.
Return compact valid JSON only.
You may write scenario briefing text and evaluation goals.
Do not compute trajectory values, risk scores, or constraint results.
Do not change the provided environment, faults, horizon, or dt.
""".strip()
        user = f"""
Operator prompt:
{prompt}

Rule-generated scenario config:
{json.dumps(rule_scenario, ensure_ascii=False)}

Return exactly:
{{
  "source": "e4b-enhanced",
  "brief": "...",
  "operator_goal": "...",
  "evaluation_focus": ["...", "..."],
  "debrief_questions": ["...", "..."]
}}
""".strip()
        enhanced = self._json_task(system, user, fallback["llm_brief"], task_name="enhance_scenario")
        merged = copy.deepcopy(rule_scenario)
        merged["llm_brief"] = enhanced
        return merged

    def _prompt(self, telemetry_snapshot: Dict[str, Any], reason: str) -> str:
        compact = json.dumps(telemetry_snapshot, ensure_ascii=False)
        return f"""{SYSTEM_PROMPT}

Reason: {reason}
Telemetry snapshot JSON:
{compact}

Return exactly this JSON shape:
{{
  "agent": "OnboardE4BDiagnosisAgent",
  "backend": "e4b-backend",
  "fault_summary": ["short bullet 1", "short bullet 2"],
  "likely_causes": [{{"cause":"...", "confidence":0.0, "evidence":["..."]}}],
  "immediate_safe_actions": ["ENTER_SAFE_MODE"],
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "uncertainty": "..."
}}
""".strip()

    def _openai_chat_url(self) -> str:
        if not settings.gemma_api_base:
            raise RuntimeError("GEMMA_API_BASE is required for GEMMA_BACKEND=remote_vllm.")
        base = settings.gemma_api_base.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return f"{base}/chat/completions"

    def _run_remote_vllm(self, telemetry_snapshot: Dict[str, Any], reason: str) -> str:
        prompt = self._prompt(telemetry_snapshot, reason)
        return self._run_remote_vllm_prompt(SYSTEM_PROMPT, prompt)

    def _run_remote_vllm_prompt(self, system_prompt: str, prompt: str, max_tokens: Optional[int] = None) -> str:
        payload = {
            "model": settings.gemma_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.gemma_temperature,
            "max_tokens": max_tokens or settings.gemma_max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if settings.gemma_api_key:
            headers["Authorization"] = f"Bearer {settings.gemma_api_key}"
        request = urllib.request.Request(
            self._openai_chat_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.gemma_timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                fallback_model = self._first_remote_model_id(headers)
                if fallback_model and fallback_model != payload["model"]:
                    payload["model"] = fallback_model
                    retry = urllib.request.Request(
                        self._openai_chat_url(),
                        data=json.dumps(payload).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(retry, timeout=settings.gemma_timeout_s) as response:
                            data = json.loads(response.read().decode("utf-8"))
                        return data["choices"][0]["message"]["content"]
                    except Exception as retry_exc:
                        raise RuntimeError(
                            f"remote vLLM retry with served E4B model '{fallback_model}' failed: {retry_exc}"
                        ) from retry_exc
            raise RuntimeError(f"remote vLLM request failed: HTTP {exc.code}: {body[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"remote vLLM request failed: {exc.reason}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"remote vLLM returned an unexpected response: {str(data)[:1000]}") from exc

    def _first_remote_model_id(self, headers: Dict[str, str]) -> Optional[str]:
        base = settings.gemma_api_base.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        request = urllib.request.Request(f"{base}/models", headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        models = data.get("data") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return None
        ids = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
        if not ids:
            return None
        preferred = [model_id for model_id in ids if "e4b" in model_id.lower() or "gemma" in model_id.lower()]
        return preferred[0] if preferred else ids[0]

    def _json_task(self, system_prompt: str, prompt: str, fallback: Dict[str, Any], task_name: str) -> Dict[str, Any]:
        if self._active_backend != "remote_vllm":
            result = copy.deepcopy(fallback)
            result["llm_enhancement"] = {
                "available": False,
                "backend": self._active_backend,
                "message": "LLM enhancement skipped; deterministic rules are active.",
                "task": task_name,
            }
            return result
        try:
            raw = self._run_remote_vllm_prompt(system_prompt, prompt)
            parsed = self._parse_json_object(raw)
            parsed = self._canonicalize_model_json(parsed)
            parsed["llm_enhancement"] = {
                "available": True,
                "backend": self._active_backend,
                "task": task_name,
            }
            return parsed
        except Exception as exc:
            result = copy.deepcopy(fallback)
            result["llm_enhancement"] = {
                "available": False,
                "backend": self._active_backend,
                "message": str(exc)[:500],
                "task": task_name,
            }
            return result

    def _parse_json_object(self, raw: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("Model did not return a JSON object.")

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
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return self._canonicalize_model_json(parsed, telemetry_snapshot)
            return parsed
        except Exception:
            # Try to extract first JSON object from a verbose model response.
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return self._canonicalize_model_json(parsed, telemetry_snapshot)
                    return parsed
                except Exception:
                    pass
        repaired = self._mock_diagnosis(telemetry_snapshot, "json-repair-fallback")
        repaired["raw_model_output"] = raw[:1500]
        repaired["backend_note"] = "Model returned non-JSON; repaired using deterministic safety fallback."
        return repaired

    def _canonicalize_model_json(
        self,
        parsed: Dict[str, Any],
        source_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not settings.canonicalize_strategies:
            return parsed
        try:
            from pi_probe.helm.strategy_normalizer import normalize_model_output

            return normalize_model_output(parsed, source_payload=source_payload or parsed)
        except Exception as exc:
            result = dict(parsed)
            result["strategy_label_normalizer_error"] = str(exc)[:300]
            return result

    def _mock_diagnosis(self, telemetry_snapshot: Dict[str, Any], reason: str) -> Dict[str, Any]:
        subs = telemetry_snapshot.get("subsystems", {})
        thermal = subs.get("thermal", {})
        power = subs.get("power", {})
        comms = subs.get("comms", {})
        computer = subs.get("computer", {})
        attitude = subs.get("attitude", {})
        fds = subs.get("fds", {})
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
            causes.append({"cause": "RTG/power margin decline or excess science/heater load", "confidence": 0.7, "evidence": ["battery voltage below nominal", f"cpu_load={cpu:.2f}"]})
            actions.extend(["SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "ENTER_SAFE_MODE"])
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
        if fault == "attitude" or float(attitude.get("attitude_error_deg", 0.0) or 0.0) > 1.0:
            summary.append("Pointing control efficiency is degraded; primary thruster path may be unreliable.")
            causes.append({"cause": "Primary attitude/roll thruster degradation", "confidence": 0.76, "evidence": [f"attitude_error_deg={attitude.get('attitude_error_deg', '--')}", f"active_fault={fault}"]})
            actions.extend(["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"])
            risk = "HIGH" if risk == "LOW" else risk
        if fault in {"fds", "telemetry"} or fds.get("engineering_data_readable") is False or fds.get("science_data_readable") is False:
            summary.append("Telemetry/FDS data path is inconsistent or unreadable.")
            causes.append({"cause": "FDS memory/code path or telemetry packaging anomaly", "confidence": 0.72, "evidence": [f"storage_health={computer.get('storage_health', '--')}", f"active_fault={fault}"]})
            actions.extend(["ISOLATE_TELEMETRY_PATH", "RELOCATE_FDS_CODE", "VERIFY_TELEMETRY_RECOVERY"])
            risk = "HIGH" if risk == "LOW" else risk

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
            "agent": "OnboardE4BDiagnosisAgent",
            "backend": "mock-safety-fallback" if self._active_backend == "mock" else self._active_backend,
            "reason": reason,
            "fault_summary": summary[:2],
            "likely_causes": causes[:3],
            "immediate_safe_actions": deduped[:3],
            "risk_level": risk,
            "uncertainty": "This v1 diagnosis is bounded to onboard summary and white-listed safe actions only.",
        }
