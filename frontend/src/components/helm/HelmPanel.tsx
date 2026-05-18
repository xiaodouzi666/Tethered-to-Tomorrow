import { Cpu } from 'lucide-react';
import type { OrchestratorSession } from '../../types/orchestrator';

export function HelmPanel({ session }: { session: OrchestratorSession | null }) {
  const monitor = session?.helm_monitor;
  const review = session?.helm_review;
  return (
    <div className="helm-card">
      <div className="orchestrator-card-head">
        <span><Cpu size={12} /> E4B Helm</span>
        <strong>{review?.source ?? (session ? 'rules-ready' : 'standby')}</strong>
      </div>
      <p>{monitor?.reason ?? 'Helm mode keeps Python policy/execution as the control authority.'}</p>
      <div className="orchestrator-policy-grid">
        <Metric label="Monitor" value={monitor?.severity ?? '--'} />
        <Metric label="Recommendation" value={review?.recommended_plan_id ?? session?.recommended_plan_id ?? '--'} />
        <Metric label="Confidence" value={typeof review?.confidence === 'number' ? `${Math.round(review.confidence * 100)}%` : '--'} />
      </div>
      {review?.remaining_risks?.length ? (
        <ul className="orchestrator-list">
          {review.remaining_risks.slice(0, 3).map(item => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
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
