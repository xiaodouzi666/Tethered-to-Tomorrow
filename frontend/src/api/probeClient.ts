import type { DiagnosisResponse, HealthResponse, ProbeSnapshot } from '../types';

const apiBase = import.meta.env.VITE_PROBE_API_BASE || 'http://localhost:8010';
const wsBase = import.meta.env.VITE_PROBE_WS_BASE || 'ws://localhost:8010';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    }
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const probeClient = {
  apiBase,
  wsBase,
  health: () => request<HealthResponse>('/health'),
  current: () => request<ProbeSnapshot>('/api/telemetry/current'),
  history: (metric: string, limit = 300) => request<{metric: string; points: Array<{timestamp:number; value:number; metric:string}>}>(`/api/telemetry/history?metric=${encodeURIComponent(metric)}&limit=${limit}`),
  injectFault: (fault: string) => request<{ok:boolean; fault:string; snapshot:ProbeSnapshot}>('/api/faults/inject', { method: 'POST', body: JSON.stringify({ fault }) }),
  command: (action: string, humanApproved = false) => request('/api/command', { method: 'POST', body: JSON.stringify({ action, params: {}, source: 'mission-control-ui', human_approved: humanApproved }) }),
  diagnose: () => request<DiagnosisResponse>('/api/agent/diagnose', { method: 'POST', body: JSON.stringify({ reason: 'manual-ui' }) }),
  gemmaStatus: () => request('/api/agent/gemma/status'),
  agentsDesign: () => request('/api/agents/design'),
  telemetryWsUrl: () => `${wsBase}/ws/telemetry`
};
