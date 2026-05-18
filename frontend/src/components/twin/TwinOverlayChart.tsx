import { useState } from 'react';
import type { ProbeSnapshot } from '../../types';
import type { TwinRunResponse } from '../../types/twin';

interface TwinOverlayChartProps {
  result?: TwinRunResponse | null;
  snapshot?: ProbeSnapshot | null;
}

type MetricKey = 'temp_c' | 'battery_voltage' | 'packet_loss';

interface MetricSpec {
  comparator: '<=' | '>=';
  key: MetricKey;
  label: string;
  max: number;
  min: number;
  readSnapshot: (snapshot?: ProbeSnapshot | null) => number | undefined;
  readTrajectory: (point: Record<string, unknown>) => number | undefined;
  threshold: number;
  thresholdLabel: string;
  unit: string;
}

const metrics: MetricSpec[] = [
  {
    comparator: '<=',
    key: 'temp_c',
    label: 'Temp',
    max: 100,
    min: 20,
    readSnapshot: (snapshot) => snapshot?.subsystems.thermal.temp_c,
    readTrajectory: (point) => readNestedNumber(point, 'thermal', 'temp_c'),
    threshold: 85,
    thresholdLabel: '85C limit',
    unit: 'C'
  },
  {
    comparator: '>=',
    key: 'battery_voltage',
    label: 'Battery',
    max: 13,
    min: 9,
    readSnapshot: (snapshot) => snapshot?.subsystems.power.battery_voltage,
    readTrajectory: (point) => readNestedNumber(point, 'power', 'battery_voltage'),
    threshold: 10.5,
    thresholdLabel: '10.5V min',
    unit: 'V'
  },
  {
    comparator: '<=',
    key: 'packet_loss',
    label: 'Packet loss',
    max: 1,
    min: 0,
    readSnapshot: (snapshot) => snapshot?.subsystems.comms.packet_loss,
    readTrajectory: (point) => readNestedNumber(point, 'comms', 'packet_loss'),
    threshold: 0.6,
    thresholdLabel: '0.60 max',
    unit: ''
  }
];

export function TwinOverlayChart({ result, snapshot }: TwinOverlayChartProps) {
  const [metricKey, setMetricKey] = useState<MetricKey>('temp_c');
  const metric = metrics.find((item) => item.key === metricKey) ?? metrics[0];
  const current = metric.readSnapshot(snapshot) ?? fallbackValue(metric);
  const realY = yForValue(current, metric);
  const thresholdY = yForValue(metric.threshold, metric);
  const predictedSeries = buildSeries(result, metric, current);
  const predictedLast = readLastPredicted(result, metric) ?? current;

  return (
    <div className="twin-chart-block">
      <div className="twin-chart-header">
        <div>
          <div className="twin-section-title">Telemetry Projection</div>
          <strong>{metric.label}: {formatMetric(predictedLast, metric)}</strong>
        </div>
        <div className="twin-metric-tabs" role="tablist" aria-label="Twin chart metric">
          {metrics.map((item) => (
            <button
              className={item.key === metric.key ? 'selected' : ''}
              key={item.key}
              onClick={() => setMetricKey(item.key)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="twin-chart-live">
        <svg viewBox="0 0 360 120" role="img" aria-label={`Twin ${metric.label} projection`}>
          <line x1="18" y1={thresholdY} x2="342" y2={thresholdY} className="twin-threshold-line" />
          <polyline points={`18,${realY} 342,${realY}`} className="twin-real-line" />
          <polyline points={predictedSeries} className="twin-predicted-line" />
          <text x="20" y={Math.max(14, realY - 7)} className="twin-chart-text">real {formatMetric(current, metric)}</text>
          <text x="246" y={Math.max(14, thresholdY - 7)} className="twin-chart-text threshold">{metric.thresholdLabel}</text>
        </svg>
      </div>

      <div className="twin-chart-legend">
        <span><i className="real" />Real</span>
        <span><i className="predicted" />Twin predicted</span>
        <span><i className="threshold" />Threshold</span>
      </div>
    </div>
  );
}

function buildSeries(result: TwinRunResponse | null | undefined, metric: MetricSpec, current: number): string {
  const trajectory = result?.trajectory ?? [];
  if (!trajectory.length) {
    return placeholderSeries(metric, current);
  }
  const maxIndex = Math.max(1, trajectory.length - 1);
  return trajectory
    .map((point, index) => {
      const x = 18 + (index / maxIndex) * 324;
      const value = metric.readTrajectory(point) ?? current;
      return `${x.toFixed(1)},${yForValue(value, metric).toFixed(1)}`;
    })
    .join(' ');
}

function placeholderSeries(metric: MetricSpec, current: number): string {
  const drift = metric.comparator === '<=' ? 0.18 : -0.15;
  const end = clamp(current + (metric.max - metric.min) * drift, metric.min, metric.max);
  return [
    [18, current],
    [126, current + (end - current) * 0.28],
    [234, current + (end - current) * 0.68],
    [342, end]
  ].map(([x, value]) => `${x},${yForValue(value, metric).toFixed(1)}`).join(' ');
}

function readLastPredicted(result: TwinRunResponse | null | undefined, metric: MetricSpec): number | undefined {
  const trajectory = result?.trajectory ?? [];
  for (let index = trajectory.length - 1; index >= 0; index -= 1) {
    const value = metric.readTrajectory(trajectory[index]);
    if (typeof value === 'number') return value;
  }
  return undefined;
}

function readNestedNumber(point: Record<string, unknown>, subsystemKey: string, metricKey: string): number | undefined {
  const subsystems = point.subsystems;
  if (!subsystems || typeof subsystems !== 'object') return undefined;
  const subsystem = (subsystems as Record<string, unknown>)[subsystemKey];
  if (!subsystem || typeof subsystem !== 'object') return undefined;
  const value = (subsystem as Record<string, unknown>)[metricKey];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function yForValue(value: number, metric: MetricSpec): number {
  const clamped = clamp(value, metric.min, metric.max);
  return 104 - ((clamped - metric.min) / (metric.max - metric.min)) * 88;
}

function fallbackValue(metric: MetricSpec): number {
  if (metric.key === 'temp_c') return 42;
  if (metric.key === 'battery_voltage') return 12;
  return 0.04;
}

function formatMetric(value: number, metric: MetricSpec): string {
  if (metric.key === 'temp_c') return `${value.toFixed(1)}${metric.unit}`;
  if (metric.key === 'battery_voltage') return `${value.toFixed(2)}${metric.unit}`;
  return value.toFixed(2);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
