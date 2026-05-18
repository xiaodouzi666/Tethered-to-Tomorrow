import type { CommandPackage } from '../../types/twin';

export function UplinkDelayQueue({ commandPackage }: { commandPackage: CommandPackage | null }) {
  const rows = commandPackage?.execution_log ?? [];
  return (
    <div className="mission-lab-card">
      <div className="mission-lab-card-head">
        <span>Uplink Queue</span>
        <strong>{commandPackage ? `${commandPackage.uplink_delay_s.toFixed(0)}s sim` : '--'}</strong>
      </div>
      {!commandPackage ? (
        <p>No package is queued.</p>
      ) : rows.length === 0 ? (
        <p>Package is ready for approval and simulated uplink.</p>
      ) : (
        <ul className="uplink-log">
          {rows.slice(-4).map((row, index) => (
            <li key={`${row.ts ?? index}-${row.type ?? index}`}>
              <span>{String(row.type ?? 'event')}</span>
              <small>{String(row.message ?? row.action ?? '')}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
