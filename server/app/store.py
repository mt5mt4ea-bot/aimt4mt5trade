from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    request_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_account_time ON snapshots(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_plans_account_time ON plans(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS heartbeats (
                    ea_instance_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS order_events (
                    event_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """
            )

    def save_snapshot(self, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                (payload["request_id"], payload["account"]["account_id"], payload["quote"]["symbol"], payload["timestamp"], json.dumps(payload, ensure_ascii=False)),
            )

    def save_plan(self, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO plans VALUES (?, ?, ?, ?, ?, ?)",
                (payload["plan_id"], payload["request_id"], payload["account_id"], payload["symbol"], payload["issued_at"], json.dumps(payload, ensure_ascii=False)),
            )

    def save_heartbeat(self, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO heartbeats VALUES (?, ?, ?, ?)",
                (payload["ea_instance_id"], payload["account_id"], now, json.dumps(payload, ensure_ascii=False)),
            )

    def save_order_event(self, payload: dict[str, Any]) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO order_events VALUES (?, ?, ?, ?, ?)",
                (payload["event_id"], payload["plan_id"], payload["account_id"], payload["timestamp"], json.dumps(payload, ensure_ascii=False)),
            )
            return cursor.rowcount > 0

    def latest(self, table: str, account_id: str | None = None) -> dict[str, Any] | None:
        if table not in {"snapshots", "plans"}:
            raise ValueError("unsupported table")
        query = f"SELECT payload FROM {table}"
        params: tuple[Any, ...] = ()
        if account_id:
            query += " WHERE account_id = ?"
            params = (account_id,)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self._lock, self._connect() as db:
            row = db.execute(query, params).fetchone()
        return json.loads(row["payload"]) if row else None

    def latest_heartbeat(self, account_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT payload, updated_at FROM heartbeats"
        params: tuple[Any, ...] = ()
        if account_id:
            query += " WHERE account_id = ?"
            params = (account_id,)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with self._lock, self._connect() as db:
            row = db.execute(query, params).fetchone()
        if not row:
            return None
        result = json.loads(row["payload"])
        result["server_received_at"] = row["updated_at"]
        return result

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

