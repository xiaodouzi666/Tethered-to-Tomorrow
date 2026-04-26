export type SubsystemStatus = 'OK' | 'WARN' | 'FAULT' | 'OFF';

export interface ProbeSnapshot {
  probe_id: string;
  ts: number;
  seq: number;
  mode: string;
  active_fault: string;
  subsystems: {
    power: { status: SubsystemStatus; battery_voltage: number; load_w: number; solar_input_w: number };
    thermal: { status: SubsystemStatus; temp_c: number; controller_ok: boolean; radiator_efficiency: number };
    comms: { status: SubsystemStatus; signal_strength: number; packet_loss: number };
    computer: { status: SubsystemStatus; cpu_load: number; mem_used_mb: number; storage_health: string };
    payload: { status: SubsystemStatus; enabled: boolean; sampling_rate: number; using_backup_sensor: boolean };
  };
  last_command?: unknown;
  events: Array<{ ts: number; type: string; message: string; [key: string]: unknown }>;
}

export interface GemmaStatus {
  backend_requested: string;
  backend_active: string;
  ready: boolean;
  model_path: string;
  model_file: string;
  model_repo: string;
  hf_repo: string;
  require_real_gemma: boolean;
  message: string;
}

export interface HealthResponse {
  ok: boolean;
  service: string;
  probe_id: string;
  mode: string;
  active_fault: string;
  allowed_commands: string[];
  high_risk_commands: string[];
  gemma: GemmaStatus;
  ts: number;
}

export interface DiagnosisResponse {
  ok: boolean;
  snapshot_seq: number;
  anomaly: {
    agent: string;
    severity: string;
    affected_subsystems: string[];
    anomaly_summary: string[];
  };
  diagnosis: {
    agent: string;
    backend: string;
    fault_summary: string[];
    likely_causes: Array<{ cause: string; confidence: number; evidence: string[] }>;
    immediate_safe_actions: string[];
    risk_level: string;
    uncertainty: string;
    [key: string]: unknown;
  };
  safety_gate: {
    agent: string;
    allowed_actions: string[];
    blocked_actions: Array<{ action: string; reason: string }>;
    high_risk_actions: Array<{ action: string; reason: string }>;
  };
}
