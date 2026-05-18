import { Fragment } from 'react';
import type { ProbeSnapshot } from '../../types';
import type { RepairTraceStep, TwinPlaybackFrame } from '../../types/twin';

interface TwinInspectorProps {
  currentFrame?: TwinPlaybackFrame | null;
  inspectorMode: 'visible' | 'hidden' | 'split';
  onInspectorModeChange: (mode: 'visible' | 'hidden' | 'split') => void;
  playbackIndex: number;
  repairTrace?: RepairTraceStep[];
  selectedSubsystem: string;
  snapshot?: ProbeSnapshot | null;
}

export function TwinInspector({
  currentFrame,
  inspectorMode,
  onInspectorModeChange,
  playbackIndex,
  repairTrace = [],
  selectedSubsystem,
  snapshot
}: TwinInspectorProps) {
  const frame = currentFrame?.subsystem_frames.find((item) => item.subsystem_id === selectedSubsystem);
  const real = realMetrics(snapshot, selectedSubsystem);
  const projected = frame?.visible_metrics ?? {};
  const trace = currentTrace(currentFrame, repairTrace, playbackIndex);
  const constraint = relatedConstraint(currentFrame, selectedSubsystem);

  return (
    <div className="twin-inspector">
      <div className="twin-inspector-head">
        <div>
          <span>Inspector</span>
          <strong>{labelForSubsystem(selectedSubsystem)}</strong>
        </div>
        <div className="twin-inspector-tabs">
          {(['split', 'visible', 'hidden'] as const).map((mode) => (
            <button
              className={inspectorMode === mode ? 'selected' : ''}
              key={mode}
              onClick={() => onInspectorModeChange(mode)}
              type="button"
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {inspectorMode !== 'hidden' && (
        <div className="twin-inspector-section">
          <span className="section-kicker">Visible telemetry</span>
          <MetricTable real={real} projected={projected} />
        </div>
      )}

      {inspectorMode !== 'visible' && (
        <div className="twin-inspector-section">
          <span className="section-kicker">Hidden state</span>
          <HiddenRows hidden={frame?.hidden_state} />
        </div>
      )}

      <div className="twin-inspector-section">
        <span className="section-kicker">Current action effect</span>
        {trace ? (
          <div className="inspector-action-effect">
            <strong>{trace.action}</strong>
            <p>{trace.note || 'Action applied in Twin playback.'}</p>
            <small>Cleared: {trace.cleared_faults.length ? trace.cleared_faults.join(', ') : 'none'}</small>
            <small>Suppressed: {trace.suppressed_faults.length ? trace.suppressed_faults.join(', ') : 'none'}</small>
            <small>Remaining root: {trace.remaining_root_causes.length ? trace.remaining_root_causes.join(', ') : 'none'}</small>
          </div>
        ) : (
          <small>No action at this frame.</small>
        )}
      </div>

      <div className="twin-inspector-section">
        <span className="section-kicker">Constraint impact</span>
        {constraint ? (
          <div className={`constraint-mini ${constraint.passed ? 'passed' : 'failed'}`}>
            <strong>{constraint.name}</strong>
            <span>{constraint.passed ? 'PASS' : 'FAIL'}</span>
          </div>
        ) : (
          <small>No related constraint at this frame.</small>
        )}
      </div>
    </div>
  );
}

function MetricTable({ projected, real }: { projected: Record<string, unknown>; real: Record<string, unknown> }) {
  const keys = Array.from(new Set([...Object.keys(real), ...Object.keys(projected)])).filter((key) => !['status'].includes(key));
  if (!keys.length) return <small>No visible telemetry for this subsystem.</small>;
  return (
    <div className="inspector-metric-table">
      {keys.slice(0, 5).map((key) => {
        const realValue = real[key];
        const projectedValue = projected[key];
        return (
          <div className="inspector-metric-row" key={key}>
            <span>{key}</span>
            <strong>{formatValue(realValue)}</strong>
            <strong>{formatValue(projectedValue)}</strong>
            <small>{formatDelta(realValue, projectedValue)}</small>
          </div>
        );
      })}
    </div>
  );
}

function HiddenRows({ hidden }: { hidden?: Record<string, unknown> }) {
  const groups = [
    ['Root', hidden?.root_causes],
    ['Recoverable', hidden?.recoverable_faults],
    ['Mitigation', hidden?.mitigations],
    ['Symptoms', hidden?.symptoms]
  ] as const;
  return (
    <div className="inspector-hidden-grid">
      {groups.map(([label, value]) => (
        <Fragment key={label}>
          <span>{label}</span>
          <div className="inspector-pill-row">
            {ids(value).length ? ids(value).map((id) => <code key={id}>{id}</code>) : <small>none</small>}
          </div>
        </Fragment>
      ))}
    </div>
  );
}

function currentTrace(
  currentFrame: TwinPlaybackFrame | null | undefined,
  trace: RepairTraceStep[],
  playbackIndex: number
): RepairTraceStep | undefined {
  if (!currentFrame?.current_action) return undefined;
  return trace.find((item) => item.action === currentFrame.current_action) ?? trace[Math.min(playbackIndex, trace.length - 1)];
}

function relatedConstraint(currentFrame: TwinPlaybackFrame | null | undefined, subsystem: string) {
  const checks = currentFrame?.constraint_frame.checks ?? [];
  const needle = subsystem === 'thermal'
    ? 'temp_c'
    : subsystem === 'power'
      ? 'battery_voltage'
      : subsystem === 'comms'
        ? 'packet_loss'
        : subsystem === 'computer'
          ? 'cpu_load'
          : '';
  return checks.find((check) => check.name.includes(needle));
}

function realMetrics(snapshot: ProbeSnapshot | null | undefined, subsystem: string): Record<string, unknown> {
  if (!snapshot) return {};
  if (subsystem === 'sensor') {
    return {
      using_backup_sensor: snapshot.subsystems.payload.using_backup_sensor,
      storage_health: snapshot.subsystems.computer.storage_health
    };
  }
  const value = snapshot.subsystems[subsystem as keyof ProbeSnapshot['subsystems']];
  return value && typeof value === 'object' ? value : {};
}

function ids(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => item && typeof item === 'object' ? String((item as Record<string, unknown>).id ?? '') : '')
    .filter(Boolean);
}

function formatValue(value: unknown): string {
  if (typeof value === 'number') return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'string') return value;
  return '--';
}

function formatDelta(real: unknown, projected: unknown): string {
  if (typeof real !== 'number' || typeof projected !== 'number') return '--';
  const delta = projected - real;
  return `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`;
}

function labelForSubsystem(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
