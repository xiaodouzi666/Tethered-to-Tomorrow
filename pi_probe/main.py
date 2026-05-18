from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pi_probe.agents.onboard import OnboardAgentRuntime
from pi_probe.config import settings
from pi_probe.helm import E4BHelmRuntime, HelmDialogueRequest, HelmStatusResponse
from pi_probe.orchestrator import (
    AbortSessionRequest,
    ApproveSessionRequest,
    DebriefReport,
    GraphBundle,
    OrchestratorSession,
    OrchestratorSessionStore,
    OrchestratorStartRequest,
    RecoveryOrchestrator,
    RejectSessionRequest,
)
from pi_probe.probe.state import ALLOWED_COMMANDS, HIGH_RISK_COMMANDS, SpacecraftState, TelemetryHistory
from pi_probe.twin.augmentation import build_augmented_scenario
from pi_probe.twin.assembly import TwinAssemblyStore, build_rule_troubleshooting, catalog_response
from pi_probe.twin.baseline_store import BaselineStore, FrozenBaseline
from pi_probe.twin.calibration import calibrate_baseline
from pi_probe.twin.campaign import run_campaign
from pi_probe.twin.command_package import (
    CommandPackageStore,
    approve_command_package,
    build_command_package,
    mark_uplink_started,
)
from pi_probe.twin.engine import TwinEngine
from pi_probe.twin.faults import KNOWN_FAULTS
from pi_probe.twin.rehearsal import RehearsalStore
from pi_probe.twin.schemas import (
    BaselineMeta,
    CampaignResponse,
    CommandPackage,
    CommandPackageRequest,
    ComponentFaultInjectionRequest,
    ComponentFaultInjectionResponse,
    ComponentLinkRequest,
    ComponentOperationRequest,
    ComponentParametersRequest,
    ComponentReplaceRequest,
    ComponentTransformRequest,
    EnvironmentConfig,
    FaultInjectionRequest,
    FreezeBaselineResponse,
    GroundTestbedSession,
    PlanPlaybackBundle,
    RecoveryEvaluationRequest,
    RecoveryEvaluationResponse,
    ReviewSuggestion,
    SimulationCampaignRequest,
    TroubleshootingRequest,
    TroubleshootingResponse,
    TwinAssemblyState,
    TwinPlanCandidate,
    TwinCompareFromBaselineRequest,
    TwinComparePlanResult,
    TwinCompareRequest,
    TwinCompareResponse,
    TwinRunRequest,
    TwinRunResponse,
    TwinSnapshotResponse,
)
from pi_probe.twin.testbed import GroundTestbedStore
from pi_probe.twin.visualization import build_playback_bundle

app = FastAPI(title="DeepRepair Probe Emulator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_allow_origin] if settings.cors_allow_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = SpacecraftState()
state_lock = threading.RLock()
history = TelemetryHistory(limit=settings.history_limit)
agents = OnboardAgentRuntime()
helm_runtime = E4BHelmRuntime(
    agents=agents,
    allowed_commands=sorted(ALLOWED_COMMANDS),
    high_risk_commands=sorted(HIGH_RISK_COMMANDS),
    auto_monitor_enabled=settings.helm_auto_monitor_enabled,
    live_execution_enabled=settings.helm_live_execution_enabled,
    brain_mode_default=settings.brain_mode,
)
clients: Set[WebSocket] = set()
rehearsals = RehearsalStore()
baseline_store = BaselineStore(ttl_sec=300)
compare_playback_cache: Dict[str, Dict[str, Any]] = {}
orchestrator_sessions = OrchestratorSessionStore(ttl_sec=900)
testbed_sessions = GroundTestbedStore(ttl_sec=900)
command_packages = CommandPackageStore(ttl_sec=900)
assemblies = TwinAssemblyStore(ttl_sec=900)
last_helm_auto_session_id: Optional[str] = None
PACKAGE_PASS_RATE_THRESHOLD = 0.8


class FaultRequest(BaseModel):
    fault: str = Field(..., description="thermal | comms | power | sensor | attitude | fds | telemetry | power_margin | clear")


class CommandRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    source: str = "mission-control-ui"
    human_approved: bool = False


class DiagnoseRequest(BaseModel):
    reason: str = "manual-ui"


class CandidatePlansRequest(BaseModel):
    snapshot: Optional[Dict[str, Any]] = None


class TwinExplainRequest(BaseModel):
    twin_result: Dict[str, Any]
    snapshot: Optional[Dict[str, Any]] = None


class ScenarioRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class AugmentationRequest(BaseModel):
    profile: str = "thermal"
    difficulty: str = "medium"
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)


class RecoveryPlanRequest(BaseModel):
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    horizon_sec: int = Field(default=300, ge=1, le=3600)
    dt: float = Field(default=1.0, ge=0.1, le=60.0)
    stochastic: bool = False


class RehearsalGenerateRequest(BaseModel):
    profile: str = "thermal"
    difficulty: str = "medium"
    mission_goal: str = ""


class RehearsalStartRequest(BaseModel):
    generated: Dict[str, Any]


class RehearsalActionRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    at_t: Optional[float] = None


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_telemetry_loop())
    if settings.helm_auto_monitor_enabled:
        asyncio.create_task(_helm_monitor_loop())


async def _telemetry_loop() -> None:
    delay = 1.0 / max(settings.telemetry_hz, 0.1)
    last_ts = time.time()
    while True:
        now = time.time()
        dt = max(0.05, now - last_ts)
        last_ts = now
        with state_lock:
            state.update(dt)
            snapshot = state.snapshot()
            history.append(snapshot)
        await _broadcast(snapshot)
        await asyncio.sleep(delay)


async def _helm_monitor_loop() -> None:
    global last_helm_auto_session_id
    while True:
        await asyncio.sleep(5.0)
        try:
            with state_lock:
                snapshot = state.snapshot()
                recent_events = list(state.events)[:8]
            result = helm_runtime.monitor_snapshot(snapshot, recent_events)
            if not result.should_start_session:
                continue
            if last_helm_auto_session_id:
                existing = orchestrator_sessions.get(last_helm_auto_session_id)
                if existing and existing.status not in {"COMPLETED", "ABORTED", "STALE"}:
                    continue
            review_mode = "auto" if settings.helm_live_execution_enabled else "assisted"
            execution_mode = "auto_step" if settings.helm_live_execution_enabled else "manual_step"
            orchestrator = _recovery_orchestrator()
            session = orchestrator.start_live(
                OrchestratorStartRequest(
                    brain_mode="gemma_helm",
                    reason="helm_auto_monitor",
                    review_mode=review_mode,
                    execution_mode=execution_mode,
                    include_compare=True,
                    include_explanation=True,
                    stochastic=False,
                )
            )
            last_helm_auto_session_id = session.session_id
        except Exception:
            # Monitor must never interrupt telemetry serving.
            continue


async def _broadcast(snapshot: Dict[str, Any]) -> None:
    if not clients:
        return
    dead: List[WebSocket] = []
    for ws in list(clients):
        try:
            await ws.send_json({"type": "telemetry", "data": snapshot})
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


@app.get("/health")
def health() -> Dict[str, Any]:
    gemma_status = agents.gemma_status()
    with state_lock:
        probe_id = state.probe_id
        mode = state.mode
        active_fault = state.active_fault
    return {
        "ok": True,
        "service": "deeprepair-probe-emulator",
        "probe_id": probe_id,
        "mode": mode,
        "active_fault": active_fault,
        "allowed_commands": sorted(ALLOWED_COMMANDS),
        "high_risk_commands": sorted(HIGH_RISK_COMMANDS),
        "gemma": gemma_status,
        "require_real_gemma": settings.require_real_gemma,
        "ts": time.time(),
    }


@app.get("/api/telemetry/current")
def telemetry_current() -> Dict[str, Any]:
    with state_lock:
        return state.snapshot()


@app.get("/api/telemetry/history")
def telemetry_history(metric: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
    with state_lock:
        if metric:
            return {"metric": metric, "points": history.metric_series(metric, limit=limit)}
        return {"rows": history.all_recent(limit=limit)}


@app.get("/api/events")
def events() -> Dict[str, Any]:
    with state_lock:
        return {"events": list(state.events)}


@app.post("/api/faults/inject")
def inject_fault(req: FaultRequest) -> Dict[str, Any]:
    try:
        with state_lock:
            state.inject_fault(req.fault)
            snapshot = state.snapshot()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "fault": req.fault, "snapshot": snapshot}


@app.post("/api/state/reset")
async def reset_probe_state() -> Dict[str, Any]:
    global state
    with state_lock:
        next_change_version = state.change_version + 1
        state = SpacecraftState(change_version=next_change_version)
        history.clear()
        snapshot = state.snapshot()
        history.append(snapshot)
    await _broadcast(snapshot)
    return {
        "ok": True,
        "message": "Probe simulator state reset to nominal baseline.",
        "snapshot": snapshot,
    }


@app.post("/api/command")
def execute_command(req: CommandRequest) -> Dict[str, Any]:
    action = req.action.upper().strip()
    if action in HIGH_RISK_COMMANDS and not req.human_approved:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{action} is high-risk and requires human_approved=true.",
                "action": action,
            },
        )
    try:
        with state_lock:
            return state.apply_command(action, req.params, req.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/agent/gemma/status")
def gemma_status() -> Dict[str, Any]:
    return agents.gemma_status()


@app.get("/api/agents/design")
def agents_design() -> Dict[str, Any]:
    return {
        "agents": [
            {
                "name": "TelemetryAnomalyAgent",
                "runs_on": "mac-probe-backend",
                "responsibility": "Threshold/trend anomaly detection over recent telemetry.",
            },
            {
                "name": "OnboardE4BDiagnosisAgent",
                "runs_on": "server-vllm-e4b",
                "responsibility": "Compact JSON fault summary, likely causes, and immediate safe action recommendations.",
            },
            {
                "name": "SafetyGateAgent",
                "runs_on": "mac-probe-backend",
                "responsibility": "Filters model output through the white-listed command set and marks high-risk actions.",
            },
            {
                "name": "CommandExecutorAgent",
                "runs_on": "mac-probe-backend",
                "responsibility": "Executes only approved white-list commands against the spacecraft emulator state.",
            },
        ],
        "allowed_commands": sorted(ALLOWED_COMMANDS),
        "high_risk_commands": sorted(HIGH_RISK_COMMANDS),
    }


@app.post("/api/agent/diagnose")
def run_diagnosis(req: DiagnoseRequest) -> Dict[str, Any]:
    try:
        with state_lock:
            snapshot = state.snapshot()
        return agents.diagnose(snapshot, reason=req.reason)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/agent/plans")
def generate_candidate_plans(req: CandidatePlansRequest) -> Dict[str, Any]:
    if req.snapshot:
        snapshot = req.snapshot
    else:
        with state_lock:
            snapshot = state.snapshot()
    try:
        return agents.generate_candidate_plans(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/agent/twin/explain")
def explain_twin_verdict(req: TwinExplainRequest) -> Dict[str, Any]:
    if req.snapshot:
        snapshot = req.snapshot
    else:
        with state_lock:
            snapshot = state.snapshot()
    try:
        return agents.explain_twin_verdict(snapshot, req.twin_result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/agent/scenario")
def generate_scenario(req: ScenarioRequest) -> Dict[str, Any]:
    try:
        return agents.generate_scenario(req.prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/twin/augment/scenario")
def generate_augmented_twin_scenario(req: AugmentationRequest) -> Dict[str, Any]:
    try:
        return {
            "ok": True,
            "scenario": build_augmented_scenario(
                req.profile,
                difficulty=req.difficulty,
                base_environment=req.environment,
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/rehearsal/generate")
def generate_rehearsal(req: RehearsalGenerateRequest) -> Dict[str, Any]:
    try:
        return rehearsals.generate(req.profile, req.difficulty, mission_goal=req.mission_goal)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/rehearsal/start")
def start_rehearsal(req: RehearsalStartRequest) -> Dict[str, Any]:
    try:
        with state_lock:
            base_state = state.clone_for_baseline()
        return rehearsals.start(req.generated, base_state=base_state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/rehearsal/{session_id}/action")
def record_rehearsal_action(session_id: str, req: RehearsalActionRequest) -> Dict[str, Any]:
    try:
        return rehearsals.record_action(session_id, req.action, params=req.params, at_t=req.at_t)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown rehearsal id: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/twin/rehearsal/{session_id}/report")
def rehearsal_report(session_id: str) -> Dict[str, Any]:
    try:
        return rehearsals.report(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown rehearsal id: {session_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recovery/evaluate-current", response_model=RecoveryEvaluationResponse)
def evaluate_current_recovery(req: RecoveryEvaluationRequest) -> RecoveryEvaluationResponse:
    try:
        return _evaluate_current_recovery(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/orchestrator/live/start", response_model=OrchestratorSession)
def orchestrator_live_start(req: OrchestratorStartRequest) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().start_live(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/orchestrator/session/{session_id}", response_model=OrchestratorSession)
def orchestrator_get_session(session_id: str) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc


@app.get("/api/orchestrator/auto-session/latest")
def orchestrator_latest_auto_session() -> Dict[str, Any]:
    if not last_helm_auto_session_id:
        return {"ok": True, "session": None}
    session = orchestrator_sessions.get(last_helm_auto_session_id)
    if session is None:
        return {"ok": True, "session": None}
    return {"ok": True, "session": session}


@app.post("/api/orchestrator/session/{session_id}/approve", response_model=OrchestratorSession)
def orchestrator_approve_session(session_id: str, req: ApproveSessionRequest) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().approve(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/orchestrator/session/{session_id}/reject", response_model=OrchestratorSession)
def orchestrator_reject_session(session_id: str, req: RejectSessionRequest) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().reject(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc


@app.post("/api/orchestrator/session/{session_id}/execute-step", response_model=OrchestratorSession)
def orchestrator_execute_step(session_id: str) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().execute_step(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/orchestrator/session/{session_id}/execute-plan", response_model=OrchestratorSession)
def orchestrator_execute_plan(session_id: str) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().execute_plan(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/orchestrator/session/{session_id}/abort", response_model=OrchestratorSession)
def orchestrator_abort_session(session_id: str, req: AbortSessionRequest) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().abort(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc


@app.post("/api/orchestrator/session/{session_id}/dialogue", response_model=OrchestratorSession)
def orchestrator_dialogue(session_id: str, req: HelmDialogueRequest) -> OrchestratorSession:
    try:
        return _recovery_orchestrator().dialogue(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/orchestrator/session/{session_id}/debrief", response_model=DebriefReport)
def orchestrator_debrief(session_id: str) -> DebriefReport:
    try:
        session = _recovery_orchestrator().debrief(session_id)
        if session.debrief_report is None:
            raise HTTPException(status_code=404, detail="Debrief not available.")
        return session.debrief_report
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc


@app.get("/api/orchestrator/session/{session_id}/graph", response_model=GraphBundle)
def orchestrator_graph(session_id: str) -> GraphBundle:
    try:
        session = _recovery_orchestrator().graph(session_id)
        if session.graph_bundle is None:
            raise HTTPException(status_code=404, detail="Graph bundle not available.")
        return session.graph_bundle
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown orchestrator session: {session_id}") from exc


@app.get("/api/helm/status", response_model=HelmStatusResponse)
def helm_status() -> HelmStatusResponse:
    return helm_runtime.status()


@app.post("/api/helm/monitor/tick")
def helm_monitor_tick() -> Dict[str, Any]:
    with state_lock:
        snapshot = state.snapshot()
        recent_events = list(state.events)[:8]
    result = helm_runtime.monitor_snapshot(snapshot, recent_events)
    return {
        "ok": True,
        "monitor": result,
        "snapshot_seq": snapshot.get("seq"),
        "active_fault": snapshot.get("active_fault"),
    }


@app.post("/api/twin/baseline/freeze", response_model=FreezeBaselineResponse)
def freeze_twin_baseline() -> FreezeBaselineResponse:
    baseline = _freeze_current_baseline(reason="manual-freeze")
    return FreezeBaselineResponse(
        baseline=_baseline_meta(baseline),
        snapshot=baseline.snapshot,
    )


@app.post("/api/agent/recovery-plan")
def generate_recovery_plan(req: RecoveryPlanRequest) -> Dict[str, Any]:
    try:
        evaluation = _evaluate_current_recovery(
            RecoveryEvaluationRequest(
                reason="legacy_recovery_plan",
                review_mode="manual",
                include_compare=True,
                include_explanation=True,
                horizon_sec=req.horizon_sec,
                dt=req.dt,
                stochastic=req.stochastic,
            )
        )
        return {
            "ok": True,
            "snapshot_seq": evaluation.snapshot_seq,
            "plans": evaluation.plan_bundle,
            "twin_compare": evaluation.twin_compare,
            "explanation": evaluation.explanation,
            "evaluation": evaluation,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/twin/run", response_model=TwinRunResponse)
def run_twin(req: TwinRunRequest) -> TwinRunResponse:
    if req.from_snapshot != "latest":
        raise HTTPException(status_code=400, detail="Only from_snapshot='latest' is supported.")
    try:
        baseline = _freeze_current_baseline(reason="manual-twin-run")
        return TwinEngine(baseline.clone_state()).run(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/compare", response_model=TwinCompareResponse)
def compare_twin(req: TwinCompareRequest) -> TwinCompareResponse:
    if req.from_snapshot != "latest":
        raise HTTPException(status_code=400, detail="Only from_snapshot='latest' is supported.")

    try:
        baseline = _freeze_current_baseline(reason="manual-twin-compare")
        return _run_twin_compare_from_baseline(baseline, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/compare/from-baseline", response_model=TwinCompareResponse)
def compare_twin_from_baseline(req: TwinCompareFromBaselineRequest) -> TwinCompareResponse:
    baseline = baseline_store.get(req.baseline_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"Unknown baseline: {req.baseline_id}")
    try:
        compare_req = TwinCompareRequest(
            from_snapshot="baseline",
            environment=req.environment,
            faults=req.faults,
            plans=req.plans,
            horizon_sec=req.horizon_sec,
            dt=req.dt,
            stochastic=req.stochastic,
        )
        return _run_twin_compare_from_baseline(baseline, compare_req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/twin/compare/{compare_id}/plan/{plan_id}/playback", response_model=PlanPlaybackBundle)
def twin_plan_playback(compare_id: str, plan_id: str) -> PlanPlaybackBundle:
    _prune_compare_playback_cache()
    row = compare_playback_cache.get(compare_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown Twin compare id: {compare_id}")
    playbacks = row.get("playbacks", {})
    playback = playbacks.get(plan_id) if isinstance(playbacks, dict) else None
    if playback is None:
        raise HTTPException(status_code=404, detail=f"Unknown Twin plan id for compare: {plan_id}")
    return playback


@app.post("/api/twin/testbed/start", response_model=GroundTestbedSession)
def start_twin_testbed() -> GroundTestbedSession:
    baseline = _freeze_current_baseline(reason="ground-testbed")
    with state_lock:
        real_snapshot = state.snapshot()
    calibration = calibrate_baseline(
        baseline_id=baseline.baseline_id,
        real_snapshot=real_snapshot,
        twin_snapshot=baseline.clone_state().snapshot(),
    )
    plan_bundle = agents.generate_candidate_plans(baseline.snapshot)
    plans = _plans_from_agent_bundle(plan_bundle)
    session = testbed_sessions.create(
        baseline=_baseline_meta(baseline),
        calibration=calibration,
        candidate_plans=plans[:3],
    )
    assembly = assemblies.create_default(session.session_id)
    return _sync_session_assembly(session, assembly)


@app.post("/api/twin/testbed/{session_id}/faults", response_model=GroundTestbedSession)
def inject_twin_testbed_faults(session_id: str, req: FaultInjectionRequest) -> GroundTestbedSession:
    try:
        return testbed_sessions.add_faults(session_id, req.faults, label=req.label)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}") from exc


@app.get("/api/twin/assembly/catalog")
def get_twin_assembly_catalog() -> Dict[str, Any]:
    return catalog_response()


@app.get("/api/twin/testbed/{session_id}/assembly", response_model=TwinAssemblyState)
def get_twin_testbed_assembly(session_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    assembly = assemblies.ensure(session_id)
    _sync_session_assembly(session, assembly)
    return assembly


@app.post("/api/twin/testbed/{session_id}/assembly/component", response_model=TwinAssemblyState)
def add_twin_testbed_component(session_id: str, req: ComponentOperationRequest) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.add_component(session_id, req)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/twin/testbed/{session_id}/assembly/component/{component_id}", response_model=TwinAssemblyState)
def remove_twin_testbed_component(session_id: str, component_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.remove_component(session_id, component_id)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/twin/testbed/{session_id}/assembly/component/{component_id}/transform", response_model=TwinAssemblyState)
def transform_twin_testbed_component(session_id: str, component_id: str, req: ComponentTransformRequest) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.transform_component(session_id, component_id, req)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/twin/testbed/{session_id}/assembly/component/{component_id}/parameters", response_model=TwinAssemblyState)
def update_twin_testbed_component_parameters(session_id: str, component_id: str, req: ComponentParametersRequest) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.update_parameters(session_id, component_id, req)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/testbed/{session_id}/assembly/component/{component_id}/replace", response_model=TwinAssemblyState)
def replace_twin_testbed_component(session_id: str, component_id: str, req: ComponentReplaceRequest) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.replace_component(session_id, component_id, req)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/testbed/{session_id}/assembly/component/{component_id}/select", response_model=TwinAssemblyState)
def select_twin_testbed_component(session_id: str, component_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.select_component(session_id, component_id)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/testbed/{session_id}/assembly/link", response_model=TwinAssemblyState)
def add_twin_testbed_link(session_id: str, req: ComponentLinkRequest) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.add_link(session_id, req)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/twin/testbed/{session_id}/assembly/link/{link_id}", response_model=TwinAssemblyState)
def remove_twin_testbed_link(session_id: str, link_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    try:
        assembly = assemblies.remove_link(session_id, link_id)
        _sync_session_assembly(session, assembly)
        return assembly
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/testbed/{session_id}/assembly/validate", response_model=TwinAssemblyState)
def validate_twin_testbed_assembly(session_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    assembly = assemblies.validate(session_id)
    _sync_session_assembly(session, assembly)
    return assembly


@app.post("/api/twin/testbed/{session_id}/assembly/undo", response_model=TwinAssemblyState)
def undo_twin_testbed_assembly(session_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    assembly = assemblies.undo(session_id)
    _sync_session_assembly(session, assembly)
    return assembly


@app.post("/api/twin/testbed/{session_id}/assembly/redo", response_model=TwinAssemblyState)
def redo_twin_testbed_assembly(session_id: str) -> TwinAssemblyState:
    session = _testbed_session_or_404(session_id)
    assembly = assemblies.redo(session_id)
    _sync_session_assembly(session, assembly)
    return assembly


@app.post("/api/twin/testbed/{session_id}/assembly/fault", response_model=ComponentFaultInjectionResponse)
def inject_twin_testbed_component_fault(session_id: str, req: ComponentFaultInjectionRequest) -> ComponentFaultInjectionResponse:
    _testbed_session_or_404(session_id)
    try:
        assembly, fault = assemblies.inject_fault(session_id, req)
        session = testbed_sessions.add_faults(session_id, [fault], label="component_fault_injection")
        session = _sync_session_assembly(session, assembly)
        return ComponentFaultInjectionResponse(ok=True, assembly=assembly, session=session, fault=fault)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/twin/testbed/{session_id}/troubleshoot", response_model=TroubleshootingResponse)
def troubleshoot_twin_testbed(session_id: str, req: TroubleshootingRequest) -> TroubleshootingResponse:
    session = testbed_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}")
    assembly = assemblies.ensure(session_id)
    rule_response = build_rule_troubleshooting(assembly=assembly, session=session, req=req)
    if not req.include_gemma:
        return rule_response
    try:
        enhanced = agents.troubleshoot_component(_model_dump(assembly), _model_dump(session), _model_dump(rule_response))
        rule_response.source = "e4b-enhanced" if enhanced.get("troubleshooting", {}).get("source") == "e4b-enhanced" else "rules+e4b-fallback"
        rule_response.gemma = enhanced
        return rule_response
    except Exception as exc:
        rule_response.source = "rules+e4b-error"
        rule_response.gemma = {"ok": False, "error": str(exc)[:500]}
        return rule_response


@app.post("/api/twin/testbed/{session_id}/campaign", response_model=CampaignResponse)
def run_twin_testbed_campaign(session_id: str, req: SimulationCampaignRequest) -> CampaignResponse:
    session = testbed_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}")
    baseline = baseline_store.get(session.baseline.baseline_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"Baseline expired for testbed session: {session.baseline.baseline_id}")
    assembly = assemblies.validate(session_id)
    session = _sync_session_assembly(session, assembly)
    if not assembly.validation.ok:
        reasons = "; ".join(issue.message for issue in assembly.validation.issues[:4])
        raise HTTPException(status_code=409, detail=f"Assembly graph is invalid; campaign blocked. {reasons}")

    plans = _testbed_plans_for_faults(req.faults or session.twin_faults, req.plans or session.candidate_plans)
    session.candidate_plans = plans
    testbed_sessions.save(session)
    campaign_req = SimulationCampaignRequest(
        plans=plans,
        faults=req.faults or session.twin_faults,
        environment_branches=req.environment_branches or _default_campaign_environments(_environment_from_state(baseline.state)),
        horizon_sec=req.horizon_sec,
        dt=req.dt,
        seeds=req.seeds,
    )
    campaign = run_campaign(baseline=baseline, req=campaign_req, session_id=session_id, assembly=assembly)
    testbed_sessions.attach_campaign(session_id, campaign)
    return campaign


@app.post("/api/twin/testbed/{session_id}/command-package", response_model=CommandPackage)
def create_twin_testbed_command_package(session_id: str, req: CommandPackageRequest) -> CommandPackage:
    session = testbed_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}")
    if session.last_campaign is None:
        raise HTTPException(status_code=409, detail="Run a simulation campaign before building a command package.")
    assembly = assemblies.validate(session_id)
    session = _sync_session_assembly(session, assembly)
    if not assembly.validation.ok:
        reasons = "; ".join(issue.message for issue in assembly.validation.issues[:4])
        raise HTTPException(status_code=409, detail=f"Assembly graph is invalid; Build Package blocked. {reasons}")
    _assert_campaign_matches_assembly(session.last_campaign, assembly)
    selected_plan_id = req.plan_id or session.selected_plan_id or session.last_campaign.best_plan_id
    _assert_package_build_allowed(session.last_campaign, selected_plan_id)
    try:
        package = build_command_package(
            session=session,
            campaign=session.last_campaign,
            assembly=assembly,
            plan_id=selected_plan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    command_packages.create(package)
    testbed_sessions.attach_package(session_id, package.package_id)
    return package


@app.get("/api/uplink/package/{package_id}", response_model=CommandPackage)
def get_uplink_package(package_id: str) -> CommandPackage:
    package = command_packages.get(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"Unknown command package: {package_id}")
    return package


@app.post("/api/uplink/package/{package_id}/approve", response_model=CommandPackage)
def approve_uplink_package(package_id: str) -> CommandPackage:
    package = command_packages.get(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"Unknown command package: {package_id}")
    _assert_uplink_package_gate(package)
    return command_packages.save(approve_command_package(package, approved_by="operator"))


@app.post("/api/uplink/package/{package_id}/execute", response_model=CommandPackage)
def execute_uplink_package(package_id: str) -> CommandPackage:
    package = command_packages.get(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"Unknown command package: {package_id}")
    _assert_uplink_package_gate(package)
    if package.requires_human_approval and package.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Command package requires approval before uplink.")
    if package.status in {"UPLINKING", "EXECUTED"}:
        return package
    package = command_packages.save(mark_uplink_started(package))
    thread = threading.Thread(target=_execute_command_package_after_delay, args=(package.package_id,), daemon=True)
    thread.start()
    return package


def _testbed_session_or_404(session_id: str) -> GroundTestbedSession:
    session = testbed_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown testbed session: {session_id}")
    return session


def _sync_session_assembly(session: GroundTestbedSession, assembly: TwinAssemblyState) -> GroundTestbedSession:
    session.assembly_id = assembly.assembly_id
    session.assembly_version = assembly.version
    session.assembly_digest = assembly.assembly_digest
    return testbed_sessions.save(session)


def _campaign_score(campaign: CampaignResponse, plan_id: Optional[str]) -> Any:
    if not plan_id:
        return None
    return next((score for score in campaign.scores if score.plan_id == plan_id), None)


def _assert_campaign_matches_assembly(campaign: CampaignResponse, assembly: TwinAssemblyState) -> None:
    if campaign.assembly_digest and campaign.assembly_digest != assembly.assembly_digest:
        raise HTTPException(
            status_code=409,
            detail=(
                "Assembly changed after the last campaign; rerun campaign before building a package. "
                f"campaign={campaign.assembly_digest[:12]} current={assembly.assembly_digest[:12]}"
            ),
        )
    if campaign.assembly_version and campaign.assembly_version != assembly.version:
        raise HTTPException(
            status_code=409,
            detail=(
                "Assembly version changed after the last campaign; rerun campaign before building a package. "
                f"campaign=v{campaign.assembly_version} current=v{assembly.version}"
            ),
        )


def _assert_package_build_allowed(campaign: CampaignResponse, plan_id: Optional[str]) -> None:
    score = _campaign_score(campaign, plan_id)
    if score is None:
        raise HTTPException(status_code=400, detail=f"Campaign score not available for plan: {plan_id}")
    if score.verdict != "PASS":
        raise HTTPException(
            status_code=409,
            detail=f"Build Package blocked: selected plan verdict is {score.verdict}; PASS is required.",
        )
    if score.pass_rate < PACKAGE_PASS_RATE_THRESHOLD:
        raise HTTPException(
            status_code=409,
            detail=f"Build Package blocked: selected plan pass_rate is {score.pass_rate:.0%}; at least 80% is required.",
        )


def _assert_uplink_package_gate(package: CommandPackage) -> None:
    errors = _uplink_package_gate_errors(package)
    if errors:
        package.gate_status = "blocked"
        package.gate_reason = "; ".join(errors)
        package.execution_log.append(
            {
                "ts": time.time(),
                "type": "gate_blocked",
                "message": package.gate_reason,
            }
        )
        command_packages.save(package)
        raise HTTPException(status_code=409, detail=package.gate_reason)
    package.gate_status = "pass"
    package.gate_reason = "Package safety gate passed."
    command_packages.save(package)


def _uplink_package_gate_errors(package: CommandPackage) -> List[str]:
    errors: List[str] = []
    session = testbed_sessions.get(package.source_session_id)
    if session is None:
        return [f"Source testbed session is missing: {package.source_session_id}."]
    baseline = baseline_store.get(package.baseline_id)
    if baseline is None or time.time() > session.baseline.expires_at:
        errors.append(f"Baseline is stale or expired: {package.baseline_id}.")
    if package.baseline_id != session.baseline.baseline_id:
        errors.append("Package baseline does not match the current session baseline.")

    assembly = assemblies.get(session.session_id)
    if assembly is None:
        errors.append("Assembly state is missing.")
    else:
        if package.assembly_id != assembly.assembly_id:
            errors.append("Package assembly_id does not match current assembly.")
        if package.assembly_version != assembly.version:
            errors.append(f"Assembly version changed: package=v{package.assembly_version} current=v{assembly.version}.")
        if package.assembly_digest != assembly.assembly_digest:
            errors.append("Assembly digest changed after package build.")
        if not assembly.validation.ok:
            reasons = "; ".join(issue.message for issue in assembly.validation.issues[:4])
            errors.append(f"Assembly graph is invalid: {reasons}")

    if package.pass_rate < PACKAGE_PASS_RATE_THRESHOLD:
        errors.append(f"Campaign pass_rate is {package.pass_rate:.0%}; at least 80% is required.")
    if package.risk_score >= 60.0:
        errors.append(f"Campaign risk_score is {package.risk_score:.1f}; must be below 60.0.")
    if package.gate_status == "blocked":
        errors.append(package.gate_reason or "Package gate is blocked.")
    if session.last_campaign is None:
        errors.append("Source campaign is missing.")
    else:
        if session.last_campaign.assembly_digest != package.assembly_digest:
            errors.append("Source campaign assembly digest no longer matches the package.")
        score = _campaign_score(session.last_campaign, package.plan_id)
        if score is None:
            errors.append(f"Source campaign score is missing for plan {package.plan_id}.")
        elif score.verdict != "PASS":
            errors.append(f"Source campaign verdict is {score.verdict}; PASS is required.")
    return errors


def _evaluate_current_recovery(req: RecoveryEvaluationRequest) -> RecoveryEvaluationResponse:
    baseline = _freeze_current_baseline(reason=req.reason)
    snapshot = baseline.snapshot
    environment = _environment_from_state(baseline.state)

    diagnosis = agents.diagnose(snapshot, reason=req.reason)
    plan_bundle = agents.generate_candidate_plans(snapshot)
    plans = [
        TwinPlanCandidate(
            id=str(plan["id"]),
            label=str(plan.get("label", plan["id"])),
            actions=plan.get("actions", []),
        )
        for plan in plan_bundle.get("plans", [])
        if isinstance(plan, dict) and plan.get("id")
    ]
    if len(plans) < 2:
        raise ValueError("Recovery planner must return at least two candidate plans.")

    compare_req = TwinCompareRequest(
        from_snapshot="latest",
        environment=environment,
        faults=[],
        plans=plans[:3],
        horizon_sec=req.horizon_sec,
        dt=req.dt,
        stochastic=req.stochastic,
    )
    twin_compare = _run_twin_compare_from_baseline(baseline, compare_req)
    best_result = next(
        (result for result in twin_compare.results if result.plan_id == twin_compare.best_plan_id),
        None,
    )

    explanation = None
    if req.include_explanation and best_result is not None:
        explanation = agents.explain_twin_verdict(snapshot, _model_dump(best_result))

    return RecoveryEvaluationResponse(
        snapshot_seq=int(snapshot.get("seq", 0)),
        snapshot_meta={
            "probe_id": snapshot.get("probe_id"),
            "mode": snapshot.get("mode"),
            "active_fault": snapshot.get("active_fault"),
            "active_faults": snapshot.get("active_faults", []),
            "change_version": snapshot.get("change_version"),
            "sim_elapsed_s": snapshot.get("sim_elapsed_s"),
            "environment": _model_dump(environment),
        },
        baseline=_baseline_meta(baseline),
        diagnosis=diagnosis,
        plan_bundle=plan_bundle,
        twin_compare=twin_compare,
        recommended_plan_id=twin_compare.best_plan_id,
        review_suggestion=_build_review_suggestion(best_result, plan_bundle, req.review_mode),
        explanation=explanation,
        fault_layers=snapshot.get("fault_layers", {}),
    )


def _plans_from_agent_bundle(plan_bundle: Dict[str, Any]) -> List[TwinPlanCandidate]:
    return [
        TwinPlanCandidate(
            id=str(plan["id"]),
            label=str(plan.get("label", plan["id"])),
            actions=plan.get("actions", []),
        )
        for plan in plan_bundle.get("plans", [])
        if isinstance(plan, dict) and plan.get("id")
    ]


def _testbed_plans_for_faults(
    faults: List[Any],
    fallback: List[TwinPlanCandidate],
) -> List[TwinPlanCandidate]:
    if not faults and fallback and any(plan.actions for plan in fallback):
        return fallback[:3]
    categories = {str(getattr(fault, "category", "")).lower() for fault in faults}
    if any("thermal" in category or "radiator" in category for category in categories):
        return [
            TwinPlanCandidate(id="plan-a", label="Conservative thermal recovery", actions=[
                {"action": "ENTER_SAFE_MODE", "at_t": 0},
                {"action": "DISABLE_PAYLOAD", "at_t": 2},
                {"action": "RESET_THERMAL_CONTROLLER", "at_t": 8},
            ]),
            TwinPlanCandidate(id="plan-b", label="Controller reset first", actions=[
                {"action": "RESET_THERMAL_CONTROLLER", "at_t": 0},
                {"action": "DISABLE_PAYLOAD", "at_t": 10},
            ]),
            TwinPlanCandidate(id="plan-c", label="Minimal intervention", actions=[
                {"action": "RESET_THERMAL_CONTROLLER", "at_t": 0},
            ]),
        ]
    if any("comms" in category or "antenna" in category or "transceiver" in category for category in categories):
        return [
            TwinPlanCandidate(id="plan-a", label="Conservative comms recovery", actions=[
                {"action": "LOWER_SAMPLING_RATE", "at_t": 0},
                {"action": "RESTART_COMMS", "at_t": 8},
            ]),
            TwinPlanCandidate(id="plan-b", label="Restart and reduce traffic", actions=[
                {"action": "RESTART_COMMS", "at_t": 0},
                {"action": "LOWER_SAMPLING_RATE", "at_t": 8},
            ]),
            TwinPlanCandidate(id="plan-c", label="Safe mode comms protection", actions=[
                {"action": "ENTER_SAFE_MODE", "at_t": 0},
                {"action": "RESTART_COMMS", "at_t": 10},
            ]),
        ]
    if any("sensor" in category for category in categories):
        return [
            TwinPlanCandidate(id="plan-a", label="Switch to backup sensor", actions=[
                {"action": "SWITCH_TO_BACKUP_SENSOR", "at_t": 0},
            ]),
            TwinPlanCandidate(id="plan-b", label="Clear pipeline then backup", actions=[
                {"action": "CLEAR_CACHE", "at_t": 0},
                {"action": "SWITCH_TO_BACKUP_SENSOR", "at_t": 5},
            ]),
            TwinPlanCandidate(id="plan-c", label="Safe sensor fallback", actions=[
                {"action": "ENTER_SAFE_MODE", "at_t": 0},
                {"action": "SWITCH_TO_BACKUP_SENSOR", "at_t": 8},
            ]),
        ]
    if any("power" in category or "battery" in category for category in categories):
        return [
            TwinPlanCandidate(id="plan-a", label="Power conservation", actions=[
                {"action": "ENTER_SAFE_MODE", "at_t": 0},
                {"action": "DISABLE_PAYLOAD", "at_t": 2},
            ]),
            TwinPlanCandidate(id="plan-b", label="Reduce compute load", actions=[
                {"action": "CLEAR_CACHE", "at_t": 0},
                {"action": "LOWER_SAMPLING_RATE", "at_t": 5},
            ]),
            TwinPlanCandidate(id="plan-c", label="Payload off only", actions=[
                {"action": "DISABLE_PAYLOAD", "at_t": 0},
            ]),
        ]
    return fallback[:3]


def _default_campaign_environments(base: EnvironmentConfig) -> List[EnvironmentConfig]:
    def clone(update: Dict[str, Any]) -> EnvironmentConfig:
        if hasattr(base, "model_copy"):
            return base.model_copy(update=update)
        return base.copy(update=update)

    return [
        base,
        clone({"radiation_level": min(1.0, base.radiation_level + 0.35)}),
        clone({"antenna_alignment_error_deg": base.antenna_alignment_error_deg + 5.0}),
        clone({
            "eclipse_factor": min(0.85, base.eclipse_factor + 0.25),
            "thermal_sink_efficiency": max(0.3, base.thermal_sink_efficiency - 0.2),
        }),
    ]


def _execute_command_package_after_delay(package_id: str) -> None:
    package = command_packages.get(package_id)
    if package is None:
        return
    time.sleep(max(0.0, package.uplink_delay_s))
    package = command_packages.get(package_id)
    if package is None:
        return
    if package.status != "UPLINKING":
        return

    try:
        for index, step in enumerate(package.steps):
            action = step.action.upper().strip()
            with state_lock:
                result = state.apply_command(
                    action,
                    step.params,
                    source=f"uplink-package:{package.package_id}",
                )
            package.execution_log.append(
                {
                    "ts": time.time(),
                    "type": "command_executed",
                    "step_index": index,
                    "action": action,
                    "message": result.get("message", "Command executed."),
                    "before_seq": result.get("before", {}).get("seq") if isinstance(result.get("before"), dict) else None,
                    "after_seq": result.get("after", {}).get("seq") if isinstance(result.get("after"), dict) else None,
                }
            )
        package.status = "EXECUTED"
        package.execution_log.append(
            {
                "ts": time.time(),
                "type": "uplink_complete",
                "message": "Command package transmitted and applied to probe emulator.",
            }
        )
    except Exception as exc:
        package.status = "FAILED"
        package.execution_log.append(
            {
                "ts": time.time(),
                "type": "uplink_failed",
                "message": str(exc),
            }
        )
    command_packages.save(package)


def _environment_from_state(base_state: SpacecraftState) -> EnvironmentConfig:
    internal = base_state.to_internal_state()
    return EnvironmentConfig(
        sun_exposure=internal["sun_exposure"],
        eclipse_factor=internal["eclipse_factor"],
        radiation_level=internal["radiation_level"],
        antenna_alignment_error_deg=internal["antenna_alignment_error_deg"],
        battery_age_factor=internal["battery_age_factor"],
        thermal_sink_efficiency=internal["thermal_sink_efficiency"],
        mission_phase=internal["mission_phase"],
    )


def _build_review_suggestion(
    best_result: Optional[TwinComparePlanResult],
    plan_bundle: Dict[str, Any],
    review_mode: str,
) -> ReviewSuggestion:
    normalized_mode = str(review_mode or "manual").lower().strip()
    if normalized_mode not in {"manual", "assisted", "auto"}:
        normalized_mode = "manual"

    if best_result is None:
        return ReviewSuggestion(
            mode=normalized_mode,
            can_auto_execute=False,
            why="No recommended Twin result is available for review.",
        )
    if best_result.verdict != "PASS":
        return ReviewSuggestion(
            mode=normalized_mode,
            can_auto_execute=False,
            why="Recommended plan did not pass Twin constraints.",
        )

    best_plan = _plan_by_id(plan_bundle, best_result.plan_id)
    high_risk_actions = [
        action for action in _plan_actions(best_plan) if action in HIGH_RISK_COMMANDS
    ]
    if high_risk_actions:
        return ReviewSuggestion(
            mode=normalized_mode,
            can_auto_execute=False,
            why=f"Recommended plan includes high-risk action(s): {', '.join(high_risk_actions)}.",
        )
    if normalized_mode == "manual":
        return ReviewSuggestion(
            mode=normalized_mode,
            can_auto_execute=False,
            why="Manual review mode requires an operator decision before execution.",
        )
    if normalized_mode == "assisted":
        return ReviewSuggestion(
            mode=normalized_mode,
            can_auto_execute=False,
            why="Assisted review mode provides a recommendation only; execution remains manual.",
        )
    return ReviewSuggestion(
        mode=normalized_mode,
        can_auto_execute=True,
        why="Recommended plan passed Twin constraints and contains no high-risk actions.",
    )


def _plan_by_id(plan_bundle: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
    for plan in plan_bundle.get("plans", []):
        if isinstance(plan, dict) and str(plan.get("id")) == plan_id:
            return plan
    return {}


def _plan_actions(plan: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    for step in plan.get("actions", []):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action", "")).upper().strip()
        if action:
            actions.append(action)
    return actions


def _freeze_current_baseline(reason: str = "manual") -> FrozenBaseline:
    with state_lock:
        return baseline_store.create(state, reason=reason)


def _baseline_meta(baseline: FrozenBaseline) -> BaselineMeta:
    return BaselineMeta(**baseline.meta_dict())


def _run_twin_compare(
    req: TwinCompareRequest,
    base_state: Optional[SpacecraftState] = None,
) -> TwinCompareResponse:
    if base_state is None:
        baseline = _freeze_current_baseline(reason="transient-compare")
    else:
        with state_lock:
            baseline = baseline_store.create(base_state, reason="transient-compare")
    return _run_twin_compare_from_baseline(baseline, req)


def _run_twin_compare_from_baseline(
    baseline: FrozenBaseline,
    req: TwinCompareRequest,
) -> TwinCompareResponse:
    results: List[TwinComparePlanResult] = []
    baseline_meta = _baseline_meta(baseline)
    compare_id = f"twin-compare-{uuid.uuid4().hex[:12]}"
    run_records: List[tuple[TwinPlanCandidate, TwinRunResponse]] = []
    for plan in req.plans:
        run_req = TwinRunRequest(
            from_snapshot=req.from_snapshot,
            environment=req.environment,
            faults=req.faults,
            actions=plan.actions,
            horizon_sec=req.horizon_sec,
            dt=req.dt,
            stochastic=req.stochastic,
        )
        run = TwinEngine(baseline.clone_state()).run(run_req)
        run_records.append((plan, run))
        results.append(
            TwinComparePlanResult(
                plan_id=plan.id,
                label=plan.label,
                baseline_id=baseline.baseline_id,
                baseline_seq=baseline.captured_seq,
                baseline_digest=baseline.state_digest,
                verdict=run.verdict,
                risk_score=run.risk_score,
                final_mode=run.final_mode,
                constraints=run.constraints,
                trajectory=run.trajectory,
                final_snapshot=run.final_snapshot,
                explanation=run.explanation,
                fault_layers=run.fault_layers,
                repair_trace=run.repair_trace,
            )
        )

    plan_by_id = {plan.id: plan for plan in req.plans}
    best = min(results, key=lambda result: _engineering_compare_score(result, plan_by_id.get(result.plan_id)))
    _store_compare_playbacks(
        compare_id=compare_id,
        baseline=baseline,
        environment=req.environment,
        best_plan_id=best.plan_id,
        run_records=run_records,
    )
    return TwinCompareResponse(
        compare_id=compare_id,
        best_plan_id=best.plan_id,
        baseline=baseline_meta,
        results=results,
        explanation=f"Best plan is {best.plan_id} with verdict {best.verdict} and risk {best.risk_score:.1f}/100.",
    )


def _engineering_compare_score(
    result: TwinComparePlanResult,
    plan: Optional[TwinPlanCandidate],
) -> tuple[bool, float, float]:
    actions = plan.actions if plan else []
    high_risk_penalty = sum(1 for step in actions if step.action.upper().strip() in HIGH_RISK_COMMANDS) * 15.0
    command_count_penalty = len(actions) * 2.0
    mode_penalty = 20.0 if result.final_mode == "FAULT" else 0.0
    recovery_penalty = 0.0
    if result.repair_trace:
        uncleared_roots = len(result.repair_trace[-1].remaining_root_causes)
        recovery_penalty += uncleared_roots * 2.0
    aggregate = result.risk_score + high_risk_penalty + command_count_penalty + mode_penalty + recovery_penalty
    return (result.verdict != "PASS", aggregate, result.risk_score)


def _store_compare_playbacks(
    *,
    compare_id: str,
    baseline: FrozenBaseline,
    environment: EnvironmentConfig,
    best_plan_id: str,
    run_records: List[tuple[TwinPlanCandidate, TwinRunResponse]],
) -> None:
    _prune_compare_playback_cache()
    playbacks: Dict[str, PlanPlaybackBundle] = {}
    for plan, run in run_records:
        playbacks[plan.id] = build_playback_bundle(
            compare_id=compare_id,
            baseline_id=baseline.baseline_id,
            plan_id=plan.id,
            label=plan.label,
            recommended=plan.id == best_plan_id,
            baseline_snapshot=baseline.snapshot,
            run=run,
            environment=environment,
        )
    compare_playback_cache[compare_id] = {
        "created_at": time.time(),
        "expires_at": time.time() + baseline_store.ttl_sec,
        "baseline_id": baseline.baseline_id,
        "playbacks": playbacks,
    }


def _prune_compare_playback_cache() -> None:
    now = time.time()
    expired = [
        compare_id
        for compare_id, row in compare_playback_cache.items()
        if float(row.get("expires_at", 0.0)) <= now
    ]
    for compare_id in expired:
        compare_playback_cache.pop(compare_id, None)


def _model_dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value if isinstance(value, dict) else {}


def _current_snapshot_for_orchestrator() -> Dict[str, Any]:
    with state_lock:
        return state.snapshot()


def _execute_orchestrator_command(action: str, params: Dict[str, Any], source: str) -> Dict[str, Any]:
    action = action.upper().strip()
    if action in HIGH_RISK_COMMANDS:
        raise ValueError(f"{action} requires HITL and cannot be executed by Helm live automation.")
    with state_lock:
        return state.apply_command(action, params, source)


def _recovery_orchestrator() -> RecoveryOrchestrator:
    return RecoveryOrchestrator(
        agents=agents,
        session_store=orchestrator_sessions,
        freeze_current_baseline=_freeze_current_baseline,
        baseline_meta=_baseline_meta,
        environment_from_state=_environment_from_state,
        run_twin_compare_from_baseline=_run_twin_compare_from_baseline,
        current_snapshot=_current_snapshot_for_orchestrator,
        allowed_commands=sorted(ALLOWED_COMMANDS),
        high_risk_commands=sorted(HIGH_RISK_COMMANDS),
        helm_runtime=helm_runtime,
        live_execution_enabled=settings.helm_live_execution_enabled,
        command_executor=_execute_orchestrator_command,
    )


@app.get("/api/twin/snapshot", response_model=TwinSnapshotResponse)
def twin_snapshot() -> TwinSnapshotResponse:
    with state_lock:
        snapshot = state.snapshot()
        internal = state.to_internal_state()
    env = EnvironmentConfig(
        sun_exposure=internal["sun_exposure"],
        eclipse_factor=internal["eclipse_factor"],
        radiation_level=internal["radiation_level"],
        antenna_alignment_error_deg=internal["antenna_alignment_error_deg"],
        battery_age_factor=internal["battery_age_factor"],
        thermal_sink_efficiency=internal["thermal_sink_efficiency"],
        mission_phase=internal["mission_phase"],
    )
    return TwinSnapshotResponse(
        snapshot_id=f"latest-{snapshot['probe_id']}-{snapshot['seq']}",
        source="real-probe-latest",
        probe_id=snapshot["probe_id"],
        seq=snapshot["seq"],
        mode=snapshot["mode"],
        active_fault=snapshot["active_fault"],
        active_faults=snapshot.get("active_faults", []),
        environment=env,
        allowed_commands=sorted(ALLOWED_COMMANDS),
        supported_fault_categories=sorted(KNOWN_FAULTS),
        snapshot=snapshot,
    )


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    try:
        with state_lock:
            snapshot = state.snapshot()
        await websocket.send_json({"type": "telemetry", "data": snapshot})
        while True:
            # Keep connection open; browser may send pings/messages.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pi_probe.main:app", host=settings.host, port=settings.port, reload=False)
