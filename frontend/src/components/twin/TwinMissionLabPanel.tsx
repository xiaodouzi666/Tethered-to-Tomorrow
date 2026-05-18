import { CheckCircle2, FlaskConical, PackageCheck, Radio, Satellite, Send } from 'lucide-react';
import type { useTwinTestbed } from '../../hooks/useTwinTestbed';
import { CommandPackageReview } from './CommandPackageReview';
import { SimulationCampaignMatrix } from './SimulationCampaignMatrix';
import { TwinAssemblyWorkbench } from './TwinAssemblyWorkbench';
import { UplinkDelayQueue } from './UplinkDelayQueue';

type TwinTestbedController = ReturnType<typeof useTwinTestbed>;

export function TwinMissionLabPanel({ testbed }: { testbed: TwinTestbedController }) {
  const busy = testbed.loading !== null;
  return (
    <div className="mission-lab-panel">
      <div className="mission-lab-title">
        <Satellite size={14} />
        Ground Twin Testbed
      </div>
      <div className="mission-lab-stage-row">
        <button disabled={busy} onClick={testbed.start} type="button">
          <FlaskConical size={13} /> Freeze Baseline
        </button>
        <button disabled={busy || !testbed.session} onClick={testbed.injectCommsFault} type="button">
          <Radio size={13} /> Inject Twin Fault
        </button>
        <button disabled={busy || !testbed.session} onClick={testbed.runCampaign} type="button">
          <CheckCircle2 size={13} /> Run Campaign
        </button>
        <button disabled={busy || !testbed.canBuildPackage} onClick={testbed.buildPackage} title={testbed.canBuildPackage ? 'Build package' : testbed.buildPackageGateReason} type="button">
          <PackageCheck size={13} /> Build Package
        </button>
        <button disabled={busy || !testbed.canApprovePackage} onClick={testbed.approvePackage} title={testbed.canApprovePackage ? 'Approve package' : testbed.packageGateReason} type="button">
          Approve
        </button>
        <button className="primary" disabled={busy || !testbed.canExecutePackage} onClick={testbed.executePackage} title={testbed.canExecutePackage ? 'Simulate uplink' : testbed.packageGateReason} type="button">
          <Send size={13} /> Simulate Uplink
        </button>
      </div>

      <div className="mission-lab-strip">
        <div>
          <span>Session</span>
          <strong>{testbed.session ? shortId(testbed.session.session_id) : '--'}</strong>
        </div>
        <div>
          <span>Baseline</span>
          <strong>{testbed.session ? shortId(testbed.session.baseline.baseline_id) : '--'}</strong>
        </div>
        <div>
          <span>Calibration</span>
          <strong>{testbed.session ? `${Math.round(testbed.session.calibration.confidence * 100)}%` : '--'}</strong>
        </div>
        <div>
          <span>Twin faults</span>
          <strong>{testbed.session?.twin_faults.length ?? 0}</strong>
        </div>
        <div>
          <span>Assembly</span>
          <strong>{testbed.assembly ? `v${testbed.assembly.version}` : '--'}</strong>
        </div>
      </div>

      <TwinAssemblyWorkbench testbed={testbed} />
      <SimulationCampaignMatrix campaign={testbed.campaign} />
      <CommandPackageReview commandPackage={testbed.commandPackage} />
      <UplinkDelayQueue commandPackage={testbed.commandPackage} />
      {!testbed.canBuildPackage && testbed.campaign && <div className="gate-note">{testbed.buildPackageGateReason}</div>}
      {testbed.commandPackage && !testbed.canApprovePackage && !testbed.canExecutePackage && <div className="gate-note">{testbed.packageGateReason}</div>}
      {testbed.error && <div className="error-box compact">{testbed.error}</div>}
      {testbed.loading && <small className="mission-lab-note">Running: {testbed.loading}</small>}
    </div>
  );
}

function shortId(value: string): string {
  return value.replace(/^(testbed-|baseline-|cmdpkg-)/, '').slice(0, 8);
}
