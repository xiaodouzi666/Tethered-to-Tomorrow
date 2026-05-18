import type { ProbeSnapshot, SubsystemStatus } from '../../types';
import type { SubsystemFrame, TwinPlaybackFrame, TwinRunResponse } from '../../types/twin';

export interface TwinSubsystemVisual {
  status: SubsystemStatus;
  battery_voltage?: number;
  controller_ok?: boolean;
  enabled?: boolean;
  health_state?: string;
  highlight_intensity?: number;
  packet_loss?: number;
  radiator_efficiency?: number;
  signal_strength?: number;
  temp_c?: number;
  using_backup_sensor?: boolean;
}

export interface TwinVisualState {
  activeFault: string;
  activeFaults: string[];
  displayFault: string;
  mode: string;
  riskScore?: number;
  subsystems: {
    power: TwinSubsystemVisual;
    thermal: TwinSubsystemVisual;
    comms: TwinSubsystemVisual;
    computer: TwinSubsystemVisual;
    payload: TwinSubsystemVisual;
    sensor: TwinSubsystemVisual;
  };
}

export function buildTwinVisualState(
  snapshot?: ProbeSnapshot | null,
  result?: TwinRunResponse | null,
  currentFrame?: TwinPlaybackFrame | null
): TwinVisualState {
  const finalSnapshot = currentFrame?.visible_snapshot ?? result?.final_snapshot;
  const finalSubsystems = readObject(finalSnapshot?.subsystems);
  const frameSubsystems = frameSubsystemMap(currentFrame?.subsystem_frames);
  const activeFault = readString(finalSnapshot, 'active_fault') ?? snapshot?.active_fault ?? 'none';
  const activeFaults = normalizeFaults(readStringArray(finalSnapshot, 'active_faults') ?? snapshot?.active_faults ?? [], activeFault);
  const mode = currentFrame?.mode ?? result?.final_mode ?? readString(finalSnapshot, 'mode') ?? snapshot?.mode ?? 'UNKNOWN';

  const subsystems = {
    power: mergeSubsystem(snapshot?.subsystems.power, readObject(finalSubsystems?.power), frameSubsystems.power),
    thermal: mergeSubsystem(snapshot?.subsystems.thermal, readObject(finalSubsystems?.thermal), frameSubsystems.thermal),
    comms: mergeSubsystem(snapshot?.subsystems.comms, readObject(finalSubsystems?.comms), frameSubsystems.comms),
    computer: mergeSubsystem(snapshot?.subsystems.computer, readObject(finalSubsystems?.computer), frameSubsystems.computer),
    payload: mergeSubsystem(snapshot?.subsystems.payload, readObject(finalSubsystems?.payload), frameSubsystems.payload),
    sensor: mergeSubsystem(undefined, undefined, frameSubsystems.sensor)
  };

  return {
    activeFault,
    activeFaults,
    displayFault: displayFault(activeFault, activeFaults, subsystems),
    mode,
    riskScore: currentFrame?.constraint_frame.risk_score ?? result?.risk_score,
    subsystems
  };
}

function mergeSubsystem(
  fallback: Record<string, unknown> | undefined,
  current: Record<string, unknown> | undefined,
  frame?: SubsystemFrame
): TwinSubsystemVisual {
  const source = { ...(fallback ?? {}), ...(current ?? {}), ...(frame?.visible_metrics ?? {}) };
  const statusFromFrame = statusFromHealth(frame?.health_state);
  return {
    status: statusFromFrame ?? readStatus(source.status),
    battery_voltage: readNumber(source.battery_voltage),
    controller_ok: readBoolean(source.controller_ok),
    enabled: readBoolean(source.enabled),
    health_state: frame?.health_state,
    highlight_intensity: frame?.highlight_intensity,
    packet_loss: readNumber(source.packet_loss),
    radiator_efficiency: readNumber(source.radiator_efficiency),
    signal_strength: readNumber(source.signal_strength),
    temp_c: readNumber(source.temp_c),
    using_backup_sensor: readBoolean(source.using_backup_sensor)
  };
}

function displayFault(
  activeFault: string,
  activeFaults: string[],
  subsystems: TwinVisualState['subsystems']
): string {
  if (activeFault !== 'none') return activeFault;
  if (activeFaults.length > 0) return activeFaults.join('+');
  if (subsystems.power.status === 'FAULT') return 'power';
  if (subsystems.thermal.status === 'FAULT') return 'thermal';
  if (subsystems.comms.status === 'FAULT') return 'comms';
  if (subsystems.computer.status === 'FAULT') return 'computer';
  if (subsystems.payload.status === 'FAULT') return 'payload';
  if (subsystems.sensor.status === 'FAULT' || subsystems.payload.using_backup_sensor) return 'sensor';
  return 'none';
}

function normalizeFaults(faults: string[], activeFault: string): string[] {
  const normalized = faults.filter((fault) => fault && fault !== 'none');
  if (activeFault !== 'none' && !normalized.includes(activeFault)) {
    normalized.unshift(activeFault);
  }
  return normalized;
}

function readObject(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' ? value as Record<string, unknown> : undefined;
}

function readString(source: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = source?.[key];
  return typeof value === 'string' ? value : undefined;
}

function readStringArray(source: Record<string, unknown> | undefined, key: string): string[] | undefined {
  const value = source?.[key];
  if (!Array.isArray(value)) return undefined;
  return value.filter((item): item is string => typeof item === 'string');
}

function readNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function readStatus(value: unknown): SubsystemStatus {
  return value === 'OK' || value === 'WARN' || value === 'FAULT' || value === 'OFF' ? value : 'OK';
}

function frameSubsystemMap(frames?: SubsystemFrame[]): Record<string, SubsystemFrame | undefined> {
  const map: Record<string, SubsystemFrame | undefined> = {};
  for (const frame of frames ?? []) {
    map[frame.subsystem_id] = frame;
  }
  return map;
}

function statusFromHealth(health?: string): SubsystemStatus | undefined {
  if (!health) return undefined;
  if (health === 'fault') return 'FAULT';
  if (health === 'warning') return 'WARN';
  if (health === 'disabled') return 'OFF';
  if (health === 'safe' || health === 'normal') return 'OK';
  return undefined;
}
