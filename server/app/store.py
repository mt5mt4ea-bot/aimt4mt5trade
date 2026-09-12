from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .auth import hash_password, token_digest


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS roles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS permissions (
                    code TEXT PRIMARY KEY,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                    permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
                    PRIMARY KEY (role_id, permission_code)
                );
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, role_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_expires ON sessions(user_id, expires_at);
                """
            )
            db.execute("PRAGMA optimize")

    def ensure_rbac(self, demo_users: list[tuple[str, str, str, str]]) -> None:
        roles = {
            "ADMIN": ("role-admin", "系统管理员"),
            "MEMBER": ("role-member", "订阅会员"),
        }
        permissions = {
            "dashboard.view": "查看交易控制台",
            "trading.control": "修改自动交易开关",
            "users.manage": "管理会员、状态和角色",
            "system.manage": "管理系统级配置",
        }
        grants = {
            "ADMIN": tuple(permissions),
            "MEMBER": ("dashboard.view",),
        }
        with self._lock, self._connect() as db:
            for role, (role_id, description) in roles.items():
                db.execute("INSERT OR IGNORE INTO roles VALUES (?, ?, ?)", (role_id, role, description))
            for code, description in permissions.items():
                db.execute("INSERT OR IGNORE INTO permissions VALUES (?, ?)", (code, description))
            for role, permission_codes in grants.items():
                role_id = roles[role][0]
                for code in permission_codes:
                    db.execute("INSERT OR IGNORE INTO role_permissions VALUES (?, ?)", (role_id, code))
            for email, name, password, role in demo_users:
                existing = db.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
                if existing:
                    continue
                user_id = f"usr_{secrets.token_hex(8)}"
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, 'ACTIVE', ?)",
                    (user_id, email.lower(), name, hash_password(password), datetime.now(timezone.utc).isoformat()),
                )
                db.execute("INSERT INTO user_roles VALUES (?, ?)", (user_id, roles[role][0]))

    def create_user(self, email: str, name: str, password_hash: str, role: str = "MEMBER") -> dict[str, Any] | None:
        user_id = f"usr_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock, self._connect() as db:
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?, 'ACTIVE', ?)", (user_id, email.lower(), name, password_hash, now))
                role_row = db.execute("SELECT id FROM roles WHERE name = ?", (role,)).fetchone()
                if not role_row:
                    raise ValueError("unknown role")
                db.execute("INSERT INTO user_roles VALUES (?, ?)", (user_id, role_row["id"]))
        except sqlite3.IntegrityError:
            return None
        return self.get_user(user_id)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                SELECT u.id, u.email, u.name, u.status, u.created_at,
                       COALESCE(GROUP_CONCAT(DISTINCT r.name), '') AS roles,
                       COALESCE(GROUP_CONCAT(DISTINCT p.code), '') AS permissions
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                LEFT JOIN permissions p ON p.code = rp.permission_code
                WHERE u.id = ? GROUP BY u.id
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["roles"] = sorted(filter(None, result["roles"].split(",")))
        result["permissions"] = sorted(filter(None, result["permissions"].split(",")))
        return result

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM users ORDER BY created_at DESC").fetchall()]
        return [user for user_id in ids if (user := self.get_user(user_id))]

    def update_user_access(self, user_id: str, role: str | None, status: str | None) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            if status:
                db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
                if status == "SUSPENDED":
                    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            if role:
                role_row = db.execute("SELECT id FROM roles WHERE name = ?", (role,)).fetchone()
                if not role_row:
                    raise ValueError("unknown role")
                db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                db.execute("INSERT OR IGNORE INTO user_roles VALUES (?, ?)", (user_id, role_row["id"]))
        return self.get_user(user_id)

    def create_session(self, user_id: str, token: str, csrf_token: str, hours: int) -> None:
        now = datetime.now(timezone.utc)
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (token_digest(token), user_id, csrf_token, now.isoformat(), (now + timedelta(hours=hours)).isoformat()),
            )

    def user_for_session(self, token: str) -> tuple[dict[str, Any], str] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT user_id, csrf_token FROM sessions WHERE token_hash = ? AND expires_at > ?",
                (token_digest(token), now),
            ).fetchone()
        if not row:
            return None
        user = self.get_user(row["user_id"])
        if not user or user["status"] != "ACTIVE":
            return None
        return user, row["csrf_token"]

    def delete_session(self, token: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))

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
