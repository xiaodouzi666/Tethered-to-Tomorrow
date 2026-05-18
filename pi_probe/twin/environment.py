from __future__ import annotations

from pi_probe.probe.state import SpacecraftState
from pi_probe.twin.schemas import EnvironmentConfig


def apply_environment(state: SpacecraftState, env: EnvironmentConfig) -> None:
    state.sun_exposure = env.sun_exposure
    state.eclipse_factor = env.eclipse_factor
    state.radiation_level = env.radiation_level
    state.antenna_alignment_error_deg = env.antenna_alignment_error_deg
    state.battery_age_factor = env.battery_age_factor
    state.thermal_sink_efficiency = env.thermal_sink_efficiency
    state.mission_phase = env.mission_phase
