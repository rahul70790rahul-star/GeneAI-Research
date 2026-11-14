"""GeneAI Intelligent Research Automation - Phase 5.4."""
from __future__ import annotations

from geneai.research_automation.core import (
    AutomationEngine,
    AutomationTask,
    TaskExecution,
    AutomationStatus,
    TriggerType,
    StepExecutor,
    GeneAnalysisStep,
    DrugSearchStep,
    ADMETStep,
    LiteratureSearchStep,
    ReportGenerationStep,
    NotificationStep,
    DataExportStep,
    AutomationTemplates,
    get_automation_engine,
    register_custom_executor,
)
from geneai.research_automation.ui import (
    render_research_automation_dashboard,
    render as render_research_automation,
)

__all__ = [
    # Core
    "AutomationEngine",
    "AutomationTask",
    "TaskExecution",
    "AutomationStatus",
    "TriggerType",
    "StepExecutor",
    "GeneAnalysisStep",
    "DrugSearchStep",
    "ADMETStep",
    "LiteratureSearchStep",
    "ReportGenerationStep",
    "NotificationStep",
    "DataExportStep",
    "AutomationTemplates",
    "get_automation_engine",
    "register_custom_executor",
    # UI
    "render_research_automation_dashboard",
    "render_research_automation",
]

__version__ = "5.4.0"