"""GeneAI Unified Biological Knowledge Database - Phase 5.3."""
from __future__ import annotations

from geneai.unified_knowledge.database import (
    KnowledgeDatabase,
    DatabaseConfig,
    get_knowledge_db,
    init_knowledge_db,
)
from geneai.unified_knowledge.query import (
    KnowledgeQuery,
    QueryResult,
    get_knowledge_query,
)
from geneai.unified_knowledge.loaders import (
    LoadStats,
    BaseLoader,
    GeneLoader,
    DiseaseLoader,
    ProteinLoader,
    PathwayLoader,
    DrugLoader,
    LiteratureLoader,
    VariantLoader,
    load_all_data,
)
from geneai.unified_knowledge.ui import (
    render_unified_knowledge_dashboard,
    render as render_unified_knowledge,
)

__all__ = [
    # Database
    "KnowledgeDatabase",
    "DatabaseConfig",
    "get_knowledge_db",
    "init_knowledge_db",
    # Query
    "KnowledgeQuery",
    "QueryResult",
    "get_knowledge_query",
    # Loaders
    "LoadStats",
    "BaseLoader",
    "GeneLoader",
    "DiseaseLoader",
    "ProteinLoader",
    "PathwayLoader",
    "DrugLoader",
    "LiteratureLoader",
    "VariantLoader",
    "load_all_data",
    # UI
    "render_unified_knowledge_dashboard",
    "render_unified_knowledge",
]

__version__ = "5.3.0"