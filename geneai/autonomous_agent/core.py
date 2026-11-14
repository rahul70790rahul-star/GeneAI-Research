"""Core data structures and main agent class for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from geneai.autonomous_agent.database import (
    create_agent_session,
    update_session_status,
    get_agent_session,
    create_task_execution,
    update_task_execution,
    get_task_executions,
    create_approval_request,
    respond_to_approval,
    get_pending_approvals,
    register_tool,
    get_registered_tools,
    initialize_autonomous_database,
)

logger = logging.getLogger(__name__)
from geneai.autonomous_agent.planner import TaskPlanner, Task, TaskPlan
from geneai.autonomous_agent.orchestrator import ToolOrchestrator
from geneai.autonomous_agent.monitor import WorkflowMonitor
from geneai.autonomous_agent.recovery import ErrorRecovery
from geneai.autonomous_agent.approval import ApprovalManager
from geneai.autonomous_agent.history import ExecutionHistory
from geneai.autonomous_agent.memory import AgentMemory
from geneai.autonomous_agent.tools import ToolRegistry
from geneai.autonomous_agent.types import AgentStatus, TaskStatus


@dataclass
class AgentConfig:
    """Configuration for the autonomous agent."""
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    retry_backoff_max: float = 60.0
    approval_timeout_hours: int = 24
    max_concurrent_tasks: int = 3
    default_llm_model: str = "gpt-4"
    enable_memory: bool = True
    memory_max_turns: int = 20


@dataclass
class ResearchResult:
    """Result of a research question processing."""
    session_id: str
    question: str
    status: AgentStatus
    task_plan: TaskPlan | None = None
    task_results: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    execution_time_seconds: float = 0.0


class AutonomousBioAgent:
    """
    Main autonomous agent for bioinformatics research.

    Capabilities:
    - Understand research questions
    - Select appropriate analysis tools
    - Execute bioinformatics pipelines
    - Analyze results
    - Identify missing information
    - Generate research summaries
    - Track workflow execution
    """

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self.planner = TaskPlanner()
        self.orchestrator = ToolOrchestrator(max_concurrent=self.config.max_concurrent_tasks)
        self.monitor = WorkflowMonitor()
        self.recovery = ErrorRecovery(
            max_retries=self.config.max_retries,
            backoff_base=self.config.retry_backoff_base,
            backoff_max=self.config.retry_backoff_max,
        )
        self.approval = ApprovalManager(timeout_hours=self.config.approval_timeout_hours)
        self.history = ExecutionHistory()
        self.memory = AgentMemory(max_turns=self.config.memory_max_turns) if self.config.enable_memory else None
        self.tools = ToolRegistry()

        # Initialize database
        initialize_autonomous_database()

        # Register built-in tools
        self._register_builtin_tools()

        logger.info("AutonomousBioAgent initialized with config: %s", self.config)

    def _register_builtin_tools(self) -> None:
        """Register built-in bioinformatics tools."""
        # These will be populated by tool wrappers
        from geneai.autonomous_agent.tools.sequence_tools import register_sequence_tools
        from geneai.autonomous_agent.tools.variant_tools import register_variant_tools
        from geneai.autonomous_agent.tools.literature_tools import register_literature_tools
        from geneai.autonomous_agent.tools.admet_tools import register_admet_tools
        from geneai.autonomous_agent.tools.docking_tools import register_docking_tools
        from geneai.autonomous_agent.tools.analysis_tools import register_analysis_tools
        from geneai.autonomous_agent.tools.disease_tools import register_disease_tools

        register_sequence_tools(self.tools)
        register_variant_tools(self.tools)
        register_literature_tools(self.tools)
        register_admet_tools(self.tools)
        register_docking_tools(self.tools)
        register_analysis_tools(self.tools)
        register_disease_tools(self.tools)

        # Persist to database
        for tool_name, tool in self.tools.tools.items():
            register_tool(
                tool_name=tool_name,
                description=tool.description,
                category=tool.category,
                parameters=tool.parameters_schema,
                requires_approval=tool.requires_approval,
            )

    def process_question(self, question: str, user_id: str | None = None) -> ResearchResult:
        """
        Process a natural language research question.

        Args:
            question: Research question in natural language
            user_id: Optional user identifier

        Returns:
            ResearchResult with execution details and summary
        """
        session_id = str(uuid.uuid4())
        start_time = datetime.now()

        logger.info("Processing question for session %s: %s", session_id, question[:100])

        # Create session
        create_agent_session(session_id, user_id, question)

        try:
            # Step 1: Decompose question into tasks
            update_session_status(session_id, AgentStatus.PLANNING.value)
            task_plan = self.planner.decompose(question)

            # Store plan in history
            self.history.record_plan(session_id, task_plan)

            # Step 2: Check for required approvals
            approval_tasks = [t for t in task_plan.tasks if t.requires_approval]
            if approval_tasks:
                update_session_status(session_id, AgentStatus.AWAITING_APPROVAL.value)
                approval_ids: dict[str, str] = {}
                for task in approval_tasks:
                    approval_id = str(uuid.uuid4())
                    create_approval_request(
                        approval_id=approval_id,
                        session_id=session_id,
                        task_id=task.task_id,
                        request_type="tool_execution",
                        description=f"Execute {task.name} with tool {task.tool_name}: {task.description}",
                    )
                    approval_ids[task.task_id] = approval_id
                # In real implementation, would wait for approvals
                # For now, auto-approve for demo
                for task in approval_tasks:
                    respond_to_approval(approval_ids[task.task_id], "approved", "system")

            # Step 3: Execute tasks
            update_session_status(session_id, AgentStatus.RUNNING.value)
            task_plan.session_id = session_id
            task_results = self.orchestrator.execute_plan(task_plan, self.tools, self.recovery, self.monitor)

            # Record results
            for result in task_results:
                self.history.record_task_result(session_id, result)

            # Step 4: Generate summary
            summary = self._generate_summary(question, task_plan, task_results)

            # Step 5: Update session
            update_session_status(
                session_id,
                AgentStatus.COMPLETED.value,
                result_summary=summary,
            )

            completed_at = datetime.now()
            execution_time = (completed_at - start_time).total_seconds()

            return ResearchResult(
                session_id=session_id,
                question=question,
                status=AgentStatus.COMPLETED,
                task_plan=task_plan,
                task_results=task_results,
                summary=summary,
                completed_at=completed_at,
                execution_time_seconds=execution_time,
            )

        except Exception as e:
            logger.exception("Error processing question for session %s", session_id)
            update_session_status(
                session_id,
                AgentStatus.FAILED.value,
                error_message=str(e),
            )
            return ResearchResult(
                session_id=session_id,
                question=question,
                status=AgentStatus.FAILED,
                error_message=str(e),
                completed_at=datetime.now(),
                execution_time_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _generate_summary(
        self,
        question: str,
        task_plan: TaskPlan,
        task_results: list[dict[str, Any]],
    ) -> str:
        """Generate a research summary from task results."""
        successful = [r for r in task_results if r.get("status") == "completed"]
        failed = [r for r in task_results if r.get("status") == "failed"]

        summary_parts = [
            f"# Research Summary",
            f"**Question:** {question}",
            f"**Tasks Executed:** {len(task_results)} ({len(successful)} successful, {len(failed)} failed)",
            "",
        ]

        if task_plan and task_plan.tasks:
            summary_parts.append("## Task Plan")
            for i, task in enumerate(task_plan.tasks, 1):
                result = next((r for r in task_results if r.get("task_id") == task.task_id), None)
                status = result.get("status", "unknown") if result else "not_executed"
                summary_parts.append(f"{i}. **{task.name}** ({task.tool_name}) - {status}")
            summary_parts.append("")

        if successful:
            summary_parts.append("## Key Results")
            for result in successful:
                summary_parts.append(f"- **{result.get('task_name', 'Task')}**: {result.get('summary', 'Completed')}")
            summary_parts.append("")

        if failed:
            summary_parts.append("## Failed Tasks")
            for result in failed:
                summary_parts.append(f"- **{result.get('task_name', 'Task')}**: {result.get('error', 'Unknown error')}")
            summary_parts.append("")

        # Add memory context if available
        if self.memory:
            context = self.memory.get_context()
            if context:
                summary_parts.append("## Conversation Context")
                summary_parts.append(context)

        return "\n".join(summary_parts)

    def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        """Get current session status."""
        session = get_agent_session(session_id)
        if not session:
            return None

        executions = get_task_executions(session_id)
        approvals = get_pending_approvals(session_id)

        return {
            "session": session,
            "executions": executions,
            "pending_approvals": approvals,
        }

    def wait_for_approval(self, session_id: str, approval_id: str, response: str, responder_id: str) -> bool:
        """Process approval response."""
        success = respond_to_approval(approval_id, response, responder_id)
        if success:
            # Check if all approvals for session are complete
            pending = get_pending_approvals(session_id)
            if not pending:
                # Resume execution - in real implementation, would trigger orchestrator resume
                pass
        return success

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a running session."""
        session = get_agent_session(session_id)
        if not session:
            return False

        if session["status"] in ("completed", "failed", "cancelled"):
            return False

        update_session_status(session_id, AgentStatus.CANCELLED.value)
        return True


def create_autonomous_agent(config: AgentConfig | None = None) -> AutonomousBioAgent:
    """Factory function to create an autonomous agent."""
    return AutonomousBioAgent(config)