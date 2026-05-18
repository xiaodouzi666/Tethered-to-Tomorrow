import type { HelmMonitorTickResponse, HelmStatusResponse } from '../types/helm';

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

export function getHelmStatus(): Promise<HelmStatusResponse> {
  return request<HelmStatusResponse>('/api/helm/status');
}

export function tickHelmMonitor(): Promise<HelmMonitorTickResponse> {
  return request<HelmMonitorTickResponse>('/api/helm/monitor/tick', { method: 'POST' });
}
