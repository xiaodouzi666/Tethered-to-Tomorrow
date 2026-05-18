import { probeClient } from './api/probeClient';

type TelemetryObject = {
  identifier: { namespace: string; key: string };
  name: string;
  type: string;
  location?: string;
  composition?: Array<{ namespace: string; key: string }>;
  telemetry?: any;
};

type TelemetrySource = 'real' | 'twin';

type MetricSpec = {
  key: string;
  name: string;
  unit: string;
};

const METRICS: MetricSpec[] = [
  { key: 'power.battery_voltage', name: 'Battery Voltage', unit: 'V' },
  { key: 'power.load_w', name: 'Load', unit: 'W' },
  { key: 'thermal.temp_c', name: 'Temperature', unit: '°C' },
  { key: 'comms.signal_strength', name: 'Signal Strength', unit: '%' },
  { key: 'comms.packet_loss', name: 'Packet Loss', unit: '%' },
  { key: 'computer.cpu_load', name: 'CPU Load', unit: '%' },
  { key: 'computer.mem_used_mb', name: 'Memory Used', unit: 'MB' },
  { key: 'payload.sampling_rate', name: 'Sampling Rate', unit: 'Hz' }
];

const ONE_MINUTE = 60 * 1000;
const FIVE_MINUTES = 5 * ONE_MINUTE;
const FIFTEEN_MINUTES = 15 * ONE_MINUTE;
const THIRTY_SECONDS = 30 * 1000;
const ONE_HOUR = 60 * ONE_MINUTE;
const ONE_DAY = 24 * ONE_HOUR;

function makeObjectKey(source: TelemetrySource, metricKey: string) {
  return `${source}.${metricKey}`;
}

function parseObjectKey(key: string): { source: TelemetrySource; metric: string } {
  if (key.startsWith('twin.')) return { source: 'twin', metric: key.slice('twin.'.length) };
  if (key.startsWith('real.')) return { source: 'real', metric: key.slice('real.'.length) };
  if (key.startsWith('twin/')) return { source: 'twin', metric: key.slice('twin/'.length) };
  if (key.startsWith('real/')) return { source: 'real', metric: key.slice('real/'.length) };
  return { source: 'real', metric: key };
}

function makeTelemetryObject(metric: MetricSpec, source: TelemetrySource): TelemetryObject {
  const key = makeObjectKey(source, metric.key);
  const isTwin = source === 'twin';
  return {
    identifier: { namespace: 'deeprepair.telemetry', key },
    name: isTwin ? `Twin Predicted ${metric.name}` : metric.name,
    type: 'deeprepair.telemetry',
    location: `deeprepair.telemetry:${source}`,
    telemetry: {
      values: [
        { key: 'utc', source: 'timestamp', name: 'Timestamp', format: 'utc', hints: { domain: 1 } },
        { key: 'value', source: 'value', name: metric.name, units: metric.unit, hints: { range: 1 } }
      ]
    }
  };
}

function makeTimeConductorConfig() {
  return {
    menuOptions: [
      {
        name: 'Realtime',
        timeSystem: 'utc',
        clock: 'local',
        clockOffsets: {
          start: -FIFTEEN_MINUTES,
          end: FIVE_MINUTES
        },
        presets: [
          { label: '15 Minutes + Prediction', bounds: { start: -FIFTEEN_MINUTES, end: FIVE_MINUTES } },
          { label: '5 Minutes + Prediction', bounds: { start: -FIVE_MINUTES, end: FIVE_MINUTES } },
          { label: '1 Minute + Prediction', bounds: { start: -ONE_MINUTE, end: FIVE_MINUTES } }
        ]
      },
      {
        name: 'Fixed',
        timeSystem: 'utc',
        bounds: {
          start: () => Date.now() - FIFTEEN_MINUTES,
          end: () => Date.now()
        },
        zoomOutLimit: ONE_DAY,
        zoomInLimit: ONE_MINUTE,
        presets: [
          { label: 'Last Hour', bounds: { start: () => Date.now() - ONE_HOUR, end: () => Date.now() } },
          { label: 'Last 15 Minutes', bounds: { start: () => Date.now() - FIFTEEN_MINUTES, end: () => Date.now() } }
        ]
      }
    ]
  };
}

function DeepRepairOpenMctPlugin(openmct: any) {
  return function install() {
    if (openmct.types?.addType) {
      openmct.types.addType('deeprepair.telemetry', {
        name: 'Telemetry Channel',
        description: 'DeepRepair real or predicted telemetry channel.'
      });
    }

    const rootIdentifier = { namespace: 'deeprepair.telemetry', key: 'root' };
    const realFolderIdentifier = { namespace: 'deeprepair.telemetry', key: 'real' };
    const twinFolderIdentifier = { namespace: 'deeprepair.telemetry', key: 'twin' };
    const objects = new Map<string, TelemetryObject>();
    objects.set('root', {
      identifier: rootIdentifier,
      name: 'DeepRepair Telemetry',
      type: 'folder',
      location: 'ROOT',
      composition: [realFolderIdentifier, twinFolderIdentifier]
    });
    objects.set('real', {
      identifier: realFolderIdentifier,
      name: 'real/* Probe Telemetry',
      type: 'folder',
      location: 'deeprepair.telemetry:root',
      composition: METRICS.map(m => ({ namespace: 'deeprepair.telemetry', key: makeObjectKey('real', m.key) }))
    });
    objects.set('twin', {
      identifier: twinFolderIdentifier,
      name: 'twin/* Predicted Telemetry',
      type: 'folder',
      location: 'deeprepair.telemetry:root',
      composition: METRICS.map(m => ({ namespace: 'deeprepair.telemetry', key: makeObjectKey('twin', m.key) }))
    });
    METRICS.forEach(metric => {
      objects.set(makeObjectKey('real', metric.key), makeTelemetryObject(metric, 'real'));
      objects.set(makeObjectKey('twin', metric.key), makeTelemetryObject(metric, 'twin'));
    });

    openmct.objects.addRoot(rootIdentifier);
    openmct.objects.addProvider('deeprepair.telemetry', {
      get(identifier: { key: string }) {
        return Promise.resolve(objects.get(identifier.key));
      }
    });

    openmct.composition.addProvider({
      appliesTo(domainObject: TelemetryObject) {
        return domainObject.identifier?.namespace === 'deeprepair.telemetry' && domainObject.type === 'folder';
      },
      load(domainObject: TelemetryObject) {
        return Promise.resolve(domainObject.composition || []);
      }
    });

    openmct.telemetry.addProvider({
      supportsRequest(domainObject: TelemetryObject) {
        return domainObject.type === 'deeprepair.telemetry';
      },
      async request(domainObject: TelemetryObject) {
        const { source, metric } = parseObjectKey(domainObject.identifier.key);
        if (source === 'twin') {
          return requestTwinPrediction(metric, 300, 5);
        }
        const data = await probeClient.history(metric, 300);
        return data.points.map(point => ({ ...point, metric: makeObjectKey('real', metric) }));
      },
      supportsSubscribe(domainObject: TelemetryObject) {
        return domainObject.type === 'deeprepair.telemetry';
      },
      subscribe(domainObject: TelemetryObject, callback: (datum: any) => void) {
        const { source, metric } = parseObjectKey(domainObject.identifier.key);
        if (source === 'twin') {
          return subscribeTwinPrediction(metric, callback);
        }
        return subscribeRealTelemetry(metric, callback);
      }
    });
  };
}

function subscribeRealTelemetry(metric: string, callback: (datum: any) => void) {
        const ws = new WebSocket(probeClient.telemetryWsUrl());
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type !== 'telemetry') return;
            const snapshot = msg.data;
            const value = readSnapshotMetric(snapshot, metric);
            if (typeof value === 'number') {
              callback({ timestamp: snapshot.ts * 1000, value, metric: makeObjectKey('real', metric) });
            }
          } catch (e) {
            console.warn('OpenMCT telemetry parse error', e);
          }
        };
        return () => ws.close();
}

function subscribeTwinPrediction(metric: string, callback: (datum: any) => void) {
  let closed = false;
  let timer: number | undefined;

  async function publishPrediction() {
    try {
      const points = await requestTwinPrediction(metric, 300, 10);
      if (closed) return;
      points.forEach(callback);
    } catch (e) {
      console.warn('OpenMCT twin prediction error', e);
    }
  }

  publishPrediction();
  timer = window.setInterval(publishPrediction, 15000);

  return () => {
    closed = true;
    if (timer !== undefined) window.clearInterval(timer);
  };
}

async function requestTwinPrediction(metric: string, horizonSec: number, dt: number) {
  const res = await fetch(`${probeClient.apiBase}/api/twin/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from_snapshot: 'latest',
      horizon_sec: horizonSec,
      dt,
      stochastic: false,
      actions: []
    })
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  const run = await res.json();
  const now = Date.now();
  const trajectory = Array.isArray(run.trajectory) ? run.trajectory : [];
  return trajectory
    .map((point: Record<string, unknown>, index: number) => {
      const value = readTrajectoryMetric(point, metric);
      const simT = typeof point.sim_t === 'number' ? point.sim_t : index * dt;
      return typeof value === 'number'
        ? { timestamp: now + simT * 1000, value, metric: makeObjectKey('twin', metric) }
        : null;
    })
    .filter(Boolean);
}

function readSnapshotMetric(snapshot: any, metric: string): number | undefined {
  if (!snapshot?.subsystems) return undefined;
  return readNestedNumber(snapshot.subsystems, metric);
}

function readTrajectoryMetric(point: Record<string, unknown>, metric: string): number | undefined {
  const subsystems = point.subsystems;
  if (!subsystems || typeof subsystems !== 'object') return undefined;
  return readNestedNumber(subsystems as Record<string, unknown>, metric);
}

function readNestedNumber(root: Record<string, unknown>, metric: string): number | undefined {
  const [subsystemKey, metricKey] = metric.split('.');
  const subsystem = root[subsystemKey];
  if (!subsystem || typeof subsystem !== 'object') return undefined;
  const value = (subsystem as Record<string, unknown>)[metricKey];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

async function boot() {
  const openmctModule = await import('openmct');
  const openmct = (openmctModule as any).default ?? openmctModule;

  try {
    openmct.setAssetPath('/node_modules/openmct/dist');
  } catch (e) {
    // Some Open MCT versions do not need setAssetPath.
  }

  if (openmct.plugins?.DarkmatterTheme) openmct.install(openmct.plugins.DarkmatterTheme());
  // Keep the testbed page deterministic: skip My Items / LocalStorage so stale
  // Open MCT objects from older real-only versions do not appear in the tree.
  if (openmct.plugins?.UTCTimeSystem) openmct.install(openmct.plugins.UTCTimeSystem());
  if (openmct.plugins?.Conductor) openmct.install(openmct.plugins.Conductor(makeTimeConductorConfig()));

  openmct.install(DeepRepairOpenMctPlugin(openmct));

  openmct.start(document.getElementById('openmct-root'));
}

boot().catch((err) => {
  const root = document.getElementById('openmct-root');
  if (root) {
    root.innerHTML = `<div style="font-family: system-ui; color: #f2f6ff; padding: 24px;">Open MCT failed to start.<pre>${String(err)}</pre></div>`;
  }
  console.error(err);
});
