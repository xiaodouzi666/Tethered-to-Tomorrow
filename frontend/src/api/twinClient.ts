import type {
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
  FaultInjectionRequest,
  RecoveryEvaluationRequest,
  RecoveryEvaluationResponse,
  FreezeBaselineResponse,
  GroundTestbedSession,
  PlanPlaybackBundle,
  SimulationCampaignRequest,
  TroubleshootingRequest,
  TroubleshootingResponse,
  TwinAssemblyCatalog,
  TwinAssemblyState,
  TwinCompareFromBaselineRequest,
  TwinCompareRequest,
  TwinCompareResponse,
  TwinRunRequest,
  TwinRunResponse,
  TwinSnapshotResponse
} from '../types/twin';

const apiBase = import.meta.env.VITE_PROBE_API_BASE || 'http://localhost:8010';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    }
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function runTwin(payload: TwinRunRequest): Promise<TwinRunResponse> {
  return request<TwinRunResponse>('/api/twin/run', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function comparePlans(payload: TwinCompareRequest): Promise<TwinCompareResponse> {
  return request<TwinCompareResponse>('/api/twin/compare', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function comparePlansFromBaseline(payload: TwinCompareFromBaselineRequest): Promise<TwinCompareResponse> {
  return request<TwinCompareResponse>('/api/twin/compare/from-baseline', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getTwinSnapshot(): Promise<TwinSnapshotResponse> {
  return request<TwinSnapshotResponse>('/api/twin/snapshot');
}

export async function freezeBaseline(): Promise<FreezeBaselineResponse> {
  return request<FreezeBaselineResponse>('/api/twin/baseline/freeze', {
    method: 'POST'
  });
}

export async function evaluateCurrentRecovery(
  payload: RecoveryEvaluationRequest
): Promise<RecoveryEvaluationResponse> {
  return request<RecoveryEvaluationResponse>('/api/recovery/evaluate-current', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getPlanPlayback(compareId: string, planId: string): Promise<PlanPlaybackBundle> {
  return request<PlanPlaybackBundle>(`/api/twin/compare/${encodeURIComponent(compareId)}/plan/${encodeURIComponent(planId)}/playback`);
}

export async function startTwinTestbed(): Promise<GroundTestbedSession> {
  return request<GroundTestbedSession>('/api/twin/testbed/start', {
    method: 'POST'
  });
}

export async function injectTwinTestbedFaults(
  sessionId: string,
  payload: FaultInjectionRequest
): Promise<GroundTestbedSession> {
  return request<GroundTestbedSession>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/faults`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function runTwinTestbedCampaign(
  sessionId: string,
  payload: SimulationCampaignRequest
): Promise<CampaignResponse> {
  return request<CampaignResponse>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/campaign`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function createTwinTestbedCommandPackage(
  sessionId: string,
  payload: CommandPackageRequest
): Promise<CommandPackage> {
  return request<CommandPackage>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/command-package`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getTwinAssemblyCatalog(): Promise<TwinAssemblyCatalog> {
  return request<TwinAssemblyCatalog>('/api/twin/assembly/catalog');
}

export async function getTwinTestbedAssembly(sessionId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly`);
}

export async function addTwinTestbedComponent(
  sessionId: string,
  payload: ComponentOperationRequest
): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function removeTwinTestbedComponent(sessionId: string, componentId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component/${encodeURIComponent(componentId)}`, {
    method: 'DELETE'
  });
}

export async function transformTwinTestbedComponent(
  sessionId: string,
  componentId: string,
  payload: ComponentTransformRequest
): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component/${encodeURIComponent(componentId)}/transform`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export async function updateTwinTestbedComponentParameters(
  sessionId: string,
  componentId: string,
  payload: ComponentParametersRequest
): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component/${encodeURIComponent(componentId)}/parameters`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export async function replaceTwinTestbedComponent(
  sessionId: string,
  componentId: string,
  payload: ComponentReplaceRequest
): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component/${encodeURIComponent(componentId)}/replace`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function selectTwinTestbedComponent(sessionId: string, componentId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/component/${encodeURIComponent(componentId)}/select`, {
    method: 'POST'
  });
}

export async function addTwinTestbedLink(
  sessionId: string,
  payload: ComponentLinkRequest
): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/link`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function removeTwinTestbedLink(sessionId: string, linkId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/link/${encodeURIComponent(linkId)}`, {
    method: 'DELETE'
  });
}

export async function validateTwinTestbedAssembly(sessionId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/validate`, {
    method: 'POST'
  });
}

export async function undoTwinTestbedAssembly(sessionId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/undo`, {
    method: 'POST'
  });
}

export async function redoTwinTestbedAssembly(sessionId: string): Promise<TwinAssemblyState> {
  return request<TwinAssemblyState>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/redo`, {
    method: 'POST'
  });
}

export async function injectTwinTestbedComponentFault(
  sessionId: string,
  payload: ComponentFaultInjectionRequest
): Promise<ComponentFaultInjectionResponse> {
  return request<ComponentFaultInjectionResponse>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/assembly/fault`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function troubleshootTwinTestbed(
  sessionId: string,
  payload: TroubleshootingRequest
): Promise<TroubleshootingResponse> {
  return request<TroubleshootingResponse>(`/api/twin/testbed/${encodeURIComponent(sessionId)}/troubleshoot`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}
