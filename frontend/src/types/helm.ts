import type { BrainMode } from './orchestrator';

export interface HelmMonitorResult {
  should_start_session: boolean;
  severity: string;
  reason: string;
  suspected_subsystems: string[];
  operator_needed: boolean;
  source: string;
}

export interface HelmReviewResult {
  recommended_plan_id?: string | null;
  confidence: number;
  why: string;
  remaining_risks: string[];
  auto_review_suggested: boolean;
  operator_question_needed: boolean;
  source: string;
}

export interface HelmOperatorQuestion {
  question_id: string;
  mode: string;
  title: string;
  summary: string;
  choices: string[];
  default_choice: string;
  plan_id?: string | null;
}

export interface HelmDialogueTurn {
  ts: number;
  speaker: string;
  choice?: string | null;
  message: string;
  response: string;
}

export interface HelmSessionContext {
  baseline_id: string;
  snapshot_seq: number;
  monitor: Record<string, unknown>;
  diagnosis_summary: Record<string, unknown>;
  plan_summary: Record<string, unknown>;
  compare_summary: Record<string, unknown>;
}

export interface HelmDialogueRequest {
  choice: string;
  message?: string;
}

export interface HelmStatusResponse {
  ready: boolean;
  gemma_ready: boolean;
  fallback_enabled: boolean;
  auto_monitor_enabled: boolean;
  live_execution_enabled: boolean;
  brain_mode_default: BrainMode;
  detail: Record<string, unknown>;
}

export interface HelmMonitorTickResponse {
  ok: boolean;
  monitor: HelmMonitorResult;
  snapshot_seq: number;
  active_fault: string;
}
