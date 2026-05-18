from __future__ import annotations

import statistics
import uuid
from typing import Any, Dict, Iterable, List, Optional

from pi_probe.probe.state import HIGH_RISK_COMMANDS
from pi_probe.twin.assembly import build_assembly_context
from pi_probe.twin.baseline_store import FrozenBaseline
from pi_probe.twin.engine import TwinEngine
from pi_probe.twin.schemas import (
    CampaignPlanScore,
    CampaignResponse,
    EnvironmentConfig,
    SimulationCampaignRequest,
    TwinAssemblyState,
    TwinPlanCandidate,
    TwinRunRequest,
    TwinRunResponse,
)


def run_campaign(
    *,
    baseline: FrozenBaseline,
    req: SimulationCampaignRequest,
    session_id: str = "",
    assembly: Optional[TwinAssemblyState] = None,
) -> CampaignResponse:
    environments = req.environment_branches or [EnvironmentConfig()]
    seeds = req.seeds or [1]
    scores: List[CampaignPlanScore] = []
    run_count = 0

    for plan in req.plans:
        runs: List[TwinRunResponse] = []
        for environment in environments:
            for seed in seeds:
                run_req = TwinRunRequest(
                    from_snapshot="baseline",
                    environment=environment,
                    faults=req.faults,
                    actions=plan.actions,
                    horizon_sec=req.horizon_sec,
                    dt=req.dt,
                    stochastic=True,
                    rng_seed=seed,
                )
                runs.append(TwinEngine(
                    baseline.clone_state(),
                    assembly_context=build_assembly_context(assembly),
                ).run(run_req))
                run_count += 1
        scores.append(_score_plan(plan, runs))

    if not scores:
        raise ValueError("Simulation campaign requires at least one candidate plan.")

    best = min(scores, key=_engineering_sort_key)
    return CampaignResponse(
        campaign_id=f"campaign-{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        baseline_id=baseline.baseline_id,
        assembly_id=assembly.assembly_id if assembly else "",
        assembly_version=assembly.version if assembly else 0,
        assembly_digest=assembly.assembly_digest if assembly else "",
        best_plan_id=best.plan_id,
        scores=scores,
        run_count=run_count,
        explanation=(
            f"Best campaign plan is {best.plan_id}: pass rate {best.pass_rate:.0%}, "
            f"worst risk {best.worst_risk_score:.1f}/100."
        ),
        gate_status="pass" if best.verdict == "PASS" and best.pass_rate >= 0.8 else "blocked",
        gate_reason=_campaign_gate_reason(best),
    )


def _campaign_gate_reason(score: CampaignPlanScore) -> str:
    if score.verdict != "PASS":
        return f"Best plan verdict is {score.verdict}; command package generation requires PASS."
    if score.pass_rate < 0.8:
        return f"Best plan pass_rate is {score.pass_rate:.0%}; command package generation requires at least 80%."
    return "Best plan passed package gate."


def _score_plan(plan: TwinPlanCandidate, runs: List[TwinRunResponse]) -> CampaignPlanScore:
    pass_count = sum(1 for run in runs if run.verdict == "PASS")
    risks = [run.risk_score for run in runs] or [100.0]
    high_risk_actions = sorted(
        {
            step.action.upper().strip()
            for step in plan.actions
            if step.action.upper().strip() in HIGH_RISK_COMMANDS
        }
    )
    recovery_values = [
        value
        for value in (_run_recovery_time(run) for run in runs)
        if value is not None
    ]
    pass_rate = pass_count / len(runs) if runs else 0.0
    worst_risk = max(risks)
    return CampaignPlanScore(
        plan_id=plan.id,
        label=plan.label,
        pass_rate=round(pass_rate, 3),
        worst_risk_score=round(worst_risk, 1),
        avg_risk_score=round(statistics.fmean(risks), 1),
        max_temp_c=round(max(_metric_series(runs, "thermal", "temp_c"), default=0.0), 3),
        min_battery_voltage=round(min(_metric_series(runs, "power", "battery_voltage"), default=0.0), 3),
        max_packet_loss=round(max(_metric_series(runs, "comms", "packet_loss"), default=0.0), 3),
        recovery_time_s=round(max(recovery_values), 3) if recovery_values else None,
        command_count=len(plan.actions),
        high_risk_actions=high_risk_actions,
        verdict="PASS" if pass_rate >= 0.8 and worst_risk < 60.0 else "FAIL",
    )


def _engineering_sort_key(score: CampaignPlanScore) -> tuple[bool, float, float, int, float]:
    high_risk_penalty = len(score.high_risk_actions) * 15.0
    recovery_penalty = (score.recovery_time_s or 9999.0) / 100.0
    aggregate = (
        score.worst_risk_score
        + high_risk_penalty
        + score.command_count * 2.0
        + recovery_penalty
        + (1.0 - score.pass_rate) * 100.0
    )
    return (score.verdict != "PASS", aggregate, score.worst_risk_score, score.command_count, -score.pass_rate)


def _metric_series(runs: Iterable[TwinRunResponse], subsystem: str, field: str) -> List[float]:
    values: List[float] = []
    for run in runs:
        for point in run.trajectory:
            subsystems = point.get("subsystems", {})
            if not isinstance(subsystems, dict):
                continue
            source = subsystems.get(subsystem, {})
            if not isinstance(source, dict):
                continue
            value = source.get(field)
            if isinstance(value, (int, float)):
                values.append(float(value))
    return values


def _run_recovery_time(run: TwinRunResponse) -> Optional[float]:
    for point in run.trajectory:
        if point.get("mode") == "FAULT":
            continue
        layers = point.get("fault_layers", {})
        recoverables = layers.get("recoverable_faults", []) if isinstance(layers, dict) else []
        active = [
            item
            for item in recoverables
            if isinstance(item, dict) and str(item.get("status", "active")) == "active"
        ]
        if not active:
            return float(point.get("sim_t", 0.0))
    return None
