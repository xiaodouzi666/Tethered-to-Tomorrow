import type { CommandPackage } from '../types/twin';

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

export async function getUplinkPackage(packageId: string): Promise<CommandPackage> {
  return request<CommandPackage>(`/api/uplink/package/${encodeURIComponent(packageId)}`);
}

export async function approveUplinkPackage(packageId: string): Promise<CommandPackage> {
  return request<CommandPackage>(`/api/uplink/package/${encodeURIComponent(packageId)}/approve`, {
    method: 'POST'
  });
}

export async function executeUplinkPackage(packageId: string): Promise<CommandPackage> {
  return request<CommandPackage>(`/api/uplink/package/${encodeURIComponent(packageId)}/execute`, {
    method: 'POST'
  });
}
