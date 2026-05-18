from __future__ import annotations

from typing import Any, Dict, List

from pi_probe.agents.gemma_adapter import E4BAdapter
from pi_probe.probe.state import ALLOWED_COMMANDS, HIGH_RISK_COMMANDS
from pi_probe.twin.planner import (
    explain_twin_verdict_rule,
    generate_rule_candidate_plans,
    generate_rule_scenario,
)


class TelemetryAnomalyAgent:
    def analyze(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        subs = snapshot.get("subsystems", {})
        anomalies: List[str] = []
        affected: List[str] = []
        active_fault = str(snapshot.get("active_fault", "none")).lower()

        thermal = subs.get("thermal", {})
        power = subs.get("power", {})
        comms = subs.get("comms", {})
        computer = subs.get("computer", {})
        payload = subs.get("payload", {})
        attitude = subs.get("attitude", {})
        fds = subs.get("fds", {})

        temp = thermal.get("temp_c", 0)
        battery = power.get("battery_voltage", 12)
        packet_loss = comms.get("packet_loss", 0)
        cpu_load = computer.get("cpu_load", 0)

        if temp > 70:
            anomalies.append(f"Thermal warning: temp={temp:.1f}C")
            affected.append("thermal")
        if active_fault == "thermal" or thermal.get("controller_ok") is False or float(thermal.get("radiator_efficiency", 1.0)) < 0.5:
            anomalies.append(
                f"Thermal fault signature: controller_ok={thermal.get('controller_ok')}, radiator_efficiency={thermal.get('radiator_efficiency')}"
            )
            affected.append("thermal")
        if battery < 11.0:
            anomalies.append(f"Power warning: battery={battery:.2f}V")
            affected.append("power")
        if active_fault == "power":
            anomalies.append(f"Power fault injected: load_w={power.get('load_w')}, cpu_load={cpu_load:.2f}")
            affected.append("power")
        if packet_loss > 0.3:
            anomalies.append(f"Comms warning: packet_loss={packet_loss:.2f}")
            affected.append("comms")
        if active_fault == "comms":
            anomalies.append(f"Comms fault injected: signal_strength={comms.get('signal_strength')}, packet_loss={packet_loss:.2f}")
            affected.append("comms")
        if cpu_load > 0.75:
            anomalies.append(f"Computer load warning: cpu_load={cpu_load:.2f}")
            affected.append("computer")
        if active_fault == "sensor" or payload.get("using_backup_sensor"):
            anomalies.append(
                f"Sensor fault signature: storage_health={computer.get('storage_health')}, using_backup_sensor={payload.get('using_backup_sensor')}"
            )
            affected.append("payload")
        if active_fault == "attitude" or float(attitude.get("attitude_error_deg", 0.0) or 0.0) > 1.0:
            anomalies.append(
                f"Attitude fault signature: attitude_error_deg={attitude.get('attitude_error_deg')}, backup_thruster={attitude.get('backup_thruster_enabled')}"
            )
            affected.append("attitude")
        if active_fault in {"fds", "telemetry"} or fds.get("engineering_data_readable") is False or fds.get("science_data_readable") is False:
            anomalies.append(
                f"FDS/telemetry fault signature: engineering_data_readable={fds.get('engineering_data_readable')}, science_data_readable={fds.get('science_data_readable')}"
            )
            affected.append("fds")

        severity = "NOMINAL"
        if snapshot.get("mode") == "FAULT" or len(anomalies) >= 2:
            severity = "FAULT"
        elif anomalies:
            severity = "WARNING"

        return {
            "agent": "TelemetryAnomalyAgent",
            "severity": severity,
            "affected_subsystems": sorted(set(affected)),
            "anomaly_summary": anomalies or ["No anomaly over v1 thresholds."],
        }


class SafetyGateAgent:
    def filter_actions(self, actions: List[str]) -> Dict[str, Any]:
        allowed = []
        blocked = []
        high_risk = []
        for action in actions:
            normalized = str(action).upper().strip()
            if normalized not in ALLOWED_COMMANDS:
                blocked.append({"action": action, "reason": "not_in_whitelist"})
            elif normalized in HIGH_RISK_COMMANDS:
                high_risk.append({"action": normalized, "reason": "requires_human_approval"})
                allowed.append(normalized)
            else:
                allowed.append(normalized)
        return {
            "agent": "SafetyGateAgent",
            "allowed_actions": allowed,
            "blocked_actions": blocked,
            "high_risk_actions": high_risk,
        }


class OnboardAgentRuntime:
    def __init__(self) -> None:
        self.gemma = E4BAdapter()
        self.anomaly = TelemetryAnomalyAgent()
        self.safety = SafetyGateAgent()

    def gemma_status(self) -> Dict[str, Any]:
        return self.gemma.status().__dict__

    def diagnose(self, snapshot: Dict[str, Any], reason: str = "manual") -> Dict[str, Any]:
        anomaly = self.anomaly.analyze(snapshot)
        diagnosis = self.gemma.diagnose(snapshot, reason=reason)
        gate = self.safety.filter_actions(diagnosis.get("immediate_safe_actions", []))
        return {
            "ok": True,
            "snapshot_seq": snapshot.get("seq"),
            "anomaly": anomaly,
            "diagnosis": diagnosis,
            "safety_gate": gate,
        }

    def generate_candidate_plans(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        rule_output = generate_rule_candidate_plans(snapshot)
        gemma_ranking = self.gemma.rank_candidate_plans(snapshot, rule_output)
        ordered_plans = _merge_plan_ranking(rule_output["plans"], gemma_ranking)
        return {
            "ok": True,
            "snapshot_seq": snapshot.get("seq"),
            "agent": "OnboardE4BRecoveryPlanner",
            "rule_planner": rule_output,
            "gemma_ranking": gemma_ranking,
            "plans": ordered_plans,
            "safety_gate": self.safety.filter_actions(_all_actions(ordered_plans)),
        }

    def explain_twin_verdict(self, snapshot: Dict[str, Any], twin_result: Dict[str, Any]) -> Dict[str, Any]:
        rule_explanation = explain_twin_verdict_rule(snapshot, twin_result)
        gemma_explanation = self.gemma.explain_twin_verdict(snapshot, twin_result, rule_explanation)
        return {
            "ok": True,
            "snapshot_seq": snapshot.get("seq"),
            "agent": "OnboardE4BTwinExplainer",
            "rule_explanation": rule_explanation,
            "explanation": gemma_explanation,
        }

    def troubleshoot_component(
        self,
        assembly_state: Dict[str, Any],
        session_state: Dict[str, Any],
        rule_troubleshooting: Dict[str, Any],
    ) -> Dict[str, Any]:
        enhanced = self.gemma.troubleshoot_component(assembly_state, session_state, rule_troubleshooting)
        gate = self.safety.filter_actions(_all_actions(enhanced.get("candidate_plans", [])))
        return {
            "ok": True,
            "agent": "OnboardE4BComponentTroubleshooter",
            "troubleshooting": enhanced,
            "safety_gate": gate,
        }

    def generate_scenario(self, prompt: str) -> Dict[str, Any]:
        rule_scenario = generate_rule_scenario(prompt)
        scenario = self.gemma.enhance_scenario(prompt, rule_scenario)
        return {
            "ok": True,
            "agent": "OnboardE4BScenarioAgent",
            "scenario": scenario,
        }


def _merge_plan_ranking(plans: List[Dict[str, Any]], gemma_ranking: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {plan["id"]: plan for plan in plans}
    ordered_ids = [
        str(plan_id)
        for plan_id in gemma_ranking.get("ordered_plan_ids", [])
        if str(plan_id) in by_id
    ]
    for plan in plans:
        if plan["id"] not in ordered_ids:
            ordered_ids.append(plan["id"])

    annotations = gemma_ranking.get("plan_annotations", {})
    merged: List[Dict[str, Any]] = []
    for plan_id in ordered_ids:
        plan = dict(by_id[plan_id])
        annotation = annotations.get(plan_id, {})
        if isinstance(annotation, dict):
            plan["llm_annotation"] = annotation
        merged.append(plan)
    return merged


def _all_actions(plans: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    for plan in plans:
        for step in plan.get("actions", []):
            action = step.get("action") if isinstance(step, dict) else None
            if action:
                actions.append(str(action))
    return actions
