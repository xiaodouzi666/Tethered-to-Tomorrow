from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from pi_probe.twin.persistence import SQLiteJSONStore
from pi_probe.twin.schemas import (
    ComponentFaultInjectionRequest,
    ComponentFaultTemplate,
    ComponentLinkRequest,
    ComponentOperationRequest,
    ComponentParametersRequest,
    ComponentReplaceRequest,
    ComponentTransformRequest,
    FaultLayer,
    FaultSpec,
    GroundTestbedSession,
    TwinAssemblyValidation,
    TwinAssemblyValidationIssue,
    TwinAssemblyState,
    TwinComponentInstance,
    TwinComponentLink,
    TwinComponentPort,
    TroubleshootingRequest,
    TroubleshootingResponse,
)


# Component graph used by the web modular twin editor. It remains rule-based, but
# the graph is now authoritative for campaign gates and simulation context.
_COMPONENT_POSITIONS: Dict[str, Dict[str, float]] = {
    "rtg-1": {"x": -2.2, "y": -0.9, "z": 0.35},
    "power-bus-1": {"x": -0.8, "y": -0.7, "z": 0.15},
    "thermal-controller-1": {"x": 0.15, "y": -0.35, "z": 0.2},
    "radiator-1": {"x": 0.05, "y": 0.75, "z": -0.15},
    "hga-1": {"x": 0.0, "y": 1.65, "z": -0.1},
    "transceiver-1": {"x": 0.65, "y": 0.0, "z": 0.0},
    "flight-computer-1": {"x": 0.05, "y": -0.05, "z": 0.55},
    "memory-bank-a": {"x": 0.35, "y": -0.25, "z": 0.7},
    "payload-bay-1": {"x": 0.75, "y": 0.4, "z": 0.85},
    "primary-sensor-1": {"x": 1.15, "y": 0.35, "z": 1.08},
    "backup-sensor-1": {"x": 1.05, "y": -0.05, "z": 1.02},
}


CATALOG: Dict[str, Dict[str, Any]] = {
    "power.rtg": {
        "display_name": "RTG Power Source",
        "subsystem": "power",
        "slot": "power_source",
        "criticality": "critical",
        "ports": [
            {"port_id": "pwr_out", "kind": "power", "direction": "out"},
            {"port_id": "thermal_waste", "kind": "thermal", "direction": "out"},
        ],
        "parameters": {"output_w": 2.6, "health_factor": 1.0},
        "fault_templates": [
            {
                "template_id": "rtg_output_decay",
                "label": "RTG output decay",
                "category": "battery_aging_penalty",
                "layer": "root_cause",
                "description": "Long-term power source degradation lowers available voltage margin.",
                "symptom": "battery_voltage trends down under the same payload load",
                "default_severity": 0.55,
                "parameters": {"battery_age_factor": 0.72},
                "affected_metrics": ["power.battery_voltage", "power.load_w"],
                "recommended_checks": ["Compare load_w against baseline", "Check whether payload can be shed"],
                "candidate_actions": ["DISABLE_PAYLOAD", "ENTER_SAFE_MODE"],
            },
            {
                "template_id": "load_spike",
                "label": "Transient load spike",
                "category": "load_spike",
                "layer": "recoverable",
                "description": "A bus transient increases load and heats the bus.",
                "symptom": "load_w and temp_c rise together",
                "default_severity": 0.45,
                "parameters": {"load_spike": 2.8},
                "affected_metrics": ["power.load_w", "thermal.temp_c"],
                "recommended_checks": ["Inspect recent payload enable/disable events"],
                "candidate_actions": ["DISABLE_PAYLOAD", "ENTER_SAFE_MODE"],
            },
        ],
    },
    "power.bus": {
        "display_name": "Power Distribution Bus",
        "subsystem": "power",
        "slot": "bus",
        "criticality": "critical",
        "ports": [
            {"port_id": "pwr_in", "kind": "power", "direction": "in"},
            {"port_id": "pwr_out", "kind": "power", "direction": "out"},
            {"port_id": "tm", "kind": "data", "direction": "out"},
        ],
        "parameters": {"redundant_channels": 2},
        "fault_templates": [
            {
                "template_id": "bus_load_spike",
                "label": "Bus over-current transient",
                "category": "load_spike",
                "layer": "recoverable",
                "description": "Transient current draw can depress voltage and raise thermal load.",
                "symptom": "voltage droop + load spike",
                "default_severity": 0.62,
                "parameters": {"load_spike": 3.2},
                "affected_metrics": ["power.battery_voltage", "power.load_w"],
                "recommended_checks": ["Check high-load components", "Try payload isolation in twin first"],
                "candidate_actions": ["DISABLE_PAYLOAD", "ENTER_SAFE_MODE"],
            }
        ],
    },
    "thermal.controller": {
        "display_name": "Thermal Controller",
        "subsystem": "thermal",
        "slot": "thermal_loop",
        "criticality": "critical",
        "ports": [
            {"port_id": "cmd", "kind": "data", "direction": "in"},
            {"port_id": "radiator_ctrl", "kind": "thermal", "direction": "out"},
        ],
        "parameters": {"pid_gain": 1.0, "watchdog": True},
        "fault_templates": [
            {
                "template_id": "controller_stuck",
                "label": "Control loop stuck",
                "category": "thermal_controller_stuck",
                "layer": "recoverable",
                "description": "Controller stops regulating heat rejection.",
                "symptom": "temp_c climbs while radiator_efficiency remains nominal",
                "default_severity": 0.64,
                "parameters": {},
                "affected_metrics": ["thermal.temp_c", "thermal.controller_ok"],
                "recommended_checks": ["Run controller reset in twin", "Check post-reset temp trend"],
                "candidate_actions": ["RESET_THERMAL_CONTROLLER", "DISABLE_PAYLOAD"],
            },
            {
                "template_id": "heater_stuck_on",
                "label": "Heater stuck on",
                "category": "heater_stuck_on",
                "layer": "recoverable",
                "description": "A heater control path remains active and adds load.",
                "symptom": "temp_c rises with extra load_w",
                "default_severity": 0.5,
                "parameters": {"heater_stuck_on": True},
                "affected_metrics": ["thermal.temp_c", "power.load_w"],
                "recommended_checks": ["Reset controller", "Disable payload if thermal margin is low"],
                "candidate_actions": ["RESET_THERMAL_CONTROLLER", "ENTER_SAFE_MODE"],
            },
        ],
    },
    "thermal.radiator": {
        "display_name": "Radiator Panel",
        "subsystem": "thermal",
        "slot": "radiator",
        "criticality": "critical",
        "ports": [
            {"port_id": "heat_in", "kind": "thermal", "direction": "in"},
            {"port_id": "heat_out", "kind": "thermal", "direction": "out"},
        ],
        "parameters": {"area_m2": 1.0, "efficiency": 1.0},
        "fault_templates": [
            {
                "template_id": "radiator_coating_degradation",
                "label": "Radiator efficiency drop",
                "category": "radiator_efficiency_drop",
                "layer": "root_cause",
                "description": "Physical heat rejection performance degrades and cannot be fully reset by software.",
                "symptom": "radiator_efficiency falls and temp_c increases slowly",
                "default_severity": 0.62,
                "parameters": {"radiator_efficiency_drop": 0.42},
                "affected_metrics": ["thermal.temp_c", "thermal.radiator_efficiency"],
                "recommended_checks": ["Separate physical root cause from controller state", "Prefer load shedding"],
                "candidate_actions": ["DISABLE_PAYLOAD", "ENTER_SAFE_MODE"],
            }
        ],
    },
    "comms.hga": {
        "display_name": "High Gain Antenna",
        "subsystem": "comms",
        "slot": "antenna",
        "criticality": "critical",
        "ports": [
            {"port_id": "rf", "kind": "rf", "direction": "inout"},
            {"port_id": "tm", "kind": "data", "direction": "in"},
        ],
        "parameters": {"pointing_error_deg": 0.0},
        "fault_templates": [
            {
                "template_id": "pointing_error",
                "label": "Antenna pointing error",
                "category": "antenna_misalignment",
                "layer": "root_cause",
                "description": "Antenna alignment error reduces signal margin and increases packet loss.",
                "symptom": "signal_strength drops while packet_loss rises",
                "default_severity": 0.58,
                "parameters": {"error_deg": 18.0},
                "affected_metrics": ["comms.signal_strength", "comms.packet_loss"],
                "recommended_checks": ["Compare HGA fault with radiation branch", "Lower sampling before restart if link is weak"],
                "candidate_actions": ["LOWER_SAMPLING_RATE", "RESTART_COMMS"],
            }
        ],
    },
    "comms.transceiver": {
        "display_name": "X-band Transceiver",
        "subsystem": "comms",
        "slot": "transceiver",
        "criticality": "critical",
        "ports": [
            {"port_id": "pwr", "kind": "power", "direction": "in"},
            {"port_id": "rf", "kind": "rf", "direction": "inout"},
            {"port_id": "data", "kind": "data", "direction": "inout"},
        ],
        "parameters": {"firmware_channel": "A", "retry_window_s": 4.0},
        "fault_templates": [
            {
                "template_id": "softlock",
                "label": "Transceiver softlock",
                "category": "transceiver_softlock",
                "layer": "recoverable",
                "description": "The transceiver stack locks up; a restart can clear it but causes blackout.",
                "symptom": "packet_loss climbs despite acceptable antenna geometry",
                "default_severity": 0.56,
                "parameters": {"packet_loss_floor": 0.48},
                "affected_metrics": ["comms.packet_loss", "comms.signal_strength"],
                "recommended_checks": ["Dry-run restart blackout", "Verify battery before high-risk restart"],
                "candidate_actions": ["LOWER_SAMPLING_RATE", "RESTART_COMMS"],
            },
            {
                "template_id": "burst_packet_loss",
                "label": "Burst packet loss",
                "category": "burst_packet_loss",
                "layer": "recoverable",
                "description": "Intermittent RF/stack bursts create loss spikes.",
                "symptom": "packet_loss bursts above the link budget threshold",
                "default_severity": 0.42,
                "parameters": {"packet_loss_floor": 0.38},
                "affected_metrics": ["comms.packet_loss"],
                "recommended_checks": ["Run stochastic campaign with multiple seeds"],
                "candidate_actions": ["LOWER_SAMPLING_RATE", "RESTART_COMMS"],
            },
        ],
    },
    "computer.flight": {
        "display_name": "Flight Computer",
        "subsystem": "computer",
        "slot": "compute",
        "criticality": "critical",
        "ports": [
            {"port_id": "cmd", "kind": "data", "direction": "in"},
            {"port_id": "tm", "kind": "data", "direction": "out"},
        ],
        "parameters": {"cpu_margin": 0.72},
        "fault_templates": [
            {
                "template_id": "scheduler_overload",
                "label": "Scheduler overload",
                "category": "scheduler_overload",
                "layer": "recoverable",
                "description": "CPU is pinned by a runaway task and increases power draw.",
                "symptom": "cpu_load high and load_w increases",
                "default_severity": 0.54,
                "parameters": {"cpu_load_floor": 0.82},
                "affected_metrics": ["computer.cpu_load", "power.load_w"],
                "recommended_checks": ["Try cache clear before reboot", "Only reboot with HITL approval"],
                "candidate_actions": ["CLEAR_CACHE", "REBOOT_COMPUTER"],
            }
        ],
    },
    "computer.memory": {
        "display_name": "Memory Bank",
        "subsystem": "computer",
        "slot": "memory",
        "criticality": "important",
        "ports": [
            {"port_id": "data", "kind": "data", "direction": "inout"},
        ],
        "parameters": {"capacity_mb": 2048},
        "fault_templates": [
            {
                "template_id": "memory_leak",
                "label": "Memory leak / cache pressure",
                "category": "memory_leak",
                "layer": "recoverable",
                "description": "Memory pressure increases until compute stability degrades.",
                "symptom": "mem_used_mb rises over time",
                "default_severity": 0.48,
                "parameters": {"memory_growth_mb": 12.0},
                "affected_metrics": ["computer.mem_used_mb", "computer.cpu_load"],
                "recommended_checks": ["Try CLEAR_CACHE first", "Escalate to REBOOT_COMPUTER only if campaign passes"],
                "candidate_actions": ["CLEAR_CACHE", "REBOOT_COMPUTER"],
            }
        ],
    },
    "payload.instrument": {
        "display_name": "Science Payload",
        "subsystem": "payload",
        "slot": "payload_bay",
        "criticality": "mission",
        "ports": [
            {"port_id": "pwr", "kind": "power", "direction": "in"},
            {"port_id": "data", "kind": "data", "direction": "out"},
        ],
        "parameters": {"sampling_rate": 1.0},
        "fault_templates": [
            {
                "template_id": "payload_overdraw",
                "label": "Payload overdraw",
                "category": "load_spike",
                "layer": "recoverable",
                "description": "Payload draws too much power and steals thermal margin.",
                "symptom": "load_w and temp_c rise after payload enable",
                "default_severity": 0.5,
                "parameters": {"load_spike": 2.4},
                "affected_metrics": ["power.load_w", "thermal.temp_c", "payload.sampling_rate"],
                "recommended_checks": ["Compare disabling payload vs lowering sampling"],
                "candidate_actions": ["LOWER_SAMPLING_RATE", "DISABLE_PAYLOAD"],
            }
        ],
    },
    "payload.sensor": {
        "display_name": "Thermal/Spectral Sensor",
        "subsystem": "sensor",
        "slot": "sensor_mount",
        "criticality": "important",
        "ports": [
            {"port_id": "data", "kind": "data", "direction": "out"},
        ],
        "parameters": {"primary": True, "bias": 0.0},
        "fault_templates": [
            {
                "template_id": "sensor_drift",
                "label": "Sensor drift",
                "category": "sensor_drift",
                "layer": "recoverable",
                "description": "A biased sensor causes misleading thermal or payload telemetry.",
                "symptom": "reported temp_c oscillates or drifts without matching power load",
                "default_severity": 0.52,
                "parameters": {"drift": 0.22},
                "affected_metrics": ["thermal.temp_c", "payload.using_backup_sensor"],
                "recommended_checks": ["Switch to backup sensor in twin", "Compare drift residuals"],
                "candidate_actions": ["SWITCH_TO_BACKUP_SENSOR", "CLEAR_CACHE"],
            },
            {
                "template_id": "primary_sensor_failure",
                "label": "Primary sensor failure",
                "category": "sensor",
                "layer": "root_cause",
                "description": "Primary sensor health collapses and must be bypassed with backup sensor.",
                "symptom": "sensor fault layer active; backup path available",
                "default_severity": 0.65,
                "parameters": {"primary_sensor_health": 0.0},
                "affected_metrics": ["payload.using_backup_sensor", "computer.storage_health"],
                "recommended_checks": ["Use backup sensor and verify telemetry consistency"],
                "candidate_actions": ["SWITCH_TO_BACKUP_SENSOR"],
            },
        ],
    },
}


DEFAULT_COMPONENTS = [
    ("rtg-1", "power.rtg"),
    ("power-bus-1", "power.bus"),
    ("thermal-controller-1", "thermal.controller"),
    ("radiator-1", "thermal.radiator"),
    ("hga-1", "comms.hga"),
    ("transceiver-1", "comms.transceiver"),
    ("flight-computer-1", "computer.flight"),
    ("memory-bank-a", "computer.memory"),
    ("payload-bay-1", "payload.instrument"),
    ("primary-sensor-1", "payload.sensor"),
    ("backup-sensor-1", "payload.sensor"),
]


DEFAULT_LINKS = [
    ("rtg-1", "pwr_out", "power-bus-1", "pwr_in", "power"),
    ("power-bus-1", "tm", "thermal-controller-1", "cmd", "data"),
    ("thermal-controller-1", "radiator_ctrl", "radiator-1", "heat_in", "thermal"),
    ("power-bus-1", "pwr_out", "transceiver-1", "pwr", "power"),
    ("power-bus-1", "pwr_out", "payload-bay-1", "pwr", "power"),
    ("transceiver-1", "rf", "hga-1", "rf", "rf"),
    ("flight-computer-1", "tm", "transceiver-1", "data", "data"),
    ("flight-computer-1", "tm", "hga-1", "tm", "data"),
    ("memory-bank-a", "data", "flight-computer-1", "cmd", "data"),
    ("payload-bay-1", "data", "flight-computer-1", "cmd", "data"),
    ("primary-sensor-1", "data", "flight-computer-1", "cmd", "data"),
    ("backup-sensor-1", "data", "flight-computer-1", "cmd", "data"),
]


class TwinAssemblyStore:
    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._store = SQLiteJSONStore("assembly", TwinAssemblyState, ttl_sec=ttl_sec)
        self._undo: Dict[str, List[TwinAssemblyState]] = {}
        self._redo: Dict[str, List[TwinAssemblyState]] = {}

    def create_default(self, session_id: str) -> TwinAssemblyState:
        now = time.time()
        components = [_component_instance(instance_id, catalog_id) for instance_id, catalog_id in DEFAULT_COMPONENTS]
        links = [
            TwinComponentLink(
                link_id=f"link-{idx + 1}",
                from_component=source,
                from_port=source_port,
                to_component=target,
                to_port=target_port,
                medium=medium,
            )
            for idx, (source, source_port, target, target_port, medium) in enumerate(DEFAULT_LINKS)
        ]
        state = TwinAssemblyState(
            assembly_id=f"assembly-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            updated_at=now,
            version=1,
            components=components,
            links=links,
            selected_component_id=components[0].instance_id if components else None,
            operation_log=[{"ts": now, "type": "assembly_created", "message": "Default spacecraft assembly created."}],
        )
        state = _finalize_state(state, undo_available=False, redo_available=False)
        self._store.put(session_id, state, event_type="assembly_created", audit_payload={"assembly_id": state.assembly_id})
        return copy.deepcopy(state)

    def get(self, session_id: str) -> Optional[TwinAssemblyState]:
        state = self._store.get(session_id)
        return copy.deepcopy(state) if state else None

    def save(self, state: TwinAssemblyState, *, event_type: str = "assembly_saved") -> TwinAssemblyState:
        state.updated_at = time.time()
        state = _finalize_state(
            state,
            undo_available=bool(self._undo.get(state.session_id)),
            redo_available=bool(self._redo.get(state.session_id)),
        )
        self._store.put(state.session_id, copy.deepcopy(state), event_type=event_type, audit_payload=_audit_payload(state))
        return copy.deepcopy(state)

    def ensure(self, session_id: str) -> TwinAssemblyState:
        existing = self.get(session_id)
        if existing is not None:
            return existing
        return self.create_default(session_id)

    def add_component(self, session_id: str, req: ComponentOperationRequest) -> TwinAssemblyState:
        state = self.ensure(session_id)
        self._push_undo(state)
        catalog_id = req.catalog_id
        if catalog_id not in CATALOG:
            raise ValueError(f"Unknown component catalog id: {catalog_id}")
        instance_id = req.instance_id or _new_instance_id(catalog_id)
        if _find_component(state.components, instance_id):
            raise ValueError(f"Component instance already exists: {instance_id}")
        component = _component_instance(instance_id, catalog_id, display_name=req.display_name, slot=req.slot, parameters=req.parameters)
        if req.position:
            component.position = _vector(req.position, default=component.position)
        if req.rotation:
            component.rotation = _vector(req.rotation)
        if req.scale:
            component.scale = _vector(req.scale, default={"x": 1.0, "y": 1.0, "z": 1.0})
        state.components.append(component)
        state.selected_component_id = component.instance_id
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_added", "message": f"Added {component.display_name}.", "component_id": instance_id})
        return self._commit(state, "component_added")

    def remove_component(self, session_id: str, component_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        component = _find_component(state.components, component_id)
        if component is None:
            raise ValueError(f"Unknown component id: {component_id}")
        if component.locked:
            raise ValueError(f"Component is locked and cannot be removed: {component_id}")
        self._push_undo(state)
        component.install_state = "removed"
        component.health_state = "offline"
        state.links = [
            link for link in state.links
            if link.from_component != component_id and link.to_component != component_id
        ]
        state.selected_component_id = _next_installed_component_id(state.components, exclude=component_id)
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_removed", "message": f"Removed {component.display_name} from the ground twin.", "component_id": component_id})
        return self._commit(state, "component_removed")

    def select_component(self, session_id: str, component_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        component = _find_component(state.components, component_id)
        if component is None:
            raise ValueError(f"Unknown component id: {component_id}")
        if component.install_state == "removed":
            raise ValueError(f"Removed component cannot be selected: {component_id}")
        state.selected_component_id = component_id
        return self.save(state)

    def add_link(self, session_id: str, req: ComponentLinkRequest) -> TwinAssemblyState:
        state = self.ensure(session_id)
        self._push_undo(state)
        _validate_link_request(state, req)
        duplicate = next((
            link for link in state.links
            if link.from_component == req.from_component
            and link.from_port == req.from_port
            and link.to_component == req.to_component
            and link.to_port == req.to_port
            and link.enabled
        ), None)
        if duplicate:
            raise ValueError(f"Link already exists: {duplicate.link_id}")
        if _find_component(state.components, req.from_component) is None:
            raise ValueError(f"Unknown from_component: {req.from_component}")
        if _find_component(state.components, req.to_component) is None:
            raise ValueError(f"Unknown to_component: {req.to_component}")
        link = TwinComponentLink(
            link_id=req.link_id or f"link-{uuid.uuid4().hex[:8]}",
            from_component=req.from_component,
            from_port=req.from_port,
            to_component=req.to_component,
            to_port=req.to_port,
            medium=req.medium,
            enabled=req.enabled,
        )
        state.links.append(link)
        state.operation_log.insert(0, {"ts": time.time(), "type": "link_added", "message": f"Linked {link.from_component}.{link.from_port} -> {link.to_component}.{link.to_port}.", "link_id": link.link_id})
        return self._commit(state, "link_added")

    def remove_link(self, session_id: str, link_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        link = next((item for item in state.links if item.link_id == link_id), None)
        if link is None:
            raise ValueError(f"Unknown link id: {link_id}")
        self._push_undo(state)
        state.links = [item for item in state.links if item.link_id != link_id]
        state.operation_log.insert(0, {"ts": time.time(), "type": "link_removed", "message": f"Removed link {link_id}.", "link_id": link_id})
        return self._commit(state, "link_removed")

    def transform_component(self, session_id: str, component_id: str, req: ComponentTransformRequest) -> TwinAssemblyState:
        state = self.ensure(session_id)
        component = _require_installed_component(state, component_id)
        if component.locked:
            raise ValueError(f"Component is locked and cannot be transformed: {component_id}")
        self._push_undo(state)
        if req.position is not None:
            component.position = _vector(req.position, default=component.position)
        if req.rotation is not None:
            component.rotation = _vector(req.rotation, default=component.rotation)
        if req.scale is not None:
            component.scale = _vector(req.scale, default=component.scale or {"x": 1.0, "y": 1.0, "z": 1.0}, minimum=0.1)
        state.selected_component_id = component_id
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_transformed", "message": f"Transformed {component.display_name}.", "component_id": component_id})
        return self._commit(state, "component_transformed")

    def update_parameters(self, session_id: str, component_id: str, req: ComponentParametersRequest) -> TwinAssemblyState:
        state = self.ensure(session_id)
        component = _require_installed_component(state, component_id)
        self._push_undo(state)
        component.parameters = {**component.parameters, **req.parameters}
        state.selected_component_id = component_id
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_parameters_updated", "message": f"Updated {component.display_name} parameters.", "component_id": component_id})
        return self._commit(state, "component_parameters_updated")

    def replace_component(self, session_id: str, component_id: str, req: ComponentReplaceRequest) -> TwinAssemblyState:
        state = self.ensure(session_id)
        old = _require_installed_component(state, component_id)
        if old.locked:
            raise ValueError(f"Component is locked and cannot be replaced: {component_id}")
        if req.catalog_id not in CATALOG:
            raise ValueError(f"Unknown component catalog id: {req.catalog_id}")
        self._push_undo(state)
        replacement = _component_instance(
            component_id,
            req.catalog_id,
            display_name=req.display_name,
            slot=req.slot or old.slot,
            parameters=req.parameters,
        )
        replacement.position = copy.deepcopy(old.position)
        replacement.rotation = copy.deepcopy(old.rotation)
        replacement.scale = copy.deepcopy(old.scale)
        state.components = [replacement if item.instance_id == component_id else item for item in state.components]
        state.selected_component_id = component_id
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_replaced", "message": f"Replaced {old.display_name} with {replacement.display_name}.", "component_id": component_id})
        return self._commit(state, "component_replaced")

    def validate(self, session_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        return self.save(state, event_type="assembly_validated")

    def undo(self, session_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        history = self._undo.get(session_id, [])
        if not history:
            return state
        self._redo.setdefault(session_id, []).append(state)
        restored = history.pop()
        restored.operation_log.insert(0, {"ts": time.time(), "type": "undo", "message": "Reverted previous assembly operation."})
        return self.save(restored, event_type="assembly_undo")

    def redo(self, session_id: str) -> TwinAssemblyState:
        state = self.ensure(session_id)
        history = self._redo.get(session_id, [])
        if not history:
            return state
        self._undo.setdefault(session_id, []).append(state)
        restored = history.pop()
        restored.operation_log.insert(0, {"ts": time.time(), "type": "redo", "message": "Reapplied assembly operation."})
        return self.save(restored, event_type="assembly_redo")

    def inject_fault(self, session_id: str, req: ComponentFaultInjectionRequest) -> tuple[TwinAssemblyState, FaultSpec]:
        state = self.ensure(session_id)
        component = _require_installed_component(state, req.component_id)
        template = _find_template(component.fault_templates, req.template_id)
        if template is None:
            raise ValueError(f"Unknown fault template {req.template_id} for component {req.component_id}")
        self._push_undo(state)
        severity = req.severity if req.severity is not None else template.default_severity
        severity = max(0.0, min(1.0, float(severity)))
        component.health_state = "fault"
        merged_parameters = {**template.parameters, **req.parameters}
        component.active_faults.append({
            "fault_id": f"{component.instance_id}:{template.template_id}",
            "template_id": template.template_id,
            "label": template.label,
            "category": template.category,
            "severity": severity,
            "parameters": copy.deepcopy(merged_parameters),
            "ts": time.time(),
        })
        fault = FaultSpec(
            id=f"component-{component.instance_id}-{template.template_id}",
            category=template.category,
            severity=severity,
            start_t=req.start_t,
            duration=req.duration,
            parameters={
                **merged_parameters,
                "component_id": component.instance_id,
                "component_catalog_id": component.catalog_id,
                "component_display_name": component.display_name,
                "fault_template_id": template.template_id,
            },
            layer=_layer_from_template(template),
            clearable_by=list(template.candidate_actions),
            suppressible_by=list(template.candidate_actions),
            source="assembly_component_fault",
        )
        state.selected_component_id = component.instance_id
        state.operation_log.insert(0, {"ts": time.time(), "type": "component_fault_injected", "message": f"Injected {template.label} into {component.display_name}.", "component_id": component.instance_id, "template_id": template.template_id})
        return self._commit(state, "component_fault_injected"), fault

    def prune(self) -> None:
        self._store.prune()

    def _push_undo(self, state: TwinAssemblyState) -> None:
        self._undo.setdefault(state.session_id, []).append(copy.deepcopy(state))
        self._undo[state.session_id] = self._undo[state.session_id][-30:]
        self._redo[state.session_id] = []

    def _commit(self, state: TwinAssemblyState, event_type: str) -> TwinAssemblyState:
        state.version += 1
        return self.save(state, event_type=event_type)


def catalog_response() -> Dict[str, Any]:
    return {
        "components": [
            _component_instance(f"catalog-{catalog_id.replace('.', '-')}", catalog_id)
            for catalog_id in CATALOG.keys()
        ],
        "catalog": copy.deepcopy(CATALOG),
        "fault_templates": _all_templates(),
    }


def build_rule_troubleshooting(
    *,
    assembly: TwinAssemblyState,
    session: GroundTestbedSession,
    req: TroubleshootingRequest,
) -> TroubleshootingResponse:
    selected_id = req.component_id or assembly.selected_component_id
    selected = _find_component(assembly.components, selected_id) if selected_id else None
    active_faults = session.twin_faults
    suspects: List[Dict[str, Any]] = []

    fault_component_ids = {
        str(fault.parameters.get("component_id"))
        for fault in active_faults
        if isinstance(fault.parameters, dict) and fault.parameters.get("component_id")
    }

    for component in assembly.components:
        confidence = 0.1
        evidence: List[str] = []
        if component.instance_id in fault_component_ids:
            confidence += 0.65
            evidence.append("Component has an injected ground-twin fault.")
        if component.health_state == "fault":
            confidence += 0.2
            evidence.append("Assembly graph marks this component as faulted.")
        if selected and component.instance_id == selected.instance_id:
            confidence += 0.05
            evidence.append("Operator selected this component for inspection.")
        if confidence > 0.1:
            suspects.append({
                "component_id": component.instance_id,
                "display_name": component.display_name,
                "subsystem": component.subsystem,
                "confidence": round(min(confidence, 0.98), 2),
                "evidence": evidence or ["Subsystem-level symptoms match this component."],
            })

    if not suspects and selected:
        suspects.append({
            "component_id": selected.instance_id,
            "display_name": selected.display_name,
            "subsystem": selected.subsystem,
            "confidence": 0.35,
            "evidence": ["No explicit component fault yet; selected component is a plausible inspection target."],
        })

    suspects = sorted(suspects, key=lambda item: float(item.get("confidence", 0.0)), reverse=True)[:5]
    candidate_actions = _candidate_actions_for_components(assembly.components, suspects)
    procedure = [
        "Freeze current real-probe baseline and keep the component graph unchanged during the campaign.",
        "Inject or confirm one component-level fault at a time so the root cause stays explainable.",
        "Run campaign across nominal, radiation, and alignment-stress environment branches.",
        "Prefer the lowest-risk plan that clears/suppresses the component fault without violating thermal, power, or comms limits.",
    ]
    if candidate_actions:
        procedure.append("Candidate command sequence: " + " → ".join(candidate_actions[:4]) + ".")

    gemma_prompt = {
        "situation": req.situation,
        "selected_component_id": selected_id,
        "active_component_faults": [fault.model_dump() if hasattr(fault, "model_dump") else fault.dict() for fault in active_faults],
        "campaign_best_plan_id": session.last_campaign.best_plan_id if session.last_campaign else None,
    }
    return TroubleshootingResponse(
        ok=True,
        source="rules",
        session_id=session.session_id,
        component_id=selected_id,
        summary=(
            f"Component-level troubleshooting prepared for {selected.display_name if selected else 'assembly graph'}. "
            f"{len(suspects)} suspect component(s), {len(candidate_actions)} candidate action(s)."
        ),
        suspects=suspects,
        candidate_actions=candidate_actions,
        procedure=procedure,
        gemma_prompt=gemma_prompt,
    )


def _component_instance(
    instance_id: str,
    catalog_id: str,
    *,
    display_name: Optional[str] = None,
    slot: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> TwinComponentInstance:
    source = CATALOG[catalog_id]
    merged_parameters = {**copy.deepcopy(source.get("parameters", {})), **(parameters or {})}
    if catalog_id == "payload.sensor" and instance_id.startswith("backup-") and not parameters:
        merged_parameters["primary"] = False
    fault_templates = [ComponentFaultTemplate(**template) for template in source.get("fault_templates", [])]
    ports = [_port_from_catalog(port, str(source["subsystem"])) for port in source.get("ports", [])]
    return TwinComponentInstance(
        instance_id=instance_id,
        catalog_id=catalog_id,
        display_name=display_name or str(source["display_name"]),
        subsystem=str(source["subsystem"]),
        slot=slot or str(source["slot"]),
        criticality=str(source.get("criticality", "important")),
        install_state="installed",
        health_state="nominal",
        ports=ports,
        parameters=merged_parameters,
        position=copy.deepcopy(_COMPONENT_POSITIONS.get(instance_id, {"x": 0.0, "y": 0.0, "z": 0.0})),
        rotation={"x": 0.0, "y": 0.0, "z": 0.0},
        scale={"x": 1.0, "y": 1.0, "z": 1.0},
        slot_constraints=copy.deepcopy(source.get("slot_constraints", {})),
        fault_templates=fault_templates,
    )


def _find_component(components: Iterable[TwinComponentInstance], component_id: Optional[str]) -> Optional[TwinComponentInstance]:
    if not component_id:
        return None
    for component in components:
        if component.instance_id == component_id:
            return component
    return None


def _find_template(templates: Iterable[ComponentFaultTemplate], template_id: str) -> Optional[ComponentFaultTemplate]:
    for template in templates:
        if template.template_id == template_id:
            return template
    return None


def _new_instance_id(catalog_id: str) -> str:
    prefix = catalog_id.split(".")[-1].replace("_", "-")
    return f"{prefix}-{uuid.uuid4().hex[:5]}"


def _layer_from_template(template: ComponentFaultTemplate) -> Optional[FaultLayer]:
    layer = template.layer.lower().strip()
    if layer == "root_cause":
        return FaultLayer.ROOT_CAUSE
    if layer == "recoverable":
        return FaultLayer.RECOVERABLE
    if layer == "symptom":
        return FaultLayer.SYMPTOM
    return None


def _all_templates() -> List[Dict[str, Any]]:
    templates: List[Dict[str, Any]] = []
    for catalog_id, component in CATALOG.items():
        for template in component.get("fault_templates", []):
            templates.append({"catalog_id": catalog_id, **copy.deepcopy(template)})
    return templates


def _candidate_actions_for_components(components: Iterable[TwinComponentInstance], suspects: List[Dict[str, Any]]) -> List[str]:
    by_id = {component.instance_id: component for component in components}
    actions: List[str] = []
    for suspect in suspects:
        component = by_id.get(str(suspect.get("component_id")))
        if not component:
            continue
        for template in component.fault_templates:
            for action in template.candidate_actions:
                normalized = action.upper().strip()
                if normalized and normalized not in actions:
                    actions.append(normalized)
    return actions


def _port_from_catalog(port: Dict[str, Any], subsystem: str) -> TwinComponentPort:
    kind = str(port.get("kind", "data"))
    required = bool(port.get("required", _default_required_port(subsystem, kind, str(port.get("direction", "inout")))))
    compatible = list(port.get("compatible_kinds", [kind]))
    return TwinComponentPort(**{**port, "required": required, "compatible_kinds": compatible})


def _default_required_port(subsystem: str, kind: str, direction: str) -> bool:
    if subsystem in {"power", "thermal", "comms", "computer", "payload", "sensor"}:
        return direction in {"in", "inout"} and kind in {"power", "thermal", "rf", "data"}
    return False


def _finalize_state(state: TwinAssemblyState, *, undo_available: bool, redo_available: bool) -> TwinAssemblyState:
    state.selected_component_id = _valid_selected_component_id(state)
    state.validation = validate_assembly_state(state)
    state.assembly_digest = assembly_digest(state)
    state.updated_at = time.time()
    state.undo_available = undo_available
    state.redo_available = redo_available
    return state


def _audit_payload(state: TwinAssemblyState) -> Dict[str, Any]:
    return {
        "assembly_id": state.assembly_id,
        "version": state.version,
        "digest": state.assembly_digest,
        "valid": state.validation.ok,
    }


def assembly_digest(state: TwinAssemblyState) -> str:
    payload = {
        "components": [
            _component_digest_payload(component)
            for component in sorted(state.components, key=lambda item: item.instance_id)
        ],
        "links": [
            link.model_dump(mode="json") if hasattr(link, "model_dump") else link.dict()
            for link in sorted(state.links, key=lambda item: item.link_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _component_digest_payload(component: TwinComponentInstance) -> Dict[str, Any]:
    data = component.model_dump(mode="json") if hasattr(component, "model_dump") else component.dict()
    data.pop("notes", None)
    return data


def validate_assembly_state(state: TwinAssemblyState) -> TwinAssemblyValidation:
    issues: List[TwinAssemblyValidationIssue] = []
    installed = [component for component in state.components if component.install_state != "removed"]
    by_id = {component.instance_id: component for component in state.components}
    installed_by_id = {component.instance_id: component for component in installed}

    required_catalogs = {
        "power.rtg",
        "power.bus",
        "thermal.controller",
        "thermal.radiator",
        "comms.hga",
        "comms.transceiver",
        "computer.flight",
        "payload.instrument",
    }
    installed_catalogs = {component.catalog_id for component in installed}
    for catalog_id in sorted(required_catalogs - installed_catalogs):
        issues.append(TwinAssemblyValidationIssue(
            code="missing_critical_component",
            message=f"Critical component missing: {catalog_id}.",
        ))
    if not any(component.catalog_id == "payload.sensor" for component in installed):
        issues.append(TwinAssemblyValidationIssue(code="missing_sensor", message="At least one sensor component must be installed."))

    if state.selected_component_id:
        selected = by_id.get(state.selected_component_id)
        if selected is None or selected.install_state == "removed":
            issues.append(TwinAssemblyValidationIssue(
                code="selected_removed_component",
                message="Selected component is missing or removed.",
                component_id=state.selected_component_id,
            ))

    for link in state.links:
        from_component = installed_by_id.get(link.from_component)
        to_component = installed_by_id.get(link.to_component)
        if not from_component or not to_component:
            issues.append(TwinAssemblyValidationIssue(
                code="link_references_removed_component",
                message=f"Link {link.link_id} references a missing or removed component.",
                link_id=link.link_id,
            ))
            continue
        from_port = _find_port(from_component, link.from_port)
        to_port = _find_port(to_component, link.to_port)
        if from_port is None or to_port is None:
            issues.append(TwinAssemblyValidationIssue(
                code="link_references_unknown_port",
                message=f"Link {link.link_id} references an unknown port.",
                link_id=link.link_id,
            ))
            continue
        if not _direction_allows(from_port.direction, outbound=True) or not _direction_allows(to_port.direction, outbound=False):
            issues.append(TwinAssemblyValidationIssue(
                code="invalid_port_direction",
                message=f"Link {link.link_id} has incompatible port directions.",
                link_id=link.link_id,
            ))
        if not _port_kinds_compatible(from_port, to_port, link.medium):
            issues.append(TwinAssemblyValidationIssue(
                code="incompatible_port_kind",
                message=f"Link {link.link_id} connects incompatible {from_port.kind} and {to_port.kind} ports.",
                link_id=link.link_id,
            ))

    for component in installed:
        for port in component.ports:
            if not port.required:
                continue
            if not _port_has_enabled_link(state, component.instance_id, port.port_id):
                issues.append(TwinAssemblyValidationIssue(
                    code="required_port_unconnected",
                    message=f"{component.display_name}.{port.port_id} is required but not connected.",
                    component_id=component.instance_id,
                    port_id=port.port_id,
                ))

    blocking = sum(1 for issue in issues if issue.severity == "error")
    return TwinAssemblyValidation(ok=blocking == 0, issues=issues, blocking_count=blocking, checked_at=time.time())


def _valid_selected_component_id(state: TwinAssemblyState) -> Optional[str]:
    selected = _find_component(state.components, state.selected_component_id)
    if selected and selected.install_state != "removed":
        return selected.instance_id
    return _next_installed_component_id(state.components)


def _next_installed_component_id(components: Iterable[TwinComponentInstance], exclude: Optional[str] = None) -> Optional[str]:
    for component in components:
        if component.instance_id != exclude and component.install_state != "removed":
            return component.instance_id
    return None


def _require_installed_component(state: TwinAssemblyState, component_id: str) -> TwinComponentInstance:
    component = _find_component(state.components, component_id)
    if component is None:
        raise ValueError(f"Unknown component id: {component_id}")
    if component.install_state == "removed":
        raise ValueError(f"Removed component cannot be modified: {component_id}")
    return component


def _validate_link_request(state: TwinAssemblyState, req: ComponentLinkRequest) -> None:
    from_component = _require_installed_component(state, req.from_component)
    to_component = _require_installed_component(state, req.to_component)
    from_port = _find_port(from_component, req.from_port)
    to_port = _find_port(to_component, req.to_port)
    if from_port is None:
        raise ValueError(f"Unknown from_port: {req.from_component}.{req.from_port}")
    if to_port is None:
        raise ValueError(f"Unknown to_port: {req.to_component}.{req.to_port}")
    if not _direction_allows(from_port.direction, outbound=True) or not _direction_allows(to_port.direction, outbound=False):
        raise ValueError("Port directions are not compatible for this link")
    if not _port_kinds_compatible(from_port, to_port, req.medium):
        raise ValueError(f"Port kinds are not compatible: {from_port.kind} -> {to_port.kind}")


def _find_port(component: TwinComponentInstance, port_id: str) -> Optional[TwinComponentPort]:
    return next((port for port in component.ports if port.port_id == port_id), None)


def _direction_allows(direction: str, *, outbound: bool) -> bool:
    normalized = direction.lower().strip()
    if normalized == "inout":
        return True
    return normalized == ("out" if outbound else "in")


def _port_kinds_compatible(from_port: TwinComponentPort, to_port: TwinComponentPort, medium: str) -> bool:
    medium = (medium or from_port.kind).lower().strip()
    from_compatible = set(from_port.compatible_kinds or [from_port.kind])
    to_compatible = set(to_port.compatible_kinds or [to_port.kind])
    return medium in from_compatible and medium in to_compatible and from_port.kind == to_port.kind == medium


def _port_has_enabled_link(state: TwinAssemblyState, component_id: str, port_id: str) -> bool:
    return any(
        link.enabled
        and (
            (link.from_component == component_id and link.from_port == port_id)
            or (link.to_component == component_id and link.to_port == port_id)
        )
        for link in state.links
    )


def _vector(values: Dict[str, Any], *, default: Optional[Dict[str, float]] = None, minimum: Optional[float] = None) -> Dict[str, float]:
    base = {"x": 0.0, "y": 0.0, "z": 0.0}
    if default:
        base.update({axis: float(default.get(axis, base[axis])) for axis in base})
    for axis in ("x", "y", "z"):
        if axis in values:
            value = float(values[axis])
            base[axis] = max(minimum, value) if minimum is not None else value
    return base


def build_assembly_context(assembly: Optional[TwinAssemblyState]) -> Dict[str, Any]:
    if assembly is None:
        return {}
    installed = [component for component in assembly.components if component.install_state != "removed"]
    installed_ids = {component.instance_id for component in installed}
    installed_catalogs = {component.catalog_id for component in installed}
    load_w = sum(_component_load(component) for component in installed)
    context = {
        "load_w_add": round(load_w - 3.2, 4),
        "radiator_efficiency_multiplier": 1.0,
        "thermal_controller_stuck": False,
        "antenna_alignment_error_deg": 0.0,
        "transceiver_softlock": False,
        "packet_loss_floor": 0.0,
        "sensor_readout_bias": 0.0,
        "using_backup_sensor": False,
        "assembly_validation_ok": assembly.validation.ok,
        "assembly_digest": assembly.assembly_digest,
    }
    if "thermal.radiator" not in installed_catalogs or not _has_catalog_link(assembly, "thermal.controller", "thermal.radiator", "thermal"):
        context["radiator_efficiency_multiplier"] = min(float(context["radiator_efficiency_multiplier"]), 0.38)
    if "thermal.controller" not in installed_catalogs:
        context["thermal_controller_stuck"] = True
    if "comms.hga" not in installed_catalogs or "comms.transceiver" not in installed_catalogs or not _has_catalog_link(assembly, "comms.transceiver", "comms.hga", "rf"):
        context["packet_loss_floor"] = max(float(context["packet_loss_floor"]), 0.72)
        context["antenna_alignment_error_deg"] = max(float(context["antenna_alignment_error_deg"]), 20.0)
    if "power.rtg" not in installed_catalogs or "power.bus" not in installed_catalogs:
        context["battery_health_factor"] = 0.62
    primary_sensors = [
        component for component in installed
        if component.catalog_id == "payload.sensor" and bool(component.parameters.get("primary", True))
    ]
    backup_sensors = [
        component for component in installed
        if component.catalog_id == "payload.sensor" and not bool(component.parameters.get("primary", True))
    ]
    primary_linked = any(_component_has_data_path(assembly, component.instance_id, installed_ids) for component in primary_sensors)
    backup_linked = any(_component_has_data_path(assembly, component.instance_id, installed_ids) for component in backup_sensors)
    if not primary_linked:
        context["sensor_readout_bias"] = 0.28
        context["using_backup_sensor"] = backup_linked
    for component in installed:
        if component.health_state == "fault":
            _apply_component_fault_context(context, component)
    return context


def _component_load(component: TwinComponentInstance) -> float:
    explicit = component.parameters.get("load_w")
    if isinstance(explicit, (int, float)):
        return float(explicit)
    defaults = {
        "power.rtg": -0.4,
        "power.bus": 0.1,
        "thermal.controller": 0.2,
        "thermal.radiator": 0.05,
        "comms.hga": 0.12,
        "comms.transceiver": 0.45,
        "computer.flight": 0.65,
        "computer.memory": 0.24,
        "payload.instrument": 1.1,
        "payload.sensor": 0.14,
    }
    return float(defaults.get(component.catalog_id, 0.2))


def _has_catalog_link(assembly: TwinAssemblyState, from_catalog: str, to_catalog: str, medium: str) -> bool:
    by_id = {component.instance_id: component for component in assembly.components if component.install_state != "removed"}
    for link in assembly.links:
        if not link.enabled or link.medium != medium:
            continue
        source = by_id.get(link.from_component)
        target = by_id.get(link.to_component)
        if source and target and source.catalog_id == from_catalog and target.catalog_id == to_catalog:
            return True
    return False


def _component_has_data_path(assembly: TwinAssemblyState, component_id: str, installed_ids: set[str]) -> bool:
    return any(
        link.enabled
        and link.medium == "data"
        and component_id in {link.from_component, link.to_component}
        and link.from_component in installed_ids
        and link.to_component in installed_ids
        for link in assembly.links
    )


def _apply_component_fault_context(context: Dict[str, Any], component: TwinComponentInstance) -> None:
    for fault in component.active_faults:
        category = str(fault.get("category", ""))
        severity = float(fault.get("severity", 0.5))
        if category in {"transceiver_softlock", "burst_packet_loss"}:
            context["transceiver_softlock"] = True
            context["packet_loss_floor"] = max(float(context["packet_loss_floor"]), 0.35 + severity * 0.35)
        elif category in {"antenna_misalignment"}:
            context["antenna_alignment_error_deg"] = max(float(context["antenna_alignment_error_deg"]), 8.0 + severity * 24.0)
        elif category in {"radiator_efficiency_drop"}:
            context["radiator_efficiency_multiplier"] = min(float(context["radiator_efficiency_multiplier"]), max(0.1, 1.0 - severity))
        elif category in {"thermal_controller_stuck", "heater_stuck_on"}:
            context["thermal_controller_stuck"] = True
            context["load_w_add"] = float(context["load_w_add"]) + severity * 0.8
        elif category in {"load_spike"}:
            context["load_w_add"] = float(context["load_w_add"]) + severity * 2.0
        elif category in {"sensor", "sensor_drift"}:
            context["sensor_readout_bias"] = max(float(context["sensor_readout_bias"]), 0.12 + severity * 0.28)
        elif category in {"scheduler_overload", "memory_leak"}:
            context["cpu_load_floor"] = max(float(context.get("cpu_load_floor", 0.0)), 0.45 + severity * 0.42)
            context["memory_growth_mb"] = max(float(context.get("memory_growth_mb", 0.0)), 4.0 + severity * 18.0)
