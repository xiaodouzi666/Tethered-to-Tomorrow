import { useState } from 'react';
import { BrainCircuit, ShieldCheck } from 'lucide-react';
import { probeClient } from '../api/probeClient';
import type { DiagnosisResponse, HealthResponse } from '../types';

export function AgentPanel({ health }: { health: HealthResponse | null }) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runDiagnosis() {
    setBusy(true);
    setError(null);
    try {
      const result = await probeClient.diagnose();
      setDiagnosis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
          <strong>Gemma backend: {gemma?.backend_active ?? 'unknown'}</strong>
          <p>{gemma?.message ?? 'Waiting for probe health...'}</p>
          <p className="muted">Model: {gemma?.model_file ?? 'waiting for config'}</p>
        </div>
      </div>
      <button className="primary" disabled={busy} onClick={runDiagnosis}>
        {busy ? 'Running...' : 'Run Onboard Gemma Diagnosis'}
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
            {diagnosis.safety_gate.allowed_actions.map(a => <span key={a}>{a}</span>)}
          </div>
          {diagnosis.safety_gate.high_risk_actions.length > 0 && (
            <div className="warning-box">High-risk action(s) require explicit human approval.</div>
          )}
        </div>
      )}
    </section>
  );
}
