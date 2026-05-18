import type { TwinComparePlanResult, TwinCompareResponse } from '../../types/twin';

interface TwinPlanCompareProps {
  currentAction?: string | null;
  loadingPlanId?: string | null;
  onSelectPlan?: (planId: string) => void;
  planBundle?: Record<string, unknown> | null;
  result?: TwinCompareResponse | null;
  selectedPlanId?: string | null;
}

const pendingPlans = [
  { id: 'plan-a', name: 'Plan A', posture: 'Conservative', note: 'Risk low · Recovery slow · Mission loss high' },
  { id: 'plan-b', name: 'Plan B', posture: 'Standard', note: 'Balanced recovery path' },
  { id: 'plan-c', name: 'Plan C', posture: 'Aggressive', note: 'Recovery fast · Risk high' }
];

export function TwinPlanCompare({ currentAction, loadingPlanId, onSelectPlan, planBundle, result, selectedPlanId }: TwinPlanCompareProps) {
  const metadata = planMetadata(planBundle);
  const planSelectionLocked = Boolean(loadingPlanId);
  return (
    <div className="twin-plan-compare">
      <div className="twin-section-title">Plan Compare</div>
      <div className="twin-plan-grid">
        {result ? result.results.map((plan) => (
          <PlanCard
            best={plan.plan_id === result.best_plan_id}
            currentAction={selectedPlanId === plan.plan_id ? currentAction : undefined}
            disabled={planSelectionLocked}
            key={plan.plan_id}
            loading={loadingPlanId === plan.plan_id}
            metadata={metadata[plan.plan_id]}
            onSelectPlan={onSelectPlan}
            plan={plan}
            selected={selectedPlanId === plan.plan_id}
          />
        )) : pendingPlans.map((plan) => (
          <div className="twin-plan-card pending" key={plan.id}>
            <div className="twin-plan-card-header">
              <strong>{plan.name}</strong>
              <span>--</span>
            </div>
            <p>{plan.posture}</p>
            <small>{plan.note}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function PlanCard({
  best,
  currentAction,
  disabled,
  loading,
  metadata,
  onSelectPlan,
  selected,
  plan
}: {
  best: boolean;
  currentAction?: string | null;
  disabled?: boolean;
  loading?: boolean;
  metadata?: PlanMetadata;
  onSelectPlan?: (planId: string) => void;
  plan: TwinComparePlanResult;
  selected: boolean;
}) {
  const identity = metadata ?? planIdentity(plan.plan_id);
  const recoveryTime = estimateRecoveryTime(plan);
  const payloadImpact = estimatePayloadImpact(plan);

  return (
    <button
      aria-busy={loading ? 'true' : 'false'}
      className={`twin-plan-card ${best ? 'best' : ''} ${selected ? 'selected' : ''} ${loading ? 'loading' : ''} ${plan.verdict === 'FAIL' ? 'failed' : 'passed'}`}
      disabled={disabled}
      onClick={() => onSelectPlan?.(plan.plan_id)}
      type="button"
    >
      <div className="twin-plan-card-header">
        <strong>{identity.name}</strong>
        <span>{plan.verdict}</span>
      </div>
      <p>{identity.posture}</p>
      <div className="twin-plan-stats">
        <Metric label="Risk" value={plan.risk_score.toFixed(1)} />
        <Metric label="Recovery" value={recoveryTime} />
        <Metric label="Payload" value={payloadImpact} />
      </div>
      {plan.baseline_digest && (
        <small>Baseline {shortDigest(plan.baseline_digest)} · seq {plan.baseline_seq ?? '--'}</small>
      )}
      {identity.note && <small>{identity.note}</small>}
      {best && <small>Best current plan</small>}
      {loading && <small className="loading-note">Loading playback...</small>}
      {currentAction && <small>Now: {currentAction}</small>}
    </button>
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

interface PlanMetadata {
  name: string;
  posture: string;
  note?: string;
}

function planIdentity(planId: string): PlanMetadata {
  if (planId === 'plan-a') return { name: 'Plan A', posture: 'Conservative' };
  if (planId === 'plan-b') return { name: 'Plan B', posture: 'Standard' };
  if (planId === 'plan-c') return { name: 'Plan C', posture: 'Aggressive' };
  return { name: planId, posture: 'Candidate' };
}

function planMetadata(planBundle?: Record<string, unknown> | null): Record<string, PlanMetadata> {
  const plans = planBundle?.plans;
  if (!Array.isArray(plans)) return {};
  const metadata: Record<string, PlanMetadata> = {};
  for (const plan of plans) {
    if (!plan || typeof plan !== 'object') continue;
    const row = plan as Record<string, unknown>;
    const id = readString(row, 'id');
    if (!id) continue;
    metadata[id] = {
      name: readString(row, 'label') ?? id,
      posture: readString(row, 'posture') ?? 'Candidate',
      note: readString(row, 'rationale')
    };
  }
  return metadata;
}

function estimateRecoveryTime(plan: TwinComparePlanResult): string {
  const trajectory = plan.trajectory ?? [];
  if (!trajectory.length) return '--';
  if (plan.verdict === 'FAIL') {
    return `>${Math.round(readSimT(trajectory[trajectory.length - 1]) ?? 0)}s`;
  }
  const safePoint = trajectory.find((point) => readMode(point) === 'SAFE_MODE');
  if (safePoint) return `${Math.round(readSimT(safePoint) ?? 0)}s`;
  const stablePoint = trajectory.find((point) => readMode(point) === plan.final_mode);
  return `${Math.round(readSimT(stablePoint ?? trajectory[trajectory.length - 1]) ?? 0)}s`;
}

function estimatePayloadImpact(plan: TwinComparePlanResult): string {
  const payload = readPayload(plan.final_snapshot);
  if (!payload) return '--';
  const enabled = payload.enabled;
  const status = payload.status;
  const samplingRate = payload.sampling_rate;
  if (enabled === false || status === 'OFF') return 'High';
  if (typeof samplingRate === 'number' && samplingRate < 0.75) return 'Medium';
  return 'Low';
}

function readMode(point: Record<string, unknown>): string | undefined {
  const mode = point.mode;
  return typeof mode === 'string' ? mode : undefined;
}

function readSimT(point: Record<string, unknown>): number | undefined {
  const simT = point.sim_t;
  return typeof simT === 'number' ? simT : undefined;
}

function readPayload(snapshot: Record<string, unknown>): Record<string, unknown> | undefined {
  const subsystems = snapshot.subsystems;
  if (!subsystems || typeof subsystems !== 'object') return undefined;
  const payload = (subsystems as Record<string, unknown>).payload;
  return payload && typeof payload === 'object' ? payload as Record<string, unknown> : undefined;
}

function readString(source: Record<string, unknown>, key: string): string | undefined {
  const value = source[key];
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function shortDigest(value: string): string {
  return value.slice(0, 8);
}
