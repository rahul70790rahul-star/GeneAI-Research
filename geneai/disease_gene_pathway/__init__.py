"""Disease-Gene-Pathway Network Analysis - Phase 4.9."""
from __future__ import annotations

from geneai.disease_gene_pathway.analysis_engine import (
    DiseaseGenePathwayAnalyzer,
    DiseaseGenePathwayResult,
    GeneNetworkEdge,
    GeneNetworkNode,
    run_disease_gene_pathway_analysis,
    run_vcf_analysis,
)
from geneai.disease_gene_pathway.api_clients import (
    DiseaseGeneAssociation,
    DisGeNETAssociation,
    GOAnnotation,
    KEGGPathway,
    PPIInteraction,
    ReactomePathway,
    UniProtEntry,
    fetch_disgenet_disease_genes,
    fetch_disgenet_gene_diseases,
    fetch_go_annotations,
    fetch_go_enrichment,
    fetch_kegg_pathways_for_genes,
    fetch_opentargets_disease_genes,
    fetch_opentargets_gene_diseases,
    fetch_reactome_pathway_analysis,
    fetch_reactome_pathways_for_genes,
    fetch_string_enrichment,
    fetch_string_interactions,
    fetch_uniprot_entry,
    search_kegg_pathways,
    search_opentargets_diseases,
)
from geneai.disease_gene_pathway.database import (
    clear_dgp_analysis_run,
    get_dgp_analysis_run,
    get_dgp_db_version,
    get_dgp_network,
    get_dgp_therapeutic_targets,
    get_recent_dgp_runs,
    initialize_dgp_database,
    search_dgp_runs,
    store_dgp_analysis_run,
    store_dgp_disease_associations,
    store_dgp_disgenet_associations,
    store_dgp_go_enrichment,
    store_dgp_kegg_pathways,
    store_dgp_network,
    store_dgp_reactome_pathways,
    store_dgp_string_enrichment,
    store_dgp_therapeutic_targets,
)
from geneai.disease_gene_pathway.report_generator import (
    generate_dgp_csv_report,
    generate_dgp_json_report,
    generate_dgp_pdf_report,
)
from geneai.disease_gene_pathway.dgp_ui import (
    render_dgp_dashboard,
)

__all__ = [
    # Analysis engine
    "DiseaseGenePathwayAnalyzer",
    "DiseaseGenePathwayResult",
    "GeneNetworkNode",
    "GeneNetworkEdge",
    "run_disease_gene_pathway_analysis",
    "run_vcf_analysis",
    # API clients
    "DiseaseGeneAssociation",
    "DisGeNETAssociation",
    "GOAnnotation",
    "KEGGPathway",
    "PPIInteraction",
    "ReactomePathway",
    "UniProtEntry",
    "fetch_opentargets_disease_genes",
    "fetch_opentargets_gene_diseases",
    "search_opentargets_diseases",
    "fetch_disgenet_gene_diseases",
    "fetch_disgenet_disease_genes",
    "fetch_string_interactions",
    "fetch_string_enrichment",
    "fetch_kegg_pathways_for_genes",
    "search_kegg_pathways",
    "fetch_reactome_pathways_for_genes",
    "fetch_reactome_pathway_analysis",
    "fetch_go_annotations",
    "fetch_go_enrichment",
    "fetch_uniprot_entry",
    # Database
    "initialize_dgp_database",
    "get_dgp_db_version",
    "store_dgp_analysis_run",
    "store_dgp_network",
    "store_dgp_disease_associations",
    "store_dgp_disgenet_associations",
    "store_dgp_kegg_pathways",
    "store_dgp_reactome_pathways",
    "store_dgp_go_enrichment",
    "store_dgp_string_enrichment",
    "store_dgp_therapeutic_targets",
    "get_dgp_analysis_run",
    "get_dgp_network",
    "get_dgp_therapeutic_targets",
    "get_recent_dgp_runs",
    "search_dgp_runs",
    "clear_dgp_analysis_run",
    # Reports
    "generate_dgp_pdf_report",
    "generate_dgp_csv_report",
    "generate_dgp_json_report",
    # UI
    "render_dgp_dashboard",
]

__version__ = "4.9.0"