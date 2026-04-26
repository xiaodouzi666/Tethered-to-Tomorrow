from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

ALLOWED_COMMANDS = {
    "ENTER_SAFE_MODE",
    "EXIT_SAFE_MODE",
    "DISABLE_PAYLOAD",
    "ENABLE_PAYLOAD",
    "RESTART_COMMS",
    "SWITCH_TO_BACKUP_SENSOR",
    "RESET_THERMAL_CONTROLLER",
    "LOWER_SAMPLING_RATE",
    "CLEAR_CACHE",
    "REBOOT_COMPUTER",
}

HIGH_RISK_COMMANDS = {"EXIT_SAFE_MODE", "RESTART_COMMS", "REBOOT_COMPUTER"}


@dataclass
class SpacecraftState:
    probe_id: str = "voyager-rpi-01"
    mode: str = "NORMAL"  # NORMAL | WARNING | FAULT | SAFE_MODE
    active_fault: str = "none"
    seq: int = 0
    started_ts: float = field(default_factory=time.time)

    battery_voltage: float = 12.4
    load_w: float = 3.2
    solar_input_w: float = 2.6

    temp_c: float = 42.0
    thermal_controller_ok: bool = True
    radiator_efficiency: float = 1.0

    signal_strength: float = 0.86
    packet_loss: float = 0.04
    comms_restarting_until: float = 0.0

    cpu_load: float = 0.28
    mem_used_mb: float = 420.0
    storage_health: str = "nominal"

    payload_enabled: bool = True
    sampling_rate: float = 1.0
    using_backup_sensor: bool = False

    last_command: Optional[Dict[str, Any]] = None
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    def now(self) -> float:
        return time.time()

    def add_event(self, event_type: str, message: str, **extra: Any) -> None:
        self.events.appendleft({
            "ts": self.now(),
            "type": event_type,
            "message": message,
            **extra,
        })

    def inject_fault(self, fault: str) -> None:
        fault = fault.lower().strip()
        self.active_fault = fault
        if fault == "clear":
            self.active_fault = "none"
            self.mode = "NORMAL"
            self.radiator_efficiency = 1.0
            self.thermal_controller_ok = True
            self.storage_health = "nominal"
            self.using_backup_sensor = False
            self.add_event("fault_clear", "Faults cleared by mission control")
            return
        if fault not in {"thermal", "comms", "power", "sensor"}:
            raise ValueError(f"Unsupported fault '{fault}'")
        self.mode = "FAULT"
        if fault == "thermal":
            self.radiator_efficiency = 0.35
            self.thermal_controller_ok = False
        if fault == "comms":
            self.signal_strength = min(self.signal_strength, 0.28)
            self.packet_loss = max(self.packet_loss, 0.35)
        if fault == "power":
            self.load_w = max(self.load_w, 6.2)
            self.cpu_load = max(self.cpu_load, 0.84)
        if fault == "sensor":
            self.storage_health = "sensor_drift_detected"
        self.add_event("fault_injected", f"Injected {fault} fault", fault=fault)

    def apply_command(self, action: str, params: Optional[Dict[str, Any]] = None, source: str = "unknown") -> Dict[str, Any]:
        params = params or {}
        action = action.upper().strip()
        if action not in ALLOWED_COMMANDS:
            raise ValueError(f"Command '{action}' not in allowed whitelist")

        before = self.snapshot()
        msg = ""

        if action == "ENTER_SAFE_MODE":
            self.mode = "SAFE_MODE"
            self.payload_enabled = False
            self.load_w = min(self.load_w, 2.1)
            self.cpu_load = min(self.cpu_load, 0.22)
            self.sampling_rate = min(self.sampling_rate, 0.25)
            msg = "Entered safe mode; payload disabled; load reduced."
        elif action == "EXIT_SAFE_MODE":
            self.mode = "NORMAL"
            self.payload_enabled = True
            self.sampling_rate = 1.0
            self.load_w = max(self.load_w, 3.2)
            msg = "Exited safe mode; payload restored."
        elif action == "DISABLE_PAYLOAD":
            self.payload_enabled = False
            self.load_w = max(1.6, self.load_w - 2.1)
            self.cpu_load = max(0.14, self.cpu_load - 0.24)
            msg = "Payload disabled."
        elif action == "ENABLE_PAYLOAD":
            self.payload_enabled = True
            self.load_w += 1.5
            self.cpu_load = min(0.95, self.cpu_load + 0.18)
            msg = "Payload enabled."
        elif action == "RESTART_COMMS":
            self.comms_restarting_until = self.now() + 4.0
            self.packet_loss = 1.0
            msg = "Comms restart initiated; temporary blackout expected."
        elif action == "SWITCH_TO_BACKUP_SENSOR":
            self.using_backup_sensor = True
            if self.active_fault == "sensor":
                self.active_fault = "none"
                self.storage_health = "nominal_backup_sensor"
                self.mode = "WARNING"
            msg = "Switched to backup sensor and marked primary as unreliable."
        elif action == "RESET_THERMAL_CONTROLLER":
            self.thermal_controller_ok = True
            self.radiator_efficiency = max(self.radiator_efficiency, 0.78)
            if self.active_fault == "thermal":
                self.active_fault = "none"
                self.mode = "WARNING"
            msg = "Thermal controller reset; radiator efficiency partially restored."
        elif action == "LOWER_SAMPLING_RATE":
            self.sampling_rate = max(0.1, self.sampling_rate * 0.4)
            self.load_w = max(1.8, self.load_w - 0.7)
            msg = "Sampling rate lowered."
        elif action == "CLEAR_CACHE":
            self.mem_used_mb = max(260.0, self.mem_used_mb - 180.0)
            self.cpu_load = max(0.2, self.cpu_load - 0.18)
            msg = "Cache cleared."
        elif action == "REBOOT_COMPUTER":
            self.cpu_load = 0.18
            self.mem_used_mb = 300.0
            self.load_w = min(self.load_w, 2.8)
            msg = "Computer reboot simulated."

        self.last_command = {
            "ts": self.now(),
            "action": action,
            "params": params,
            "source": source,
            "message": msg,
        }
        self.add_event("command_executed", msg, action=action, source=source)
        return {"ok": True, "message": msg, "before": before, "after": self.snapshot()}

    def update(self, dt: float) -> None:
        t = self.now() - self.started_ts
        jitter = random.uniform(-0.03, 0.03)

        # Fault effects
        if self.active_fault == "thermal":
            self.temp_c += (0.42 + max(0, self.load_w - 3.5) * 0.08) * dt
            self.packet_loss = min(0.78, self.packet_loss + 0.008 * dt)
        elif self.active_fault == "comms":
            self.signal_strength = max(0.12, self.signal_strength - 0.012 * dt)
            self.packet_loss = min(0.92, self.packet_loss + 0.02 * dt)
        elif self.active_fault == "power":
            self.battery_voltage -= 0.035 * dt
            self.temp_c += 0.15 * dt
        elif self.active_fault == "sensor" and not self.using_backup_sensor:
            # Simulated drift in temperature reading.
            self.temp_c += math.sin(t * 0.7) * 0.05 + random.uniform(-0.15, 0.15)

        # Natural dynamics
        target_temp = 39.0 + self.load_w * (2.1 / max(self.radiator_efficiency, 0.1))
        if self.thermal_controller_ok and self.active_fault != "thermal":
            self.temp_c += (target_temp - self.temp_c) * 0.045 * dt
        elif self.mode == "SAFE_MODE":
            self.temp_c += (38.0 - self.temp_c) * 0.06 * dt

        # Power dynamics
        net = self.solar_input_w - self.load_w
        self.battery_voltage += net * 0.006 * dt
        self.battery_voltage = max(9.2, min(12.8, self.battery_voltage))

        # Comms restart
        if self.comms_restarting_until > self.now():
            self.signal_strength = 0.05
            self.packet_loss = 1.0
        elif self.last_command and self.last_command.get("action") == "RESTART_COMMS":
            self.signal_strength += (0.72 - self.signal_strength) * 0.08 * dt
            self.packet_loss += (0.09 - self.packet_loss) * 0.08 * dt

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
        self.cpu_load = max(0.05, min(0.99, self.cpu_load + random.uniform(-0.01, 0.01)))
        self.mem_used_mb = max(200.0, min(1600.0, self.mem_used_mb + random.uniform(-2.5, 2.5)))

        # Mode update if not forced safe
        if self.mode != "SAFE_MODE":
            if self.temp_c > 82 or self.battery_voltage < 10.4 or self.packet_loss > 0.68:
                self.mode = "FAULT"
            elif self.temp_c > 70 or self.battery_voltage < 11.0 or self.packet_loss > 0.3:
                self.mode = "WARNING"
            elif self.active_fault == "none":
                self.mode = "NORMAL"

        self.seq += 1

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
        return "OK"

    def snapshot(self) -> Dict[str, Any]:
        ts = self.now()
        return {
            "probe_id": self.probe_id,
            "ts": ts,
            "seq": self.seq,
            "mode": self.mode,
            "active_fault": self.active_fault,
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

    def metric_series(self, metric: str, limit: int = 300) -> List[Dict[str, Any]]:
        selected = list(self.rows)[-limit:]
        return [
            {"timestamp": row["ts"] * 1000, "value": row.get(metric), "metric": metric}
            for row in selected
            if metric in row
        ]

    def all_recent(self, limit: int = 300) -> List[Dict[str, Any]]:
        return list(self.rows)[-limit:]
