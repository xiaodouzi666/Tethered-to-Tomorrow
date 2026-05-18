import { Network } from 'lucide-react';
import { BrainModeToggle } from '../helm/BrainModeToggle';
import { HelmChatPanel } from '../helm/HelmChatPanel';
import { HelmDecisionTrace } from '../helm/HelmDecisionTrace';
import { HelmGraphPanel } from '../helm/HelmGraphPanel';
import { HelmPanel } from '../helm/HelmPanel';
import type { BrainMode, ExecutionMode, OrchestratorSession, ReviewMode } from '../../types/orchestrator';
import { ApprovalBar } from './ApprovalBar';
import { DebriefDrawer } from './DebriefDrawer';
import { ExecutionModeToggle } from './ExecutionModeToggle';
import { RecommendationCard } from './RecommendationCard';
import { ReviewModeToggle } from './ReviewModeToggle';
import { SessionStatusBar } from './SessionStatusBar';
import type { HelmStatusResponse } from '../../types/helm';

export function OrchestratorPanel({
  disabled,
  error,
  brainMode,
  executionMode,
  helmStatus,
  onAbort,
  onApprove,
  onBrainModeChange,
  onHelmDialogue,
  onExecutePlan,
  onExecuteStep,
  onExecutionModeChange,
  onReject,
  onReviewModeChange,
  reviewMode,
  session
}: {
  disabled?: boolean;
  error?: string | null;
  brainMode: BrainMode;
  executionMode: ExecutionMode;
  helmStatus?: HelmStatusResponse | null;
  onAbort: () => void;
  onApprove: () => void;
  onBrainModeChange: (mode: BrainMode) => void;
  onHelmDialogue: (choice: string, message?: string) => void;
  onExecutePlan: () => void;
  onExecuteStep: () => void;
  onExecutionModeChange: (mode: ExecutionMode) => void;
  onReject: () => void;
  onReviewModeChange: (mode: ReviewMode) => void;
  reviewMode: ReviewMode;
  session: OrchestratorSession | null;
}) {
  const fullAutoArmed = Boolean(helmStatus?.auto_monitor_enabled && helmStatus.live_execution_enabled);
  const autoProgressed = Boolean(
    session?.execution_ticket ||
    (session?.execution_log?.length ?? 0) > 0 ||
    ['APPROVED', 'EXECUTING', 'OBSERVING', 'COMPLETED'].includes(session?.status ?? '')
  );
  const autoHandled = Boolean(
    fullAutoArmed &&
    session?.brain_mode === 'gemma_helm' &&
    session.policy_result?.can_auto_step &&
    session.policy_result?.blocking_conditions.length === 0 &&
    autoProgressed
  );
  const classicReviewLocked = Boolean(session?.brain_mode === 'classic_python' && session.review_result?.status === 'approved');
  const controlsDisabled = Boolean(disabled || classicReviewLocked);
  return (
    <div className="orchestrator-panel">
      <div className="orchestrator-title">
        <Network size={14} />
        Recovery Orchestrator
      </div>
      <AutomationModeStrip status={helmStatus} />
      <div className="section-kicker">Brain Mode</div>
      <BrainModeToggle disabled={controlsDisabled} onChange={onBrainModeChange} value={brainMode} />
      <SessionStatusBar session={session} />
      {(brainMode === 'gemma_helm' || session?.brain_mode === 'gemma_helm') && (
        <>
          <HelmPanel session={session} />
          {autoHandled ? (
            <AutoExecutionNotice session={session} />
          ) : (
            <HelmChatPanel disabled={disabled} onDialogue={onHelmDialogue} session={session} />
          )}
          <HelmDecisionTrace session={session} />
          <HelmGraphPanel session={session} />
        </>
      )}
      <div className="section-kicker">Review Mode</div>
      <ReviewModeToggle disabled={controlsDisabled} onChange={onReviewModeChange} value={reviewMode} />
      <div className="section-kicker">Execution Mode</div>
      <ExecutionModeToggle disabled={controlsDisabled} onChange={onExecutionModeChange} value={executionMode} />
      <RecommendationCard session={session} />
      {autoHandled ? (
        <div className="orchestrator-card compact auto-execution-card">
          <div className="orchestrator-card-head">
            <span>Auto Execution</span>
            <strong>{session?.status ?? 'READY'}</strong>
          </div>
          <p>Policy gate approved full-auto low-risk execution. Manual approval controls are hidden unless the plan requires HITL or policy blocks automation.</p>
        </div>
      ) : (
        <ApprovalBar
          disabled={controlsDisabled}
          onAbort={onAbort}
          onApprove={onApprove}
          onExecutePlan={onExecutePlan}
          onExecuteStep={onExecuteStep}
          onReject={onReject}
          session={session}
        />
      )}
      <ExecutionLog session={session} />
      <DebriefDrawer session={session} />
      {session?.graph_bundle && (
        <small className="orchestrator-graph-note">
          Graph: {session.graph_bundle.nodes.length} nodes / {session.graph_bundle.edges.length} edges
        </small>
      )}
      {error && <div className="error-box compact">{error}</div>}
    </div>
  );
}

function AutoExecutionNotice({ session }: { session: OrchestratorSession | null }) {
  const rows = session?.execution_log ?? [];
  const last = rows[rows.length - 1];
  return (
    <div className="helm-card compact auto-execution-card">
      <div className="orchestrator-card-head">
        <span>Helm Auto Mode</span>
        <strong>{session?.policy_result.level ?? 'auto_allowed'}</strong>
      </div>
      <p>
        E4B Helm selected the plan and Python policy gate is handling low-risk live execution.
        High-risk steps still require HITL and will bring the approval controls back.
      </p>
      {last && <small>Last step: {String(last.action ?? 'step')} · {String(last.message ?? last.type ?? 'recorded')}</small>}
    </div>
  );
}

function AutomationModeStrip({ status }: { status?: HelmStatusResponse | null }) {
  if (!status) {
    return (
      <div className="automation-mode-strip idle">
        <span>Automation</span>
        <strong>checking</strong>
      </div>
    );
  }

  const fullAuto = status.auto_monitor_enabled && status.live_execution_enabled;
  const monitorOnly = status.auto_monitor_enabled && !status.live_execution_enabled;
  const label = fullAuto ? 'full auto armed' : monitorOnly ? 'monitor only' : 'manual trigger';
  const detail = fullAuto
    ? 'E4B Helm + Auto Review + Auto Step selected by backend mode.'
    : monitorOnly
      ? 'E4B Helm monitor is on; execution still requires approval/dry-run.'
      : 'Use Analyze Current State to start recovery.';

  return (
    <div className={`automation-mode-strip ${fullAuto ? 'armed' : monitorOnly ? 'monitor' : 'idle'}`}>
      <span>Automation</span>
      <strong>{label}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ExecutionLog({ session }: { session: OrchestratorSession | null }) {
  const rows = session?.execution_log ?? [];
  return (
    <div className="orchestrator-card compact">
      <div className="orchestrator-card-head">
        <span>Execution Log</span>
        <strong>{rows.length}</strong>
      </div>
      {rows.length === 0 ? (
        <p>No dry-run steps yet.</p>
      ) : (
        <ul className="orchestrator-list">
          {rows.slice(-3).map((row, index) => (
            <li key={`${row.ts ?? index}-${row.action ?? index}`}>
              {String(row.action ?? 'step')} · {String(row.message ?? row.type ?? 'dry-run')}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
