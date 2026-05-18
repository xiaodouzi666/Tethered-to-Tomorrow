from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Generic, Optional, Type, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


def _default_db_path() -> str:
    root = Path(__file__).resolve().parents[2]
    return str(root / "runtime" / "deeprepair_twin.sqlite3")


def database_path() -> str:
    return os.getenv("TWIN_DB_PATH", _default_db_path())


class SQLiteJSONStore(Generic[T]):
    def __init__(self, namespace: str, model: Type[T], ttl_sec: Optional[int] = None) -> None:
        self.namespace = namespace
        self.model = model
        self.ttl_sec = ttl_sec
        self.path = database_path()
        self._lock = RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    namespace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (namespace, item_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def get(self, item_id: str) -> Optional[T]:
        self.prune()
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT payload FROM kv_store WHERE namespace = ? AND item_id = ?",
                (self.namespace, item_id),
            ).fetchone()
        if row is None:
            return None
        return self.model(**json.loads(str(row["payload"])))

    def put(self, item_id: str, value: T, *, event_type: str = "save", audit_payload: Optional[Dict[str, Any]] = None) -> T:
        now = time.time()
        payload = _model_payload(value)
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO kv_store(namespace, item_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, item_id)
                DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (self.namespace, item_id, payload, now),
            )
            conn.execute(
                "INSERT INTO audit_log(namespace, item_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (self.namespace, item_id, event_type, json.dumps(audit_payload or {}, sort_keys=True), now),
            )
        return value

    def delete(self, item_id: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM kv_store WHERE namespace = ? AND item_id = ?", (self.namespace, item_id))

    def prune(self) -> None:
        if not self.ttl_sec:
            return
        cutoff = time.time() - self.ttl_sec
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM kv_store WHERE namespace = ? AND updated_at < ?", (self.namespace, cutoff))


def audit_event(namespace: str, item_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    store = SQLiteJSONStore(namespace, _AuditPlaceholder)
    now = time.time()
    with store._lock, store._connection() as conn:
        conn.execute(
            "INSERT INTO audit_log(namespace, item_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (namespace, item_id, event_type, json.dumps(payload, sort_keys=True, default=str), now),
        )


def _model_payload(value: BaseModel) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), sort_keys=True, default=str)
    return value.json()


class _AuditPlaceholder(BaseModel):
    ok: bool = True
