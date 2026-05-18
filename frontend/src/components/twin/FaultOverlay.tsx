import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import type { Group, Mesh } from 'three';
import type { TwinVisualState } from './visualState';

interface FaultOverlayProps {
  twinState: TwinVisualState;
}

export function FaultOverlay({ twinState }: FaultOverlayProps) {
  const rootRef = useRef<Group>(null);
  const thermalRef = useRef<Mesh>(null);
  const commsRef = useRef<Mesh>(null);
  const powerRef = useRef<Mesh>(null);
  const sensorRef = useRef<Mesh>(null);
  const thermalFault = isFault(twinState, 'thermal') || twinState.subsystems.thermal.status === 'FAULT';
  const commsFault = isFault(twinState, 'comms') || twinState.subsystems.comms.status === 'FAULT';
  const powerFault = isFault(twinState, 'power') || twinState.subsystems.power.status === 'FAULT';
  const sensorFault = isFault(twinState, 'sensor') || twinState.subsystems.payload.using_backup_sensor === true;

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const pulse = 1 + Math.sin(t * 4.8) * 0.12;
    const fastPulse = 1 + Math.sin(t * 12) * 0.18;

    if (thermalRef.current) {
      thermalRef.current.scale.set(pulse, pulse, pulse);
    }
    if (powerRef.current) {
      powerRef.current.scale.set(1 + Math.sin(t * 8) * 0.05, 1 + Math.sin(t * 8) * 0.12, 1 + Math.sin(t * 8) * 0.05);
    }
    if (sensorRef.current) {
      sensorRef.current.visible = Math.sin(t * 11) > -0.25;
      sensorRef.current.scale.setScalar(fastPulse);
    }
    if (commsRef.current) {
      commsRef.current.visible = Math.sin(t * 9) > 0.05;
      commsRef.current.scale.set(1, 0.85 + Math.sin(t * 7) * 0.16, 1);
    }
  });

  if (!thermalFault && !commsFault && !powerFault && !sensorFault) {
    return null;
  }

  return (
    <group ref={rootRef}>
      {thermalFault && (
        <mesh ref={thermalRef} position={[0, 0.45, -0.05]}>
          <sphereGeometry args={[0.62, 32, 32]} />
          <meshBasicMaterial color="#ff4769" transparent opacity={0.16} depthWrite={false} />
        </mesh>
      )}

      {commsFault && (
        <mesh ref={commsRef} position={[0, 1.82, 0]} rotation={[Math.PI, 0, 0]}>
          <coneGeometry args={[0.88, 1.75, 32, 1, true]} />
          <meshBasicMaterial color="#ffb35f" transparent opacity={0.17} depthWrite={false} />
        </mesh>
      )}

      {powerFault && (
        <mesh ref={powerRef} position={[0, -0.42, 0.18]}>
          <boxGeometry args={[0.9, 0.34, 0.56]} />
          <meshBasicMaterial color="#ffbd5f" transparent opacity={0.2} depthWrite={false} />
        </mesh>
      )}

      {sensorFault && (
        <mesh ref={sensorRef} position={[0.58, 0.12, 0.52]}>
          <sphereGeometry args={[0.28, 24, 24]} />
          <meshBasicMaterial color="#ff61d8" transparent opacity={0.2} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

function isFault(twinState: TwinVisualState, fault: string): boolean {
  return twinState.activeFault === fault || twinState.activeFaults.includes(fault);
}
