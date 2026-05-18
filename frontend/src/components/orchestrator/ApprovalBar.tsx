import { CheckCircle2, FastForward, PauseCircle, Play, XCircle } from 'lucide-react';
import type { OrchestratorSession } from '../../types/orchestrator';

export function ApprovalBar({
  disabled,
  onAbort,
  onApprove,
  onExecutePlan,
  onExecuteStep,
  onReject,
  session
}: {
  disabled?: boolean;
  onAbort: () => void;
  onApprove: () => void;
  onExecutePlan: () => void;
  onExecuteStep: () => void;
  onReject: () => void;
  session: OrchestratorSession | null;
}) {
  const approved = session?.review_result?.status === 'approved';
  const isDryRun = session?.execution_ticket?.dry_run !== false;
  const blockers = session?.policy_result?.blocking_conditions ?? [];
  const approvalBlocked = blockers.length > 0 || session?.policy_result?.allowed === false;
  const classicReviewLocked = Boolean(session?.brain_mode === 'classic_python' && approved);
  const terminal = ['COMPLETED', 'ABORTED', 'STALE'].includes(session?.status ?? '');
  const running = ['EXECUTING', 'OBSERVING'].includes(session?.status ?? '');
  const approveDisabled = disabled || !session || approved || terminal || running || approvalBlocked;
  const rejectDisabled = disabled || !session || approved || terminal || running;
  const executeDisabled = disabled || !approved || terminal || running;
  const abortDisabled = disabled || !session || terminal;
  return (
    <div className="orchestrator-actions">
      <div className="button-row wrap">
        <button disabled={approveDisabled} onClick={onApprove} type="button">
          <CheckCircle2 size={14} /> {approved ? 'Approved' : 'Approve Plan'}
        </button>
        <button className="danger" disabled={rejectDisabled} onClick={onReject} type="button">
          <XCircle size={14} /> Reject
        </button>
        <button disabled={executeDisabled} onClick={onExecuteStep} type="button">
          <Play size={14} /> {isDryRun ? 'Dry-run Step' : 'Live Step'}
        </button>
        <button disabled={executeDisabled} onClick={onExecutePlan} type="button">
          <FastForward size={14} /> {isDryRun ? 'Dry-run Plan' : 'Live Plan'}
        </button>
        <button disabled={abortDisabled} onClick={onAbort} type="button">
          <PauseCircle size={14} /> Abort
        </button>
      </div>
      <small>
        {terminal
          ? 'This recovery session is closed. Run Analyze Current State to start a new decision cycle.'
          : classicReviewLocked
          ? 'Classic Python approval locks this recovery session. Run Analyze Current State again to start a new decision cycle.'
          : (
            <>
              Approval only creates an execution ticket; it does not change Probe state.
              {' '}
              {isDryRun ? 'Dry-run only. No probe command is sent.' : 'Live low-risk execution enabled. HITL actions remain blocked.'}
            </>
          )}
      </small>
      {approvalBlocked && !terminal && (
        <div className="warning-box compact">
          Approval blocked: {blockers.join(', ') || 'policy gate requires reanalysis'}.
        </div>
      )}
    </div>
  );
}
