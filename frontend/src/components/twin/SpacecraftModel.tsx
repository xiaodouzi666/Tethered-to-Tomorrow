import { Html, useGLTF } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { Suspense, useMemo, useRef } from 'react';
import { Color, MeshStandardMaterial, Quaternion, Vector3 } from 'three';
import type { Group, Material, Mesh } from 'three';
import type { ProbeSnapshot, SubsystemStatus } from '../../types';
import type { TwinAssemblyState, TwinComponentInstance } from '../../types/twin';
import type { TwinVisualState } from './visualState';
import voyagerModelUrl from '../../../../assets/Voyager.glb?url';

interface SpacecraftModelProps {
  assembly?: TwinAssemblyState | null;
  currentAction?: string | null;
  onSelectAssemblyComponent?: (componentId: string) => void;
  onSelectSubsystem?: (subsystem: string) => void;
  selectedAssemblyComponentId?: string | null;
  selectedSubsystem?: string | null;
  snapshot?: ProbeSnapshot | null;
  twinState: TwinVisualState;
}

const palette = {
  ok: '#43d68c',
  warn: '#f6c85f',
  fault: '#f05d7a',
  safe: '#3aaeea',
  disabled: '#6b778c',
  bus: '#2b7fc0',
  beam: '#6ed6ff'
};

const VOYAGER_MODEL_POSITION: [number, number, number] = [0, -0.7, -0.85];
const VOYAGER_MODEL_SCALE = 0.2;
const ANTENNA_PIVOT: [number, number, number] = [0, -0.4, -0.85];
const ANTENNA_PIVOT_OFFSET: [number, number, number] = [0, 0.4, 0.85];
const ANTENNA_POINT = new Vector3(...ANTENNA_PIVOT);
const EARTH_POINT = new Vector3(1.96, -1.0, -0.14);
const EARTH_AXIS = EARTH_POINT.clone().sub(ANTENNA_POINT).normalize();
const VOYAGER_PARTS = {
  power: [2.85, -0.9, 1.9] as [number, number, number],
  thermal: [0.0, -0.85, 1.9] as [number, number, number],
  comms: [0.0, 1.35, 0.0] as [number, number, number],
  computer: [0.15, -0.25, 1.25] as [number, number, number],
  payload: [0.8, 3.8, 4.0] as [number, number, number],
  sensor: [0.5, 7.3, 9.2] as [number, number, number]
};

export function SpacecraftModel({
  assembly,
  currentAction,
  onSelectAssemblyComponent,
  onSelectSubsystem,
  selectedAssemblyComponentId,
  selectedSubsystem,
  twinState
}: SpacecraftModelProps) {
  const rollRef = useRef<Group>(null);
  const powerStatus = twinState.subsystems.power.status;
  const thermalStatus = twinState.subsystems.thermal.status;
  const commsStatus = twinState.subsystems.comms.status;
  const computerStatus = twinState.subsystems.computer.status;
  const payloadStatus = twinState.subsystems.payload.status;
  const sensorStatus = twinState.subsystems.sensor.status;
  const payloadEnabled = twinState.subsystems.payload.enabled !== false && payloadStatus !== 'OFF';
  const sensorFault = sensorStatus === 'FAULT' || twinState.activeFaults.includes('sensor') || twinState.subsystems.payload.using_backup_sensor === true;
  const safeMode = twinState.mode === 'SAFE_MODE';
  const busStatus = worstStatus(thermalStatus, computerStatus);
  const busColor = statusColor(busStatus, safeMode);
  const radiatorColor = statusColor(thermalStatus, safeMode);
  const powerColor = statusColor(powerStatus, safeMode);
  const antennaColor = statusColor(commsStatus, safeMode);
  const payloadColor = statusColor(payloadStatus, safeMode, !payloadEnabled);
  const sensorColor = sensorFault ? palette.fault : statusColor(sensorStatus, safeMode);
  const heatGlow = thermalStatus === 'FAULT' || twinState.activeFaults.includes('thermal');
  const commsFault = commsStatus === 'FAULT' || twinState.activeFaults.includes('comms');
  const powerFault = powerStatus === 'FAULT' || twinState.activeFaults.includes('power');
  const payloadFault = !payloadEnabled;
  const beamOpacity = commsStatus === 'FAULT' ? 0.08 : commsStatus === 'WARN' ? 0.18 : 0.28;

  useFrame(({ clock }) => {
    if (!rollRef.current) return;
    rollRef.current.setRotationFromAxisAngle(EARTH_AXIS, clock.elapsedTime * 0.18);
  });

  return (
    <group>
      <group position={ANTENNA_PIVOT}>
        <group ref={rollRef} position={ANTENNA_PIVOT_OFFSET}>
          <Suspense fallback={
            <PrimitiveSpacecraft
              antennaColor={antennaColor}
              beamOpacity={beamOpacity}
              heatGlow={heatGlow}
              payloadColor={payloadColor}
              payloadEnabled={payloadEnabled}
              powerStatus={powerStatus}
              radiatorColor={radiatorColor}
              safeMode={safeMode}
              sensorColor={sensorColor}
              sensorFault={sensorFault}
              busColor={busColor}
              powerColor={powerColor}
            />
          }>
            <group position={VOYAGER_MODEL_POSITION} scale={VOYAGER_MODEL_SCALE}>
              <VoyagerBody busStatus={busStatus} safeMode={safeMode} />
              <StatusBeacons
                antennaColor={antennaColor}
                commsStatus={commsStatus}
                payloadColor={payloadColor}
                payloadEnabled={payloadEnabled}
                powerColor={powerColor}
                powerStatus={powerStatus}
                radiatorColor={radiatorColor}
                sensorColor={sensorColor}
                sensorFault={sensorFault}
                thermalStatus={thermalStatus}
              />
              <FaultGlows
                commsFault={commsFault}
                currentAction={currentAction}
                payloadFault={payloadFault}
                powerFault={powerFault}
                selectedSubsystem={selectedSubsystem}
                sensorFault={sensorFault}
                thermalFault={heatGlow}
              />
              <SubsystemHitTargets onSelectSubsystem={onSelectSubsystem} selectedSubsystem={selectedSubsystem} />
              <AssemblyComponentNodes
                assembly={assembly}
                onSelectAssemblyComponent={onSelectAssemblyComponent}
                selectedAssemblyComponentId={selectedAssemblyComponentId}
              />
            </group>
          </Suspense>

          <Html position={[0, -1.08, 0]} center>
            <div className={`twin-scene-label ${twinState.displayFault !== 'none' ? 'fault' : ''}`}>
              {twinState.displayFault === 'none' ? twinState.mode : twinState.displayFault}
            </div>
          </Html>
        </group>
      </group>
      <EarthPointingBeam color={antennaColor} fault={commsStatus === 'FAULT'} opacity={beamOpacity} />
    </group>
  );
}

function AssemblyComponentNodes({
  assembly,
  onSelectAssemblyComponent,
  selectedAssemblyComponentId
}: {
  assembly?: TwinAssemblyState | null;
  onSelectAssemblyComponent?: (componentId: string) => void;
  selectedAssemblyComponentId?: string | null;
}) {
  if (!assembly) return null;
  const installed = assembly.components.filter((component) => component.install_state !== 'removed');
  return (
    <>
      {installed.map((component) => (
        <AssemblyComponentNode
          component={component}
          key={component.instance_id}
          onSelectAssemblyComponent={onSelectAssemblyComponent}
          selected={component.instance_id === selectedAssemblyComponentId}
        />
      ))}
    </>
  );
}

function AssemblyComponentNode({
  component,
  onSelectAssemblyComponent,
  selected
}: {
  component: TwinComponentInstance;
  onSelectAssemblyComponent?: (componentId: string) => void;
  selected: boolean;
}) {
  const ref = useRef<Mesh>(null);
  const position = componentPosition(component);
  const rotation = componentRotation(component);
  const scale = componentScale(component);
  const fault = component.health_state === 'fault' || component.active_faults.length > 0;
  const color = fault ? palette.fault : selected ? '#9ee7ff' : componentSubsystemColor(component.subsystem);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const pulse = fault || selected ? 1 + Math.sin(clock.elapsedTime * (fault ? 8 : 5)) * 0.16 : 1;
    ref.current.scale.set(scale[0] * pulse, scale[1] * pulse, scale[2] * pulse);
  });

  return (
    <group position={position} rotation={rotation}>
      <mesh
        ref={ref}
        onClick={(event) => {
          event.stopPropagation();
          onSelectAssemblyComponent?.(component.instance_id);
        }}
      >
        <sphereGeometry args={[0.12, 18, 18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={fault ? 0.7 : selected ? 0.55 : 0.18} roughness={0.28} />
      </mesh>
      {(selected || fault) && (
        <Html position={[0, 0.2, 0]} center>
          <div className={`twin-scene-label ${fault ? 'fault' : ''}`}>
            {component.display_name}
          </div>
        </Html>
      )}
    </group>
  );
}

interface PrimitiveSpacecraftProps {
  antennaColor: string;
  beamOpacity: number;
  busColor: string;
  heatGlow: boolean;
  payloadColor: string;
  payloadEnabled: boolean;
  powerColor: string;
  powerStatus: SubsystemStatus;
  radiatorColor: string;
  safeMode: boolean;
  sensorColor: string;
  sensorFault: boolean;
}

function PrimitiveSpacecraft({
  antennaColor,
  beamOpacity,
  busColor,
  heatGlow,
  payloadColor,
  payloadEnabled,
  powerColor,
  powerStatus,
  radiatorColor,
  safeMode,
  sensorColor,
  sensorFault
}: PrimitiveSpacecraftProps) {
  return (
    <>
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[1.42, 0.58, 0.76]} />
        <meshStandardMaterial color={busColor} emissive={busColor} emissiveIntensity={0.12} roughness={0.42} />
      </mesh>

      <mesh position={[0, -0.42, 0.18]}>
        <boxGeometry args={[0.72, 0.22, 0.42]} />
        <meshStandardMaterial color={powerColor} emissive={powerColor} emissiveIntensity={0.22} roughness={0.38} />
      </mesh>

      <SolarPanel side="left" status={powerStatus} safeMode={safeMode} />
      <SolarPanel side="right" status={powerStatus} safeMode={safeMode} />
      <Radiator color={radiatorColor} heatGlow={heatGlow} />
      <HighGainAntenna color={antennaColor} opacity={beamOpacity} />
      <PayloadModule color={payloadColor} enabled={payloadEnabled} />
      <SensorPod color={sensorColor} fault={sensorFault} />
    </>
  );
}

function VoyagerBody({ busStatus, safeMode }: { busStatus: SubsystemStatus; safeMode: boolean }) {
  const { scene } = useGLTF(voyagerModelUrl);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((object) => {
      const mesh = object as Mesh;
      if (!mesh.isMesh) return;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      if (Array.isArray(mesh.material)) {
        mesh.material = mesh.material.map((material) => cloneStatusMaterial(material, busStatus, safeMode));
      } else if (mesh.material) {
        mesh.material = cloneStatusMaterial(mesh.material, busStatus, safeMode);
      }
    });
    return clone;
  }, [busStatus, safeMode, scene]);

  return (
    <primitive object={model} />
  );
}

function StatusBeacons({
  antennaColor,
  commsStatus,
  payloadColor,
  payloadEnabled,
  powerColor,
  powerStatus,
  radiatorColor,
  sensorColor,
  sensorFault,
  thermalStatus
}: {
  antennaColor: string;
  commsStatus: SubsystemStatus;
  payloadColor: string;
  payloadEnabled: boolean;
  powerColor: string;
  powerStatus: SubsystemStatus;
  radiatorColor: string;
  sensorColor: string;
  sensorFault: boolean;
  thermalStatus: SubsystemStatus;
}) {
  return (
    <>
      <StatusBeacon color={powerColor} fault={powerStatus === 'FAULT'} position={VOYAGER_PARTS.power} show={powerStatus !== 'OK'} />
      <StatusBeacon color={radiatorColor} fault={thermalStatus === 'FAULT'} position={VOYAGER_PARTS.thermal} show={thermalStatus !== 'OK'} />
      <StatusBeacon color={antennaColor} fault={commsStatus === 'FAULT'} position={VOYAGER_PARTS.comms} show={commsStatus !== 'OK'} />
      <StatusBeacon color={payloadColor} fault={!payloadEnabled} position={VOYAGER_PARTS.payload} show={!payloadEnabled} />
      <StatusBeacon color={sensorColor} fault={sensorFault} position={VOYAGER_PARTS.sensor} show={sensorFault} />
    </>
  );
}

function StatusBeacon({
  color,
  fault,
  position,
  show
}: {
  color: string;
  fault: boolean;
  position: [number, number, number];
  show: boolean;
}) {
  const ref = useRef<Group>(null);

  useFrame(({ clock }) => {
    if (!ref.current || !fault) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 8) * 0.18;
    ref.current.scale.setScalar(pulse);
  });

  if (!show) return null;

  return (
    <group ref={ref} position={position}>
      <mesh>
        <sphereGeometry args={[fault ? 0.22 : 0.16, 18, 18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={fault ? 0.78 : 0.38} roughness={0.22} />
      </mesh>
      {fault && (
        <mesh>
          <sphereGeometry args={[0.52, 18, 18]} />
          <meshBasicMaterial color={palette.fault} transparent opacity={0.16} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

function FaultGlows({
  commsFault,
  currentAction,
  payloadFault,
  powerFault,
  selectedSubsystem,
  sensorFault,
  thermalFault
}: {
  commsFault: boolean;
  currentAction?: string | null;
  payloadFault: boolean;
  powerFault: boolean;
  selectedSubsystem?: string | null;
  sensorFault: boolean;
  thermalFault: boolean;
}) {
  const thermalRef = useRef<Mesh>(null);
  const commsRef = useRef<Group>(null);
  const powerRef = useRef<Mesh>(null);
  const payloadRef = useRef<Mesh>(null);
  const sensorRef = useRef<Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const slowPulse = 1 + Math.sin(t * 5) * 0.13;
    const fastPulse = 1 + Math.sin(t * 10) * 0.18;
    if (thermalRef.current) thermalRef.current.scale.setScalar(slowPulse);
    if (powerRef.current) powerRef.current.scale.set(1 + Math.sin(t * 8) * 0.12, 1 + Math.sin(t * 8) * 0.08, 1 + Math.sin(t * 8) * 0.12);
    if (payloadRef.current) payloadRef.current.scale.setScalar(slowPulse);
    if (sensorRef.current) {
      sensorRef.current.visible = Math.sin(t * 12) > -0.2;
      sensorRef.current.scale.setScalar(fastPulse);
    }
    if (commsRef.current) {
      commsRef.current.visible = Math.sin(t * 9) > -0.05;
      commsRef.current.scale.setScalar(fastPulse);
    }
  });

  const actionSubsystem = subsystemForAction(currentAction);
  const showAction = Boolean(actionSubsystem);
  if (!thermalFault && !commsFault && !powerFault && !payloadFault && !sensorFault && !selectedSubsystem && !showAction) return null;

  return (
    <>
      {thermalFault && (
        <mesh ref={thermalRef} position={VOYAGER_PARTS.thermal}>
          <sphereGeometry args={[1.15, 32, 32]} />
          <meshBasicMaterial color="#ff4769" transparent opacity={0.18} depthWrite={false} />
        </mesh>
      )}

      {commsFault && (
        <group ref={commsRef} position={VOYAGER_PARTS.comms}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.64, 0.06, 12, 36]} />
            <meshBasicMaterial color="#ff7990" transparent opacity={0.72} depthWrite={false} />
          </mesh>
          <mesh>
            <sphereGeometry args={[0.72, 24, 24]} />
            <meshBasicMaterial color="#ff4769" transparent opacity={0.16} depthWrite={false} />
          </mesh>
        </group>
      )}

      {powerFault && (
        <mesh ref={powerRef} position={VOYAGER_PARTS.power} rotation={[0.1, 0.2, -0.45]}>
          <boxGeometry args={[1.15, 0.42, 0.52]} />
          <meshBasicMaterial color="#ffbd5f" transparent opacity={0.28} depthWrite={false} />
        </mesh>
      )}

      {payloadFault && (
        <mesh ref={payloadRef} position={VOYAGER_PARTS.payload}>
          <sphereGeometry args={[0.62, 24, 24]} />
          <meshBasicMaterial color="#9aa7b8" transparent opacity={0.2} depthWrite={false} />
        </mesh>
      )}

      {sensorFault && (
        <mesh ref={sensorRef} position={VOYAGER_PARTS.sensor}>
          <sphereGeometry args={[0.54, 24, 24]} />
          <meshBasicMaterial color="#ff61d8" transparent opacity={0.28} depthWrite={false} />
        </mesh>
      )}
      {selectedSubsystem && (
        <mesh position={partPosition(selectedSubsystem)}>
          <sphereGeometry args={[0.78, 28, 28]} />
          <meshBasicMaterial color="#9ee7ff" transparent opacity={0.13} depthWrite={false} />
        </mesh>
      )}
      {actionSubsystem && (
        <ActionPulse subsystem={actionSubsystem} />
      )}
    </>
  );
}

function ActionPulse({ subsystem }: { subsystem: string }) {
  const ref = useRef<Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 12) * 0.22;
    ref.current.scale.setScalar(pulse);
  });
  return (
    <mesh ref={ref} position={partPosition(subsystem)}>
      <sphereGeometry args={[0.72, 28, 28]} />
      <meshBasicMaterial color="#9ee7ff" transparent opacity={0.24} depthWrite={false} />
    </mesh>
  );
}

function SubsystemHitTargets({
  onSelectSubsystem,
  selectedSubsystem
}: {
  onSelectSubsystem?: (subsystem: string) => void;
  selectedSubsystem?: string | null;
}) {
  const ids = ['power', 'thermal', 'comms', 'computer', 'payload', 'sensor'];
  return (
    <>
      {ids.map((id) => (
        <mesh
          key={id}
          onClick={(event) => {
            event.stopPropagation();
            onSelectSubsystem?.(id);
          }}
          position={partPosition(id)}
        >
          <sphereGeometry args={[0.5, 16, 16]} />
          <meshBasicMaterial
            color={selectedSubsystem === id ? '#9ee7ff' : '#ffffff'}
            opacity={selectedSubsystem === id ? 0.12 : 0.001}
            transparent
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

function EarthPointingBeam({ color, fault, opacity }: { color: string; fault: boolean; opacity: number }) {
  const ref = useRef<Group>(null);
  const { midpoint, length, quaternion } = useMemo(() => {
    const direction = EARTH_POINT.clone().sub(ANTENNA_POINT);
    const beamLength = direction.length();
    const beamMidpoint = ANTENNA_POINT.clone().add(EARTH_POINT).multiplyScalar(0.5);
    const beamQuaternion = new Quaternion().setFromUnitVectors(
      new Vector3(0, 1, 0),
      direction.normalize()
    );
    return { midpoint: beamMidpoint, length: beamLength, quaternion: beamQuaternion };
  }, []);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    ref.current.visible = !fault || Math.sin(clock.elapsedTime * 9) > -0.1;
  });

  return (
    <group ref={ref} position={midpoint} quaternion={quaternion}>
      <mesh>
        <cylinderGeometry args={[0.035, 0.008, length, 18, 1, true]} />
        <meshBasicMaterial color={color} transparent opacity={Math.max(0.12, opacity)} depthWrite={false} />
      </mesh>
      <mesh position={[0, length / 2, 0]}>
        <sphereGeometry args={[0.055, 16, 16]} />
        <meshBasicMaterial color="#6ed6ff" transparent opacity={0.55} depthWrite={false} />
      </mesh>
    </group>
  );
}

function cloneStatusMaterial(material: Material, status: SubsystemStatus, safeMode: boolean): Material {
  const cloned = material.clone();
  if (cloned instanceof MeshStandardMaterial) {
    const tint = new Color(statusColor(status, safeMode));
    cloned.color.lerp(tint, status === 'FAULT' ? 0.22 : safeMode ? 0.18 : status === 'WARN' ? 0.14 : 0.04);
    cloned.emissive = tint;
    cloned.emissiveIntensity = status === 'FAULT' ? 0.16 : safeMode ? 0.09 : 0.035;
    cloned.roughness = Math.min(0.72, cloned.roughness + 0.08);
  }
  return cloned;
}

function SolarPanel({ side, status, safeMode }: { side: 'left' | 'right'; status: SubsystemStatus; safeMode: boolean }) {
  const sign = side === 'left' ? -1 : 1;
  const panelColor = statusColor(status, safeMode);
  return (
    <group position={[sign * 1.18, 0, 0]}>
      <mesh position={[sign * 0.33, 0, 0]}>
        <boxGeometry args={[0.76, 0.045, 0.82]} />
        <meshStandardMaterial color={panelColor} emissive={panelColor} emissiveIntensity={0.18} roughness={0.32} />
      </mesh>
      {[-0.24, 0, 0.24].map((z) => (
        <mesh key={z} position={[sign * 0.33, 0.026, z]}>
          <boxGeometry args={[0.72, 0.018, 0.025]} />
          <meshBasicMaterial color="#0b1830" transparent opacity={0.6} />
        </mesh>
      ))}
    </group>
  );
}

function Radiator({ color, heatGlow }: { color: string; heatGlow: boolean }) {
  return (
    <group position={[0, 0.43, -0.05]}>
      <mesh>
        <boxGeometry args={[0.78, 0.05, 0.42]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={heatGlow ? 0.35 : 0.14} roughness={0.28} />
      </mesh>
      {[-0.28, -0.14, 0, 0.14, 0.28].map((x) => (
        <mesh key={x} position={[x, 0.04, 0]}>
          <boxGeometry args={[0.035, 0.05, 0.48]} />
          <meshBasicMaterial color="#bfe9ff" transparent opacity={0.34} />
        </mesh>
      ))}
    </group>
  );
}

function HighGainAntenna({ color, opacity }: { color: string; opacity: number }) {
  return (
    <group position={[0, 0.92, 0]}>
      <mesh rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.36, 0.18, 32]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.24} roughness={0.24} />
      </mesh>
      <mesh position={[0, 0.2, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.035, 0.035, 0.48, 16]} />
        <meshStandardMaterial color="#bfe9ff" emissive="#6ed6ff" emissiveIntensity={0.2} />
      </mesh>
      <mesh position={[0, 0.95, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.68, 1.5, 32, 1, true]} />
        <meshBasicMaterial color={palette.beam} transparent opacity={opacity} depthWrite={false} />
      </mesh>
    </group>
  );
}

function PayloadModule({ color, enabled }: { color: string; enabled: boolean }) {
  return (
    <group position={[0, -0.02, 0.54]}>
      <mesh>
        <boxGeometry args={[0.55, 0.3, 0.28]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={enabled ? 0.26 : 0.04} roughness={0.38} />
      </mesh>
      <mesh position={[0, 0, 0.2]}>
        <cylinderGeometry args={[0.16, 0.16, 0.14, 24]} />
        <meshStandardMaterial color={enabled ? '#9ee7ff' : '#7b8496'} emissive={enabled ? '#6ed6ff' : '#000000'} emissiveIntensity={enabled ? 0.18 : 0} />
      </mesh>
    </group>
  );
}

function SensorPod({ color, fault }: { color: string; fault: boolean }) {
  return (
    <group position={[0.58, 0.12, 0.52]}>
      <mesh>
        <sphereGeometry args={[0.15, 24, 24]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={fault ? 0.42 : 0.18} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0, 0.17]}>
        <cylinderGeometry args={[0.06, 0.08, 0.13, 16]} />
        <meshStandardMaterial color="#c8ecff" emissive="#6ed6ff" emissiveIntensity={fault ? 0.08 : 0.2} />
      </mesh>
    </group>
  );
}

function statusColor(status: SubsystemStatus, safeMode: boolean, disabled = false): string {
  if (disabled || status === 'OFF') return palette.disabled;
  if (status === 'FAULT') return palette.fault;
  if (status === 'WARN') return palette.warn;
  if (safeMode) return palette.safe;
  return status === 'OK' ? palette.ok : palette.bus;
}

function worstStatus(a: SubsystemStatus, b: SubsystemStatus): SubsystemStatus {
  const rank: Record<SubsystemStatus, number> = { OK: 0, OFF: 1, WARN: 2, FAULT: 3 };
  return rank[a] >= rank[b] ? a : b;
}

function partPosition(subsystem: string): [number, number, number] {
  return (VOYAGER_PARTS as Record<string, [number, number, number]>)[subsystem] ?? [0, 0, 0];
}

function componentPosition(component: TwinComponentInstance): [number, number, number] {
  const p = component.position || {};
  return [Number(p.x ?? 0), Number(p.y ?? 0), Number(p.z ?? 0)];
}

function componentRotation(component: TwinComponentInstance): [number, number, number] {
  const r = component.rotation || {};
  return [Number(r.x ?? 0), Number(r.y ?? 0), Number(r.z ?? 0)];
}

function componentScale(component: TwinComponentInstance): [number, number, number] {
  const s = component.scale || {};
  return [Number(s.x ?? 1), Number(s.y ?? 1), Number(s.z ?? 1)];
}

function componentSubsystemColor(subsystem: string): string {
  if (subsystem === 'power') return palette.warn;
  if (subsystem === 'thermal') return '#ff8a65';
  if (subsystem === 'comms') return palette.beam;
  if (subsystem === 'computer') return '#a78bfa';
  if (subsystem === 'sensor') return '#ff61d8';
  if (subsystem === 'payload') return '#64d6a7';
  return '#dceaff';
}

function subsystemForAction(action?: string | null): string | null {
  if (!action) return null;
  if (action.includes('THERMAL')) return 'thermal';
  if (action.includes('COMMS')) return 'comms';
  if (action.includes('PAYLOAD')) return 'payload';
  if (action.includes('SAFE_MODE')) return 'power';
  if (action.includes('CACHE') || action.includes('REBOOT')) return 'computer';
  if (action.includes('SENSOR')) return 'sensor';
  return null;
}

useGLTF.preload(voyagerModelUrl);
