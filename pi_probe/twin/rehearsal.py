from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from pi_probe.probe.state import ALLOWED_COMMANDS, SpacecraftState
from pi_probe.twin.augmentation import augment_telemetry_snapshot, build_augmented_scenario
from pi_probe.twin.constraints import evaluate_constraints
from pi_probe.twin.engine import TwinEngine
from pi_probe.twin.planner import generate_rule_candidate_plans
from pi_probe.twin.schemas import EnvironmentConfig, FaultSpec, PlanStep, TwinRunRequest


class RehearsalStore:
    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def generate(self, profile: str, difficulty: str, mission_goal: str = "") -> Dict[str, Any]:
        scenario = build_augmented_scenario(profile, difficulty=difficulty)
        constraints = [
            "temp_c <= 85",
            "battery_voltage >= 10.5",
            "packet_loss <= 0.60",
            "signal_strength >= 0.15",
            "cpu_load <= 0.95",
            "safe_mode_reachable == True",
        ]
        return {
            "ok": True,
            "environment": scenario["environment"],
            "hidden_faults": scenario["faults"],
            "mission_goal": mission_goal or _mission_goal(scenario["profile"], difficulty),
            "constraints": constraints,
            "difficulty": difficulty,
            "profile": scenario["profile"],
            "augmentation": scenario["augmentation"],
        }

    def start(self, generated: Dict[str, Any], base_state: Optional[SpacecraftState] = None) -> Dict[str, Any]:
        session_id = f"rehearsal-{uuid.uuid4().hex[:12]}"
        state = (base_state or SpacecraftState()).clone()
        environment = EnvironmentConfig(**generated["environment"])
        hidden_faults = [FaultSpec(**fault) for fault in generated["hidden_faults"]]

        engine = TwinEngine(state)
        preview = engine.run(TwinRunRequest(
            from_snapshot="latest",
            environment=environment,
            faults=hidden_faults,
            actions=[],
            horizon_sec=1,
            dt=1,
            stochastic=False,
        ))
        visible_telemetry = augment_telemetry_snapshot(
            preview.trajectory[0],
            noise=0.015,
            drift=0.0,
            missing_rate=0.0,
            delay_events=False,
            packet_jitter=0.01,
        )
        hidden_context = {
            "environment": generated["environment"],
            "hidden_faults": generated["hidden_faults"],
            "constraints": generated["constraints"],
            "difficulty": generated["difficulty"],
            "profile": generated["profile"],
            "mission_goal": generated["mission_goal"],
        }
        self.sessions[session_id] = {
            "id": session_id,
            "created_ts": time.time(),
            "base_state": state.to_internal_state(),
            "hidden_context": hidden_context,
            "actions_taken": [],
            "initial_twin_state": preview.trajectory[0],
            "visible_telemetry": visible_telemetry,
            "last_report": None,
        }
        return {
            "ok": True,
            "id": session_id,
            "initial_twin_state": preview.trajectory[0],
            "visible_telemetry": visible_telemetry,
            "hidden_scoring_context": {
                "stored_server_side": True,
                "difficulty": generated["difficulty"],
                "profile": generated["profile"],
                "constraint_count": len(generated["constraints"]),
            },
        }

    def record_action(self, session_id: str, action: str, params: Optional[Dict[str, Any]] = None, at_t: Optional[float] = None) -> Dict[str, Any]:
        session = self._get(session_id)
        normalized = action.upper().strip()
        if normalized not in ALLOWED_COMMANDS:
            raise ValueError(f"Command '{action}' not in allowed whitelist")
        entry = {
            "action": normalized,
            "params": params or {},
            "at_t": at_t if at_t is not None else len(session["actions_taken"]) * 10.0,
            "recorded_ts": time.time(),
        }
        session["actions_taken"].append(entry)
        return {"ok": True, "id": session_id, "action": entry}

    def report(self, session_id: str) -> Dict[str, Any]:
        session = self._get(session_id)
        hidden = session["hidden_context"]
        base_state = SpacecraftState.from_internal_state(session["base_state"])
        actions = [PlanStep(**action) for action in session["actions_taken"]]
        run = TwinEngine(base_state).run(TwinRunRequest(
            from_snapshot="latest",
            environment=EnvironmentConfig(**hidden["environment"]),
            faults=[FaultSpec(**fault) for fault in hidden["hidden_faults"]],
            actions=actions,
            horizon_sec=300,
            dt=1,
            stochastic=False,
        ))
        constraints = [constraint.model_dump() if hasattr(constraint, "model_dump") else constraint.dict() for constraint in evaluate_constraints(run.trajectory)]
        violations = [constraint for constraint in constraints if not constraint.get("passed")]
        best_alternative = _best_alternative(base_state, hidden)
        score = _score(run.risk_score, violations, len(actions), best_alternative)
        report = {
            "ok": True,
            "id": session_id,
            "score": score,
            "actions_taken": session["actions_taken"],
            "constraint_violations": violations,
            "best_alternative": best_alternative,
            "debrief": _debrief(score, run.verdict, violations, best_alternative),
            "final_snapshot": run.final_snapshot,
            "difficulty": hidden["difficulty"],
            "mission_goal": hidden["mission_goal"],
        }
        session["last_report"] = report
        return report

    def _get(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            raise KeyError(session_id)
        return self.sessions[session_id]


def _best_alternative(base_state: SpacecraftState, hidden: Dict[str, Any]) -> Dict[str, Any]:
    planner = generate_rule_candidate_plans(base_state.snapshot())
    candidates = []
    for plan in planner["plans"]:
        run = TwinEngine(base_state).run(TwinRunRequest(
            from_snapshot="latest",
            environment=EnvironmentConfig(**hidden["environment"]),
            faults=[FaultSpec(**fault) for fault in hidden["hidden_faults"]],
            actions=[PlanStep(**action) for action in plan.get("actions", [])],
            horizon_sec=300,
            dt=1,
            stochastic=False,
        ))
        candidates.append({
            "plan_id": plan["id"],
            "label": plan.get("label", plan["id"]),
            "risk_score": run.risk_score,
            "verdict": run.verdict,
            "actions": plan.get("actions", []),
        })
    return min(candidates, key=lambda item: (item["verdict"] != "PASS", item["risk_score"])) if candidates else {}


def _score(risk_score: float, violations: List[Dict[str, Any]], action_count: int, best_alternative: Dict[str, Any]) -> Dict[str, Any]:
    raw = 100.0 - risk_score - len(violations) * 8.0 - max(0, action_count - 4) * 3.0
    if best_alternative and best_alternative.get("verdict") == "PASS" and risk_score > best_alternative.get("risk_score", 100.0) + 20:
        raw -= 8.0
    return {
        "total": round(max(0.0, min(100.0, raw)), 1),
        "risk_component": round(max(0.0, 100.0 - risk_score), 1),
        "constraint_penalty": len(violations) * 8,
        "action_efficiency_penalty": max(0, action_count - 4) * 3,
    }


def _debrief(score: Dict[str, Any], verdict: str, violations: List[Dict[str, Any]], best_alternative: Dict[str, Any]) -> List[str]:
    lines = [f"Final Twin verdict: {verdict}. Score: {score['total']}/100."]
    if violations:
        lines.append("Constraint violations: " + ", ".join(item.get("name", "constraint") for item in violations[:3]) + ".")
    else:
        lines.append("No configured constraints were violated.")
    if best_alternative:
        lines.append(f"Best alternative: {best_alternative.get('label')} at risk {best_alternative.get('risk_score')}/100.")
    return lines


def _mission_goal(profile: str, difficulty: str) -> str:
    if profile == "thermal":
        return f"{difficulty.title()} thermal recovery: preserve temperature margin while minimizing payload loss."
    if profile == "comms":
        return f"{difficulty.title()} comms recovery: restore usable command link without unsafe resets."
    if profile == "power":
        return f"{difficulty.title()} power recovery: avoid deep discharge and preserve core operations."
    if profile == "sensor":
        return f"{difficulty.title()} sensor recovery: identify unreliable sensing and restore trustworthy telemetry."
    return f"{difficulty.title()} mission recovery: keep constraints inside limits with minimum mission loss."
