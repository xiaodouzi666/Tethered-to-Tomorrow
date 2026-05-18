from __future__ import annotations

from typing import Any, Dict, List, Optional

from pi_probe.helm.schemas import HelmReviewResult
from pi_probe.twin.schemas import TwinCompareResponse


def review_twin_compare(
    *,
    snapshot: Dict[str, Any],
    twin_compare: TwinCompareResponse,
    plan_bundle: Dict[str, Any],
    policy_result: Any,
    agents: Any,
) -> HelmReviewResult:
    best_id = twin_compare.best_plan_id
    best = next((result for result in twin_compare.results if result.plan_id == best_id), None)
    remaining_risks = _remaining_risks(best)
    why = _rule_why(best_id, best, policy_result)
    source = "rules-fallback"

    try:
        if best is not None:
            explanation = agents.explain_twin_verdict(snapshot, _dump(best))
            readable = _read_explanation(explanation)
            if readable:
                why = readable
                source = "e4b-review"
    except Exception as exc:
        remaining_risks.append(f"E4B review unavailable: {exc}")

    return HelmReviewResult(
        recommended_plan_id=best_id,
        confidence=_confidence(best),
        why=why,
        remaining_risks=remaining_risks,
        auto_review_suggested=bool(getattr(policy_result, "can_auto_review", False)),
        operator_question_needed=not bool(getattr(policy_result, "can_auto_step", False)),
        source=source,
    )


def _remaining_risks(best: Any) -> List[str]:
    if best is None:
        return ["No best Twin result was available."]
    risks = []
    for constraint in getattr(best, "constraints", []):
        if not getattr(constraint, "passed", False):
            risks.append(getattr(constraint, "message", getattr(constraint, "name", "constraint failed")))
    if getattr(best, "risk_score", 100.0) > 20:
        risks.append(f"Twin risk score remains high ({getattr(best, 'risk_score', 100.0):.1f}).")
    return risks


def _rule_why(plan_id: str, best: Any, policy_result: Any) -> str:
    if best is None:
        return "Helm could not identify a valid Twin result; operator review is required."
    verdict = getattr(best, "verdict", "UNKNOWN")
    risk = getattr(best, "risk_score", 100.0)
    blockers = getattr(policy_result, "blocking_conditions", [])
    if blockers:
        return f"Plan {plan_id} is the current Twin best, but policy blocks progression: {', '.join(blockers)}."
    return f"Plan {plan_id} is recommended because Twin verdict is {verdict} with risk {risk:.1f}."


def _confidence(best: Any) -> float:
    if best is None:
        return 0.0
    risk = float(getattr(best, "risk_score", 100.0))
    return max(0.0, min(1.0, 1.0 - risk / 100.0))


def _dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value if isinstance(value, dict) else {}


def _read_explanation(value: Dict[str, Any]) -> Optional[str]:
    for key in ("recommended_operator_readout", "summary", "explanation"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item
    nested = value.get("explanation")
    if isinstance(nested, dict):
        return _read_explanation(nested)
    return None
