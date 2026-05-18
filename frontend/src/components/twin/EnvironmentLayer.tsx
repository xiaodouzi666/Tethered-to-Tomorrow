import { Html } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import type { Group } from 'three';
import type { TwinEnvironmentConfig } from '../../types/twin';

interface EnvironmentLayerProps {
  environment: TwinEnvironmentConfig;
}

interface RadiationStreak {
  length: number;
  position: [number, number, number];
  rotation: [number, number, number];
}

export function EnvironmentLayer({ environment }: EnvironmentLayerProps) {
  const radiationGroupRef = useRef<Group>(null);
  const effectiveSun = clamp(environment.sun_exposure * (1 - environment.eclipse_factor), 0, 1.5);
  const eclipse = clamp(environment.eclipse_factor, 0, 1);
  const radiation = clamp(environment.radiation_level, 0, 1);
  const streaks = useRadiationStreaks(radiation);
  const coldLight = eclipse > 0.5;

  useFrame((_, delta) => {
    if (!radiationGroupRef.current) return;
    radiationGroupRef.current.rotation.z += delta * (0.08 + radiation * 0.18);
  });

  return (
    <>
      <ambientLight intensity={coldLight ? 0.22 : 0.38 + effectiveSun * 0.18} color={coldLight ? '#9dc3ff' : '#eef7ff'} />
      <directionalLight position={[4.8, 3.4, 2.2]} intensity={0.65 + effectiveSun * 1.1} color={effectiveSun > 0.8 ? '#fff3d5' : '#d7ecff'} />
      <pointLight position={[-3.2, -2.3, 1.8]} intensity={0.25 + radiation * 0.7} color="#75d7ff" />

      <DirectionArrow
        color="#ffd166"
        label="SUN"
        opacity={0.36 + effectiveSun * 0.34}
        position={[-2.65, 1.55, -0.9]}
        rotation={[0.2, 0, -0.82]}
        scale={0.88 + effectiveSun * 0.18}
      />
      <DirectionArrow
        color="#6ed6ff"
        label="EARTH"
        opacity={0.44}
        position={[2.08, -1.1, -0.18]}
        rotation={[0.15, 0, 2.35]}
        scale={0.82}
      />

      {eclipse > 0.5 && (
        <mesh position={[-3.35, 1.9, -2.6]}>
          <sphereGeometry args={[0.18 + eclipse * 0.12, 24, 24]} />
          <meshBasicMaterial color="#8fb4df" transparent opacity={0.28 + eclipse * 0.22} />
        </mesh>
      )}

      <group ref={radiationGroupRef}>
        {streaks.map((streak, index) => (
          <mesh key={index} position={streak.position} rotation={streak.rotation}>
            <boxGeometry args={[0.018, 0.018, streak.length]} />
            <meshBasicMaterial color={radiation > 0.5 ? '#ffdd8a' : '#8fe8ff'} transparent opacity={0.16 + radiation * 0.3} depthWrite={false} />
          </mesh>
        ))}
      </group>

      <mesh position={[3.2, 2.2, -2.5]}>
        <sphereGeometry args={[0.18 + effectiveSun * 0.1, 24, 24]} />
        <meshBasicMaterial color={effectiveSun > 0.8 ? '#fff0a8' : '#d7ecff'} />
      </mesh>
    </>
  );
}

function DirectionArrow({
  color,
  label,
  opacity,
  position,
  rotation,
  scale
}: {
  color: string;
  label: string;
  opacity: number;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: number;
}) {
  return (
    <group position={position} rotation={rotation} scale={scale}>
      <mesh position={[0, 0.42, 0]}>
        <cylinderGeometry args={[0.025, 0.025, 0.82, 12]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} />
      </mesh>
      <mesh position={[0, 0.9, 0]}>
        <coneGeometry args={[0.095, 0.22, 18]} />
        <meshBasicMaterial color={color} transparent opacity={opacity + 0.16} />
      </mesh>
      <Html position={[0.12, 1.03, 0]} center>
        <span className="twin-scene-env-label">{label}</span>
      </Html>
    </group>
  );
}

function useRadiationStreaks(radiation: number): RadiationStreak[] {
  return useMemo(() => {
    const count = Math.round(8 + radiation * 30);
    return Array.from({ length: count }, (_, index) => {
      const a = pseudo(index + 1);
      const b = pseudo(index + 11);
      const c = pseudo(index + 29);
      return {
        length: 0.36 + pseudo(index + 7) * 0.52,
        position: [-3 + a * 6, -1.8 + b * 3.6, -1.1 + c * 1.8] as [number, number, number],
        rotation: [0.6 + b * 0.8, 0.1 + c * 0.4, -0.9 + a * 0.4] as [number, number, number]
      };
    });
  }, [radiation]);
}

function pseudo(seed: number): number {
  const value = Math.sin(seed * 12.9898) * 43758.5453;
  return value - Math.floor(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
