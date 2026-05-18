from __future__ import annotations

from typing import Any, Dict, Iterable

from pi_probe.helm.strategy_normalizer import normalize_plan_bundle, normalize_strategy_labels
from pi_probe.twin.planner import generate_rule_candidate_plans


def propose_candidate_plans(
    *,
    snapshot: Dict[str, Any],
    diagnosis: Dict[str, Any],
    agents: Any,
    allowed_commands: Iterable[str],
) -> Dict[str, Any]:
    dataset_strategy_bundle = _plans_from_dataset_strategy_labels(diagnosis)
    if dataset_strategy_bundle.get("plans"):
        normalized = normalize_plan_bundle(dataset_strategy_bundle, allowed_commands)
        if normalized.get("plans"):
            fallback = generate_rule_candidate_plans(snapshot)
            fallback_normalized = normalize_plan_bundle(fallback, allowed_commands)
            existing_ids = {plan.get("id") for plan in normalized.get("plans", [])}
            normalized["plans"].extend([
                plan for plan in fallback_normalized.get("plans", [])
                if plan.get("id") not in existing_ids
            ][: max(0, 3 - len(normalized.get("plans", [])))])
            normalized["diagnosis_reference"] = {
                "risk_level": diagnosis.get("risk_level"),
                "fault_summary": diagnosis.get("fault_summary", []),
                "recommended_strategy_labels": diagnosis.get("recommended_strategy_labels", []),
            }
            return normalized

    try:
        plan_bundle = agents.generate_candidate_plans(snapshot)
    except Exception as exc:
        plan_bundle = generate_rule_candidate_plans(snapshot)
        plan_bundle["llm_fallback_reason"] = str(exc)

    normalized = normalize_plan_bundle(plan_bundle, allowed_commands)
    if len(normalized.get("plans", [])) < 2:
        fallback = generate_rule_candidate_plans(snapshot)
        fallback["llm_fallback_reason"] = "Helm normalizer found too few executable plans."
        normalized = normalize_plan_bundle(fallback, allowed_commands)
    normalized["diagnosis_reference"] = {
        "risk_level": diagnosis.get("risk_level"),
        "fault_summary": diagnosis.get("fault_summary", []),
    }
    return normalized


def _plans_from_dataset_strategy_labels(diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    labels = diagnosis.get("recommended_strategy_labels")
    if not isinstance(labels, list) or not labels:
        return {"plans": []}
    labels = normalize_strategy_labels(labels, source_payload=diagnosis)
    steps = []
    for index, label in enumerate(labels):
        if not isinstance(label, str) or not label.strip():
            continue
        steps.append({"action": label.upper().strip(), "params": {}, "at_t": float(index * 8)})
    if not steps:
        return {"plans": []}
    return {
        "agent": "E4BDatasetStrategyPlanner",
        "source": "e4b-dataset-labels",
        "diagnosis_reference": {
            "risk_level": diagnosis.get("risk_level"),
            "fault_summary": diagnosis.get("fault_summary", []),
            "raw_recommended_strategy_labels": diagnosis.get("raw_recommended_strategy_labels", []),
            "recommended_strategy_labels": labels,
        },
        "plans": [
            {
                "id": "e4b-strategy-a",
                "label": "E4B strategy",
                "actions": steps,
                "rationale": "Canonicalized from E4B fine-tuned recommended_strategy_labels.",
                "llm_annotation": {
                    "root_cause_hypothesis": diagnosis.get("root_cause_hypothesis"),
                    "strategy_rationale": diagnosis.get("strategy_rationale"),
                    "remaining_root_causes_after_strategy": diagnosis.get("remaining_root_causes_after_strategy", []),
                },
            }
        ],
    }
