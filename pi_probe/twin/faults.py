from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from pi_probe.probe.state import SpacecraftState
from pi_probe.twin.schemas import FaultSpec


THERMAL_FAULTS = {"radiator_efficiency_drop", "thermal_controller_stuck", "heater_stuck_on"}
COMMS_FAULTS = {"antenna_misalignment", "transceiver_degradation", "burst_packet_loss"}
POWER_FAULTS = {"battery_aging_penalty", "load_spike", "solar_panel_efficiency_loss"}
COMPUTER_FAULTS = {"memory_leak", "scheduler_overload", "reboot_instability"}
SENSOR_FAULTS = {"sensor_drift", "drift", "stuck_value", "intermittent_dropout", "single_channel_sensor_anomaly"}
ATTITUDE_FAULTS = {
    "attitude",
    "attitude_thruster_degradation",
    "primary_attitude_thruster_degradation",
    "pointing_control_efficiency_loss",
    "roll_thruster_fuel_line_residue_buildup",
    "roll_thruster_clogging_risk",
    "dormant_roll_thrusters_unavailable",
    "heater_power_control_switch_state_error",
    "primary_roll_thruster_heater_power_cost",
}
FDS_FAULTS = {
    "fds",
    "telemetry",
    "telemetry_inconsistency",
    "telemetry_path_fault_unresolved",
    "engineering_data_unreadable",
    "science_data_unreadable",
    "aacs_state_mismatch",
    "aacs_or_packaging_chain_anomaly",
    "fds_memory_chip_failure",
    "fds_code_segment_loss",
    "link_stable_no_safe_mode",
    "commands_still_accepted",
}
DATASET_POWER_FAULTS = {
    "power_margin_reduction",
    "power_margin",
    "rtg_power_decline",
    "long_term_power_generation_loss",
    "thermal_support_load_too_high",
    "instrument_heater_shutdown_decision",
}
TOP_LEVEL_FAULTS = {"thermal", "comms", "power", "computer", "sensor", "attitude", "fds", "telemetry", "power_margin"}
KNOWN_FAULTS = (
    TOP_LEVEL_FAULTS
    | THERMAL_FAULTS
    | COMMS_FAULTS
    | POWER_FAULTS
    | COMPUTER_FAULTS
    | SENSOR_FAULTS
    | ATTITUDE_FAULTS
    | FDS_FAULTS
    | DATASET_POWER_FAULTS
)


def active_fault_specs(faults: Iterable[FaultSpec], sim_t: float) -> List[FaultSpec]:
    return [
        fault
        for fault in faults
        if fault.start_t <= sim_t <= fault.start_t + fault.duration
    ]


def active_fault_systems(faults: Iterable[FaultSpec], sim_t: float) -> Set[str]:
    systems: Set[str] = set()
    for fault in active_fault_specs(faults, sim_t):
        category = _category(fault)
        if category == "thermal" or category in THERMAL_FAULTS:
            systems.add("thermal")
        elif category == "comms" or category in COMMS_FAULTS:
            systems.add("comms")
        elif category == "power" or category in POWER_FAULTS:
            systems.add("power")
        elif category == "sensor" or category in SENSOR_FAULTS:
            systems.add("sensor")
        elif category in ATTITUDE_FAULTS:
            systems.add("attitude")
        elif category in FDS_FAULTS:
            systems.add("fds")
        elif category in DATASET_POWER_FAULTS:
            systems.add("power")
    return systems


def unknown_fault_categories(faults: Iterable[FaultSpec]) -> List[str]:
    unknown: List[str] = []
    for fault in faults:
        category = _category(fault)
        if category not in KNOWN_FAULTS and category not in unknown:
            unknown.append(category)
    return unknown


def apply_faults(state: SpacecraftState, faults: List[FaultSpec], sim_t: float) -> None:
    for fault in active_fault_specs(faults, sim_t):
        category = _category(fault)
        severity = _severity(fault)

        _register_fault_spec(state, fault, category, severity)
    state._refresh_fault_labels()


def resolve_fault_context(state: SpacecraftState, sim_t: float) -> Dict[str, Any]:
    context = state.local_fault_context()
    context["sim_t"] = sim_t
    return context


def _register_fault_spec(state: SpacecraftState, fault: FaultSpec, category: str, severity: float) -> None:
    params = fault.parameters
    source = fault.source or "scenario"
    if category == "thermal":
        _ensure_root(
            state,
            "radiator_degraded",
            "thermal",
            severity,
            {"radiator_efficiency_multiplier": _radiator_multiplier(params, severity)},
            source,
            suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
        )
        if bool(params.get("thermal_controller_stuck", severity >= 0.55)):
            _ensure_recoverable(
                state,
                "thermal_controller_stuck",
                "thermal",
                severity,
                {},
                source,
                clearable_by=["RESET_THERMAL_CONTROLLER"],
            )
            state.thermal_controller_stable = False
        if params.get("heater_stuck_on"):
            _ensure_recoverable(
                state,
                "heater_stuck_on",
                "thermal",
                severity,
                {"load_w_add": 0.4 + 1.8 * severity},
                source,
                clearable_by=["RESET_THERMAL_CONTROLLER"],
            )
    elif category == "radiator_efficiency_drop":
        _ensure_root(
            state,
            "radiator_degraded",
            "thermal",
            severity,
            {"radiator_efficiency_multiplier": _radiator_multiplier(params, severity)},
            source,
            suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
        )
    elif category in {"thermal_controller_stuck", "heater_stuck_on"}:
        _ensure_recoverable(
            state,
            category,
            "thermal",
            severity,
            {"load_w_add": 0.4 + 1.8 * severity} if category == "heater_stuck_on" else {},
            source,
            clearable_by=["RESET_THERMAL_CONTROLLER"],
        )
        state.thermal_controller_stable = False
    elif category == "comms":
        _ensure_root(
            state,
            "antenna_misalignment",
            "comms",
            severity,
            {"antenna_alignment_error_deg": float(params.get("antenna_alignment_error_deg", 8.0 + 52.0 * severity))},
            source,
            suppressible_by=["LOWER_SAMPLING_RATE"],
        )
        if bool(params.get("transceiver_degradation", True)):
            _ensure_recoverable(
                state,
                "transceiver_softlock",
                "comms",
                severity,
                {},
                source,
                clearable_by=["RESTART_COMMS"],
                suppressible_by=["LOWER_SAMPLING_RATE"],
            )
            state.transceiver_softlock = True
    elif category == "antenna_misalignment":
        _ensure_root(
            state,
            "antenna_misalignment",
            "comms",
            severity,
            {"antenna_alignment_error_deg": float(params.get("error_deg", 8.0 + 52.0 * severity))},
            source,
            suppressible_by=["LOWER_SAMPLING_RATE"],
        )
    elif category in {"transceiver_degradation", "burst_packet_loss"}:
        _ensure_recoverable(
            state,
            "transceiver_softlock" if category == "transceiver_degradation" else "comms_stack_stall",
            "comms",
            severity,
            {"packet_loss_floor": 0.25 + 0.65 * severity} if category == "burst_packet_loss" else {},
            source,
            clearable_by=["RESTART_COMMS"],
            suppressible_by=["LOWER_SAMPLING_RATE"],
        )
    elif category == "power":
        _ensure_root(
            state,
            "battery_aged",
            "power",
            severity,
            {"battery_health_factor": float(params.get("battery_age_factor", max(0.1, 1.0 - 0.6 * severity)))},
            source,
            suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
        )
        _ensure_recoverable(
            state,
            "compute_overload_transient",
            "computer",
            severity,
            {"load_w_add": float(params.get("load_spike", 1.0 + 4.0 * severity))},
            source,
            clearable_by=["CLEAR_CACHE", "REBOOT_COMPUTER"],
            suppressible_by=["ENTER_SAFE_MODE"],
        )
    elif category == "battery_aging_penalty":
        _ensure_root(
            state,
            "battery_aged",
            "power",
            severity,
            {"battery_health_factor": max(0.1, 1.0 - 0.6 * severity)},
            source,
            suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
        )
    elif category == "solar_panel_efficiency_loss":
        _ensure_root(
            state,
            "solar_panel_efficiency_drop",
            "power",
            severity,
            {"sun_exposure_multiplier": max(0.05, 1.0 - 0.85 * severity)},
            source,
            suppressible_by=["ENTER_SAFE_MODE"],
        )
    elif category == "load_spike":
        _ensure_recoverable(
            state,
            "load_spike_transient",
            "power",
            severity,
            {"load_w_add": float(params.get("load_spike", 1.0 + 4.0 * severity))},
            source,
            clearable_by=["ENTER_SAFE_MODE", "REBOOT_COMPUTER"],
            suppressible_by=["ENTER_SAFE_MODE"],
        )
    elif category in {"computer", "memory_leak", "scheduler_overload", "reboot_instability"}:
        fault_id = "memory_leak_runtime" if category == "memory_leak" else "compute_overload_transient"
        _ensure_recoverable(
            state,
            fault_id,
            "computer",
            severity,
            {"memory_growth_mb": 2.5 + 18.0 * severity} if category == "memory_leak" else {"cpu_load_floor": 0.45 + 0.5 * severity},
            source,
            clearable_by=["CLEAR_CACHE", "REBOOT_COMPUTER"],
            suppressible_by=["ENTER_SAFE_MODE"],
        )
    elif category == "sensor":
        _ensure_root(
            state,
            "primary_sensor_hardware_failed",
            "sensor",
            severity,
            {"primary_sensor_health": 0.0},
            source,
            suppressible_by=["SWITCH_TO_BACKUP_SENSOR"],
        )
        _ensure_recoverable(
            state,
            "sensor_readout_fault",
            "sensor",
            severity,
            {"sensor_readout_bias": float(params.get("drift", 0.1 + 0.25 * severity))},
            source,
            clearable_by=["CLEAR_CACHE"],
            suppressible_by=["SWITCH_TO_BACKUP_SENSOR"],
        )
    elif category in SENSOR_FAULTS:
        _ensure_recoverable(
            state,
            "sensor_readout_fault",
            "sensor",
            severity,
            {"sensor_readout_bias": float(params.get("drift", 0.1 + 0.25 * severity))},
            source,
            clearable_by=["CLEAR_CACHE"],
            suppressible_by=["SWITCH_TO_BACKUP_SENSOR"],
        )
    elif category in {"attitude", "attitude_thruster_degradation", "primary_attitude_thruster_degradation", "pointing_control_efficiency_loss"}:
        _ensure_root(
            state,
            "primary_attitude_thruster_degradation",
            "attitude",
            severity,
            {
                "attitude_error_deg": float(params.get("attitude_error_deg", 0.7 + 3.2 * severity)),
                "pointing_control_efficiency": float(params.get("pointing_control_efficiency", max(0.1, 1.0 - 0.72 * severity))),
            },
            source,
            suppressible_by=["SWITCH_TO_BACKUP_THRUSTER", "ENABLE_THRUSTER_HEATERS"],
        )
        if bool(params.get("heater_power_control_fault", severity >= 0.45)):
            _ensure_recoverable(
                state,
                "thruster_heater_power_switch_error",
                "attitude",
                severity,
                {"attitude_error_deg": 0.5 + 1.8 * severity},
                source,
                clearable_by=["RESTORE_HEATER_POWER", "ENABLE_THRUSTER_HEATERS"],
            )
        state.primary_thruster_ok = False
    elif category in {"roll_thruster_fuel_line_residue_buildup", "roll_thruster_clogging_risk"}:
        _ensure_root(
            state,
            "roll_thruster_fuel_line_residue_buildup",
            "attitude",
            severity,
            {"attitude_error_deg": float(params.get("attitude_error_deg", 0.5 + 2.4 * severity))},
            source,
            suppressible_by=["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"],
        )
    elif category in {"dormant_roll_thrusters_unavailable", "heater_power_control_switch_state_error"}:
        _ensure_recoverable(
            state,
            "thruster_heater_power_switch_error",
            "attitude",
            severity,
            {"attitude_error_deg": 0.4 + 1.6 * severity},
            source,
            clearable_by=["RESTORE_HEATER_POWER", "ENABLE_THRUSTER_HEATERS"],
        )
    elif category == "primary_roll_thruster_heater_power_cost":
        _ensure_root(
            state,
            "primary_roll_thruster_heater_power_cost",
            "payload",
            severity,
            {"load_w_add": 0.25 + 0.9 * severity},
            source,
            suppressible_by=["SHUT_DOWN_PRIMARY_ROLL_HEATER", "SHED_NONESSENTIAL_LOAD"],
        )
    elif category in {"power_margin", "power_margin_reduction", "rtg_power_decline", "long_term_power_generation_loss"}:
        _ensure_root(
            state,
            "rtg_power_decline",
            "power",
            severity,
            {"battery_health_factor": float(params.get("battery_health_factor", max(0.1, 1.0 - 0.5 * severity)))},
            source,
            suppressible_by=["SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "ENTER_SAFE_MODE"],
        )
        _ensure_root(
            state,
            "instrument_heater_power_burden",
            "payload",
            max(0.3, severity * 0.7),
            {"load_w_add": float(params.get("load_w_add", 0.35 + 1.2 * severity))},
            source,
            suppressible_by=["SHED_NONESSENTIAL_LOAD", "DISABLE_INSTRUMENT", "REALLOCATE_POWER_BUDGET"],
        )
    elif category in {"thermal_support_load_too_high", "instrument_heater_shutdown_decision"}:
        _ensure_root(
            state,
            "thermal_support_load_too_high",
            "payload",
            severity,
            {"load_w_add": float(params.get("load_w_add", 0.35 + 1.4 * severity))},
            source,
            suppressible_by=["SHED_NONESSENTIAL_LOAD", "DISABLE_INSTRUMENT", "SHUT_DOWN_PRIMARY_ROLL_HEATER"],
        )
    elif category in FDS_FAULTS:
        _ensure_root(
            state,
            "fds_memory_chip_failure" if category in {"fds", "fds_memory_chip_failure", "fds_code_segment_loss"} else "telemetry_path_fault_unresolved",
            "fds",
            severity,
            {
                "memory_growth_mb": 2.0 + 8.0 * severity,
                "packet_loss_floor": 0.06 + 0.24 * severity,
            },
            source,
            suppressible_by=["RELOCATE_FDS_CODE", "ISOLATE_TELEMETRY_PATH", "VERIFY_TELEMETRY_RECOVERY"],
        )
        if category in {"fds", "fds_code_segment_loss", "engineering_data_unreadable", "science_data_unreadable", "aacs_state_mismatch", "aacs_or_packaging_chain_anomaly"}:
            _ensure_recoverable(
                state,
                "fds_code_segment_loss",
                "fds",
                severity,
                {"engineering_data_readable": False, "science_data_readable": False},
                source,
                clearable_by=["RELOCATE_FDS_CODE"],
                suppressible_by=["ISOLATE_TELEMETRY_PATH"],
            )


def _ensure_root(
    state: SpacecraftState,
    fault_id: str,
    system: str,
    severity: float,
    parameters: Dict[str, Any],
    source: str,
    *,
    suppressible_by: List[str] | None = None,
) -> None:
    if fault_id in state.root_cause_faults:
        return
    state.root_cause_faults[fault_id] = state._fault_record(
        fault_id,
        system,
        "root_cause",
        severity,
        parameters=parameters,
        suppressible_by=suppressible_by or [],
        source=source,
    )


def _ensure_recoverable(
    state: SpacecraftState,
    fault_id: str,
    system: str,
    severity: float,
    parameters: Dict[str, Any],
    source: str,
    *,
    clearable_by: List[str] | None = None,
    suppressible_by: List[str] | None = None,
) -> None:
    if fault_id in state.recoverable_faults:
        return
    state.recoverable_faults[fault_id] = state._fault_record(
        fault_id,
        system,
        "recoverable",
        severity,
        parameters=parameters,
        clearable_by=clearable_by or [],
        suppressible_by=suppressible_by or [],
        source=source,
    )


def _radiator_multiplier(params: Dict[str, Any], severity: float) -> float:
    if "radiator_efficiency_drop" in params:
        return max(0.05, float(params["radiator_efficiency_drop"]))
    return max(0.18, 1.0 - 0.9 * severity)


def _category(fault: FaultSpec) -> str:
    return fault.category.lower().strip()


def _severity(fault: FaultSpec) -> float:
    return max(0.0, min(1.0, fault.severity))
