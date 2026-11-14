"""Agent memory module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    entry_type: str = ""  # question, answer, tool_result, summary, correction
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    importance: float = 1.0  # 0-1, higher = more important


class AgentMemory:
    """
    Conversation memory for the autonomous agent.

    Maintains context across interactions within a session.
    """

    def __init__(self, max_turns: int = 20, max_entries: int = 100):
        self.max_turns = max_turns
        self.max_entries = max_entries
        self.entries: list[MemoryEntry] = []
        self.logger = logging.getLogger(__name__)

    def add_entry(
        self,
        session_id: str,
        entry_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 1.0,
    ) -> str:
        """Add a memory entry."""
        entry = MemoryEntry(
            session_id=session_id,
            entry_type=entry_type,
            content=content,
            metadata=metadata or {},
            importance=importance,
        )
        self.entries.append(entry)

        # Trim if too many entries
        if len(self.entries) > self.max_entries:
            # Keep most important and recent
            self.entries.sort(key=lambda e: (e.importance, e.timestamp.timestamp()))
            self.entries = self.entries[-self.max_entries:]

        self.logger.debug("Added memory entry %s for session %s", entry.entry_id, session_id)
        return entry.entry_id

    def get_recent(self, session_id: str, n: int | None = None) -> list[MemoryEntry]:
        """Get recent entries for a session."""
        session_entries = [e for e in self.entries if e.session_id == session_id]
        session_entries.sort(key=lambda e: e.timestamp)
        if n:
            return session_entries[-n:]
        return session_entries

    def get_by_type(self, session_id: str, entry_type: str) -> list[MemoryEntry]:
        """Get entries by type for a session."""
        return [e for e in self.entries if e.session_id == session_id and e.entry_type == entry_type]

    def search(self, session_id: str, query: str) -> list[MemoryEntry]:
        """Search memory by content."""
        query = query.lower()
        return [
            e for e in self.entries
            if e.session_id == session_id and query in e.content.lower()
        ]

    def get_context(self, session_id: str, max_tokens: int = 2000) -> str:
        """
        Get formatted context for LLM.

        Returns a string summarizing recent conversation.
        """
        recent = self.get_recent(session_id, self.max_turns)
        if not recent:
            return ""

        context_parts = ["## Conversation Context\n"]
        for entry in recent:
            if entry.entry_type == "question":
                context_parts.append(f"**User**: {entry.content}")
            elif entry.entry_type == "answer":
                context_parts.append(f"**Assistant**: {entry.content[:500]}...")
            elif entry.entry_type == "tool_result":
                tool = entry.metadata.get("tool", "unknown")
                context_parts.append(f"**Tool ({tool})**: {entry.content[:300]}...")
            elif entry.entry_type == "summary":
                context_parts.append(f"**Summary**: {entry.content[:500]}...")

        return "\n\n".join(context_parts)

    def clear_session(self, session_id: str) -> int:
        """Clear all entries for a session."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.session_id != session_id]
        cleared = before - len(self.entries)
        self.logger.info("Cleared %d entries for session %s", cleared, session_id)
        return cleared

    def get_stats(self, session_id: str) -> dict[str, Any]:
        """Get memory statistics for a session."""
        session_entries = [e for e in self.entries if e.session_id == session_id]
        types = {}
        for e in session_entries:
            types[e.entry_type] = types.get(e.entry_type, 0) + 1

        return {
            "total_entries": len(session_entries),
            "by_type": types,
            "date_range": {
                "first": min(e.timestamp for e in session_entries).isoformat() if session_entries else None,
                "last": max(e.timestamp for e in session_entries).isoformat() if session_entries else None,
            },
        }


class LongTermMemory:
    """
    Long-term memory across sessions.

    Stores learned patterns, successful workflows, user preferences.
    """

    def __init__(self):
        self.patterns: dict[str, dict[str, Any]] = {}
        self.user_preferences: dict[str, dict[str, Any]] = {}
        self.successful_workflows: list[dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)

    def record_workflow(
        self,
        question_type: str,
        task_plan: dict[str, Any],
        success: bool,
        execution_time: float,
    ) -> None:
        """Record a workflow execution for learning."""
        pattern = self.patterns.get(question_type, {
            "count": 0,
            "success_count": 0,
            "avg_time": 0,
            "common_tasks": {},
        })

        pattern["count"] += 1
        if success:
            pattern["success_count"] += 1
        pattern["avg_time"] = (pattern["avg_time"] * (pattern["count"] - 1) + execution_time) / pattern["count"]

        for task in task_plan.get("tasks", []):
            tool = task.get("tool_name")
            if tool:
                pattern["common_tasks"][tool] = pattern["common_tasks"].get(tool, 0) + 1

        self.patterns[question_type] = pattern

        if success:
            self.successful_workflows.append({
                "question_type": question_type,
                "plan": task_plan,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat(),
            })

    def get_recommendations(self, question_type: str) -> dict[str, Any] | None:
        """Get tool/task recommendations for a question type."""
        pattern = self.patterns.get(question_type)
        if not pattern:
            return None

        # Sort tasks by frequency
        sorted_tasks = sorted(
            pattern["common_tasks"].items(),
            key=lambda x: x[1],
            reverse=True
        )

        return {
            "recommended_tools": [t for t, _ in sorted_tasks[:5]],
            "success_rate": pattern["success_count"] / pattern["count"] if pattern["count"] > 0 else 0,
            "avg_execution_time": pattern["avg_time"],
            "total_executions": pattern["count"],
        }

    def set_user_preference(self, user_id: str, key: str, value: Any) -> None:
        """Set a user preference."""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}
        self.user_preferences[user_id][key] = value

    def get_user_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        return self.user_preferences.get(user_id, {}).get(key, default)


# Global memory instances
_short_term_memory = AgentMemory()
_long_term_memory = LongTermMemory()


def get_short_term_memory() -> AgentMemory:
    """Get the global short-term memory."""
    return _short_term_memory


def get_long_term_memory() -> LongTermMemory:
    """Get the global long-term memory."""
    return _long_term_memory