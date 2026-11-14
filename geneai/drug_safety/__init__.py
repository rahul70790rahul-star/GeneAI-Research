"""Drug Safety & Toxicity Prediction - Phase 4.11."""
from __future__ import annotations

from geneai.drug_safety.data_integration import (
    ADMETlabPrediction,
    ChEMBLToxicity,
    DrugInteraction,
    PubChemToxicity,
    SafetyProfile,
    Tox21Assay,
    assess_toxicity_risk,
    build_safety_profile,
    calculate_toxicity_relevant_properties,
    fetch_admetlab_prediction,
    fetch_chembl_toxicity,
    fetch_drug_interactions,
    fetch_pubchem_toxicity,
    fetch_pubchem_compound_safety,
    fetch_tox21_data,
    predict_drug_safety,
)
from geneai.drug_safety.database import (
    clear_ds_analysis_run,
    get_ds_admetlab_prediction,
    get_ds_analysis_run,
    get_ds_chembl_toxicity,
    get_ds_db_version,
    get_ds_drug_interactions,
    get_ds_ml_predictions,
    get_ds_models,
    get_ds_pubchem_toxicity,
    get_recent_ds_runs,
    initialize_ds_database,
    search_ds_runs,
    store_ds_admetlab_prediction,
    store_ds_analysis_run,
    store_ds_chembl_toxicity,
    store_ds_drug_interactions,
    store_ds_ml_predictions,
    store_ds_model_metadata,
    store_ds_pubchem_toxicity,
)
from geneai.drug_safety.ml_models import (
    TOXICITY_ENDPOINTS,
    ToxicityModel,
    ToxicityModelManager,
    ToxicityPrediction,
    create_synthetic_toxicity_data,
    load_pretrained_models,
)
from geneai.drug_safety.report_generator import (
    generate_ds_csv_report,
    generate_ds_json_report,
    generate_ds_pdf_report,
)
from geneai.drug_safety.safety_ui import (
    render_drug_safety_dashboard,
)

__all__ = [
    # Data integration
    "SafetyProfile",
    "PubChemToxicity",
    "ChEMBLToxicity",
    "ADMETlabPrediction",
    "Tox21Assay",
    "DrugInteraction",
    "build_safety_profile",
    "predict_drug_safety",
    "fetch_pubchem_toxicity",
    "fetch_pubchem_compound_safety",
    "fetch_chembl_toxicity",
    "fetch_admetlab_prediction",
    "fetch_tox21_data",
    "fetch_drug_interactions",
    "calculate_toxicity_relevant_properties",
    "assess_toxicity_risk",
    # ML models
    "ToxicityModelManager",
    "ToxicityModel",
    "ToxicityPrediction",
    "TOXICITY_ENDPOINTS",
    "load_pretrained_models",
    "create_synthetic_toxicity_data",
    # Database
    "initialize_ds_database",
    "get_ds_db_version",
    "store_ds_analysis_run",
    "store_ds_pubchem_toxicity",
    "store_ds_chembl_toxicity",
    "store_ds_admetlab_prediction",
    "store_ds_ml_predictions",
    "store_ds_drug_interactions",
    "store_ds_model_metadata",
    "get_ds_analysis_run",
    "get_ds_pubchem_toxicity",
    "get_ds_chembl_toxicity",
    "get_ds_admetlab_prediction",
    "get_ds_ml_predictions",
    "get_ds_drug_interactions",
    "get_ds_models",
    "get_recent_ds_runs",
    "search_ds_runs",
    "clear_ds_analysis_run",
    # Reports
    "generate_ds_pdf_report",
    "generate_ds_csv_report",
    "generate_ds_json_report",
    # UI
    "render_drug_safety_dashboard",
]

__version__ = "4.11.0"