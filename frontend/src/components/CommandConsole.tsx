import { useState } from 'react';
import { probeClient } from '../api/probeClient';

const COMMANDS = [
  { action: 'ENTER_SAFE_MODE', human: false },
  { action: 'EXIT_SAFE_MODE', human: true },
  { action: 'DISABLE_PAYLOAD', human: false },
  { action: 'ENABLE_PAYLOAD', human: false },
  { action: 'RESET_THERMAL_CONTROLLER', human: false },
  { action: 'LOWER_SAMPLING_RATE', human: false },
  { action: 'RESTART_COMMS', human: true },
  { action: 'SWITCH_TO_BACKUP_SENSOR', human: false },
  { action: 'SWITCH_TO_BACKUP_THRUSTER', human: true },
  { action: 'ENABLE_THRUSTER_HEATERS', human: true },
  { action: 'SHUT_DOWN_PRIMARY_ROLL_HEATER', human: false },
  { action: 'RESTORE_HEATER_POWER', human: true },
  { action: 'SHED_NONESSENTIAL_LOAD', human: false },
  { action: 'DISABLE_INSTRUMENT', human: false },
  { action: 'RESTORE_INSTRUMENT', human: false },
  { action: 'REALLOCATE_POWER_BUDGET', human: false },
  { action: 'ISOLATE_TELEMETRY_PATH', human: false },
  { action: 'RELOCATE_FDS_CODE', human: true },
  { action: 'VERIFY_TELEMETRY_RECOVERY', human: false },
  { action: 'CLEAR_CACHE', human: false },
  { action: 'REBOOT_COMPUTER', human: true }
];

const FAULTS = ['thermal', 'comms', 'power', 'sensor', 'attitude', 'fds', 'power_margin', 'clear'];

export function CommandConsole({ onUplink }: { onUplink: () => void }) {
  const [log, setLog] = useState<string>('Ready.');
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>, label: string, uplink = false) => {
    setBusy(true);
    setLog(`Sending ${label}...`);
    try {
      const result = await fn();
      setLog(JSON.stringify(result, null, 2));
      if (uplink) onUplink();
    } catch (err) {
      setLog(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel command-panel">
      <div className="panel-title">Command & Fault Console</div>
      <div className="subheading">Inject Fault</div>
      <div className="button-row wrap">
        {FAULTS.map(fault => (
          <button disabled={busy} key={fault} onClick={() => run(() => probeClient.injectFault(fault), `fault:${fault}`)}>
            {fault === 'clear' ? 'Clear Faults' : `Inject ${fault}`}
          </button>
        ))}
      </div>
      <div className="subheading">Simulator State</div>
      <div className="button-row wrap">
        <button
          className="danger"
          disabled={busy}
          onClick={() => run(() => probeClient.resetState(), 'reset-probe-state', true)}
          type="button"
        >
          Reset Probe State
        </button>
      </div>
      <div className="subheading">White-listed Uplink Commands</div>
      <div className="button-row wrap">
        {COMMANDS.map(cmd => (
          <button
            disabled={busy}
            key={cmd.action}
            className={cmd.human ? 'danger' : ''}
            onClick={() => run(() => probeClient.command(cmd.action, cmd.human), cmd.action, true)}>
            {cmd.action}{cmd.human ? ' (HITL)' : ''}
          </button>
        ))}
      </div>
      <pre className="console-output">{log}</pre>
    </section>
  );
}
