from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

ALLOWED_COMMANDS = {
    "ENTER_SAFE_MODE",
    "EXIT_SAFE_MODE",
    "DISABLE_PAYLOAD",
    "ENABLE_PAYLOAD",
    "RESTART_COMMS",
    "SWITCH_TO_BACKUP_SENSOR",
    "SWITCH_TO_BACKUP_THRUSTER",
    "ENABLE_THRUSTER_HEATERS",
    "SHUT_DOWN_PRIMARY_ROLL_HEATER",
    "RESTORE_HEATER_POWER",
    "RESET_THERMAL_CONTROLLER",
    "LOWER_SAMPLING_RATE",
    "SHED_NONESSENTIAL_LOAD",
    "DISABLE_INSTRUMENT",
    "RESTORE_INSTRUMENT",
    "CLEAR_CACHE",
    "REBOOT_COMPUTER",
    "RELOCATE_FDS_CODE",
    "VERIFY_TELEMETRY_RECOVERY",
    "ISOLATE_TELEMETRY_PATH",
    "REALLOCATE_POWER_BUDGET",
}

HIGH_RISK_COMMANDS = {
    "EXIT_SAFE_MODE",
    "RESTART_COMMS",
    "REBOOT_COMPUTER",
    "SWITCH_TO_BACKUP_THRUSTER",
    "ENABLE_THRUSTER_HEATERS",
    "RESTORE_HEATER_POWER",
    "RELOCATE_FDS_CODE",
}
SUPPORTED_FAULTS = {"thermal", "comms", "power", "sensor", "attitude", "fds", "telemetry", "power_margin"}

DEFAULT_SCIENCE_INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "imaging": {"enabled": True, "heater_enabled": True, "essential": False, "priority": 5, "power_w": 0.42, "heat_w": 0.16},
    "plasma_wave": {"enabled": True, "heater_enabled": True, "essential": False, "priority": 4, "power_w": 0.35, "heat_w": 0.12},
    "infrared_spectrometer": {"enabled": True, "heater_enabled": True, "essential": False, "priority": 3, "power_w": 0.32, "heat_w": 0.1},
    "cosmic_ray": {"enabled": True, "heater_enabled": False, "essential": False, "priority": 2, "power_w": 0.22, "heat_w": 0.05},
    "magnetometer": {"enabled": True, "heater_enabled": False, "essential": True, "priority": 1, "power_w": 0.18, "heat_w": 0.03},
}


@dataclass
class SpacecraftState:
    probe_id: str = "deeprepair-probe-01"
    mode: str = "NORMAL"  # NORMAL | WARNING | FAULT | SAFE_MODE
    primary_fault: str = "none"
    active_faults: List[str] = field(default_factory=list)
    latent_faults: List[str] = field(default_factory=list)
    root_cause_faults: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recoverable_faults: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_mitigations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    seq: int = 0
    started_ts: float = field(default_factory=time.time)
    sim_elapsed_s: float = 0.0
    change_version: int = 0

    sun_exposure: float = 1.0
    eclipse_factor: float = 0.0
    radiation_level: float = 0.0
    antenna_alignment_error_deg: float = 0.0
    battery_age_factor: float = 1.0
    thermal_sink_efficiency: float = 1.0
    mission_phase: str = "cruise"
    radiator_physical_efficiency: float = 1.0
    battery_health_factor: float = 1.0
    primary_sensor_health: float = 1.0
    thermal_controller_stable: bool = True
    transceiver_softlock: bool = False
    memory_leak_rate: float = 0.0
    cache_pressure: float = 0.0
    sensor_readout_bias: float = 0.0
    primary_thruster_ok: bool = True
    backup_thruster_enabled: bool = False
    tcm_thruster_branch_enabled: bool = False
    roll_thruster_heaters_enabled: bool = False
    primary_roll_heater_enabled: bool = True
    attitude_error_deg: float = 0.05
    pointing_control_efficiency: float = 1.0
    telemetry_path_ok: bool = True
    fds_code_relocated: bool = False
    engineering_data_readable: bool = True
    science_data_readable: bool = True
    science_instruments: Dict[str, Dict[str, Any]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SCIENCE_INSTRUMENTS))

    battery_voltage: float = 12.4
    load_w: float = 3.2
    solar_input_w: float = 2.6

    temp_c: float = 42.0
    thermal_controller_ok: bool = True
    radiator_efficiency: float = 1.0

    signal_strength: float = 0.86
    packet_loss: float = 0.04
    comms_restart_remaining_s: float = 0.0

    cpu_load: float = 0.28
    mem_used_mb: float = 420.0
    storage_health: str = "nominal"

    payload_enabled: bool = True
    sampling_rate: float = 1.0
    using_backup_sensor: bool = False

    last_command: Optional[Dict[str, Any]] = None
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    @property
    def active_fault(self) -> str:
        return self.primary_fault or "none"

    @active_fault.setter
    def active_fault(self, fault: str) -> None:
        normalized = self._normalize_fault(fault)
        if normalized in {"none", "clear"}:
            self._clear_faults()
            return
        self._activate_fault(normalized)

    @staticmethod
    def _normalize_fault(fault: str) -> str:
        return str(fault or "none").lower().strip() or "none"

    def _has_fault(self, fault: str) -> bool:
        return self._normalize_fault(fault) in self.active_faults

    def _activate_fault(self, fault: str) -> None:
        normalized = self._normalize_fault(fault)
        if normalized not in SUPPORTED_FAULTS:
            raise ValueError(f"Unsupported fault '{fault}'")
        if normalized not in self.active_faults:
            self.active_faults.append(normalized)
        self.primary_fault = self.primary_fault if self.primary_fault != "none" else normalized

    def _remove_fault(self, fault: str) -> None:
        normalized = self._normalize_fault(fault)
        self.active_faults = [item for item in self.active_faults if item != normalized]
        if self.primary_fault == normalized:
            self.primary_fault = self.active_faults[0] if self.active_faults else "none"

    def _clear_faults(self) -> None:
        self.primary_fault = "none"
        self.active_faults = []
        self.latent_faults = []

    def clone(self) -> "SpacecraftState":
        return copy.deepcopy(self)

    def clone_for_baseline(self) -> "SpacecraftState":
        return copy.deepcopy(self)

    def state_digest(self) -> str:
        payload = json.dumps(self.to_internal_state(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def internal_state(self) -> Dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "mode": self.mode,
            "primary_fault": self.primary_fault,
            "active_fault": self.active_fault,
            "active_faults": list(self.active_faults),
            "latent_faults": list(self.latent_faults),
            "root_cause_faults": copy.deepcopy(self.root_cause_faults),
            "recoverable_faults": copy.deepcopy(self.recoverable_faults),
            "active_mitigations": copy.deepcopy(self.active_mitigations),
            "seq": self.seq,
            "started_ts": self.started_ts,
            "sim_elapsed_s": self.sim_elapsed_s,
            "change_version": self.change_version,
            "sun_exposure": self.sun_exposure,
            "eclipse_factor": self.eclipse_factor,
            "radiation_level": self.radiation_level,
            "antenna_alignment_error_deg": self.antenna_alignment_error_deg,
            "battery_age_factor": self.battery_age_factor,
            "thermal_sink_efficiency": self.thermal_sink_efficiency,
            "mission_phase": self.mission_phase,
            "radiator_physical_efficiency": self.radiator_physical_efficiency,
            "battery_health_factor": self.battery_health_factor,
            "primary_sensor_health": self.primary_sensor_health,
            "thermal_controller_stable": self.thermal_controller_stable,
            "transceiver_softlock": self.transceiver_softlock,
            "memory_leak_rate": self.memory_leak_rate,
            "cache_pressure": self.cache_pressure,
            "sensor_readout_bias": self.sensor_readout_bias,
            "primary_thruster_ok": self.primary_thruster_ok,
            "backup_thruster_enabled": self.backup_thruster_enabled,
            "tcm_thruster_branch_enabled": self.tcm_thruster_branch_enabled,
            "roll_thruster_heaters_enabled": self.roll_thruster_heaters_enabled,
            "primary_roll_heater_enabled": self.primary_roll_heater_enabled,
            "attitude_error_deg": self.attitude_error_deg,
            "pointing_control_efficiency": self.pointing_control_efficiency,
            "telemetry_path_ok": self.telemetry_path_ok,
            "fds_code_relocated": self.fds_code_relocated,
            "engineering_data_readable": self.engineering_data_readable,
            "science_data_readable": self.science_data_readable,
            "science_instruments": copy.deepcopy(self.science_instruments),
            "battery_voltage": self.battery_voltage,
            "load_w": self.load_w,
            "solar_input_w": self.solar_input_w,
            "temp_c": self.temp_c,
            "thermal_controller_ok": self.thermal_controller_ok,
            "radiator_efficiency": self.radiator_efficiency,
            "signal_strength": self.signal_strength,
            "packet_loss": self.packet_loss,
            "comms_restart_remaining_s": self.comms_restart_remaining_s,
            "cpu_load": self.cpu_load,
            "mem_used_mb": self.mem_used_mb,
            "storage_health": self.storage_health,
            "payload_enabled": self.payload_enabled,
            "sampling_rate": self.sampling_rate,
            "using_backup_sensor": self.using_backup_sensor,
            "last_command": copy.deepcopy(self.last_command),
            "events": copy.deepcopy(list(self.events)),
        }

    def to_internal_state(self) -> Dict[str, Any]:
        return self.internal_state()

    @classmethod
    def from_internal_state(cls, data: Dict[str, Any]) -> "SpacecraftState":
        state = cls()
        scalar_fields = [
            "probe_id",
            "mode",
            "seq",
            "started_ts",
            "sim_elapsed_s",
            "change_version",
            "sun_exposure",
            "eclipse_factor",
            "radiation_level",
            "antenna_alignment_error_deg",
            "battery_age_factor",
            "thermal_sink_efficiency",
            "mission_phase",
            "radiator_physical_efficiency",
            "battery_health_factor",
            "primary_sensor_health",
            "thermal_controller_stable",
            "transceiver_softlock",
            "memory_leak_rate",
            "cache_pressure",
            "sensor_readout_bias",
            "primary_thruster_ok",
            "backup_thruster_enabled",
            "tcm_thruster_branch_enabled",
            "roll_thruster_heaters_enabled",
            "primary_roll_heater_enabled",
            "attitude_error_deg",
            "pointing_control_efficiency",
            "telemetry_path_ok",
            "fds_code_relocated",
            "engineering_data_readable",
            "science_data_readable",
            "battery_voltage",
            "load_w",
            "solar_input_w",
            "temp_c",
            "thermal_controller_ok",
            "radiator_efficiency",
            "signal_strength",
            "packet_loss",
            "comms_restart_remaining_s",
            "cpu_load",
            "mem_used_mb",
            "storage_health",
            "payload_enabled",
            "sampling_rate",
            "using_backup_sensor",
        ]
        for key in scalar_fields:
            if key in data:
                setattr(state, key, data[key])
        if "comms_restart_remaining_s" not in data and "comms_restarting_until" in data:
            remaining = float(data.get("comms_restarting_until") or 0.0) - state.now()
            state.comms_restart_remaining_s = max(0.0, remaining)

        active_faults = data.get("active_faults")
        if active_faults is None:
            fault = cls._normalize_fault(data.get("primary_fault", data.get("active_fault", "none")))
            active_faults = [] if fault == "none" else [fault]
        state.active_faults = [cls._normalize_fault(item) for item in active_faults if cls._normalize_fault(item) in SUPPORTED_FAULTS]
        state.primary_fault = cls._normalize_fault(data.get("primary_fault", state.active_faults[0] if state.active_faults else "none"))
        if state.primary_fault not in state.active_faults:
            state.primary_fault = state.active_faults[0] if state.active_faults else "none"
        state.latent_faults = [
            cls._normalize_fault(item)
            for item in data.get("latent_faults", [])
            if cls._normalize_fault(item) in SUPPORTED_FAULTS
        ]
        state.root_cause_faults = copy.deepcopy(data.get("root_cause_faults", {}))
        state.recoverable_faults = copy.deepcopy(data.get("recoverable_faults", {}))
        state.active_mitigations = copy.deepcopy(data.get("active_mitigations", {}))
        if isinstance(data.get("science_instruments"), dict):
            state.science_instruments = copy.deepcopy(data["science_instruments"])
        if not state.root_cause_faults and not state.recoverable_faults:
            for fault in state.active_faults:
                state._inject_fault_bundle(fault)
        state._refresh_fault_labels()

        state.last_command = copy.deepcopy(data.get("last_command"))
        state.events = deque(copy.deepcopy(data.get("events", [])), maxlen=200)
        return state

    def now(self) -> float:
        return self.started_ts + self.sim_elapsed_s

    def _bump_change_version(self) -> None:
        self.change_version += 1

    def add_event(self, event_type: str, message: str, **extra: Any) -> None:
        self.events.appendleft({
            "ts": self.now(),
            "type": event_type,
            "message": message,
            **extra,
        })

    def _fault_record(
        self,
        fault_id: str,
        system: str,
        layer: str,
        severity: float,
        *,
        status: str = "active",
        parameters: Optional[Dict[str, Any]] = None,
        clearable_by: Optional[List[str]] = None,
        suppressible_by: Optional[List[str]] = None,
        source: str = "manual",
    ) -> Dict[str, Any]:
        return {
            "id": fault_id,
            "system": system,
            "layer": layer,
            "severity": max(0.0, min(1.0, float(severity))),
            "status": status,
            "parameters": parameters or {},
            "clearable_by": clearable_by or [],
            "suppressible_by": suppressible_by or [],
            "source": source,
        }

    def _inject_fault_bundle(self, fault: str, source: str = "manual") -> None:
        fault = self._normalize_fault(fault)
        if fault not in SUPPORTED_FAULTS:
            raise ValueError(f"Unsupported fault '{fault}'")
        self._activate_fault(fault)
        self.mode = "FAULT"

        if fault == "thermal":
            self.root_cause_faults["radiator_degraded"] = self._fault_record(
                "radiator_degraded",
                "thermal",
                "root_cause",
                0.72,
                parameters={"radiator_efficiency_multiplier": 0.35},
                suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
                source=source,
            )
            self.recoverable_faults["thermal_controller_stuck"] = self._fault_record(
                "thermal_controller_stuck",
                "thermal",
                "recoverable",
                0.7,
                clearable_by=["RESET_THERMAL_CONTROLLER"],
                source=source,
            )
            self.thermal_controller_stable = False
        elif fault == "comms":
            self.root_cause_faults["antenna_misalignment"] = self._fault_record(
                "antenna_misalignment",
                "comms",
                "root_cause",
                0.68,
                parameters={"antenna_alignment_error_deg": 18.0},
                suppressible_by=["LOWER_SAMPLING_RATE"],
                source=source,
            )
            self.recoverable_faults["transceiver_softlock"] = self._fault_record(
                "transceiver_softlock",
                "comms",
                "recoverable",
                0.65,
                clearable_by=["RESTART_COMMS"],
                suppressible_by=["LOWER_SAMPLING_RATE"],
                source=source,
            )
            self.antenna_alignment_error_deg = max(self.antenna_alignment_error_deg, 18.0)
            self.transceiver_softlock = True
        elif fault == "power":
            self.root_cause_faults["battery_aged"] = self._fault_record(
                "battery_aged",
                "power",
                "root_cause",
                0.72,
                parameters={"battery_health_factor": 0.72},
                suppressible_by=["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
                source=source,
            )
            self.root_cause_faults["rtg_power_decline"] = self._fault_record(
                "rtg_power_decline",
                "power",
                "root_cause",
                0.68,
                parameters={"battery_health_factor": 0.76},
                suppressible_by=["SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "ENTER_SAFE_MODE"],
                source=source,
            )
            self.root_cause_faults["instrument_heater_power_burden"] = self._fault_record(
                "instrument_heater_power_burden",
                "payload",
                "root_cause",
                0.55,
                parameters={"load_w_add": 0.65},
                suppressible_by=["SHED_NONESSENTIAL_LOAD", "DISABLE_INSTRUMENT", "REALLOCATE_POWER_BUDGET"],
                source=source,
            )
            self.recoverable_faults["compute_overload_transient"] = self._fault_record(
                "compute_overload_transient",
                "computer",
                "recoverable",
                0.64,
                clearable_by=["CLEAR_CACHE", "REBOOT_COMPUTER"],
                suppressible_by=["ENTER_SAFE_MODE"],
                source=source,
            )
            self.battery_health_factor = min(self.battery_health_factor, 0.72)
            self.cache_pressure = max(self.cache_pressure, 0.65)
        elif fault == "sensor":
            self.root_cause_faults["primary_sensor_hardware_failed"] = self._fault_record(
                "primary_sensor_hardware_failed",
                "sensor",
                "root_cause",
                0.7,
                parameters={"primary_sensor_health": 0.0},
                suppressible_by=["SWITCH_TO_BACKUP_SENSOR"],
                source=source,
            )
            self.recoverable_faults["sensor_readout_fault"] = self._fault_record(
                "sensor_readout_fault",
                "sensor",
                "recoverable",
                0.6,
                clearable_by=["CLEAR_CACHE"],
                suppressible_by=["SWITCH_TO_BACKUP_SENSOR"],
                source=source,
            )
            self.primary_sensor_health = min(self.primary_sensor_health, 0.0)
            self.sensor_readout_bias = max(self.sensor_readout_bias, 0.25)
        elif fault == "attitude":
            self.root_cause_faults["primary_attitude_thruster_degradation"] = self._fault_record(
                "primary_attitude_thruster_degradation",
                "attitude",
                "root_cause",
                0.72,
                parameters={"attitude_error_deg": 2.8, "pointing_control_efficiency": 0.48},
                suppressible_by=["SWITCH_TO_BACKUP_THRUSTER", "ENABLE_THRUSTER_HEATERS"],
                source=source,
            )
            self.root_cause_faults["roll_thruster_fuel_line_residue_buildup"] = self._fault_record(
                "roll_thruster_fuel_line_residue_buildup",
                "attitude",
                "root_cause",
                0.62,
                parameters={"attitude_error_deg": 1.7},
                suppressible_by=["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"],
                source=source,
            )
            self.recoverable_faults["thruster_heater_power_switch_error"] = self._fault_record(
                "thruster_heater_power_switch_error",
                "attitude",
                "recoverable",
                0.6,
                parameters={"thruster_heater_unavailable": True},
                clearable_by=["RESTORE_HEATER_POWER", "ENABLE_THRUSTER_HEATERS"],
                source=source,
            )
            self.primary_thruster_ok = False
            self.attitude_error_deg = max(self.attitude_error_deg, 2.8)
            self.pointing_control_efficiency = min(self.pointing_control_efficiency, 0.48)
        elif fault in {"fds", "telemetry"}:
            self.root_cause_faults["fds_memory_chip_failure"] = self._fault_record(
                "fds_memory_chip_failure",
                "fds",
                "root_cause",
                0.7,
                parameters={"memory_growth_mb": 8.0},
                suppressible_by=["RELOCATE_FDS_CODE", "ISOLATE_TELEMETRY_PATH"],
                source=source,
            )
            self.root_cause_faults["telemetry_path_fault_unresolved"] = self._fault_record(
                "telemetry_path_fault_unresolved",
                "fds" if fault == "fds" else "telemetry",
                "root_cause",
                0.62,
                parameters={"packet_loss_floor": 0.22},
                suppressible_by=["ISOLATE_TELEMETRY_PATH", "VERIFY_TELEMETRY_RECOVERY"],
                source=source,
            )
            self.recoverable_faults["fds_code_segment_loss"] = self._fault_record(
                "fds_code_segment_loss",
                "fds",
                "recoverable",
                0.68,
                parameters={"engineering_data_readable": False, "science_data_readable": False},
                clearable_by=["RELOCATE_FDS_CODE"],
                suppressible_by=["ISOLATE_TELEMETRY_PATH"],
                source=source,
            )
            self.telemetry_path_ok = False
            self.engineering_data_readable = False
            self.science_data_readable = False
            self.storage_health = "fds_code_segment_loss"
        elif fault == "power_margin":
            self.root_cause_faults["rtg_power_decline"] = self._fault_record(
                "rtg_power_decline",
                "power",
                "root_cause",
                0.74,
                parameters={"battery_health_factor": 0.72},
                suppressible_by=["SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET", "ENTER_SAFE_MODE"],
                source=source,
            )
            self.root_cause_faults["thermal_support_load_too_high"] = self._fault_record(
                "thermal_support_load_too_high",
                "payload",
                "root_cause",
                0.6,
                parameters={"load_w_add": 0.85},
                suppressible_by=["SHED_NONESSENTIAL_LOAD", "SHUT_DOWN_PRIMARY_ROLL_HEATER"],
                source=source,
            )
            self.battery_health_factor = min(self.battery_health_factor, 0.72)
        self._refresh_fault_labels()

    def _clear_all_fault_layers(self) -> None:
        self.root_cause_faults = {}
        self.recoverable_faults = {}
        self.active_mitigations = {}
        self.radiator_physical_efficiency = 1.0
        self.battery_health_factor = 1.0
        self.antenna_alignment_error_deg = 0.0
        self.primary_sensor_health = 1.0
        self.thermal_controller_stable = True
        self.transceiver_softlock = False
        self.memory_leak_rate = 0.0
        self.cache_pressure = 0.0
        self.sensor_readout_bias = 0.0
        self.primary_thruster_ok = True
        self.backup_thruster_enabled = False
        self.tcm_thruster_branch_enabled = False
        self.roll_thruster_heaters_enabled = False
        self.primary_roll_heater_enabled = True
        self.attitude_error_deg = 0.05
        self.pointing_control_efficiency = 1.0
        self.telemetry_path_ok = True
        self.fds_code_relocated = False
        self.engineering_data_readable = True
        self.science_data_readable = True
        self.science_instruments = copy.deepcopy(DEFAULT_SCIENCE_INSTRUMENTS)

    def _active_fault_records(self, registry: Dict[str, Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
        return [
            (fault_id, record)
            for fault_id, record in registry.items()
            if str(record.get("status", "active")) == "active"
        ]

    def _refresh_fault_labels(self) -> None:
        systems: List[str] = []
        for _, record in self._active_fault_records(self.recoverable_faults):
            system = str(record.get("system", ""))
            if system == "computer":
                system = "power"
            if system in SUPPORTED_FAULTS and system not in systems:
                systems.append(system)
        for _, record in self._active_fault_records(self.root_cause_faults):
            system = str(record.get("system", ""))
            if system == "computer":
                system = "power"
            # Root causes remain available in fault_layers, but the UI-facing
            # active fault label should only stay set when the root cause is
            # still creating a hard observable fault. This keeps "repaired but
            # degraded" states from looking like unresolved recoverable faults.
            if system in SUPPORTED_FAULTS and self.status_for_subsystem(system) == "FAULT" and system not in systems:
                systems.append(system)
        self.active_faults = systems
        self.primary_fault = systems[0] if systems else "none"

    def _clear_recoverable(self, fault_id: str, action: str) -> bool:
        record = self.recoverable_faults.get(fault_id)
        if not record or str(record.get("status", "active")) == "cleared":
            return False
        clearable_by = [str(item).upper() for item in record.get("clearable_by", [])]
        if clearable_by and action not in clearable_by:
            return False
        record["status"] = "cleared"
        record["cleared_by"] = action
        record["cleared_at"] = self.now()
        return True

    def _suppress_recoverable(self, fault_id: str, action: str) -> bool:
        record = self.recoverable_faults.get(fault_id)
        if not record or str(record.get("status", "active")) != "active":
            return False
        suppressible_by = [str(item).upper() for item in record.get("suppressible_by", [])]
        if suppressible_by and action not in suppressible_by:
            return False
        record["status"] = "suppressed"
        record["suppressed_by"] = action
        record["suppressed_at"] = self.now()
        return True

    def _set_mitigation(self, name: str, **values: Any) -> Dict[str, Any]:
        previous = copy.deepcopy(self.active_mitigations.get(name))
        next_value = {"active": True, **values}
        self.active_mitigations[name] = next_value
        return {"before": previous, "after": copy.deepcopy(next_value)}

    def _remaining_root_causes(self) -> List[str]:
        return [fault_id for fault_id, _ in self._active_fault_records(self.root_cause_faults)]

    def _metric_deltas(self, before: Dict[str, float], after: Dict[str, float]) -> Dict[str, float]:
        deltas: Dict[str, float] = {}
        for key, before_value in before.items():
            after_value = after.get(key)
            if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
                delta = round(float(after_value) - float(before_value), 4)
                if delta:
                    deltas[key] = delta
        return deltas

    def _disable_instrument(self, instrument: str) -> Optional[Dict[str, Any]]:
        name = str(instrument or "").lower().strip()
        record = self.science_instruments.get(name)
        if not record or not record.get("enabled", False):
            return None
        record["enabled"] = False
        record["disabled_at"] = self.now()
        power = float(record.get("power_w", 0.0))
        heat = float(record.get("heat_w", 0.0))
        self.load_w = max(0.8, self.load_w - power)
        self.temp_c = max(20.0, self.temp_c - heat * 0.35)
        return {"instrument": name, "power_w": power, "heat_w": heat}

    def _restore_instrument(self, instrument: str) -> Optional[Dict[str, Any]]:
        name = str(instrument or "").lower().strip()
        record = self.science_instruments.get(name)
        if not record or record.get("enabled", False):
            return None
        record["enabled"] = True
        record["restored_at"] = self.now()
        power = float(record.get("power_w", 0.0))
        self.load_w += power
        return {"instrument": name, "power_w": power}

    def _shed_nonessential_load(self) -> Optional[Dict[str, Any]]:
        candidates = [
            (str(name), item)
            for name, item in self.science_instruments.items()
            if item.get("enabled", False) and not item.get("essential", False)
        ]
        if not candidates:
            return None
        name, _ = max(candidates, key=lambda item: (int(item[1].get("priority", 0)), float(item[1].get("power_w", 0.0))))
        return self._disable_instrument(name)

    def fault_layer_summary(self) -> Dict[str, Any]:
        symptoms: List[Dict[str, Any]] = []
        if self.temp_c > 70:
            symptoms.append({
                "id": "temp_high",
                "system": "thermal",
                "status": "fault" if self.temp_c > 82 else "warning",
                "value": round(self.temp_c, 3),
                "threshold": 82.0 if self.temp_c > 82 else 70.0,
            })
        if self.battery_voltage < 11.0:
            symptoms.append({
                "id": "voltage_low",
                "system": "power",
                "status": "fault" if self.battery_voltage < 10.4 else "warning",
                "value": round(self.battery_voltage, 3),
                "threshold": 10.4 if self.battery_voltage < 10.4 else 11.0,
            })
        if self.packet_loss > 0.3:
            symptoms.append({
                "id": "packet_loss_high",
                "system": "comms",
                "status": "fault" if self.packet_loss > 0.68 else "warning",
                "value": round(self.packet_loss, 3),
                "threshold": 0.68 if self.packet_loss > 0.68 else 0.3,
            })
        if self.signal_strength < 0.25:
            symptoms.append({
                "id": "signal_weak",
                "system": "comms",
                "status": "fault" if self.signal_strength < 0.15 else "warning",
                "value": round(self.signal_strength, 3),
                "threshold": 0.15 if self.signal_strength < 0.15 else 0.25,
            })
        if self.cpu_load > 0.75:
            symptoms.append({
                "id": "cpu_high",
                "system": "computer",
                "status": "fault" if self.cpu_load > 0.9 else "warning",
                "value": round(self.cpu_load, 3),
                "threshold": 0.9 if self.cpu_load > 0.9 else 0.75,
            })
        if self.sensor_readout_bias and not self.using_backup_sensor:
            symptoms.append({
                "id": "sensor_readout_unreliable",
                "system": "sensor",
                "status": "warning",
                "value": round(self.sensor_readout_bias, 3),
                "threshold": 0.0,
            })
        if self.attitude_error_deg > 1.0:
            symptoms.append({
                "id": "pointing_control_efficiency_loss",
                "system": "attitude",
                "status": "fault" if self.attitude_error_deg > 3.0 else "warning",
                "value": round(self.attitude_error_deg, 3),
                "threshold": 3.0 if self.attitude_error_deg > 3.0 else 1.0,
            })
        if not self.engineering_data_readable or not self.science_data_readable:
            symptoms.append({
                "id": "telemetry_inconsistency",
                "system": "fds",
                "status": "fault",
                "value": 0.0,
                "threshold": 1.0,
            })
        return {
            "root_causes": [copy.deepcopy(record) for record in self.root_cause_faults.values()],
            "recoverable_faults": [copy.deepcopy(record) for record in self.recoverable_faults.values()],
            "active_mitigations": [
                {"id": name, **copy.deepcopy(value)}
                for name, value in self.active_mitigations.items()
                if bool(value.get("active", True))
            ],
            "symptoms": symptoms,
        }

    def local_fault_context(self) -> Dict[str, Any]:
        self._refresh_fault_labels()
        effective: Dict[str, Any] = {
            "radiator_efficiency_multiplier": 1.0,
            "thermal_controller_stuck": False,
            "antenna_alignment_error_deg": self.antenna_alignment_error_deg,
            "transceiver_softlock": False,
            "packet_loss_floor": 0.0,
            "battery_health_factor": self.battery_health_factor,
            "sun_exposure_multiplier": 1.0,
            "load_w_add": 0.0,
            "cpu_load_floor": 0.0,
            "memory_growth_mb": 0.0,
            "sensor_readout_bias": 0.0,
            "using_backup_sensor": self.using_backup_sensor,
            "attitude_error_deg": self.attitude_error_deg,
            "pointing_control_efficiency": self.pointing_control_efficiency,
            "telemetry_path_ok": self.telemetry_path_ok,
            "engineering_data_readable": self.engineering_data_readable,
            "science_data_readable": self.science_data_readable,
        }
        for fault_id, record in self._active_fault_records(self.root_cause_faults):
            params = record.get("parameters", {})
            severity = float(record.get("severity", 0.5))
            if fault_id == "radiator_degraded":
                effective["radiator_efficiency_multiplier"] = min(
                    effective["radiator_efficiency_multiplier"],
                    float(params.get("radiator_efficiency_multiplier", max(0.1, 1.0 - 0.8 * severity))),
                )
            elif fault_id == "antenna_misalignment":
                effective["antenna_alignment_error_deg"] = max(
                    float(effective["antenna_alignment_error_deg"]),
                    float(params.get("antenna_alignment_error_deg", 8.0 + 28.0 * severity)),
                )
            elif fault_id == "battery_aged":
                effective["battery_health_factor"] = min(
                    float(effective["battery_health_factor"]),
                    float(params.get("battery_health_factor", max(0.1, 1.0 - 0.5 * severity))),
                )
            elif fault_id == "solar_panel_efficiency_drop":
                effective["sun_exposure_multiplier"] = min(
                    float(effective["sun_exposure_multiplier"]),
                    float(params.get("sun_exposure_multiplier", max(0.05, 1.0 - 0.6 * severity))),
                )
            elif fault_id == "primary_sensor_hardware_failed" and not self.using_backup_sensor:
                effective["sensor_readout_bias"] = max(float(effective["sensor_readout_bias"]), 0.12 + 0.25 * severity)
            elif fault_id in {"rtg_power_decline", "long_term_power_generation_loss"}:
                effective["battery_health_factor"] = min(
                    float(effective["battery_health_factor"]),
                    float(params.get("battery_health_factor", max(0.1, 1.0 - 0.45 * severity))),
                )
            elif fault_id in {"instrument_heater_power_burden", "thermal_support_load_too_high", "primary_roll_thruster_heater_power_cost"}:
                effective["load_w_add"] = max(float(effective["load_w_add"]), float(params.get("load_w_add", 0.4 + 1.2 * severity)))
            elif fault_id in {"primary_attitude_thruster_degradation", "roll_thruster_fuel_line_residue_buildup"}:
                if not self.backup_thruster_enabled and not self.tcm_thruster_branch_enabled:
                    effective["attitude_error_deg"] = max(
                        float(effective["attitude_error_deg"]),
                        float(params.get("attitude_error_deg", 0.8 + 3.2 * severity)),
                    )
                    effective["pointing_control_efficiency"] = min(
                        float(effective["pointing_control_efficiency"]),
                        float(params.get("pointing_control_efficiency", max(0.1, 1.0 - 0.75 * severity))),
                    )
            elif fault_id in {"fds_memory_chip_failure", "telemetry_path_fault_unresolved", "aacs_or_packaging_chain_anomaly"}:
                effective["memory_growth_mb"] = max(float(effective["memory_growth_mb"]), float(params.get("memory_growth_mb", 2.0 + 8.0 * severity)))
                effective["packet_loss_floor"] = max(float(effective["packet_loss_floor"]), float(params.get("packet_loss_floor", 0.08 + 0.25 * severity)))
                effective["telemetry_path_ok"] = False

        for fault_id, record in self._active_fault_records(self.recoverable_faults):
            params = record.get("parameters", {})
            severity = float(record.get("severity", 0.5))
            if fault_id == "thermal_controller_stuck":
                effective["thermal_controller_stuck"] = True
            elif fault_id == "transceiver_softlock":
                effective["transceiver_softlock"] = True
                effective["packet_loss_floor"] = max(float(effective["packet_loss_floor"]), float(params.get("packet_loss_floor", 0.0)))
            elif fault_id == "compute_overload_transient":
                effective["cpu_load_floor"] = max(float(effective["cpu_load_floor"]), float(params.get("cpu_load_floor", 0.45 + 0.4 * severity)))
                effective["load_w_add"] = max(float(effective["load_w_add"]), float(params.get("load_w_add", 1.5 * severity)))
            elif fault_id == "load_spike_transient":
                effective["load_w_add"] = max(float(effective["load_w_add"]), float(params.get("load_w_add", 1.0 + 3.0 * severity)))
            elif fault_id == "sensor_readout_fault" and not self.using_backup_sensor:
                effective["sensor_readout_bias"] = max(float(effective["sensor_readout_bias"]), float(params.get("sensor_readout_bias", 0.1 + 0.22 * severity)))
            elif fault_id == "cache_accumulation":
                effective["memory_growth_mb"] = max(float(effective["memory_growth_mb"]), 4.0 + 20.0 * severity)
            elif fault_id == "memory_leak_runtime":
                effective["memory_growth_mb"] = max(float(effective["memory_growth_mb"]), float(params.get("memory_growth_mb", 4.0 + 20.0 * severity)))
            elif fault_id in {"thruster_heater_power_switch_error", "dormant_roll_thrusters_unavailable", "attitude_controller_stuck"}:
                if not self.backup_thruster_enabled:
                    effective["attitude_error_deg"] = max(float(effective["attitude_error_deg"]), float(params.get("attitude_error_deg", 0.6 + 2.4 * severity)))
            elif fault_id == "fds_code_segment_loss":
                effective["engineering_data_readable"] = False
                effective["science_data_readable"] = False
                effective["memory_growth_mb"] = max(float(effective["memory_growth_mb"]), 2.0 + 6.0 * severity)

        if self.active_mitigations.get("safe_mode", {}).get("active"):
            effective["load_w_add"] = min(float(effective["load_w_add"]), 0.0)
            effective["cpu_load_floor"] = min(float(effective["cpu_load_floor"]), 0.3)
        if self.active_mitigations.get("payload_disabled", {}).get("active"):
            effective["load_w_add"] = min(float(effective["load_w_add"]), 0.0)
        if self.active_mitigations.get("using_backup_sensor", {}).get("active"):
            effective["using_backup_sensor"] = True
            effective["sensor_readout_bias"] = 0.0
        if self.active_mitigations.get("backup_thruster_branch", {}).get("active"):
            effective["attitude_error_deg"] = min(float(effective["attitude_error_deg"]), 0.25)
            effective["pointing_control_efficiency"] = max(float(effective["pointing_control_efficiency"]), 0.82)
        if self.active_mitigations.get("instrument_load_shed", {}).get("active"):
            effective["load_w_add"] = min(float(effective["load_w_add"]), 0.0)
        if self.active_mitigations.get("fds_code_relocated", {}).get("active"):
            effective["engineering_data_readable"] = True
            effective["science_data_readable"] = True
        if self.active_mitigations.get("telemetry_path_isolated", {}).get("active"):
            effective["packet_loss_floor"] = min(float(effective["packet_loss_floor"]), 0.18)
        return {
            **self.fault_layer_summary(),
            "effective": effective,
        }

    def inject_fault(self, fault: str) -> None:
        fault = fault.lower().strip()
        if fault == "clear":
            self._clear_faults()
            self._clear_all_fault_layers()
            self.mode = "NORMAL"
            self.radiator_efficiency = 1.0
            self.thermal_controller_ok = True
            self.signal_strength = 0.86
            self.packet_loss = 0.04
            self.comms_restart_remaining_s = 0.0
            self.load_w = 3.2 if self.payload_enabled else min(self.load_w, 2.1)
            self.cpu_load = min(self.cpu_load, 0.28)
            self.storage_health = "nominal"
            self.using_backup_sensor = False
            self._bump_change_version()
            self.add_event("fault_clear", "Faults cleared by mission control")
            return
        self._inject_fault_bundle(fault)
        self._bump_change_version()
        self.add_event("fault_injected", f"Injected {fault} fault", fault=fault)

    def apply_command(self, action: str, params: Optional[Dict[str, Any]] = None, source: str = "unknown") -> Dict[str, Any]:
        params = params or {}
        action = action.upper().strip()
        if action not in ALLOWED_COMMANDS:
            raise ValueError(f"Command '{action}' not in allowed whitelist")

        before = self.snapshot()
        before_metrics = self.flatten_metrics()
        cleared_faults: List[str] = []
        suppressed_faults: List[str] = []
        mitigation_changes: Dict[str, Any] = {}
        msg = ""

        def clear_fault(fault_id: str) -> None:
            if self._clear_recoverable(fault_id, action):
                cleared_faults.append(fault_id)

        def suppress_fault(fault_id: str) -> None:
            if self._suppress_recoverable(fault_id, action):
                suppressed_faults.append(fault_id)

        def set_mitigation(name: str, **values: Any) -> None:
            mitigation_changes[name] = self._set_mitigation(name, **values)

        if action == "ENTER_SAFE_MODE":
            self.mode = "SAFE_MODE"
            self.payload_enabled = False
            self.load_w = min(self.load_w, 2.1)
            self.cpu_load = min(self.cpu_load, 0.22)
            self.sampling_rate = min(self.sampling_rate, 0.25)
            set_mitigation("safe_mode")
            set_mitigation("payload_disabled")
            set_mitigation("sampling_rate_reduced", rate=self.sampling_rate)
            suppress_fault("compute_overload_transient")
            msg = "Entered safe mode; payload disabled; load reduced."
        elif action == "EXIT_SAFE_MODE":
            self.mode = "NORMAL"
            self.payload_enabled = True
            self.sampling_rate = 1.0
            self.load_w = max(self.load_w, 3.2)
            mitigation_changes["safe_mode"] = {"before": copy.deepcopy(self.active_mitigations.get("safe_mode")), "after": {"active": False}}
            mitigation_changes["payload_disabled"] = {"before": copy.deepcopy(self.active_mitigations.get("payload_disabled")), "after": {"active": False}}
            mitigation_changes["sampling_rate_reduced"] = {"before": copy.deepcopy(self.active_mitigations.get("sampling_rate_reduced")), "after": {"active": False}}
            self.active_mitigations.pop("safe_mode", None)
            self.active_mitigations.pop("payload_disabled", None)
            self.active_mitigations.pop("sampling_rate_reduced", None)
            msg = "Exited safe mode; payload restored."
        elif action == "DISABLE_PAYLOAD":
            self.payload_enabled = False
            self.load_w = max(1.6, self.load_w - 2.1)
            self.cpu_load = max(0.14, self.cpu_load - 0.24)
            set_mitigation("payload_disabled")
            msg = "Payload disabled."
        elif action == "ENABLE_PAYLOAD":
            self.payload_enabled = True
            self.load_w += 1.5
            self.cpu_load = min(0.95, self.cpu_load + 0.18)
            mitigation_changes["payload_disabled"] = {"before": copy.deepcopy(self.active_mitigations.get("payload_disabled")), "after": {"active": False}}
            self.active_mitigations.pop("payload_disabled", None)
            msg = "Payload enabled."
        elif action == "RESTART_COMMS":
            clear_fault("transceiver_softlock")
            self.transceiver_softlock = False
            self.comms_restart_remaining_s = 4.0
            self.packet_loss = 1.0
            set_mitigation("restarting_comms", remaining_s=self.comms_restart_remaining_s)
            msg = "Comms restart initiated; temporary blackout expected."
        elif action == "SWITCH_TO_BACKUP_SENSOR":
            self.using_backup_sensor = True
            suppress_fault("sensor_readout_fault")
            self.storage_health = "nominal_backup_sensor"
            set_mitigation("using_backup_sensor")
            self.mode = "WARNING" if self._remaining_root_causes() else "NORMAL"
            msg = "Switched to backup sensor and marked primary as unreliable."
        elif action == "SWITCH_TO_BACKUP_THRUSTER":
            self.backup_thruster_enabled = True
            self.tcm_thruster_branch_enabled = True
            suppress_fault("attitude_controller_stuck")
            suppress_fault("thruster_heater_power_switch_error")
            self.attitude_error_deg = min(self.attitude_error_deg, 0.25)
            self.pointing_control_efficiency = max(self.pointing_control_efficiency, 0.84)
            set_mitigation("backup_thruster_branch", branch="tcm")
            self.mode = "WARNING" if self._remaining_root_causes() else "NORMAL"
            msg = "Switched pointing control to backup/TCM thruster branch. Primary thruster degradation remains recorded."
        elif action == "ENABLE_THRUSTER_HEATERS":
            clear_fault("thruster_heater_power_switch_error")
            clear_fault("dormant_roll_thrusters_unavailable")
            self.roll_thruster_heaters_enabled = True
            self.load_w += 0.28
            self.temp_c += 0.08
            set_mitigation("roll_thruster_heaters_enabled")
            msg = "Enabled dormant thruster heaters after power check; heater fault cleared where recoverable."
        elif action == "SHUT_DOWN_PRIMARY_ROLL_HEATER":
            self.primary_roll_heater_enabled = False
            self.load_w = max(0.8, self.load_w - 0.28)
            set_mitigation("primary_roll_heater_shutdown")
            msg = "Primary roll thruster heater shut down to recover power margin. Roll thruster root cause remains."
        elif action == "RESTORE_HEATER_POWER":
            clear_fault("thruster_heater_power_switch_error")
            self.roll_thruster_heaters_enabled = True
            self.primary_roll_heater_enabled = True
            self.load_w += 0.18
            set_mitigation("heater_power_restored")
            msg = "Heater power switch state restored. Physical residue or aging faults remain."
        elif action == "RESET_THERMAL_CONTROLLER":
            clear_fault("thermal_controller_stuck")
            self.thermal_controller_ok = True
            self.thermal_controller_stable = True
            set_mitigation("thermal_controller_reset_recently", remaining_s=30.0)
            self.mode = "WARNING" if self._remaining_root_causes() else "NORMAL"
            msg = "Thermal controller reset; control loop restored. Physical radiator degradation, if present, remains."
        elif action == "LOWER_SAMPLING_RATE":
            self.sampling_rate = max(0.1, self.sampling_rate * 0.4)
            self.load_w = max(1.8, self.load_w - 0.7)
            set_mitigation("sampling_rate_reduced", rate=self.sampling_rate)
            suppress_fault("transceiver_softlock")
            msg = "Sampling rate lowered."
        elif action in {"SHED_NONESSENTIAL_LOAD", "REALLOCATE_POWER_BUDGET"}:
            disabled = self._shed_nonessential_load()
            set_mitigation("instrument_load_shed", disabled=disabled)
            set_mitigation("power_budget_reallocated")
            if disabled:
                msg = f"Disabled nonessential instrument {disabled['instrument']} to recover power margin."
            else:
                self.payload_enabled = False
                self.load_w = max(1.4, self.load_w - 0.8)
                set_mitigation("payload_disabled")
                msg = "No nonessential instruments remained; payload load reduced instead."
        elif action == "DISABLE_INSTRUMENT":
            disabled = self._disable_instrument(str(params.get("instrument") or ""))
            if not disabled:
                disabled = self._shed_nonessential_load()
            set_mitigation("instrument_load_shed", disabled=disabled)
            msg = f"Disabled instrument {disabled['instrument']}." if disabled else "No enabled nonessential instrument was available to disable."
        elif action == "RESTORE_INSTRUMENT":
            restored = self._restore_instrument(str(params.get("instrument") or ""))
            msg = f"Restored instrument {restored['instrument']}." if restored else "No disabled instrument matched restore request."
        elif action == "CLEAR_CACHE":
            clear_fault("cache_accumulation")
            clear_fault("compute_overload_transient")
            clear_fault("sensor_readout_fault")
            self.cache_pressure = 0.0
            self.mem_used_mb = max(260.0, self.mem_used_mb - 180.0)
            self.cpu_load = max(0.2, self.cpu_load - 0.18)
            msg = "Cache cleared."
        elif action == "REBOOT_COMPUTER":
            clear_fault("cache_accumulation")
            clear_fault("compute_overload_transient")
            clear_fault("memory_leak_runtime")
            self.cpu_load = 0.18
            self.mem_used_mb = 300.0
            self.load_w = min(self.load_w, 2.8)
            self.cache_pressure = 0.0
            msg = "Computer reboot simulated."
        elif action == "RELOCATE_FDS_CODE":
            clear_fault("fds_code_segment_loss")
            self.fds_code_relocated = True
            self.engineering_data_readable = True
            self.science_data_readable = True
            self.storage_health = "fds_code_relocated"
            set_mitigation("fds_code_relocated")
            msg = "FDS code segments relocated around suspected memory failure. Memory-chip root cause remains."
        elif action == "VERIFY_TELEMETRY_RECOVERY":
            self.telemetry_path_ok = self.fds_code_relocated or self.telemetry_path_ok
            self.engineering_data_readable = self.engineering_data_readable or self.telemetry_path_ok
            set_mitigation("telemetry_recovery_verified", telemetry_path_ok=self.telemetry_path_ok)
            msg = "Telemetry recovery verification executed; no physical root cause was cleared."
        elif action == "ISOLATE_TELEMETRY_PATH":
            suppress_fault("fds_code_segment_loss")
            self.telemetry_path_ok = True
            set_mitigation("telemetry_path_isolated")
            self.packet_loss = min(self.packet_loss, 0.22)
            msg = "Telemetry path isolated to a stable branch. Unresolved telemetry/FDS root causes remain."

        self._refresh_fault_labels()
        self._bump_change_version()
        after_metrics = self.flatten_metrics()
        repair_trace = {
            "step_index": 0,
            "action": action,
            "cleared_faults": cleared_faults,
            "suppressed_faults": suppressed_faults,
            "remaining_root_causes": self._remaining_root_causes(),
            "mitigation_changes": mitigation_changes,
            "key_metric_deltas": self._metric_deltas(before_metrics, after_metrics),
            "note": msg,
        }
        self.last_command = {
            "ts": self.now(),
            "action": action,
            "params": params,
            "source": source,
            "message": msg,
            "repair_trace": repair_trace,
        }
        self.add_event("command_executed", msg, action=action, source=source)
        return {
            "ok": True,
            "message": msg,
            "before": before,
            "after": self.snapshot(),
            "cleared_faults": cleared_faults,
            "suppressed_faults": suppressed_faults,
            "remaining_root_causes": self._remaining_root_causes(),
            "mitigation_changes": mitigation_changes,
            "repair_trace": repair_trace,
        }

    def update(
        self,
        dt: float,
        environment: Optional[dict] = None,
        fault_context: Optional[dict] = None,
        stochastic: bool = True,
        rng: Optional[random.Random] = None,
    ) -> None:
        dt = max(0.0, float(dt))
        if environment:
            self._apply_environment(environment)
        if fault_context is None:
            fault_context = self.local_fault_context()
        self._refresh_fault_labels()
        active_faults = set(self.active_faults)
        effective = fault_context.get("effective", {}) if isinstance(fault_context, dict) else {}

        self.sim_elapsed_s += dt
        t = self.sim_elapsed_s
        rand = rng.uniform if rng else random.uniform
        jitter = rand(-0.03, 0.03) if stochastic else 0.0
        sun_exposure = max(0.0, self.sun_exposure * float(effective.get("sun_exposure_multiplier", 1.0)))
        eclipse_factor = max(0.0, min(1.0, self.eclipse_factor))
        radiation_level = max(0.0, min(1.0, self.radiation_level))
        antenna_alignment_error_deg = max(
            0.0,
            abs(float(effective.get("antenna_alignment_error_deg", self.antenna_alignment_error_deg))),
        )
        cooling_factor = max(self.thermal_sink_efficiency, 0.1)
        battery_age_factor = max(0.0, min(
            self.battery_age_factor,
            self.battery_health_factor,
            float(effective.get("battery_health_factor", 1.0)),
        ))
        radiator_multiplier = max(0.05, min(1.0, float(effective.get("radiator_efficiency_multiplier", 1.0))))
        self.radiator_efficiency = max(0.05, min(1.0, self.radiator_physical_efficiency * radiator_multiplier))
        thermal_controller_stuck = bool(effective.get("thermal_controller_stuck", False))
        self.thermal_controller_ok = bool(self.thermal_controller_stable and not thermal_controller_stuck)
        effective_load_w = max(0.5, self.load_w + float(effective.get("load_w_add", 0.0)))
        cpu_load_floor = max(0.0, min(0.99, float(effective.get("cpu_load_floor", 0.0))))
        memory_growth_mb = max(0.0, float(effective.get("memory_growth_mb", 0.0)))
        sensor_readout_bias = max(0.0, float(effective.get("sensor_readout_bias", 0.0)))
        using_backup_sensor = bool(effective.get("using_backup_sensor", self.using_backup_sensor))
        transceiver_softlock = bool(effective.get("transceiver_softlock", False))
        attitude_error_deg = max(0.0, abs(float(effective.get("attitude_error_deg", self.attitude_error_deg))))
        pointing_efficiency = max(0.0, min(1.0, float(effective.get("pointing_control_efficiency", self.pointing_control_efficiency))))
        self.attitude_error_deg = attitude_error_deg
        self.pointing_control_efficiency = pointing_efficiency
        self.telemetry_path_ok = bool(effective.get("telemetry_path_ok", self.telemetry_path_ok))
        self.engineering_data_readable = bool(effective.get("engineering_data_readable", self.engineering_data_readable))
        self.science_data_readable = bool(effective.get("science_data_readable", self.science_data_readable))

        # Fault-layer effects derived from effective context.
        if thermal_controller_stuck:
            self.temp_c += (0.28 + max(0, effective_load_w - 3.5) * 0.06) * dt
            self.packet_loss = min(0.78, self.packet_loss + 0.004 * dt)
        if transceiver_softlock:
            self.signal_strength = max(0.08, self.signal_strength - 0.01 * dt)
            self.packet_loss = min(0.92, self.packet_loss + 0.018 * dt)
        packet_loss_floor = max(0.0, min(1.0, float(effective.get("packet_loss_floor", 0.0))))
        if packet_loss_floor:
            self.packet_loss = max(self.packet_loss, packet_loss_floor)
        if battery_age_factor < 0.95:
            self.battery_voltage -= (0.01 + (0.95 - battery_age_factor) * 0.045) * dt
            self.temp_c += (0.03 + (0.95 - battery_age_factor) * 0.08) * dt
        if cpu_load_floor:
            self.cpu_load = max(self.cpu_load, cpu_load_floor)
        if memory_growth_mb:
            self.mem_used_mb = min(1600.0, self.mem_used_mb + memory_growth_mb * dt)
            self.storage_health = "memory_pressure"
        if sensor_readout_bias and not using_backup_sensor:
            drift_noise = rand(-0.15, 0.15) if stochastic else 0.0
            self.temp_c += math.sin(t * 0.7) * 0.05 + sensor_readout_bias + drift_noise

        alignment_penalty = antenna_alignment_error_deg * 0.002
        pointing_penalty = attitude_error_deg * 0.006 + (1.0 - pointing_efficiency) * 0.08
        radiation_penalty = radiation_level * 0.08
        self.signal_strength = max(0.0, min(1.0, self.signal_strength - alignment_penalty - radiation_penalty - pointing_penalty))
        self.packet_loss = max(
            0.0,
            min(1.0, self.packet_loss + alignment_penalty * 0.4 + radiation_penalty * 0.5 + pointing_penalty * 0.35),
        )
        if radiation_level:
            self.cpu_load = min(0.99, self.cpu_load + 0.003 * radiation_level * dt)
        if not self.telemetry_path_ok:
            self.storage_health = "telemetry_path_fault"
        if not self.engineering_data_readable or not self.science_data_readable:
            self.storage_health = "fds_data_unreadable"

        # Natural dynamics
        solar_heat = sun_exposure * 3.5 * (1.0 - eclipse_factor)
        target_temp = 36.0 + effective_load_w * (2.1 / max(self.radiator_efficiency, 0.1)) + solar_heat
        if self.thermal_controller_ok:
            self.temp_c += (target_temp - self.temp_c) * 0.045 * cooling_factor * dt
        elif self.mode == "SAFE_MODE":
            self.temp_c += (38.0 - self.temp_c) * 0.06 * cooling_factor * dt

        # Power dynamics
        effective_solar = self.solar_input_w * sun_exposure * (1.0 - eclipse_factor)
        aging_penalty = (1.0 - battery_age_factor) * 0.01
        net = effective_solar - effective_load_w - aging_penalty
        self.battery_voltage += net * 0.006 * dt
        self.battery_voltage = max(9.2, min(12.8, self.battery_voltage))

        # Comms restart
        if self.comms_restart_remaining_s > 0:
            self.signal_strength = 0.05
            self.packet_loss = 1.0
            self.comms_restart_remaining_s = max(0.0, self.comms_restart_remaining_s - dt)
            if "restarting_comms" in self.active_mitigations:
                self.active_mitigations["restarting_comms"]["remaining_s"] = self.comms_restart_remaining_s
        elif self.last_command and self.last_command.get("action") == "RESTART_COMMS":
            self.signal_strength += (0.72 - self.signal_strength) * 0.08 * dt
            self.packet_loss += (0.09 - self.packet_loss) * 0.08 * dt
            self.active_mitigations.pop("restarting_comms", None)

        # Derivative effects
        if self.temp_c > 75:
            self.packet_loss = min(0.95, self.packet_loss + 0.003 * dt)
            self.battery_voltage -= 0.002 * dt
        if self.mode == "SAFE_MODE":
            self.signal_strength += (0.82 - self.signal_strength) * 0.04 * dt
            self.packet_loss += (0.08 - self.packet_loss) * 0.04 * dt

        # Clamp and jitter
        self.temp_c = max(20.0, min(110.0, self.temp_c + jitter))
        self.signal_strength = max(0.0, min(1.0, self.signal_strength))
        self.packet_loss = max(0.0, min(1.0, self.packet_loss))
        cpu_jitter = rand(-0.01, 0.01) if stochastic else 0.0
        mem_jitter = rand(-2.5, 2.5) if stochastic else 0.0
        self.cpu_load = max(0.05, min(0.99, self.cpu_load + cpu_jitter))
        self.mem_used_mb = max(200.0, min(1600.0, self.mem_used_mb + mem_jitter))
        self._decrement_mitigations(dt)
        self._refresh_fault_labels()
        active_faults = set(self.active_faults)

        # Mode update if not forced safe
        if self.mode != "SAFE_MODE":
            if self.temp_c > 82 or self.battery_voltage < 10.4 or self.packet_loss > 0.68 or self.attitude_error_deg > 3.0:
                self.mode = "FAULT"
            elif self.temp_c > 70 or self.battery_voltage < 11.0 or self.packet_loss > 0.3 or self.attitude_error_deg > 1.0:
                self.mode = "WARNING"
            elif self._remaining_root_causes():
                self.mode = "WARNING"
            elif not active_faults:
                self.mode = "NORMAL"

        self.seq += 1

    def _decrement_mitigations(self, dt: float) -> None:
        expired: List[str] = []
        for name, mitigation in self.active_mitigations.items():
            if name == "restarting_comms":
                continue
            if "remaining_s" not in mitigation:
                continue
            remaining = max(0.0, float(mitigation.get("remaining_s", 0.0)) - dt)
            mitigation["remaining_s"] = remaining
            if remaining <= 0:
                expired.append(name)
        for name in expired:
            self.active_mitigations.pop(name, None)

    def _apply_environment(self, environment: Dict[str, Any]) -> None:
        allowed = {
            "sun_exposure",
            "eclipse_factor",
            "radiation_level",
            "antenna_alignment_error_deg",
            "battery_age_factor",
            "thermal_sink_efficiency",
            "mission_phase",
        }
        for key, value in environment.items():
            if key in allowed:
                setattr(self, key, value)

    def status_for_subsystem(self, subsystem: str) -> str:
        if subsystem == "thermal":
            if self.temp_c > 82:
                return "FAULT"
            if self.temp_c > 70:
                return "WARN"
            return "OK"
        if subsystem == "power":
            if self.battery_voltage < 10.4:
                return "FAULT"
            if self.battery_voltage < 11.0:
                return "WARN"
            return "OK"
        if subsystem == "comms":
            if self.packet_loss > 0.68:
                return "FAULT"
            if self.packet_loss > 0.3:
                return "WARN"
            return "OK"
        if subsystem == "computer":
            if self.cpu_load > 0.9:
                return "FAULT"
            if self.cpu_load > 0.75:
                return "WARN"
            return "OK"
        if subsystem == "payload":
            return "OK" if self.payload_enabled else "OFF"
        if subsystem == "attitude":
            if self.attitude_error_deg > 3.0:
                return "FAULT"
            if self.attitude_error_deg > 1.0 or not self.primary_thruster_ok:
                return "WARN"
            return "OK"
        if subsystem in {"fds", "telemetry"}:
            if not self.engineering_data_readable or not self.science_data_readable:
                return "FAULT"
            if not self.telemetry_path_ok or self.fds_code_relocated:
                return "WARN"
            return "OK"
        return "OK"

    def snapshot(self) -> Dict[str, Any]:
        ts = self.now()
        return {
            "probe_id": self.probe_id,
            "ts": ts,
            "seq": self.seq,
            "sim_elapsed_s": round(self.sim_elapsed_s, 3),
            "change_version": self.change_version,
            "mode": self.mode,
            "active_fault": self.active_fault,
            "primary_fault": self.primary_fault,
            "active_faults": list(self.active_faults),
            "fault_layers": self.fault_layer_summary(),
            "subsystems": {
                "power": {
                    "status": self.status_for_subsystem("power"),
                    "battery_voltage": round(self.battery_voltage, 3),
                    "load_w": round(self.load_w, 3),
                    "solar_input_w": round(self.solar_input_w, 3),
                },
                "thermal": {
                    "status": self.status_for_subsystem("thermal"),
                    "temp_c": round(self.temp_c, 3),
                    "controller_ok": self.thermal_controller_ok,
                    "radiator_efficiency": round(self.radiator_efficiency, 3),
                },
                "comms": {
                    "status": self.status_for_subsystem("comms"),
                    "signal_strength": round(self.signal_strength, 3),
                    "packet_loss": round(self.packet_loss, 3),
                },
                "computer": {
                    "status": self.status_for_subsystem("computer"),
                    "cpu_load": round(self.cpu_load, 3),
                    "mem_used_mb": round(self.mem_used_mb, 1),
                    "storage_health": self.storage_health,
                },
                "payload": {
                    "status": self.status_for_subsystem("payload"),
                    "enabled": self.payload_enabled,
                    "sampling_rate": round(self.sampling_rate, 3),
                    "using_backup_sensor": self.using_backup_sensor,
                    "instruments": copy.deepcopy(self.science_instruments),
                    "enabled_instrument_count": sum(1 for item in self.science_instruments.values() if item.get("enabled", False)),
                },
                "attitude": {
                    "status": self.status_for_subsystem("attitude"),
                    "primary_thruster_ok": self.primary_thruster_ok,
                    "backup_thruster_enabled": self.backup_thruster_enabled,
                    "tcm_thruster_branch_enabled": self.tcm_thruster_branch_enabled,
                    "roll_thruster_heaters_enabled": self.roll_thruster_heaters_enabled,
                    "primary_roll_heater_enabled": self.primary_roll_heater_enabled,
                    "attitude_error_deg": round(self.attitude_error_deg, 3),
                    "pointing_control_efficiency": round(self.pointing_control_efficiency, 3),
                },
                "fds": {
                    "status": self.status_for_subsystem("fds"),
                    "telemetry_path_ok": self.telemetry_path_ok,
                    "fds_code_relocated": self.fds_code_relocated,
                    "engineering_data_readable": self.engineering_data_readable,
                    "science_data_readable": self.science_data_readable,
                },
            },
            "last_command": self.last_command,
            "events": list(self.events)[:20],
        }

    def flatten_metrics(self) -> Dict[str, float]:
        s = self.snapshot()["subsystems"]
        return {
            "power.battery_voltage": s["power"]["battery_voltage"],
            "power.load_w": s["power"]["load_w"],
            "thermal.temp_c": s["thermal"]["temp_c"],
            "comms.signal_strength": s["comms"]["signal_strength"],
            "comms.packet_loss": s["comms"]["packet_loss"],
            "computer.cpu_load": s["computer"]["cpu_load"],
            "computer.mem_used_mb": s["computer"]["mem_used_mb"],
            "payload.sampling_rate": s["payload"]["sampling_rate"],
            "attitude.attitude_error_deg": s.get("attitude", {}).get("attitude_error_deg", 0.0),
            "attitude.pointing_control_efficiency": s.get("attitude", {}).get("pointing_control_efficiency", 1.0),
            "payload.enabled_instrument_count": s["payload"].get("enabled_instrument_count", 0),
        }


class TelemetryHistory:
    def __init__(self, limit: int = 1000) -> None:
        self.limit = limit
        self.rows: Deque[Dict[str, Any]] = deque(maxlen=limit)

    def append(self, snapshot: Dict[str, Any]) -> None:
        row = {"ts": snapshot["ts"], "mode": snapshot["mode"], "active_fault": snapshot["active_fault"]}
        subs = snapshot["subsystems"]
        row.update({
            "power.battery_voltage": subs["power"]["battery_voltage"],
            "power.load_w": subs["power"]["load_w"],
            "thermal.temp_c": subs["thermal"]["temp_c"],
            "comms.signal_strength": subs["comms"]["signal_strength"],
            "comms.packet_loss": subs["comms"]["packet_loss"],
            "computer.cpu_load": subs["computer"]["cpu_load"],
            "computer.mem_used_mb": subs["computer"]["mem_used_mb"],
            "payload.sampling_rate": subs["payload"]["sampling_rate"],
        })
        self.rows.append(row)

    def clear(self) -> None:
        self.rows.clear()

    def metric_series(self, metric: str, limit: int = 300) -> List[Dict[str, Any]]:
        selected = list(self.rows)[-limit:]
        return [
            {"timestamp": row["ts"] * 1000, "value": row.get(metric), "metric": metric}
            for row in selected
            if metric in row
        ]

    def all_recent(self, limit: int = 300) -> List[Dict[str, Any]]:
        return list(self.rows)[-limit:]
