"""Memory management for Biotech Assistant - Phase 5.1."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Single turn in conversation."""
    turn_id: str
    user_question: str
    assistant_answer: dict[str, Any]
    timestamp: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "user_question": self.user_question,
            "assistant_answer": self.assistant_answer,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTurn":
        return cls(
            turn_id=data["turn_id"],
            user_question=data["user_question"],
            assistant_answer=data["assistant_answer"],
            timestamp=data["timestamp"],
        )


@dataclass
class ConversationMemory:
    """Manages conversation history and persistent context."""
    
    turns: list[ConversationTurn] = field(default_factory=list)
    max_turns: int = 20
    context: dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_turn(self, question: str, answer: dict[str, Any]) -> ConversationTurn:
        """Add a conversation turn."""
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4())[:8],
            user_question=question,
            assistant_answer=answer,
            timestamp=datetime.now().isoformat(),
        )
        self.turns.append(turn)
        self.updated_at = datetime.now().isoformat()
        
        # Trim if exceeding max
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        
        return turn
    
    def get_recent(self, n: int = 5) -> list[ConversationTurn]:
        """Get recent conversation turns."""
        return self.turns[-n:] if self.turns else []
    
    def get_all(self) -> list[ConversationTurn]:
        """Get all conversation turns."""
        return self.turns.copy()
    
    def get_context_summary(self, max_turns: int = 5) -> str:
        """Generate a summary of conversation context."""
        if not self.turns:
            return "No previous conversation."
        
        summary_parts = [f"Session: {self.session_id} (started {self.created_at})"]
        summary_parts.append(f"Total turns: {len(self.turns)}")
        summary_parts.append("Recent conversation:")
        
        for turn in self.turns[-max_turns:]:
            q = turn.user_question[:120]
            a = turn.assistant_answer.get("answer_text", "")[:150]
            q_type = turn.assistant_answer.get("question_type", "unknown")
            conf = turn.assistant_answer.get("confidence", 0)
            summary_parts.append(f"  [{q_type}] Q: {q}")
            summary_parts.append(f"  A (conf: {conf:.0%}): {a}...")
        
        if self.context:
            summary_parts.append(f"Persistent context: {json.dumps(self.context, default=str)[:500]}")
        
        return "\n".join(summary_parts)
    
    def update_context(self, key: str, value: Any) -> None:
        """Update persistent context."""
        self.context[key] = value
        self.updated_at = datetime.now().isoformat()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """Get persistent context value."""
        return self.context.get(key, default)
    
    def remove_context(self, key: str) -> bool:
        """Remove context key."""
        if key in self.context:
            del self.context[key]
            self.updated_at = datetime.now().isoformat()
            return True
        return False
    
    def clear_context(self) -> None:
        """Clear all context."""
        self.context.clear()
        self.updated_at = datetime.now().isoformat()
    
    def clear(self) -> None:
        """Clear conversation and context."""
        self.turns.clear()
        self.context.clear()
        self.session_id = str(uuid.uuid4())[:8]
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turns": [t.to_dict() for t in self.turns],
            "context": self.context,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMemory":
        """Deserialize from dictionary."""
        memory = cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            context=data.get("context", {}),
        )
        memory.turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        return memory
    
    def export(self, format: str = "json") -> str:
        """Export conversation."""
        if format == "json":
            return json.dumps(self.to_dict(), indent=2)
        elif format == "markdown":
            md = [f"# GeneAI Conversation - Session {self.session_id}"]
            md.append(f"Started: {self.created_at}")
            md.append(f"Updated: {self.updated_at}")
            md.append(f"Turns: {len(self.turns)}")
            md.append("")
            
            for turn in self.turns:
                md.append(f"## Turn {turn.turn_id} - {turn.timestamp}")
                md.append(f"**Question:** {turn.user_question}")
                md.append("")
                ans = turn.assistant_answer
                md.append(f"**Answer:** {ans.get('answer_text', 'N/A')}")
                md.append(f"**Type:** {ans.get('question_type', 'unknown')}")
                md.append(f"**Confidence:** {ans.get('confidence', 0):.0%}")
                
                citations = ans.get("citations", [])
                if citations:
                    md.append("**Citations:**")
                    for c in citations:
                        md.append(f"- [{c.get('source_type', 'unknown')}] {c.get('identifier', 'N/A')}: {c.get('title', 'N/A')}")
                
                follow_ups = ans.get("follow_up_questions", [])
                if follow_ups:
                    md.append("**Follow-up Questions:**")
                    for f in follow_ups:
                        md.append(f"- {f}")
                
                md.append("---")
                md.append("")
            
            return "\n".join(md)
        
        return ""


class MemoryStore:
    """Persistent memory store for conversations."""
    
    def __init__(self, storage_dir: str | Path = ".geneai_memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._current_memory: ConversationMemory | None = None
        self._sessions: dict[str, Any] = {}
    
    def create_conversation(self) -> str:
        """Create a new conversation session and return ID."""
        mem = self.new_session()
        self._sessions[mem.session_id] = mem
        return mem.session_id

    def add_turn(self, conv_id: str, turn: Any) -> None:
        """Add a turn to a conversation session."""
        mem = self._sessions.get(conv_id)
        if mem is None:
            mem = ConversationMemory()
            mem.session_id = conv_id
            self._sessions[conv_id] = mem
        if hasattr(mem, "turns"):
            mem.turns.append(turn)
        else:
            setattr(mem, "turns", [turn])

    def get_history(self, conv_id: str) -> list[Any]:
        """Get history for a conversation session."""
        mem = self._sessions.get(conv_id)
        if mem is None:
            return []
        return getattr(mem, "turns", [])

    def get_context(self, conv_id: str, max_turns: int = 5) -> list[Any]:
        """Get recent context turns for a conversation session."""
        history = self.get_history(conv_id)
        return history[-max_turns:]
    
    def new_session(self) -> ConversationMemory:
        """Create a new conversation session."""
        self._current_memory = ConversationMemory()
        return self._current_memory
    
    def get_current(self) -> ConversationMemory:
        """Get current memory, creating if needed."""
        if self._current_memory is None:
            self._current_memory = self.new_session()
        return self._current_memory
    
    def save(self, memory: ConversationMemory | None = None) -> Path:
        """Save memory to disk."""
        memory = memory or self._current_memory
        if memory is None:
            raise ValueError("No memory to save")
        
        filepath = self.storage_dir / f"session_{memory.session_id}.json"
        with open(filepath, "w") as f:
            json.dump(memory.to_dict(), f, indent=2)
        
        logger.info(f"Saved session {memory.session_id} to {filepath}")
        return filepath
    
    def load(self, session_id: str) -> ConversationMemory:
        """Load memory from disk."""
        filepath = self.storage_dir / f"session_{session_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        
        with open(filepath) as f:
            data = json.load(f)
        
        memory = ConversationMemory.from_dict(data)
        self._current_memory = memory
        logger.info(f"Loaded session {session_id}")
        return memory
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions."""
        sessions = []
        for filepath in self.storage_dir.glob("session_*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "turns": len(data.get("turns", [])),
                    "filepath": str(filepath),
                })
            except Exception as e:
                logger.warning(f"Failed to read {filepath}: {e}")
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        filepath = self.storage_dir / f"session_{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            logger.info(f"Deleted session {session_id}")
            return True
        return False


# Global memory store
_memory_store: MemoryStore | None = None


def get_memory_store(storage_dir: str | Path = ".geneai_memory") -> MemoryStore:
    """Get global memory store."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore(storage_dir)
    return _memory_store


def get_current_memory() -> ConversationMemory:
    """Get current conversation memory."""
    return get_memory_store().get_current()


def new_conversation() -> ConversationMemory:
    """Start a new conversation."""
    return get_memory_store().new_session()


# Backward-compatibility aliases
ConversationMemoryManager = MemoryStore
get_memory_manager = get_memory_store