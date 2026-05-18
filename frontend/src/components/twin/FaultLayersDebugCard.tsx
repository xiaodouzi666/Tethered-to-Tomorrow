import type { FaultLayerItem, FaultLayerSummary } from '../../types/twin';

interface FaultLayersDebugCardProps {
  summary?: FaultLayerSummary | null;
}

export function FaultLayersDebugCard({ summary }: FaultLayersDebugCardProps) {
  return (
    <div className="fault-layer-card">
      <div className="section-kicker">Fault Layers</div>
      <FaultLayerGroup title="Root Causes" items={summary?.root_causes} />
      <FaultLayerGroup title="Recoverable" items={summary?.recoverable_faults} />
      <FaultLayerGroup title="Mitigations" items={summary?.active_mitigations} />
      <FaultLayerGroup title="Symptoms" items={summary?.symptoms} />
    </div>
  );
}

function FaultLayerGroup({ title, items }: { title: string; items?: FaultLayerItem[] }) {
  const visible = (items ?? []).filter(Boolean);
  return (
    <div className="fault-layer-group">
      <span>{title}</span>
      {visible.length === 0 ? (
        <small>none</small>
      ) : (
        <div className="fault-layer-pills">
          {visible.slice(0, 4).map((item, index) => (
            <code key={`${item.id}-${index}`} className={item.status === 'cleared' ? 'cleared' : ''}>
              {item.id}
              {item.status ? `:${item.status}` : ''}
            </code>
          ))}
          {visible.length > 4 && <code>+{visible.length - 4}</code>}
        </div>
      )}
    </div>
  );
}
