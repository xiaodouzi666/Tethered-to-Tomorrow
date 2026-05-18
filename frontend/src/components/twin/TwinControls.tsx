import { GitCompare, Play, RefreshCw, RotateCcw } from 'lucide-react';
import type { TwinScenario } from '../../hooks/useTwinRun';
import type { BaselineMeta, BaselineStatus, TwinMode } from '../../types/twin';

interface TwinControlsProps {
  baseline: BaselineMeta | null;
  baselineStatus: BaselineStatus;
  loading: 'run' | 'compare' | 'snapshot' | 'orchestrator' | null;
  mode: TwinMode;
  onCompare: () => void;
  onRefreshBaseline: () => void;
  onRefreshSnapshot: () => void;
  onReset: () => void;
  onRun: () => void;
  onScenarioChange: (scenario: TwinScenario) => void;
  onModeChange: (mode: TwinMode) => void;
  scenario: TwinScenario;
}

const scenarios: Array<{ id: TwinScenario; label: string }> = [
  { id: 'nominal', label: 'Nominal' },
  { id: 'thermal', label: 'Load Thermal Scenario' },
  { id: 'comms', label: 'Load Comms Scenario' },
  { id: 'power', label: 'Load Power Scenario' }
];

export function TwinControls({
  baseline,
  baselineStatus,
  loading,
  mode,
  onCompare,
  onModeChange,
  onRefreshBaseline,
  onRefreshSnapshot,
  onReset,
  onRun,
  onScenarioChange,
  scenario
}: TwinControlsProps) {
  const busy = loading !== null;

  return (
    <div className="twin-controls">
      <div className="twin-mode-row">
        <button
          className={mode === 'live' ? 'selected' : ''}
          disabled={busy}
          onClick={() => onModeChange('live')}
          type="button"
        >
          Live Analysis
        </button>
        <button
          className={mode === 'demo' ? 'selected' : ''}
          disabled={busy}
          onClick={() => onModeChange('demo')}
          type="button"
        >
          Demo Scenario
        </button>
      </div>

      {mode === 'live' && (
        <BaselineStrip baseline={baseline} status={baselineStatus} />
      )}

      {mode === 'demo' && (
        <div className="twin-scenario-row">
          {scenarios.map(item => (
            <button
              className={item.id === scenario ? 'selected' : ''}
              disabled={busy}
              key={item.id}
              onClick={() => onScenarioChange(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      <div className="button-row wrap">
        <button className="primary" disabled={busy} onClick={onRun} type="button">
          <Play size={14} /> {mode === 'live' ? 'Analyze Current State' : 'Run Demo Scenario'}
        </button>
        {mode === 'demo' && (
          <button disabled={busy} onClick={onCompare} type="button">
            <GitCompare size={14} /> Compare Plans
          </button>
        )}
        <button disabled={busy} onClick={onRefreshSnapshot} type="button">
          <RefreshCw size={14} /> Snapshot
        </button>
        {mode === 'live' && (
          <button disabled={busy} onClick={onRefreshBaseline} type="button">
            <RefreshCw size={14} /> Refresh Baseline
          </button>
        )}
        <button disabled={busy} onClick={onReset} type="button">
          <RotateCcw size={14} /> Reset Twin
        </button>
      </div>
    </div>
  );
}

function BaselineStrip({
  baseline,
  status
}: {
  baseline: BaselineMeta | null;
  status: BaselineStatus;
}) {
  return (
    <div className={`twin-baseline-strip ${status}`}>
      <div>
        <span>Baseline</span>
        <strong>{baseline ? shortId(baseline.baseline_id) : '--'}</strong>
      </div>
      <div>
        <span>Seq</span>
        <strong>{baseline?.captured_seq ?? '--'}</strong>
      </div>
      <div>
        <span>Digest</span>
        <strong>{baseline ? shortDigest(baseline.state_digest) : '--'}</strong>
      </div>
      <b>{status}</b>
    </div>
  );
}

function shortId(value: string): string {
  return value.replace(/^baseline-/, '').slice(0, 6);
}

function shortDigest(value: string): string {
  return value.slice(0, 8);
}
