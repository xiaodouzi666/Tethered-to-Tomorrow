# DeepRepair Mission Control Test and Demo Manual

This manual is the final smoke-test and demo checklist for DeepRepair Mission Control v1.
It covers the local Probe backend, the remote E4B/Gemma reasoning service, Mission Control,
the Ground Twin workflow, Open MCT telemetry, and the Ground Twin Testbed.

Captured figures are embedded where available. Sections without a figure are still valid
acceptance steps and can be executed directly during the demo.

![DeepRepair cover](../../cover.png)

## 0. Startup Checks

### 0.1 Remote E4B vLLM

**Goal**

Verify that the remote E4B model service is running and exposes the fine-tuned Gemma model.

**Steps**

1. Open the remote E4B/vLLM terminal.
2. Confirm the model server is running.
3. From the Mac or the remote host, query the model endpoint:

```bash
curl http://<remote-host>:8000/v1/models
```

**Expected Result**

- The request returns HTTP 200.
- The response includes the deployed Gemma/E4B model id.
- The service remains running during the full Mission Control demo.

### 0.2 Probe Backend

**Goal**

Start the local Probe backend with Gemma Helm enabled, auto-monitoring enabled, and low-risk
live execution available.

**Steps**

1. From the repository root, start the backend:

```bash
./scripts/start_probe_gemma_remote_vllm.sh
```

2. Keep this terminal open during the demo.
3. Watch the log for backend startup, model adapter startup, and incoming API requests.

**Expected Result**

- The backend listens on the configured local port.
- Probe health endpoints return successfully.
- E4B/Gemma requests are routed through the backend adapter.
- Low-risk command execution remains policy-gated.

### 0.3 Probe Health

**Goal**

Confirm that the Probe backend, E4B adapter, command whitelist, and automation flags are ready.

**Steps**

Run:

```bash
curl http://localhost:8010/health
curl http://localhost:8010/api/probe/state
curl http://localhost:8010/api/orchestrator/auto-session/latest
```

**Expected Result**

- Health returns HTTP 200.
- Probe state contains live telemetry fields.
- Auto-session returns either the latest session or a clean idle state.
- No repeated backend error loop appears in the terminal.

### 0.4 Frontend Vite

**Goal**

Open the Mission Control and Ground Twin interfaces.

**Steps**

```bash
cd frontend
npm run dev
```

Then open:

- Mission Control: `http://localhost:5173/`
- Ground Twin Testbed: `http://localhost:5173/twin`
- Open MCT: the Open MCT route exposed by the current build

**Expected Result**

- The Vite server starts successfully.
- The Mission Control page renders without a blank screen.
- The Probe Link indicator can reach `ONLINE` once the backend is running.

## 1. Mission Control Console

![Mission Control overview](../../images/mainpage.png)

### 1.1 Probe Link Status

**Goal**

Confirm that the frontend is connected to the Probe backend.

**Steps**

1. Open Mission Control.
2. Check the top-right Probe Link indicator.
3. Refresh once if the backend was started after the page loaded.

**Expected Result**

- The indicator shows `Probe Link: ONLINE`.
- The refresh button can update the current state.
- Telemetry and command panels are enabled.

### 1.2 Real Probe Telemetry

**Goal**

Confirm that real telemetry is continuously read from the simulated Probe.

**Steps**

1. Inspect the Real Probe Telemetry panel.
2. Check temperature, battery voltage, packet loss, signal strength, and controller state.
3. Wait a few seconds and confirm that values remain coherent.

**Expected Result**

- Temperature is displayed in degrees Celsius.
- Battery voltage and communications indicators are visible.
- The 3D/mission view reflects the current subsystem state.

### 1.3 Thermal Fault Injection

![Thermal fault injected](../../images/thermal.png)

**Goal**

Verify thermal fault injection and the visible response across telemetry and decision panels.

**Steps**

1. Click `Inject Thermal`.
2. Watch the telemetry and fault panels.
3. Confirm that the temperature rises or the thermal subsystem becomes degraded.

**Expected Result**

- A thermal fault appears in the fault or root-cause area.
- The temperature channel shows an abnormal value or trend.
- The recommendation area begins to prefer a thermal recovery action.

### 1.4 Communications Fault Injection

**Goal**

Verify communications fault handling and high-risk command gating.

**Steps**

1. Clear existing faults if needed.
2. Click `Inject Comms`.
3. Observe signal strength, packet loss, and recovery recommendations.

**Expected Result**

- Signal strength or packet loss becomes abnormal.
- The system may recommend `RESTART_COMMS` or another communications recovery action.
- High-risk actions remain gated by review or manual approval.

### 1.5 Power Fault Injection

**Goal**

Verify battery and power fault handling.

**Steps**

1. Clear existing faults if needed.
2. Click the power/battery fault action.
3. Observe battery voltage and recovery recommendations.

**Expected Result**

- Battery telemetry changes to an abnormal state.
- The diagnosis panel identifies a power-related condition.
- Recovery recommendations remain within the policy gate.

### 1.6 Sensor Fault Injection

**Goal**

Verify sensor degradation and backup sensor recovery semantics.

**Steps**

1. Clear existing faults if needed.
2. Inject a sensor-related fault.
3. Observe visible telemetry and suggested actions.

**Expected Result**

- The affected sensor appears degraded or unavailable.
- The system can recommend backup-sensor or reduced-load mitigation.
- The action remains reviewable before execution.

### 1.7 Clear Faults

**Goal**

Clear currently injected faults without restarting the application.

**Steps**

1. Click `Clear Faults`.
2. Wait for the telemetry refresh cycle.
3. Inspect the fault list and recommendation panel.

**Expected Result**

- Active injected faults are removed.
- Telemetry returns toward nominal values.
- Recommendation status returns to standby or low-risk nominal behavior.

### 1.8 Reset Probe State

**Goal**

Reset the full simulated Probe state.

**Steps**

1. Click `Reset Probe State`.
2. Confirm the action if the UI asks for confirmation.
3. Refresh Mission Control and inspect telemetry.

**Expected Result**

- Faults are cleared.
- Telemetry returns to a nominal baseline.
- Existing Ground Twin baselines may become stale or invalidated because the real Probe state changed.

## 2. Whitelisted Command Tests

### 2.1 ENTER_SAFE_MODE

**Goal**

Verify the low-risk safe-mode transition.

**Steps**

1. Open the command area.
2. Select or execute `ENTER_SAFE_MODE`.
3. Observe Probe state and execution log.

**Expected Result**

- The command is accepted by the whitelist.
- Probe mode changes to safe mode.
- The command log records a successful low-risk action.

### 2.2 DISABLE_PAYLOAD and ENABLE_PAYLOAD

**Goal**

Verify payload command behavior.

**Steps**

1. Execute `DISABLE_PAYLOAD`.
2. Confirm that payload state changes to disabled.
3. Execute `ENABLE_PAYLOAD`.
4. Confirm that payload state changes back to enabled.

**Expected Result**

- Both commands are accepted when policy allows them.
- Payload state updates are visible in telemetry or state panels.

### 2.3 RESET_THERMAL_CONTROLLER

**Goal**

Verify layered thermal recovery behavior.

**Steps**

1. Inject a thermal fault.
2. Execute or dry-run `RESET_THERMAL_CONTROLLER`.
3. Observe temperature, controller state, and remaining degraded flags.

**Expected Result**

- The thermal controller recovery action is accepted as an allowed command.
- Controller-related fields can improve.
- Physical degradation such as radiator damage may remain visible by design.

### 2.4 High-Risk Commands

**Goal**

Confirm that high-risk commands are visible but properly gated.

**Commands**

- `RESTART_COMMS`
- `REBOOT_COMPUTER`
- `EXIT_SAFE_MODE`

**Expected Result**

- High-risk commands are not silently executed.
- Manual approval or policy review is required.
- The UI explains why approval is disabled when the command is not policy-safe.

## 3. E4B Diagnosis

### 3.1 Run Onboard E4B Diagnosis

**Goal**

Confirm that the frontend can call the Probe backend and that the backend can call the remote
Gemma/E4B model.

**Steps**

1. Open Mission Control.
2. Trigger the onboard E4B diagnosis action.
3. Watch the backend terminal for the model request.
4. Inspect the returned diagnosis and recommendation.

**Expected Result**

- The backend receives the request.
- The model adapter returns a structured diagnosis.
- The UI shows a diagnosis, risk signal, and recommended recovery action.

## 4. Ground Twin Entry

![Ground Twin live workspace](<../../images/twin mainpage.png>)

### 4.1 Open Ground Twin

**Goal**

Confirm that the Digital Twin workflow is available as a separate workspace.

**Steps**

1. Click `Ground Twin` from Mission Control, or open `/twin` directly.
2. Check the Live Analysis area, right-side context panels, and Ground Twin Testbed.

**Expected Result**

- The Ground Twin page renders.
- Probe link status remains available.
- Live analysis and testbed controls are visible.

## 5. Ground Twin Live Analysis

![Ground Twin initial state](../../images/twin-2.png)

### 5.1 Analyze Current State

![Live analysis result](../../images/twin-3.png)

**Goal**

Freeze the current Probe state, run the recovery orchestrator, generate candidate plans, run
Twin compare, and load playback for the recommended plan when the baseline is fresh.

**Steps**

1. Ensure Probe Link is `ONLINE`.
2. Choose the desired Brain Mode.
3. Click `Analyze Current State`.
4. Wait for diagnosis, plan generation, Twin compare, and playback loading.

**Expected Result**

- A baseline digest and sequence number are created.
- Candidate plans appear in Plan Compare.
- A Twin verdict is shown.
- Playback loads only when the baseline is valid and fresh.

### 5.2 Baseline Status

**Goal**

Understand when a Ground Twin baseline can be used for playback and plan comparison.

**Baseline States**

- `fresh`: Safe to use for compare and playback.
- `stale`: The real Probe has moved beyond the baseline sequence.
- `expired`: The baseline exceeded its time-to-live.
- `invalidated`: The real Probe state changed in a way that makes the baseline unsafe to reuse.

**Expected Result**

- Fresh baselines can load plan playback.
- Stale, expired, or invalidated baselines should trigger a new analysis or compare before playback.
- Old playback should not be reused after baseline invalidation.

### 5.3 Refresh Baseline

**Goal**

Use the current real Probe state as the new Twin starting point.

**Steps**

1. Click `Refresh Baseline`.
2. Wait for a new digest and sequence number.
3. Run analysis or compare again.

**Expected Result**

- The baseline digest changes.
- The baseline state returns to fresh if the Probe state is stable.
- Plan playback is regenerated from the new baseline.

### 5.4 Snapshot

**Goal**

Fetch simulation-ready metadata for the current Probe state.

**Steps**

1. Click `Snapshot`.
2. Inspect digest, sequence, timestamp, and telemetry metadata.

**Expected Result**

- Snapshot metadata matches the current real Probe state.
- The snapshot can be used as the input for Twin analysis.

### 5.5 Reset Twin

**Goal**

Clear frontend Twin analysis state without resetting the real Probe.

**Steps**

1. Click `Reset Twin`.
2. Confirm that plan comparison, playback, and selected plan state are cleared.

**Expected Result**

- Twin analysis panels return to idle.
- The real Probe state remains unchanged.

## 6. Brain Mode Tests

### 6.1 Classic Python Mode

**Goal**

Test deterministic Python-orchestrated diagnosis and plan generation.

**Steps**

1. Select `Classic Python`.
2. Run `Analyze Current State`.
3. Inspect diagnosis, plans, and Twin verdict.

**Expected Result**

- The session is deterministic and fast.
- Candidate plans are generated by the Python orchestrator.
- The recommendation can still be reviewed before execution.

### 6.2 Gemma Helm Mode

**Goal**

Test Gemma/E4B-led diagnosis and recommendation generation.

**Steps**

1. Select `Gemma Helm`.
2. Run analysis.
3. Inspect Helm dialogue, diagnosis text, recommended action, and policy gate.

**Expected Result**

- The backend calls the remote model service.
- Helm dialogue explains the reasoning path.
- The final recommendation remains constrained by policy.

### 6.3 Full Auto Armed Mode

![Full Auto Armed](../../images/command-1.png)

**Goal**

Confirm that the UI reflects full automatic monitoring and execution mode when enabled.

**Expected Result**

- Review mode can show `Auto`.
- Execution mode can show `Auto Step`.
- Policy still blocks unsafe actions.
- Low-risk actions can execute automatically only when the gate allows them.

## 7. Review and Execution Modes

### 7.1 Manual Review

**Goal**

Require explicit human approval before execution.

**Expected Result**

- Recommendations are shown but not executed automatically.
- `Approve Plan` or equivalent approval controls must be used by the operator.

### 7.2 Assisted Review

**Goal**

Allow the system to recommend an action while the operator remains in control.

**Expected Result**

- A recommended plan is selected.
- Human approval is still required before live execution.

### 7.3 Auto Review

**Goal**

Allow the system to select an acceptable plan automatically while preserving policy enforcement.

**Expected Result**

- The system can select the recommended plan.
- Policy gate can still downgrade or block execution.
- Unsafe actions remain unavailable.

### 7.4 Dry-Run Step and Dry-Run Plan

**Goal**

Verify execution simulation without changing the real Probe state.

**Steps**

1. Select a recommendation.
2. Run dry-run step or dry-run plan.
3. Inspect execution log output.

**Expected Result**

- The UI shows what would be executed.
- Probe state is not changed.
- The result is useful for operator review.

### 7.5 Live Low-Risk Execution

![Gemma Helm recovery](../../images/command-2.png)

**Goal**

Verify that low-risk commands can be executed live when full auto and policy allow it.

**Steps**

1. Start the backend with full auto settings.
2. Trigger a recoverable low-risk fault.
3. Let Helm choose the recommendation.
4. Confirm that the command executes only if the policy gate allows it.

**Expected Result**

- Low-risk commands can execute live.
- The execution log records the selected command.
- The Helm decision trace explains the action and policy result.

## 8. Playback, Inspector, and Plan Compare

### 8.1 Plan Compare

![Plan compare](../../images/plancompare.png)

**Goal**

Compare candidate recovery plans generated from the same baseline.

**Steps**

1. Run analysis with a fresh baseline.
2. Inspect Conservative and Aggressive candidates.
3. Compare risk, recovery time, payload impact, and verdict.

**Expected Result**

- Each plan has a verdict.
- Risk and constraint status are visible.
- The recommended plan is clearly indicated.

### 8.2 Playback Timeline

![Playback and inspector](../../images/timeline+inspector.png)

**Goal**

Replay the Twin-predicted trajectory for the selected plan.

**Steps**

1. Select a valid plan from Plan Compare.
2. Use playback controls to step or play.
3. Observe telemetry projection and inspector state.

**Expected Result**

- Timeline controls are enabled when playback exists.
- The selected frame updates the inspector.
- Playback is blocked if the baseline is stale, expired, or invalidated.

### 8.3 Twin Inspector

**Goal**

Inspect subsystem state for the selected playback frame.

**Expected Result**

- Visible telemetry includes real and predicted values.
- Hidden state displays root cause, recoverability, mitigation, and symptoms.
- Current action effect is shown when a plan step applies at the frame.

### 8.4 Telemetry Projection

**Goal**

View Real versus Twin predicted telemetry against threshold limits.

**Expected Result**

- Real telemetry and Twin-predicted telemetry are visually distinct.
- Threshold lines are visible where relevant.
- The projection matches the selected playback frame and plan.

### 8.5 Constraints Panel

![Constraint panel](../../images/twin-4.png)

**Goal**

Verify whether the selected plan satisfies safety and mission constraints.

**Expected Result**

- Passing constraints are marked as pass.
- Failed constraints identify the reason.
- Approval controls reflect the policy outcome.

## 9. Demo Scenario Mode

### 9.1 Built-In Scenario

**Goal**

Run a repeatable scenario that does not depend on the current real fault state.

**Steps**

1. Select a demo scenario if available.
2. Run the scenario.
3. Inspect generated diagnosis, plans, playback, and constraints.

**Expected Result**

- The scenario produces deterministic demo output.
- Plan comparison and playback can be shown without manually injecting each fault.

## 10. Ground Twin Testbed

### 10.1 Freeze Baseline

![Ground Twin baseline and assembly](../../images/modular-1.png)

**Goal**

Create a Ground Twin testbed session and freeze the current baseline.

**Steps**

1. Open the Ground Twin Testbed panel.
2. Click `Freeze Baseline`.
3. Inspect session, baseline, calibration, and Twin fault counters.

**Expected Result**

- A testbed session is created.
- Baseline metadata is visible.
- Assembly controls become available.

### 10.2 Assembly Workbench

![Valid assembly graph](../../images/modular-2.png)

**Goal**

Verify that the component graph can be assembled and validated.

**Steps**

1. Select the component graph or assembly view.
2. Add or inspect installed nodes.
3. Validate the graph.

**Expected Result**

- The graph shows installed components.
- The validation result reaches `VALID` when blockers are resolved.
- Digest/version metadata updates after graph changes.

### 10.3 Inject Twin Fault

![Component ports and fault templates](../../images/modular-3.png)

**Goal**

Inject faults into the Ground Twin only, without changing the real Probe.

**Steps**

1. Select an installed component.
2. Choose a fault template.
3. Inject the Twin fault.

**Expected Result**

- The Twin fault counter increases.
- The real Probe telemetry does not change.
- Future campaign or compare output reflects the injected Twin condition.

### 10.4 Run Campaign

**Goal**

Score candidate repairs across environment branches and deterministic seeds.

**Steps**

1. Freeze a baseline.
2. Prepare the assembly state.
3. Click `Run Campaign`.

**Expected Result**

- Candidate repairs are scored.
- Campaign output identifies the more robust plan.
- Results can feed command package generation.

### 10.5 Build Package, Approve, and Simulate Uplink

**Goal**

Generate a command package after campaign selection and simulate uplink.

**Steps**

1. Build the command package.
2. Approve it if policy allows.
3. Simulate uplink.

**Expected Result**

- A package is built from the selected plan.
- Approval remains policy-gated.
- The uplink queue reflects the simulated package state.

## 11. Autonomous Monitoring

### 11.1 Nominal Auto Monitor

**Goal**

Confirm that Helm does not repair a healthy Probe unnecessarily.

**Steps**

1. Reset Probe state.
2. Keep Full Auto Armed running.
3. Watch auto-session updates.

**Expected Result**

- The monitor may report standby or no action.
- No unnecessary command is executed.

### 11.2 Thermal Auto Monitor

**Goal**

Confirm that Helm detects a thermal fault and attempts a policy-safe recovery.

**Steps**

1. Inject a thermal fault.
2. Wait for the next auto-monitor cycle.
3. Inspect the diagnosis, recommendation, and execution result.

**Expected Result**

- Thermal risk is detected.
- A low-risk mitigation may be selected.
- Live execution occurs only when the policy gate allows it.

### 11.3 Communications HITL Monitor

**Goal**

Confirm that high-risk communications recovery remains human-in-the-loop.

**Steps**

1. Inject a communications fault.
2. Wait for auto-monitor output.
3. Inspect the recommended command and approval state.

**Expected Result**

- Communications risk is detected.
- High-risk recovery is recommended but not automatically executed.
- The UI explains the manual approval requirement.

## 12. Open MCT

### 12.1 Telemetry Root

![Open MCT telemetry root](../../images/mct-1.png)

**Goal**

Verify that Open MCT exposes both real and Twin telemetry roots.

**Expected Result**

- `real/*` telemetry channels are visible.
- `twin/*` predicted channels are visible when Twin data exists.
- Channel names match the Mission Control telemetry model.

### 12.2 Real Telemetry Channels

![Open MCT real telemetry channels](../../images/mct-2.png)

**Goal**

Verify live real telemetry in Open MCT.

**Expected Result**

- Temperature, voltage, communications, and controller channels are available.
- Values refresh from the backend.
- The channel table or plot view matches Mission Control state.

### 12.3 Temperature Plot

![Open MCT temperature plot](../../images/mct-3.png)

**Goal**

Verify plotting for real telemetry.

**Expected Result**

- The temperature plot renders over time.
- New data points arrive while the backend is running.
- Fault injection is reflected in the trend.

### 12.4 Twin Predicted Channels

![Open MCT twin predicted channel](../../images/mct-4.png)

**Goal**

Verify predicted telemetry generated by Twin analysis.

**Expected Result**

- Twin predicted channels appear after analysis or playback is available.
- Predicted battery, temperature, or mission channels can be plotted.
- Predicted telemetry remains distinct from real Probe telemetry.

## 13. Recommended Demo Paths

### 13.1 Basic Link Demo

1. Start remote E4B/vLLM.
2. Start the Probe backend.
3. Start Vite.
4. Open Mission Control and confirm Probe Link is online.
5. Show real telemetry.
6. Inject a thermal fault.
7. Run E4B diagnosis.
8. Show recommendation and policy gate.

**Expected Story**

DeepRepair connects a live spacecraft-style Probe simulator to a reasoning backend, detects
an injected fault, and presents a policy-controlled recovery recommendation.

### 13.2 Helm Auto Recovery Demo

1. Reset Probe state.
2. Enable Full Auto Armed mode.
3. Inject a thermal fault.
4. Wait for Helm auto-session output.
5. Show the Helm dialogue, recommendation, policy gate, and execution trace.

**Expected Story**

The system can move from detection to recommendation to low-risk recovery while preserving
policy gates and operator visibility.

### 13.3 Ground Twin Plan Demo

1. Open Ground Twin.
2. Run `Analyze Current State`.
3. Show Plan Compare.
4. Show playback timeline.
5. Show inspector hidden state and constraints.

**Expected Story**

The Ground Twin evaluates candidate recovery plans before execution, compares outcomes, and
blocks unsafe playback when the baseline is no longer valid.

### 13.4 Ground Twin Testbed Demo

1. Freeze a baseline.
2. Open Assembly Workbench.
3. Show a valid modular graph.
4. Select a component and inject a Twin-only fault.
5. Run a campaign.
6. Build a command package and simulate uplink.

**Expected Story**

The testbed separates real Probe state from experimental Twin faults, allowing repeatable
repair package evaluation before any real command is considered.

### 13.5 Open MCT Demo

1. Open Open MCT.
2. Show `real/*` telemetry channels.
3. Show the temperature plot.
4. Run or load Twin analysis.
5. Show `twin/*` predicted telemetry.

**Expected Story**

Mission Control telemetry and Twin predictions are available through an operations-style
telemetry browser.

## 14. Operational Notes

### 14.1 Why Baselines Become Invalidated

The Ground Twin freezes a baseline at a specific Probe digest and sequence number. When the
real Probe state changes through fault injection, reset, command execution, or live telemetry
advance, the old baseline may no longer represent the current world state. In that case, the
frontend should request a new analysis or compare instead of loading old playback.

### 14.2 Why Thermal State May Remain Degraded After Recovery

`RESET_THERMAL_CONTROLLER` represents a controller recovery action. It can improve controller
state, but it does not necessarily repair physical degradation such as a damaged radiator.
Residual thermal symptoms can therefore remain visible after the controller reset.

### 14.3 Whether Approve Plan Changes Probe State

Approval alone should not change the real Probe state. State changes occur only when a live
execution command is sent and accepted by the backend policy gate.

### 14.4 Why Playback Can Look Subtle

Some plans mitigate risk without creating dramatic visual changes. The clearest evidence is
often in the telemetry projection, constraints panel, risk score, and hidden-state inspector
rather than the 3D scene alone.

### 14.5 Whether REBOOT_COMPUTER Reboots the Mac

No. In this demo, `REBOOT_COMPUTER` is a simulated Probe command routed through the backend
policy layer. It does not reboot the local Mac.

## 15. Final Acceptance Checklist

- [ ] Remote E4B/vLLM service is running.
- [ ] Probe backend health checks pass.
- [ ] Mission Control shows Probe Link online.
- [ ] Real telemetry is visible and refreshes.
- [ ] Thermal, communications, power, and sensor faults can be injected.
- [ ] Faults can be cleared and Probe state can be reset.
- [ ] Whitelisted low-risk commands execute only through the backend.
- [ ] High-risk commands remain policy-gated.
- [ ] E4B diagnosis returns a structured recommendation.
- [ ] Ground Twin analysis creates a baseline, plans, verdict, and playback when valid.
- [ ] Stale, expired, or invalidated baselines do not reuse old playback.
- [ ] Plan Compare shows candidate risk, recovery, payload, and verdict.
- [ ] Playback Timeline, Twin Inspector, Telemetry Projection, and Constraints panels render.
- [ ] Full Auto Armed mode still respects policy gates.
- [ ] Ground Twin Testbed can freeze a baseline and show modular assembly state.
- [ ] Twin-only faults do not mutate the real Probe state.
- [ ] Open MCT exposes real and predicted telemetry channels.
- [ ] The recommended demo path can be completed end to end.
