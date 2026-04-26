import { probeClient } from './api/probeClient';

type TelemetryObject = {
  identifier: { namespace: string; key: string };
  name: string;
  type: string;
  location?: string;
  composition?: Array<{ namespace: string; key: string }>;
  telemetry?: any;
};

const METRICS = [
  { key: 'power.battery_voltage', name: 'Battery Voltage', unit: 'V' },
  { key: 'power.load_w', name: 'Load', unit: 'W' },
  { key: 'thermal.temp_c', name: 'Temperature', unit: '°C' },
  { key: 'comms.signal_strength', name: 'Signal Strength', unit: '%' },
  { key: 'comms.packet_loss', name: 'Packet Loss', unit: '%' },
  { key: 'computer.cpu_load', name: 'CPU Load', unit: '%' },
  { key: 'computer.mem_used_mb', name: 'Memory Used', unit: 'MB' },
  { key: 'payload.sampling_rate', name: 'Sampling Rate', unit: 'Hz' }
];

function makeTelemetryObject(metric: { key: string; name: string; unit: string }): TelemetryObject {
  return {
    identifier: { namespace: 'deeprepair.telemetry', key: metric.key },
    name: metric.name,
    type: 'deeprepair.telemetry',
    location: 'deeprepair.telemetry:root',
    telemetry: {
      values: [
        { key: 'utc', source: 'timestamp', name: 'Timestamp', format: 'utc', hints: { domain: 1 } },
        { key: 'value', source: 'value', name: metric.name, units: metric.unit, hints: { range: 1 } }
      ]
    }
  };
}

function DeepRepairOpenMctPlugin(openmct: any) {
  return function install() {
    const rootIdentifier = { namespace: 'deeprepair.telemetry', key: 'root' };
    const objects = new Map<string, TelemetryObject>();
    objects.set('root', {
      identifier: rootIdentifier,
      name: 'DeepRepair Real Telemetry',
      type: 'folder',
      location: 'ROOT',
      composition: METRICS.map(m => ({ namespace: 'deeprepair.telemetry', key: m.key }))
    });
    METRICS.forEach(metric => objects.set(metric.key, makeTelemetryObject(metric)));

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
        const metric = domainObject.identifier.key;
        const data = await probeClient.history(metric, 300);
        return data.points;
      },
      supportsSubscribe(domainObject: TelemetryObject) {
        return domainObject.type === 'deeprepair.telemetry';
      },
      subscribe(domainObject: TelemetryObject, callback: (datum: any) => void) {
        const metric = domainObject.identifier.key;
        const ws = new WebSocket(probeClient.telemetryWsUrl());
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type !== 'telemetry') return;
            const snapshot = msg.data;
            const subs = snapshot.subsystems;
            const lookup: Record<string, number> = {
              'power.battery_voltage': subs.power.battery_voltage,
              'power.load_w': subs.power.load_w,
              'thermal.temp_c': subs.thermal.temp_c,
              'comms.signal_strength': subs.comms.signal_strength,
              'comms.packet_loss': subs.comms.packet_loss,
              'computer.cpu_load': subs.computer.cpu_load,
              'computer.mem_used_mb': subs.computer.mem_used_mb,
              'payload.sampling_rate': subs.payload.sampling_rate
            };
            if (metric in lookup) {
              callback({ timestamp: snapshot.ts * 1000, value: lookup[metric], metric });
            }
          } catch (e) {
            console.warn('OpenMCT telemetry parse error', e);
          }
        };
        return () => ws.close();
      }
    });
  };
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
  if (openmct.plugins?.LocalStorage) openmct.install(openmct.plugins.LocalStorage());
  if (openmct.plugins?.MyItems) openmct.install(openmct.plugins.MyItems());
  if (openmct.plugins?.Conductor) openmct.install(openmct.plugins.Conductor());
  if (openmct.plugins?.UTCTimeSystem) openmct.install(openmct.plugins.UTCTimeSystem());

  openmct.install(DeepRepairOpenMctPlugin(openmct));

  // Favor a wide fixed time window for v1 realtime demo.
  try {
    openmct.time.clock('local', { start: -15 * 60 * 1000, end: 0 });
    openmct.time.timeSystem('utc');
  } catch (e) {
    console.warn('OpenMCT time configuration skipped', e);
  }

  openmct.start(document.getElementById('openmct-root'));
}

boot().catch((err) => {
  const root = document.getElementById('openmct-root');
  if (root) {
    root.innerHTML = `<div style="font-family: system-ui; color: #f2f6ff; padding: 24px;">Open MCT failed to start.<pre>${String(err)}</pre></div>`;
  }
  console.error(err);
});
