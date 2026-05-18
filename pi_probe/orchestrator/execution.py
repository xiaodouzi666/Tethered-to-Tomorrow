from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from pi_probe.orchestrator.schemas import (
    ExecutionTicket,
    OrchestratorSession,
    SessionStatus,
    StepValidationResult,
)

LOW_RISK_LIVE_ACTIONS = {
    "ENTER_SAFE_MODE",
    "DISABLE_PAYLOAD",
    "LOWER_SAMPLING_RATE",
    "RESET_THERMAL_CONTROLLER",
    "CLEAR_CACHE",
    "SWITCH_TO_BACKUP_SENSOR",
    "SHED_NONESSENTIAL_LOAD",
    "REALLOCATE_POWER_BUDGET",
    "DISABLE_INSTRUMENT",
    "VERIFY_TELEMETRY_RECOVERY",
    "ISOLATE_TELEMETRY_PATH",
}
LIVE_BLOCKED_HIGH_RISK = {
    "REBOOT_COMPUTER",
    "EXIT_SAFE_MODE",
    "RESTART_COMMS",
    "SWITCH_TO_BACKUP_THRUSTER",
    "ENABLE_THRUSTER_HEATERS",
    "RESTORE_HEATER_POWER",
    "RELOCATE_FDS_CODE",
}


def create_execution_ticket(
    session: OrchestratorSession,
    *,
    plan_id: str,
    approved_by: str,
    dry_run: bool = True,
    ttl_sec: int = 300,
) -> ExecutionTicket:
    issued_at = time.time()
    return ExecutionTicket(
        ticket_id=f"ticket-{uuid.uuid4().hex[:12]}",
        session_id=session.session_id,
        baseline_id=session.baseline.baseline_id,
        plan_id=plan_id,
        plan_digest=_plan_digest(_plan_steps(session, plan_id)),
        approved_by=approved_by,
        issued_at=issued_at,
        expires_at=issued_at + ttl_sec,
        dry_run=dry_run,
    )


def dry_run_execute_next_step(
    session: OrchestratorSession,
    *,
    live_snapshot: Optional[Dict[str, Any]] = None,
) -> OrchestratorSession:
    if not session.execution_ticket:
        raise ValueError("Session has no approved execution ticket.")
    if time.time() > session.execution_ticket.expires_at:
        raise ValueError("Execution ticket has expired.")

    plan_id = session.execution_ticket.plan_id
    steps = _plan_steps(session, plan_id)
    if session.current_step_index >= len(steps):
        session.status = SessionStatus.COMPLETED
        return session

    step_index = session.current_step_index
    step = steps[step_index]
    action = str(step.get("action", "")).upper().strip()
    expected_frame = _expected_frame_for_action(session, plan_id, action, step_index)
    validation = validate_step_outcome(
        live_snapshot=live_snapshot,
        expected_frame=expected_frame,
        action=action,
        step_index=step_index,
        dry_run=True,
    )

    now = time.time()
    session.status = SessionStatus.OBSERVING
    session.execution_log.append(
        {
            "ts": now,
            "type": "would_execute",
            "dry_run": True,
            "step_index": step_index,
            "action": action,
            "params": step.get("params", {}),
            "baseline_id": session.baseline.baseline_id,
            "plan_id": plan_id,
            "ticket_id": session.execution_ticket.ticket_id,
            "message": f"Dry-run only: would execute {action}. No command was sent.",
        }
    )
    session.step_validation_log.append(validation)
    session.current_step_index += 1
    if session.current_step_index >= len(steps):
        session.status = SessionStatus.COMPLETED
    return session


def dry_run_execute_plan(
    session: OrchestratorSession,
    *,
    live_snapshot: Optional[Dict[str, Any]] = None,
    max_steps: int = 10,
) -> OrchestratorSession:
    steps_run = 0
    while steps_run < max_steps:
        before = session.current_step_index
        dry_run_execute_next_step(session, live_snapshot=live_snapshot)
        steps_run += 1
        if session.status == SessionStatus.COMPLETED or session.current_step_index == before:
            break
        last_validation = session.step_validation_log[-1] if session.step_validation_log else None
        if last_validation and last_validation.recommendation != "continue":
            break
    return session


def execute_next_step_live(
    session: OrchestratorSession,
    *,
    live_snapshot: Optional[Dict[str, Any]],
    command_executor: Callable[[str, Dict[str, Any], str], Dict[str, Any]],
) -> OrchestratorSession:
    if not session.execution_ticket:
        raise ValueError("Session has no approved execution ticket.")
    if time.time() > session.execution_ticket.expires_at:
        raise ValueError("Execution ticket has expired.")

    plan_id = session.execution_ticket.plan_id
    steps = _plan_steps(session, plan_id)
    if session.current_step_index >= len(steps):
        session.status = SessionStatus.COMPLETED
        return session

    step_index = session.current_step_index
    step = steps[step_index]
    action = str(step.get("action", "")).upper().strip()
    if action in LIVE_BLOCKED_HIGH_RISK or action not in LOW_RISK_LIVE_ACTIONS:
        session.execution_log.append(
            {
                "ts": time.time(),
                "type": "live_blocked",
                "dry_run": False,
                "step_index": step_index,
                "action": action,
                "message": f"{action} requires HITL/dry-run; live auto execution is blocked.",
            }
        )
        session.status = SessionStatus.REVIEW_READY
        return session

    expected_frame = _expected_frame_for_action(session, plan_id, action, step_index)
    result = command_executor(action, step.get("params", {}) if isinstance(step.get("params", {}), dict) else {}, "helm-live-execution")
    after_snapshot = result.get("after") if isinstance(result, dict) else live_snapshot
    validation = validate_step_outcome(
        live_snapshot=after_snapshot if isinstance(after_snapshot, dict) else live_snapshot,
        expected_frame=expected_frame,
        action=action,
        step_index=step_index,
        dry_run=False,
    )

    session.status = SessionStatus.OBSERVING
    session.execution_log.append(
        {
            "ts": time.time(),
            "type": "live_execute",
            "dry_run": False,
            "step_index": step_index,
            "action": action,
            "params": step.get("params", {}),
            "baseline_id": session.baseline.baseline_id,
            "plan_id": plan_id,
            "ticket_id": session.execution_ticket.ticket_id,
            "message": f"Live low-risk command executed: {action}.",
            "command_result": result,
        }
    )
    session.step_validation_log.append(validation)
    session.current_step_index += 1
    if validation.recommendation != "continue":
        session.status = SessionStatus.OBSERVING
        return session
    if session.current_step_index >= len(steps):
        session.status = SessionStatus.COMPLETED
    return session


def execute_plan_live(
    session: OrchestratorSession,
    *,
    live_snapshot: Optional[Dict[str, Any]],
    command_executor: Callable[[str, Dict[str, Any], str], Dict[str, Any]],
    max_steps: int = 10,
) -> OrchestratorSession:
    steps_run = 0
    while steps_run < max_steps:
        before = session.current_step_index
        execute_next_step_live(session, live_snapshot=live_snapshot, command_executor=command_executor)
        steps_run += 1
        if session.status in {SessionStatus.COMPLETED, SessionStatus.REVIEW_READY} or session.current_step_index == before:
            break
        last_validation = session.step_validation_log[-1] if session.step_validation_log else None
        if last_validation and last_validation.recommendation != "continue":
            break
    return session


def validate_step_outcome(
    *,
    live_snapshot: Optional[Dict[str, Any]],
    expected_frame: Optional[Dict[str, Any]],
    action: str,
    step_index: int,
    dry_run: bool = True,
) -> StepValidationResult:
    if dry_run:
        return StepValidationResult(
            step_index=step_index,
            action=action,
            passed=True,
            within_envelope=True,
            deviations=[
                {
                    "metric": "execution",
                    "kind": "dry_run",
                    "message": "No live command was sent; validation is a scaffold against the expected Twin frame.",
                }
            ],
            recommendation="continue",
            expected_frame_t=_frame_t(expected_frame),
            note="Dry-run validation only.",
        )

    deviations: List[Dict[str, Any]] = []
    if live_snapshot and expected_frame:
        for metric, tolerance in {
            "subsystems.thermal.temp_c": 12.0,
            "subsystems.power.battery_voltage": 0.8,
            "subsystems.comms.packet_loss": 0.35,
            "subsystems.comms.signal_strength": 0.35,
        }.items():
            live_value = _metric(live_snapshot, metric)
            expected_value = _metric(expected_frame, metric)
            if isinstance(live_value, (int, float)) and isinstance(expected_value, (int, float)):
                delta = abs(float(live_value) - float(expected_value))
                if delta > tolerance:
                    deviations.append({
                        "metric": metric,
                        "live": live_value,
                        "expected": expected_value,
                        "delta": round(delta, 4),
                        "tolerance": tolerance,
                    })

    passed = not deviations
    return StepValidationResult(
        step_index=step_index,
        action=action,
        passed=passed,
        within_envelope=passed,
        deviations=deviations,
        recommendation="continue" if passed else "pause",
        expected_frame_t=_frame_t(expected_frame),
        note="Live validation completed." if passed else "Live telemetry deviated from Twin envelope.",
    )


def _plan_steps(session: OrchestratorSession, plan_id: str) -> List[Dict[str, Any]]:
    for plan in session.plan_bundle.get("plans", []):
        if isinstance(plan, dict) and str(plan.get("id")) == plan_id:
            return [step for step in plan.get("actions", []) if isinstance(step, dict)]
    return []


def _plan_digest(steps: List[Dict[str, Any]]) -> str:
    payload = json.dumps(steps, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expected_frame_for_action(
    session: OrchestratorSession,
    plan_id: str,
    action: str,
    step_index: int,
) -> Optional[Dict[str, Any]]:
    for result in session.twin_compare.results:
        if result.plan_id != plan_id:
            continue
        for point in result.trajectory:
            last_command = point.get("last_command")
            if isinstance(last_command, dict) and str(last_command.get("action")) == action:
                return point
        if result.trajectory:
            return result.trajectory[min(step_index, len(result.trajectory) - 1)]
    return None


def _frame_t(frame: Optional[Dict[str, Any]]) -> Optional[float]:
    if not frame:
        return None
    value = frame.get("sim_t")
    return float(value) if isinstance(value, (int, float)) else None


def _metric(source: Dict[str, Any], dotted: str) -> Any:
    value: Any = source
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value
