from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from pi_probe.probe.state import HIGH_RISK_COMMANDS
from pi_probe.twin.schemas import (
    CampaignResponse,
    CommandPackage,
    CommandPackageStep,
    GroundTestbedSession,
    TwinAssemblyState,
    TwinPlanCandidate,
)


PACKAGE_PASS_RATE_THRESHOLD = 0.8


class CommandPackageStore:
    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._store: Dict[str, CommandPackage] = {}

    def create(self, package: CommandPackage) -> CommandPackage:
        self.prune()
        self._store[package.package_id] = package
        return package

    def get(self, package_id: str) -> Optional[CommandPackage]:
        self.prune()
        return self._store.get(package_id)

    def save(self, package: CommandPackage) -> CommandPackage:
        package.updated_at = time.time()
        self._store[package.package_id] = package
        return package

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_sec
        expired = [
            package_id
            for package_id, package in self._store.items()
            if package.updated_at < cutoff and package.status in {"DRAFT", "EXECUTED", "FAILED", "ABORTED"}
        ]
        for package_id in expired:
            self._store.pop(package_id, None)


def build_command_package(
    *,
    session: GroundTestbedSession,
    campaign: CampaignResponse,
    assembly: Optional[TwinAssemblyState] = None,
    plan_id: Optional[str] = None,
) -> CommandPackage:
    selected_plan_id = plan_id or campaign.best_plan_id
    plan = _plan_by_id(session.candidate_plans, selected_plan_id)
    if plan is None:
        raise ValueError(f"Unknown plan for command package: {selected_plan_id}")

    score = next((item for item in campaign.scores if item.plan_id == selected_plan_id), None)
    if score is None:
        raise ValueError(f"Campaign score not available for plan: {selected_plan_id}")
    gate_status, gate_reason = package_gate_status(score.verdict, score.pass_rate)

    now = time.time()
    plan_digest = _plan_digest(plan)
    return CommandPackage(
        package_id=f"cmdpkg-{uuid.uuid4().hex[:12]}",
        source_session_id=session.session_id,
        baseline_id=session.baseline.baseline_id,
        assembly_id=assembly.assembly_id if assembly else session.assembly_id or "",
        assembly_version=assembly.version if assembly else session.assembly_version,
        assembly_digest=assembly.assembly_digest if assembly else session.assembly_digest,
        plan_id=selected_plan_id,
        plan_digest=plan_digest,
        risk_score=score.worst_risk_score,
        pass_rate=score.pass_rate,
        steps=[
            _package_step(action=step.action.upper().strip(), params=step.params, earliest_send_t=step.at_t)
            for step in plan.actions
        ],
        requires_human_approval=True,
        status="DRAFT",
        gate_status=gate_status,
        gate_reason=gate_reason,
        created_at=now,
        updated_at=now,
        execution_log=[
            {
                "ts": now,
                "type": "package_created",
                "baseline_id": session.baseline.baseline_id,
                "baseline_digest": session.baseline.state_digest,
                "assembly_id": assembly.assembly_id if assembly else session.assembly_id,
                "assembly_version": assembly.version if assembly else session.assembly_version,
                "assembly_digest": assembly.assembly_digest if assembly else session.assembly_digest,
                "plan_digest": plan_digest,
                "message": gate_reason,
            }
        ],
    )


def approve_command_package(package: CommandPackage, approved_by: str = "operator") -> CommandPackage:
    package.approved_by = approved_by
    package.status = "APPROVED"
    package.updated_at = time.time()
    package.execution_log.append(
        {
            "ts": package.updated_at,
            "type": "approved",
            "message": f"Command package approved by {approved_by}.",
        }
    )
    return package


def mark_uplink_started(package: CommandPackage) -> CommandPackage:
    package.status = "UPLINKING"
    package.updated_at = time.time()
    package.execution_log.append(
        {
            "ts": package.updated_at,
            "type": "uplink_started",
            "message": f"Simulated one-way delay started ({package.uplink_delay_s:.1f}s).",
        }
    )
    return package


def package_gate_status(verdict: str, pass_rate: float) -> tuple[str, str]:
    if verdict != "PASS":
        return "blocked", f"Campaign verdict is {verdict}; Build Package requires PASS."
    if pass_rate < PACKAGE_PASS_RATE_THRESHOLD:
        return "blocked", f"Campaign pass_rate is {pass_rate:.0%}; Build Package requires at least 80%."
    return "pass", "Package safety gate passed."


def _plan_by_id(plans: List[TwinPlanCandidate], plan_id: str) -> Optional[TwinPlanCandidate]:
    for plan in plans:
        if plan.id == plan_id:
            return plan
    return None


def _plan_digest(plan: TwinPlanCandidate) -> str:
    payload = {
        "id": plan.id,
        "actions": [
            {
                "action": step.action.upper().strip(),
                "params": step.params,
                "at_t": step.at_t,
            }
            for step in plan.actions
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_step(action: str, params: Dict[str, Any], earliest_send_t: float) -> CommandPackageStep:
    return CommandPackageStep(
        action=action,
        params=params,
        earliest_send_t=earliest_send_t,
        preconditions=_preconditions(action),
        expected_effects=_expected_effects(action),
        abort_if=_abort_conditions(action),
    )


def _preconditions(action: str) -> List[str]:
    common = ["battery_voltage >= 10.5", "probe_link == ONLINE"]
    if action == "RESTART_COMMS":
        return common + ["packet_loss <= 0.80", "no active comms blackout"]
    if action == "RESET_THERMAL_CONTROLLER":
        return common + ["temp_c <= 110.0"]
    if action == "ENTER_SAFE_MODE":
        return ["battery_voltage >= 10.0"]
    if action in {"SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "DISABLE_INSTRUMENT"}:
        return ["battery_voltage >= 9.8", "probe_link == ONLINE"]
    if action == "SWITCH_TO_BACKUP_THRUSTER":
        return common + ["human_approval == true", "backup_thruster_branch_available == true"]
    if action == "ENABLE_THRUSTER_HEATERS":
        return common + ["human_approval == true", "power_margin_available == true"]
    if action == "RELOCATE_FDS_CODE":
        return common + ["human_approval == true", "fds_memory_map_verified == true"]
    if action in {"ISOLATE_TELEMETRY_PATH", "VERIFY_TELEMETRY_RECOVERY"}:
        return common + ["commands_still_accepted == true"]
    if action in HIGH_RISK_COMMANDS:
        return common + ["human_approval == true"]
    return common


def _expected_effects(action: str) -> Dict[str, Any]:
    if action == "LOWER_SAMPLING_RATE":
        return {"sampling_rate": "<=0.4", "packet_loss": "stabilizes within 60s"}
    if action == "RESTART_COMMS":
        return {"temporary_blackout_s": 4, "signal_strength": ">=0.15 after 30s"}
    if action == "RESET_THERMAL_CONTROLLER":
        return {"thermal_controller_stable": True, "temp_trend": "non-increasing after settling"}
    if action == "ENTER_SAFE_MODE":
        return {"payload_enabled": False, "load_w": "reduced"}
    if action == "SWITCH_TO_BACKUP_SENSOR":
        return {"using_backup_sensor": True}
    if action in {"SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "DISABLE_INSTRUMENT"}:
        return {"load_w": "reduced", "noncritical_instrument": "disabled if available"}
    if action == "SWITCH_TO_BACKUP_THRUSTER":
        return {"backup_thruster_enabled": True, "attitude_error_deg": "decreases after settling"}
    if action == "ENABLE_THRUSTER_HEATERS":
        return {"roll_thruster_heaters_enabled": True, "power_load": "slightly increased"}
    if action == "SHUT_DOWN_PRIMARY_ROLL_HEATER":
        return {"primary_roll_heater_enabled": False, "load_w": "reduced"}
    if action == "RESTORE_HEATER_POWER":
        return {"heater_power_state": "restored"}
    if action == "RELOCATE_FDS_CODE":
        return {"fds_code_relocated": True, "engineering_data_readable": True}
    if action == "ISOLATE_TELEMETRY_PATH":
        return {"telemetry_path_ok": True, "unresolved_root_cause": "retained"}
    if action == "VERIFY_TELEMETRY_RECOVERY":
        return {"telemetry_verification": "recorded"}
    return {"command_status": "accepted"}


def _abort_conditions(action: str) -> List[str]:
    conditions = ["battery_voltage < 10.5", "probe_link == OFFLINE"]
    if action == "RESTART_COMMS":
        conditions.append("comms blackout > 120s")
    if action == "RESET_THERMAL_CONTROLLER":
        conditions.append("temp_c > 115.0")
    if action in {"ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER", "RESTORE_HEATER_POWER"}:
        conditions.append("battery_voltage < 10.8")
    if action == "RELOCATE_FDS_CODE":
        conditions.append("engineering telemetry unreadable after relocation")
    return conditions
