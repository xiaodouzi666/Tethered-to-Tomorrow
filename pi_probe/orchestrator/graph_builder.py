from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from pi_probe.orchestrator.schemas import GraphBundle, OrchestratorSession


def build_graph_bundle(session: OrchestratorSession) -> GraphBundle:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_nodes: Set[str] = set()
    seen_edges: Set[Tuple[str, str, str]] = set()

    def add_node(node_id: str, node_type: str, label: str, **extra: Any) -> None:
        if not node_id or node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append({"id": node_id, "type": node_type, "label": label, **extra})

    def add_edge(source: str, target: str, relation: str, **extra: Any) -> None:
        key = (source, target, relation)
        if not source or not target or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": source, "target": target, "relation": relation, **extra})

    add_node(session.baseline.baseline_id, "baseline", "Frozen baseline", seq=session.baseline.captured_seq)
    selected_plan = session.selected_plan_id or session.recommended_plan_id or ""
    if selected_plan:
        add_node(selected_plan, "plan", selected_plan, recommended=selected_plan == session.recommended_plan_id)
        add_edge(session.baseline.baseline_id, selected_plan, "evaluates")

    for group_name, node_type in (
        ("root_causes", "fault"),
        ("recoverable_faults", "fault"),
        ("active_mitigations", "mitigation"),
        ("symptoms", "symptom"),
    ):
        records = getattr(session.fault_layers, group_name, [])
        for record in records:
            if not isinstance(record, dict):
                continue
            node_id = str(record.get("id", ""))
            add_node(node_id, node_type, node_id, status=record.get("status"), system=record.get("system"))
            system = str(record.get("system", ""))
            if system:
                subsystem_id = f"subsystem:{system}"
                add_node(subsystem_id, "subsystem", system)
                add_edge(node_id, subsystem_id, "affects")

    result = next((item for item in session.twin_compare.results if item.plan_id == selected_plan), None)
    if result:
        for trace in result.repair_trace:
            action_id = f"action:{trace.action}:{trace.step_index}"
            add_node(action_id, "action", trace.action, step_index=trace.step_index)
            if selected_plan:
                add_edge(selected_plan, action_id, "contains")
            for fault_id in trace.cleared_faults:
                add_node(fault_id, "fault", fault_id)
                add_edge(action_id, fault_id, "clears")
            for fault_id in trace.suppressed_faults:
                add_node(fault_id, "fault", fault_id)
                add_edge(action_id, fault_id, "suppresses")
            for fault_id in trace.remaining_root_causes:
                add_node(fault_id, "fault", fault_id)
                add_edge(fault_id, action_id, "remains_after")
        for check in result.constraints:
            check_id = f"constraint:{check.name}"
            add_node(check_id, "constraint", check.name, passed=check.passed)
            if selected_plan:
                add_edge(selected_plan, check_id, "satisfies" if check.passed else "violates")

    return GraphBundle(
        session_id=session.session_id,
        nodes=nodes,
        edges=edges,
        summary=f"{len(nodes)} nodes and {len(edges)} edges generated for recovery trace.",
    )
