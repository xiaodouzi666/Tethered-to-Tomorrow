import type { OrchestratorSession } from '../../types/orchestrator';

const labels: Record<string, string> = {
  approve_recommended_plan: 'Approve',
  request_safer_plan: 'Safer plan',
  ask_for_more_explanation: 'Explain',
  abort: 'Abort'
};

export function HelmChatPanel({
  disabled,
  onDialogue,
  session
}: {
  disabled?: boolean;
  onDialogue: (choice: string, message?: string) => void;
  session: OrchestratorSession | null;
}) {
  const question = session?.operator_question;
  const hasApproveChoice = Boolean(question?.choices.includes('approve_recommended_plan'));
  const blockers = session?.policy_result?.blocking_conditions ?? [];
  if (!question) {
    return (
      <div className="helm-card compact">
        <div className="section-kicker">Helm Dialogue</div>
        <p>No operator question is pending.</p>
      </div>
    );
  }
  return (
    <div className="helm-card compact">
      <div className="orchestrator-card-head">
        <span>Helm Dialogue</span>
        <strong>{question.mode}</strong>
      </div>
      <p><b>{question.title}</b></p>
      <p>{question.summary}</p>
      <div className="button-row wrap">
        {!hasApproveChoice && (
          <button disabled title={blockers.join(', ') || 'Policy gate blocked approval'} type="button">
            {labels.approve_recommended_plan}
          </button>
        )}
        {question.choices.map(choice => (
          <button
            className={choice === 'abort' ? 'danger' : ''}
            disabled={disabled}
            key={choice}
            onClick={() => onDialogue(choice)}
            type="button"
          >
            {labels[choice] ?? choice}
          </button>
        ))}
      </div>
      {!hasApproveChoice && (
        <small>
          Approval is disabled because this recommendation is not policy-safe
          {blockers.length ? `: ${blockers.join(', ')}` : ''}.
        </small>
      )}
      {session?.dialogue_log?.length ? (
        <ul className="orchestrator-list">
          {session.dialogue_log.slice(-2).map((turn, index) => (
            <li key={`${turn.ts}-${index}`}>{turn.choice}: {turn.response}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
