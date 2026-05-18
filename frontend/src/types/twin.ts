export interface TwinEnvironmentConfig {
  sun_exposure: number;
  eclipse_factor: number;
  radiation_level: number;
  antenna_alignment_error_deg: number;
  battery_age_factor: number;
  thermal_sink_efficiency: number;
  mission_phase: string;
}

export interface TwinFaultSpec {
  id: string;
  category: string;
  severity: number;
  start_t?: number;
  duration?: number;
  parameters?: Record<string, unknown>;
  layer?: string | null;
  status?: string;
  clearable_by?: string[];
  suppressible_by?: string[];
  retrigger_policy?: string;
  source?: string;
}

export interface TwinPlanStep {
  action: string;
  params: Record<string, unknown>;
  at_t?: number;
}

export interface TwinRunRequest {
  from_snapshot?: string;
  environment?: TwinEnvironmentConfig;
  faults?: TwinFaultSpec[];
  actions?: TwinPlanStep[];
  horizon_sec?: number;
  dt?: number;
  stochastic?: boolean;
  rng_seed?: number | null;
  stop_on_violation?: boolean;
}

export interface TwinConstraintResult {
  name: string;
  passed: boolean;
  current_value?: number | null;
  worst_value?: number | null;
  threshold?: number | null;
  message: string;
}

export interface FaultLayerItem {
  id: string;
  system?: string;
  layer?: string;
  severity?: number;
  status?: string;
  parameters?: Record<string, unknown>;
  clearable_by?: string[];
  suppressible_by?: string[];
  source?: string;
  [key: string]: unknown;
}

export interface FaultLayerSummary {
  root_causes: FaultLayerItem[];
  recoverable_faults: FaultLayerItem[];
  active_mitigations: FaultLayerItem[];
  symptoms: FaultLayerItem[];
}

export interface RepairTraceStep {
  step_index: number;
  action: string;
  cleared_faults: string[];
  suppressed_faults: string[];
  remaining_root_causes: string[];
  mitigation_changes: Record<string, unknown>;
  key_metric_deltas: Record<string, number>;
  note: string;
}

export interface SubsystemFrame {
  subsystem_id: string;
  health_state: 'normal' | 'warning' | 'fault' | 'safe' | 'disabled' | string;
  highlight_intensity: number;
  visible_metrics: Record<string, unknown>;
  hidden_state: Record<string, unknown>;
  note: string;
}

export interface EnvironmentEvent {
  t: number;
  event_type: string;
  label: string;
  payload: Record<string, unknown>;
}

export interface ActionEvent {
  t: number;
  step_index: number;
  action: string;
  affected_subsystems: string[];
  summary: string;
}

export interface ConstraintFrame {
  t: number;
  checks: TwinConstraintResult[];
  risk_score: number;
  verdict: 'PASS' | 'FAIL' | string;
}

export interface TwinPlaybackFrame {
  t: number;
  seq_offset: number;
  mode: string;
  current_action?: string | null;
  subsystem_frames: SubsystemFrame[];
  visible_snapshot: Record<string, unknown>;
  hidden_fault_layers: FaultLayerSummary;
  constraint_frame: ConstraintFrame;
  key_metric_deltas: Record<string, number>;
}

export interface PlanPlaybackBundle {
  compare_id: string;
  baseline_id: string;
  plan_id: string;
  label: string;
  recommended: boolean;
  baseline_snapshot: Record<string, unknown>;
  frames: TwinPlaybackFrame[];
  action_events: ActionEvent[];
  environment_events: EnvironmentEvent[];
  repair_trace: RepairTraceStep[];
  verdict: 'PASS' | 'FAIL';
  risk_score: number;
  recovery_time_s?: number | null;
}

export interface TwinRunResponse {
  run_id: string;
  verdict: 'PASS' | 'FAIL';
  risk_score: number;
  final_mode: string;
  constraints: TwinConstraintResult[];
  trajectory: Array<Record<string, unknown>>;
  final_snapshot: Record<string, unknown>;
  explanation: string;
  fault_layers?: FaultLayerSummary;
  repair_trace?: RepairTraceStep[];
}

export interface BaselineMeta {
  baseline_id: string;
  captured_at: number;
  expires_at: number;
  captured_seq: number;
  captured_change_version: number;
  captured_fault: string;
  state_digest: string;
}

export type BaselineStatus = 'none' | 'fresh' | 'stale' | 'invalidated' | 'expired';

export interface FreezeBaselineResponse {
  baseline: BaselineMeta;
  snapshot: Record<string, unknown>;
}

export interface TwinPlanCandidate {
  id: string;
  label?: string;
  actions: TwinPlanStep[];
}

export interface TwinCompareRequest {
  from_snapshot?: string;
  environment?: TwinEnvironmentConfig;
  faults?: TwinFaultSpec[];
  plans: TwinPlanCandidate[];
  horizon_sec?: number;
  dt?: number;
  stochastic?: boolean;
}

export interface TwinCompareFromBaselineRequest extends TwinCompareRequest {
  baseline_id: string;
}

export interface TwinComparePlanResult {
  plan_id: string;
  label?: string;
  baseline_id?: string;
  baseline_seq?: number;
  baseline_digest?: string;
  verdict: 'PASS' | 'FAIL';
  risk_score: number;
  final_mode: string;
  constraints: TwinConstraintResult[];
  trajectory: Array<Record<string, unknown>>;
  final_snapshot: Record<string, unknown>;
  explanation: string;
  fault_layers?: FaultLayerSummary;
  repair_trace?: RepairTraceStep[];
}

export interface TwinCompareResponse {
  compare_id: string;
  best_plan_id: string;
  baseline?: BaselineMeta | null;
  results: TwinComparePlanResult[];
  explanation: string;
}

export interface TwinSnapshotResponse {
  snapshot_id: string;
  source: string;
  probe_id: string;
  seq: number;
  mode: string;
  active_fault: string;
  active_faults: string[];
  environment: TwinEnvironmentConfig;
  allowed_commands: string[];
  supported_fault_categories: string[];
  snapshot: Record<string, unknown>;
}

export type TwinMode = 'live' | 'demo';

export type ReviewMode = 'manual' | 'assisted' | 'auto';

export interface RecoveryEvaluationRequest {
  reason: string;
  review_mode: ReviewMode;
  include_compare: boolean;
  include_explanation: boolean;
  horizon_sec: number;
  dt: number;
  stochastic: boolean;
}

export interface ReviewSuggestion {
  mode: string;
  can_auto_execute: boolean;
  why: string;
}

export interface RecoveryEvaluationResponse {
  snapshot_seq: number;
  snapshot_meta: Record<string, unknown>;
  baseline: BaselineMeta;
  diagnosis: Record<string, unknown>;
  plan_bundle: Record<string, unknown>;
  twin_compare: TwinCompareResponse;
  recommended_plan_id: string;
  review_suggestion: ReviewSuggestion;
  explanation?: Record<string, unknown> | null;
  fault_layers?: FaultLayerSummary;
}

export interface TwinCalibration {
  baseline_id: string;
  metric_deltas: Record<string, number>;
  max_abs_delta: number;
  confidence: number;
  note: string;
}

export interface FaultInjectionRequest {
  faults: TwinFaultSpec[];
  label?: string;
}

export interface SimulationCampaignRequest {
  plans?: TwinPlanCandidate[];
  faults?: TwinFaultSpec[];
  environment_branches?: TwinEnvironmentConfig[];
  horizon_sec?: number;
  dt?: number;
  seeds?: number[];
}

export interface CampaignPlanScore {
  plan_id: string;
  label: string;
  pass_rate: number;
  worst_risk_score: number;
  avg_risk_score: number;
  max_temp_c: number;
  min_battery_voltage: number;
  max_packet_loss: number;
  recovery_time_s?: number | null;
  command_count: number;
  high_risk_actions: string[];
  verdict: 'PASS' | 'FAIL' | string;
}

export interface CampaignResponse {
  campaign_id: string;
  session_id: string;
  baseline_id: string;
  assembly_id?: string;
  assembly_version?: number;
  assembly_digest?: string;
  best_plan_id: string;
  scores: CampaignPlanScore[];
  run_count: number;
  explanation: string;
  gate_status?: string;
  gate_reason?: string;
}

export interface CommandPackageStep {
  action: string;
  params: Record<string, unknown>;
  earliest_send_t: number;
  preconditions: string[];
  expected_effects: Record<string, unknown>;
  abort_if: string[];
}

export interface CommandPackage {
  package_id: string;
  source_session_id: string;
  baseline_id: string;
  assembly_id?: string;
  assembly_version?: number;
  assembly_digest?: string;
  plan_id: string;
  plan_digest: string;
  risk_score: number;
  pass_rate: number;
  steps: CommandPackageStep[];
  requires_human_approval: boolean;
  approved_by?: string | null;
  status: string;
  gate_status?: string;
  gate_reason?: string;
  created_at: number;
  updated_at: number;
  uplink_delay_s: number;
  execution_log: Array<Record<string, unknown>>;
}

export interface CommandPackageRequest {
  plan_id?: string | null;
}

export interface GroundTestbedSession {
  session_id: string;
  created_at: number;
  updated_at: number;
  status: string;
  baseline: BaselineMeta;
  calibration: TwinCalibration;
  twin_faults: TwinFaultSpec[];
  candidate_plans: TwinPlanCandidate[];
  last_campaign?: CampaignResponse | null;
  selected_plan_id?: string | null;
  command_package_id?: string | null;
  assembly_id?: string | null;
  assembly_version?: number;
  assembly_digest?: string;
}

export interface TwinAssemblyValidationIssue {
  code: string;
  severity: string;
  message: string;
  component_id?: string | null;
  link_id?: string | null;
  port_id?: string | null;
}

export interface TwinAssemblyValidation {
  ok: boolean;
  issues: TwinAssemblyValidationIssue[];
  blocking_count: number;
  checked_at: number;
}

export interface TwinComponentPort {
  port_id: string;
  kind: string;
  direction: string;
  required: boolean;
  compatible_kinds: string[];
}

export interface ComponentFaultTemplate {
  template_id: string;
  label: string;
  category: string;
  layer: string;
  description: string;
  symptom: string;
  default_severity: number;
  parameters: Record<string, unknown>;
  affected_metrics: string[];
  recommended_checks: string[];
  candidate_actions: string[];
  destructive: boolean;
}

export interface TwinComponentInstance {
  instance_id: string;
  catalog_id: string;
  display_name: string;
  subsystem: string;
  slot: string;
  criticality: string;
  install_state: string;
  health_state: string;
  ports: TwinComponentPort[];
  parameters: Record<string, unknown>;
  position: Record<string, number>;
  rotation: Record<string, number>;
  scale: Record<string, number>;
  locked: boolean;
  slot_constraints: Record<string, unknown>;
  fault_templates: ComponentFaultTemplate[];
  active_faults: Array<Record<string, unknown>>;
  notes: string[];
}

export interface TwinComponentLink {
  link_id: string;
  from_component: string;
  from_port: string;
  to_component: string;
  to_port: string;
  medium: string;
  enabled: boolean;
}

export interface TwinAssemblyState {
  assembly_id: string;
  session_id: string;
  updated_at: number;
  version: number;
  assembly_digest: string;
  validation: TwinAssemblyValidation;
  undo_available: boolean;
  redo_available: boolean;
  components: TwinComponentInstance[];
  links: TwinComponentLink[];
  selected_component_id?: string | null;
  operation_log: Array<Record<string, unknown>>;
}

export interface TwinAssemblyCatalog {
  components: TwinComponentInstance[];
  catalog: Record<string, unknown>;
  fault_templates: Array<Record<string, unknown>>;
}

export interface ComponentOperationRequest {
  catalog_id: string;
  instance_id?: string | null;
  display_name?: string | null;
  slot?: string | null;
  parameters?: Record<string, unknown>;
  position?: Record<string, number>;
  rotation?: Record<string, number>;
  scale?: Record<string, number>;
}

export interface ComponentTransformRequest {
  position?: Record<string, number> | null;
  rotation?: Record<string, number> | null;
  scale?: Record<string, number> | null;
}

export interface ComponentParametersRequest {
  parameters: Record<string, unknown>;
}

export interface ComponentReplaceRequest {
  catalog_id: string;
  display_name?: string | null;
  slot?: string | null;
  parameters?: Record<string, unknown>;
}

export interface ComponentLinkRequest {
  link_id?: string | null;
  from_component: string;
  from_port?: string;
  to_component: string;
  to_port?: string;
  medium?: string;
  enabled?: boolean;
}

export interface ComponentFaultInjectionRequest {
  component_id: string;
  template_id: string;
  severity?: number | null;
  start_t?: number;
  duration?: number;
  parameters?: Record<string, unknown>;
}

export interface ComponentFaultInjectionResponse {
  ok: boolean;
  assembly: TwinAssemblyState;
  session: GroundTestbedSession;
  fault: TwinFaultSpec;
}

export interface TroubleshootingRequest {
  component_id?: string | null;
  situation?: string;
  include_gemma?: boolean;
}

export interface TroubleshootingResponse {
  ok: boolean;
  source: string;
  session_id: string;
  component_id?: string | null;
  summary: string;
  suspects: Array<Record<string, unknown>>;
  candidate_actions: string[];
  procedure: string[];
  gemma_prompt: Record<string, unknown>;
  gemma?: Record<string, unknown> | null;
}
