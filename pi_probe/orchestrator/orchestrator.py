from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from pi_probe.orchestrator.execution import (
    create_execution_ticket,
    dry_run_execute_next_step,
    dry_run_execute_plan,
    execute_next_step_live,
    execute_plan_live,
)
from pi_probe.orchestrator.graph_builder import build_graph_bundle
from pi_probe.orchestrator.policy_gate import evaluate_policy
from pi_probe.orchestrator.reporting import build_debrief
from pi_probe.orchestrator.schemas import (
    AbortSessionRequest,
    ApproveSessionRequest,
    OrchestratorSession,
    OrchestratorStartRequest,
    PolicyGateResult,
    RejectSessionRequest,
    SessionStatus,
)
from pi_probe.orchestrator.session_store import OrchestratorSessionStore
from pi_probe.probe.state import SpacecraftState
from pi_probe.twin.baseline_store import FrozenBaseline
from pi_probe.twin.schemas import (
    BaselineMeta,
    EnvironmentConfig,
    TwinCompareRequest,
    TwinCompareResponse,
    TwinPlanCandidate,
)


class RecoveryOrchestrator:
    def __init__(
        self,
        *,
        agents: Any,
        session_store: OrchestratorSessionStore,
        freeze_current_baseline: Callable[[str], FrozenBaseline],
        baseline_meta: Callable[[FrozenBaseline], BaselineMeta],
        environment_from_state: Callable[[SpacecraftState], EnvironmentConfig],
        run_twin_compare_from_baseline: Callable[[FrozenBaseline, TwinCompareRequest], TwinCompareResponse],
        current_snapshot: Callable[[], Dict[str, Any]],
        allowed_commands: List[str],
        high_risk_commands: List[str],
        helm_runtime: Any = None,
        live_execution_enabled: bool = False,
        command_executor: Optional[Callable[[str, Dict[str, Any], str], Dict[str, Any]]] = None,
    ):
        self.agents = agents
        self.session_store = session_store
        self.freeze_current_baseline = freeze_current_baseline
        self.baseline_meta = baseline_meta
        self.environment_from_state = environment_from_state
        self.run_twin_compare_from_baseline = run_twin_compare_from_baseline
        self.current_snapshot = current_snapshot
        self.allowed_commands = allowed_commands
        self.high_risk_commands = high_risk_commands
        self.helm_runtime = helm_runtime
        self.live_execution_enabled = live_execution_enabled
        self.command_executor = command_executor

    def start_live(self, req: OrchestratorStartRequest) -> OrchestratorSession:
        baseline = self.freeze_current_baseline(req.reason)
        baseline_meta = self.baseline_meta(baseline)
        snapshot = baseline.snapshot
        environment = req.environment_overrides or self.environment_from_state(baseline.state)

        is_helm = str(req.brain_mode) == "BrainMode.GEMMA_HELM" or str(req.brain_mode) == "gemma_helm"
        helm_monitor = None
        if is_helm and self.helm_runtime:
            helm_monitor = self.helm_runtime.monitor_snapshot(snapshot, snapshot.get("events", []))
            diagnosis = self.helm_runtime.diagnose_current_state(
                snapshot=snapshot,
                fault_layers=snapshot.get("fault_layers", {}),
                recent_events=snapshot.get("events", []),
                reason=req.reason,
            )
            plan_bundle = self.helm_runtime.propose_candidate_plans(snapshot, diagnosis)
        else:
            diagnosis = self.agents.diagnose(snapshot, reason=req.reason)
            plan_bundle = self.agents.generate_candidate_plans(snapshot)
        plans = _plans_from_bundle(plan_bundle)
        if len(plans) < 2:
            raise ValueError("Recovery planner must return at least two candidate plans.")

        compare_req = TwinCompareRequest(
            from_snapshot="latest",
            environment=environment,
            faults=req.faults,
            plans=plans[:3],
            horizon_sec=req.horizon_sec,
            dt=req.dt,
            stochastic=req.stochastic,
        )
        twin_compare = self.run_twin_compare_from_baseline(baseline, compare_req)
        best_result = _result_by_id(twin_compare, twin_compare.best_plan_id)

        explanation: Optional[Dict[str, Any]] = None
        if req.include_explanation and best_result is not None:
            explanation = self.agents.explain_twin_verdict(snapshot, _model_dump(best_result))

        policy = self._evaluate_policy(
            baseline=baseline_meta,
            twin_compare=twin_compare,
            plan_bundle=plan_bundle,
            selected_plan_id=twin_compare.best_plan_id,
            review_mode=req.review_mode,
            execution_mode=req.execution_mode,
            live_snapshot=snapshot,
        )
        recommended_plan_id = twin_compare.best_plan_id
        helm_review = None
        operator_question = None
        helm_context = None
        if is_helm and self.helm_runtime:
            helm_review = self.helm_runtime.review_twin_compare(
                snapshot=snapshot,
                twin_compare=twin_compare,
                plan_bundle=plan_bundle,
                policy_result=policy,
            )
            if helm_review.recommended_plan_id:
                recommended_plan_id = helm_review.recommended_plan_id
                policy = self._evaluate_policy(
                    baseline=baseline_meta,
                    twin_compare=twin_compare,
                    plan_bundle=plan_bundle,
                    selected_plan_id=recommended_plan_id,
                    review_mode=req.review_mode,
                    execution_mode=req.execution_mode,
                    live_snapshot=snapshot,
                )
            operator_question = self.helm_runtime.ask_operator_question(
                review_mode=str(req.review_mode.value if hasattr(req.review_mode, "value") else req.review_mode),
                recommended_plan_id=recommended_plan_id,
                helm_review=helm_review,
                policy_result=policy,
            )
            helm_context = {
                "baseline_id": baseline_meta.baseline_id,
                "snapshot_seq": int(snapshot.get("seq", 0)),
                "monitor": _model_dump(helm_monitor),
                "diagnosis_summary": {
                    "fault_summary": diagnosis.get("fault_summary", []),
                    "risk_level": diagnosis.get("risk_level"),
                },
                "plan_summary": {
                    "plan_count": len(plan_bundle.get("plans", [])),
                    "recommended_plan_id": recommended_plan_id,
                },
                "compare_summary": {
                    "compare_id": twin_compare.compare_id,
                    "best_plan_id": twin_compare.best_plan_id,
                    "verdict": best_result.verdict if best_result else "UNKNOWN",
                    "risk_score": best_result.risk_score if best_result else 100.0,
                },
            }
        now = time.time()
        session = OrchestratorSession(
            session_id=f"orch-{uuid.uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            status=SessionStatus.WAITING_APPROVAL,
            brain_mode=req.brain_mode,
            review_mode=req.review_mode,
            execution_mode=req.execution_mode,
            baseline=baseline_meta,
            snapshot_meta={
                "probe_id": snapshot.get("probe_id"),
                "seq": snapshot.get("seq"),
                "mode": snapshot.get("mode"),
                "active_fault": snapshot.get("active_fault"),
                "active_faults": snapshot.get("active_faults", []),
                "change_version": snapshot.get("change_version"),
                "sim_elapsed_s": snapshot.get("sim_elapsed_s"),
                "environment": _model_dump(environment),
            },
            diagnosis=diagnosis,
            plan_bundle=plan_bundle,
            twin_compare=twin_compare,
            selected_plan_id=recommended_plan_id,
            recommended_plan_id=recommended_plan_id,
            review_result={
                "status": "pending",
                "recommended_plan_id": recommended_plan_id,
                "source": "e4b_helm_plus_policy_gate" if is_helm else "e4b_plus_policy_gate",
            },
            policy_result=policy,
            explanation=explanation,
            fault_layers=snapshot.get("fault_layers", {}),
            dry_run=True,
            helm_monitor=helm_monitor,
            helm_review=helm_review,
            operator_question=operator_question,
            helm_context=helm_context,
        )
        session.graph_bundle = build_graph_bundle(session)
        session = self.session_store.create(session)
        return self._auto_progress_if_allowed(session, approved_by="helm-auto-start")

    def get(self, session_id: str) -> OrchestratorSession:
        session = self.session_store.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session

    def approve(self, session_id: str, req: ApproveSessionRequest) -> OrchestratorSession:
        session = self.get(session_id)
        plan_id = req.plan_id or session.recommended_plan_id
        if not plan_id:
            raise ValueError("No plan id is available for approval.")
        session.selected_plan_id = plan_id
        session.policy_result = self._evaluate_policy(
            baseline=session.baseline,
            twin_compare=session.twin_compare,
            plan_bundle=session.plan_bundle,
            selected_plan_id=plan_id,
            review_mode=session.review_mode,
            execution_mode=session.execution_mode,
            live_snapshot=self.current_snapshot(),
        )
        if not session.policy_result.allowed:
            session.review_result = {
                "status": "blocked",
                "plan_id": plan_id,
                "approved_by": req.approved_by,
                "blocking_conditions": session.policy_result.blocking_conditions,
            }
            session.status = SessionStatus.STALE if session.policy_result.requires_reanalysis else SessionStatus.REVIEW_READY
            return self.session_store.save(session)

        session.execution_ticket = create_execution_ticket(
            session,
            plan_id=plan_id,
            approved_by=req.approved_by,
            dry_run=not self._live_execution_allowed_for_session(session, plan_id),
        )
        session.review_result = {
            "status": "approved",
            "plan_id": plan_id,
            "approved_by": req.approved_by,
            "dry_run": session.execution_ticket.dry_run,
            "ticket_id": session.execution_ticket.ticket_id,
        }
        session.dry_run = session.execution_ticket.dry_run
        session.status = SessionStatus.APPROVED
        session.graph_bundle = build_graph_bundle(session)
        return self.session_store.save(session)

    def reject(self, session_id: str, req: RejectSessionRequest) -> OrchestratorSession:
        session = self.get(session_id)
        session.review_result = {
            "status": "rejected",
            "reason": req.reason,
            "plan_id": session.selected_plan_id or session.recommended_plan_id,
        }
        session.status = SessionStatus.ABORTED
        session.debrief_report = build_debrief(session)
        return self.session_store.save(session)

    def execute_step(self, session_id: str) -> OrchestratorSession:
        session = self.get(session_id)
        session.policy_result = self._evaluate_policy(
            baseline=session.baseline,
            twin_compare=session.twin_compare,
            plan_bundle=session.plan_bundle,
            selected_plan_id=session.selected_plan_id,
            review_mode=session.review_mode,
            execution_mode=session.execution_mode,
            live_snapshot=self.current_snapshot(),
        )
        if not session.policy_result.allowed:
            session.status = SessionStatus.STALE if session.policy_result.requires_reanalysis else SessionStatus.REVIEW_READY
            return self.session_store.save(session)
        session.status = SessionStatus.EXECUTING
        if session.execution_ticket and not session.execution_ticket.dry_run and self.command_executor:
            session = execute_next_step_live(
                session,
                live_snapshot=self.current_snapshot(),
                command_executor=self.command_executor,
            )
        else:
            session = dry_run_execute_next_step(session, live_snapshot=self.current_snapshot())
        if session.status == SessionStatus.COMPLETED:
            session.debrief_report = build_debrief(session)
        session.graph_bundle = build_graph_bundle(session)
        return self.session_store.save(session)

    def execute_plan(self, session_id: str) -> OrchestratorSession:
        session = self.get(session_id)
        session.policy_result = self._evaluate_policy(
            baseline=session.baseline,
            twin_compare=session.twin_compare,
            plan_bundle=session.plan_bundle,
            selected_plan_id=session.selected_plan_id,
            review_mode=session.review_mode,
            execution_mode=session.execution_mode,
            live_snapshot=self.current_snapshot(),
        )
        if not session.policy_result.allowed:
            session.status = SessionStatus.STALE if session.policy_result.requires_reanalysis else SessionStatus.REVIEW_READY
            return self.session_store.save(session)
        session.status = SessionStatus.EXECUTING
        if session.execution_ticket and not session.execution_ticket.dry_run and self.command_executor:
            session = execute_plan_live(
                session,
                live_snapshot=self.current_snapshot(),
                command_executor=self.command_executor,
            )
        else:
            session = dry_run_execute_plan(session, live_snapshot=self.current_snapshot())
        if session.status == SessionStatus.COMPLETED:
            session.debrief_report = build_debrief(session)
        session.graph_bundle = build_graph_bundle(session)
        return self.session_store.save(session)

    def abort(self, session_id: str, req: AbortSessionRequest) -> OrchestratorSession:
        session = self.get(session_id)
        session.status = SessionStatus.ABORTED
        session.review_result = {
            "status": "aborted",
            "reason": req.reason,
        }
        session.debrief_report = build_debrief(session)
        return self.session_store.save(session)

    def _auto_progress_if_allowed(self, session: OrchestratorSession, *, approved_by: str) -> OrchestratorSession:
        """Advance a Helm auto session without exposing approval controls.

        Classic/manual sessions still stop at WAITING_APPROVAL. High-risk or
        policy-blocked plans also stop there so the frontend can show HITL
        controls.
        """
        brain_mode = str(session.brain_mode.value if hasattr(session.brain_mode, "value") else session.brain_mode)
        review_mode = str(session.review_mode.value if hasattr(session.review_mode, "value") else session.review_mode)
        execution_mode = str(session.execution_mode.value if hasattr(session.execution_mode, "value") else session.execution_mode)
        if brain_mode != "gemma_helm":
            return session
        if review_mode != "auto" or execution_mode != "auto_step":
            return session
        if not self.live_execution_enabled or not self.command_executor:
            return session
        if not session.policy_result.allowed or not session.policy_result.can_auto_step:
            return session
        if session.policy_result.blocking_conditions:
            return session

        session = self.approve(
            session.session_id,
            ApproveSessionRequest(plan_id=session.recommended_plan_id, approved_by=approved_by),
        )
        if session.execution_ticket and not session.execution_ticket.dry_run:
            session = self.execute_plan(session.session_id)
        return session

    def debrief(self, session_id: str) -> OrchestratorSession:
        session = self.get(session_id)
        session.debrief_report = build_debrief(session)
        return self.session_store.save(session)

    def graph(self, session_id: str) -> OrchestratorSession:
        session = self.get(session_id)
        session.graph_bundle = build_graph_bundle(session)
        return self.session_store.save(session)

    def dialogue(self, session_id: str, req: Any) -> OrchestratorSession:
        session = self.get(session_id)
        if not self.helm_runtime:
            raise ValueError("E4B Helm runtime is not configured.")

        context = {
            "recommended_plan_id": session.recommended_plan_id,
            "why": session.helm_review.why if session.helm_review else None,
        }
        response = self.helm_runtime.response_for_dialogue(req, context)
        from pi_probe.helm.dialogue import dialogue_turn

        session.dialogue_log.append(dialogue_turn(req, response))
        choice = str(req.choice)
        if choice == "approve_recommended_plan":
            self.session_store.save(session)
            return self.approve(session_id, ApproveSessionRequest(plan_id=session.recommended_plan_id, approved_by="helm-dialogue"))
        if choice == "abort":
            self.session_store.save(session)
            return self.abort(session_id, AbortSessionRequest(reason=req.message or "helm_dialogue_abort"))
        if choice == "request_safer_plan":
            safer = _lowest_risk_non_high_risk_plan(session, self.high_risk_commands)
            if safer:
                session.selected_plan_id = safer
                session.recommended_plan_id = safer
                session.review_result = {
                    "status": "safer_plan_selected",
                    "plan_id": safer,
                    "response": response,
                }
        elif choice == "ask_for_more_explanation":
            session.review_result = {
                "status": "explanation_requested",
                "plan_id": session.recommended_plan_id,
                "response": response,
            }
        session.status = SessionStatus.WAITING_APPROVAL
        return self.session_store.save(session)

    def _evaluate_policy(
        self,
        *,
        baseline: BaselineMeta,
        twin_compare: TwinCompareResponse,
        plan_bundle: Dict[str, Any],
        selected_plan_id: Optional[str],
        review_mode: Any,
        execution_mode: Any,
        live_snapshot: Optional[Dict[str, Any]],
    ) -> PolicyGateResult:
        return evaluate_policy(
            baseline=baseline,
            twin_compare=twin_compare,
            plan_bundle=plan_bundle,
            selected_plan_id=selected_plan_id,
            review_mode=review_mode,
            execution_mode=execution_mode,
            allowed_commands=self.allowed_commands,
            high_risk_commands=self.high_risk_commands,
            live_snapshot=live_snapshot,
        )

    def _live_execution_allowed_for_session(self, session: OrchestratorSession, plan_id: str) -> bool:
        if not self.live_execution_enabled:
            return False
        if str(session.brain_mode.value if hasattr(session.brain_mode, "value") else session.brain_mode) != "gemma_helm":
            return False
        if not session.policy_result.can_auto_step and str(session.execution_mode.value if hasattr(session.execution_mode, "value") else session.execution_mode) == "auto_step":
            return False
        high_risk = {str(item).upper() for item in self.high_risk_commands} | {
            "REBOOT_COMPUTER",
            "EXIT_SAFE_MODE",
            "RESTART_COMMS",
            "SWITCH_TO_BACKUP_THRUSTER",
            "ENABLE_THRUSTER_HEATERS",
            "RESTORE_HEATER_POWER",
            "RELOCATE_FDS_CODE",
        }
        for step in _plan_steps_from_bundle(session.plan_bundle, plan_id):
            action = str(step.get("action", "")).upper().strip()
            if action in high_risk:
                return False
        return True


def _plans_from_bundle(plan_bundle: Dict[str, Any]) -> List[TwinPlanCandidate]:
    plans: List[TwinPlanCandidate] = []
    for plan in plan_bundle.get("plans", []):
        if not isinstance(plan, dict) or not plan.get("id"):
            continue
        plans.append(
            TwinPlanCandidate(
                id=str(plan["id"]),
                label=str(plan.get("label", plan["id"])),
                actions=plan.get("actions", []),
            )
        )
    return plans


def _result_by_id(compare: TwinCompareResponse, plan_id: str):
    for result in compare.results:
        if result.plan_id == plan_id:
            return result
    return None


def _plan_steps_from_bundle(plan_bundle: Dict[str, Any], plan_id: str) -> List[Dict[str, Any]]:
    for plan in plan_bundle.get("plans", []):
        if isinstance(plan, dict) and str(plan.get("id")) == str(plan_id):
            return [step for step in plan.get("actions", []) if isinstance(step, dict)]
    return []


def _lowest_risk_non_high_risk_plan(session: OrchestratorSession, high_risk_commands: List[str]) -> Optional[str]:
    high_risk = {str(item).upper() for item in high_risk_commands} | {
        "REBOOT_COMPUTER",
        "EXIT_SAFE_MODE",
        "RESTART_COMMS",
        "SWITCH_TO_BACKUP_THRUSTER",
        "ENABLE_THRUSTER_HEATERS",
        "RESTORE_HEATER_POWER",
        "RELOCATE_FDS_CODE",
    }
    candidates = []
    for result in session.twin_compare.results:
        steps = _plan_steps_from_bundle(session.plan_bundle, result.plan_id)
        if any(str(step.get("action", "")).upper().strip() in high_risk for step in steps):
            continue
        candidates.append(result)
    if not candidates:
        return None
    best = min(candidates, key=lambda result: (result.verdict != "PASS", result.risk_score))
    return best.plan_id


def _model_dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value if isinstance(value, dict) else {}
