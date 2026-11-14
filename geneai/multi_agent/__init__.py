"""GeneAI Multi-Agent System - Phase 5.2."""
from __future__ import annotations

from geneai.multi_agent.core import (
    BaseAgent,
    AgentCapability,
    AgentMessage,
    MessageType,
    AgentStatus,
    MessageBus,
    get_message_bus,
)
from geneai.multi_agent.agents import (
    GeneAnalysisAgent,
    ProteinAnalysisAgent,
    DrugDiscoveryAgent,
    ADMETAgent,
    LiteratureAgent,
    DiseaseAnalysisAgent,
    BiomarkerAgent,
    DrugRepurposingAgent,
    WorkflowAgent,
    create_all_agents,
    register_all_agents,
)
from geneai.multi_agent.orchestrator import (
    AgentOrchestrator,
    Workflow,
    WorkflowStep,
    WorkflowStatus,
    WorkflowTemplates,
    get_orchestrator,
)
from geneai.multi_agent.ui import (
    render_multi_agent_dashboard,
    render_agent_chat,
    render as render_multi_agent,
)

__all__ = [
    # Core
    "BaseAgent",
    "AgentCapability",
    "AgentMessage",
    "MessageType",
    "AgentStatus",
    "MessageBus",
    "get_message_bus",
    # Agents
    "GeneAnalysisAgent",
    "ProteinAnalysisAgent",
    "DrugDiscoveryAgent",
    "ADMETAgent",
    "LiteratureAgent",
    "DiseaseAnalysisAgent",
    "BiomarkerAgent",
    "DrugRepurposingAgent",
    "WorkflowAgent",
    "create_all_agents",
    "register_all_agents",
    # Orchestrator
    "AgentOrchestrator",
    "Workflow",
    "WorkflowStep",
    "WorkflowStatus",
    "WorkflowTemplates",
    "get_orchestrator",
    # UI
    "render_multi_agent_dashboard",
    "render_agent_chat",
    "render_multi_agent",
]

__version__ = "5.2.0"