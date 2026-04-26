from __future__ import annotations

from typing import Any, Dict, List

from pi_probe.agents.gemma_adapter import GemmaAdapter
from pi_probe.probe.state import ALLOWED_COMMANDS, HIGH_RISK_COMMANDS


class TelemetryAnomalyAgent:
    def analyze(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        subs = snapshot.get("subsystems", {})
        anomalies: List[str] = []
        affected: List[str] = []

        temp = subs.get("thermal", {}).get("temp_c", 0)
        battery = subs.get("power", {}).get("battery_voltage", 12)
        packet_loss = subs.get("comms", {}).get("packet_loss", 0)
        cpu_load = subs.get("computer", {}).get("cpu_load", 0)

        if temp > 70:
            anomalies.append(f"Thermal warning: temp={temp:.1f}C")
            affected.append("thermal")
        if battery < 11.0:
            anomalies.append(f"Power warning: battery={battery:.2f}V")
            affected.append("power")
        if packet_loss > 0.3:
            anomalies.append(f"Comms warning: packet_loss={packet_loss:.2f}")
            affected.append("comms")
        if cpu_load > 0.75:
            anomalies.append(f"Computer load warning: cpu_load={cpu_load:.2f}")
            affected.append("computer")

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
        self.gemma = GemmaAdapter()
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
