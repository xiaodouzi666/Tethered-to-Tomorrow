from __future__ import annotations

import math
import random
import uuid
from typing import Any, Dict, List, Optional, Set

from pi_probe.probe.state import ALLOWED_COMMANDS, SpacecraftState
from pi_probe.twin.constraints import evaluate_constraints, verdict_from_constraints
from pi_probe.twin.environment import apply_environment as apply_environment_config
from pi_probe.twin.faults import apply_faults, resolve_fault_context, unknown_fault_categories
from pi_probe.twin.schemas import ConstraintResult, EnvironmentConfig, FaultSpec, PlanStep, RepairTraceStep, TwinRunRequest, TwinRunResponse


class TwinEngine:
    def __init__(self, base_state: SpacecraftState, assembly_context: Optional[Dict[str, Any]] = None):
        self.base_state = base_state.clone_for_baseline()
        self.state = base_state.clone_for_baseline()
        self.assembly_context = assembly_context or {}
        self.sim_t = 0.0
        self.trajectory: List[Dict[str, Any]] = []
        self.repair_trace: List[RepairTraceStep] = []
        self._structured_fault_systems: Set[str] = set()
        self._rng: random.Random | None = None

    def apply_environment(self, env: EnvironmentConfig) -> None:
        apply_environment_config(self.state, env)

    def apply_faults(self, faults: List[FaultSpec]) -> None:
        apply_faults(self.state, faults, self.sim_t)

    def apply_action(self, step: PlanStep) -> None:
        action = step.action.upper().strip()
        if action not in ALLOWED_COMMANDS:
            raise ValueError(f"Command '{action}' not in allowed whitelist")
        result = self.state.apply_command(action, step.params, source="twin-simulation")
        trace = result.get("repair_trace")
        if isinstance(trace, dict):
            trace = {**trace, "step_index": len(self.repair_trace)}
            self.repair_trace.append(RepairTraceStep(**trace))

    def step(self, dt: float, req: TwinRunRequest, fault_context: Dict[str, Any]) -> None:
        self.state.update(
            dt,
            fault_context=fault_context,
            stochastic=req.stochastic,
            rng=self._rng,
        )
        self.sim_t = round(self.sim_t + dt, 6)
        self.trajectory.append(self._trajectory_point(self.sim_t))

    def run(self, req: TwinRunRequest) -> TwinRunResponse:
        self.state = self.base_state.clone_for_baseline()
        self.sim_t = 0.0
        self.trajectory = []
        self.repair_trace = []
        self._structured_fault_systems = set()
        self._rng = random.Random(req.rng_seed) if req.rng_seed is not None else None

        self.apply_environment(req.environment)
        self.trajectory.append(self._trajectory_point(self.sim_t))

        executed_actions: Set[int] = set()
        total_steps = max(1, math.ceil(req.horizon_sec / req.dt))
        for _ in range(total_steps):
            self.apply_faults(req.faults)
            self._apply_due_actions(req.actions, executed_actions)
            fault_context = _merge_assembly_context(
                resolve_fault_context(self.state, self.sim_t),
                self.assembly_context,
            )
            self.step(req.dt, req, fault_context)
            if req.stop_on_violation:
                checks = evaluate_constraints(self.trajectory)
                if verdict_from_constraints(checks) == "FAIL":
                    break

        constraints = evaluate_constraints(self.trajectory)
        verdict = verdict_from_constraints(constraints)
        risk_score = _risk_score(constraints)
        final_snapshot = self.state.snapshot()
        unknown_categories = unknown_fault_categories(req.faults)
        explanation = _explanation(verdict, risk_score, constraints, unknown_categories)

        return TwinRunResponse(
            run_id=f"twin-{uuid.uuid4().hex[:12]}",
            verdict=verdict,
            risk_score=risk_score,
            final_mode=final_snapshot["mode"],
            constraints=constraints,
            trajectory=self.trajectory,
            final_snapshot=final_snapshot,
            explanation=explanation,
            fault_layers=final_snapshot.get("fault_layers", {}),
            repair_trace=self.repair_trace,
        )

    def _apply_due_actions(self, actions: List[PlanStep], executed_actions: Set[int]) -> None:
        indexed_actions = sorted(enumerate(actions), key=lambda item: (item[1].at_t, item[0]))
        for index, step in indexed_actions:
            if index not in executed_actions and self.sim_t >= step.at_t:
                self.apply_action(step)
                executed_actions.add(index)

    def _trajectory_point(self, sim_t: float) -> Dict[str, Any]:
        snapshot = self.state.snapshot()
        return {
            "sim_t": round(sim_t, 3),
            "seq": snapshot["seq"],
            "mode": snapshot["mode"],
            "active_fault": snapshot["active_fault"],
            "primary_fault": snapshot.get("primary_fault", snapshot["active_fault"]),
            "active_faults": snapshot.get("active_faults", []),
            "subsystems": snapshot["subsystems"],
            "last_command": snapshot.get("last_command"),
            "fault_layers": snapshot.get("fault_layers", {}),
        }


def _risk_score(results: List[ConstraintResult]) -> float:
    if not results:
        return 100.0
    failed_penalty = sum(1 for result in results if not result.passed) / len(results)
    margin_penalty = sum(_constraint_margin(result) for result in results) / len(results)
    normalized = max(0.0, min(1.0, failed_penalty + 0.25 * margin_penalty))
    return round(normalized * 100.0, 1)


def _merge_assembly_context(fault_context: Dict[str, Any], assembly_context: Dict[str, Any]) -> Dict[str, Any]:
    if not assembly_context:
        return fault_context
    merged = dict(fault_context)
    effective = dict(merged.get("effective", {}))
    for key, value in dict(assembly_context).items():
        if key in {"assembly_validation_ok", "assembly_digest"}:
            continue
        if key in {"radiator_efficiency_multiplier", "battery_health_factor", "sun_exposure_multiplier"}:
            effective[key] = min(float(effective.get(key, 1.0)), float(value))
        elif key in {
            "antenna_alignment_error_deg",
            "packet_loss_floor",
            "cpu_load_floor",
            "memory_growth_mb",
            "sensor_readout_bias",
        }:
            effective[key] = max(float(effective.get(key, 0.0)), float(value))
        elif key in {"thermal_controller_stuck", "transceiver_softlock", "using_backup_sensor"}:
            effective[key] = bool(effective.get(key, False)) or bool(value)
        elif key == "load_w_add":
            effective[key] = float(effective.get(key, 0.0)) + float(value)
        else:
            effective[key] = value
    merged["effective"] = effective
    merged["assembly"] = {
        "validation_ok": bool(assembly_context.get("assembly_validation_ok", True)),
        "digest": str(assembly_context.get("assembly_digest", "")),
    }
    return merged


def _constraint_margin(result: ConstraintResult) -> float:
    if result.threshold in (None, 0) or result.worst_value is None:
        return 0.0 if result.passed else 1.0
    name = result.name
    worst = result.worst_value
    threshold = result.threshold
    if "<=" in name:
        return max(0.0, (worst - threshold) / abs(threshold))
    if ">=" in name:
        return max(0.0, (threshold - worst) / abs(threshold))
    return 0.0 if result.passed else 1.0


def _explanation(
    verdict: str,
    risk_score: float,
    constraints: List[ConstraintResult],
    unknown_categories: List[str],
) -> str:
    failed = [constraint.name for constraint in constraints if not constraint.passed]
    parts = [f"Twin verdict {verdict} with risk {risk_score:.1f}/100."]
    if failed:
        parts.append("Failed constraints: " + ", ".join(failed) + ".")
    else:
        parts.append("All configured constraints passed.")
    if unknown_categories:
        parts.append("Ignored unknown fault categories: " + ", ".join(unknown_categories) + ".")
    return " ".join(parts)
