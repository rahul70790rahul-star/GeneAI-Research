"""ADMET Prediction - Phase 4.9: Advanced AI-Based ADMET Prediction Engine."""
from __future__ import annotations

from geneai.admet_prediction.admet_engine import (
    ADMETPredictionEngine,
    ADMETPrediction,
    ADMETResult,
    create_admet_engine,
    predict_admet,
)
from geneai.admet_prediction.admet_scoring import (
    ADMETScore,
    CategoryScore,
    OverallADMETScore,
    calculate_overall_admet_score,
    compare_compounds,
    generate_risk_report,
)
from geneai.admet_prediction.data_integration import (
    get_chembl_molecule_by_chembl_id,
    get_pubchem_compound_by_cid,
    get_pubchem_compound_by_smiles,
    get_uniprot_entry,
    merge_compound_data,
    search_chembl_by_smiles,
    search_pubchem_by_name,
)
from geneai.admet_prediction.database import (
    get_admet_db_version,
    get_admet_predictions,
    get_admet_score,
    get_compound_history,
    get_model_metadata,
    get_recent_runs,
    initialize_admet_database,
    search_admet_runs,
    store_admet_model,
    store_admet_prediction_run,
    store_admet_predictions,
    store_admet_score,
)
from geneai.admet_prediction.ml_models import (
    ADMETModel,
    ADMETModelManager,
    train_models_from_data,
)
from geneai.admet_prediction.molecular_properties import (
    assess_drug_likeness,
    calculate_molecular_properties,
)
from geneai.admet_prediction.admet_ui import (
    render_admet_dashboard,
)

__all__ = [
    # Core prediction
    "ADMETPredictionEngine",
    "ADMETPrediction",
    "ADMETResult",
    "create_admet_engine",
    "predict_admet",
    # Scoring
    "ADMETScore",
    "CategoryScore",
    "OverallADMETScore",
    "calculate_overall_admet_score",
    "compare_compounds",
    "generate_risk_report",
    # Data integration
    "get_pubchem_compound_by_cid",
    "get_pubchem_compound_by_smiles",
    "search_pubchem_by_name",
    "get_chembl_molecule_by_chembl_id",
    "search_chembl_by_smiles",
    "get_uniprot_entry",
    "merge_compound_data",
    # Database
    "initialize_admet_database",
    "get_admet_db_version",
    "store_admet_prediction_run",
    "store_admet_predictions",
    "store_admet_score",
    "get_admet_prediction_run",
    "get_admet_predictions",
    "get_admet_score",
    "get_recent_runs",
    "search_admet_runs",
    "get_compound_history",
    "store_admet_model",
    "get_model_metadata",
    # ML Models
    "ADMETModel",
    "ADMETModelManager",
    "train_models_from_data",
    # Molecular properties
    "calculate_molecular_properties",
    "assess_drug_likeness",
    # Reports
    "generate_admet_pdf_report",
    "generate_admet_csv_report",
    "generate_admet_json_report",
    # UI
    "render_admet_dashboard",
]

__version__ = "4.9.0"