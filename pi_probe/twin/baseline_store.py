from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pi_probe.probe.state import SpacecraftState


@dataclass
class FrozenBaseline:
    baseline_id: str
    created_at: float
    expires_at: float
    captured_seq: int
    captured_change_version: int
    captured_fault: str
    state_digest: str
    snapshot: Dict[str, Any]
    state: SpacecraftState
    reason: str = "manual"

    def clone_state(self) -> SpacecraftState:
        return self.state.clone_for_baseline()

    def meta_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "captured_at": self.created_at,
            "expires_at": self.expires_at,
            "captured_seq": self.captured_seq,
            "captured_change_version": self.captured_change_version,
            "captured_fault": self.captured_fault,
            "state_digest": self.state_digest,
        }


class BaselineStore:
    def __init__(self, ttl_sec: int = 300) -> None:
        self.ttl_sec = ttl_sec
        self._store: Dict[str, FrozenBaseline] = {}

    def create(self, state: SpacecraftState, reason: str = "manual") -> FrozenBaseline:
        self.prune()
        created_at = time.time()
        cloned = state.clone_for_baseline()
        snapshot = cloned.snapshot()
        baseline = FrozenBaseline(
            baseline_id=f"baseline-{uuid.uuid4().hex[:12]}",
            created_at=created_at,
            expires_at=created_at + self.ttl_sec,
            captured_seq=int(snapshot.get("seq", cloned.seq)),
            captured_change_version=int(snapshot.get("change_version", cloned.change_version)),
            captured_fault=str(snapshot.get("active_fault", cloned.active_fault)),
            state_digest=cloned.state_digest(),
            snapshot=snapshot,
            state=cloned,
            reason=reason,
        )
        self._store[baseline.baseline_id] = baseline
        return baseline

    def get(self, baseline_id: str) -> Optional[FrozenBaseline]:
        self.prune()
        return self._store.get(baseline_id)

    def delete(self, baseline_id: str) -> None:
        self._store.pop(baseline_id, None)

    def prune(self) -> None:
        now = time.time()
        expired = [
            baseline_id
            for baseline_id, baseline in self._store.items()
            if baseline.expires_at <= now
        ]
        for baseline_id in expired:
            self.delete(baseline_id)
