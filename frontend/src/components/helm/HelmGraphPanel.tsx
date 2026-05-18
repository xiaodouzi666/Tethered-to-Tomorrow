import type { OrchestratorSession } from '../../types/orchestrator';

export function HelmGraphPanel({ session }: { session: OrchestratorSession | null }) {
  if (!session?.graph_bundle) return null;
  return (
    <div className="helm-card compact">
      <div className="orchestrator-card-head">
        <span>Graph / Audit Context</span>
        <strong>{session.graph_bundle.nodes.length} nodes</strong>
      </div>
      <p>{session.graph_bundle.summary || 'Graph bundle is ready for the next visualization layer.'}</p>
      <small>{session.graph_bundle.edges.length} causal/action edges available.</small>
    </div>
  );
}
