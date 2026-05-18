import type { OrchestratorSession } from '../../types/orchestrator';

export function HelmDecisionTrace({ session }: { session: OrchestratorSession | null }) {
  if (!session) return null;
  const context = session.helm_context;
  return (
    <div className="helm-card compact">
      <div className="section-kicker">Helm Decision Trace</div>
      <TraceRow label="Diagnosis" value={summary(context?.diagnosis_summary, session.diagnosis)} />
      <TraceRow label="Plans" value={`${context?.plan_summary?.plan_count ?? planCount(session)} candidate(s)`} />
      <TraceRow label="Twin" value={`${session.twin_compare.best_plan_id} · ${session.twin_compare.explanation}`} />
      <TraceRow label="Policy" value={`${session.policy_result.level} · ${session.policy_result.effective_execution_mode}`} />
    </div>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="helm-trace-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function planCount(session: OrchestratorSession): number {
  return Array.isArray(session.plan_bundle.plans) ? session.plan_bundle.plans.length : 0;
}

function summary(...sources: Array<Record<string, unknown> | undefined | null>): string {
  for (const source of sources) {
    if (!source) continue;
    const fault = source.fault_summary;
    if (Array.isArray(fault) && fault.length) return fault.slice(0, 2).join('; ');
    const risk = source.risk_level;
    if (typeof risk === 'string') return risk;
  }
  return '--';
}
