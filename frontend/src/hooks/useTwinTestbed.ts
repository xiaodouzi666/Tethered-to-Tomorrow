import { useCallback, useMemo, useState } from 'react';
import {
  addTwinTestbedComponent,
  addTwinTestbedLink,
  createTwinTestbedCommandPackage,
  getTwinAssemblyCatalog,
  getTwinTestbedAssembly,
  injectTwinTestbedComponentFault,
  injectTwinTestbedFaults,
  redoTwinTestbedAssembly,
  removeTwinTestbedComponent,
  removeTwinTestbedLink,
  replaceTwinTestbedComponent,
  runTwinTestbedCampaign,
  selectTwinTestbedComponent,
  startTwinTestbed,
  troubleshootTwinTestbed,
  transformTwinTestbedComponent,
  undoTwinTestbedAssembly,
  updateTwinTestbedComponentParameters,
  validateTwinTestbedAssembly
} from '../api/twinClient';
import {
  approveUplinkPackage,
  executeUplinkPackage,
  getUplinkPackage
} from '../api/uplinkClient';
import type {
  CampaignResponse,
  CommandPackage,
  ComponentFaultTemplate,
  ComponentLinkRequest,
  ComponentOperationRequest,
  ComponentTransformRequest,
  GroundTestbedSession,
  TroubleshootingResponse,
  TwinAssemblyCatalog,
  TwinAssemblyState,
  TwinEnvironmentConfig,
  TwinFaultSpec
} from '../types/twin';

const defaultFaults: TwinFaultSpec[] = [
  {
    id: 'ground-comms-misalignment',
    category: 'antenna_misalignment',
    severity: 0.62,
    start_t: 0,
    duration: 600,
    parameters: { alignment_error_deg: 5.5 },
    layer: 'root_cause',
    source: 'ground_testbed'
  },
  {
    id: 'ground-comms-softlock',
    category: 'transceiver_softlock',
    severity: 0.55,
    start_t: 0,
    duration: 180,
    layer: 'recoverable',
    clearable_by: ['RESTART_COMMS'],
    source: 'ground_testbed'
  }
];

const environmentBranches: TwinEnvironmentConfig[] = [
  {
    sun_exposure: 1,
    eclipse_factor: 0.05,
    radiation_level: 0.02,
    antenna_alignment_error_deg: 0,
    battery_age_factor: 1,
    thermal_sink_efficiency: 1,
    mission_phase: 'cruise'
  },
  {
    sun_exposure: 1,
    eclipse_factor: 0.08,
    radiation_level: 0.05,
    antenna_alignment_error_deg: 0.3,
    battery_age_factor: 1,
    thermal_sink_efficiency: 0.99,
    mission_phase: 'radiation-watch'
  },
  {
    sun_exposure: 0.98,
    eclipse_factor: 0.1,
    radiation_level: 0.06,
    antenna_alignment_error_deg: 0.6,
    battery_age_factor: 0.995,
    thermal_sink_efficiency: 0.98,
    mission_phase: 'alignment-stress'
  }
];

export function useTwinTestbed() {
  const [session, setSession] = useState<GroundTestbedSession | null>(null);
  const [campaign, setCampaign] = useState<CampaignResponse | null>(null);
  const [commandPackage, setCommandPackage] = useState<CommandPackage | null>(null);
  const [catalog, setCatalog] = useState<TwinAssemblyCatalog | null>(null);
  const [assembly, setAssembly] = useState<TwinAssemblyState | null>(null);
  const [troubleshooting, setTroubleshooting] = useState<TroubleshootingResponse | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedComponent = useMemo(() => {
    if (!assembly?.selected_component_id) return null;
    return assembly.components.find((component) => component.instance_id === assembly.selected_component_id && component.install_state !== 'removed') ?? null;
  }, [assembly]);

  const selectedScore = useMemo(() => {
    if (!campaign) return null;
    return campaign.scores.find((score) => score.plan_id === campaign.best_plan_id) ?? null;
  }, [campaign]);

  const buildPackageGateReason = useMemo(() => {
    if (!session) return 'Freeze a baseline first.';
    if (!assembly) return 'Assembly state is not loaded.';
    if (!assembly.validation.ok) return assembly.validation.issues[0]?.message ?? 'Assembly graph is invalid.';
    if (!campaign) return 'Run a campaign first.';
    if (campaign.assembly_digest !== assembly.assembly_digest || campaign.assembly_version !== assembly.version) {
      return 'Assembly changed after campaign; rerun campaign.';
    }
    if (!selectedScore) return 'Campaign score is missing.';
    if (selectedScore.verdict !== 'PASS') return `Best plan verdict is ${selectedScore.verdict}; PASS is required.`;
    if (selectedScore.pass_rate < 0.8) return `Best plan pass rate is ${(selectedScore.pass_rate * 100).toFixed(0)}%; at least 80% is required.`;
    return campaign.gate_reason || '';
  }, [assembly, campaign, selectedScore, session]);

  const canBuildPackage = Boolean(
    session &&
    assembly?.validation.ok &&
    campaign &&
    selectedScore?.verdict === 'PASS' &&
    selectedScore.pass_rate >= 0.8 &&
    campaign.assembly_digest === assembly.assembly_digest &&
    campaign.assembly_version === assembly.version
  );

  const packageGateReason = useMemo(() => {
    if (!commandPackage) return 'Build a package first.';
    if (!assembly) return 'Assembly state is not loaded.';
    if (commandPackage.gate_status === 'blocked') return commandPackage.gate_reason || 'Package gate is blocked.';
    if (commandPackage.assembly_digest !== assembly.assembly_digest || commandPackage.assembly_version !== assembly.version) {
      return 'Assembly changed after package build.';
    }
    if (!assembly.validation.ok) return assembly.validation.issues[0]?.message ?? 'Assembly graph is invalid.';
    if (commandPackage.pass_rate < 0.8) return `Package pass rate is ${(commandPackage.pass_rate * 100).toFixed(0)}%; at least 80% is required.`;
    if (commandPackage.risk_score >= 60) return `Package risk is ${commandPackage.risk_score.toFixed(1)}; must be below 60.0.`;
    return commandPackage.gate_reason || '';
  }, [assembly, commandPackage]);

  const packageGateOpen = Boolean(
    commandPackage &&
    assembly?.validation.ok &&
    commandPackage.gate_status !== 'blocked' &&
    commandPackage.assembly_digest === assembly.assembly_digest &&
    commandPackage.assembly_version === assembly.version &&
    commandPackage.pass_rate >= 0.8 &&
    commandPackage.risk_score < 60
  );
  const canApprovePackage = Boolean(commandPackage && commandPackage.status === 'DRAFT' && packageGateOpen);
  const canExecutePackage = Boolean(commandPackage && commandPackage.status === 'APPROVED' && packageGateOpen);

  const clearStaleSafetyArtifacts = useCallback((nextAssembly: TwinAssemblyState) => {
    setAssembly(nextAssembly);
    setCampaign(null);
    setCommandPackage(null);
  }, []);

  const start = useCallback(async () => {
    setLoading('freeze');
    setError(null);
    try {
      const next = await startTwinTestbed();
      const [nextCatalog, nextAssembly] = await Promise.all([
        getTwinAssemblyCatalog(),
        getTwinTestbedAssembly(next.session_id)
      ]);
      setSession(next);
      setCatalog(nextCatalog);
      setAssembly(nextAssembly);
      setCampaign(null);
      setCommandPackage(null);
      setTroubleshooting(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, []);

  const injectCommsFault = useCallback(async () => {
    if (!session) {
      setError('Start a Ground Twin session first.');
      return;
    }
    setLoading('faults');
    setError(null);
    try {
      setSession(await injectTwinTestbedFaults(session.session_id, {
        faults: defaultFaults,
        label: 'ground_testbed_comms_fault'
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [session]);

  const selectComponent = useCallback(async (componentId: string) => {
    if (!session) return;
    setLoading('select-component');
    setError(null);
    try {
      setAssembly(await selectTwinTestbedComponent(session.session_id, componentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [session]);

  const addComponent = useCallback(async (payload: ComponentOperationRequest) => {
    if (!session) {
      setError('Start a Ground Twin session first.');
      return;
    }
    setLoading('add-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await addTwinTestbedComponent(session.session_id, payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const addSpareSensor = useCallback(async () => {
    await addComponent({
      catalog_id: 'payload.sensor',
      display_name: 'Hot-swapped Spare Sensor',
      slot: 'sensor_mount_spare',
      parameters: { primary: false, hot_swap: true },
      position: { x: 1.45, y: -0.3, z: 1.15 }
    });
  }, [addComponent]);

  const removeSelectedComponent = useCallback(async () => {
    if (!session || !assembly?.selected_component_id) return;
    setLoading('remove-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await removeTwinTestbedComponent(session.session_id, assembly.selected_component_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [assembly?.selected_component_id, clearStaleSafetyArtifacts, session]);

  const transformComponent = useCallback(async (componentId: string, payload: ComponentTransformRequest) => {
    if (!session) return;
    setLoading('transform-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await transformTwinTestbedComponent(session.session_id, componentId, payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const updateSelectedParameters = useCallback(async (parameters: Record<string, unknown>) => {
    if (!session || !selectedComponent) return;
    setLoading('component-params');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await updateTwinTestbedComponentParameters(session.session_id, selectedComponent.instance_id, { parameters }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, selectedComponent, session]);

  const replaceSelectedComponent = useCallback(async (catalogId: string) => {
    if (!session || !selectedComponent) return;
    setLoading('replace-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await replaceTwinTestbedComponent(session.session_id, selectedComponent.instance_id, { catalog_id: catalogId }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, selectedComponent, session]);

  const addLink = useCallback(async (payload: ComponentLinkRequest) => {
    if (!session) return;
    setLoading('link-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await addTwinTestbedLink(session.session_id, payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const removeLink = useCallback(async (linkId: string) => {
    if (!session) return;
    setLoading('unlink-component');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await removeTwinTestbedLink(session.session_id, linkId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const validateAssembly = useCallback(async () => {
    if (!session) return;
    setLoading('validate-assembly');
    setError(null);
    try {
      setAssembly(await validateTwinTestbedAssembly(session.session_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [session]);

  const undoAssembly = useCallback(async () => {
    if (!session) return;
    setLoading('undo-assembly');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await undoTwinTestbedAssembly(session.session_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const redoAssembly = useCallback(async () => {
    if (!session) return;
    setLoading('redo-assembly');
    setError(null);
    try {
      clearStaleSafetyArtifacts(await redoTwinTestbedAssembly(session.session_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [clearStaleSafetyArtifacts, session]);

  const injectSelectedFault = useCallback(async (template?: ComponentFaultTemplate | null) => {
    if (!session || !selectedComponent) {
      setError('Select a component in the Ground Twin assembly first.');
      return;
    }
    const faultTemplate = template ?? selectedComponent.fault_templates[0];
    if (!faultTemplate) {
      setError(`${selectedComponent.display_name} has no fault template.`);
      return;
    }
    setLoading('component-fault');
    setError(null);
    try {
      const result = await injectTwinTestbedComponentFault(session.session_id, {
        component_id: selectedComponent.instance_id,
        template_id: faultTemplate.template_id,
        severity: faultTemplate.default_severity
      });
      setAssembly(result.assembly);
      setSession(result.session);
      setCampaign(null);
      setCommandPackage(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [selectedComponent, session]);

  const requestTroubleshooting = useCallback(async () => {
    if (!session) {
      setError('Start a Ground Twin session first.');
      return;
    }
    setLoading('troubleshoot');
    setError(null);
    try {
      const result = await troubleshootTwinTestbed(session.session_id, {
        component_id: assembly?.selected_component_id ?? undefined,
        situation: 'operator_requested_component_troubleshooting',
        include_gemma: true
      });
      setTroubleshooting(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [assembly?.selected_component_id, session]);

  const runCampaign = useCallback(async () => {
    if (!session) {
      setError('Start a Ground Twin session first.');
      return;
    }
    setLoading('campaign');
    setError(null);
    try {
      const result = await runTwinTestbedCampaign(session.session_id, {
        environment_branches: environmentBranches,
        horizon_sec: 60,
        dt: 1,
        seeds: [1, 2, 3]
      });
      setCampaign(result);
      setSession({
        ...session,
        last_campaign: result,
        selected_plan_id: result.best_plan_id,
        status: 'CAMPAIGN_COMPLETE',
        assembly_id: result.assembly_id,
        assembly_version: result.assembly_version,
        assembly_digest: result.assembly_digest
      });
      setCommandPackage(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [session]);

  const buildPackage = useCallback(async () => {
    if (!session) {
      setError('Start a Ground Twin session first.');
      return;
    }
    if (!canBuildPackage) {
      setError(buildPackageGateReason || 'Build Package gate is blocked.');
      return;
    }
    setLoading('package');
    setError(null);
    try {
      const result = await createTwinTestbedCommandPackage(session.session_id, {
        plan_id: campaign?.best_plan_id ?? session.selected_plan_id ?? undefined
      });
      setCommandPackage(result);
      setSession({ ...session, command_package_id: result.package_id, status: 'COMMAND_PACKAGE_DRAFT' });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [buildPackageGateReason, campaign?.best_plan_id, canBuildPackage, session]);

  const approvePackage = useCallback(async () => {
    if (!commandPackage) return;
    if (!canApprovePackage) {
      setError(packageGateReason || 'Approval gate is blocked.');
      return;
    }
    setLoading('approve');
    setError(null);
    try {
      setCommandPackage(await approveUplinkPackage(commandPackage.package_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [canApprovePackage, commandPackage, packageGateReason]);

  const executePackage = useCallback(async () => {
    if (!commandPackage) return;
    if (!canExecutePackage) {
      setError(packageGateReason || 'Uplink gate is blocked.');
      return;
    }
    setLoading('uplink');
    setError(null);
    try {
      const started = await executeUplinkPackage(commandPackage.package_id);
      setCommandPackage(started);
      window.setTimeout(async () => {
        try {
          setCommandPackage(await getUplinkPackage(started.package_id));
        } catch {
          // best-effort refresh after simulated one-way delay
        }
      }, Math.max(1000, started.uplink_delay_s * 1000 + 600));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [canExecutePackage, commandPackage, packageGateReason]);

  return {
    addComponent,
    addLink,
    addSpareSensor,
    approvePackage,
    assembly,
    buildPackage,
    buildPackageGateReason,
    campaign,
    canApprovePackage,
    canBuildPackage,
    canExecutePackage,
    catalog,
    commandPackage,
    error,
    executePackage,
    injectCommsFault,
    injectSelectedFault,
    loading,
    packageGateReason,
    redoAssembly,
    removeLink,
    removeSelectedComponent,
    requestTroubleshooting,
    replaceSelectedComponent,
    runCampaign,
    selectedComponent,
    selectComponent,
    session,
    start,
    transformComponent,
    troubleshooting,
    undoAssembly,
    updateSelectedParameters,
    validateAssembly
  };
}
