"""SHAP Explainability Module for ML Models - Phase 5 Enhancement."""
from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    shap = None

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Lazy imports for optional GeneAI modules
_ADMETModel = None
_ADMETModelManager = None
_ToxicityModelManager = None
_ToxicityModel = None
_BiomarkerDiscoveryEngine = None
_AICandidateRanker = None
_CandidateFeatures = None
_DrugTargetPredictor = None
_train_evaluate_target_model = None

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


def _import_admet():
    global _ADMETModel, _ADMETModelManager
    if _ADMETModel is None:
        try:
            from geneai.admet_prediction.ml_models import ADMETModel, ADMETModelManager
            _ADMETModel = ADMETModel
            _ADMETModelManager = ADMETModelManager
        except ImportError:
            _ADMETModel = object
            _ADMETModelManager = object
    return _ADMETModelManager


def _import_safety():
    global _ToxicityModelManager, _ToxicityModel
    if _ToxicityModel is None:
        try:
            from geneai.drug_safety.ml_models import ToxicityModelManager, ToxicityModel
            _ToxicityModelManager = ToxicityModelManager
            _ToxicityModel = ToxicityModel
        except ImportError:
            _ToxicityModel = object
            _ToxicityModelManager = object
    return _ToxicityModelManager


def _import_biomarker():
    global _BiomarkerDiscoveryEngine
    if _BiomarkerDiscoveryEngine is None:
        try:
            from geneai.biomarker_discovery.ml_engine import BiomarkerDiscoveryEngine
            _BiomarkerDiscoveryEngine = BiomarkerDiscoveryEngine
        except ImportError:
            _BiomarkerDiscoveryEngine = object
    return _BiomarkerDiscoveryEngine


def _import_ranking():
    global _AICandidateRanker, _CandidateFeatures
    if _AICandidateRanker is None:
        try:
            from geneai.ai_research_intelligence.ai_candidate_ranking import AICandidateRanker, CandidateFeatures
            _AICandidateRanker = AICandidateRanker
            _CandidateFeatures = CandidateFeatures
        except ImportError:
            _AICandidateRanker = object
            _CandidateFeatures = object
    return _AICandidateRanker


def _import_drug_target():
    global _DrugTargetPredictor, _train_evaluate_target_model
    if _DrugTargetPredictor is None:
        try:
            from geneai.drug_target_prediction.ml_models import DrugTargetPredictor
            from geneai.drug_discovery.target_ml import train_evaluate_target_model
            _DrugTargetPredictor = DrugTargetPredictor
            _train_evaluate_target_model = train_evaluate_target_model
        except ImportError:
            _DrugTargetPredictor = object
            _train_evaluate_target_model = None
    return _DrugTargetPredictor


class SHAPExplainer:
    """Unified SHAP explainer for various model types."""

    def __init__(self, model: Any, feature_names: list[str], model_type: str = "tree"):
        """
        Initialize SHAP explainer.

        Args:
            model: Trained model (sklearn pipeline, xgboost, lightgbm, etc.)
            feature_names: List of feature names
            model_type: "tree" for tree-based, "linear" for linear, "kernel" for model-agnostic
        """
        if not SHAP_AVAILABLE:
            raise ImportError("SHAP is required. Install with: pip install shap")

        self.model = model
        self.feature_names = feature_names
        self.model_type = model_type
        self.explainer = None
        self._create_explainer()

    def _create_explainer(self):
        """Create appropriate SHAP explainer based on model type."""
        if self.model_type == "tree":
            # TreeSHAP for tree-based models (XGBoost, LightGBM, RF, GB)
            self.explainer = shap.TreeExplainer(self.model)
        elif self.model_type == "linear":
            # LinearSHAP for linear models
            self.explainer = shap.LinearExplainer(self.model, np.zeros((1, len(self.feature_names))))
        else:
            # KernelSHAP for model-agnostic (slower)
            self.explainer = shap.KernelExplainer(
                self.model.predict_proba if hasattr(self.model, "predict_proba") else self.model.predict,
                np.zeros((1, len(self.feature_names)))
            )

    def explain_instance(self, instance: np.ndarray) -> dict[str, Any]:
        """
        Explain a single prediction.

        Args:
            instance: Single sample features (1D array)

        Returns:
            Dictionary with SHAP values, base value, and feature contributions
        """
        if instance.ndim == 1:
            instance = instance.reshape(1, -1)

        shap_values = self.explainer.shap_values(instance)

        # Handle multi-class (take class 1 for binary)
        if isinstance(shap_values, list):
            shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        if shap_values.ndim == 3:
            shap_values = shap_values[:, :, 1] if shap_values.shape[2] > 1 else shap_values[:, :, 0]

        base_value = self.explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            base_value = base_value[1] if len(base_value) > 1 else base_value[0]

        return {
            "shap_values": shap_values[0].tolist() if shap_values.ndim > 1 else shap_values.tolist(),
            "base_value": float(base_value),
            "feature_names": self.feature_names,
            "feature_values": instance[0].tolist(),
        }

    def explain_batch(self, instances: np.ndarray) -> dict[str, Any]:
        """Explain multiple predictions."""
        shap_values = self.explainer.shap_values(instances)

        if isinstance(shap_values, list):
            shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        if shap_values.ndim == 3:
            shap_values = shap_values[:, :, 1] if shap_values.shape[2] > 1 else shap_values[:, :, 0]

        base_value = self.explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            base_value = base_value[1] if len(base_value) > 1 else base_value[0]

        return {
            "shap_values": shap_values.tolist(),
            "base_value": float(base_value),
            "feature_names": self.feature_names,
            "feature_values": instances.tolist(),
        }

    def get_global_importance(self, instances: np.ndarray) -> pd.DataFrame:
        """Get global feature importance from SHAP values."""
        result = self.explain_batch(instances)
        shap_vals = np.array(result["shap_values"])

        # Mean absolute SHAP value per feature
        mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)

        importance_df = pd.DataFrame({
            "feature": self.feature_names,
            "mean_abs_shap": mean_abs_shap,
            "std_shap": np.std(shap_vals, axis=0),
        }).sort_values("mean_abs_shap", ascending=False)

        return importance_df

    def plot_summary(self, instances: np.ndarray, max_display: int = 20, show: bool = True):
        """Create SHAP summary plot."""
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib required for plotting")

        shap_vals = self.explainer.shap_values(instances)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]
        if shap_vals.ndim == 3:
            shap_vals = shap_vals[:, :, 1] if shap_vals.shape[2] > 1 else shap_vals[:, :, 0]

        shap.summary_plot(
            shap_vals,
            instances,
            feature_names=self.feature_names,
            max_display=max_display,
            show=show,
        )

    def plot_waterfall(self, instance: np.ndarray, max_display: int = 15, show: bool = True):
        """Create SHAP waterfall plot for single instance."""
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib required for plotting")

        explanation = self.explain_instance(instance)

        # Create SHAP Explanation object
        exp = shap.Explanation(
            values=np.array(explanation["shap_values"]),
            base_values=explanation["base_value"],
            data=np.array(explanation["feature_values"]),
            feature_names=explanation["feature_names"],
        )

        shap.plots.waterfall(exp, max_display=max_display, show=show)

    def plot_dependence(self, instances: np.ndarray, feature: str, interaction_feature: str = "auto", show: bool = True):
        """Create SHAP dependence plot."""
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib required for plotting")

        shap_vals = self.explainer.shap_values(instances)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]
        if shap_vals.ndim == 3:
            shap_vals = shap_vals[:, :, 1] if shap_vals.shape[2] > 1 else shap_vals[:, :, 0]

        feature_idx = self.feature_names.index(feature)
        shap.dependence_plot(
            feature_idx,
            shap_vals,
            instances,
            feature_names=self.feature_names,
            interaction_index=interaction_feature,
            show=show,
        )


def create_admet_explainer(model_manager: Any, endpoint: str, background_data: np.ndarray = None) -> SHAPExplainer | None:
    """Create SHAP explainer for ADMET model."""
    _import_admet()
    model = model_manager.get_model(endpoint)
    if model is None or not getattr(model, "is_fitted", False):
        return None

    # Determine model type
    classifier = getattr(model, "pipeline", {}).named_steps.get("classifier") if hasattr(getattr(model, "pipeline", {}), "named_steps") else None
    model_type = "tree"  # RF, GB, XGB, LGB are all tree-based

    # Use background data for KernelExplainer if needed
    if background_data is not None and model_type != "tree":
        explainer = SHAPExplainer(model.pipeline, model.feature_names, model_type="kernel")
    else:
        explainer = SHAPExplainer(model.pipeline, model.feature_names, model_type)

    return explainer


def create_safety_explainer(model_manager: Any, endpoint: str) -> SHAPExplainer | None:
    """Create SHAP explainer for toxicity model."""
    _import_safety()
    if not hasattr(model_manager, "models") or endpoint not in model_manager.models:
        return None

    model_obj = model_manager.models[endpoint]
    return SHAPExplainer(getattr(model_obj, "model", model_obj), getattr(model_obj, "feature_names", []), model_type="tree")


def create_biomarker_explainer(engine: Any, model_name: str) -> SHAPExplainer | None:
    """Create SHAP explainer for biomarker model."""
    _import_biomarker()
    # Would need to store trained models in engine
    # This is a placeholder for integration
    return None


def create_ranking_explainer(ranker: Any) -> SHAPExplainer | None:
    """Create SHAP explainer for candidate ranker."""
    _import_ranking()
    if not getattr(ranker, "is_trained", False) or getattr(ranker, "model", None) is None:
        return None

    return SHAPExplainer(ranker.model, getattr(ranker, "feature_names", []), model_type="tree")


def create_target_explainer(predictor: Any) -> SHAPExplainer | None:
    """Create SHAP explainer for drug-target predictor."""
    _import_drug_target()
    if not getattr(predictor, "is_fitted", False):
        return None

    return SHAPExplainer(getattr(predictor, "pipeline", predictor), getattr(predictor, "feature_names", []), model_type="tree")


def batch_explain_with_shap(models: dict[str, Any], feature_names: list[str], instances: np.ndarray) -> dict[str, dict[str, Any]]:
    """Batch explain multiple models with SHAP."""
    results = {}
    for name, model in models.items():
        explainer = SHAPExplainer(model, feature_names, model_type="tree")
        results[name] = explainer.explain_batch(instances)
    return results


def shap_values_to_dataframe(shap_values: np.ndarray, feature_names: list[str], feature_values: np.ndarray = None) -> pd.DataFrame:
    """Convert SHAP values to DataFrame for analysis."""
    df = pd.DataFrame(shap_values, columns=feature_names)
    if feature_values is not None:
        for i, name in enumerate(feature_names):
            df[f"{name}_value"] = feature_values[:, i] if feature_values.ndim > 1 else feature_values[i]
    return df


def compute_shap_interaction_values(explainer: SHAPExplainer, instances: np.ndarray) -> np.ndarray:
    """Compute SHAP interaction values (only for TreeExplainer)."""
    if not SHAP_AVAILABLE or not isinstance(explainer.explainer, shap.TreeExplainer):
        raise ValueError("Interaction values only available for TreeExplainer")
    return explainer.explainer.shap_interaction_values(instances)


def create_shap_force_plot(explainer: SHAPExplainer, instance: np.ndarray, show: bool = True):
    """Create SHAP force plot for single instance."""
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError("matplotlib required for plotting")

    explanation = explainer.explain_instance(instance)
    exp = shap.Explanation(
        values=np.array(explanation["shap_values"]),
        base_values=explanation["base_value"],
        data=np.array(explanation["feature_values"]),
        feature_names=explanation["feature_names"],
    )
    shap.plots.force(exp, show=show)