from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FaultLayer(str, Enum):
    ROOT_CAUSE = "root_cause"
    RECOVERABLE = "recoverable"
    SYMPTOM = "symptom"


class FaultStatus(str, Enum):
    LATENT = "latent"
    ACTIVE = "active"
    CLEARED = "cleared"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


class EnvironmentConfig(BaseModel):
    sun_exposure: float = 1.0
    eclipse_factor: float = 0.0
    radiation_level: float = 0.0
    antenna_alignment_error_deg: float = 0.0
    battery_age_factor: float = 1.0
    thermal_sink_efficiency: float = 1.0
    mission_phase: str = "cruise"


class FaultSpec(BaseModel):
    id: str
    category: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    start_t: float = 0.0
    duration: float = 9999.0
    parameters: Dict[str, Any] = Field(default_factory=dict)
    layer: Optional[FaultLayer] = None
    status: FaultStatus = FaultStatus.ACTIVE
    clearable_by: List[str] = Field(default_factory=list)
    suppressible_by: List[str] = Field(default_factory=list)
    retrigger_policy: str = "none"
    source: str = "manual"


class PlanStep(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    at_t: float = 0.0


class TwinRunRequest(BaseModel):
    from_snapshot: str = "latest"
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    faults: List[FaultSpec] = Field(default_factory=list)
    actions: List[PlanStep] = Field(default_factory=list)
    horizon_sec: int = Field(default=600, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False
    rng_seed: Optional[int] = None
    stop_on_violation: bool = False


class BaselineMeta(BaseModel):
    baseline_id: str
    captured_at: float
    expires_at: float
    captured_seq: int
    captured_change_version: int
    captured_fault: str
    state_digest: str


class FreezeBaselineResponse(BaseModel):
    baseline: BaselineMeta
    snapshot: Dict[str, Any]


class ConstraintResult(BaseModel):
    name: str
    passed: bool
    current_value: Optional[float] = None
    worst_value: Optional[float] = None
    threshold: Optional[float] = None
    message: str = ""


class FaultLayerSummary(BaseModel):
    root_causes: List[Dict[str, Any]] = Field(default_factory=list)
    recoverable_faults: List[Dict[str, Any]] = Field(default_factory=list)
    active_mitigations: List[Dict[str, Any]] = Field(default_factory=list)
    symptoms: List[Dict[str, Any]] = Field(default_factory=list)


class RepairTraceStep(BaseModel):
    step_index: int
    action: str
    cleared_faults: List[str] = Field(default_factory=list)
    suppressed_faults: List[str] = Field(default_factory=list)
    remaining_root_causes: List[str] = Field(default_factory=list)
    mitigation_changes: Dict[str, Any] = Field(default_factory=dict)
    key_metric_deltas: Dict[str, float] = Field(default_factory=dict)
    note: str = ""


class SubsystemFrame(BaseModel):
    subsystem_id: str
    health_state: str
    highlight_intensity: float = 0.0
    visible_metrics: Dict[str, Any] = Field(default_factory=dict)
    hidden_state: Dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class EnvironmentEvent(BaseModel):
    t: float
    event_type: str
    label: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ActionEvent(BaseModel):
    t: float
    step_index: int
    action: str
    affected_subsystems: List[str] = Field(default_factory=list)
    summary: str = ""


class ConstraintFrame(BaseModel):
    t: float
    checks: List[ConstraintResult] = Field(default_factory=list)
    risk_score: float = 0.0
    verdict: str = "PASS"


class TwinPlaybackFrame(BaseModel):
    t: float
    seq_offset: int
    mode: str
    current_action: Optional[str] = None
    subsystem_frames: List[SubsystemFrame] = Field(default_factory=list)
    visible_snapshot: Dict[str, Any] = Field(default_factory=dict)
    hidden_fault_layers: Dict[str, Any] = Field(default_factory=dict)
    constraint_frame: ConstraintFrame
    key_metric_deltas: Dict[str, float] = Field(default_factory=dict)


class PlanPlaybackBundle(BaseModel):
    compare_id: str
    baseline_id: str
    plan_id: str
    label: str = ""
    recommended: bool = False
    baseline_snapshot: Dict[str, Any]
    frames: List[TwinPlaybackFrame] = Field(default_factory=list)
    action_events: List[ActionEvent] = Field(default_factory=list)
    environment_events: List[EnvironmentEvent] = Field(default_factory=list)
    repair_trace: List[RepairTraceStep] = Field(default_factory=list)
    verdict: str
    risk_score: float
    recovery_time_s: Optional[float] = None


class TwinRunResponse(BaseModel):
    run_id: str
    verdict: str
    risk_score: float
    final_mode: str
    constraints: List[ConstraintResult]
    trajectory: List[Dict[str, Any]]
    final_snapshot: Dict[str, Any]
    explanation: str
    fault_layers: FaultLayerSummary = Field(default_factory=FaultLayerSummary)
    repair_trace: List[RepairTraceStep] = Field(default_factory=list)


class TwinPlanCandidate(BaseModel):
    id: str
    label: str = ""
    actions: List[PlanStep] = Field(default_factory=list)


class TwinCompareRequest(BaseModel):
    from_snapshot: str = "latest"
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    faults: List[FaultSpec] = Field(default_factory=list)
    plans: List[TwinPlanCandidate] = Field(min_length=2, max_length=3)
    horizon_sec: int = Field(default=600, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False


class TwinCompareFromBaselineRequest(BaseModel):
    baseline_id: str
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    faults: List[FaultSpec] = Field(default_factory=list)
    plans: List[TwinPlanCandidate] = Field(min_length=2, max_length=3)
    horizon_sec: int = Field(default=300, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False


class TwinCalibration(BaseModel):
    baseline_id: str
    metric_deltas: Dict[str, float] = Field(default_factory=dict)
    max_abs_delta: float = 0.0
    confidence: float = 1.0
    note: str = ""


class FaultInjectionRequest(BaseModel):
    faults: List[FaultSpec] = Field(default_factory=list)
    label: str = "operator_fault_injection"


class SimulationCampaignRequest(BaseModel):
    plans: List[TwinPlanCandidate] = Field(default_factory=list)
    faults: List[FaultSpec] = Field(default_factory=list)
    environment_branches: List[EnvironmentConfig] = Field(default_factory=list)
    horizon_sec: int = Field(default=600, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    seeds: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])


class CampaignPlanScore(BaseModel):
    plan_id: str
    label: str = ""
    pass_rate: float
    worst_risk_score: float
    avg_risk_score: float
    max_temp_c: float
    min_battery_voltage: float
    max_packet_loss: float
    recovery_time_s: Optional[float] = None
    command_count: int
    high_risk_actions: List[str] = Field(default_factory=list)
    verdict: str


class CampaignResponse(BaseModel):
    campaign_id: str
    session_id: str = ""
    baseline_id: str
    assembly_id: str = ""
    assembly_version: int = 0
    assembly_digest: str = ""
    best_plan_id: str
    scores: List[CampaignPlanScore] = Field(default_factory=list)
    run_count: int = 0
    explanation: str = ""
    gate_status: str = "unknown"
    gate_reason: str = ""


class CommandPackageStep(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    earliest_send_t: float = 0.0
    preconditions: List[str] = Field(default_factory=list)
    expected_effects: Dict[str, Any] = Field(default_factory=dict)
    abort_if: List[str] = Field(default_factory=list)


class CommandPackage(BaseModel):
    package_id: str
    source_session_id: str
    baseline_id: str
    assembly_id: str = ""
    assembly_version: int = 0
    assembly_digest: str = ""
    plan_id: str
    plan_digest: str
    risk_score: float
    pass_rate: float
    steps: List[CommandPackageStep] = Field(default_factory=list)
    requires_human_approval: bool = True
    approved_by: Optional[str] = None
    status: str = "DRAFT"
    gate_status: str = "pending"
    gate_reason: str = ""
    created_at: float
    updated_at: float
    uplink_delay_s: float = 8.0
    execution_log: List[Dict[str, Any]] = Field(default_factory=list)


class CommandPackageRequest(BaseModel):
    plan_id: Optional[str] = None


class GroundTestbedSession(BaseModel):
    session_id: str
    created_at: float
    updated_at: float
    status: str = "BASELINE_FROZEN"
    baseline: BaselineMeta
    calibration: TwinCalibration
    twin_faults: List[FaultSpec] = Field(default_factory=list)
    candidate_plans: List[TwinPlanCandidate] = Field(default_factory=list)
    last_campaign: Optional[CampaignResponse] = None
    selected_plan_id: Optional[str] = None
    command_package_id: Optional[str] = None
    assembly_id: Optional[str] = None
    assembly_version: int = 0
    assembly_digest: str = ""


class TwinAssemblyValidationIssue(BaseModel):
    code: str
    severity: str = "error"
    message: str
    component_id: Optional[str] = None
    link_id: Optional[str] = None
    port_id: Optional[str] = None


class TwinAssemblyValidation(BaseModel):
    ok: bool = True
    issues: List[TwinAssemblyValidationIssue] = Field(default_factory=list)
    blocking_count: int = 0
    checked_at: float = 0.0


class TwinComponentPort(BaseModel):
    port_id: str
    kind: str = "data"
    direction: str = "inout"
    required: bool = False
    compatible_kinds: List[str] = Field(default_factory=list)


class ComponentFaultTemplate(BaseModel):
    template_id: str
    label: str
    category: str
    layer: str = "recoverable"
    description: str = ""
    symptom: str = ""
    default_severity: float = Field(default=0.5, ge=0.0, le=1.0)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    affected_metrics: List[str] = Field(default_factory=list)
    recommended_checks: List[str] = Field(default_factory=list)
    candidate_actions: List[str] = Field(default_factory=list)
    destructive: bool = False


class TwinComponentInstance(BaseModel):
    instance_id: str
    catalog_id: str
    display_name: str
    subsystem: str
    slot: str
    criticality: str = "important"
    install_state: str = "installed"
    health_state: str = "nominal"
    ports: List[TwinComponentPort] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)
    rotation: Dict[str, float] = Field(default_factory=dict)
    scale: Dict[str, float] = Field(default_factory=dict)
    locked: bool = False
    slot_constraints: Dict[str, Any] = Field(default_factory=dict)
    fault_templates: List[ComponentFaultTemplate] = Field(default_factory=list)
    active_faults: List[Dict[str, Any]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TwinComponentLink(BaseModel):
    link_id: str
    from_component: str
    from_port: str
    to_component: str
    to_port: str
    medium: str = "data"
    enabled: bool = True


class TwinAssemblyState(BaseModel):
    assembly_id: str
    session_id: str
    updated_at: float
    version: int = 1
    assembly_digest: str = ""
    validation: TwinAssemblyValidation = Field(default_factory=TwinAssemblyValidation)
    undo_available: bool = False
    redo_available: bool = False
    components: List[TwinComponentInstance] = Field(default_factory=list)
    links: List[TwinComponentLink] = Field(default_factory=list)
    selected_component_id: Optional[str] = None
    operation_log: List[Dict[str, Any]] = Field(default_factory=list)


class ComponentOperationRequest(BaseModel):
    catalog_id: str
    instance_id: Optional[str] = None
    display_name: Optional[str] = None
    slot: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)
    rotation: Dict[str, float] = Field(default_factory=dict)
    scale: Dict[str, float] = Field(default_factory=dict)


class ComponentTransformRequest(BaseModel):
    position: Optional[Dict[str, float]] = None
    rotation: Optional[Dict[str, float]] = None
    scale: Optional[Dict[str, float]] = None


class ComponentParametersRequest(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ComponentReplaceRequest(BaseModel):
    catalog_id: str
    display_name: Optional[str] = None
    slot: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ComponentLinkRequest(BaseModel):
    link_id: Optional[str] = None
    from_component: str
    from_port: str = "data"
    to_component: str
    to_port: str = "data"
    medium: str = "data"
    enabled: bool = True


class ComponentFaultInjectionRequest(BaseModel):
    component_id: str
    template_id: str
    severity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    start_t: float = 0.0
    duration: float = 9999.0
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ComponentFaultInjectionResponse(BaseModel):
    ok: bool = True
    assembly: TwinAssemblyState
    session: GroundTestbedSession
    fault: FaultSpec


class TroubleshootingRequest(BaseModel):
    component_id: Optional[str] = None
    situation: str = "operator_requested_component_troubleshooting"
    include_gemma: bool = True


class TroubleshootingResponse(BaseModel):
    ok: bool = True
    source: str = "rules"
    session_id: str
    component_id: Optional[str] = None
    summary: str = ""
    suspects: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_actions: List[str] = Field(default_factory=list)
    procedure: List[str] = Field(default_factory=list)
    gemma_prompt: Dict[str, Any] = Field(default_factory=dict)
    gemma: Optional[Dict[str, Any]] = None


class TwinComparePlanResult(BaseModel):
    plan_id: str
    label: str = ""
    baseline_id: str = ""
    baseline_seq: int = 0
    baseline_digest: str = ""
    verdict: str
    risk_score: float
    final_mode: str
    constraints: List[ConstraintResult]
    trajectory: List[Dict[str, Any]]
    final_snapshot: Dict[str, Any]
    explanation: str
    fault_layers: FaultLayerSummary = Field(default_factory=FaultLayerSummary)
    repair_trace: List[RepairTraceStep] = Field(default_factory=list)


class TwinCompareResponse(BaseModel):
    compare_id: str
    best_plan_id: str
    baseline: Optional[BaselineMeta] = None
    results: List[TwinComparePlanResult]
    explanation: str


class TwinSnapshotResponse(BaseModel):
    snapshot_id: str
    source: str
    probe_id: str
    seq: int
    mode: str
    active_fault: str
    active_faults: List[str]
    environment: EnvironmentConfig
    allowed_commands: List[str]
    supported_fault_categories: List[str]
    snapshot: Dict[str, Any]


class RecoveryEvaluationRequest(BaseModel):
    reason: str = "operator_requested_analysis"
    review_mode: str = "manual"
    include_compare: bool = True
    include_explanation: bool = True
    horizon_sec: int = Field(default=300, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False


class ReviewSuggestion(BaseModel):
    mode: str
    can_auto_execute: bool
    why: str


class RecoveryEvaluationResponse(BaseModel):
    snapshot_seq: int
    snapshot_meta: Dict[str, Any]
    baseline: BaselineMeta
    diagnosis: Dict[str, Any]
    plan_bundle: Dict[str, Any]
    twin_compare: TwinCompareResponse
    recommended_plan_id: str
    review_suggestion: ReviewSuggestion
    explanation: Optional[Dict[str, Any]] = None
    fault_layers: FaultLayerSummary = Field(default_factory=FaultLayerSummary)
