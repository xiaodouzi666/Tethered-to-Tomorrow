from __future__ import annotations

from typing import List

from pi_probe.orchestrator.schemas import DebriefReport, OrchestratorSession


def build_debrief(session: OrchestratorSession) -> DebriefReport:
    selected_plan = session.selected_plan_id or session.recommended_plan_id or ""
    result = next(
        (item for item in session.twin_compare.results if item.plan_id == selected_plan),
        None,
    )
    cleared = []
    remaining = []
    violations: List[str] = []
    if result:
        for trace in result.repair_trace:
            cleared.extend(trace.cleared_faults)
            remaining.extend(trace.remaining_root_causes)
        violations = [check.name for check in result.constraints if not check.passed]

    diagnosis_summary = _diagnosis_summary(session)
    final_outcome = session.status.value
    summary = (
        f"Session {session.session_id} reviewed plan {selected_plan or 'none'} "
        f"against baseline {session.baseline.baseline_id}."
    )
    next_action = "Refresh baseline and reanalyze." if session.policy_result.requires_reanalysis else "Continue operator review."
    if session.status.value == "COMPLETED":
        next_action = "Review remaining root causes before returning to nominal operations."

    return DebriefReport(
        session_id=session.session_id,
        baseline_id=session.baseline.baseline_id,
        primary_fault=session.baseline.captured_fault,
        summary=summary,
        diagnosis_summary=diagnosis_summary,
        selected_plan=selected_plan,
        executed_steps=session.execution_log,
        cleared_faults=sorted(set(cleared)),
        remaining_root_causes=sorted(set(remaining)),
        constraint_violations=violations,
        final_outcome=final_outcome,
        recommended_next_action=next_action,
        llm_debrief="E4B debrief hook is available; this dry-run report is rule generated.",
    )


def _diagnosis_summary(session: OrchestratorSession) -> str:
    diagnosis = session.diagnosis.get("diagnosis")
    if isinstance(diagnosis, dict):
        fault_summary = diagnosis.get("fault_summary")
        if isinstance(fault_summary, list) and fault_summary:
            return "; ".join(str(item) for item in fault_summary[:3])
        uncertainty = diagnosis.get("uncertainty")
        if isinstance(uncertainty, str):
            return uncertainty
    return "No diagnosis summary available."
