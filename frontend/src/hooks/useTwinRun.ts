import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  abortOrchestratorSession,
  approveOrchestratorSession,
  executeOrchestratorPlan,
  executeOrchestratorStep,
  getOrchestratorSession,
  getLatestAutoOrchestratorSession,
  rejectOrchestratorSession,
  sendOrchestratorDialogue,
  startLiveOrchestratorSession
} from '../api/orchestratorClient';
import { getHelmStatus } from '../api/helmClient';
import { comparePlans, getPlanPlayback, getTwinSnapshot, runTwin } from '../api/twinClient';
import type { ProbeSnapshot } from '../types';
import type { HelmStatusResponse } from '../types/helm';
import type {
  ExecutionMode,
  OrchestratorSession,
  BrainMode,
  ReviewMode
} from '../types/orchestrator';
import type {
  BaselineMeta,
  BaselineStatus,
  PlanPlaybackBundle,
  TwinEnvironmentConfig,
  TwinMode,
  TwinRunResponse,
  TwinCompareResponse,
  TwinSnapshotResponse
} from '../types/twin';
import {
  buildDemoCompareRequest,
  buildDemoRunRequest,
  type TwinScenario
} from '../twin/demoScenarios';

export type { TwinScenario };
export type ReviewDecision = 'approved' | 'rejected' | null;

const defaultEnvironment: TwinEnvironmentConfig = {
  sun_exposure: 1.0,
  eclipse_factor: 0.2,
  radiation_level: 0.1,
  antenna_alignment_error_deg: 2.0,
  battery_age_factor: 0.93,
  thermal_sink_efficiency: 0.82,
  mission_phase: 'cruise'
};

const STALE_AFTER_SEQ_DELTA = 120;
const LAST_ORCHESTRATOR_SESSION_ID_KEY = 'deeprepair.lastOrchestratorSessionId';

interface PlaybackAnchor {
  compareId: string;
  activeFault?: string;
  changeVersion?: number;
  snapshotSeq?: number;
}

function getBaselineStatus(baseline: BaselineMeta | null, snapshot?: ProbeSnapshot | null): BaselineStatus {
  if (!baseline) return 'none';
  if (
    snapshot &&
    (
      (typeof snapshot.change_version === 'number' && snapshot.change_version !== baseline.captured_change_version) ||
      snapshot.active_fault !== baseline.captured_fault
    )
  ) {
    return 'invalidated';
  }
  if (Date.now() / 1000 > baseline.expires_at) return 'expired';
  if (snapshot && snapshot.seq - baseline.captured_seq > STALE_AFTER_SEQ_DELTA) return 'stale';
  return 'fresh';
}

function shouldBlockPlaybackForStatus(status: BaselineStatus): boolean {
  return status === 'stale' || status === 'invalidated' || status === 'expired';
}

function playbackRefreshMessage(status: BaselineStatus): string {
  return `Baseline is ${status}; run a new analysis or compare before loading plan playback.`;
}

function playbackErrorMessage(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  if (message.includes('Unknown Twin compare id')) {
    return 'Playback cache expired; run a new analysis or compare before loading plan playback.';
  }
  return message;
}

function buildPlaybackAnchor(compareId: string, snapshot?: ProbeSnapshot | null): PlaybackAnchor {
  return {
    compareId,
    activeFault: snapshot?.active_fault,
    changeVersion: snapshot?.change_version,
    snapshotSeq: snapshot?.seq
  };
}

function matchesPlaybackAnchor(anchor: PlaybackAnchor | null, compareId: string, snapshot?: ProbeSnapshot | null): boolean {
  if (!anchor || anchor.compareId !== compareId || !snapshot) return false;
  if (anchor.activeFault !== snapshot.active_fault) return false;
  if (
    typeof anchor.changeVersion === 'number' &&
    typeof snapshot.change_version === 'number' &&
    anchor.changeVersion !== snapshot.change_version
  ) {
    return false;
  }
  if (
    typeof anchor.snapshotSeq === 'number' &&
    typeof snapshot.seq === 'number' &&
    snapshot.seq - anchor.snapshotSeq > STALE_AFTER_SEQ_DELTA
  ) {
    return false;
  }
  return true;
}

function rememberOrchestratorSession(session: OrchestratorSession): void {
  try {
    window.localStorage.setItem(LAST_ORCHESTRATOR_SESSION_ID_KEY, session.session_id);
  } catch {
    // Best-effort restore; localStorage may be unavailable.
  }
}

function forgetOrchestratorSession(): void {
  try {
    window.localStorage.removeItem(LAST_ORCHESTRATOR_SESSION_ID_KEY);
  } catch {
    // Best-effort cleanup only.
  }
}

export function useTwinRun(snapshot?: ProbeSnapshot | null) {
  const [mode, setMode] = useState<TwinMode>('live');
  const [scenario, setScenario] = useState<TwinScenario>('thermal');
  const [brainMode, setBrainMode] = useState<BrainMode>('classic_python');
  const [reviewMode, setReviewMode] = useState<ReviewMode>('manual');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('manual_step');
  const [reviewDecision, setReviewDecision] = useState<ReviewDecision>(null);
  const [baseline, setBaseline] = useState<BaselineMeta | null>(null);
  const [orchestratorSession, setOrchestratorSession] = useState<OrchestratorSession | null>(null);
  const [runResult, setRunResult] = useState<TwinRunResponse | null>(null);
  const [compareResult, setCompareResult] = useState<TwinCompareResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [playbackBundle, setPlaybackBundle] = useState<PlanPlaybackBundle | null>(null);
  const [selectedSubsystem, setSelectedSubsystem] = useState<string>('thermal');
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [inspectorMode, setInspectorMode] = useState<'visible' | 'hidden' | 'split'>('split');
  const [snapshotMeta, setSnapshotMeta] = useState<TwinSnapshotResponse | null>(null);
  const [helmStatus, setHelmStatus] = useState<HelmStatusResponse | null>(null);
  const [loading, setLoading] = useState<'run' | 'compare' | 'snapshot' | 'orchestrator' | null>(null);
  const [playbackLoadingPlanId, setPlaybackLoadingPlanId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const baselineRef = useRef<BaselineMeta | null>(baseline);
  const snapshotRef = useRef<ProbeSnapshot | null | undefined>(snapshot);
  const loadingRef = useRef<typeof loading>(loading);
  const trustedPlaybackAnchorRef = useRef<PlaybackAnchor | null>(null);
  const ignoredAutoSessionIdRef = useRef<string | null>(null);
  baselineRef.current = baseline;
  snapshotRef.current = snapshot;
  loadingRef.current = loading;

  const environment = useMemo(() => {
    if (snapshotMeta?.environment) return snapshotMeta.environment;
    if (snapshot?.mode === 'SAFE_MODE') {
      return { ...defaultEnvironment, thermal_sink_efficiency: 0.9, eclipse_factor: 0.1 };
    }
    return defaultEnvironment;
  }, [snapshot?.mode, snapshotMeta?.environment]);

  const baselineStatus = useMemo<BaselineStatus>(() => getBaselineStatus(baseline, snapshot), [baseline, snapshot]);

  const refreshSnapshot = useCallback(async () => {
    setLoading('snapshot');
    setError(null);
    try {
      setSnapshotMeta(await getTwinSnapshot());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadHelmStatus = async () => {
      try {
        const status = await getHelmStatus();
        if (cancelled) return;
        setHelmStatus(status);
        if (status.auto_monitor_enabled && status.live_execution_enabled) {
          setBrainMode('gemma_helm');
          setReviewMode('auto');
          setExecutionMode('auto_step');
        } else if (status.auto_monitor_enabled) {
          setBrainMode('gemma_helm');
          setReviewMode('assisted');
          setExecutionMode('manual_step');
        }
      } catch {
        // Helm status is optional for the UI; controls remain manually selectable.
      }
    };

    void loadHelmStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyBestCompareResult = useCallback((compare: TwinCompareResponse): void => {
    const best = compare.results.find(plan => plan.plan_id === compare.best_plan_id);
    if (!best) return;
    setRunResult({
      run_id: compare.compare_id,
      verdict: best.verdict,
      risk_score: best.risk_score,
      final_mode: best.final_mode,
      constraints: best.constraints,
      trajectory: best.trajectory,
      final_snapshot: best.final_snapshot,
      explanation: best.explanation,
      fault_layers: best.fault_layers,
      repair_trace: best.repair_trace
    });
  }, []);

  const loadPlanPlayback = useCallback(async (
    compareId: string,
    planId: string,
    playbackBaseline?: BaselineMeta | null,
    options?: { trustFreshCompare?: boolean }
  ) => {
    const status = getBaselineStatus(playbackBaseline ?? baselineRef.current, snapshotRef.current);
    const trustedCurrentCompare =
      status === 'invalidated' &&
      matchesPlaybackAnchor(trustedPlaybackAnchorRef.current, compareId, snapshotRef.current);
    if (shouldBlockPlaybackForStatus(status) && !options?.trustFreshCompare && !trustedCurrentCompare) {
      setPlaybackBundle(null);
      setSelectedPlanId(null);
      setPlaybackIndex(0);
      setPlaybackLoadingPlanId(null);
      setIsPlaying(false);
      trustedPlaybackAnchorRef.current = null;
      setError(playbackRefreshMessage(status));
      return;
    }

    setPlaybackLoadingPlanId(planId);
    setError(null);
    setIsPlaying(false);
    try {
      const bundle = await getPlanPlayback(compareId, planId);
      setPlaybackBundle(bundle);
      setSelectedPlanId(planId);
      setPlaybackIndex(0);
      if (options?.trustFreshCompare) {
        trustedPlaybackAnchorRef.current = buildPlaybackAnchor(compareId, snapshotRef.current);
      }
    } catch (err) {
      setPlaybackBundle(null);
      setSelectedPlanId(null);
      setPlaybackIndex(0);
      trustedPlaybackAnchorRef.current = null;
      setError(playbackErrorMessage(err));
    } finally {
      setPlaybackLoadingPlanId((current) => current === planId ? null : current);
    }
  }, []);

  useEffect(() => {
    if (!shouldBlockPlaybackForStatus(baselineStatus)) return;
    if (
      baselineStatus === 'invalidated' &&
      playbackBundle?.compare_id &&
      matchesPlaybackAnchor(trustedPlaybackAnchorRef.current, playbackBundle.compare_id, snapshot)
    ) {
      return;
    }
    setPlaybackBundle(null);
    setSelectedPlanId(null);
    setPlaybackIndex(0);
    setPlaybackLoadingPlanId(null);
    setIsPlaying(false);
    trustedPlaybackAnchorRef.current = null;
    setError(playbackRefreshMessage(baselineStatus));
  }, [baselineStatus, playbackBundle?.compare_id, snapshot]);

  const analyzeCurrent = useCallback(async () => {
    setLoading('compare');
    setError(null);
    setReviewDecision(null);
    setBaseline(null);
    setOrchestratorSession(null);
    forgetOrchestratorSession();
    setCompareResult(null);
    setRunResult(null);
    setPlaybackBundle(null);
    setSelectedPlanId(null);
    setPlaybackIndex(0);
    setIsPlaying(false);
    trustedPlaybackAnchorRef.current = null;
    try {
      const session = await startLiveOrchestratorSession({
        brain_mode: brainMode,
        reason: 'operator_requested_analysis',
        review_mode: reviewMode,
        execution_mode: executionMode,
        include_compare: true,
        include_explanation: true,
        horizon_sec: 300,
        dt: 1,
        stochastic: false
      });
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
      setBaseline(session.baseline);
      setCompareResult(session.twin_compare);
      applyBestCompareResult(session.twin_compare);
      await loadPlanPlayback(
        session.twin_compare.compare_id,
        session.recommended_plan_id ?? session.twin_compare.best_plan_id,
        session.baseline,
        { trustFreshCompare: true }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [applyBestCompareResult, brainMode, executionMode, loadPlanPlayback, reviewMode]);

  const applyOrchestratorSession = useCallback(async (
    session: OrchestratorSession,
    options?: { trustFreshCompare?: boolean }
  ) => {
    rememberOrchestratorSession(session);
    setOrchestratorSession(session);
    setBaseline(session.baseline);
    setCompareResult(session.twin_compare);
    applyBestCompareResult(session.twin_compare);
    await loadPlanPlayback(
      session.twin_compare.compare_id,
      session.recommended_plan_id ?? session.twin_compare.best_plan_id,
      session.baseline,
      options
    );
  }, [applyBestCompareResult, loadPlanPlayback]);

  useEffect(() => {
    if (mode !== 'live' || orchestratorSession) return undefined;
    let cancelled = false;
    const sessionId = window.localStorage.getItem(LAST_ORCHESTRATOR_SESSION_ID_KEY);
    if (!sessionId) return undefined;

    const restoreSession = async () => {
      setLoading('orchestrator');
      try {
        const session = await getOrchestratorSession(sessionId);
        if (!cancelled) {
          await applyOrchestratorSession(session);
        }
      } catch {
        forgetOrchestratorSession();
      } finally {
        if (!cancelled) setLoading(null);
      }
    };

    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, [applyOrchestratorSession, mode, orchestratorSession]);

  useEffect(() => {
    if (mode !== 'live' || brainMode !== 'gemma_helm') return;
    let cancelled = false;

    const pollLatestAutoSession = async () => {
      try {
        if (loadingRef.current) return;
        const session = await getLatestAutoOrchestratorSession();
        if (cancelled || !session) return;
        if (ignoredAutoSessionIdRef.current === session.session_id) return;
        if (orchestratorSession && orchestratorSession.session_id !== session.session_id) {
          return;
        }
        if (orchestratorSession?.session_id === session.session_id && orchestratorSession.updated_at >= session.updated_at) {
          return;
        }
        if (!orchestratorSession && shouldBlockPlaybackForStatus(getBaselineStatus(session.baseline, snapshotRef.current))) {
          return;
        }
        await applyOrchestratorSession(session, {
          trustFreshCompare: Date.now() / 1000 - session.updated_at < 20
        });
      } catch {
        // Auto monitor polling should never interrupt manual Twin controls.
      }
    };

    void pollLatestAutoSession();
    const timer = window.setInterval(() => {
      void pollLatestAutoSession();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [applyOrchestratorSession, brainMode, mode, orchestratorSession]);

  const refreshBaseline = useCallback(async () => {
    await analyzeCurrent();
  }, [analyzeCurrent]);

  const run = useCallback(async () => {
    if (mode === 'live') {
      await analyzeCurrent();
      return;
    }

    setLoading('run');
    setError(null);
    setReviewDecision(null);
    setOrchestratorSession(null);
    forgetOrchestratorSession();
    setCompareResult(null);
    setPlaybackBundle(null);
    setSelectedPlanId(null);
    setPlaybackIndex(0);
    setIsPlaying(false);
    trustedPlaybackAnchorRef.current = null;
    try {
      const result = await runTwin(buildDemoRunRequest(scenario, environment));
      setRunResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [analyzeCurrent, environment, mode, scenario]);

  const compare = useCallback(async () => {
    if (mode === 'live') {
      await analyzeCurrent();
      return;
    }

    setLoading('compare');
    setError(null);
    setReviewDecision(null);
    setOrchestratorSession(null);
    forgetOrchestratorSession();
    trustedPlaybackAnchorRef.current = null;
    try {
      const result = await comparePlans(buildDemoCompareRequest(scenario, environment));
      setBaseline(result.baseline ?? null);
      setCompareResult(result);
      applyBestCompareResult(result);
      await loadPlanPlayback(result.compare_id, result.best_plan_id, result.baseline ?? null, {
        trustFreshCompare: true
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [analyzeCurrent, applyBestCompareResult, environment, loadPlanPlayback, mode, scenario]);

  const reset = useCallback(() => {
    if (orchestratorSession?.session_id) {
      ignoredAutoSessionIdRef.current = orchestratorSession.session_id;
    }
    setBaseline(null);
    setRunResult(null);
    setCompareResult(null);
    setOrchestratorSession(null);
    forgetOrchestratorSession();
    setReviewDecision(null);
    setPlaybackBundle(null);
    setSelectedPlanId(null);
    setPlaybackIndex(0);
    setIsPlaying(false);
    setError(null);
    trustedPlaybackAnchorRef.current = null;
  }, [orchestratorSession?.session_id]);

  const approve = useCallback(async () => {
    if (baselineStatus !== 'fresh') {
      setReviewDecision(null);
      setError(`Baseline is ${baselineStatus}; refresh baseline before approval.`);
      return;
    }
    if (!orchestratorSession) {
      setError('No orchestrator session is available. Run live analysis first.');
      return;
    }
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await approveOrchestratorSession(orchestratorSession.session_id, {
        plan_id: selectedPlanId ?? orchestratorSession.recommended_plan_id,
        approved_by: 'operator'
      });
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
      setReviewDecision(session.review_result?.status === 'approved' ? 'approved' : null);
      if (session.review_result?.status !== 'approved') {
        setError(`Approval blocked: ${session.policy_result.blocking_conditions.join(', ') || 'policy gate'}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [baselineStatus, orchestratorSession, selectedPlanId]);

  const reject = useCallback(async () => {
    if (!orchestratorSession) {
      setReviewDecision('rejected');
      return;
    }
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await rejectOrchestratorSession(orchestratorSession.session_id, { reason: 'operator_rejected' });
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
      setReviewDecision('rejected');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [orchestratorSession]);

  const executeStep = useCallback(async () => {
    if (!orchestratorSession) {
      setError('No orchestrator session is available. Run live analysis first.');
      return;
    }
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await executeOrchestratorStep(orchestratorSession.session_id);
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [orchestratorSession]);

  const executePlan = useCallback(async () => {
    if (!orchestratorSession) {
      setError('No orchestrator session is available. Run live analysis first.');
      return;
    }
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await executeOrchestratorPlan(orchestratorSession.session_id);
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [orchestratorSession]);

  const abortSession = useCallback(async () => {
    if (!orchestratorSession) return;
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await abortOrchestratorSession(orchestratorSession.session_id, { reason: 'operator_aborted' });
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [orchestratorSession]);

  const sendHelmDialogue = useCallback(async (choice: string, message = '') => {
    if (!orchestratorSession) {
      setError('No orchestrator session is available. Run Helm analysis first.');
      return;
    }
    setLoading('orchestrator');
    setError(null);
    try {
      const session = await sendOrchestratorDialogue(orchestratorSession.session_id, { choice, message });
      rememberOrchestratorSession(session);
      setOrchestratorSession(session);
      if (session.twin_compare?.compare_id && session.recommended_plan_id) {
        await loadPlanPlayback(session.twin_compare.compare_id, session.recommended_plan_id, session.baseline);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [loadPlanPlayback, orchestratorSession]);

  const currentFrame = useMemo(() => {
    if (!playbackBundle?.frames.length) return null;
    return playbackBundle.frames[Math.min(playbackIndex, playbackBundle.frames.length - 1)] ?? null;
  }, [playbackBundle, playbackIndex]);

  const stepPlayback = useCallback((direction: -1 | 1) => {
    setIsPlaying(false);
    setPlaybackIndex((index) => {
      const last = Math.max(0, (playbackBundle?.frames.length ?? 1) - 1);
      return Math.max(0, Math.min(last, index + direction));
    });
  }, [playbackBundle?.frames.length]);

  useEffect(() => {
    refreshSnapshot();
  }, [refreshSnapshot]);

  useEffect(() => {
    if (!isPlaying || !playbackBundle?.frames.length) return undefined;
    const timer = window.setInterval(() => {
      setPlaybackIndex((index) => {
        const last = playbackBundle.frames.length - 1;
        if (index >= last) {
          window.clearInterval(timer);
          setIsPlaying(false);
          return last;
        }
        return index + 1;
      });
    }, 250);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackBundle]);

  return {
    analyzeCurrent,
    approve,
    abortSession,
    baseline,
    baselineStatus,
    brainMode,
    compare,
    compareResult,
    environment,
    error,
    executePlan,
    executeStep,
    executionMode,
    currentFrame,
    helmStatus,
    inspectorMode,
    isPlaying,
    loadPlanPlayback,
    loading,
    mode,
    orchestratorSession,
    playbackBundle,
    playbackIndex,
    playbackLoadingPlanId,
    refreshBaseline,
    refreshSnapshot,
    reject,
    reset,
    reviewDecision,
    reviewMode,
    run,
    runResult,
    scenario,
    selectedPlanId,
    selectedSubsystem,
    setInspectorMode,
    setExecutionMode,
    setBrainMode,
    setIsPlaying,
    setMode,
    setPlaybackIndex,
    setReviewMode,
    setScenario,
    setSelectedSubsystem,
    sendHelmDialogue,
    stepPlayback,
    snapshotMeta
  };
}
