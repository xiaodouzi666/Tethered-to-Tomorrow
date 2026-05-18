import type { OrchestratorSession } from '../../types/orchestrator';

export function RecommendationCard({ session }: { session: OrchestratorSession | null }) {
  if (!session) {
    return (
      <div className="orchestrator-card">
        <div className="section-kicker">Recommendation</div>
        <p>Run live analysis to create an orchestrator session.</p>
      </div>
    );
  }

  const plan = findPlan(session, session.recommended_plan_id ?? '');
  const result = session.twin_compare.results.find(item => item.plan_id === session.recommended_plan_id);
  const policy = session.policy_result;

  return (
    <div className="orchestrator-card">
      <div className="orchestrator-card-head">
        <span>Recommendation</span>
        <strong>{session.recommended_plan_id ?? '--'}</strong>
      </div>
      <p>{typeof plan?.rationale === 'string' ? plan.rationale : session.twin_compare.explanation}</p>
      <div className="orchestrator-policy-grid">
        <Metric label="Verdict" value={result?.verdict ?? '--'} />
        <Metric label="Risk" value={typeof result?.risk_score === 'number' ? result.risk_score.toFixed(1) : '--'} />
        <Metric label="Gate" value={policy.level} />
      </div>
      {policy.reasons.length > 0 && (
        <ul className="orchestrator-list">
          {policy.reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      {policy.blocking_conditions.length > 0 && (
        <div className="warning-box compact">
          {policy.blocking_conditions.join(', ')}
        </div>
      )}
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

function findPlan(session: OrchestratorSession, planId: string): Record<string, unknown> | null {
  const plans = session.plan_bundle.plans;
  if (!Array.isArray(plans)) return null;
  return plans.find(plan => typeof plan === 'object' && plan !== null && String((plan as Record<string, unknown>).id) === planId) as Record<string, unknown> | null;
}
