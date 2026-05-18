import type {
  AbortSessionRequest,
  ApproveSessionRequest,
  DebriefReport,
  GraphBundle,
  HelmDialogueRequest,
  OrchestratorSession,
  OrchestratorStartRequest,
  RejectSessionRequest
} from '../types/orchestrator';

const apiBase = import.meta.env.VITE_PROBE_API_BASE || 'http://localhost:8010';

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

export function startLiveOrchestratorSession(payload: OrchestratorStartRequest): Promise<OrchestratorSession> {
  return request<OrchestratorSession>('/api/orchestrator/live/start', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function getOrchestratorSession(sessionId: string): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}`);
}

export async function getLatestAutoOrchestratorSession(): Promise<OrchestratorSession | null> {
  const result = await request<{ ok: boolean; session: OrchestratorSession | null }>('/api/orchestrator/auto-session/latest');
  return result.session ?? null;
}

export function approveOrchestratorSession(
  sessionId: string,
  payload: ApproveSessionRequest
): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function rejectOrchestratorSession(
  sessionId: string,
  payload: RejectSessionRequest
): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/reject`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function executeOrchestratorStep(sessionId: string): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/execute-step`, {
    method: 'POST'
  });
}

export function executeOrchestratorPlan(sessionId: string): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/execute-plan`, {
    method: 'POST'
  });
}

export function abortOrchestratorSession(
  sessionId: string,
  payload: AbortSessionRequest
): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/abort`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function sendOrchestratorDialogue(
  sessionId: string,
  payload: HelmDialogueRequest
): Promise<OrchestratorSession> {
  return request<OrchestratorSession>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/dialogue`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function getOrchestratorDebrief(sessionId: string): Promise<DebriefReport> {
  return request<DebriefReport>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/debrief`);
}

export function getOrchestratorGraph(sessionId: string): Promise<GraphBundle> {
  return request<GraphBundle>(`/api/orchestrator/session/${encodeURIComponent(sessionId)}/graph`);
}
