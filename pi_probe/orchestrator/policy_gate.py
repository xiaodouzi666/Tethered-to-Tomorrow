from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Optional, Set

from pi_probe.orchestrator.schemas import (
    ExecutionMode,
    PolicyGateResult,
    ReviewMode,
)
from pi_probe.twin.schemas import BaselineMeta, TwinComparePlanResult, TwinCompareResponse

AUTO_REVIEW_RISK_THRESHOLD = 20.0
AUTO_STEP_RISK_THRESHOLD = 10.0
BASELINE_STALE_AFTER_SEQ_DELTA = 120
AUTO_BLOCKING_HIGH_RISK = {
    "REBOOT_COMPUTER",
    "EXIT_SAFE_MODE",
    "RESTART_COMMS",
    "SWITCH_TO_BACKUP_THRUSTER",
    "ENABLE_THRUSTER_HEATERS",
    "RESTORE_HEATER_POWER",
    "RELOCATE_FDS_CODE",
}


def evaluate_policy(
    *,
    baseline: BaselineMeta,
    twin_compare: TwinCompareResponse,
    plan_bundle: Dict[str, Any],
    selected_plan_id: Optional[str],
    review_mode: ReviewMode,
    execution_mode: ExecutionMode,
    allowed_commands: Iterable[str],
    high_risk_commands: Iterable[str],
    live_snapshot: Optional[Dict[str, Any]] = None,
) -> PolicyGateResult:
    allowed_set = {str(item).upper() for item in allowed_commands}
    high_risk_set = {str(item).upper() for item in high_risk_commands} | AUTO_BLOCKING_HIGH_RISK
    plan_id = selected_plan_id or twin_compare.best_plan_id
    result = _result_by_id(twin_compare, plan_id)
    actions = _plan_actions(plan_bundle, plan_id)
    baseline_status = baseline_status_from_snapshot(baseline, live_snapshot)

    reasons = []
    blocking = []

    if baseline_status != "fresh":
        blocking.append(f"baseline_{baseline_status}")
    if result is None:
        blocking.append("selected_plan_missing")
    elif result.verdict != "PASS":
        blocking.append("selected_plan_failed_twin_constraints")

    unknown_actions = [action for action in actions if action not in allowed_set]
    if unknown_actions:
        blocking.append(f"non_whitelisted_actions:{','.join(unknown_actions)}")

    high_risk_actions = [action for action in actions if action in high_risk_set]
    if high_risk_actions:
        reasons.append(f"High-risk action(s) require human control: {', '.join(high_risk_actions)}.")

    risk_score = result.risk_score if result else 100.0
    has_trace = bool(result and result.repair_trace)
    if not has_trace:
        reasons.append("No repair trace is available; automatic progression is disabled.")

    can_auto_review = (
        not blocking
        and risk_score <= AUTO_REVIEW_RISK_THRESHOLD
        and has_trace
    )
    can_auto_step = (
        can_auto_review
        and risk_score <= AUTO_STEP_RISK_THRESHOLD
        and not high_risk_actions
    )

    effective_review = review_mode
    if review_mode == ReviewMode.AUTO and not can_auto_review:
        effective_review = ReviewMode.ASSISTED
        reasons.append("Auto review downgraded to assisted by policy gate.")

    effective_execution = execution_mode
    if execution_mode == ExecutionMode.AUTO_STEP and not can_auto_step:
        effective_execution = ExecutionMode.MANUAL_STEP
        reasons.append("Auto step execution downgraded to manual_step by policy gate.")
    if execution_mode == ExecutionMode.MANUAL_PLAN and high_risk_actions:
        effective_execution = ExecutionMode.MANUAL_STEP
        reasons.append("Manual plan execution downgraded to stepwise review for high-risk action(s).")

    if blocking:
        level = "manual_only"
        allowed = False
    elif can_auto_step and effective_execution == ExecutionMode.AUTO_STEP:
        level = "auto_allowed"
        allowed = True
    elif can_auto_review or effective_review in {ReviewMode.ASSISTED, ReviewMode.AUTO}:
        level = "assisted_allowed"
        allowed = True
    else:
        level = "manual_only"
        allowed = True

    if not reasons and allowed:
        reasons.append("Selected plan is policy-gated for dry-run review.")

    return PolicyGateResult(
        allowed=allowed,
        level=level,
        baseline_status=baseline_status,
        requested_review_mode=review_mode,
        effective_review_mode=effective_review,
        requested_execution_mode=execution_mode,
        effective_execution_mode=effective_execution,
        can_auto_review=can_auto_review,
        can_auto_step=can_auto_step,
        reasons=reasons,
        blocking_conditions=blocking,
        requires_reanalysis=baseline_status in {"stale", "expired", "invalidated"},
    )


def baseline_status_from_snapshot(
    baseline: BaselineMeta,
    live_snapshot: Optional[Dict[str, Any]],
) -> str:
    if time.time() > baseline.expires_at:
        return "expired"
    if not live_snapshot:
        return "fresh"
    if live_snapshot.get("active_fault") != baseline.captured_fault:
        return "invalidated"
    change_version = live_snapshot.get("change_version")
    if isinstance(change_version, int) and change_version != baseline.captured_change_version:
        return "invalidated"
    seq = live_snapshot.get("seq")
    if isinstance(seq, int) and seq - baseline.captured_seq > BASELINE_STALE_AFTER_SEQ_DELTA:
        return "stale"
    return "fresh"


def _result_by_id(compare: TwinCompareResponse, plan_id: str) -> Optional[TwinComparePlanResult]:
    for result in compare.results:
        if result.plan_id == plan_id:
            return result
    return None


def _plan_actions(plan_bundle: Dict[str, Any], plan_id: str) -> list[str]:
    for plan in plan_bundle.get("plans", []):
        if not isinstance(plan, dict) or str(plan.get("id")) != plan_id:
            continue
        actions = []
        for step in plan.get("actions", []):
            if isinstance(step, dict) and step.get("action"):
                actions.append(str(step["action"]).upper().strip())
        return actions
    return []
