from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pi_probe.helm.schemas import (
    BrainMode,
    HelmDialogueTurn,
    HelmMonitorResult,
    HelmOperatorQuestion,
    HelmReviewResult,
    HelmSessionContext,
)
from pi_probe.twin.schemas import (
    BaselineMeta,
    EnvironmentConfig,
    FaultSpec,
    FaultLayerSummary,
    TwinCompareResponse,
)


class ReviewMode(str, Enum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTO = "auto"


class ExecutionMode(str, Enum):
    MANUAL_STEP = "manual_step"
    MANUAL_PLAN = "manual_plan"
    AUTO_STEP = "auto_step"


class SessionStatus(str, Enum):
    IDLE = "IDLE"
    BASELINE_FROZEN = "BASELINE_FROZEN"
    DIAGNOSING = "DIAGNOSING"
    PLANS_GENERATED = "PLANS_GENERATED"
    TWIN_COMPARED = "TWIN_COMPARED"
    REVIEW_READY = "REVIEW_READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    STALE = "STALE"


class OrchestratorStartRequest(BaseModel):
    brain_mode: BrainMode = BrainMode.CLASSIC_PYTHON
    reason: str = "operator_requested_analysis"
    review_mode: ReviewMode = ReviewMode.MANUAL
    execution_mode: ExecutionMode = ExecutionMode.MANUAL_STEP
    include_compare: bool = True
    include_explanation: bool = True
    horizon_sec: int = Field(default=300, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False
    faults: List[FaultSpec] = Field(default_factory=list)
    environment_overrides: Optional[EnvironmentConfig] = None


class PolicyGateResult(BaseModel):
    allowed: bool
    level: str
    baseline_status: str
    requested_review_mode: ReviewMode
    effective_review_mode: ReviewMode
    requested_execution_mode: ExecutionMode
    effective_execution_mode: ExecutionMode
    can_auto_review: bool
    can_auto_step: bool
    reasons: List[str] = Field(default_factory=list)
    blocking_conditions: List[str] = Field(default_factory=list)
    requires_reanalysis: bool = False


class ExecutionTicket(BaseModel):
    ticket_id: str
    session_id: str
    baseline_id: str
    plan_id: str
    plan_digest: str
    approved_by: Optional[str] = None
    issued_at: float
    expires_at: float
    dry_run: bool = True


class StepValidationResult(BaseModel):
    step_index: int
    action: str
    passed: bool
    within_envelope: bool
    deviations: List[Dict[str, Any]] = Field(default_factory=list)
    recommendation: str = "continue"
    expected_frame_t: Optional[float] = None
    note: str = ""


class DebriefReport(BaseModel):
    session_id: str
    baseline_id: str
    primary_fault: str
    summary: str
    diagnosis_summary: str = ""
    selected_plan: str = ""
    executed_steps: List[Dict[str, Any]] = Field(default_factory=list)
    cleared_faults: List[str] = Field(default_factory=list)
    remaining_root_causes: List[str] = Field(default_factory=list)
    constraint_violations: List[str] = Field(default_factory=list)
    final_outcome: str = ""
    recommended_next_action: str = ""
    llm_debrief: str = ""


class GraphBundle(BaseModel):
    session_id: str
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ApproveSessionRequest(BaseModel):
    plan_id: Optional[str] = None
    approved_by: str = "operator"


class RejectSessionRequest(BaseModel):
    reason: str = "operator_rejected"


class AbortSessionRequest(BaseModel):
    reason: str = "operator_aborted"


class OrchestratorSession(BaseModel):
    session_id: str
    created_at: float
    updated_at: float
    status: SessionStatus
    brain_mode: BrainMode = BrainMode.CLASSIC_PYTHON
    review_mode: ReviewMode
    execution_mode: ExecutionMode
    baseline: BaselineMeta
    snapshot_meta: Dict[str, Any] = Field(default_factory=dict)
    diagnosis: Dict[str, Any] = Field(default_factory=dict)
    plan_bundle: Dict[str, Any] = Field(default_factory=dict)
    twin_compare: TwinCompareResponse
    selected_plan_id: Optional[str] = None
    recommended_plan_id: Optional[str] = None
    review_result: Optional[Dict[str, Any]] = None
    policy_result: PolicyGateResult
    execution_ticket: Optional[ExecutionTicket] = None
    execution_log: List[Dict[str, Any]] = Field(default_factory=list)
    step_validation_log: List[StepValidationResult] = Field(default_factory=list)
    debrief_report: Optional[DebriefReport] = None
    graph_bundle: Optional[GraphBundle] = None
    explanation: Optional[Dict[str, Any]] = None
    fault_layers: FaultLayerSummary = Field(default_factory=FaultLayerSummary)
    dry_run: bool = True
    current_step_index: int = 0
    helm_monitor: Optional[HelmMonitorResult] = None
    helm_review: Optional[HelmReviewResult] = None
    operator_question: Optional[HelmOperatorQuestion] = None
    dialogue_log: List[HelmDialogueTurn] = Field(default_factory=list)
    helm_context: Optional[HelmSessionContext] = None
