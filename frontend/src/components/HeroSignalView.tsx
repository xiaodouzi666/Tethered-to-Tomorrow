import { useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import type { PickingInfo } from '@deck.gl/core';
import { Radio } from 'lucide-react';

const DSN = [
  { name: 'Goldstone DSN', position: [-116.89, 35.43] as [number, number], color: [35, 180, 255] as [number, number, number] },
  { name: 'Madrid DSN', position: [-4.25, 40.43] as [number, number], color: [35, 180, 255] as [number, number, number] },
  { name: 'Canberra DSN', position: [148.98, -35.40] as [number, number], color: [35, 180, 255] as [number, number, number] }
];

const PROBE = { name: 'Voyager-RPi-01', position: [78, 18] as [number, number] };

interface HeroSignalViewProps {
  linkStatus: 'connecting' | 'online' | 'offline';
  mode?: string;
  activeFault?: string;
  uplinkPulse?: number;
}

export function HeroSignalView({ linkStatus, mode, activeFault, uplinkPulse = 0 }: HeroSignalViewProps) {
  const pulse = uplinkPulse % 2 === 1;

  const layers = useMemo(() => {
    const arcs = DSN.map((dsn) => ({
      from: dsn.position,
      to: PROBE.position,
      name: `${dsn.name} → ${PROBE.name}`,
      color: dsn.color
    }));

    return [
      new ArcLayer({
        id: 'dsn-uplink-arcs',
        data: arcs,
        getSourcePosition: (d: any) => d.from,
        getTargetPosition: (d: any) => d.to,
        getSourceColor: () => pulse ? [255, 190, 70] : [55, 170, 255],
        getTargetColor: () => pulse ? [255, 90, 90] : [132, 232, 255],
        getWidth: pulse ? 5 : 3,
        greatCircle: true,
        pickable: true
      }),
      new ScatterplotLayer({
        id: 'dsn-points',
        data: DSN,
        getPosition: (d: any) => d.position,
        getRadius: 220000,
        radiusUnits: 'meters',
        getFillColor: [50, 180, 255, 220],
        pickable: true
      }),
      new ScatterplotLayer({
        id: 'probe-point',
        data: [PROBE],
        getPosition: (d: any) => d.position,
        getRadius: pulse ? 520000 : 360000,
        radiusUnits: 'meters',
        getFillColor: pulse ? [255, 120, 60, 230] : [255, 210, 80, 230],
        pickable: true
      }),
      new TextLayer({
        id: 'labels',
        data: [...DSN, PROBE],
        getPosition: (d: any) => d.position,
        getText: (d: any) => d.name,
        getSize: 13,
        getColor: [220, 240, 255],
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'bottom',
        getPixelOffset: [0, -14]
      })
    ];
  }, [pulse]);

  const tooltip = ({ object }: PickingInfo) => object?.name;

  return (
    <section className="hero-card">
      <div className="hero-overlay">
        <div className="hero-title"><Radio size={16}/> Signal Delay View</div>
        <div className="hero-stats">
          <span>One-way delay: <strong>~23h 14m</strong></span>
          <span>Demo acceleration: <strong>8s</strong></span>
          <span>Mode: <strong>{mode || 'UNKNOWN'}</strong></span>
          <span>Fault: <strong>{activeFault || 'none'}</strong></span>
          <span className={`status-pill ${linkStatus}`}>Probe {linkStatus}</span>
        </div>
      </div>
      <DeckGL
        initialViewState={{ longitude: 10, latitude: 18, zoom: 1.15, bearing: 0, pitch: 28 }}
        controller={true}
        layers={layers}
        getTooltip={tooltip}
      />
      <div className="earth-bg" />
    </section>
  );
}
