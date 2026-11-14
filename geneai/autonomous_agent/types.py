"""Shared type definitions for Autonomous Bioinformatics Agent."""
from __future__ import annotations

from enum import Enum


class AgentStatus(Enum):
    """Agent session status."""
    PENDING = "pending"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    AWAITING_APPROVAL = "awaiting_approval"


class TaskType(Enum):
    """Types of tasks the agent can perform."""
    SEQUENCE_ANALYSIS = "sequence_analysis"
    VARIANT_ANALYSIS = "variant_analysis"
    LITERATURE_SEARCH = "literature_search"
    GENE_IDENTIFICATION = "gene_identification"
    PROTEIN_ANALYSIS = "protein_analysis"
    PATHWAY_ANALYSIS = "pathway_analysis"
    ADMET_PREDICTION = "admet_prediction"
    DRUG_REPURPOSING = "drug_repurposing"
    MOLECULAR_DOCKING = "molecular_docking"
    DRUG_OPTIMIZATION = "drug_optimization"
    DISEASE_ANALYSIS = "disease_analysis"
    BIOMARKER_DISCOVERY = "biomarker_discovery"
    REPORT_GENERATION = "report_generation"
    DATA_VISUALIZATION = "data_visualization"


class ApprovalStatus(Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalType(Enum):
    """Types of approval requests."""
    TOOL_EXECUTION = "tool_execution"
    DATA_ACCESS = "data_access"
    EXTERNAL_API = "external_api"
    RESOURCE_ALLOCATION = "resource_allocation"
    MODEL_DEPLOYMENT = "model_deployment"
    LITERATURE_SEARCH = "literature_search"
    CUSTOM = "custom"