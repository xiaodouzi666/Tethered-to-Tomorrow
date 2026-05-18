from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from pi_probe.helm.dialogue import build_operator_question, response_for_choice
from pi_probe.helm.monitor import monitor_snapshot
from pi_probe.helm.planner import propose_candidate_plans
from pi_probe.helm.reviewer import review_twin_compare
from pi_probe.helm.schemas import (
    HelmDialogueRequest,
    HelmMonitorResult,
    HelmOperatorQuestion,
    HelmReviewResult,
    HelmStatusResponse,
)


class E4BHelmRuntime:
    def __init__(
        self,
        *,
        agents: Any,
        allowed_commands: Iterable[str],
        high_risk_commands: Iterable[str],
        auto_monitor_enabled: bool = False,
        live_execution_enabled: bool = False,
        brain_mode_default: Any = "classic_python",
    ):
        self.agents = agents
        self.allowed_commands = list(allowed_commands)
        self.high_risk_commands = list(high_risk_commands)
        self.auto_monitor_enabled = auto_monitor_enabled
        self.live_execution_enabled = live_execution_enabled
        self.brain_mode_default = brain_mode_default
        self.last_monitor_result: Optional[HelmMonitorResult] = None

    def status(self) -> HelmStatusResponse:
        gemma_status = self.agents.gemma_status()
        backend = gemma_status.get("backend_requested") or gemma_status.get("backend")
        gemma_ready = bool(gemma_status.get("ok", True)) and backend != "mock"
        return HelmStatusResponse(
            ready=True,
            gemma_ready=gemma_ready,
            fallback_enabled=True,
            auto_monitor_enabled=self.auto_monitor_enabled,
            live_execution_enabled=self.live_execution_enabled,
            brain_mode_default=self.brain_mode_default,
            detail=gemma_status,
        )

    def monitor_snapshot(self, snapshot: Dict[str, Any], recent_events: Iterable[Dict[str, Any]] | None = None) -> HelmMonitorResult:
        result = monitor_snapshot(snapshot, recent_events)
        self.last_monitor_result = result
        return result

    def diagnose_current_state(
        self,
        *,
        snapshot: Dict[str, Any],
        fault_layers: Dict[str, Any],
        recent_events: Iterable[Dict[str, Any]] | None,
        reason: str,
    ) -> Dict[str, Any]:
        try:
            diagnosis = self.agents.diagnose(snapshot, reason=reason)
            diagnosis["helm_source"] = "gemma"
            return diagnosis
        except Exception as exc:
            return self._fallback_diagnosis(snapshot, fault_layers, str(exc))

    def propose_candidate_plans(self, snapshot: Dict[str, Any], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        bundle = propose_candidate_plans(
            snapshot=snapshot,
            diagnosis=diagnosis,
            agents=self.agents,
            allowed_commands=self.allowed_commands,
        )
        bundle["helm_source"] = bundle.get("helm_source", "gemma-or-rules")
        return bundle

    def review_twin_compare(
        self,
        *,
        snapshot: Dict[str, Any],
        twin_compare: Any,
        plan_bundle: Dict[str, Any],
        policy_result: Any,
    ) -> HelmReviewResult:
        return review_twin_compare(
            snapshot=snapshot,
            twin_compare=twin_compare,
            plan_bundle=plan_bundle,
            policy_result=policy_result,
            agents=self.agents,
        )

    def ask_operator_question(
        self,
        *,
        review_mode: str,
        recommended_plan_id: str | None,
        helm_review: HelmReviewResult | None,
        policy_result: Any,
    ) -> HelmOperatorQuestion:
        return build_operator_question(
            review_mode=review_mode,
            recommended_plan_id=recommended_plan_id,
            helm_review=helm_review,
            policy_result=policy_result,
        )

    def response_for_dialogue(self, req: HelmDialogueRequest, context: Dict[str, Any]) -> str:
        return response_for_choice(req.choice, context)

    def _fallback_diagnosis(self, snapshot: Dict[str, Any], fault_layers: Dict[str, Any], reason: str) -> Dict[str, Any]:
        summaries: List[str] = []
        for item in fault_layers.get("root_causes", []):
            if isinstance(item, dict):
                summaries.append(f"Root cause active: {item.get('id')}")
        for item in fault_layers.get("recoverable_faults", []):
            if isinstance(item, dict) and str(item.get("status", "active")) == "active":
                summaries.append(f"Recoverable fault active: {item.get('id')}")
        if not summaries and snapshot.get("active_fault") not in {None, "none"}:
            summaries.append(f"Active fault label: {snapshot.get('active_fault')}")
        if not summaries:
            summaries.append("No active Helm rule fault detected.")
        return {
            "agent": "E4BHelmRuntime",
            "backend": "rules-fallback",
            "fault_summary": summaries,
            "likely_causes": [],
            "immediate_safe_actions": [],
            "risk_level": "LOW" if snapshot.get("active_fault") in {None, "none"} else "MEDIUM",
            "uncertainty": f"E4B unavailable; rule fallback used. Reason: {reason}",
            "helm_source": "rules-fallback",
        }
