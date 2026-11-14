"""Drug Repurposing module for GeneAI Research - Phase 4.6."""

from .dgidb_client import (
    search_dgidb_genes,
    get_dgidb_drug,
    get_dgidb_categories,
    get_dgidb_sources,
)

from .ctd_client import (
    search_ctd_chemical_gene,
    search_ctd_disease_chemical,
    search_ctd_gene_disease,
    search_ctd_pathways,
)

from .ttd_client import (
    search_ttd_target,
    search_ttd_drug,
    get_ttd_target_drugs,
    get_ttd_drug_targets,
    ttd_access_status,
)

from .repurposing_engine import (
    RepurposingCandidate,
    DrugRepurposingEngine,
    create_repurposing_engine,
)

from .drug_matching import (
    match_disease_to_genes,
    match_genes_to_drugs,
    match_disease_to_drugs,
    find_repurposing_opportunities,
)

# Backwards-compatible alias used by the biotech assistant tool registry.
find_repurposing_candidates = find_repurposing_opportunities

from .target_matching import (
    get_target_profile,
    find_targets_for_disease,
    find_diseases_for_target,
    get_target_drugs_comprehensive,
    assess_target_druggability,
)

from .evidence_scoring import (
    EvidenceScore,
    EvidenceScorer,
    score_candidate,
    score_candidates_batch,
)

from .literature_analysis import (
    search_pubmed_for_drug_disease,
    search_pubmed_for_drug_target,
    search_pubmed_for_target_disease,
    search_pubmed_for_repurposing,
    get_publication_details,
    extract_drug_findings,
    build_literature_evidence_summary,
)

from .candidate_ranking import (
    CandidateRanker,
    rank_candidates,
    get_top_candidates,
    filter_candidates,
    deduplicate_candidates,
    group_candidates_by_target,
    group_candidates_by_mechanism,
    compare_candidates,
)

from .network_analysis import (
    create_disease_gene_drug_network,
    create_drug_target_network,
    create_target_disease_network,
    create_candidate_ranking_chart,
    create_evidence_comparison_chart,
    create_phase_distribution_chart,
    create_evidence_class_distribution,
    export_network_data,
)

from .report_generator import (
    generate_repurposing_report_csv,
    generate_repurposing_report_json,
    generate_candidate_comparison_csv,
    generate_repurposing_pdf_content,
    export_analysis_to_database,
    build_repurposing_summary_report,
)

from .drug_repurposing_ui import render_drug_repurposing_dashboard

__all__ = [
    # DGIdb
    "search_dgidb_genes",
    "get_dgidb_drug",
    "get_dgidb_categories",
    "get_dgidb_sources",
    # CTD
    "search_ctd_chemical_gene",
    "search_ctd_disease_chemical",
    "search_ctd_gene_disease",
    "search_ctd_pathways",
    # TTD
    "search_ttd_target",
    "search_ttd_drug",
    "get_ttd_target_drugs",
    "get_ttd_drug_targets",
    "ttd_access_status",
    # Repurposing Engine
    "RepurposingCandidate",
    "DrugRepurposingEngine",
    "create_repurposing_engine",
    # Drug Matching
    "match_disease_to_genes",
    "match_genes_to_drugs",
    "match_disease_to_drugs",
    "find_repurposing_opportunities",
    "find_repurposing_candidates",
    # Target Matching
    "get_target_profile",
    "find_targets_for_disease",
    "find_diseases_for_target",
    "get_target_drugs_comprehensive",
    "assess_target_druggability",
    # Evidence Scoring
    "EvidenceScore",
    "EvidenceScorer",
    "score_candidate",
    "score_candidates_batch",
    # Literature Analysis
    "search_pubmed_for_drug_disease",
    "search_pubmed_for_drug_target",
    "search_pubmed_for_target_disease",
    "search_pubmed_for_repurposing",
    "get_publication_details",
    "extract_drug_findings",
    "build_literature_evidence_summary",
    # Candidate Ranking
    "CandidateRanker",
    "rank_candidates",
    "get_top_candidates",
    "filter_candidates",
    "deduplicate_candidates",
    "group_candidates_by_target",
    "group_candidates_by_mechanism",
    "compare_candidates",
    # Network Analysis
    "create_disease_gene_drug_network",
    "create_drug_target_network",
    "create_target_disease_network",
    "create_candidate_ranking_chart",
    "create_evidence_comparison_chart",
    "create_phase_distribution_chart",
    "create_evidence_class_distribution",
    "export_network_data",
    # Report Generator
    "generate_repurposing_report_csv",
    "generate_repurposing_report_json",
    "generate_candidate_comparison_csv",
    "generate_repurposing_pdf_content",
    "export_analysis_to_database",
    "build_repurposing_summary_report",
    # UI
    "render_drug_repurposing_dashboard",
]