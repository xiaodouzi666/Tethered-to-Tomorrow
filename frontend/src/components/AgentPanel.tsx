import { useState } from 'react';
import { BrainCircuit, ShieldCheck } from 'lucide-react';
import { probeClient } from '../api/probeClient';
import type { DiagnosisResponse, HealthResponse } from '../types';

export function AgentPanel({ health, onUplink }: { health: HealthResponse | null; onUplink: () => void }) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  async function runDiagnosis() {
    setBusy(true);
    setError(null);
    setActionStatus(null);
    try {
      const result = await probeClient.diagnose();
      setDiagnosis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function executeSuggestedAction(action: string) {
    setBusy(true);
    setError(null);
    setActionStatus(`Sending ${action}...`);
    const needsHumanApproval = diagnosis?.safety_gate.high_risk_actions.some(x => x.action === action) ?? false;
    try {
      await probeClient.command(action, needsHumanApproval);
      setActionStatus(`Executed ${action}.`);
      onUplink();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setActionStatus(null);
    } finally {
      setBusy(false);
    }
  }

  const gemma = health?.gemma;
  return (
    <section className="panel agent-panel">
      <div className="panel-title"><BrainCircuit size={16}/> Onboard Agents</div>
      <div className="gemma-status">
        <span className={`status-dot ${gemma?.ready ? 'ok' : 'fault'}`} />
        <div>
          <strong>E4B backend: {gemma?.backend_active ?? 'unknown'}</strong>
          <p>{gemma?.message ?? 'Waiting for probe health...'}</p>
          <p className="muted">Model: {gemma?.model ?? gemma?.model_file ?? 'waiting for config'}</p>
        </div>
      </div>
      <button className="primary" disabled={busy} onClick={runDiagnosis}>
        {busy ? 'Running...' : 'Run Onboard E4B Diagnosis'}
      </button>
      {error && <div className="error-box">{error}</div>}
      {diagnosis && (
        <div className="diagnosis">
          <div className="diagnosis-header"><ShieldCheck size={15}/> Safety-gated Diagnosis</div>
          <div className={`risk ${diagnosis.diagnosis.risk_level}`}>{diagnosis.diagnosis.risk_level}</div>
          <div className="subheading">Fault Summary</div>
          <ul>{diagnosis.diagnosis.fault_summary?.map((x, i) => <li key={i}>{x}</li>)}</ul>
          <div className="subheading">Likely Causes</div>
          {diagnosis.diagnosis.likely_causes?.map((c, i) => (
            <div className="cause" key={i}>
              <strong>{c.cause}</strong>
              <span>{Math.round(c.confidence * 100)}%</span>
              <p>{c.evidence?.join(' · ')}</p>
            </div>
          ))}
          <div className="subheading">Allowed Immediate Actions</div>
          <div className="chips">
            {diagnosis.safety_gate.allowed_actions.map(a => {
              const highRisk = diagnosis.safety_gate.high_risk_actions.some(x => x.action === a);
              return (
                <button
                  className={`chip-button ${highRisk ? 'danger' : ''}`}
                  disabled={busy}
                  key={a}
                  onClick={() => executeSuggestedAction(a)}>
                  {a}{highRisk ? ' (HITL)' : ''}
                </button>
              );
            })}
          </div>
          {actionStatus && <div className="action-status">{actionStatus}</div>}
          {diagnosis.safety_gate.high_risk_actions.length > 0 && (
            <div className="warning-box">High-risk action(s) require explicit human approval.</div>
          )}
        </div>
      )}
    </section>
  );
}
