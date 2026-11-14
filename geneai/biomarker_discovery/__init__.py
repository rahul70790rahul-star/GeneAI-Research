"""Biomarker Discovery - Phase 4.10: AI Biomarker Discovery Engine."""
from __future__ import annotations

from geneai.biomarker_discovery.data_integration import (
    EnsemblGene,
    GEODataset,
    GEOSample,
    NCBIGene,
    UniProtBiomarkerInfo,
    fetch_ensembl_gene,
    fetch_geo_dataset,
    fetch_ncbi_gene,
    fetch_uniprot_biomarker_info,
    search_geo_datasets,
)
from geneai.biomarker_discovery.database import (
    clear_bd_analysis_run,
    get_bd_analysis_run,
    get_bd_candidates,
    get_bd_db_version,
    get_bd_differential_expression,
    get_bd_feature_ranking,
    get_bd_model_performance,
    get_bd_roc_curves,
    get_recent_bd_runs,
    initialize_bd_database,
    search_bd_runs,
    store_bd_analysis_run,
    store_bd_candidates,
    store_bd_dataset,
    store_bd_differential_expression,
    store_bd_feature_ranking,
    store_bd_model_performance,
    store_bd_roc_curves,
)
from geneai.biomarker_discovery.ml_engine import (
    BiomarkerCandidate,
    BiomarkerDiscoveryEngine,
    BiomarkerResult,
    compare_biomarker_sets,
    run_biomarker_discovery,
)
from geneai.biomarker_discovery.bd_ui import (
    render_biomarker_discovery_dashboard,
)

__all__ = [
    # Data integration
    "GEODataset",
    "GEOSample",
    "NCBIGene",
    "EnsemblGene",
    "UniProtBiomarkerInfo",
    "fetch_geo_dataset",
    "search_geo_datasets",
    "fetch_ncbi_gene",
    "fetch_ensembl_gene",
    "fetch_uniprot_biomarker_info",
    # ML Engine
    "BiomarkerDiscoveryEngine",
    "BiomarkerCandidate",
    "BiomarkerResult",
    "run_biomarker_discovery",
    "compare_biomarker_sets",
    # Database
    "initialize_bd_database",
    "get_bd_db_version",
    "store_bd_analysis_run",
    "store_bd_candidates",
    "store_bd_model_performance",
    "store_bd_roc_curves",
    "store_bd_feature_ranking",
    "store_bd_differential_expression",
    "store_bd_dataset",
    "get_bd_analysis_run",
    "get_bd_candidates",
    "get_bd_model_performance",
    "get_bd_roc_curves",
    "get_bd_feature_ranking",
    "get_bd_differential_expression",
    "get_recent_bd_runs",
    "search_bd_runs",
    "clear_bd_analysis_run",
    # UI
    "render_biomarker_discovery_dashboard",
]

__version__ = "4.10.0"