import type { OrchestratorSession } from '../../types/orchestrator';

export function SessionStatusBar({ session }: { session: OrchestratorSession | null }) {
  if (!session) {
    return (
      <div className="orchestrator-status-bar empty">
        <span>Session</span>
        <strong>none</strong>
        <b>IDLE</b>
      </div>
    );
  }
  return (
    <div className={`orchestrator-status-bar ${session.status.toLowerCase()}`}>
      <span>{shortId(session.session_id)}</span>
      <strong>Baseline {shortId(session.baseline.baseline_id)}</strong>
      <b>{session.status}</b>
    </div>
  );
}

function shortId(value: string): string {
  return value.replace(/^(orch|baseline)-/, '').slice(0, 8);
}
