import { OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { Maximize2, Minimize2 } from 'lucide-react';
import { useState } from 'react';
import type { ProbeSnapshot } from '../../types';
import type { TwinAssemblyState, TwinEnvironmentConfig, TwinPlaybackFrame, TwinRunResponse } from '../../types/twin';
import { EnvironmentLayer } from './EnvironmentLayer';
import { SpacecraftModel } from './SpacecraftModel';
import { buildTwinVisualState } from './visualState';

interface TwinSceneProps {
  assembly?: TwinAssemblyState | null;
  currentFrame?: TwinPlaybackFrame | null;
  environment: TwinEnvironmentConfig;
  onSelectAssemblyComponent?: (componentId: string) => void;
  onSelectSubsystem?: (subsystem: string) => void;
  result?: TwinRunResponse | null;
  selectedAssemblyComponentId?: string | null;
  selectedSubsystem?: string | null;
  snapshot?: ProbeSnapshot | null;
}

export function TwinScene({
  assembly,
  currentFrame,
  environment,
  onSelectAssemblyComponent,
  onSelectSubsystem,
  result,
  selectedAssemblyComponentId,
  selectedSubsystem,
  snapshot
}: TwinSceneProps) {
  const [expanded, setExpanded] = useState(false);
  const twinState = buildTwinVisualState(snapshot, result, currentFrame);
  const risk = currentFrame ? `${currentFrame.constraint_frame.risk_score.toFixed(1)}` : result ? `${result.risk_score.toFixed(1)}` : '--';

  return (
    <div className={`twin-scene-shell ${expanded ? 'expanded' : ''}`}>
      <Canvas camera={{ position: expanded ? [0, 2.1, 4.7] : [0, 2.5, 6], fov: expanded ? 38 : 45 }}>
        <ambientLight intensity={0.45} />
        <directionalLight position={[5, 5, 2]} intensity={1.15} />
        <EnvironmentLayer environment={environment} />
        <SpacecraftModel
          assembly={assembly}
          currentAction={currentFrame?.current_action}
          onSelectAssemblyComponent={onSelectAssemblyComponent}
          onSelectSubsystem={onSelectSubsystem}
          selectedAssemblyComponentId={selectedAssemblyComponentId}
          selectedSubsystem={selectedSubsystem}
          snapshot={snapshot}
          twinState={twinState}
        />
        <OrbitControls enablePan={false} enableZoom={expanded} autoRotate={false} />
      </Canvas>
      <button
        aria-label={expanded ? 'Collapse 3D view' : 'Expand 3D view'}
        className="twin-scene-expand"
        onClick={() => setExpanded((value) => !value)}
        title={expanded ? 'Collapse 3D view' : 'Expand 3D view'}
        type="button"
      >
        {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
      </button>
      <div className="twin-fault-overlay">
        <span>Mode {twinState.mode}</span>
        <span>Fault {twinState.displayFault}</span>
        <span>Risk {risk}</span>
      </div>
    </div>
  );
}
