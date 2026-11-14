"""AI Research Intelligence (Phase 4.13) - Package initialization."""
from __future__ import annotations

from geneai.ai_research_intelligence.knowledge_graph import (
    KGNode,
    KGEdge,
    add_node,
    add_edge,
    get_node,
    get_nodes_by_type,
    find_nodes,
    get_neighbors,
    shortest_path,
    compute_centrality,
    store_analysis_result,
    get_analysis_result,
    bulk_load_from_opentargets,
    get_subgraph,
    initialize_knowledge_graph,
)

from geneai.ai_research_intelligence.mutation_to_drug_workflow import (
    VariantAnnotation,
    GeneDiseaseLink,
    DrugCandidate,
    MutationToDrugResult,
    MutationToDrugWorkflow,
    run_mutation_to_drug_workflow,
)

from geneai.ai_research_intelligence.ai_candidate_ranking import (
    CandidateFeatures,
    RankingResult,
    AICandidateRanker,
    extract_candidate_features,
    rank_candidates,
    create_training_data_from_historical,
)

from geneai.ai_research_intelligence.ai_research_assistant import (
    ResearchQuestion,
    ResearchAnswer,
    ResearchSession,
    AIResearchAssistant,
    create_research_assistant,
)

from geneai.ai_research_intelligence.reproducibility import (
    Experiment,
    ReproducibilityTracker,
    initialize_reproducibility,
    track_function,
)

from geneai.ai_research_intelligence.advanced_report_generator import (
    ReportConfig,
    ReportSection,
    AdvancedReportGenerator,
    create_mutation_to_drug_report,
    create_integrated_analysis_report,
    generate_comparative_report,
)

from geneai.ai_research_intelligence.unified_dashboard import (
    render_ai_research_intelligence_dashboard,
)

from geneai.ai_research_intelligence.database import (
    initialize_ari_database,
    store_mtd_run,
    get_mtd_run,
    get_recent_mtd_runs,
    store_ranking_run,
    get_ranking_run,
    get_recent_ranking_runs,
    store_research_session,
    get_research_session,
    store_report,
    get_reports_for_run,
    search_mtd_runs,
    clear_mtd_run,
)

__all__ = [
    # Knowledge Graph
    "KGNode",
    "KGEdge",
    "add_node",
    "add_edge",
    "get_node",
    "get_nodes_by_type",
    "find_nodes",
    "get_neighbors",
    "shortest_path",
    "compute_centrality",
    "store_analysis_result",
    "get_analysis_result",
    "bulk_load_from_opentargets",
    "get_subgraph",
    "initialize_knowledge_graph",
    # Mutation-to-Drug Workflow
    "VariantAnnotation",
    "GeneDiseaseLink",
    "DrugCandidate",
    "MutationToDrugResult",
    "MutationToDrugWorkflow",
    "run_mutation_to_drug_workflow",
    # AI Candidate Ranking
    "CandidateFeatures",
    "RankingResult",
    "AICandidateRanker",
    "extract_candidate_features",
    "rank_candidates",
    "create_training_data_from_historical",
    # AI Research Assistant
    "ResearchQuestion",
    "ResearchAnswer",
    "ResearchSession",
    "AIResearchAssistant",
    "create_research_assistant",
    # Reproducibility
    "Experiment",
    "ReproducibilityTracker",
    "initialize_reproducibility",
    "track_function",
    # Advanced Reports
    "ReportConfig",
    "ReportSection",
    "AdvancedReportGenerator",
    "create_mutation_to_drug_report",
    "create_integrated_analysis_report",
    "generate_comparative_report",
    # Unified Dashboard
    "render_ai_research_intelligence_dashboard",
    # Database
    "initialize_ari_database",
    "store_mtd_run",
    "get_mtd_run",
    "get_recent_mtd_runs",
    "store_ranking_run",
    "get_ranking_run",
    "get_recent_ranking_runs",
    "store_research_session",
    "get_research_session",
    "store_report",
    "get_reports_for_run",
    "search_mtd_runs",
    "clear_mtd_run",
]