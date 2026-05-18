from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from pi_probe.twin.constraints import evaluate_constraints, verdict_from_constraints
from pi_probe.twin.schemas import (
    ActionEvent,
    ConstraintFrame,
    ConstraintResult,
    EnvironmentConfig,
    EnvironmentEvent,
    PlanPlaybackBundle,
    RepairTraceStep,
    SubsystemFrame,
    TwinPlaybackFrame,
    TwinRunResponse,
)

SUBSYSTEMS = ["power", "thermal", "comms", "computer", "payload", "sensor", "attitude", "fds"]

ROOT_BY_SUBSYSTEM = {
    "power": {"battery_aged", "power_bus_degraded", "solar_panel_efficiency_drop", "rtg_power_decline", "long_term_power_generation_loss"},
    "thermal": {"radiator_degraded", "sun_exposure_overlimit"},
    "comms": {"antenna_misalignment", "link_budget_degraded"},
    "computer": {"storage_degraded"},
    "payload": {"instrument_heater_power_burden", "thermal_support_load_too_high", "primary_roll_thruster_heater_power_cost"},
    "sensor": {"primary_sensor_hardware_failed", "sensor_mount_shifted"},
    "attitude": {"primary_attitude_thruster_degradation", "roll_thruster_fuel_line_residue_buildup"},
    "fds": {"fds_memory_chip_failure", "telemetry_path_fault_unresolved", "aacs_or_packaging_chain_anomaly"},
}

RECOVERABLE_BY_SUBSYSTEM = {
    "power": {"load_spike_transient"},
    "thermal": {"thermal_controller_stuck", "heater_stuck_on"},
    "comms": {"transceiver_softlock", "comms_stack_stall"},
    "computer": {"compute_overload_transient", "memory_leak_runtime", "cache_accumulation"},
    "payload": set(),
    "sensor": {"sensor_readout_fault", "sensor_calibration_drift_runtime"},
    "attitude": {"thruster_heater_power_switch_error", "dormant_roll_thrusters_unavailable", "attitude_controller_stuck"},
    "fds": {"fds_code_segment_loss", "telemetry_decoder_stale"},
}

MITIGATIONS_BY_SUBSYSTEM = {
    "power": {"safe_mode", "payload_disabled", "instrument_load_shed", "power_budget_reallocated"},
    "thermal": {"thermal_controller_reset_recently", "safe_mode", "payload_disabled"},
    "comms": {"restarting_comms", "sampling_rate_reduced"},
    "computer": {"rebooting", "clear_cache", "safe_mode"},
    "payload": {"payload_disabled", "sampling_rate_reduced", "instrument_load_shed", "primary_roll_heater_shutdown"},
    "sensor": {"using_backup_sensor"},
    "attitude": {"backup_thruster_branch", "roll_thruster_heaters_enabled", "heater_power_restored", "primary_roll_heater_shutdown"},
    "fds": {"fds_code_relocated", "telemetry_path_isolated", "telemetry_recovery_verified"},
}

ACTION_SUBSYSTEMS = {
    "RESET_THERMAL_CONTROLLER": ["thermal"],
    "RESTART_COMMS": ["comms"],
    "SWITCH_TO_BACKUP_SENSOR": ["sensor"],
    "ENTER_SAFE_MODE": ["power", "thermal", "payload", "computer"],
    "EXIT_SAFE_MODE": ["power", "payload"],
    "DISABLE_PAYLOAD": ["payload", "thermal", "power"],
    "ENABLE_PAYLOAD": ["payload", "power"],
    "LOWER_SAMPLING_RATE": ["comms", "payload"],
    "CLEAR_CACHE": ["computer"],
    "REBOOT_COMPUTER": ["computer", "comms"],
    "SHED_NONESSENTIAL_LOAD": ["power", "payload"],
    "REALLOCATE_POWER_BUDGET": ["power", "payload"],
    "DISABLE_INSTRUMENT": ["payload", "power"],
    "RESTORE_INSTRUMENT": ["payload", "power"],
    "SWITCH_TO_BACKUP_THRUSTER": ["attitude", "comms"],
    "ENABLE_THRUSTER_HEATERS": ["attitude", "power"],
    "SHUT_DOWN_PRIMARY_ROLL_HEATER": ["attitude", "power"],
    "RESTORE_HEATER_POWER": ["attitude", "power"],
    "RELOCATE_FDS_CODE": ["fds", "computer"],
    "VERIFY_TELEMETRY_RECOVERY": ["fds", "comms"],
    "ISOLATE_TELEMETRY_PATH": ["fds", "comms"],
}


def build_playback_bundle(
    *,
    compare_id: str,
    baseline_id: str,
    plan_id: str,
    label: str,
    recommended: bool,
    baseline_snapshot: Dict[str, Any],
    run: TwinRunResponse,
    environment: EnvironmentConfig,
) -> PlanPlaybackBundle:
    action_events = _action_events(run.trajectory, run.repair_trace)
    frames: List[TwinPlaybackFrame] = []
    previous_metrics = _visible_metrics(baseline_snapshot)
    for index, point in enumerate(run.trajectory):
        prefix = run.trajectory[: index + 1]
        checks = evaluate_constraints(prefix)
        verdict = verdict_from_constraints(checks)
        risk_score = _risk_score(checks)
        visible_snapshot = _visible_snapshot(point)
        key_metric_deltas = _metric_deltas(previous_metrics, _visible_metrics(visible_snapshot))
        current_action = _current_action_for_frame(float(point.get("sim_t", 0.0)), action_events)
        fault_layers = _fault_layers(point)
        frames.append(
            TwinPlaybackFrame(
                t=float(point.get("sim_t", 0.0)),
                seq_offset=max(0, int(point.get("seq", 0)) - int(baseline_snapshot.get("seq", 0))),
                mode=str(point.get("mode", "UNKNOWN")),
                current_action=current_action,
                subsystem_frames=_subsystem_frames(point, fault_layers, current_action),
                visible_snapshot=visible_snapshot,
                hidden_fault_layers=fault_layers,
                constraint_frame=ConstraintFrame(
                    t=float(point.get("sim_t", 0.0)),
                    checks=checks,
                    risk_score=risk_score,
                    verdict=verdict,
                ),
                key_metric_deltas=key_metric_deltas,
            )
        )
        previous_metrics = _visible_metrics(visible_snapshot)

    return PlanPlaybackBundle(
        compare_id=compare_id,
        baseline_id=baseline_id,
        plan_id=plan_id,
        label=label,
        recommended=recommended,
        baseline_snapshot=baseline_snapshot,
        frames=frames,
        action_events=action_events,
        environment_events=_environment_events(environment),
        repair_trace=run.repair_trace,
        verdict=run.verdict,
        risk_score=run.risk_score,
        recovery_time_s=_recovery_time(frames),
    )


def _visible_snapshot(point: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sim_t": point.get("sim_t"),
        "mode": point.get("mode"),
        "active_fault": point.get("active_fault"),
        "primary_fault": point.get("primary_fault"),
        "active_faults": point.get("active_faults", []),
        "subsystems": point.get("subsystems", {}),
        "last_command": point.get("last_command"),
    }


def _fault_layers(point: Dict[str, Any]) -> Dict[str, Any]:
    layers = point.get("fault_layers")
    if isinstance(layers, dict):
        return layers
    return {
        "root_causes": [],
        "recoverable_faults": [],
        "active_mitigations": [],
        "symptoms": [],
    }


def _subsystem_frames(point: Dict[str, Any], fault_layers: Dict[str, Any], current_action: Optional[str]) -> List[SubsystemFrame]:
    subsystems = point.get("subsystems", {})
    frames: List[SubsystemFrame] = []
    for subsystem_id in SUBSYSTEMS:
        source = _subsystem_source(subsystems, subsystem_id)
        hidden = _hidden_for_subsystem(fault_layers, subsystem_id)
        health_state = _health_state(subsystem_id, source, str(point.get("mode", "")), hidden)
        action_active = bool(current_action and subsystem_id in ACTION_SUBSYSTEMS.get(current_action, []))
        highlight = _highlight_intensity(health_state, hidden, action_active)
        frames.append(
            SubsystemFrame(
                subsystem_id=subsystem_id,
                health_state=health_state,
                highlight_intensity=highlight,
                visible_metrics=source,
                hidden_state=hidden,
                note=_subsystem_note(subsystem_id, hidden, current_action),
            )
        )
    return frames


def _subsystem_source(subsystems: Dict[str, Any], subsystem_id: str) -> Dict[str, Any]:
    if subsystem_id == "sensor":
        payload = subsystems.get("payload", {})
        computer = subsystems.get("computer", {})
        return {
            "using_backup_sensor": payload.get("using_backup_sensor", False) if isinstance(payload, dict) else False,
            "storage_health": computer.get("storage_health", "nominal") if isinstance(computer, dict) else "nominal",
        }
    value = subsystems.get(subsystem_id, {})
    return value if isinstance(value, dict) else {}


def _hidden_for_subsystem(fault_layers: Dict[str, Any], subsystem_id: str) -> Dict[str, Any]:
    return {
        "root_causes": _filter_records(fault_layers.get("root_causes", []), subsystem_id, ROOT_BY_SUBSYSTEM[subsystem_id]),
        "recoverable_faults": _filter_records(fault_layers.get("recoverable_faults", []), subsystem_id, RECOVERABLE_BY_SUBSYSTEM[subsystem_id]),
        "mitigations": _filter_records(fault_layers.get("active_mitigations", []), subsystem_id, MITIGATIONS_BY_SUBSYSTEM[subsystem_id]),
        "symptoms": _filter_records(fault_layers.get("symptoms", []), subsystem_id, set()),
    }


def _filter_records(records: Any, subsystem_id: str, accepted_ids: set[str]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    if not isinstance(records, list):
        return filtered
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id", ""))
        system = str(record.get("system", ""))
        if record_id in accepted_ids or system == subsystem_id:
            filtered.append(record)
    return filtered


def _health_state(subsystem_id: str, source: Dict[str, Any], mode: str, hidden: Dict[str, Any]) -> str:
    if mode == "SAFE_MODE":
        return "safe"
    if subsystem_id == "payload" and source.get("enabled") is False:
        return "disabled"
    status = str(source.get("status", "OK")).upper()
    if status == "FAULT":
        return "fault"
    if status == "WARN":
        return "warning"
    active_hidden = [
        item
        for key in ("root_causes", "recoverable_faults", "symptoms")
        for item in hidden.get(key, [])
        if str(item.get("status", "active")) in {"active", "fault", "warning"}
    ]
    if active_hidden:
        return "warning"
    return "normal"


def _highlight_intensity(health_state: str, hidden: Dict[str, Any], action_active: bool) -> float:
    base = {
        "fault": 1.0,
        "warning": 0.68,
        "safe": 0.45,
        "disabled": 0.36,
        "normal": 0.12,
    }.get(health_state, 0.12)
    if hidden.get("root_causes"):
        base = max(base, 0.72)
    if action_active:
        base = 1.0
    return round(min(1.0, base), 3)


def _subsystem_note(subsystem_id: str, hidden: Dict[str, Any], current_action: Optional[str]) -> str:
    if current_action and subsystem_id in ACTION_SUBSYSTEMS.get(current_action, []):
        return f"{current_action} is affecting {subsystem_id}."
    root = [str(item.get("id")) for item in hidden.get("root_causes", [])]
    recoverable = [str(item.get("id")) for item in hidden.get("recoverable_faults", []) if str(item.get("status", "active")) == "active"]
    if root and recoverable:
        return f"{', '.join(recoverable)} active; {', '.join(root)} remains."
    if root:
        return f"{', '.join(root)} remains."
    if recoverable:
        return f"{', '.join(recoverable)} active."
    return ""


def _action_events(trajectory: List[Dict[str, Any]], repair_trace: List[RepairTraceStep]) -> List[ActionEvent]:
    events: List[ActionEvent] = []
    used_times: set[float] = set()
    for index, trace in enumerate(repair_trace):
        t = _find_action_time(trajectory, trace.action, used_times)
        used_times.add(t)
        events.append(
            ActionEvent(
                t=t,
                step_index=trace.step_index,
                action=trace.action,
                affected_subsystems=ACTION_SUBSYSTEMS.get(trace.action, []),
                summary=_trace_summary(trace),
            )
        )
    return events


def _find_action_time(trajectory: List[Dict[str, Any]], action: str, used_times: set[float]) -> float:
    for point in trajectory:
        last_command = point.get("last_command")
        if not isinstance(last_command, dict):
            continue
        if last_command.get("action") == action:
            t = float(point.get("sim_t", 0.0))
            if t not in used_times:
                return t
    return 0.0


def _trace_summary(trace: RepairTraceStep) -> str:
    parts: List[str] = []
    if trace.cleared_faults:
        parts.append("Cleared " + ", ".join(trace.cleared_faults))
    if trace.suppressed_faults:
        parts.append("Suppressed " + ", ".join(trace.suppressed_faults))
    if trace.remaining_root_causes:
        parts.append(", ".join(trace.remaining_root_causes) + " remains")
    return "; ".join(parts) if parts else trace.note


def _current_action_for_frame(t: float, events: Iterable[ActionEvent]) -> Optional[str]:
    for event in events:
        if event.t <= t <= event.t + 6.0:
            return event.action
    return None


def _environment_events(environment: EnvironmentConfig) -> List[EnvironmentEvent]:
    events: List[EnvironmentEvent] = []
    if environment.eclipse_factor > 0.05:
        events.append(EnvironmentEvent(t=0.0, event_type="eclipse", label="Eclipse factor active", payload={"eclipse_factor": environment.eclipse_factor}))
    if environment.radiation_level > 0.05:
        events.append(EnvironmentEvent(t=0.0, event_type="radiation", label="Radiation level elevated", payload={"radiation_level": environment.radiation_level}))
    if environment.antenna_alignment_error_deg > 1.0:
        events.append(EnvironmentEvent(t=0.0, event_type="alignment", label="Antenna alignment offset", payload={"antenna_alignment_error_deg": environment.antenna_alignment_error_deg}))
    if environment.thermal_sink_efficiency < 0.95:
        events.append(EnvironmentEvent(t=0.0, event_type="thermal_sink", label="Thermal sink efficiency reduced", payload={"thermal_sink_efficiency": environment.thermal_sink_efficiency}))
    if environment.battery_age_factor < 0.98:
        events.append(EnvironmentEvent(t=0.0, event_type="battery_age", label="Battery aging penalty active", payload={"battery_age_factor": environment.battery_age_factor}))
    return events


def _recovery_time(frames: List[TwinPlaybackFrame], stable_frames: int = 5) -> Optional[float]:
    streak = 0
    first_t: Optional[float] = None
    for frame in frames:
        layers = frame.hidden_fault_layers
        recoverables = layers.get("recoverable_faults", []) if isinstance(layers, dict) else []
        active_recoverables = [
            item
            for item in recoverables
            if isinstance(item, dict) and str(item.get("status", "active")) == "active"
        ]
        ok = (
            frame.constraint_frame.verdict == "PASS"
            and frame.mode != "FAULT"
            and not active_recoverables
        )
        if ok:
            if streak == 0:
                first_t = frame.t
            streak += 1
            if streak >= stable_frames:
                return first_t
        else:
            streak = 0
            first_t = None
    return None


def _visible_metrics(snapshot: Dict[str, Any]) -> Dict[str, float]:
    subsystems = snapshot.get("subsystems", {})
    values = {
        "temp_c": _metric(subsystems, "thermal", "temp_c"),
        "battery_voltage": _metric(subsystems, "power", "battery_voltage"),
        "packet_loss": _metric(subsystems, "comms", "packet_loss"),
        "signal_strength": _metric(subsystems, "comms", "signal_strength"),
        "cpu_load": _metric(subsystems, "computer", "cpu_load"),
    }
    return {key: value for key, value in values.items() if value is not None}


def _metric(subsystems: Dict[str, Any], subsystem: str, metric: str) -> Optional[float]:
    source = subsystems.get(subsystem, {})
    if not isinstance(source, dict):
        return None
    value = source.get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _metric_deltas(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, float]:
    deltas: Dict[str, float] = {}
    for key, after_value in after.items():
        before_value = before.get(key)
        if before_value is None:
            continue
        delta = round(after_value - before_value, 4)
        if delta:
            deltas[key] = delta
    return deltas


def _risk_score(results: List[ConstraintResult]) -> float:
    if not results:
        return 100.0
    failed_penalty = sum(1 for result in results if not result.passed) / len(results)
    margin_penalty = sum(_constraint_margin(result) for result in results) / len(results)
    normalized = max(0.0, min(1.0, failed_penalty + 0.25 * margin_penalty))
    return round(normalized * 100.0, 1)


def _constraint_margin(result: ConstraintResult) -> float:
    if result.threshold in (None, 0) or result.worst_value is None:
        return 0.0 if result.passed else 1.0
    if "<=" in result.name:
        return max(0.0, (result.worst_value - result.threshold) / abs(result.threshold))
    if ">=" in result.name:
        return max(0.0, (result.threshold - result.worst_value) / abs(result.threshold))
    return 0.0 if result.passed else 1.0
