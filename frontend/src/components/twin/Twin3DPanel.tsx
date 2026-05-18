import { Box } from 'lucide-react';
import type { ProbeSnapshot } from '../../types';
import { useTwinRun } from '../../hooks/useTwinRun';
import { useTwinTestbed } from '../../hooks/useTwinTestbed';
import { OrchestratorPanel } from '../orchestrator/OrchestratorPanel';
import { TwinConstraintPanel } from './TwinConstraintPanel';
import { TwinControls } from './TwinControls';
import { TwinEnvironmentTimeline } from './TwinEnvironmentTimeline';
import { FaultLayersDebugCard } from './FaultLayersDebugCard';
import { TwinInspector } from './TwinInspector';
import { TwinOverlayChart } from './TwinOverlayChart';
import { TwinPlaybackTimeline } from './TwinPlaybackTimeline';
import { TwinPlanCompare } from './TwinPlanCompare';
import { TwinScene } from './TwinScene';
import { TwinMissionLabPanel } from './TwinMissionLabPanel';

interface Twin3DPanelProps {
  snapshot?: ProbeSnapshot | null;
}

export function Twin3DPanel({ snapshot }: Twin3DPanelProps) {
  const twin = useTwinRun(snapshot);
  const testbed = useTwinTestbed();
  const footerMessage = twin.loading
    ? `Running ${twin.loading}`
    : readOrchestratorExplanation(twin.orchestratorSession) ?? twin.runResult?.explanation ?? 'Twin ready';
  const faultLayers = twin.orchestratorSession?.fault_layers ?? twin.runResult?.fault_layers ?? snapshot?.fault_layers ?? null;

  return (
    <section className="panel twin-panel twin-panel-live">
      <div className="panel-title">
        <Box size={16} />
        Digital Twin Panel
        {twin.runResult && <span className={`twin-title-verdict ${twin.runResult.verdict}`}>{twin.runResult.verdict}</span>}
      </div>

      <div className="twin-live-grid">
        <div className="twin-main-stack">
          <TwinScene
            assembly={testbed.assembly}
            currentFrame={twin.currentFrame}
            environment={twin.environment}
            onSelectAssemblyComponent={testbed.selectComponent}
            onSelectSubsystem={twin.setSelectedSubsystem}
            result={twin.runResult}
            selectedAssemblyComponentId={testbed.assembly?.selected_component_id ?? null}
            selectedSubsystem={twin.selectedSubsystem}
            snapshot={snapshot}
          />
          <TwinPlaybackTimeline
            bundle={twin.playbackBundle}
            currentFrame={twin.currentFrame}
            index={twin.playbackIndex}
            isPlaying={twin.isPlaying}
            onPlayChange={twin.setIsPlaying}
            onSeek={twin.setPlaybackIndex}
            onStep={twin.stepPlayback}
          />
          <TwinEnvironmentTimeline events={twin.playbackBundle?.environment_events} />
          <TwinOverlayChart result={twin.runResult} snapshot={snapshot} />
          <TwinPlanCompare
            currentAction={twin.currentFrame?.current_action}
            loadingPlanId={twin.playbackLoadingPlanId}
            onSelectPlan={(planId) => {
              if (twin.compareResult) {
                void twin.loadPlanPlayback(twin.compareResult.compare_id, planId);
              }
            }}
            planBundle={twin.orchestratorSession?.plan_bundle}
            result={twin.compareResult}
            selectedPlanId={twin.selectedPlanId}
          />

          <div className="twin-footer-row baseline">
            <span>Frozen seq {twin.baseline?.captured_seq ?? '--'}</span>
            <span>Live seq {snapshot?.seq ?? twin.snapshotMeta?.seq ?? '--'}</span>
            <span>Digest {twin.baseline ? shortDigest(twin.baseline.state_digest) : '--'} · {twin.baselineStatus}</span>
          </div>
          <div className="twin-footer-row message">
            <span>{footerMessage}</span>
          </div>
          {twin.error && <div className="error-box">{twin.error}</div>}
        </div>
        <div className="twin-side-stack">
          <TwinControls
            baseline={twin.baseline}
            baselineStatus={twin.baselineStatus}
            loading={twin.loading}
            mode={twin.mode}
            onCompare={twin.compare}
            onModeChange={twin.setMode}
            onRefreshBaseline={twin.refreshBaseline}
            onRefreshSnapshot={twin.refreshSnapshot}
            onReset={twin.reset}
            onRun={twin.run}
            onScenarioChange={twin.setScenario}
            scenario={twin.scenario}
          />
          <TwinInspector
            currentFrame={twin.currentFrame}
            inspectorMode={twin.inspectorMode}
            onInspectorModeChange={twin.setInspectorMode}
            playbackIndex={twin.playbackIndex}
            repairTrace={twin.playbackBundle?.repair_trace ?? twin.runResult?.repair_trace ?? []}
            selectedSubsystem={twin.selectedSubsystem}
            snapshot={snapshot}
          />
          <OrchestratorPanel
            disabled={twin.loading !== null}
            error={twin.error}
            brainMode={twin.brainMode}
            executionMode={twin.executionMode}
            helmStatus={twin.helmStatus}
            onAbort={twin.abortSession}
            onApprove={twin.approve}
            onBrainModeChange={twin.setBrainMode}
            onExecutePlan={twin.executePlan}
            onExecuteStep={twin.executeStep}
            onExecutionModeChange={twin.setExecutionMode}
            onHelmDialogue={twin.sendHelmDialogue}
            onReject={twin.reject}
            onReviewModeChange={twin.setReviewMode}
            reviewMode={twin.reviewMode}
            session={twin.orchestratorSession}
          />
          <TwinMissionLabPanel testbed={testbed} />
          <FaultLayersDebugCard summary={faultLayers} />
          <TwinConstraintPanel currentFrame={twin.currentFrame} result={twin.runResult} />
        </div>
      </div>
    </section>
  );
}

function shortDigest(value: string): string {
  return value.slice(0, 8);
}

function readOrchestratorExplanation(session: ReturnType<typeof useTwinRun>['orchestratorSession']): string | undefined {
  if (!session) return undefined;
  const explanation = session.explanation;
  if (explanation && typeof explanation === 'object') {
    const direct = readString(explanation, 'explanation');
    if (direct) return direct;

    const nested = readRecord(explanation, 'explanation');
    const nestedSummary = nested ? readString(nested, 'summary') ?? readString(nested, 'recommended_operator_readout') : undefined;
    if (nestedSummary) return nestedSummary;

    const rule = readRecord(explanation, 'rule_explanation');
    const ruleSummary = rule ? readString(rule, 'summary') ?? readString(rule, 'recommended_operator_readout') : undefined;
    if (ruleSummary) return ruleSummary;
  }
  return session.twin_compare.explanation;
}

function readRecord(source: Record<string, unknown>, key: string): Record<string, unknown> | undefined {
  const value = source[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function readString(source: Record<string, unknown>, key: string): string | undefined {
  const value = source[key];
  return typeof value === 'string' && value.trim() ? value : undefined;
}
