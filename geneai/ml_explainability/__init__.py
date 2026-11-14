"""GeneAI ML Explainability - Phase 5 Enhancement."""
from __future__ import annotations

# SHAP is an optional dependency - import lazily
try:
    from geneai.ml_explainability.shap_explainer import (
        SHAPExplainer,
        create_admet_explainer,
        create_safety_explainer,
        create_ranking_explainer,
        create_target_explainer,
        batch_explain_with_shap,
        shap_values_to_dataframe,
        compute_shap_interaction_values,
        create_shap_force_plot,
        SHAP_AVAILABLE,
    )
    _SHAP_IMPORTED = True
except ImportError:
    # SHAP not available - provide placeholder
    SHAPExplainer = None
    create_admet_explainer = None
    create_safety_explainer = None
    create_ranking_explainer = None
    create_target_explainer = None
    batch_explain_with_shap = None
    shap_values_to_dataframe = None
    compute_shap_interaction_values = None
    create_shap_force_plot = None
    SHAP_AVAILABLE = False
    _SHAP_IMPORTED = False

__all__ = [
    "SHAPExplainer",
    "create_admet_explainer",
    "create_safety_explainer",
    "create_ranking_explainer",
    "create_target_explainer",
    "batch_explain_with_shap",
    "shap_values_to_dataframe",
    "compute_shap_interaction_values",
    "create_shap_force_plot",
    "SHAP_AVAILABLE",
]

__version__ = "5.13.0"