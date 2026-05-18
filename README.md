# DeepRepair Mission Control

DeepRepair Mission Control is an operations-style spacecraft recovery demo. It connects a live Probe simulator, an E4B/Gemma reasoning layer, a policy-gated recovery orchestrator, a Ground Twin planner, a modular testbed, and Open MCT telemetry views into one end-to-end mission-control workflow.

The demo is designed for a Mac-hosted backend and frontend, with the E4B/Gemma model served separately through a remote OpenAI-compatible vLLM endpoint.

## What It Shows

- Live spacecraft telemetry with fault injection and command execution.
- Probe-side diagnosis through a remote fine-tuned E4B/Gemma model.
- Helm-style recovery reasoning with manual, assisted, and automatic review modes.
- Policy-gated execution for low-risk and high-risk recovery commands.
- Ground Twin plan comparison, playback, hidden-state inspection, and constraint checks.
- A modular Ground Twin Testbed for assembly validation, Twin-only faults, simulation campaigns, command packages, and simulated uplink.
- Open MCT views for real telemetry and Twin-predicted telemetry channels.

## Repository Layout

```text
frontend/        React + TypeScript Mission Control UI, Ground Twin UI, Open MCT entrypoints
pi_probe/        FastAPI Probe simulator, telemetry, agents, Helm, orchestrator, Twin engine
scripts/         Install, backend, frontend, and remote vLLM startup scripts
docs/            API notes, agent design notes, and final test/demo instructions
assets/          Shared 3D and visual assets
```

## Architecture

```text
Remote GPU host
  vLLM OpenAI-compatible API
  fine-tuned E4B/Gemma model
          |
          | GEMMA_API_BASE
          v
Mac / local development machine
  FastAPI Probe backend on :8010
    - Probe state simulator
    - telemetry history and websocket stream
    - fault injection
    - command whitelist and safety gate
    - E4B/Gemma adapter
    - Helm runtime
    - recovery orchestrator
    - Ground Twin engine and testbed
          |
          | VITE_PROBE_API_BASE / VITE_PROBE_WS_BASE
          v
  Vite frontend on :5173
    - Mission Control
    - Ground Twin Testbed
    - Open MCT
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- A remote vLLM server for the real E4B/Gemma path, or mock mode for local UI/backend testing

Python dependencies are listed in [pi_probe/requirements.txt](pi_probe/requirements.txt). Frontend dependencies are listed in [frontend/package.json](frontend/package.json).

## Quick Start: Mock Mode

Use this path when the remote model service is not available and you only need the local application flow.

```bash
git clone https://github.com/xiaodouzi666/Tethered-to-Tomorrow.git
cd Tethered-to-Tomorrow

bash scripts/install_probe_backend.sh
bash scripts/start_probe_mock.sh
```

In another terminal:

```bash
bash scripts/start_frontend.sh
```

Open:

```text
http://localhost:5173
```

## Quick Start: Remote E4B/Gemma Mode

### 1. Start vLLM on the GPU Host

Run this on the remote machine that has the fine-tuned model checkpoint available:

```bash
export GEMMA_MODEL=gemma4_e4b_tuned
export VLLM_PORT=8000
bash scripts/server_start_vllm_e4b.sh
```

Validate the model endpoint from the Mac:

```bash
curl http://<remote-host>:8000/v1/models
```

### 2. Start the Probe Backend on the Mac

```bash
cd Tethered-to-Tomorrow
export GEMMA_API_BASE=http://<remote-host>:8000/v1
export GEMMA_MODEL=gemma4_e4b_tuned
bash scripts/start_probe_gemma_remote_vllm.sh
```

Health checks:

```bash
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/api/agent/gemma/status
curl http://127.0.0.1:8010/api/orchestrator/auto-session/latest
```

### 3. Start the Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Main UI Entry Points

- Mission Control: `http://localhost:5173/`
- Ground Twin Testbed: `http://localhost:5173/twin`
- Open MCT: `http://localhost:5173/openmct.html`

## Core Workflows

### Mission Control

1. Confirm `Probe Link: ONLINE`.
2. Inspect live telemetry and subsystem status.
3. Inject a fault such as thermal, communications, power, or sensor.
4. Run onboard E4B diagnosis.
5. Review the recommendation and policy gate.
6. Execute an allowed low-risk command or keep high-risk commands gated for operator review.

### Helm Recovery

1. Start the backend with remote Gemma enabled.
2. Select E4B Helm in the recovery panel.
3. Run live analysis or enable the backend auto monitor.
4. Review the Helm dialogue, recommendation, policy result, and execution trace.
5. Use manual, assisted, or auto review modes depending on the demo path.

### Ground Twin

1. Open the Ground Twin workspace.
2. Run `Analyze Current State`.
3. Inspect generated plans, Twin verdicts, constraints, and telemetry projection.
4. Use the playback timeline to step through predicted state.
5. Switch candidate plans to compare recovery outcomes.

The frontend intentionally blocks stale, expired, or invalidated baselines from reusing old playback. Run a new analysis or compare after the real Probe state changes.

### Ground Twin Testbed

1. Freeze a baseline.
2. Inspect or modify the modular component graph.
3. Inject Twin-only component faults.
4. Run a campaign across environment branches and deterministic seeds.
5. Build a command package.
6. Approve and simulate uplink when the package passes policy checks.

### Open MCT

1. Open `openmct.html`.
2. Browse `real/*` telemetry channels.
3. Plot real temperature, voltage, communications, or subsystem channels.
4. Run Twin analysis.
5. Browse `twin/*` predicted channels when Twin data is available.

## Backend Configuration

Common environment variables:

```text
PROBE_HOST=127.0.0.1
PROBE_PORT=8010
GEMMA_BACKEND=remote_vllm
REQUIRE_REAL_GEMMA=1
GEMMA_API_BASE=http://<remote-host>:8000/v1
GEMMA_MODEL=gemma4_e4b_tuned
GEMMA_API_KEY=
GEMMA_TEMPERATURE=0.2
GEMMA_MAX_TOKENS=768
HELM_AUTO_MONITOR_ENABLED=0
HELM_LIVE_EXECUTION_ENABLED=0
TELEMETRY_HZ=1.0
```

For mock mode:

```bash
bash scripts/start_probe_mock.sh
```

For real E4B/Gemma mode:

```bash
export GEMMA_API_BASE=http://<remote-host>:8000/v1
bash scripts/start_probe_gemma_remote_vllm.sh
```

## Frontend Configuration

[frontend/.env.example](frontend/.env.example):

```text
VITE_PROBE_API_BASE=http://localhost:8010
VITE_PROBE_WS_BASE=ws://localhost:8010
```

Useful commands:

```bash
cd frontend
npm install
npm run dev
npm run build
npm run preview
```

## Important API Routes

```text
GET  /health
GET  /api/telemetry/current
GET  /api/telemetry/history?metric=thermal.temp_c&limit=300
WS   /ws/telemetry
POST /api/faults/inject
POST /api/command
POST /api/agent/diagnose
GET  /api/agent/gemma/status

POST /api/orchestrator/live/start
GET  /api/orchestrator/session/{session_id}
GET  /api/orchestrator/auto-session/latest
POST /api/orchestrator/session/{session_id}/approve
POST /api/orchestrator/session/{session_id}/execute-step
POST /api/orchestrator/session/{session_id}/dialogue

POST /api/twin/run
POST /api/twin/compare
GET  /api/twin/compare/{compare_id}/plan/{plan_id}/playback
POST /api/twin/testbed/start
POST /api/twin/testbed/{session_id}/campaign
POST /api/twin/testbed/{session_id}/command-package
```

More API notes are in [docs/API.md](docs/API.md).

## Safety Model

- Commands must pass the backend whitelist.
- High-risk commands require human-in-the-loop review.
- The model can recommend actions but cannot execute shell commands.
- Approval creates an execution ticket; it does not directly mutate Probe state.
- Dry-run execution does not change the Probe.
- Live execution is available only through the backend policy gate.
- Ground Twin playback is tied to a frozen baseline and cannot safely reuse old compare ids after baseline invalidation.

## Demo Checklist

The full test and demo checklist is in [docs/DEEPREPAIR_TEST_INSTRUCTIONS.md](docs/DEEPREPAIR_TEST_INSTRUCTIONS.md).

Recommended short demo:

1. Start remote vLLM.
2. Start the Probe backend.
3. Start the frontend.
4. Show Mission Control with live telemetry.
5. Inject a thermal fault.
6. Run E4B/Helm diagnosis.
7. Show policy-gated recommendation.
8. Open Ground Twin and run analysis.
9. Show Plan Compare, playback, inspector, constraints, and telemetry projection.
10. Open Ground Twin Testbed and show baseline freeze, assembly graph, Twin-only fault, campaign, and package flow.
11. Open Open MCT and show real plus Twin telemetry channels.

## Build Verification

Frontend production build:

```bash
cd frontend
npm run build
```

The current build may emit large chunk warnings because Open MCT, Three.js, and the Twin workspace are bundled into the demo build. Those warnings do not block the build.
