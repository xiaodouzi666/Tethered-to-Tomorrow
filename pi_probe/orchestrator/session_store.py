from __future__ import annotations

import time
from typing import Dict, Optional

from pi_probe.orchestrator.schemas import OrchestratorSession


class OrchestratorSessionStore:
    def __init__(self, ttl_sec: int = 900):
        self.ttl_sec = ttl_sec
        self._store: Dict[str, OrchestratorSession] = {}

    def create(self, session: OrchestratorSession) -> OrchestratorSession:
        self.prune()
        self._store[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[OrchestratorSession]:
        self.prune()
        return self._store.get(session_id)

    def save(self, session: OrchestratorSession) -> OrchestratorSession:
        session.updated_at = time.time()
        self._store[session.session_id] = session
        return session

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def prune(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._store.items()
            if session.updated_at + self.ttl_sec <= now
        ]
        for session_id in expired:
            self.delete(session_id)
