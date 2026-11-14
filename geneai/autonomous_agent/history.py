"""Execution history module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from geneai.autonomous_agent.database import (
    get_execution_history,
    get_session_history,
    record_history_entry,
)
from geneai.autonomous_agent.planner import TaskPlan, Task

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """A single history entry."""
    entry_id: str
    session_id: str
    entry_type: str  # plan, task_start, task_complete, task_error, approval, summary
    timestamp: datetime
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionHistory:
    """
    Track and query execution history for sessions.

    Provides:
    - Full audit trail
    - Reproducibility
    - Debugging support
    - Learning from past runs
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _persist(self, entry_id: str, session_id: str, entry_type: str, data: dict[str, Any]) -> None:
        """Best-effort persistence of a history entry."""
        try:
            record_history_entry(entry_id, session_id, entry_type, datetime.now(), data)
        except Exception:  # pragma: no cover - history must never break execution
            self.logger.warning("Could not persist history entry %s", entry_id, exc_info=True)

    def record_plan(self, session_id: str, plan: TaskPlan) -> str:
        """Record a task plan."""
        entry_id = str(uuid.uuid4())
        data = {
            "plan_id": plan.plan_id,
            "question": plan.question,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "description": t.description,
                    "tool_name": t.tool_name,
                    "task_type": t.task_type.value,
                    "dependencies": t.dependencies,
                    "requires_approval": t.requires_approval,
                    "priority": t.priority,
                    "parameters": t.parameters,
                }
                for t in plan.tasks
            ],
            "metadata": plan.metadata,
        }
        self._persist(entry_id, session_id, "plan", data)
        self.logger.info("Recorded plan %s for session %s", plan.plan_id, session_id)
        return entry_id

    def record_task_start(self, session_id: str, task: Task) -> str:
        """Record task start."""
        entry_id = str(uuid.uuid4())
        data = {
            "task_id": task.task_id,
            "name": task.name,
            "tool_name": task.tool_name,
            "parameters": task.parameters,
        }
        self._persist(entry_id, session_id, "task_start", data)
        self.logger.debug("Recorded task start %s for session %s", task.task_id, session_id)
        return entry_id

    def record_task_result(self, session_id: str, result: dict[str, Any]) -> str:
        """Record task result."""
        entry_id = str(uuid.uuid4())
        data = {
            "task_id": result.get("task_id"),
            "task_name": result.get("task_name"),
            "tool_name": result.get("tool_name"),
            "status": result.get("status"),
            "result": result.get("result"),
            "error": result.get("error"),
            "execution_time_seconds": result.get("execution_time_seconds"),
            "retry_count": result.get("retry_count", 0),
        }
        self._persist(entry_id, session_id, "task_complete", data)
        self.logger.debug("Recorded task result %s for session %s", result.get("task_id"), session_id)
        return entry_id

    def record_approval(self, session_id: str, approval_id: str, action: str, details: dict[str, Any]) -> str:
        """Record approval action."""
        entry_id = str(uuid.uuid4())
        data = {
            "approval_id": approval_id,
            "action": action,  # requested, approved, rejected, expired
            "details": details,
        }
        self._persist(entry_id, session_id, "approval", data)
        self.logger.info("Recorded approval %s: %s for session %s", approval_id, action, session_id)
        return entry_id

    def record_summary(self, session_id: str, summary: str) -> str:
        """Record final summary."""
        entry_id = str(uuid.uuid4())
        data = {
            "summary": summary,
        }
        self._persist(entry_id, session_id, "summary", data)
        self.logger.info("Recorded summary for session %s", session_id)
        return entry_id

    def get_session_history(self, session_id: str) -> list[HistoryEntry]:
        """Get full history for a session."""
        # In production, would query database
        rows = get_session_history(session_id)
        entries = []
        for row in rows:
            entries.append(HistoryEntry(
                entry_id=row["entry_id"],
                session_id=row["session_id"],
                entry_type=row["entry_type"],
                timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
                data=row["data"] if isinstance(row["data"], dict) else {},
                metadata=row["metadata"] if isinstance(row["metadata"], dict) else {},
            ))
        return entries

    def get_task_history(self, session_id: str, task_id: str) -> list[HistoryEntry]:
        """Get history for a specific task."""
        history = self.get_session_history(session_id)
        return [e for e in history if e.data.get("task_id") == task_id]

    def get_failed_tasks(self, session_id: str) -> list[dict[str, Any]]:
        """Get all failed tasks in a session."""
        history = self.get_session_history(session_id)
        failed = []
        for entry in history:
            if entry.entry_type == "task_complete" and entry.data.get("status") == "failed":
                failed.append(entry.data)
        return failed

    def get_execution_timeline(self, session_id: str) -> list[dict[str, Any]]:
        """Get chronological timeline of execution."""
        history = self.get_session_history(session_id)
        history.sort(key=lambda e: e.timestamp)

        timeline = []
        for entry in history:
            timeline.append({
                "timestamp": entry.timestamp.isoformat(),
                "type": entry.entry_type,
                "description": self._describe_entry(entry),
                "data": entry.data,
            })
        return timeline

    def _describe_entry(self, entry: HistoryEntry) -> str:
        """Generate human-readable description of entry."""
        if entry.entry_type == "plan":
            return f"Created plan with {len(entry.data.get('tasks', []))} tasks"
        elif entry.entry_type == "task_start":
            return f"Started task: {entry.data.get('name', 'unknown')}"
        elif entry.entry_type == "task_complete":
            status = entry.data.get("status", "unknown")
            return f"Task {entry.data.get('task_name', 'unknown')} {status}"
        elif entry.entry_type == "approval":
            return f"Approval {entry.data.get('action', 'unknown')}: {entry.data.get('details', {}).get('description', '')}"
        elif entry.entry_type == "summary":
            return "Generated final summary"
        return entry.entry_type

    def export_session(self, session_id: str) -> dict[str, Any]:
        """Export full session data for reproducibility."""
        history = self.get_session_history(session_id)

        return {
            "session_id": session_id,
            "exported_at": datetime.now().isoformat(),
            "history": [
                {
                    "entry_id": e.entry_id,
                    "type": e.entry_type,
                    "timestamp": e.timestamp.isoformat(),
                    "data": e.data,
                    "metadata": e.metadata,
                }
                for e in history
            ],
        }

    def import_session(self, data: dict[str, Any]) -> str:
        """Import session from exported data."""
        session_id = data["session_id"]
        for entry_data in data["history"]:
            # Would persist to database
            pass
        self.logger.info("Imported session %s", session_id)
        return session_id


class HistoryQuery:
    """Query interface for execution history."""

    def __init__(self, history: ExecutionHistory):
        self.history = history

    def find_sessions_by_question(self, keyword: str) -> list[str]:
        """Find sessions containing a keyword in their question."""
        # Would query database
        return []

    def find_sessions_by_tool(self, tool_name: str) -> list[str]:
        """Find sessions that used a specific tool."""
        return []

    def find_sessions_by_status(self, status: str) -> list[str]:
        """Find sessions with a specific final status."""
        return []

    def get_tool_usage_stats(self, session_id: str) -> dict[str, int]:
        """Get tool usage statistics for a session."""
        history = self.history.get_session_history(session_id)
        stats = {}
        for entry in history:
            if entry.entry_type == "task_complete":
                tool = entry.data.get("tool_name")
                if tool:
                    stats[tool] = stats.get(tool, 0) + 1
        return stats

    def get_average_task_duration(self, session_id: str, tool_name: str | None = None) -> float:
        """Get average task duration, optionally filtered by tool."""
        history = self.history.get_session_history(session_id)
        durations = []
        for entry in history:
            if entry.entry_type == "task_complete":
                if tool_name is None or entry.data.get("tool_name") == tool_name:
                    dur = entry.data.get("execution_time_seconds", 0)
                    if dur > 0:
                        durations.append(dur)
        return sum(durations) / len(durations) if durations else 0.0