import type { ProbeSnapshot } from '../types';

export function TelemetryDashboard({ snapshot }: { snapshot: ProbeSnapshot | null }) {
  const events = snapshot?.events ?? [];
  return (
    <section className="panel tall">
      <div className="panel-title">Real Probe Telemetry</div>
      <div className="mini-grid">
        <Metric label="seq" value={snapshot?.seq ?? '--'} />
        <Metric label="mode" value={snapshot?.mode ?? '--'} />
        <Metric label="fault" value={snapshot?.active_fault ?? '--'} />
        <Metric label="last ts" value={snapshot ? new Date(snapshot.ts * 1000).toLocaleTimeString() : '--'} />
      </div>
      <div className="schematic">
        <div className="spacecraft-body">
          <div className="module power">PWR</div>
          <div className="module thermal">THM</div>
          <div className="module comms">COM</div>
          <div className="module computer">CPU</div>
          <div className="module payload">PAY</div>
        </div>
        <div className="solar-panel left" />
        <div className="solar-panel right" />
      </div>
      <div className="event-feed">
        <div className="subheading">Recent Events</div>
        {events.length === 0 ? <div className="muted">No events yet.</div> : events.map((e, i) => (
          <div className="event-row" key={`${e.ts}-${i}`}>
            <span>{new Date(e.ts * 1000).toLocaleTimeString()}</span>
            <strong>{e.type}</strong>
            <p>{e.message}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
