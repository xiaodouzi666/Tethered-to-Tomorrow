from __future__ import annotations

import time
import uuid
from typing import Dict, Optional

from pi_probe.twin.schemas import (
    CampaignResponse,
    FaultSpec,
    GroundTestbedSession,
    TwinCalibration,
    TwinPlanCandidate,
    BaselineMeta,
)


class GroundTestbedStore:
    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._store: Dict[str, GroundTestbedSession] = {}

    def create(
        self,
        *,
        baseline: BaselineMeta,
        calibration: TwinCalibration,
        candidate_plans: list[TwinPlanCandidate],
    ) -> GroundTestbedSession:
        self.prune()
        now = time.time()
        session = GroundTestbedSession(
            session_id=f"testbed-{uuid.uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            status="BASELINE_FROZEN",
            baseline=baseline,
            calibration=calibration,
            candidate_plans=candidate_plans,
        )
        self._store[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[GroundTestbedSession]:
        self.prune()
        return self._store.get(session_id)

    def save(self, session: GroundTestbedSession) -> GroundTestbedSession:
        session.updated_at = time.time()
        self._store[session.session_id] = session
        return session

    def add_faults(
        self,
        session_id: str,
        faults: list[FaultSpec],
        label: str = "operator_fault_injection",
    ) -> GroundTestbedSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        stamped = [
            fault.model_copy(update={"source": label}) if hasattr(fault, "model_copy") else fault.copy(update={"source": label})
            for fault in faults
        ]
        session.twin_faults.extend(stamped)
        session.status = "FAULTS_INJECTED"
        return self.save(session)

    def attach_campaign(self, session_id: str, campaign: CampaignResponse) -> GroundTestbedSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        session.last_campaign = campaign
        session.selected_plan_id = campaign.best_plan_id
        session.status = "CAMPAIGN_COMPLETE"
        return self.save(session)

    def attach_package(self, session_id: str, package_id: str) -> GroundTestbedSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        session.command_package_id = package_id
        session.status = "COMMAND_PACKAGE_DRAFT"
        return self.save(session)

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_sec
        expired = [
            session_id
            for session_id, session in self._store.items()
            if session.updated_at < cutoff
        ]
        for session_id in expired:
            self._store.pop(session_id, None)
