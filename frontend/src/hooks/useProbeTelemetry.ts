import { useEffect, useMemo, useState } from 'react';
import { probeClient } from '../api/probeClient';
import type { HealthResponse, ProbeSnapshot } from '../types';

interface UseProbeTelemetryResult {
  snapshot: ProbeSnapshot | null;
  health: HealthResponse | null;
  linkStatus: 'connecting' | 'online' | 'offline';
  error: string | null;
  refreshHealth: () => Promise<void>;
}

export function useProbeTelemetry(): UseProbeTelemetryResult {
  const [snapshot, setSnapshot] = useState<ProbeSnapshot | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [linkStatus, setLinkStatus] = useState<'connecting' | 'online' | 'offline'>('connecting');
  const [error, setError] = useState<string | null>(null);

  const refreshHealth = async () => {
    try {
      const h = await probeClient.health();
      setHealth(h);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLinkStatus('offline');
    }
  };

  useEffect(() => {
    refreshHealth();
    probeClient.current().then(setSnapshot).catch(() => undefined);
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closedByComponent = false;

    const connect = () => {
      setLinkStatus('connecting');
      ws = new WebSocket(probeClient.telemetryWsUrl());
      ws.onopen = () => {
        setLinkStatus('online');
        setError(null);
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'telemetry') {
            setSnapshot(msg.data);
          }
        } catch (err) {
          console.warn('bad telemetry message', err);
        }
      };
      ws.onerror = () => {
        setLinkStatus('offline');
      };
      ws.onclose = () => {
        if (!closedByComponent) {
          setLinkStatus('offline');
          retryTimer = setTimeout(connect, 1500);
        }
      };
    };

    connect();
    return () => {
      closedByComponent = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  return useMemo(() => ({ snapshot, health, linkStatus, error, refreshHealth }), [snapshot, health, linkStatus, error]);
}
