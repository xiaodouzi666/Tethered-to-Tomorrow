import type { ProbeSnapshot } from '../types';

function fmt(value: number | undefined, digits = 2) {
  return typeof value === 'number' ? value.toFixed(digits) : '--';
}

export function StatusCards({ snapshot }: { snapshot: ProbeSnapshot | null }) {
  const s = snapshot?.subsystems;
  const cards = [
    { label: 'Battery', value: `${fmt(s?.power.battery_voltage)} V`, status: s?.power.status ?? 'OFF', hint: `Load ${fmt(s?.power.load_w)} W` },
    { label: 'Thermal', value: `${fmt(s?.thermal.temp_c, 1)} °C`, status: s?.thermal.status ?? 'OFF', hint: `Radiator ${fmt((s?.thermal.radiator_efficiency ?? 0) * 100, 0)}%` },
    { label: 'Comms', value: `${fmt((s?.comms.signal_strength ?? 0) * 100, 0)}%`, status: s?.comms.status ?? 'OFF', hint: `Loss ${fmt((s?.comms.packet_loss ?? 0) * 100, 0)}%` },
    { label: 'Computer', value: `${fmt((s?.computer.cpu_load ?? 0) * 100, 0)}%`, status: s?.computer.status ?? 'OFF', hint: `${fmt(s?.computer.mem_used_mb, 0)} MB` },
    { label: 'Payload', value: s?.payload.enabled ? 'ENABLED' : 'OFF', status: s?.payload.status ?? 'OFF', hint: `Rate ${fmt(s?.payload.sampling_rate, 2)} Hz` }
  ];

  return (
    <div className="status-grid">
      {cards.map(card => (
        <div className="status-card" key={card.label}>
          <div className="status-row">
            <span>{card.label}</span>
            <span className={`subsystem-status ${card.status}`}>{card.status}</span>
          </div>
          <div className="status-value">{card.value}</div>
          <div className="status-hint">{card.hint}</div>
        </div>
      ))}
    </div>
  );
}
