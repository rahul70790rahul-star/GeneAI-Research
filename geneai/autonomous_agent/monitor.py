"""Workflow monitoring module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskMetrics:
    """Metrics for a single task."""
    task_id: str
    task_name: str
    tool_name: str | None
    status: str = "pending"
    start_time: float | None = None
    end_time: float | None = None
    duration_seconds: float = 0.0
    retry_count: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowMonitor:
    """
    Monitor workflow execution in real-time.

    Provides:
    - Task progress tracking
    - Performance metrics
    - Anomaly detection
    - Alerting
    """

    def __init__(self):
        self.metrics: dict[str, TaskMetrics] = {}
        self.session_metrics: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def record_start(self, task_id: str, task_name: str = "", tool_name: str | None = None) -> None:
        """Record task start."""
        with self._lock:
            if task_id not in self.metrics:
                self.metrics[task_id] = TaskMetrics(
                    task_id=task_id,
                    task_name=task_name,
                    tool_name=tool_name,
                )
            self.metrics[task_id].status = "running"
            self.metrics[task_id].start_time = time.time()
            self.logger.debug("Task %s started", task_id)

    def record_completion(
        self,
        task_id: str,
        result: Any,  # TaskResult
    ) -> None:
        """Record task completion."""
        with self._lock:
            if task_id in self.metrics:
                m = self.metrics[task_id]
                m.status = result.status.value if hasattr(result.status, 'value') else str(result.status)
                m.end_time = time.time()
                if m.start_time:
                    m.duration_seconds = m.end_time - m.start_time
                m.retry_count = result.retry_count if hasattr(result, 'retry_count') else 0
                m.error = result.error if hasattr(result, 'error') else None
                self.logger.debug("Task %s completed with status %s", task_id, m.status)

    def record_session_start(self, session_id: str, question: str) -> None:
        """Record session start."""
        with self._lock:
            self.session_metrics[session_id] = {
                "question": question,
                "start_time": time.time(),
                "tasks_total": 0,
                "tasks_completed": 0,
                "tasks_failed": 0,
                "current_status": "planning",
            }

    def record_session_update(
        self,
        session_id: str,
        tasks_total: int | None = None,
        tasks_completed: int | None = None,
        tasks_failed: int | None = None,
        status: str | None = None,
    ) -> None:
        """Update session metrics."""
        with self._lock:
            if session_id in self.session_metrics:
                m = self.session_metrics[session_id]
                if tasks_total is not None:
                    m["tasks_total"] = tasks_total
                if tasks_completed is not None:
                    m["tasks_completed"] = tasks_completed
                if tasks_failed is not None:
                    m["tasks_failed"] = tasks_failed
                if status is not None:
                    m["current_status"] = status

    def get_task_metrics(self, task_id: str) -> TaskMetrics | None:
        """Get metrics for a task."""
        with self._lock:
            return self.metrics.get(task_id)

    def get_session_metrics(self, session_id: str) -> dict[str, Any] | None:
        """Get metrics for a session."""
        with self._lock:
            return self.session_metrics.get(session_id)

    def get_all_metrics(self) -> dict[str, TaskMetrics]:
        """Get all task metrics."""
        with self._lock:
            return self.metrics.copy()

    def get_running_tasks(self) -> list[TaskMetrics]:
        """Get currently running tasks."""
        with self._lock:
            return [m for m in self.metrics.values() if m.status == "running"]

    def get_failed_tasks(self) -> list[TaskMetrics]:
        """Get failed tasks."""
        with self._lock:
            return [m for m in self.metrics.values() if m.status == "failed"]

    def check_anomalies(self) -> list[dict[str, Any]]:
        """Check for anomalies in execution."""
        anomalies = []
        with self._lock:
            for task_id, metrics in self.metrics.items():
                # Long running tasks
                if metrics.status == "running" and metrics.start_time:
                    elapsed = time.time() - metrics.start_time
                    if elapsed > 300:  # 5 minutes
                        anomalies.append({
                            "type": "long_running",
                            "task_id": task_id,
                            "elapsed_seconds": elapsed,
                            "message": f"Task running for {elapsed:.0f}s",
                        })

                # High retry count
                if metrics.retry_count > 3:
                    anomalies.append({
                        "type": "high_retries",
                        "task_id": task_id,
                        "retry_count": metrics.retry_count,
                        "message": f"Task retried {metrics.retry_count} times",
                    })

                # Repeated failures
                if metrics.status == "failed" and metrics.retry_count >= 3:
                    anomalies.append({
                        "type": "repeated_failure",
                        "task_id": task_id,
                        "error": metrics.error,
                        "message": f"Task failed after {metrics.retry_count} retries",
                    })

        return anomalies

    def get_summary(self) -> dict[str, Any]:
        """Get monitoring summary."""
        with self._lock:
            total = len(self.metrics)
            completed = sum(1 for m in self.metrics.values() if m.status == "completed")
            failed = sum(1 for m in self.metrics.values() if m.status == "failed")
            running = sum(1 for m in self.metrics.values() if m.status == "running")
            pending = sum(1 for m in self.metrics.values() if m.status == "pending")

            avg_duration = 0.0
            durations = [m.duration_seconds for m in self.metrics.values() if m.duration_seconds > 0]
            if durations:
                avg_duration = sum(durations) / len(durations)

            return {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": pending,
                "success_rate": completed / total if total > 0 else 0,
                "average_duration_seconds": avg_duration,
                "anomalies": self.check_anomalies(),
            }