import { useState } from 'react';
import { probeClient } from '../api/probeClient';

const COMMANDS = [
  { action: 'ENTER_SAFE_MODE', human: false },
  { action: 'DISABLE_PAYLOAD', human: false },
  { action: 'RESET_THERMAL_CONTROLLER', human: false },
  { action: 'LOWER_SAMPLING_RATE', human: false },
  { action: 'RESTART_COMMS', human: true },
  { action: 'SWITCH_TO_BACKUP_SENSOR', human: false },
  { action: 'CLEAR_CACHE', human: false },
  { action: 'REBOOT_COMPUTER', human: true }
];

const FAULTS = ['thermal', 'comms', 'power', 'sensor', 'clear'];

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
