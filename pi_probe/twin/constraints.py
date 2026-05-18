from __future__ import annotations

from typing import Any, Dict, List

from pi_probe.twin.schemas import ConstraintResult


def evaluate_constraints(trajectory: List[Dict[str, Any]]) -> List[ConstraintResult]:
    if not trajectory:
        return [
            ConstraintResult(
                name="trajectory_non_empty",
                passed=False,
                message="Twin produced no trajectory points.",
            )
        ]

    temp_values = [_metric(point, "thermal", "temp_c", 0.0) for point in trajectory]
    battery_values = [_metric(point, "power", "battery_voltage", 0.0) for point in trajectory]
    packet_values = [_metric(point, "comms", "packet_loss", 0.0) for point in trajectory]
    signal_values = [_metric(point, "comms", "signal_strength", 0.0) for point in trajectory]
    cpu_values = [_metric(point, "computer", "cpu_load", 0.0) for point in trajectory]

    max_temp = max(temp_values)
    min_battery = min(battery_values)
    max_packet_loss = max(packet_values)
    min_signal = min(signal_values)
    max_cpu = max(cpu_values)
    safe_mode_reachable = min_battery >= 9.5 and max_cpu <= 0.98

    return [
        ConstraintResult(
            name="temp_c <= 85",
            passed=max_temp <= 85.0,
            current_value=temp_values[-1],
            worst_value=max_temp,
            threshold=85.0,
            message=_message(max_temp <= 85.0, "Temperature remained within limit.", "Temperature exceeded 85C."),
        ),
        ConstraintResult(
            name="battery_voltage >= 10.5",
            passed=min_battery >= 10.5,
            current_value=battery_values[-1],
            worst_value=min_battery,
            threshold=10.5,
            message=_message(min_battery >= 10.5, "Battery remained above reserve limit.", "Battery dropped below 10.5V."),
        ),
        ConstraintResult(
            name="packet_loss <= 0.60",
            passed=max_packet_loss <= 0.60,
            current_value=packet_values[-1],
            worst_value=max_packet_loss,
            threshold=0.60,
            message=_message(max_packet_loss <= 0.60, "Packet loss remained within limit.", "Packet loss exceeded 0.60."),
        ),
        ConstraintResult(
            name="signal_strength >= 0.15",
            passed=min_signal >= 0.15,
            current_value=signal_values[-1],
            worst_value=min_signal,
            threshold=0.15,
            message=_message(min_signal >= 0.15, "Signal strength remained usable.", "Signal strength dropped below 0.15."),
        ),
        ConstraintResult(
            name="cpu_load <= 0.95",
            passed=max_cpu <= 0.95,
            current_value=cpu_values[-1],
            worst_value=max_cpu,
            threshold=0.95,
            message=_message(max_cpu <= 0.95, "CPU load remained within limit.", "CPU load exceeded 0.95."),
        ),
        ConstraintResult(
            name="safe_mode_reachable == True",
            passed=safe_mode_reachable,
            current_value=1.0 if safe_mode_reachable else 0.0,
            worst_value=1.0 if safe_mode_reachable else 0.0,
            threshold=1.0,
            message=_message(safe_mode_reachable, "Safe mode remains reachable.", "Safe mode may not be reachable under this run."),
        ),
    ]


def verdict_from_constraints(results: List[ConstraintResult]) -> str:
    return "PASS" if all(result.passed for result in results) else "FAIL"


def _metric(point: Dict[str, Any], subsystem: str, metric: str, default: float) -> float:
    value = point.get("subsystems", {}).get(subsystem, {}).get(metric, default)
    return float(value)


def _message(passed: bool, ok: str, failed: str) -> str:
    return ok if passed else failed
