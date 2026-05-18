from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pi_probe.helm.schemas import HelmMonitorResult


def monitor_snapshot(snapshot: Dict[str, Any], recent_events: Iterable[Dict[str, Any]] | None = None) -> HelmMonitorResult:
    subsystems = snapshot.get("subsystems", {}) if isinstance(snapshot.get("subsystems"), dict) else {}
    reasons: List[str] = []
    suspected: List[str] = []

    def add(system: str, reason: str) -> None:
        if system not in suspected:
            suspected.append(system)
        reasons.append(reason)

    mode = str(snapshot.get("mode", "NORMAL"))
    active_fault = str(snapshot.get("active_fault", "none"))
    if mode == "FAULT":
        add("probe", "Probe mode is FAULT.")
    if active_fault and active_fault != "none":
        add(active_fault, f"Active fault label is {active_fault}.")

    thermal = subsystems.get("thermal", {})
    if isinstance(thermal, dict):
        temp_c = _float(thermal.get("temp_c"))
        if temp_c is not None and temp_c >= 70:
            add("thermal", f"Thermal trend is elevated at {temp_c:.1f}C.")
        if thermal.get("controller_ok") is False:
            add("thermal", "Thermal controller is not OK.")

    power = subsystems.get("power", {})
    if isinstance(power, dict):
        voltage = _float(power.get("battery_voltage"))
        if voltage is not None and voltage <= 10.8:
            add("power", f"Battery voltage is low at {voltage:.2f}V.")

    comms = subsystems.get("comms", {})
    if isinstance(comms, dict):
        loss = _float(comms.get("packet_loss"))
        signal = _float(comms.get("signal_strength"))
        if loss is not None and loss >= 0.3:
            add("comms", f"Packet loss is elevated at {loss:.2f}.")
        if signal is not None and signal <= 0.25:
            add("comms", f"Signal strength is weak at {signal:.2f}.")

    events = list(recent_events or [])
    if events and any(str(event.get("type")) == "fault_injected" for event in events[:5]):
        add("probe", "Recent fault injection event is present.")

    if not reasons:
        return HelmMonitorResult()

    severity = "MEDIUM"
    if mode == "FAULT" or len(suspected) > 1:
        severity = "HIGH"
    if any("low at" in reason or "weak" in reason for reason in reasons):
        severity = "HIGH"

    return HelmMonitorResult(
        should_start_session=True,
        severity=severity,
        reason=" ".join(reasons),
        suspected_subsystems=suspected,
        operator_needed=True,
        source="rules",
    )


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
