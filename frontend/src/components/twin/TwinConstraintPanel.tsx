import { ShieldCheck, ShieldX } from 'lucide-react';
import type { TwinConstraintResult, TwinPlaybackFrame, TwinRunResponse } from '../../types/twin';

interface TwinConstraintPanelProps {
  currentFrame?: TwinPlaybackFrame | null;
  result?: TwinRunResponse | null;
}

const pendingConstraints = [
  'temp_c <= 85',
  'battery_voltage >= 10.5',
  'packet_loss <= 0.60'
];

export function TwinConstraintPanel({ currentFrame, result }: TwinConstraintPanelProps) {
  const frameConstraints = currentFrame?.constraint_frame.checks;
  const constraints = frameConstraints ?? result?.constraints;
  const verdict = currentFrame?.constraint_frame.verdict ?? result?.verdict;
  const risk = currentFrame?.constraint_frame.risk_score ?? result?.risk_score;

  return (
    <div className="twin-constraint-panel">
      <div className="twin-constraint-heading">
        <div className="twin-section-title">Constraints</div>
        {verdict && risk !== undefined && (
          <div className={`twin-verdict ${verdict}`}>{verdict} · risk {risk.toFixed(1)}</div>
        )}
      </div>

      <div className="twin-constraint-list">
        {constraints ? constraints.map((constraint) => (
          <ConstraintRow constraint={constraint} key={constraint.name} />
        )) : pendingConstraints.map((name) => (
          <div className="twin-constraint-row pending" key={name}>
            <span>{name}</span>
            <strong>--</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConstraintRow({ constraint }: { constraint: TwinConstraintResult }) {
  const failed = !constraint.passed;

  return (
    <div className={`twin-constraint-card ${failed ? 'failed' : 'passed'}`}>
      <div className="twin-constraint-main">
        {constraint.passed ? <ShieldCheck size={15} /> : <ShieldX size={15} />}
        <strong>{constraint.name}</strong>
        <span>{constraint.passed ? 'PASS' : 'FAIL'}</span>
      </div>
      <div className="twin-constraint-values">
        <Metric label="Current" value={formatConstraintValue(constraint.current_value, constraint)} />
        <Metric label="Worst" value={formatConstraintValue(constraint.worst_value, constraint)} />
        <Metric label="Threshold" value={formatThreshold(constraint)} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatThreshold(constraint: TwinConstraintResult): string {
  if (constraint.threshold === null || constraint.threshold === undefined) {
    return constraint.name.includes('safe_mode') ? 'required' : '--';
  }
  return formatConstraintValue(constraint.threshold, constraint);
}

function formatConstraintValue(value: number | null | undefined, constraint: TwinConstraintResult): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  if (constraint.name.includes('temp_c')) return `${value.toFixed(1)}C`;
  if (constraint.name.includes('battery_voltage')) return `${value.toFixed(2)}V`;
  if (constraint.name.includes('packet_loss') || constraint.name.includes('signal_strength') || constraint.name.includes('cpu_load')) {
    return value.toFixed(2);
  }
  if (constraint.name.includes('safe_mode')) return value > 0 ? 'yes' : 'no';
  return value.toFixed(2);
}
