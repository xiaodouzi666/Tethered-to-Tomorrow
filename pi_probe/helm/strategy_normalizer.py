from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

STRATEGY_TO_COMMANDS: Dict[str, List[str]] = {
    "SWITCH_POINTING_CONTROL_TO_TCM_BRANCH": ["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"],
    "ENABLE_TCM_THRUSTER_BRANCH": ["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"],
    "SWITCH_TO_BACKUP_ROLL_THRUSTERS": ["ENABLE_THRUSTER_HEATERS", "SWITCH_TO_BACKUP_THRUSTER"],
    "VALIDATE_DORMANT_TCM_THRUSTERS": ["ENABLE_THRUSTER_HEATERS"],
    "ENABLE_DORMANT_ROLL_THRUSTER_HEATERS": ["ENABLE_THRUSTER_HEATERS"],
    "ENABLE_THRUSTER_HEATERS_WITH_POWER_CHECK": ["ENABLE_THRUSTER_HEATERS"],
    "SHUT_DOWN_PRIMARY_ROLL_HEATER": ["SHUT_DOWN_PRIMARY_ROLL_HEATER"],
    "SHUT_DOWN_NONCRITICAL_INSTRUMENT_HEATER": ["SHED_NONESSENTIAL_LOAD"],
    "REALLOCATE_POWER_BUDGET": ["REALLOCATE_POWER_BUDGET"],
    "REALLOCATE_POWER_TO_CRITICAL_SYSTEMS": ["REALLOCATE_POWER_BUDGET", "SHED_NONESSENTIAL_LOAD"],
    "ACCEPT_REDUCED_THERMAL_MARGIN_WITH_MONITORING": ["LOWER_SAMPLING_RATE"],
    "CONTINUE_THERMAL_AND_POWER_MONITORING": ["VERIFY_TELEMETRY_RECOVERY"],
    "MONITOR_AND_ISOLATE_TELEMETRY_PATH": ["ISOLATE_TELEMETRY_PATH"],
    "PREPARE_REDUNDANT_PATH_EVALUATION": ["ISOLATE_TELEMETRY_PATH"],
    "MAINTAIN_OPERATIONS_WHILE_LINK_STABLE": ["VERIFY_TELEMETRY_RECOVERY"],
    "RELOCATE_FDS_CODE_SEGMENTS": ["RELOCATE_FDS_CODE"],
    "UPDATE_FDS_MEMORY_REFERENCES": ["RELOCATE_FDS_CODE"],
    "VERIFY_ENGINEERING_TELEMETRY_RECOVERY": ["VERIFY_TELEMETRY_RECOVERY"],
    "PREPARE_BRANCH_SWITCH_IF_CLOGGING_WORSENS": ["ENABLE_THRUSTER_HEATERS"],
    "RESTORE_HEATER_POWER_SWITCH_STATE": ["RESTORE_HEATER_POWER"],
}

STRATEGY_WHITELIST: Set[str] = set(STRATEGY_TO_COMMANDS)

TCM_STRATEGIES = [
    "ENABLE_TCM_THRUSTER_BRANCH",
    "SWITCH_POINTING_CONTROL_TO_TCM_BRANCH",
    "CONTINUE_THERMAL_AND_POWER_MONITORING",
]

ROLL_BACKUP_STRATEGIES = [
    "SWITCH_TO_BACKUP_ROLL_THRUSTERS",
]

ALIAS_MAP: Dict[str, List[str]] = {
    "RECONFIGURE_POINTING_CONTROL": ["SWITCH_POINTING_CONTROL_TO_TCM_BRANCH"],
    "RECONFIGURE_POINTING_BRANCH": ["ENABLE_TCM_THRUSTER_BRANCH"],
    "SWITCH_TO_TCM_THRUSTERS": TCM_STRATEGIES,
    "THRUSTER BRANCH SWITCH": ["ENABLE_TCM_THRUSTER_BRANCH"],
    "RECONFIGURE POINTING SUBSYSTEM": ["SWITCH_POINTING_CONTROL_TO_TCM_BRANCH"],
    "RECONFIGURE THRUSTER SET FOR ATTITUDE POINTING": [
        "ENABLE_TCM_THRUSTER_BRANCH",
        "SWITCH_POINTING_CONTROL_TO_TCM_BRANCH",
    ],
}


def _context_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "mission_phase",
        "visible_telemetry_summary",
        "fault_layers",
        "constraints",
        "evidence",
        "context",
        "task_summary",
        "fault_summary",
        "likely_causes",
        "uncertainty",
        "root_cause_hypothesis",
        "strategy_rationale",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
    return "\n".join(parts).lower()


def _alias_key(label: str) -> str:
    return " ".join(label.replace("-", "_").strip().upper().split())


def _alias_candidates(label: str, context: str) -> List[str]:
    cleaned = str(label).strip()
    key = _alias_key(cleaned)
    if key == "SWITCH_TO_SECONDARY_THRUSTERS":
        if "tcm" in context or "trajectory correction" in context:
            return TCM_STRATEGIES
        if "roll" in context:
            return ROLL_BACKUP_STRATEGIES
        return [*TCM_STRATEGIES, *ROLL_BACKUP_STRATEGIES]
    return ALIAS_MAP.get(key, [cleaned.upper().strip()])


def normalize_strategy_labels(
    labels: Iterable[Any],
    source_payload: Optional[Dict[str, Any]] = None,
    whitelist: Optional[Set[str]] = None,
) -> List[str]:
    context = _context_text(source_payload or {})
    allowed = whitelist or STRATEGY_WHITELIST
    normalized: List[str] = []
    for label in labels or []:
        candidates = _alias_candidates(str(label), context)
        if allowed:
            candidates = [candidate for candidate in candidates if candidate in allowed]
        for candidate in candidates:
            if candidate not in normalized:
                normalized.append(candidate)
    return normalized


def normalize_model_output(
    model_json: Dict[str, Any],
    source_payload: Optional[Dict[str, Any]] = None,
    whitelist: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    normalized = dict(model_json)
    labels = normalized.get("recommended_strategy_labels")
    if isinstance(labels, list):
        context_payload = dict(normalized)
        if source_payload:
            context_payload.update(source_payload)
        normalized["raw_recommended_strategy_labels"] = list(labels)
        normalized["recommended_strategy_labels"] = normalize_strategy_labels(
            labels,
            source_payload=context_payload,
            whitelist=whitelist or STRATEGY_WHITELIST,
        )
        normalized["strategy_label_normalizer"] = "e4b_strategy_alias_normalizer"
    return normalized


def normalize_plan_bundle(plan_bundle: Dict[str, Any], allowed_commands: Iterable[str]) -> Dict[str, Any]:
    allowed = {str(command).upper().strip() for command in allowed_commands}
    source_payload = {
        "fault_summary": plan_bundle.get("fault_summary"),
        "diagnosis_reference": plan_bundle.get("diagnosis_reference"),
        "context": plan_bundle.get("context"),
    }
    normalized_plans: List[Dict[str, Any]] = []
    for index, plan in enumerate(plan_bundle.get("plans", []), start=1):
        if not isinstance(plan, dict):
            continue
        plan_id = str(plan.get("id") or f"plan-{index}")
        actions = []
        seen_actions = set()
        for step in plan.get("actions", []):
            if not isinstance(step, dict):
                continue
            action = str(step.get("action", "")).upper().strip()
            strategy_candidates = normalize_strategy_labels(
                [action],
                source_payload={**source_payload, "plan": plan},
                whitelist=STRATEGY_WHITELIST,
            )
            mapped_actions = []
            for strategy in strategy_candidates or [action]:
                mapped_actions.extend(STRATEGY_TO_COMMANDS.get(strategy, [strategy]))
            for mapped in mapped_actions:
                if mapped not in allowed:
                    continue
                if mapped in seen_actions:
                    continue
                seen_actions.add(mapped)
                actions.append({
                    "action": mapped,
                    "params": step.get("params", {}) if isinstance(step.get("params", {}), dict) else {},
                    "at_t": float(step.get("at_t", 0.0)) if isinstance(step.get("at_t", 0.0), (int, float)) else 0.0,
                })
        if not actions:
            continue
        normalized_plans.append({
            "id": plan_id,
            "label": str(plan.get("label") or plan_id),
            "actions": actions,
            "rationale": str(plan.get("rationale") or "Rule-normalized candidate plan."),
            "llm_annotation": plan.get("llm_annotation") or {},
        })
    return {
        **plan_bundle,
        "plans": normalized_plans,
        "normalizer": "helm_strategy_normalizer",
    }
