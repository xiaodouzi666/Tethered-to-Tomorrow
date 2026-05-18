from __future__ import annotations

from typing import Any, Dict, List, Set

from pi_probe.probe.state import ALLOWED_COMMANDS
from pi_probe.twin.augmentation import build_augmented_scenario
from pi_probe.twin.schemas import EnvironmentConfig, FaultSpec, PlanStep


def generate_rule_candidate_plans(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic recovery planner used before any LLM enhancement.

    The planner intentionally produces commands only. It does not score a plan;
    TwinEngine is responsible for numeric simulation, constraints, and risk.
    """

    context = infer_fault_context(snapshot)
    dominant = _dominant_context(context)
    plans = _plans_for_context(dominant)
    return {
        "agent": "TwinRecoveryPlanner",
        "source": "rules-fallback",
        "fault_context": sorted(context) or ["nominal"],
        "dominant_context": dominant,
        "plans": plans,
        "notes": [
            "Rules generate candidate actions only.",
            "TwinEngine must simulate and score all plans before execution.",
            "E4B may rank or explain plans but must not compute telemetry values.",
        ],
    }


def generate_rule_scenario(prompt: str) -> Dict[str, Any]:
    text = prompt.lower()
    if any(token in text for token in ["thermal", "heat", "radiator", "temperature", "hot"]):
        scenario = _thermal_scenario()
        profile = "thermal"
    elif any(token in text for token in ["comms", "packet", "signal", "antenna", "link"]):
        scenario = _comms_scenario()
        profile = "comms"
    elif any(token in text for token in ["power", "battery", "solar", "load", "voltage"]):
        scenario = _power_scenario()
        profile = "power"
    elif any(token in text for token in ["sensor", "drift", "stuck", "dropout"]):
        scenario = _sensor_scenario()
        profile = "sensor"
    elif any(token in text for token in ["thruster", "attitude", "pointing", "roll", "tcm"]):
        scenario = _attitude_scenario()
        profile = "attitude"
    elif any(token in text for token in ["fds", "telemetry", "engineering data", "science data", "memory chip", "aacs"]):
        scenario = _fds_scenario()
        profile = "fds"
    else:
        scenario = _thermal_scenario()
        profile = "thermal"
        scenario["scenario_id"] = "generated-general-recovery"
        scenario["title"] = "General Recovery Drill"

    difficulty = _difficulty_from_prompt(text)
    augmentation = build_augmented_scenario(
        profile,
        difficulty=difficulty,
        base_environment=EnvironmentConfig(**scenario["environment"]),
    )
    scenario["environment"] = augmentation["environment"]
    scenario["faults"] = augmentation["faults"]
    scenario["difficulty"] = difficulty
    scenario["augmentation"] = augmentation["augmentation"]
    scenario["prompt"] = prompt
    scenario["source"] = "rules-fallback"
    return scenario


def explain_twin_verdict_rule(snapshot: Dict[str, Any], twin_result: Dict[str, Any]) -> Dict[str, Any]:
    constraints = [_as_dict(item) for item in twin_result.get("constraints", [])]
    failed = [item for item in constraints if not item.get("passed", False)]
    passed = [item for item in constraints if item.get("passed", False)]
    final_snapshot = twin_result.get("final_snapshot", {})
    final_mode = twin_result.get("final_mode") or final_snapshot.get("mode", "UNKNOWN")
    risk = float(twin_result.get("risk_score", 100.0))
    verdict = str(twin_result.get("verdict", "UNKNOWN"))

    if failed:
        root = ", ".join(str(item.get("name", "constraint")) for item in failed[:3])
        summary = f"Twin verdict {verdict}: failed constraints include {root}."
    else:
        summary = f"Twin verdict {verdict}: all configured constraints passed."

    return {
        "agent": "TwinVerdictExplainer",
        "source": "rules-fallback",
        "summary": summary,
        "risk_score": risk,
        "final_mode": final_mode,
        "passed_constraints": [item.get("name") for item in passed],
        "failed_constraints": [item.get("name") for item in failed],
        "recommended_operator_readout": _operator_readout(snapshot, twin_result, failed),
    }


def infer_fault_context(snapshot: Dict[str, Any]) -> Set[str]:
    context: Set[str] = set()
    active_fault = str(snapshot.get("active_fault", "none")).lower()
    if active_fault != "none":
        context.add(active_fault)
    for fault in snapshot.get("active_faults", []):
        normalized = str(fault).lower()
        if normalized != "none":
            context.add(normalized)

    subs = snapshot.get("subsystems", {})
    power = subs.get("power", {})
    thermal = subs.get("thermal", {})
    comms = subs.get("comms", {})
    computer = subs.get("computer", {})
    payload = subs.get("payload", {})
    attitude = subs.get("attitude", {})
    fds = subs.get("fds", {})
    fault_layers = snapshot.get("fault_layers", {}) if isinstance(snapshot.get("fault_layers", {}), dict) else {}
    layer_ids = {
        str(item.get("id", "")).lower()
        for key in ("root_causes", "recoverable_faults", "symptoms")
        for item in fault_layers.get(key, [])
        if isinstance(item, dict)
    }

    if thermal.get("status") == "FAULT" or float(thermal.get("temp_c", 0.0)) > 70.0 or thermal.get("controller_ok") is False:
        context.add("thermal")
    if power.get("status") == "FAULT" or float(power.get("battery_voltage", 12.0)) < 11.0:
        context.add("power")
    if comms.get("status") == "FAULT" or float(comms.get("packet_loss", 0.0)) > 0.3:
        context.add("comms")
    if computer.get("status") == "FAULT" or float(computer.get("cpu_load", 0.0)) > 0.75:
        context.add("computer")
    if str(computer.get("storage_health", "")).startswith("sensor") or payload.get("using_backup_sensor"):
        context.add("sensor")
    if (
        attitude.get("status") == "FAULT"
        or float(attitude.get("attitude_error_deg", 0.0) or 0.0) > 1.0
        or {"primary_attitude_thruster_degradation", "roll_thruster_fuel_line_residue_buildup", "thruster_heater_power_switch_error", "primary_roll_thruster_heater_power_cost"} & layer_ids
    ):
        context.add("attitude")
    if (
        fds.get("status") == "FAULT"
        or fds.get("engineering_data_readable") is False
        or fds.get("science_data_readable") is False
        or {"fds_memory_chip_failure", "fds_code_segment_loss", "telemetry_path_fault_unresolved"} & layer_ids
    ):
        context.add("fds")
    if {"rtg_power_decline", "instrument_heater_power_burden", "thermal_support_load_too_high", "primary_roll_thruster_heater_power_cost"} & layer_ids:
        context.add("power")
    return context


def plans_to_twin_candidates(planner_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = []
    for plan in planner_output.get("plans", []):
        candidates.append({
            "id": plan["id"],
            "label": plan.get("label", plan["id"]),
            "actions": plan.get("actions", []),
        })
    return candidates


def _plans_for_context(context: str) -> List[Dict[str, Any]]:
    if context == "thermal":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "DISABLE_PAYLOAD", "RESET_THERMAL_CONTROLLER"], [0, 2, 20], "Maximize thermal safety before recovery."),
            _plan("plan-b", "Standard", "balanced recovery", ["DISABLE_PAYLOAD", "RESET_THERMAL_CONTROLLER", "LOWER_SAMPLING_RATE"], [0, 6, 12], "Reduce heat load and recover controller."),
            _plan("plan-c", "Aggressive", "fast recovery", ["RESET_THERMAL_CONTROLLER", "LOWER_SAMPLING_RATE"], [0, 8], "Restore controller first, preserving more mission activity."),
        ]
    if context == "comms":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["LOWER_SAMPLING_RATE", "ENTER_SAFE_MODE", "RESTART_COMMS"], [0, 3, 12], "Lower link pressure before restarting communications."),
            _plan("plan-b", "Standard", "balanced recovery", ["LOWER_SAMPLING_RATE", "RESTART_COMMS"], [0, 8], "Reduce traffic and attempt link recovery."),
            _plan("plan-c", "Aggressive", "fast recovery", ["RESTART_COMMS"], [0], "Restart communications immediately."),
        ]
    if context == "power":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "SHED_NONESSENTIAL_LOAD", "DISABLE_PAYLOAD"], [0, 2, 4], "Minimize power draw and shed noncritical science load first."),
            _plan("plan-b", "Standard", "balanced recovery", ["SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "LOWER_SAMPLING_RATE"], [0, 3, 8], "Preserve core operations while progressively recovering power margin."),
            _plan("plan-c", "Aggressive", "fast recovery", ["DISABLE_INSTRUMENT", "LOWER_SAMPLING_RATE", "CLEAR_CACHE"], [0, 4, 8], "Shed one science instrument and reduce data rate before clearing compute load."),
        ]
    if context == "sensor":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "SWITCH_TO_BACKUP_SENSOR"], [0, 4], "Stabilize mode before changing sensor path."),
            _plan("plan-b", "Standard", "balanced recovery", ["SWITCH_TO_BACKUP_SENSOR", "LOWER_SAMPLING_RATE"], [0, 8], "Move to backup sensor and reduce data rate."),
            _plan("plan-c", "Aggressive", "fast recovery", ["SWITCH_TO_BACKUP_SENSOR"], [0], "Switch sensor path immediately."),
        ]
    if context == "computer":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "CLEAR_CACHE", "LOWER_SAMPLING_RATE"], [0, 2, 6], "Reduce compute activity and clear memory pressure."),
            _plan("plan-b", "Standard", "balanced recovery", ["CLEAR_CACHE", "LOWER_SAMPLING_RATE"], [0, 5], "Clear memory pressure while preserving operations."),
            _plan("plan-c", "Aggressive", "fast recovery", ["CLEAR_CACHE"], [0], "Clear cache immediately."),
        ]
    if context == "attitude":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"], [0, 5, 18], "Stabilize power/thermal state before validating backup attitude control."),
            _plan("plan-b", "Standard", "balanced recovery", ["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER", "LOWER_SAMPLING_RATE"], [0, 10, 20], "Warm dormant thrusters, move pointing control to backup, and reduce data pressure."),
            _plan("plan-c", "Aggressive", "fast recovery", ["SWITCH_TO_BACKUP_THRUSTER"], [0], "Switch attitude control path immediately; requires high-confidence operator review."),
        ]
    if context == "fds":
        return [
            _plan("plan-a", "Conservative", "safe recovery", ["ENTER_SAFE_MODE", "ISOLATE_TELEMETRY_PATH", "RELOCATE_FDS_CODE", "VERIFY_TELEMETRY_RECOVERY"], [0, 3, 12, 30], "Stabilize operations, isolate the telemetry path, relocate FDS code, then verify recovered data."),
            _plan("plan-b", "Standard", "balanced recovery", ["ISOLATE_TELEMETRY_PATH", "RELOCATE_FDS_CODE", "VERIFY_TELEMETRY_RECOVERY"], [0, 8, 22], "Repair FDS path without entering safe mode while preserving auditability."),
            _plan("plan-c", "Aggressive", "fast recovery", ["RELOCATE_FDS_CODE", "VERIFY_TELEMETRY_RECOVERY"], [0, 18], "Relocate FDS code immediately; memory-chip root cause remains."),
        ]
    return [
        _plan("plan-a", "Conservative", "safe recovery", ["LOWER_SAMPLING_RATE"], [0], "Reduce mission load while observing."),
        _plan("plan-b", "Standard", "balanced recovery", [], [], "No action; continue observing nominal telemetry."),
        _plan("plan-c", "Aggressive", "fast recovery", ["CLEAR_CACHE"], [0], "Refresh compute state without changing mode."),
    ]


def _dominant_context(context: Set[str]) -> str:
    for candidate in ["thermal", "power", "attitude", "fds", "comms", "sensor", "computer"]:
        if candidate in context:
            return candidate
    return "nominal"


def _difficulty_from_prompt(text: str) -> str:
    if any(token in text for token in ["extreme", "severe", "critical"]):
        return "extreme"
    if any(token in text for token in ["hard", "difficult", "multi", "compound", "double"]):
        return "hard"
    if any(token in text for token in ["easy", "simple", "basic"]):
        return "easy"
    return "medium"


def _plan(
    plan_id: str,
    label: str,
    posture: str,
    actions: List[str],
    at_times: List[float],
    rationale: str,
) -> Dict[str, Any]:
    steps = []
    for index, action in enumerate(actions):
        if action not in ALLOWED_COMMANDS:
            continue
        steps.append(_dump_model(PlanStep(action=action, params={}, at_t=at_times[index] if index < len(at_times) else 0)))
    return {
        "id": plan_id,
        "label": label,
        "posture": posture,
        "actions": steps,
        "rationale": rationale,
        "llm_annotation": "",
    }


def _thermal_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-thermal-recovery",
        "title": "Thermal Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(thermal_sink_efficiency=0.82, eclipse_factor=0.1)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-thermal-radiator", category="thermal", severity=0.72, start_t=0, duration=300, parameters={"radiator_efficiency_drop": 0.4}))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Recover thermal margin without unnecessary mission loss.",
    }


def _comms_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-comms-recovery",
        "title": "Comms Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(radiation_level=0.12, antenna_alignment_error_deg=4.0)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-comms-degrade", category="comms", severity=0.72, start_t=0, duration=300, parameters={"antenna_alignment_error_deg": 18, "transceiver_degradation": True}))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Recover command link while preserving probe safety.",
    }


def _power_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-power-recovery",
        "title": "Power Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(sun_exposure=0.8, eclipse_factor=0.2, battery_age_factor=0.9)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-power-load", category="power", severity=0.68, start_t=0, duration=300, parameters={"load_spike": 5.4, "battery_age_factor": 0.72}))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Recover power margin and avoid deep discharge.",
    }


def _sensor_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-sensor-recovery",
        "title": "Sensor Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(radiation_level=0.18)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-sensor-drift", category="sensor", severity=0.62, start_t=0, duration=300, parameters={"drift": 0.18}))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Identify unreliable sensing and switch to backup path.",
    }


def _attitude_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-attitude-recovery",
        "title": "Attitude Thruster Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(radiation_level=0.08, antenna_alignment_error_deg=2.0)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-attitude-thruster", category="primary_attitude_thruster_degradation", severity=0.7, start_t=0, duration=300))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Recover pointing control without losing command link or power margin.",
    }


def _fds_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": "generated-fds-recovery",
        "title": "FDS Telemetry Recovery Drill",
        "environment": _dump_model(EnvironmentConfig(radiation_level=0.12)),
        "faults": [
            _dump_model(FaultSpec(id="scenario-fds-code", category="fds_code_segment_loss", severity=0.68, start_t=0, duration=300))
        ],
        "horizon_sec": 300,
        "dt": 1.0,
        "operator_goal": "Restore readable engineering and science telemetry while retaining root-cause evidence.",
    }


def _operator_readout(snapshot: Dict[str, Any], twin_result: Dict[str, Any], failed: List[Dict[str, Any]]) -> str:
    seq = snapshot.get("seq", "--")
    verdict = twin_result.get("verdict", "UNKNOWN")
    risk = twin_result.get("risk_score", "--")
    if failed:
        names = ", ".join(str(item.get("name", "constraint")) for item in failed[:2])
        return f"Snapshot {seq}: Twin predicts {verdict} at risk {risk}/100; watch {names}."
    return f"Snapshot {seq}: Twin predicts {verdict} at risk {risk}/100; constraints remain inside limits."


def _dump_model(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}
