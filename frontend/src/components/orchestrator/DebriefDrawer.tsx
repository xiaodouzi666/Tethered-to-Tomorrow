import type { OrchestratorSession } from '../../types/orchestrator';

export function DebriefDrawer({ session }: { session: OrchestratorSession | null }) {
  const report = session?.debrief_report;
  if (!report) {
    return (
      <div className="orchestrator-card compact">
        <div className="section-kicker">Debrief</div>
        <p>Debrief appears after completion, rejection, or abort.</p>
      </div>
    );
  }
  return (
    <details className="orchestrator-debrief" open>
      <summary>Debrief</summary>
      <p>{report.summary}</p>
      <div className="orchestrator-policy-grid">
        <Metric label="Outcome" value={report.final_outcome} />
        <Metric label="Cleared" value={String(report.cleared_faults.length)} />
        <Metric label="Remaining" value={String(report.remaining_root_causes.length)} />
      </div>
      <small>{report.recommended_next_action}</small>
    </details>
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
