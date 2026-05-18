import type { CommandPackage } from '../../types/twin';

export function CommandPackageReview({ commandPackage }: { commandPackage: CommandPackage | null }) {
  return (
    <div className="mission-lab-card">
      <div className="mission-lab-card-head">
        <span>Command Package</span>
        <strong>{commandPackage?.status ?? 'not built'}</strong>
      </div>
      {!commandPackage ? (
        <p>Build a package after the campaign selects the most robust plan.</p>
      ) : (
        <>
          <div className="package-summary">
            <span>{shortId(commandPackage.package_id)}</span>
            <span>Plan {commandPackage.plan_id}</span>
            <span>Pass {(commandPackage.pass_rate * 100).toFixed(0)}%</span>
            <span>Risk {commandPackage.risk_score.toFixed(1)}</span>
            <span>Asm v{commandPackage.assembly_version}</span>
            <span>{commandPackage.gate_status}</span>
          </div>
          {commandPackage.gate_reason && <div className="gate-note">{commandPackage.gate_reason}</div>}
          <ol className="package-steps">
            {commandPackage.steps.map((step, index) => (
              <li key={`${step.action}-${index}`}>
                <strong>{step.action}</strong>
                <small>{step.preconditions.slice(0, 2).join(' · ')}</small>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function shortId(value: string): string {
  return value.replace(/^cmdpkg-/, '').slice(0, 8);
}
