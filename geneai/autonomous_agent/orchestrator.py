"""Tool orchestration module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from geneai.autonomous_agent.planner import Task, TaskPlan
from geneai.autonomous_agent.types import TaskStatus
from geneai.autonomous_agent.tools import ToolRegistry, Tool
from geneai.autonomous_agent.recovery import ErrorRecovery
from geneai.autonomous_agent.monitor import WorkflowMonitor
from geneai.autonomous_agent.database import (
    create_task_execution,
    update_task_execution,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_id: str
    task_name: str
    tool_name: str | None
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_time_seconds: float = 0.0
    retry_count: int = 0
    execution_id: str | None = None
    started_at: float = field(default_factory=lambda: __import__('time').time())
    completed_at: float | None = None


class ToolOrchestrator:
    """
    Execute task plans with proper tool selection and concurrency control.
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self.logger = logging.getLogger(__name__)

    def execute_plan(
        self,
        plan: TaskPlan,
        tools: ToolRegistry,
        recovery: ErrorRecovery,
        monitor: WorkflowMonitor,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a task plan.

        Args:
            plan: TaskPlan to execute
            tools: Registry of available tools
            recovery: Error recovery handler
            monitor: Workflow monitor for tracking progress
            session_id: Agent session that owns this plan (defaults to plan.session_id)

        Returns:
            List of task results
        """
        session_id = session_id or getattr(plan, "session_id", "") or ""
        self.logger.info("Executing plan %s with %d tasks", plan.plan_id, len(plan.tasks))

        # Get topological order
        ordered_tasks = plan.topological_sort()
        completed_tasks: set[str] = set()
        task_results: dict[str, TaskResult] = {}
        futures = {}
        scheduled: set[str] = set()

        # Submit initial ready tasks
        ready_tasks = plan.get_ready_tasks(completed_tasks)
        for task in ready_tasks[:self.max_concurrent]:
            future = self.executor.submit(
                self._execute_task,
                task,
                tools,
                recovery,
                monitor,
                task_results,
                session_id,
            )
            futures[future] = task
            scheduled.add(task.task_id)

        # Process completions
        while futures:
            done, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)

            for future in done:
                task = futures.pop(future)
                try:
                    result = future.result()
                    task_results[task.task_id] = result
                    completed_tasks.add(task.task_id)

                    # Update database
                    try:
                        update_task_execution(
                            execution_id=result.execution_id or result.task_id,
                            status=result.status.value,
                            result=result.result,
                            error_message=result.error,
                            retry_count=result.retry_count,
                        )
                    except Exception:
                        self.logger.warning(
                            "Could not persist execution for task %s", task.task_id, exc_info=True
                        )

                    # Notify monitor
                    monitor.record_completion(task.task_id, result)

                    # Submit newly ready tasks
                    ready_tasks = plan.get_ready_tasks(completed_tasks)
                    for new_task in ready_tasks:
                        if new_task.task_id in scheduled:
                            continue
                        if len(futures) < self.max_concurrent:
                            future = self.executor.submit(
                                self._execute_task,
                                new_task,
                                tools,
                                recovery,
                                monitor,
                                task_results,
                                session_id,
                            )
                            futures[future] = new_task
                            scheduled.add(new_task.task_id)

                except Exception as e:
                    self.logger.exception("Task %s failed with exception", task.task_id)
                    error_result = TaskResult(
                        task_id=task.task_id,
                        task_name=task.name,
                        tool_name=task.tool_name,
                        status=TaskStatus.FAILED,
                        error=str(e),
                    )
                    task_results[task.task_id] = error_result
                    completed_tasks.add(task.task_id)

        # Convert to list of dicts
        results = []
        for task in plan.tasks:
            result = task_results.get(task.task_id)
            if result:
                results.append({
                    "task_id": result.task_id,
                    "task_name": result.task_name,
                    "tool_name": result.tool_name,
                    "status": result.status.value,
                    "result": result.result,
                    "error": result.error,
                    "execution_time_seconds": result.execution_time_seconds,
                    "retry_count": result.retry_count,
                })
            else:
                results.append({
                    "task_id": task.task_id,
                    "task_name": task.name,
                    "tool_name": task.tool_name,
                    "status": TaskStatus.SKIPPED.value,
                    "error": "Not executed",
                })

        self.logger.info("Plan %s completed with %d results", plan.plan_id, len(results))
        return results

    def _execute_task(
        self,
        task: Task,
        tools: ToolRegistry,
        recovery: ErrorRecovery,
        monitor: WorkflowMonitor,
        previous_results: dict[str, TaskResult],
        session_id: str = "",
    ) -> TaskResult:
        """Execute a single task with retries."""
        start_time = time.time()
        execution_id = str(uuid.uuid4())

        # Create execution record (best effort: never block execution on persistence)
        try:
            create_task_execution(
                execution_id=execution_id,
                session_id=session_id,
                task_id=task.task_id,
                task_name=task.name,
                tool_name=task.tool_name,
                tool_params=task.parameters,
            )
        except Exception:
            self.logger.warning(
                "Could not create execution record for task %s", task.task_id, exc_info=True
            )

        monitor.record_start(task.task_id)

        # Get tool
        tool = tools.get(task.tool_name) if task.tool_name else None
        if not tool:
            return TaskResult(
                task_id=task.task_id,
                task_name=task.name,
                tool_name=task.tool_name,
                status=TaskStatus.FAILED,
                error=f"Tool not found: {task.tool_name}",
                execution_id=execution_id,
                execution_time_seconds=time.time() - start_time,
            )

        # Prepare parameters with context from previous results
        params = self._prepare_parameters(task, previous_results)

        # Execute with retry
        last_error = None
        for attempt in range(task.max_retries + 1):
            task.retry_count = attempt
            try:
                self.logger.info("Executing task %s (attempt %d/%d)", task.name, attempt + 1, task.max_retries + 1)

                result = tool.execute(**params)

                execution_time = time.time() - start_time
                return TaskResult(
                    task_id=task.task_id,
                    task_name=task.name,
                    tool_name=task.tool_name,
                    status=TaskStatus.COMPLETED,
                    result=result,
                    execution_time_seconds=execution_time,
                    retry_count=attempt,
                    execution_id=execution_id,
                    completed_at=time.time(),
                )

            except Exception as e:
                last_error = e
                self.logger.warning("Task %s attempt %d failed: %s", task.name, attempt + 1, e)

                if attempt < task.max_retries:
                    # Apply recovery strategy
                    delay = recovery.get_backoff(attempt)
                    self.logger.info("Retrying in %.1f seconds", delay)
                    time.sleep(delay)
                    # Could modify params based on recovery
                    params = recovery.adjust_parameters(params, e, attempt)
                else:
                    break

        # All retries exhausted
        execution_time = time.time() - start_time
        return TaskResult(
            task_id=task.task_id,
            task_name=task.name,
            tool_name=task.tool_name,
            status=TaskStatus.FAILED,
            error=str(last_error),
            execution_time_seconds=execution_time,
            retry_count=task.max_retries,
            execution_id=execution_id,
            completed_at=time.time(),
        )

    def _prepare_parameters(
        self,
        task: Task,
        previous_results: dict[str, TaskResult],
    ) -> dict[str, Any]:
        """Prepare tool parameters, injecting context from previous results."""
        params = task.parameters.copy()

        # Inject common context
        params.setdefault("context", {})

        # Add results from dependency tasks
        for dep_id in task.dependencies:
            dep_result = previous_results.get(dep_id)
            if dep_result and dep_result.result:
                params["context"][f"dep_{dep_id}"] = dep_result.result

        return params

    def shutdown(self) -> None:
        """Shutdown the executor."""
        self.executor.shutdown(wait=True)