import type { ProbeSnapshot } from '../types';
import type { CSSProperties } from 'react';

export function TelemetryDashboard({ snapshot }: { snapshot: ProbeSnapshot | null }) {
  const events = snapshot?.events ?? [];
  const subsystems = snapshot?.subsystems;
  const solarLevel = clamp((subsystems?.power.solar_input_w ?? 0) / 3.2, 0.12, 1);
  const batteryLevel = clamp(((subsystems?.power.battery_voltage ?? 10.5) - 10.2) / 2.7, 0, 1);
  const heatLevel = clamp(((subsystems?.thermal.temp_c ?? 35) - 35) / 75, 0, 1);
  const packetLoss = clamp(subsystems?.comms.packet_loss ?? 0, 0, 1);
  const cpuLevel = clamp(subsystems?.computer.cpu_load ?? 0, 0, 1);
  const schematicStyle = {
    '--solar-level': solarLevel.toFixed(2),
    '--battery-level': batteryLevel.toFixed(2),
    '--heat-level': heatLevel.toFixed(2),
    '--packet-loss': packetLoss.toFixed(2),
    '--cpu-level': cpuLevel.toFixed(2)
  } as CSSProperties;
  const modules = buildModules(snapshot);

  return (
    <section className="panel tall">
      <div className="panel-title">Real Probe Telemetry</div>
      <div className="mini-grid">
        <Metric label="seq" value={snapshot?.seq ?? '--'} />
        <Metric label="mode" value={snapshot?.mode ?? '--'} />
        <Metric label="fault" value={snapshot?.active_fault ?? '--'} />
        <Metric label="last ts" value={snapshot ? new Date(snapshot.ts * 1000).toLocaleTimeString() : '--'} />
      </div>
      <div className="schematic live-schematic" data-mode={snapshot?.mode ?? 'UNKNOWN'} data-fault={snapshot?.active_fault ?? 'none'} style={schematicStyle}>
        <div className="schematic-starfield" />
        <div className="schematic-chip mode-chip">Mode {snapshot?.mode ?? '--'}</div>
        <div className="schematic-chip fault-chip">Fault {snapshot?.active_fault ?? '--'}</div>
        <div className="solar-panel left live-panel"><span>{formatNumber(subsystems?.power.solar_input_w, 1)} W</span></div>
        <div className="solar-panel right live-panel"><span>Solar</span></div>
        <div className="power-tether left" />
        <div className="power-tether right" />
        <div className="thermal-glow" />
        <div className="comms-wave wave-one" />
        <div className="comms-wave wave-two" />
        <div className="comms-wave wave-three" />
        <div className="spacecraft-body live-bus">
          {modules.map((module) => (
            <div className={`module status-${module.status.toLowerCase()}`} data-module={module.key} key={module.key} title={module.title}>
              <span className="module-light" />
              <strong>{module.code}</strong>
              <small>{module.value}</small>
            </div>
          ))}
        </div>
        <div className="schematic-readouts">
          <Readout label="Battery" value={`${formatNumber(subsystems?.power.battery_voltage, 2)}V`} level={batteryLevel} />
          <Readout label="Thermal" value={`${formatNumber(subsystems?.thermal.temp_c, 1)}C`} level={heatLevel} danger />
          <Readout label="Link loss" value={`${Math.round((subsystems?.comms.packet_loss ?? 0) * 100)}%`} level={packetLoss} danger />
        </div>
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

function Readout({ label, value, level, danger = false }: { label: string; value: string; level: number; danger?: boolean }) {
  const safeLevel = clamp(level, 0, 1);
  return (
    <div
      className={`schematic-readout ${danger ? 'danger' : ''}`}
      style={{ '--level': safeLevel.toFixed(2), '--level-pct': `${Math.round(safeLevel * 100)}%` } as CSSProperties}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <i />
    </div>
  );
}

function buildModules(snapshot: ProbeSnapshot | null) {
  const s = snapshot?.subsystems;
  return [
    {
      key: 'power',
      code: 'PWR',
      status: s?.power.status ?? 'OFF',
      value: `${formatNumber(s?.power.battery_voltage, 1)}V`,
      title: `Battery ${formatNumber(s?.power.battery_voltage, 2)}V, load ${formatNumber(s?.power.load_w, 1)}W`
    },
    {
      key: 'thermal',
      code: 'THM',
      status: s?.thermal.status ?? 'OFF',
      value: `${formatNumber(s?.thermal.temp_c, 0)}C`,
      title: `Temp ${formatNumber(s?.thermal.temp_c, 1)}C, radiator ${Math.round((s?.thermal.radiator_efficiency ?? 0) * 100)}%`
    },
    {
      key: 'comms',
      code: 'COM',
      status: s?.comms.status ?? 'OFF',
      value: `${Math.round((s?.comms.signal_strength ?? 0) * 100)}%`,
      title: `Signal ${Math.round((s?.comms.signal_strength ?? 0) * 100)}%, packet loss ${Math.round((s?.comms.packet_loss ?? 0) * 100)}%`
    },
    {
      key: 'computer',
      code: 'CPU',
      status: s?.computer.status ?? 'OFF',
      value: `${Math.round((s?.computer.cpu_load ?? 0) * 100)}%`,
      title: `CPU ${Math.round((s?.computer.cpu_load ?? 0) * 100)}%, memory ${formatNumber(s?.computer.mem_used_mb, 0)} MB`
    },
    {
      key: 'payload',
      code: 'PAY',
      status: s?.payload.status ?? 'OFF',
      value: s?.payload.enabled ? `${formatNumber(s?.payload.sampling_rate, 2)}Hz` : 'OFF',
      title: s?.payload.enabled ? `Payload sampling ${formatNumber(s?.payload.sampling_rate, 2)}Hz` : 'Payload disabled'
    }
  ];
}

function formatNumber(value: number | undefined, digits: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(digits);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
