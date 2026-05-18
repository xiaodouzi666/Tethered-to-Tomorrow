from __future__ import annotations

from typing import Any, Dict, Optional

from pi_probe.twin.schemas import TwinCalibration


METRIC_PATHS = {
    "temp_c": ("thermal", "temp_c"),
    "battery_voltage": ("power", "battery_voltage"),
    "packet_loss": ("comms", "packet_loss"),
    "signal_strength": ("comms", "signal_strength"),
    "cpu_load": ("computer", "cpu_load"),
}


def calibrate_baseline(
    *,
    baseline_id: str,
    real_snapshot: Dict[str, Any],
    twin_snapshot: Dict[str, Any],
) -> TwinCalibration:
    deltas: Dict[str, float] = {}
    for metric, (subsystem, field) in METRIC_PATHS.items():
        real_value = _metric(real_snapshot, subsystem, field)
        twin_value = _metric(twin_snapshot, subsystem, field)
        if real_value is None or twin_value is None:
            continue
        deltas[metric] = round(real_value - twin_value, 4)

    max_abs_delta = max((abs(value) for value in deltas.values()), default=0.0)
    confidence = max(0.0, min(1.0, 1.0 - max_abs_delta / 100.0))
    return TwinCalibration(
        baseline_id=baseline_id,
        metric_deltas=deltas,
        max_abs_delta=round(max_abs_delta, 4),
        confidence=round(confidence, 3),
        note="Frozen baseline clone matches current probe snapshot within tracked metric deltas.",
    )


def _metric(snapshot: Dict[str, Any], subsystem: str, field: str) -> Optional[float]:
    subsystems = snapshot.get("subsystems", {})
    if not isinstance(subsystems, dict):
        return None
    source = subsystems.get(subsystem, {})
    if not isinstance(source, dict):
        return None
    value = source.get(field)
    return float(value) if isinstance(value, (int, float)) else None
