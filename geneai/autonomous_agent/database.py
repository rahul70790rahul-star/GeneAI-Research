"""Database module for Autonomous Agent execution history."""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

AUTONOMOUS_DB_PATH = DATABASE_PATH.parent / "geneai_autonomous_agent.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Agent sessions
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    result_summary TEXT,
    error_message TEXT
);

-- Task execution history
CREATE TABLE IF NOT EXISTS task_executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    tool_name TEXT,
    tool_params_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    result_json TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id) ON DELETE CASCADE
);

-- Human approval requests
CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    description TEXT NOT NULL,
    parameters_json TEXT,
    metadata_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at REAL NOT NULL,
    expires_at REAL,
    responded_at REAL,
    response TEXT,
    responder_id TEXT,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id) ON DELETE CASCADE
);

-- Execution history entries (audit trail)
CREATE TABLE IF NOT EXISTS history_entries (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    data_json TEXT,
    metadata_json TEXT,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id) ON DELETE CASCADE
);

-- Tool registry
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT,
    parameters_json TEXT,
    requires_approval INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    registered_at REAL NOT NULL
);

-- Agent configuration
CREATE TABLE IF NOT EXISTS agent_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user ON agent_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON agent_sessions(status);
CREATE INDEX IF NOT EXISTS idx_executions_session ON task_executions(session_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON task_executions(status);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approval_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_history_session ON history_entries(session_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(AUTONOMOUS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after v1 without dropping existing data."""
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(approval_requests)").fetchall()
    }
    for column, ddl in (
        ("parameters_json", "ALTER TABLE approval_requests ADD COLUMN parameters_json TEXT"),
        ("metadata_json", "ALTER TABLE approval_requests ADD COLUMN metadata_json TEXT"),
        ("expires_at", "ALTER TABLE approval_requests ADD COLUMN expires_at REAL"),
    ):
        if column not in existing:
            conn.execute(ddl)


def initialize_autonomous_database() -> None:
    """Create all autonomous agent tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            _migrate_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO agent_config (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", str(_SCHEMA_VERSION), time.time()),
            )
            conn.commit()
            logger.info("Autonomous agent database initialized at %s", AUTONOMOUS_DB_PATH)
        finally:
            conn.close()


def init_database() -> None:
    """Backwards-compatible alias for :func:`initialize_autonomous_database`."""
    initialize_autonomous_database()


def get_autonomous_db_version() -> int:
    """Get current autonomous agent database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT value FROM agent_config WHERE key = 'schema_version'").fetchone()
            return int(row["value"]) if row else 0
        finally:
            conn.close()


# Session operations
def create_agent_session(
    session_id: str,
    user_id: str | None,
    question: str,
) -> str:
    """Create a new agent session."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO agent_sessions (session_id, user_id, question, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (session_id, user_id, question, now, now),
            )
            conn.commit()
            logger.info("Created agent session %s for user %s", session_id, user_id)
            return session_id
        finally:
            conn.close()


def update_session_status(
    session_id: str,
    status: str,
    result_summary: str | None = None,
    error_message: str | None = None,
) -> bool:
    """Update session status."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            if status == "completed":
                cursor = conn.execute(
                    """
                    UPDATE agent_sessions
                    SET status = ?, result_summary = ?, error_message = ?, updated_at = ?, completed_at = ?
                    WHERE session_id = ?
                    """,
                    (status, result_summary, error_message, now, now, session_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE agent_sessions
                    SET status = ?, result_summary = ?, error_message = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (status, result_summary, error_message, now, session_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_agent_session(session_id: str) -> dict[str, Any] | None:
    """Get session by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_recent_sessions(limit: int = 50, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get recent sessions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM agent_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_sessions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


# Task execution operations
def create_task_execution(
    execution_id: str,
    session_id: str,
    task_id: str,
    task_name: str,
    tool_name: str | None = None,
    tool_params: dict[str, Any] | None = None,
) -> str:
    """Create a new task execution record."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO task_executions
                (execution_id, session_id, task_id, task_name, tool_name, tool_params_json, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    execution_id,
                    session_id,
                    task_id,
                    task_name,
                    tool_name,
                    json.dumps(tool_params) if tool_params else None,
                    now,
                ),
            )
            conn.commit()
            return execution_id
        finally:
            conn.close()


def update_task_execution(
    execution_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    retry_count: int | None = None,
) -> bool:
    """Update task execution status."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            if retry_count is not None:
                cursor = conn.execute(
                    """
                    UPDATE task_executions
                    SET status = ?, result_json = ?, error_message = ?, completed_at = ?, retry_count = ?
                    WHERE execution_id = ?
                    """,
                    (status, json.dumps(result) if result else None, error_message, now, retry_count, execution_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE task_executions
                    SET status = ?, result_json = ?, error_message = ?, completed_at = ?
                    WHERE execution_id = ?
                    """,
                    (status, json.dumps(result) if result else None, error_message, now, execution_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_task_executions(session_id: str) -> list[dict[str, Any]]:
    """Get all task executions for a session."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM task_executions WHERE session_id = ? ORDER BY started_at",
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


# Approval operations
def _to_epoch(value: Any) -> float | None:
    """Convert an ISO-8601 string, datetime, or numeric timestamp to epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def create_approval_request(
    approval_id: str,
    session_id: str,
    task_id: str,
    request_type: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    expires_at: Any = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Create a human approval request."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO approval_requests
                (approval_id, session_id, task_id, request_type, description,
                 parameters_json, metadata_json, status, requested_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    approval_id,
                    session_id,
                    task_id,
                    request_type,
                    description,
                    json.dumps(parameters) if parameters else None,
                    json.dumps(metadata) if metadata else None,
                    now,
                    _to_epoch(expires_at),
                ),
            )
            conn.commit()
            logger.info("Created approval request %s for session %s", approval_id, session_id)
            return approval_id
        finally:
            conn.close()


def get_approval_request(approval_id: str) -> dict[str, Any] | None:
    """Get a single approval request by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            return _approval_row_to_dict(row) if row else None
        finally:
            conn.close()


def _approval_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["parameters"] = json.loads(data.get("parameters_json") or "{}")
    data["metadata"] = json.loads(data.get("metadata_json") or "{}")
    return data


def respond_to_approval(
    approval_id: str,
    response: str,
    responder_id: str,
) -> bool:
    """Respond to an approval request."""
    now = time.time()
    normalized = response.strip().lower()
    if normalized in ("approve", "approved", "yes", "true"):
        status = "approved"
    elif normalized in ("expire", "expired"):
        status = "expired"
    elif normalized in ("cancel", "cancelled", "canceled"):
        status = "cancelled"
    else:
        status = "rejected"
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, response = ?, responded_at = ?, responder_id = ?
                WHERE approval_id = ?
                """,
                (status, response, now, responder_id, approval_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_pending_approvals(session_id: str | None = None) -> list[dict[str, Any]]:
    """Get pending approval requests."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM approval_requests WHERE session_id = ? AND status = 'pending' ORDER BY requested_at",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY requested_at"
                ).fetchall()
            return [_approval_row_to_dict(row) for row in rows]
        finally:
            conn.close()


# Tool registry operations
def register_tool(
    tool_name: str,
    description: str,
    category: str | None = None,
    parameters: dict[str, Any] | None = None,
    requires_approval: bool = False,
) -> None:
    """Register a tool in the registry."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_registry
                (tool_name, description, category, parameters_json, requires_approval, enabled, registered_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (tool_name, description, category, json.dumps(parameters) if parameters else None, int(requires_approval), now),
            )
            conn.commit()
        finally:
            conn.close()


def get_registered_tools(category: str | None = None, enabled_only: bool = True) -> list[dict[str, Any]]:
    """Get registered tools."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM tool_registry WHERE 1=1"
            params = []
            if enabled_only:
                query += " AND enabled = 1"
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " ORDER BY tool_name"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def set_tool_enabled(tool_name: str, enabled: bool) -> bool:
    """Enable or disable a tool."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                "UPDATE tool_registry SET enabled = ? WHERE tool_name = ?",
                (int(enabled), tool_name),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# Configuration
def set_config(key: str, value: str) -> None:
    """Set agent configuration."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO agent_config (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
            conn.commit()
        finally:
            conn.close()


def get_config(key: str, default: str | None = None) -> str | None:
    """Get agent configuration."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT value FROM agent_config WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()


# Execution history operations
def record_history_entry(
    entry_id: str,
    session_id: str,
    entry_type: str,
    timestamp: Any = None,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Persist a single history entry (audit trail)."""
    ts = _to_epoch(timestamp) if timestamp is not None else time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO history_entries
                (entry_id, session_id, entry_type, timestamp, data_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    session_id,
                    entry_type,
                    ts,
                    json.dumps(data) if data else None,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()
            return entry_id
        finally:
            conn.close()


def _history_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["timestamp"] = (
        datetime.fromtimestamp(data["timestamp"]).isoformat() if data.get("timestamp") else None
    )
    data["data"] = json.loads(data.get("data_json") or "{}")
    data["metadata"] = json.loads(data.get("metadata_json") or "{}")
    return data


def get_session_history(session_id: str) -> list[dict[str, Any]]:
    """Get the full execution history for a session, oldest first."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM history_entries WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [_history_row_to_dict(row) for row in rows]
        finally:
            conn.close()


def get_execution_history(
    session_id: str | None = None,
    limit: int = 100,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent task executions, optionally filtered by session and status."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM task_executions WHERE 1=1"
            params: list[Any] = []
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()