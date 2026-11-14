"""Research Paper Analysis module for GeneAI Research - Phase 4.8."""

from .literature_clients import (
    search_europe_pmc,
    get_europe_pmc_fulltext,
    search_crossref,
    search_openalex,
    get_openalex_work,
    search_all_sources,
    LiteratureSourceError,
)

from .paper_analyzer import (
    PaperMetadata,
    ExtractedEntities,
    StructuredSummary,
    DrugTargetRelationship,
    fetch_paper_content,
    analyze_paper,
    analyze_research_papers,
    extract_entities_from_text,
    generate_structured_summary,
    extract_drug_target_relationships,
)

from .gap_identification import (
    ResearchGap,
    GapAnalysisResult,
    identify_gaps_from_papers,
    generate_gap_report,
)

from .paper_comparison import (
    PaperComparison,
    compare_papers,
    export_comparison_csv,
    export_comparison_json,
)

from .research_assistant import (
    ResearchAssistant,
    AssistantResponse,
    create_research_assistant,
)

from .drug_intelligence import (
    DrugTargetIntelligence,
    DiseaseTargetIntelligence,
    TherapeuticCompoundIntelligence,
    enrich_drug_target_relationships,
    identify_disease_target_associations,
    identify_therapeutic_compounds,
    generate_drug_discovery_report,
)

from .report_generator import (
    generate_analysis_report_csv,
    generate_analysis_report_json,
    generate_gap_report_csv,
    generate_comparison_report_csv,
    generate_pdf_report,
    generate_executive_summary,
)

from .research_analysis_ui import render_research_analysis_dashboard

__all__ = [
    # Literature Clients
    "search_europe_pmc",
    "get_europe_pmc_fulltext",
    "search_crossref",
    "search_openalex",
    "get_openalex_work",
    "search_all_sources",
    "LiteratureSourceError",
    # Paper Analyzer
    "PaperMetadata",
    "ExtractedEntities",
    "StructuredSummary",
    "DrugTargetRelationship",
    "fetch_paper_content",
    "analyze_paper",
    "analyze_research_papers",
    "extract_entities_from_text",
    "generate_structured_summary",
    "extract_drug_target_relationships",
    # Gap Identification
    "ResearchGap",
    "GapAnalysisResult",
    "identify_gaps_from_papers",
    "generate_gap_report",
    # Paper Comparison
    "PaperComparison",
    "compare_papers",
    "export_comparison_csv",
    "export_comparison_json",
    # Research Assistant
    "ResearchAssistant",
    "AssistantResponse",
    "create_research_assistant",
    # Drug Intelligence
    "DrugTargetIntelligence",
    "DiseaseTargetIntelligence",
    "TherapeuticCompoundIntelligence",
    "enrich_drug_target_relationships",
    "identify_disease_target_associations",
    "identify_therapeutic_compounds",
    "generate_drug_discovery_report",
    # Report Generator
    "generate_analysis_report_csv",
    "generate_analysis_report_json",
    "generate_gap_report_csv",
    "generate_comparison_report_csv",
    "generate_pdf_report",
    "generate_executive_summary",
    # UI
    "render_research_analysis_dashboard",
]