import { Box, ExternalLink } from 'lucide-react';

export function TwinLaunchSection() {
  return (
    <section className="panel twin-launch-panel">
      <div className="panel-title"><Box size={16} /> Ground Twin Testbed</div>
      <p>
        Open the standalone Twin workbench to freeze baselines, inject ground-only faults, run simulation campaigns, review command packages, and simulate uplink.
        Mission Control keeps live telemetry and the command console, while the Twin workspace uses a wider engineering layout.
      </p>
      <a className="primary-link" href="/twin.html" target="_blank" rel="noreferrer">
        Open Ground Twin <ExternalLink size={14} />
      </a>
    </section>
  );
}
