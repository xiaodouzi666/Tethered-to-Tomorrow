from __future__ import annotations

import copy
import random
from typing import Any, Dict, Iterable, List, Optional

from pi_probe.twin.schemas import EnvironmentConfig, FaultSpec


DIFFICULTY_BANDS = {
    "easy": (0.25, 0.45),
    "medium": (0.45, 0.7),
    "hard": (0.7, 0.9),
    "extreme": (0.85, 1.0),
}

PROFILE_FAULTS = {
    "thermal": ["radiator_efficiency_drop", "thermal_controller_stuck", "heater_stuck_on"],
    "comms": ["antenna_misalignment", "transceiver_degradation", "burst_packet_loss"],
    "power": ["battery_aging_penalty", "load_spike", "solar_panel_efficiency_loss"],
    "computer": ["memory_leak", "scheduler_overload", "reboot_instability"],
    "sensor": ["sensor_drift", "stuck_value", "intermittent_dropout"],
    "attitude": ["primary_attitude_thruster_degradation", "roll_thruster_fuel_line_residue_buildup", "heater_power_control_switch_state_error"],
    "fds": ["fds_memory_chip_failure", "fds_code_segment_loss", "telemetry_path_fault_unresolved"],
    "power_margin": ["rtg_power_decline", "thermal_support_load_too_high", "instrument_heater_shutdown_decision"],
}


def randomize_environment(base: EnvironmentConfig) -> EnvironmentConfig:
    """Generate scenario-level environment augmentation around a base config."""

    return EnvironmentConfig(
        sun_exposure=_jitter(base.sun_exposure, 0.18, 0.35, 1.35),
        eclipse_factor=_jitter(base.eclipse_factor, 0.2, 0.0, 0.85),
        radiation_level=_jitter(base.radiation_level, 0.18, 0.0, 0.9),
        antenna_alignment_error_deg=_jitter(base.antenna_alignment_error_deg, 5.0, 0.0, 35.0),
        battery_age_factor=_jitter(base.battery_age_factor, 0.08, 0.62, 1.05),
        thermal_sink_efficiency=_jitter(base.thermal_sink_efficiency, 0.14, 0.55, 1.1),
        mission_phase=base.mission_phase,
    )


def compose_augmented_faults(profile: str, difficulty: str) -> List[FaultSpec]:
    """Create single/double, delayed, environment-triggered, and temporal fault variants."""

    normalized_profile = _profile(profile)
    lo, hi = DIFFICULTY_BANDS.get(difficulty.lower().strip(), DIFFICULTY_BANDS["medium"])
    count = _fault_count(difficulty)
    categories = _select_categories(normalized_profile, count)
    faults: List[FaultSpec] = []

    for index, category in enumerate(categories):
        severity = round(random.uniform(lo, hi), 2)
        start_t = round(_start_time(index, difficulty), 1)
        duration = round(_duration(difficulty), 1)
        parameter_profile = random.choice(["gradual", "burst", "environment_triggered", "delayed"])
        if parameter_profile == "delayed":
            start_t = max(start_t, round(random.uniform(20.0, 120.0), 1))
        faults.append(FaultSpec(
            id=f"aug-{category}-{index + 1}",
            category=category,
            severity=severity,
            start_t=start_t,
            duration=duration,
            parameters=_parameters_for_fault(category, severity, parameter_profile),
        ))

    return faults


def augment_telemetry_snapshot(
    snapshot: Dict[str, Any],
    noise: float = 0.02,
    drift: float = 0.0,
    missing_rate: float = 0.0,
    delay_events: bool = False,
    packet_jitter: float = 0.0,
) -> Dict[str, Any]:
    """Apply telemetry augmentation for rehearsal/evaluation datasets.

    This helper works on a snapshot copy. It never mutates real Probe state.
    """

    augmented = copy.deepcopy(snapshot)
    subsystems = augmented.get("subsystems", {})

    _jitter_metric(subsystems.get("thermal", {}), "temp_c", noise * 8.0, drift)
    _jitter_metric(subsystems.get("power", {}), "battery_voltage", noise * 0.6, -abs(drift) * 0.02)
    _jitter_metric(subsystems.get("comms", {}), "signal_strength", noise * 0.12, -abs(drift) * 0.01, 0.0, 1.0)
    _jitter_metric(subsystems.get("comms", {}), "packet_loss", noise * 0.12 + packet_jitter, abs(drift) * 0.01, 0.0, 1.0)
    _jitter_metric(subsystems.get("computer", {}), "cpu_load", noise * 0.12, abs(drift) * 0.01, 0.0, 1.0)
    _apply_missing_values(subsystems, missing_rate)

    if delay_events and augmented.get("events"):
        delayed = []
        for event in augmented["events"]:
            event_copy = dict(event)
            if isinstance(event_copy.get("ts"), (int, float)):
                event_copy["ts"] = event_copy["ts"] - random.uniform(2.0, 18.0)
                event_copy["delayed"] = True
            delayed.append(event_copy)
        augmented["events"] = delayed

    augmented["augmentation"] = {
        "telemetry_noise": noise,
        "drift": drift,
        "missing_rate": missing_rate,
        "delay_events": delay_events,
        "packet_jitter": packet_jitter,
    }
    return augmented


def build_augmented_scenario(
    profile: str,
    difficulty: str = "medium",
    base_environment: Optional[EnvironmentConfig] = None,
) -> Dict[str, Any]:
    base = base_environment or EnvironmentConfig()
    environment = randomize_environment(base)
    faults = compose_augmented_faults(profile, difficulty)
    return {
        "profile": _profile(profile),
        "difficulty": difficulty,
        "environment": _dump_model(environment),
        "faults": [_dump_model(fault) for fault in faults],
        "augmentation": {
            "environment": [
                "sun_exposure",
                "eclipse_factor",
                "radiation_level",
                "battery_age_factor",
                "thermal_sink_efficiency",
            ],
            "fault_composition": "single/double/environment-triggered/delayed",
            "temporal": "start_t/duration/gradual_or_burst",
            "telemetry": "noise/drift/missing_values/delayed_events/packet_jitter",
        },
    }


def _select_categories(profile: str, count: int) -> List[str]:
    primary = random.choice(PROFILE_FAULTS.get(profile, PROFILE_FAULTS["thermal"]))
    if count == 1:
        return [primary]
    secondary_profiles = [item for item in PROFILE_FAULTS if item != profile]
    secondary_profile = random.choice(secondary_profiles)
    secondary = random.choice(PROFILE_FAULTS[secondary_profile])
    return [primary, secondary]


def _parameters_for_fault(category: str, severity: float, temporal_profile: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "augmentation_profile": temporal_profile,
        "progression": "burst" if temporal_profile == "burst" else "gradual",
    }
    if category == "radiator_efficiency_drop":
        params["min_efficiency"] = round(max(0.12, 1.0 - 0.9 * severity), 2)
    elif category == "thermal_controller_stuck":
        params["thermal_controller_stuck"] = True
    elif category == "heater_stuck_on":
        params["heater_stuck_on"] = round(severity, 2)
    elif category == "antenna_misalignment":
        params["error_deg"] = round(8 + 45 * severity, 1)
    elif category == "transceiver_degradation":
        params["transceiver_degradation"] = True
    elif category == "burst_packet_loss":
        params["intermittent_dropout"] = round(0.25 + 0.65 * severity, 2)
        params["period"] = 6.0 if temporal_profile == "burst" else 14.0
        params["duty"] = round(0.25 + 0.45 * severity, 2)
    elif category == "battery_aging_penalty":
        params["battery_age_factor"] = round(max(0.55, 1.0 - 0.45 * severity), 2)
    elif category == "load_spike":
        params["load_spike"] = round(3.2 + 4.8 * severity, 2)
    elif category == "solar_panel_efficiency_loss":
        params["solar_panel_efficiency_loss"] = round(0.2 + 0.65 * severity, 2)
    elif category == "memory_leak":
        params["memory_leak"] = round(4.0 + 18.0 * severity, 2)
    elif category == "scheduler_overload":
        params["scheduler_overload"] = round(min(0.98, 0.42 + 0.52 * severity), 2)
    elif category == "reboot_instability":
        params["reboot_instability"] = True
    elif category == "sensor_drift":
        params["drift"] = round(0.04 + 0.3 * severity, 3)
    elif category == "stuck_value":
        params["stuck_value"] = {"temp_c": round(42 + 42 * severity, 1)}
    elif category == "intermittent_dropout":
        params["intermittent_dropout"] = round(0.25 + 0.55 * severity, 2)
        params["period"] = 8.0
        params["duty"] = round(0.2 + 0.5 * severity, 2)
    elif category in {"primary_attitude_thruster_degradation", "roll_thruster_fuel_line_residue_buildup"}:
        params["attitude_error_deg"] = round(0.6 + 3.0 * severity, 2)
        params["pointing_control_efficiency"] = round(max(0.1, 1.0 - 0.75 * severity), 2)
    elif category == "heater_power_control_switch_state_error":
        params["heater_power_control_fault"] = True
    elif category in {"rtg_power_decline", "thermal_support_load_too_high", "instrument_heater_shutdown_decision"}:
        params["battery_health_factor"] = round(max(0.55, 1.0 - 0.45 * severity), 2)
        params["load_w_add"] = round(0.3 + 1.4 * severity, 2)
    elif category in {"fds_memory_chip_failure", "fds_code_segment_loss", "telemetry_path_fault_unresolved"}:
        params["memory_growth_mb"] = round(2.0 + 10.0 * severity, 2)
        params["packet_loss_floor"] = round(0.06 + 0.25 * severity, 2)
    if temporal_profile == "environment_triggered":
        params["trigger"] = random.choice(["eclipse_entry", "radiation_spike", "low_sun_exposure"])
    return params


def _fault_count(difficulty: str) -> int:
    if difficulty.lower().strip() in {"hard", "extreme"}:
        return random.choice([1, 2, 2])
    return random.choice([1, 1, 2])


def _start_time(index: int, difficulty: str) -> float:
    if index == 0:
        return 0.0 if difficulty.lower().strip() != "easy" else random.uniform(0.0, 20.0)
    return random.uniform(20.0, 180.0)


def _duration(difficulty: str) -> float:
    if difficulty.lower().strip() == "easy":
        return random.uniform(120.0, 300.0)
    if difficulty.lower().strip() == "extreme":
        return random.uniform(300.0, 900.0)
    return random.uniform(180.0, 600.0)


def _profile(profile: str) -> str:
    normalized = profile.lower().strip()
    return normalized if normalized in PROFILE_FAULTS else "thermal"


def _jitter(value: float, delta: float, min_value: float, max_value: float) -> float:
    return round(max(min_value, min(max_value, value + random.uniform(-delta, delta))), 4)


def _jitter_metric(
    container: Dict[str, Any],
    key: str,
    noise_range: float,
    drift: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> None:
    value = container.get(key)
    if not isinstance(value, (int, float)):
        return
    next_value = float(value) + random.uniform(-noise_range, noise_range) + drift
    if min_value is not None:
        next_value = max(min_value, next_value)
    if max_value is not None:
        next_value = min(max_value, next_value)
    container[key] = round(next_value, 3)


def _apply_missing_values(subsystems: Dict[str, Any], missing_rate: float) -> None:
    if missing_rate <= 0:
        return
    keys: Iterable[tuple[str, str]] = [
        ("thermal", "temp_c"),
        ("power", "battery_voltage"),
        ("comms", "packet_loss"),
        ("comms", "signal_strength"),
        ("computer", "cpu_load"),
    ]
    for subsystem, key in keys:
        if random.random() < missing_rate and isinstance(subsystems.get(subsystem), dict):
            subsystems[subsystem][key] = None


def _dump_model(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
