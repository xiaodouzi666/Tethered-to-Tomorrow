import type {
  BaselineMeta,
  FaultLayerSummary,
  TwinCompareResponse
} from './twin';
import type {
  HelmDialogueTurn,
  HelmMonitorResult,
  HelmOperatorQuestion,
  HelmReviewResult,
  HelmSessionContext
} from './helm';

export type BrainMode = 'classic_python' | 'gemma_helm';
export type ReviewMode = 'manual' | 'assisted' | 'auto';
export type ExecutionMode = 'manual_step' | 'manual_plan' | 'auto_step';
export type SessionStatus =
  | 'IDLE'
  | 'BASELINE_FROZEN'
  | 'DIAGNOSING'
  | 'PLANS_GENERATED'
  | 'TWIN_COMPARED'
  | 'REVIEW_READY'
  | 'WAITING_APPROVAL'
  | 'APPROVED'
  | 'EXECUTING'
  | 'OBSERVING'
  | 'COMPLETED'
  | 'ABORTED'
  | 'STALE';

export interface OrchestratorStartRequest {
  brain_mode: BrainMode;
  reason: string;
  review_mode: ReviewMode;
  execution_mode: ExecutionMode;
  include_compare: boolean;
  include_explanation: boolean;
  horizon_sec: number;
  dt: number;
  stochastic: boolean;
}

export interface PolicyGateResult {
  allowed: boolean;
  level: string;
  baseline_status: string;
  requested_review_mode: ReviewMode;
  effective_review_mode: ReviewMode;
  requested_execution_mode: ExecutionMode;
  effective_execution_mode: ExecutionMode;
  can_auto_review: boolean;
  can_auto_step: boolean;
  reasons: string[];
  blocking_conditions: string[];
  requires_reanalysis: boolean;
}

export interface ExecutionTicket {
  ticket_id: string;
  session_id: string;
  baseline_id: string;
  plan_id: string;
  plan_digest: string;
  approved_by?: string | null;
  issued_at: number;
  expires_at: number;
  dry_run: boolean;
}

export interface StepValidationResult {
  step_index: number;
  action: string;
  passed: boolean;
  within_envelope: boolean;
  deviations: Array<Record<string, unknown>>;
  recommendation: string;
  expected_frame_t?: number | null;
  note: string;
}

export interface DebriefReport {
  session_id: string;
  baseline_id: string;
  primary_fault: string;
  summary: string;
  diagnosis_summary: string;
  selected_plan: string;
  executed_steps: Array<Record<string, unknown>>;
  cleared_faults: string[];
  remaining_root_causes: string[];
  constraint_violations: string[];
  final_outcome: string;
  recommended_next_action: string;
  llm_debrief: string;
}

export interface GraphBundle {
  session_id: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  summary: string;
}

export interface OrchestratorSession {
  session_id: string;
  created_at: number;
  updated_at: number;
  status: SessionStatus;
  brain_mode: BrainMode;
  review_mode: ReviewMode;
  execution_mode: ExecutionMode;
  baseline: BaselineMeta;
  snapshot_meta: Record<string, unknown>;
  diagnosis: Record<string, unknown>;
  plan_bundle: Record<string, unknown>;
  twin_compare: TwinCompareResponse;
  selected_plan_id?: string | null;
  recommended_plan_id?: string | null;
  review_result?: Record<string, unknown> | null;
  policy_result: PolicyGateResult;
  execution_ticket?: ExecutionTicket | null;
  execution_log: Array<Record<string, unknown>>;
  step_validation_log: StepValidationResult[];
  debrief_report?: DebriefReport | null;
  graph_bundle?: GraphBundle | null;
  explanation?: Record<string, unknown> | null;
  fault_layers?: FaultLayerSummary;
  dry_run: boolean;
  current_step_index: number;
  helm_monitor?: HelmMonitorResult | null;
  helm_review?: HelmReviewResult | null;
  operator_question?: HelmOperatorQuestion | null;
  dialogue_log: HelmDialogueTurn[];
  helm_context?: HelmSessionContext | null;
}

export interface ApproveSessionRequest {
  plan_id?: string | null;
  approved_by: string;
}

export interface RejectSessionRequest {
  reason: string;
}

export interface AbortSessionRequest {
  reason: string;
}

export interface HelmDialogueRequest {
  choice: string;
  message?: string;
}
