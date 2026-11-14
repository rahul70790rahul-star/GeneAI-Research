"""Intelligent Research Automation - Phase 5.4 Core.

The engine runs ordered, dependency-aware research pipelines made of small
step executors. Every executor performs real work (local knowledge database
queries, RDKit-based ADMET prediction, report rendering, file export, or an
explicitly requested live lookup); nothing is fabricated.

Live network access is opt-in per step (``"live": True``) so that automated
pipelines remain usable offline and against the locally cached knowledge base.
"""
from __future__ import annotations

import csv
import inspect
import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from croniter import croniter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations and data classes
# ---------------------------------------------------------------------------
class AutomationStatus(Enum):
    """Status of an automation task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class TriggerType(Enum):
    """Types of triggers for automation.

    ``SCHEDULE``/``EVENT`` are the historical spellings; ``SCHEDULED`` and
    ``EVENT_DRIVEN`` are the canonical names used by the dashboard API.
    """

    MANUAL = "manual"
    SCHEDULE = "schedule"
    SCHEDULED = "scheduled"
    EVENT = "event"
    EVENT_DRIVEN = "event_driven"
    WEBHOOK = "webhook"
    API = "api"


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _now() -> str:
    return datetime.now().isoformat()


@dataclass
class AutomationTask:
    """An automated research task."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    trigger_type: TriggerType = TriggerType.MANUAL
    schedule: str = ""  # cron expression for schedule triggers
    event_type: str = ""  # for event triggers
    webhook_url: str = ""  # for webhook triggers
    steps: list[dict[str, Any]] = field(default_factory=list)
    status: AutomationStatus = AutomationStatus.PENDING
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "schedule": self.schedule,
            "event_type": self.event_type,
            "webhook_url": self.webhook_url,
            "steps": self.steps,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "context": self.context,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutomationTask":
        try:
            trigger = TriggerType(data.get("trigger_type", "manual"))
        except ValueError:
            trigger = TriggerType.MANUAL
        try:
            status = AutomationStatus(data.get("status", "pending"))
        except ValueError:
            status = AutomationStatus.PENDING
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            trigger_type=trigger,
            schedule=data.get("schedule", ""),
            event_type=data.get("event_type", ""),
            webhook_url=data.get("webhook_url", ""),
            steps=data.get("steps", []),
            status=status,
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            last_run=data.get("last_run"),
            next_run=data.get("next_run"),
            run_count=int(data.get("run_count", 0) or 0),
            success_count=int(data.get("success_count", 0) or 0),
            failure_count=int(data.get("failure_count", 0) or 0),
            last_error=data.get("last_error"),
            context=data.get("context", {}) or {},
            tags=data.get("tags", []) or [],
        )


@dataclass
class TaskExecution:
    """Record of a task execution.

    ``step_results`` is the keyed mapping used by the API. ``steps_results``
    preserves the ordered list consumed by the Streamlit dashboard.
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    status: AutomationStatus = AutomationStatus.RUNNING
    # ISO-8601 strings so the dashboard can slice/parse them directly. A
    # ``datetime`` passed by a caller is still accepted via ``_iso`` below.
    started_at: datetime | str = field(default_factory=_now)
    completed_at: datetime | str | None = None
    current_step: str | None = None
    step_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

    @property
    def steps_results(self) -> list[dict[str, Any]]:
        """Ordered step results (dashboard compatibility)."""
        return sorted(
            self.step_results.values(),
            key=lambda item: item.get("step_index", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "current_step": self.current_step,
            "step_results": self.step_results,
            "steps_results": self.steps_results,
            "error": self.error,
            "output": self.output,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _render_template(text: str, context: dict[str, Any]) -> str:
    """Replace ``{{key}}`` placeholders with values from ``context``."""
    import re

    def replace(match: "re.Match[str]") -> str:
        key = match.group(1).strip()
        if key not in context:
            return match.group(0)
        value = context[key]
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, default=str)

    return re.sub(r"\{\{([^{}]+)\}\}", replace, text)


def _executor_accepts_context(executor: "StepExecutor") -> bool:
    try:
        signature = inspect.signature(executor.execute)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return True
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2


def _export_directory() -> Path:
    try:
        from geneai.config import DATA_DIR

        directory = Path(DATA_DIR) / "exports"
    except Exception:  # pragma: no cover - configuration is always available
        directory = Path("exports")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------
class StepExecutor(ABC):
    """Base class for step executors.

    Subclasses may implement either ``get_step_type()`` or a ``step_type``
    property. ``execute`` receives the step parameters and an optional shared
    execution context; executors that only accept one argument are supported.
    """

    @property
    def step_type(self) -> str:
        return self.get_step_type()

    def get_step_type(self) -> str:
        name = self.__class__.__name__
        if name.endswith("Step") and len(name) > 4:
            name = name[:-4]
        return name.lower()

    @abstractmethod
    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a step and return its result."""
        raise NotImplementedError


def _local_knowledge_db():
    try:
        from geneai.unified_knowledge import get_knowledge_db

        return get_knowledge_db()
    except Exception:  # pragma: no cover - optional local cache
        logger.debug("Local knowledge database unavailable", exc_info=True)
        return None


class GeneAnalysisStep(StepExecutor):
    """Annotate a gene symbol or identify genes associated with a disease."""

    def get_step_type(self) -> str:
        return "gene_analysis"

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        symbol = str(
            step.get("gene_symbol")
            or step.get("symbol")
            or step.get("gene")
            or context.get("gene_symbol")
            or ""
        ).strip().upper()

        if symbol:
            info: dict[str, Any] = {"symbol": symbol}
            db = _local_knowledge_db()
            if db is not None:
                try:
                    record = db.get_gene_by_symbol(symbol)
                except Exception:
                    record = None
                if record:
                    for key in (
                        "name",
                        "description",
                        "chromosome",
                        "ensembl_id",
                        "entrez_id",
                        "biotype",
                        "uniprot_ids",
                    ):
                        value = record.get(key)
                        if value:
                            info[key] = value
                    info["source"] = "local_knowledge_db"
                else:
                    info["source"] = "requested_symbol"
            else:
                info["source"] = "requested_symbol"
            info["annotated"] = bool(info.get("name") or info.get("description"))
            return {"gene_info": info, "gene_symbol": symbol}

        disease = str(step.get("disease") or context.get("disease") or "").strip()
        if not disease:
            raise ValueError("No gene symbol or disease specified for gene analysis")

        from geneai.drug_discovery.gene_identification import identify_disease_genes

        limit = int(step.get("limit", 20))
        genes = identify_disease_genes(disease, limit=limit)
        return {"genes": genes, "count": len(genes), "disease": disease}


class DrugSearchStep(StepExecutor):
    """Search drugs by name, target or disease.

    The local knowledge database is queried by default. Set ``"live": True`` to
    fall back to the multi-database clients when the local cache has no match.
    """

    def get_step_type(self) -> str:
        return "drug_search"

    @staticmethod
    def _local_search(search_type: str, query: str, limit: int) -> list[dict[str, Any]]:
        db = _local_knowledge_db()
        if db is None:
            return []
        pattern = f"%{query}%"
        try:
            if search_type == "name":
                rows = db.fetchall(
                    "SELECT * FROM drugs WHERE name LIKE ? ORDER BY name LIMIT ?",
                    (pattern, limit),
                )
            elif search_type == "target":
                rows = db.fetchall(
                    """SELECT DISTINCT d.* FROM drugs d
                       JOIN drug_targets dt ON dt.drug_id = d.id
                       WHERE dt.target_uniprot LIKE ? OR dt.target_name LIKE ?
                       LIMIT ?""",
                    (pattern, pattern, limit),
                )
            else:
                rows = db.fetchall(
                    """SELECT DISTINCT * FROM drugs
                       WHERE indications LIKE ? OR therapeutic_area LIKE ? OR name LIKE ?
                       LIMIT ?""",
                    (pattern, pattern, pattern, limit),
                )
        except Exception:
            logger.warning("Local drug search failed", exc_info=True)
            return []
        return [dict(row) for row in rows]

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        search_type = str(step.get("search_type", "disease"))
        query = str(step.get("query") or context.get("disease") or "").strip()
        limit = int(step.get("limit", 20))
        if not query:
            raise ValueError("No query provided for drug search")

        drugs = self._local_search(search_type, query, limit)
        source = "local_knowledge_db"
        error: str | None = None

        if not drugs and step.get("live", False):
            try:
                from geneai.drug_discovery.drug_search import (
                    search_drugs_by_disease,
                    search_drugs_by_name,
                    search_drugs_by_target,
                )

                if search_type == "target":
                    drugs = search_drugs_by_target(query, limit=limit)
                elif search_type == "name":
                    drugs = search_drugs_by_name(query, limit=limit)
                elif search_type == "disease":
                    drugs = search_drugs_by_disease(query, limit=limit)
                else:
                    raise ValueError(f"Unknown search type: {search_type}")
                source = "live"
            except Exception as exc:
                error = str(exc)
                logger.warning("Live drug search failed: %s", exc, exc_info=True)
                drugs = []

        result = {
            "drugs": drugs,
            "count": len(drugs),
            "search_type": search_type,
            "query": query,
            "source": source,
        }
        if error:
            result["error"] = error
        return result


class ADMETStep(StepExecutor):
    """Predict ADMET properties with the real RDKit-based engine."""

    def get_step_type(self) -> str:
        return "admet"

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        import dataclasses

        context = context or {}
        smiles = str(step.get("smiles") or context.get("smiles") or "").strip()
        if not smiles:
            raise ValueError("No SMILES provided for ADMET prediction")

        from geneai.admet_prediction.admet_engine import predict_admet

        result = predict_admet(smiles)
        if dataclasses.is_dataclass(result):
            payload = dataclasses.asdict(result)
        elif isinstance(result, dict):
            payload = result
        elif hasattr(result, "to_dict"):
            payload = result.to_dict()
        else:  # pragma: no cover - defensive
            payload = {"result": result}

        predictions = payload.get("predictions") if isinstance(payload, dict) else None
        if not predictions:
            predictions = [payload]
        return {
            "predictions": predictions,
            "admet": payload,
            "smiles": smiles,
        }


class LiteratureSearchStep(StepExecutor):
    """Search the local literature cache, optionally PubMed."""

    def get_step_type(self) -> str:
        return "literature_search"

    @staticmethod
    def _local_search(query: str, limit: int) -> list[dict[str, Any]]:
        db = _local_knowledge_db()
        if db is None:
            return []
        pattern = f"%{query}%"
        try:
            rows = db.fetchall(
                """SELECT * FROM literature
                   WHERE title LIKE ? OR abstract LIKE ?
                   ORDER BY year DESC LIMIT ?""",
                (pattern, pattern, limit),
            )
        except Exception:
            logger.warning("Local literature search failed", exc_info=True)
            return []
        return [dict(row) for row in rows]

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        query = str(step.get("query") or context.get("disease") or "").strip()
        limit = int(step.get("max_results", step.get("limit", 10)))
        if not query:
            raise ValueError("No query provided for literature search")

        articles = self._local_search(query, limit)
        source = "local_knowledge_db"
        error: str | None = None

        if not articles and step.get("live", False):
            try:
                from geneai.research import search_pubmed

                articles = search_pubmed(query, limit)
                source = "PubMed"
            except Exception as exc:
                error = str(exc)
                logger.warning("PubMed search failed: %s", exc, exc_info=True)
                articles = []

        result = {
            "articles": articles,
            "papers": articles,
            "count": len(articles),
            "query": query,
            "source": source,
        }
        if error:
            result["error"] = error
        return result


class ReportGenerationStep(StepExecutor):
    """Render a provenance-aware research report."""

    def get_step_type(self) -> str:
        return "report_generation"

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        title = str(
            step.get("title") or context.get("title") or "Automated Research Report"
        )
        method = str(
            step.get("method") or "Automated analysis using the GeneAI Research platform"
        )
        limitations = str(
            step.get("limitations") or "Automated analysis requires expert review"
        )
        sections = step.get("sections") or []

        rendered_sections: list[dict[str, str]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            rendered_sections.append(
                {
                    "title": str(section.get("title", "Results")),
                    "content": _render_template(str(section.get("content", "")), context),
                }
            )

        if rendered_sections:
            results_text = "\n\n".join(
                f"### {section['title']}\n\n{section['content']}"
                for section in rendered_sections
            )
        else:
            results_text = json.dumps(context, indent=2, default=str)

        from geneai.report import build_report

        report = build_report(title, method, results_text, limitations)
        return {
            "report": report,
            "title": title,
            "format": step.get("format", "markdown"),
            "sections": rendered_sections,
        }


class NotificationStep(StepExecutor):
    """Deliver a notification through a webhook or the application log."""

    def get_step_type(self) -> str:
        return "notification"

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        message = str(step.get("message") or context.get("message") or "Automation task completed")
        subject = str(step.get("subject", ""))
        recipients = step.get("recipients") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        recipients = list(recipients)

        notification_type = str(step.get("type", "log")).lower()
        webhook_url = str(step.get("webhook_url", ""))

        if notification_type == "webhook" and webhook_url:
            import requests

            try:
                response = requests.post(
                    webhook_url,
                    json={
                        "subject": subject,
                        "message": message,
                        "context": context,
                    },
                    timeout=10,
                )
                response.raise_for_status()
                return {
                    "sent": True,
                    "recipient_count": len(recipients) or 1,
                    "channel": "webhook",
                    "status_code": response.status_code,
                }
            except Exception as exc:
                logger.error("Webhook notification failed: %s", exc)
                return {
                    "sent": False,
                    "recipient_count": len(recipients),
                    "channel": "webhook",
                    "error": str(exc),
                }

        # Log delivery is a real, inspectable channel (no credentials required).
        logger.info(
            "Notification%s: %s%s",
            f" to {', '.join(recipients)}" if recipients else "",
            subject + ": " if subject else "",
            message,
        )
        return {
            "sent": True,
            "recipient_count": len(recipients),
            "channel": "log",
            "subject": subject,
            "message": message,
        }


class DataExportStep(StepExecutor):
    """Export step data to CSV, JSON or Excel."""

    def get_step_type(self) -> str:
        return "data_export"

    def execute(
        self, step: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        data = step.get("data")
        if data is None:
            data_key = step.get("data_key", "results")
            data = context.get(data_key, context)

        export_format = str(step.get("format", "json")).lower()
        extension = {"csv": "csv", "json": "json", "excel": "xlsx", "xlsx": "xlsx"}.get(
            export_format, export_format
        )
        filename = step.get("filename") or step.get("filepath")
        if filename:
            filepath = Path(str(filename))
            if not filepath.is_absolute():
                filepath = _export_directory() / filepath
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = _export_directory() / f"export_{stamp}.{extension}"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        record_count = len(data) if isinstance(data, (list, tuple, dict)) else 1

        if export_format == "json":
            with filepath.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)
        elif export_format == "csv":
            if not isinstance(data, list):
                raise ValueError("CSV export requires list data")
            fieldnames: list[str] = []
            for record in data:
                if isinstance(record, dict):
                    for key in record:
                        if key not in fieldnames:
                            fieldnames.append(key)
            with filepath.open("w", encoding="utf-8", newline="") as handle:
                if fieldnames:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    for record in data:
                        writer.writerow(
                            {
                                key: json.dumps(value, default=str)
                                if isinstance(value, (dict, list))
                                else value
                                for key, value in (record or {}).items()
                            }
                        )
                else:
                    writer = csv.writer(handle)
                    writer.writerows(data)
        elif export_format in ("excel", "xlsx"):
            import pandas as pd

            pd.DataFrame(data).to_excel(filepath, index=False)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        return {
            "exported": True,
            "file_path": str(filepath),
            "filepath": str(filepath),
            "format": export_format,
            "record_count": record_count,
        }


# Registry of step executors -------------------------------------------------
_STEP_EXECUTORS: dict[str, StepExecutor] = {}


def register_step_executor(executor: StepExecutor, name: str | None = None) -> None:
    """Register a step executor under its step type (or an explicit name)."""
    key = name or getattr(executor, "step_type", None) or executor.get_step_type()
    if not key:
        raise ValueError("Step executor has no step type")
    _STEP_EXECUTORS[str(key)] = executor


def get_step_executor(step_type: str) -> StepExecutor | None:
    """Get a step executor by type."""
    return _STEP_EXECUTORS.get(step_type)


def register_custom_executor(*args: Any) -> None:
    """Register a custom executor.

    Supports both ``register_custom_executor(executor)`` and the explicit
    ``register_custom_executor("name", executor)`` form used by the dashboard.
    """
    if len(args) == 1:
        executor = args[0]
        name = getattr(executor, "step_type", None) or executor.get_step_type()
        register_step_executor(executor, str(name))
        return
    if len(args) == 2:
        name, executor = args
        register_step_executor(executor, str(name))
        alias = getattr(executor, "step_type", None)
        if alias and alias != name:
            register_step_executor(executor, str(alias))
        return
    raise TypeError("register_custom_executor expects (executor) or (name, executor)")


# Register default executors
for _executor in (
    GeneAnalysisStep(),
    DrugSearchStep(),
    ADMETStep(),
    LiteratureSearchStep(),
    ReportGenerationStep(),
    NotificationStep(),
    DataExportStep(),
):
    register_step_executor(_executor)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class AutomationEngine:
    """Engine for executing and scheduling automated research tasks."""

    def __init__(self, storage_path: str | Path | None = None):
        """Create an engine.

        Persistence is opt-in: pass ``storage_path`` to load/save tasks to
        disk, or pass ``":memory:"``/omit it for an isolated in-memory engine.
        The shared dashboard engine created by :func:`get_automation_engine`
        always uses the configured data directory.
        """
        if storage_path == ":memory:":
            storage_path = None
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.tasks: dict[str, AutomationTask] = {}
        self.executions: list[TaskExecution] = []
        self.scheduled_tasks: set[str] = set()
        self.event_handlers: dict[str, set[str]] = {}
        self._running = False
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._load_tasks()

    # -- persistence ----------------------------------------------------
    def _load_tasks(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            with self.storage_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            for task_data in payload.get("tasks", []):
                task = AutomationTask.from_dict(task_data)
                self.tasks[task.task_id] = task
                if task.trigger_type in (TriggerType.SCHEDULE, TriggerType.SCHEDULED):
                    if task.schedule:
                        self.scheduled_tasks.add(task.task_id)
                if task.event_type:
                    self.event_handlers.setdefault(task.event_type, set()).add(task.task_id)
            logger.info("Loaded %s automation tasks", len(self.tasks))
        except Exception as exc:
            logger.error("Failed to load automation tasks: %s", exc)

    def _save_tasks(self) -> None:
        if self.storage_path is None:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "tasks": [task.to_dict() for task in self.tasks.values()],
                "saved_at": _now(),
            }
            with self.storage_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception as exc:
            logger.error("Failed to save automation tasks: %s", exc)

    # -- task management ------------------------------------------------
    @property
    def executors(self) -> dict[str, StepExecutor]:
        """The live executor registry."""
        return _STEP_EXECUTORS

    def create_task(
        self,
        name: str,
        description: str = "",
        trigger_type: TriggerType = TriggerType.MANUAL,
        schedule: str = "",
        steps: list[dict] | None = None,
        event_type: str = "",
        task_id: str | None = None,
        tags: list[str] | None = None,
        context: dict[str, Any] | None = None,
        webhook_url: str = "",
        **_: Any,
    ) -> str:
        """Create a task and return its identifier."""
        task = AutomationTask(
            task_id=task_id or str(uuid.uuid4())[:8],
            name=name,
            description=description,
            trigger_type=trigger_type,
            schedule=schedule,
            event_type=event_type,
            webhook_url=webhook_url,
            steps=steps or [],
            tags=tags or [],
            context=context or {},
        )
        if task.trigger_type in (TriggerType.SCHEDULE, TriggerType.SCHEDULED) and schedule:
            task.next_run = self._calculate_next_run(schedule)
            self.scheduled_tasks.add(task.task_id)
            task.status = AutomationStatus.SCHEDULED
        if event_type:
            self.event_handlers.setdefault(event_type, set()).add(task.task_id)

        self.tasks[task.task_id] = task
        self._save_tasks()
        return task.task_id

    def get_task(self, task_id: str) -> AutomationTask | None:
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: AutomationStatus | None = None,
        tags: list[str] | None = None,
    ) -> list[AutomationTask]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [task for task in tasks if task.status == status]
        if tags:
            tasks = [task for task in tasks if any(tag in task.tags for tag in tags)]
        return tasks

    def update_task(self, task_id: str, **kwargs: Any) -> AutomationTask | None:
        task = self.tasks.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)
        task.updated_at = _now()
        if task.trigger_type in (TriggerType.SCHEDULE, TriggerType.SCHEDULED) and task.schedule:
            task.next_run = self._calculate_next_run(task.schedule)
        self._save_tasks()
        return task

    def delete_task(self, task_id: str) -> bool:
        if task_id not in self.tasks:
            return False
        del self.tasks[task_id]
        self.scheduled_tasks.discard(task_id)
        for handlers in self.event_handlers.values():
            handlers.discard(task_id)
        self._save_tasks()
        return True

    def _calculate_next_run(self, schedule: str) -> str | None:
        try:
            return croniter(schedule, datetime.now()).get_next(datetime).isoformat()
        except Exception:
            logger.warning("Invalid cron schedule: %s", schedule)
            return None

    # -- execution ------------------------------------------------------
    def execute_task(
        self, task_id: str, context: dict[str, Any] | None = None
    ) -> TaskExecution:
        """Execute a task and return its execution record."""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        execution = TaskExecution(task_id=task_id)
        self.executions.append(execution)
        task.status = AutomationStatus.RUNNING
        task.last_run = _now()
        task.run_count += 1

        exec_context: dict[str, Any] = dict(task.context)
        exec_context.update(context or {})
        completed: set[str] = set()
        failed_ids: set[str] = set()

        try:
            for index, raw_step in enumerate(task.steps):
                step = dict(raw_step)
                # Flatten nested ``parameters`` while keeping step metadata.
                parameters = step.get("parameters")
                if isinstance(parameters, dict):
                    step.update(parameters)
                step_type = str(step.get("executor") or step.get("type") or "")
                step_id = str(step.get("step_id") or f"step{index}")
                execution.current_step = step_id

                dependencies = step.get("depends_on") or []
                if isinstance(dependencies, str):
                    dependencies = [dependencies]
                missing = [dep for dep in dependencies if dep not in completed]
                executor = get_step_executor(step_type)

                if missing:
                    status = "skipped"
                    result: dict[str, Any] = {
                        "error": f"Dependencies not satisfied: {', '.join(missing)}"
                    }
                elif executor is None:
                    status = "failed"
                    result = {"error": f"No executor registered for step type: {step_type}"}
                else:
                    logger.info(
                        "Executing step %s/%s (%s)", index + 1, len(task.steps), step_type
                    )
                    try:
                        if _executor_accepts_context(executor):
                            result = executor.execute(step, exec_context)
                        else:
                            result = executor.execute(step)
                        status = "completed"
                    except Exception as exc:
                        status = "failed"
                        result = {"error": str(exc)}
                        logger.error("Step %s failed: %s", step_id, exc, exc_info=True)

                record = {
                    "step_index": index,
                    "step_id": step_id,
                    "step_type": step_type,
                    "status": status,
                    "result": result,
                    "timestamp": _now(),
                }
                execution.step_results[step_id] = record
                exec_context[step_id] = result
                exec_context[f"step_{index}_result"] = result
                if status == "completed":
                    completed.add(step_id)
                    exec_context.update(
                        {key: value for key, value in result.items() if key not in exec_context}
                    )
                elif status == "failed":
                    failed_ids.add(step_id)

            execution.status = (
                AutomationStatus.FAILED if failed_ids else AutomationStatus.COMPLETED
            )
        except Exception as exc:  # pragma: no cover - defensive
            execution.status = AutomationStatus.FAILED
            execution.error = str(exc)
            logger.error("Task %s failed: %s", task_id, exc, exc_info=True)
        finally:
            execution.completed_at = _now()
            execution.current_step = None
            execution.output = exec_context
            task.status = execution.status
            if execution.status == AutomationStatus.COMPLETED:
                task.success_count += 1
                task.last_error = None
            else:
                task.failure_count += 1
                errors = [
                    record["result"].get("error")
                    for record in execution.step_results.values()
                    if record["status"] == "failed" and isinstance(record.get("result"), dict)
                ]
                task.last_error = execution.error or (errors[0] if errors else "Step failed")
            if task.trigger_type in (TriggerType.SCHEDULE, TriggerType.SCHEDULED) and task.schedule:
                task.next_run = self._calculate_next_run(task.schedule)
            self._save_tasks()

        return execution

    def get_execution(self, execution_id: str | TaskExecution) -> TaskExecution | None:
        """Look up an execution by id (or return an execution object as-is)."""
        if isinstance(execution_id, TaskExecution):
            return execution_id
        return next(
            (item for item in self.executions if item.execution_id == execution_id),
            None,
        )

    def cancel_execution(self, execution_id: str | TaskExecution) -> bool:
        execution = self.get_execution(execution_id)
        if execution is None:
            return False
        execution.status = AutomationStatus.CANCELLED
        execution.completed_at = _now()
        execution.current_step = None
        task = self.tasks.get(execution.task_id)
        if task is not None:
            task.status = AutomationStatus.CANCELLED
            self._save_tasks()
        return True

    def get_task_history(self, task_id: str) -> list[TaskExecution]:
        return [item for item in self.executions if item.task_id == task_id]

    def get_execution_history(
        self, task_id: str | None = None, limit: int = 50
    ) -> list[TaskExecution]:
        executions = self.executions
        if task_id:
            executions = [item for item in executions if item.task_id == task_id]
        return executions[-limit:]

    # -- scheduling -----------------------------------------------------
    def schedule_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        if not task.schedule:
            logger.warning("Task %s has no cron schedule", task_id)
            return False
        task.next_run = self._calculate_next_run(task.schedule)
        task.status = AutomationStatus.SCHEDULED
        self.scheduled_tasks.add(task_id)
        self._save_tasks()
        return True

    def unschedule_task(self, task_id: str) -> bool:
        self.scheduled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if task is not None:
            task.next_run = None
            if task.status == AutomationStatus.SCHEDULED:
                task.status = AutomationStatus.PENDING
            self._save_tasks()
            return True
        return False

    def get_scheduled_tasks(self) -> list[AutomationTask]:
        return [
            self.tasks[task_id]
            for task_id in self.scheduled_tasks
            if task_id in self.tasks
        ]

    def check_scheduled_tasks(self) -> list[AutomationTask]:
        now = datetime.now()
        due: list[AutomationTask] = []
        for task in self.get_scheduled_tasks():
            if not task.next_run:
                continue
            try:
                if datetime.fromisoformat(task.next_run) <= now:
                    due.append(task)
            except (TypeError, ValueError):
                continue
        return due

    def run_due_tasks(self) -> list[TaskExecution]:
        executions: list[TaskExecution] = []
        for task in self.check_scheduled_tasks():
            logger.info("Running scheduled task: %s (%s)", task.name, task.task_id)
            executions.append(self.execute_task(task.task_id))
        return executions

    def start_scheduler(self, interval_seconds: int = 60) -> None:
        """Start a background scheduler thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        def loop() -> None:
            while not self._stop_event.wait(max(1, int(interval_seconds))):
                try:
                    self.run_due_tasks()
                except Exception:
                    logger.error("Scheduled run failed", exc_info=True)

        self._scheduler_thread = threading.Thread(
            target=loop, name="geneai-automation-scheduler", daemon=True
        )
        self._scheduler_thread.start()
        logger.info("Automation scheduler started (interval=%ss)", interval_seconds)

    def stop_scheduler(self) -> None:
        """Stop the background scheduler thread."""
        self._running = False
        self._stop_event.set()
        thread = self._scheduler_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self._scheduler_thread = None
        logger.info("Automation scheduler stopped")

    # -- events ---------------------------------------------------------
    def register_event_handler(self, event_type: str, task_id: str) -> None:
        self.event_handlers.setdefault(event_type, set()).add(task_id)

    def get_event_handlers(self, event_type: str) -> list[str]:
        return list(self.event_handlers.get(event_type, set()))

    def trigger_event(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> list[TaskExecution]:
        executions: list[TaskExecution] = []
        for task_id in list(self.event_handlers.get(event_type, set())):
            try:
                executions.append(self.execute_task(task_id, data or {}))
            except Exception:
                logger.error("Event-triggered task %s failed", task_id, exc_info=True)
        return executions


# Global automation engine ---------------------------------------------------
_automation_engine: AutomationEngine | None = None


def get_automation_engine(
    storage_path: str | Path | None = None,
) -> AutomationEngine:
    """Get the global automation engine instance.

    The shared engine persists its tasks in the configured data directory so
    that scheduled workflows survive application restarts.
    """
    global _automation_engine
    if _automation_engine is None:
        if storage_path is None:
            try:
                from geneai.config import DATA_DIR

                storage_path = Path(DATA_DIR) / "automation_tasks.json"
            except Exception:  # pragma: no cover - configuration is available
                storage_path = "automation_tasks.json"
        _automation_engine = AutomationEngine(storage_path)
    return _automation_engine


# ---------------------------------------------------------------------------
# Predefined automation templates
# ---------------------------------------------------------------------------
def _template_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class AutomationTemplates:
    """Ready-to-run research workflows."""

    @staticmethod
    def _register(engine: AutomationEngine, **kwargs: Any) -> AutomationTask:
        task_id = engine.create_task(**kwargs)
        task = engine.get_task(task_id)
        if task is None:  # pragma: no cover - create_task always registers
            raise RuntimeError("Failed to register automation template")
        return task

    @staticmethod
    def daily_gene_monitoring(
        genes: list[str], engine: AutomationEngine | None = None
    ) -> AutomationTask:
        """Monitor a panel of genes every day."""
        engine = engine or get_automation_engine()
        gene_list = [str(gene).strip().upper() for gene in genes if str(gene).strip()]
        steps: list[dict[str, Any]] = [
            {
                "step_id": f"gene_{index}",
                "executor": "gene_analysis",
                "parameters": {"gene_symbol": gene},
            }
            for index, gene in enumerate(gene_list)
        ]
        steps.append(
            {
                "step_id": "report",
                "executor": "report_generation",
                "parameters": {
                    "title": "Daily Gene Monitoring Report",
                    "sections": [
                        {
                            "title": "Gene annotations",
                            "content": "{{gene_0}}",
                        }
                    ],
                },
                "depends_on": [f"gene_{index}" for index in range(len(gene_list))],
            }
        )
        return AutomationTemplates._register(
            engine,
            name="Daily Gene Monitoring: " + ", ".join(gene_list),
            description="Daily annotation of a monitored gene panel",
            trigger_type=TriggerType.SCHEDULED,
            schedule="0 9 * * *",
            steps=steps,
            task_id=_template_id("daily_gene_monitoring"),
            tags=["gene", "monitoring", "daily"],
        )

    @staticmethod
    def drug_discovery_pipeline(
        disease: str, engine: AutomationEngine | None = None
    ) -> AutomationTask:
        """Run a drug discovery pipeline for a disease."""
        engine = engine or get_automation_engine()
        steps = [
            {
                "step_id": "search_drugs",
                "executor": "drug_search",
                "parameters": {"search_type": "disease", "query": disease, "limit": 20},
            },
            {
                "step_id": "admet",
                "executor": "admet",
                "parameters": {"smiles": "{{search_drugs.drugs[0].smiles}}"},
                "depends_on": ["search_drugs"],
            },
            {
                "step_id": "report",
                "executor": "report_generation",
                "parameters": {
                    "title": f"Drug Discovery Pipeline: {disease}",
                    "sections": [
                        {"title": "Drug candidates", "content": "{{search_drugs}}"},
                        {"title": "ADMET", "content": "{{admet}}"},
                    ],
                },
                "depends_on": ["search_drugs"],
            },
        ]
        return AutomationTemplates._register(
            engine,
            name=f"Drug Discovery Pipeline: {disease}",
            description=f"Search and profile drug candidates for {disease}",
            trigger_type=TriggerType.MANUAL,
            steps=steps,
            task_id=_template_id("drug_discovery_pipeline"),
            tags=["drug_discovery", disease.lower()],
        )

    @staticmethod
    def biomarker_discovery_workflow(
        disease: str,
        sample_type: str = "blood",
        engine: AutomationEngine | None = None,
    ) -> AutomationTask:
        """Discover candidate biomarkers for a disease."""
        engine = engine or get_automation_engine()
        steps = [
            {
                "step_id": "gene_analysis",
                "executor": "gene_analysis",
                "parameters": {"disease": disease, "limit": 50},
            },
            {
                "step_id": "literature",
                "executor": "literature_search",
                "parameters": {
                    "query": f"{disease} biomarker {sample_type}",
                    "max_results": 30,
                },
            },
            {
                "step_id": "report",
                "executor": "report_generation",
                "parameters": {
                    "title": f"Biomarker Discovery Report: {disease}",
                    "sections": [
                        {"title": "Candidate genes", "content": "{{gene_analysis}}"},
                        {"title": "Literature", "content": "{{literature}}"},
                    ],
                },
                "depends_on": ["gene_analysis", "literature"],
            },
        ]
        return AutomationTemplates._register(
            engine,
            name=f"Biomarker Discovery: {disease}",
            description=f"Discover biomarkers for {disease} using {sample_type} samples",
            trigger_type=TriggerType.MANUAL,
            steps=steps,
            task_id=_template_id("biomarker_discovery"),
            tags=["biomarker", "discovery", disease.lower()],
        )

    @staticmethod
    def weekly_literature_review(
        genes: list[str], engine: AutomationEngine | None = None
    ) -> AutomationTask:
        """Review the literature for a gene panel every week."""
        engine = engine or get_automation_engine()
        gene_list = [str(gene).strip().upper() for gene in genes if str(gene).strip()]
        steps = [
            {
                "step_id": f"literature_{index}",
                "executor": "literature_search",
                "parameters": {
                    "query": f"{gene} cancer",
                    "max_results": 20,
                },
            }
            for index, gene in enumerate(gene_list)
        ]
        steps.append(
            {
                "step_id": "report",
                "executor": "report_generation",
                "parameters": {
                    "title": "Weekly Literature Review",
                    "sections": [
                        {"title": "Literature", "content": "{{literature_0}}"}
                    ],
                },
                "depends_on": [f"literature_{index}" for index in range(len(gene_list))],
            }
        )
        return AutomationTemplates._register(
            engine,
            name="Weekly Literature Review: " + ", ".join(gene_list),
            description="Weekly literature review for a monitored gene panel",
            trigger_type=TriggerType.SCHEDULED,
            schedule="0 8 * * 1",
            steps=steps,
            task_id=_template_id("weekly_literature_review"),
            tags=["literature", "weekly"],
        )

    # -- historical template names (kept for compatibility) -------------
    @staticmethod
    def daily_literature_monitor(
        disease: str, webhook_url: str = "", engine: AutomationEngine | None = None
    ) -> AutomationTask:
        engine = engine or get_automation_engine()
        steps: list[dict[str, Any]] = [
            {
                "step_id": "literature",
                "executor": "literature_search",
                "parameters": {"query": disease, "limit": 20, "live": True},
            }
        ]
        if webhook_url:
            steps.append(
                {
                    "step_id": "notify",
                    "executor": "notification",
                    "parameters": {
                        "type": "webhook",
                        "webhook_url": webhook_url,
                        "message": f"New literature found for {disease}",
                    },
                }
            )
        else:
            steps.append(
                {
                    "step_id": "notify",
                    "executor": "notification",
                    "parameters": {
                        "type": "log",
                        "message": f"Literature check completed for {disease}",
                    },
                }
            )
        return AutomationTemplates._register(
            engine,
            name=f"Daily Literature Monitor: {disease}",
            description=f"Monitor PubMed for new papers on {disease}",
            trigger_type=TriggerType.SCHEDULED,
            schedule="0 6 * * *",
            steps=steps,
            task_id=_template_id("daily_literature_monitor"),
            tags=["literature", "monitoring", disease.lower()],
        )

    @staticmethod
    def weekly_drug_discovery_scan(
        disease: str, engine: AutomationEngine | None = None
    ) -> AutomationTask:
        template = AutomationTemplates.drug_discovery_pipeline(disease, engine)
        template.task_id = _template_id("weekly_drug_discovery_scan")
        template.name = f"Weekly Drug Discovery Scan: {disease}"
        template.trigger_type = TriggerType.SCHEDULED
        template.schedule = "0 9 * * 1"
        if engine is not None:
            engine.tasks.pop(next((k for k, v in engine.tasks.items() if v is template), ""), None)
            engine.tasks[template.task_id] = template
            engine.schedule_task(template.task_id)
        return template

    @staticmethod
    def admet_screening_pipeline(
        smiles_list: list[str], engine: AutomationEngine | None = None
    ) -> AutomationTask:
        engine = engine or get_automation_engine()
        steps = [
            {
                "step_id": f"admet_{index}",
                "executor": "admet",
                "parameters": {"smiles": smiles},
            }
            for index, smiles in enumerate(smiles_list)
        ]
        steps.append(
            {
                "step_id": "export",
                "executor": "data_export",
                "parameters": {
                    "format": "csv",
                    "data_key": "results",
                    "filename": "admet_screening_results.csv",
                },
                "depends_on": [f"admet_{index}" for index in range(len(smiles_list))],
            }
        )
        return AutomationTemplates._register(
            engine,
            name="ADMET Screening Pipeline",
            description="Screen compounds for ADMET properties",
            trigger_type=TriggerType.MANUAL,
            steps=steps,
            task_id=_template_id("admet_screening_pipeline"),
            tags=["admet", "screening"],
        )


__all__ = [
    "ADMETStep",
    "AutomationEngine",
    "AutomationStatus",
    "AutomationTask",
    "AutomationTemplates",
    "DataExportStep",
    "DrugSearchStep",
    "GeneAnalysisStep",
    "LiteratureSearchStep",
    "NotificationStep",
    "ReportGenerationStep",
    "StepExecutor",
    "TaskExecution",
    "TriggerType",
    "get_automation_engine",
    "get_step_executor",
    "register_custom_executor",
    "register_step_executor",
]
