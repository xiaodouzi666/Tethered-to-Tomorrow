import type {
  TwinCompareRequest,
  TwinEnvironmentConfig,
  TwinFaultSpec,
  TwinPlanStep,
  TwinRunRequest
} from '../types/twin';

export type TwinScenario = 'nominal' | 'thermal' | 'comms' | 'power';

export function buildDemoRunRequest(
  scenario: TwinScenario,
  environment: TwinEnvironmentConfig
): TwinRunRequest {
  return {
    from_snapshot: 'latest',
    environment,
    faults: faultsForScenario(scenario),
    actions: actionsForScenario(scenario),
    horizon_sec: 300,
    dt: 1,
    stochastic: false
  };
}

export function buildDemoCompareRequest(
  scenario: TwinScenario,
  environment: TwinEnvironmentConfig
): TwinCompareRequest {
  return {
    from_snapshot: 'latest',
    environment,
    faults: faultsForScenario(scenario),
    plans: [
      { id: 'plan-a', label: 'Conservative', actions: conservativeActionsForScenario(scenario) },
      { id: 'plan-b', label: 'Standard', actions: actionsForScenario(scenario) },
      { id: 'plan-c', label: 'Aggressive', actions: aggressiveActionsForScenario(scenario) }
    ],
    horizon_sec: 300,
    dt: 1,
    stochastic: false
  };
}

function faultsForScenario(scenario: TwinScenario): TwinFaultSpec[] {
  if (scenario === 'nominal') return [];
  if (scenario === 'thermal') {
    return [{
      id: 'thermal-radiator-degrade',
      category: 'thermal',
      severity: 0.7,
      start_t: 0,
      duration: 300,
      parameters: { radiator_efficiency_drop: 0.45 }
    }];
  }
  if (scenario === 'comms') {
    return [{
      id: 'comms-link-degrade',
      category: 'comms',
      severity: 0.75,
      start_t: 0,
      duration: 300,
      parameters: { antenna_alignment_error_deg: 18, transceiver_degradation: true }
    }];
  }
  return [{
    id: 'power-aging-load-spike',
    category: 'power',
    severity: 0.65,
    start_t: 0,
    duration: 300,
    parameters: { battery_age_factor: 0.72, load_spike: 5.2 }
  }];
}

function actionsForScenario(scenario: TwinScenario): TwinPlanStep[] {
  if (scenario === 'nominal') return [];
  if (scenario === 'thermal') {
    return [
      { action: 'ENTER_SAFE_MODE', params: {}, at_t: 10 },
      { action: 'DISABLE_PAYLOAD', params: {}, at_t: 12 },
      { action: 'RESET_THERMAL_CONTROLLER', params: {}, at_t: 20 }
    ];
  }
  if (scenario === 'comms') {
    return [
      { action: 'RESTART_COMMS', params: {}, at_t: 8 },
      { action: 'SWITCH_TO_BACKUP_SENSOR', params: {}, at_t: 18 }
    ];
  }
  return [
    { action: 'ENTER_SAFE_MODE', params: {}, at_t: 6 },
    { action: 'DISABLE_PAYLOAD', params: {}, at_t: 8 },
    { action: 'LOWER_SAMPLING_RATE', params: {}, at_t: 14 }
  ];
}

function conservativeActionsForScenario(scenario: TwinScenario): TwinPlanStep[] {
  if (scenario === 'nominal') return [];
  return [
    { action: 'ENTER_SAFE_MODE', params: {}, at_t: 0 },
    { action: 'DISABLE_PAYLOAD', params: {}, at_t: 2 },
    { action: 'LOWER_SAMPLING_RATE', params: {}, at_t: 4 }
  ];
}

function aggressiveActionsForScenario(scenario: TwinScenario): TwinPlanStep[] {
  if (scenario === 'nominal') return [];
  if (scenario === 'thermal') {
    return [
      { action: 'RESET_THERMAL_CONTROLLER', params: {}, at_t: 0 },
      { action: 'DISABLE_PAYLOAD', params: {}, at_t: 12 }
    ];
  }
  if (scenario === 'comms') {
    return [
      { action: 'RESTART_COMMS', params: {}, at_t: 0 }
    ];
  }
  return [
    { action: 'DISABLE_PAYLOAD', params: {}, at_t: 0 },
    { action: 'LOWER_SAMPLING_RATE', params: {}, at_t: 3 }
  ];
}
