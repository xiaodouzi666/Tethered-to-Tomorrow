from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pi_probe.agents.onboard import OnboardAgentRuntime
from pi_probe.config import settings
from pi_probe.probe.state import ALLOWED_COMMANDS, HIGH_RISK_COMMANDS, SpacecraftState, TelemetryHistory

app = FastAPI(title="DeepRepair Probe Emulator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_allow_origin] if settings.cors_allow_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = SpacecraftState()
history = TelemetryHistory(limit=settings.history_limit)
agents = OnboardAgentRuntime()
clients: Set[WebSocket] = set()


class FaultRequest(BaseModel):
    fault: str = Field(..., description="thermal | comms | power | sensor | clear")


class CommandRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    source: str = "mission-control-ui"
    human_approved: bool = False


class DiagnoseRequest(BaseModel):
    reason: str = "manual-ui"


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_telemetry_loop())


async def _telemetry_loop() -> None:
    delay = 1.0 / max(settings.telemetry_hz, 0.1)
    last_ts = time.time()
    while True:
        now = time.time()
        dt = max(0.05, now - last_ts)
        last_ts = now
        state.update(dt)
        snapshot = state.snapshot()
        history.append(snapshot)
        await _broadcast(snapshot)
        await asyncio.sleep(delay)


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
    return {
        "ok": True,
        "service": "deeprepair-probe-emulator",
        "probe_id": state.probe_id,
        "mode": state.mode,
        "active_fault": state.active_fault,
        "allowed_commands": sorted(ALLOWED_COMMANDS),
        "high_risk_commands": sorted(HIGH_RISK_COMMANDS),
        "gemma": gemma_status,
        "require_real_gemma": settings.require_real_gemma,
        "ts": time.time(),
    }


@app.get("/api/telemetry/current")
def telemetry_current() -> Dict[str, Any]:
    return state.snapshot()


@app.get("/api/telemetry/history")
def telemetry_history(metric: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
    if metric:
        return {"metric": metric, "points": history.metric_series(metric, limit=limit)}
    return {"rows": history.all_recent(limit=limit)}


@app.get("/api/events")
def events() -> Dict[str, Any]:
    return {"events": list(state.events)}


@app.post("/api/faults/inject")
def inject_fault(req: FaultRequest) -> Dict[str, Any]:
    try:
        state.inject_fault(req.fault)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "fault": req.fault, "snapshot": state.snapshot()}


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
                "runs_on": "raspberry-pi",
                "responsibility": "Threshold/trend anomaly detection over recent telemetry.",
            },
            {
                "name": "OnboardGemmaDiagnosisAgent",
                "runs_on": "raspberry-pi-local-gemma4",
                "responsibility": "Compact JSON fault summary, likely causes, and immediate safe action recommendations.",
            },
            {
                "name": "SafetyGateAgent",
                "runs_on": "raspberry-pi",
                "responsibility": "Filters model output through the white-listed command set and marks high-risk actions.",
            },
            {
                "name": "CommandExecutorAgent",
                "runs_on": "raspberry-pi",
                "responsibility": "Executes only approved white-list commands against the spacecraft emulator state.",
            },
        ],
        "allowed_commands": sorted(ALLOWED_COMMANDS),
        "high_risk_commands": sorted(HIGH_RISK_COMMANDS),
    }


@app.post("/api/agent/diagnose")
def run_diagnosis(req: DiagnoseRequest) -> Dict[str, Any]:
    try:
        return agents.diagnose(state.snapshot(), reason=req.reason)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    try:
        await websocket.send_json({"type": "telemetry", "data": state.snapshot()})
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
