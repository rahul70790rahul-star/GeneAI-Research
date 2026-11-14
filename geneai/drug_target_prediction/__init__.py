"""Drug-Target Interaction Prediction module for GeneAI Research - Phase 4.7."""

from .binding_affinity import (
    estimate_binding_affinity,
    analyze_binding_site_compatibility,
    get_chembl_affinity_data,
    calculate_ligand_efficiency,
    classify_binding_potency,
    generate_affinity_report,
)

from .ml_models import (
    DrugTargetPredictor,
    create_sample_training_data,
    train_chembl_model,
    MODEL_TYPES,
    DEFAULT_RF_PARAMS,
    DEFAULT_GB_PARAMS,
    DEFAULT_LR_PARAMS,
)

from .molecular_descriptors import (
    calculate_molecular_descriptors,
    calculate_morgan_fingerprint,
    calculate_maccs_keys,
    calculate_rdkit_fingerprint,
    calculate_all_fingerprints,
    smiles_to_features,
    batch_calculate_descriptors,
    batch_calculate_fingerprints,
    get_descriptor_names,
    is_rdkit_available,
    DESCRIPTOR_NAMES,
)

from .prediction_engine import (
    DrugTargetPredictionEngine,
    create_engine,
    predict_drug_target_interactions,
)

from .visualization import (
    create_prediction_confidence_chart,
    create_target_profile_heatmap,
    create_affinity_scatter,
    create_feature_importance_chart,
    create_training_history_chart,
    create_drug_property_radar,
    create_interaction_network,
    create_comparison_chart,
)

from .report_generator import (
    generate_prediction_report_csv,
    generate_affinity_report_csv,
    generate_comprehensive_report_json,
    generate_target_profile_report,
    generate_batch_screening_report,
    generate_model_performance_report,
    export_predictions_for_external_tools,
)

from .drug_target_ui import render_drug_target_prediction_dashboard

__all__ = [
    # Binding Affinity
    "estimate_binding_affinity",
    "analyze_binding_site_compatibility",
    "get_chembl_affinity_data",
    "calculate_ligand_efficiency",
    "classify_binding_potency",
    "generate_affinity_report",
    # ML Models
    "DrugTargetPredictor",
    "create_sample_training_data",
    "train_chembl_model",
    "MODEL_TYPES",
    "DEFAULT_RF_PARAMS",
    "DEFAULT_GB_PARAMS",
    "DEFAULT_LR_PARAMS",
    # Molecular Descriptors
    "calculate_molecular_descriptors",
    "calculate_morgan_fingerprint",
    "calculate_maccs_keys",
    "calculate_rdkit_fingerprint",
    "calculate_all_fingerprints",
    "smiles_to_features",
    "batch_calculate_descriptors",
    "batch_calculate_fingerprints",
    "get_descriptor_names",
    "is_rdkit_available",
    "DESCRIPTOR_NAMES",
    # Prediction Engine
    "DrugTargetPredictionEngine",
    "create_engine",
    "predict_drug_target_interactions",
    # Visualization
    "create_prediction_confidence_chart",
    "create_target_profile_heatmap",
    "create_affinity_scatter",
    "create_feature_importance_chart",
    "create_training_history_chart",
    "create_drug_property_radar",
    "create_interaction_network",
    "create_comparison_chart",
    # Reports
    "generate_prediction_report_csv",
    "generate_affinity_report_csv",
    "generate_comprehensive_report_json",
    "generate_target_profile_report",
    "generate_batch_screening_report",
    "generate_model_performance_report",
    "export_predictions_for_external_tools",
    # UI
    "render_drug_target_prediction_dashboard",
]