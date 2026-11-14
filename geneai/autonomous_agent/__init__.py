"""Autonomous Bioinformatics Agent package."""
from __future__ import annotations

# Core agent
from geneai.autonomous_agent.core import (
    AutonomousBioAgent,
    AgentConfig,
    ResearchResult,
    create_autonomous_agent,
)
from geneai.autonomous_agent.types import (
    AgentStatus,
    TaskStatus,
    TaskType,
    ApprovalStatus,
    ApprovalType,
)

# Planning
from geneai.autonomous_agent.planner import (
    Task,
    TaskPlan,
    TaskPlanner,
)

# Orchestration
from geneai.autonomous_agent.orchestrator import (
    ToolOrchestrator,
    TaskResult,
)

# Monitoring
from geneai.autonomous_agent.monitor import (
    WorkflowMonitor,
    TaskMetrics,
)

# Recovery
from geneai.autonomous_agent.recovery import (
    ErrorRecovery,
    RecoveryStrategy,
)

# Approval
from geneai.autonomous_agent.approval import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
)

# History
from geneai.autonomous_agent.history import (
    ExecutionHistory,
    HistoryEntry,
    HistoryQuery,
)

# Tools
from geneai.autonomous_agent.tools import (
    Tool,
    ToolSpec,
    ToolParameter,
    ToolRegistry,
    get_tool_registry,
    tool_registry,
)

# Memory
from geneai.autonomous_agent.memory import (
    AgentMemory,
    LongTermMemory,
    MemoryEntry,
    get_short_term_memory,
    get_long_term_memory,
)

# Prompts
from geneai.autonomous_agent.prompts import (
    SYSTEM_PROMPT,
    PLANNING_PROMPT,
    get_system_prompt,
    get_planning_prompt,
    get_tool_selection_prompt,
    get_interpretation_prompt,
    get_summary_prompt,
    get_error_recovery_prompt,
    get_approval_prompt,
)

# UI
from geneai.autonomous_agent.autonomous_agent_ui import render_autonomous_agent_ui

# Database
from geneai.autonomous_agent.database import (
    init_database,
    create_agent_session,
    get_agent_session,
    update_session_status,
    create_task_execution,
    update_task_execution,
    get_task_executions,
    create_approval_request,
    respond_to_approval,
    get_pending_approvals,
    get_approval_request,
    register_tool,
    get_registered_tools,
    get_execution_history,
    get_session_history,
)

__all__ = [
    # Core
    "AutonomousBioAgent",
    "AgentConfig",
    "AgentStatus",
    "ResearchResult",
    "TaskStatus",
    "create_autonomous_agent",
    # Planning
    "Task",
    "TaskPlan",
    "TaskPlanner",
    "TaskType",
    # Orchestration
    "ToolOrchestrator",
    "TaskResult",
    # Monitoring
    "WorkflowMonitor",
    "TaskMetrics",
    # Recovery
    "ErrorRecovery",
    "RecoveryStrategy",
    # Approval
    "ApprovalManager",
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalType",
    # History
    "ExecutionHistory",
    "HistoryEntry",
    "HistoryQuery",
    # Tools
    "Tool",
    "ToolSpec",
    "ToolParameter",
    "ToolRegistry",
    "get_tool_registry",
    "tool_registry",
    # Memory
    "AgentMemory",
    "LongTermMemory",
    "MemoryEntry",
    "get_short_term_memory",
    "get_long_term_memory",
    # Prompts
    "SYSTEM_PROMPT",
    "PLANNING_PROMPT",
    "get_system_prompt",
    "get_planning_prompt",
    "get_tool_selection_prompt",
    "get_interpretation_prompt",
    "get_summary_prompt",
    "get_error_recovery_prompt",
    "get_approval_prompt",
    # UI
    "render_autonomous_agent_ui",
    # Database
    "init_database",
    "create_agent_session",
    "get_agent_session",
    "update_session_status",
    "create_task_execution",
    "update_task_execution",
    "get_task_executions",
    "create_approval_request",
    "respond_to_approval",
    "get_pending_approvals",
    "get_approval_request",
    "register_tool",
    "get_registered_tools",
    "get_execution_history",
    "get_session_history",
]