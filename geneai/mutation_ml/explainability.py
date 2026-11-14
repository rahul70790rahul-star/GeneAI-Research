"""SHAP explainability for mutation ML models."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

warnings.filterwarnings("ignore", category=UserWarning)

from geneai.mutation_ml.training import TrainingResult

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    """Result of SHAP explanation."""
    variant_id: str
    shap_values: np.ndarray
    feature_names: list[str]
    base_value: float
    prediction: float
    feature_values: np.ndarray
    top_positive: list[dict[str, Any]]
    top_negative: list[dict[str, Any]]
    summary: str


class MutationExplainer:
    """SHAP-based explainer for mutation pathogenicity models."""

    def __init__(
        self,
        training_result: TrainingResult,
        background_data: np.ndarray | None = None,
        max_background_samples: int = 100,
    ):
        if not SHAP_AVAILABLE:
            raise ImportError("SHAP is required for explainability. Install with: pip install shap")

        self.training_result = training_result
        self.model = training_result.model
        self.preprocessor = training_result.preprocessor
        self.feature_names = training_result.preprocessor.feature_names if training_result.preprocessor else []
        self.background_data = background_data
        self.max_background_samples = max_background_samples
        self._explainer = None
        self._expected_value = None

    def _get_explainer(self) -> shap.Explainer:
        """Get or create SHAP explainer."""
        if self._explainer is not None:
            return self._explainer

        # Get underlying classifier
        model = self.model
        
        # Unwrap CalibratedClassifierCV if present (can be nested)
        while hasattr(model, "estimator"):
            model = model.estimator
        while hasattr(model, "base_estimator_"):
            model = model.base_estimator_
        
        # Unwrap Pipeline to get classifier
        if hasattr(model, "named_steps"):
            # For Pipeline, get the classifier step
            classifier = model.named_steps.get("classifier", model)
            # If classifier is CalibratedClassifierCV, unwrap it
            while hasattr(classifier, "estimator"):
                classifier = classifier.estimator
            while hasattr(classifier, "base_estimator_"):
                classifier = classifier.base_estimator_
            # If it's a pipeline, get the final step
            if hasattr(classifier, "named_steps"):
                classifier = classifier.named_steps.get("classifier", classifier)
        else:
            classifier = model
        
        # For calibrated models, the fitted classifier is in the calibrated classifiers
        # Check if the original model has calibrated_classifiers_
        if hasattr(self.model, "calibrated_classifiers_") and len(self.model.calibrated_classifiers_) > 0:
            # Get the first calibrated classifier
            cal_clf = self.model.calibrated_classifiers_[0]
            # The fitted pipeline is in cal_clf.estimator
            if hasattr(cal_clf, "estimator") and hasattr(cal_clf.estimator, "named_steps"):
                fitted_classifier = cal_clf.estimator.named_steps.get("classifier")
                if fitted_classifier is not None and hasattr(fitted_classifier, "coef_"):
                    classifier = fitted_classifier

        # Create background data if not provided
        if self.background_data is None and self.preprocessor:
            # Use a sample of training data as background
            logger.warning("No background data provided. Using k-means summary of training data.")
            n_background = max(100, min(500, len(self.feature_names) * 2))
            # Create synthetic background data with variation
            background_df = pd.DataFrame(
                np.random.randn(n_background, len(self.feature_names)),
                columns=self.feature_names
            )
            self.background_data = shap.kmeans(self.preprocessor.transform(background_df), min(10, n_background))

        # Choose explainer based on model type
        if hasattr(classifier, "predict_proba"):
            # Tree-based models
            if hasattr(classifier, "feature_importances_"):
                if hasattr(classifier, "estimators_"):  # Random Forest
                    self._explainer = shap.TreeExplainer(classifier)
                else:  # Gradient Boosting, XGBoost, LightGBM
                    self._explainer = shap.TreeExplainer(classifier)
            elif hasattr(classifier, "coef_"):
                # Linear models - use coefficients directly (simpler and more reliable)
                self._explainer = "linear_coef"
                self._linear_classifier = classifier
            else:
                # Fallback to permutation explainer
                self._explainer = shap.PermutationExplainer(
                    classifier.predict_proba, self.background_data
                )
        else:
            # Fallback to permutation explainer
            self._explainer = shap.PermutationExplainer(
                classifier.predict_proba, self.background_data
            )

        # For linear models, expected value = intercept + coef * E[x]
        if self._explainer == "linear_coef":
            # For linear models, we need to use the preprocessor's feature space
            # The background data is already in the preprocessed space
            bg_data = self.background_data
            if hasattr(bg_data, "data"):
                bg_data = bg_data.data
            bg_mean = np.mean(bg_data, axis=0)
            self._background_mean = bg_mean
            # Expected value = intercept + coef * E[x]
            self._expected_value = self._linear_classifier.intercept_[0] + np.dot(self._linear_classifier.coef_[0], bg_mean)
        elif hasattr(self._explainer, "expected_value"):
            self._expected_value = self._explainer.expected_value
        else:
            # For PermutationExplainer, compute mean prediction using the model directly
            # Convert background_data to numpy array if needed
            bg_data = self.background_data
            if hasattr(bg_data, "data"):
                bg_data = bg_data.data
            bg_preds = self.model.predict_proba(bg_data)
            self._expected_value = np.mean(bg_preds[:, 1]) if bg_preds.ndim > 1 else np.mean(bg_preds)
        
        if isinstance(self._expected_value, np.ndarray):
            self._expected_value = self._expected_value[1] if len(self._expected_value) > 1 else self._expected_value[0]

        return self._explainer

    def explain(
        self,
        variant_data: pd.DataFrame | dict[str, Any] | np.ndarray,
        top_k: int = 10,
    ) -> ExplanationResult:
        """Explain a single variant prediction."""
        # Convert to DataFrame
        if isinstance(variant_data, dict):
            variant_df = pd.DataFrame([variant_data])
        elif isinstance(variant_data, np.ndarray):
            variant_df = pd.DataFrame(variant_data, columns=self.feature_names)
        else:
            variant_df = variant_data.copy()

        # Preprocess
        if self.preprocessor:
            X = self.preprocessor.transform(variant_df)
        else:
            X = variant_df.values

        # Get explainer
        explainer = self._get_explainer()

        # Compute SHAP values
        if self._explainer == "linear_coef":
            # For linear models, SHAP values = coef * (x - E[x])
            # Use background data mean as expected value
            if hasattr(self, '_background_mean'):
                bg_mean = self._background_mean
            else:
                bg_data = self.background_data
                if hasattr(bg_data, "data"):
                    bg_data = bg_data.data
                bg_mean = np.mean(bg_data, axis=0)
                self._background_mean = bg_mean
            
            # SHAP values for linear model: coef * (x - E[x])
            shap_vals = self._linear_classifier.coef_[0] * (X[0] - bg_mean)
        else:
            shap_values = explainer.shap_values(X)

            # Handle different SHAP output formats
            if isinstance(shap_values, list):
                # Binary classification - list of [class0_shap, class1_shap]
                shap_vals = shap_values[1] if len(shap_values) > 1 else shap_values[0]
            elif shap_values.ndim == 3:
                # Multi-output
                shap_vals = shap_values[:, :, 1] if shap_values.shape[2] > 1 else shap_values[:, :, 0]
            else:
                shap_vals = shap_values

            # For single sample
            if shap_vals.ndim > 1:
                shap_vals = shap_vals[0]

        # Get prediction
        pred_proba = self.model.predict_proba(X)[0, 1]
        pred_class = self.model.predict(X)[0]

        # Get feature values
        feature_vals = X[0] if X.ndim > 1 else X

        # Identify top contributing features
        abs_shap = np.abs(shap_vals)
        top_indices = np.argsort(abs_shap)[-top_k:][::-1]

        top_positive = []
        top_negative = []

        for idx in top_indices:
            feat_name = self.feature_names[idx] if idx < len(self.feature_names) else f"feature_{idx}"
            feat_val = feature_vals[idx]
            shap_val = shap_vals[idx]

            contrib = {
                "feature": feat_name,
                "value": float(feat_val) if not np.isnan(feat_val) else None,
                "shap_value": float(shap_val),
                "direction": "increases" if shap_val > 0 else "decreases",
            }

            if shap_val > 0:
                top_positive.append(contrib)
            else:
                top_negative.append(contrib)

        # Generate summary
        summary = self._generate_summary(top_positive, top_negative, pred_proba)

        return ExplanationResult(
            variant_id=variant_data.get("variant_id", "unknown") if isinstance(variant_data, dict) else "unknown",
            shap_values=shap_vals,
            feature_names=self.feature_names,
            base_value=float(self._expected_value) if self._expected_value is not None else 0.0,
            prediction=float(pred_proba),
            feature_values=feature_vals,
            top_positive=top_positive,
            top_negative=top_negative,
            summary=summary,
        )

    def _generate_summary(
        self,
        top_positive: list[dict],
        top_negative: list[dict],
        prediction: float,
    ) -> str:
        """Generate human-readable summary."""
        pred_label = "pathogenic" if prediction > 0.5 else "benign"
        confidence = "high" if abs(prediction - 0.5) > 0.3 else "medium" if abs(prediction - 0.5) > 0.1 else "low"

        pos_features = [f"{f['feature']} ({f['shap_value']:.3f})" for f in top_positive[:3]]
        neg_features = [f"{f['feature']} ({f['shap_value']:.3f})" for f in top_negative[:3]]

        summary = (
            f"Prediction: {pred_label} (probability={prediction:.3f}, confidence={confidence}). "
            f"Top factors increasing pathogenicity: {', '.join(pos_features) if pos_features else 'none'}. "
            f"Top factors decreasing pathogenicity: {', '.join(neg_features) if neg_features else 'none'}."
        )
        return summary

    def explain_batch(
        self,
        variants: pd.DataFrame,
        top_k: int = 10,
    ) -> list[ExplanationResult]:
        """Explain multiple variants."""
        results = []
        for _, row in variants.iterrows():
            try:
                result = self.explain(row.to_dict(), top_k)
                results.append(result)
            except Exception as e:
                logger.warning("Failed to explain variant: %s", e)
                continue
        return results

    def global_feature_importance(
        self,
        X: np.ndarray,
        max_samples: int = 500,
    ) -> pd.DataFrame:
        """Compute global feature importance using SHAP."""
        explainer = self._get_explainer()

        # Sample data if too large
        if len(X) > max_samples:
            indices = np.random.choice(len(X), max_samples, replace=False)
            X_sample = X[indices]
        else:
            X_sample = X

        if self._explainer == "linear_coef":
            # For linear models, mean |SHAP| = |coef| * std(x)
            # Use the background mean from preprocessed space
            shap_vals = self._linear_classifier.coef_[0] * (X_sample - self._background_mean)
            mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)
        else:
            shap_values = explainer.shap_values(X_sample)

            if isinstance(shap_values, list):
                shap_vals = shap_values[1] if len(shap_values) > 1 else shap_values[0]
            elif shap_values.ndim == 3:
                shap_vals = shap_vals[:, :, 1] if shap_vals.shape[2] > 1 else shap_vals[:, :, 0]

            mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)

        importance_df = pd.DataFrame({
            "feature": self.feature_names[:len(mean_abs_shap)],
            "mean_abs_shap": mean_abs_shap,
        }).sort_values("mean_abs_shap", ascending=False)

        return importance_df

    def plot_shap_summary(
        self,
        X: np.ndarray,
        max_samples: int = 500,
        show: bool = False,
    ) -> Any:
        """Create SHAP summary plot."""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available for plotting")
            return None

        explainer = self._get_explainer()

        if len(X) > max_samples:
            indices = np.random.choice(len(X), max_samples, replace=False)
            X_sample = X[indices]
        else:
            X_sample = X

        shap_values = explainer.shap_values(X_sample)

        if isinstance(shap_values, list):
            shap_vals = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        elif shap_values.ndim == 3:
            shap_vals = shap_vals[:, :, 1] if shap_vals.shape[2] > 1 else shap_vals[:, :, 0]

        plt.figure(figsize=(10, 8))
        shap.summary_plot(
            shap_vals,
            X_sample,
            feature_names=self.feature_names,
            show=show,
        )
        return plt.gcf()

    def plot_shap_waterfall(
        self,
        explanation: ExplanationResult,
        max_display: int = 15,
        show: bool = False,
    ) -> Any:
        """Create SHAP waterfall plot for single prediction."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        plt.figure(figsize=(10, 6))
        shap.plots.waterfall(
            shap.Explanation(
                values=explanation.shap_values,
                base_values=explanation.base_value,
                data=explanation.feature_values,
                feature_names=explanation.feature_names,
            ),
            max_display=max_display,
            show=show,
        )
        return plt.gcf()

    def plot_shap_force(
        self,
        explanation: ExplanationResult,
        show: bool = False,
    ) -> Any:
        """Create SHAP force plot for single prediction."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        shap.plots.force(
            explanation.base_value,
            explanation.shap_values,
            explanation.feature_values,
            feature_names=explanation.feature_names,
            matplotlib=True,
            show=show,
        )
        return plt.gcf()


def explain_prediction(
    training_result: TrainingResult,
    variant_data: pd.DataFrame | dict[str, Any] | np.ndarray,
    background_data: np.ndarray | None = None,
    top_k: int = 10,
) -> ExplanationResult:
    """Convenience function to explain a prediction."""
    explainer = MutationExplainer(training_result, background_data)
    return explainer.explain(variant_data, top_k)


def create_explainer(
    training_result: TrainingResult,
    background_data: np.ndarray | None = None,
) -> MutationExplainer:
    """Create a MutationExplainer instance."""
    return MutationExplainer(training_result, background_data)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("SHAP Explainer ready")
    print(f"SHAP available: {SHAP_AVAILABLE}")
    print(f"Matplotlib available: {MATPLOTLIB_AVAILABLE}")