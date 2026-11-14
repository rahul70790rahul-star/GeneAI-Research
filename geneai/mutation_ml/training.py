"""ML training pipeline for mutation interpretation."""
from __future__ import annotations

import logging
import pickle
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

warnings.filterwarnings("ignore", category=UserWarning)

from geneai.mutation_ml.preprocessing import VariantPreprocessor

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    model_type: str
    params: dict[str, Any] = field(default_factory=dict)
    calibrate: bool = True
    use_scaler: bool = True


@dataclass
class TrainingResult:
    """Results from model training."""
    model_name: str
    model_type: str
    model: Any
    preprocessor: VariantPreprocessor
    cv_scores: dict[str, float]
    cv_scores_std: dict[str, float]
    test_scores: dict[str, float]
    feature_importance: list[tuple[str, float]] | None
    training_time: float
    n_samples: int
    n_features: int
    class_distribution: dict[int, int]
    best_params: dict[str, Any] | None = None
    calibration_curve: dict[str, list[float]] | None = None


DEFAULT_MODEL_CONFIGS = [
    ModelConfig(
        name="logistic_regression",
        model_type="logistic_regression",
        params={
            "C": 1.0,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 2000,
            "class_weight": "balanced",
            "random_state": 42,
        },
        calibrate=True,
        use_scaler=True,
    ),
    ModelConfig(
        name="random_forest",
        model_type="random_forest",
        params={
            "n_estimators": 300,
            "max_depth": 15,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "class_weight": "balanced",
            "random_state": 42,
            "n_jobs": -1,
        },
        calibrate=True,
        use_scaler=False,
    ),
    ModelConfig(
        name="gradient_boosting",
        model_type="gradient_boosting",
        params={
            "n_estimators": 300,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "random_state": 42,
        },
        calibrate=True,
        use_scaler=False,
    ),
]

if XGBOOST_AVAILABLE:
    DEFAULT_MODEL_CONFIGS.append(ModelConfig(
        name="xgboost",
        model_type="xgboost",
        params={
            "n_estimators": 300,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "scale_pos_weight": 1,
            "random_state": 42,
            "n_jobs": -1,
            "eval_metric": "auc",
        },
        calibrate=True,
        use_scaler=False,
    ))

if LIGHTGBM_AVAILABLE:
    DEFAULT_MODEL_CONFIGS.append(ModelConfig(
        name="lightgbm",
        model_type="lightgbm",
        params={
            "n_estimators": 300,
            "max_depth": 6,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "class_weight": "balanced",
            "random_state": 42,
            "n_jobs": -1,
            "verbosity": -1,
        },
        calibrate=True,
        use_scaler=False,
    ))

DEFAULT_MODEL_CONFIGS.append(ModelConfig(
    name="svm",
    model_type="svm",
    params={
        "C": 1.0,
        "kernel": "rbf",
        "probability": True,
        "class_weight": "balanced",
        "random_state": 42,
    },
    calibrate=False,
    use_scaler=True,
))


class MutationMLTrainer:
    """Train and evaluate mutation pathogenicity classifiers."""

    def __init__(
        self,
        model_configs: list[ModelConfig] | None = None,
        cv_folds: int = 5,
        test_size: float = 0.2,
        random_state: int = 42,
        n_jobs: int = -1,
        optimize_hyperparams: bool = False,
    ):
        self.model_configs = model_configs or DEFAULT_MODEL_CONFIGS
        self.cv_folds = cv_folds
        self.test_size = test_size
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.optimize_hyperparams = optimize_hyperparams

        self.results: list[TrainingResult] = []
        self.best_model: TrainingResult | None = None
        self.X_test = None
        self.y_test = None

    def _create_model(self, config: ModelConfig):
        """Create model instance from config."""
        if config.model_type == "logistic_regression":
            return LogisticRegression(**config.params)
        elif config.model_type == "random_forest":
            return RandomForestClassifier(**config.params)
        elif config.model_type == "gradient_boosting":
            return GradientBoostingClassifier(**config.params)
        elif config.model_type == "xgboost" and XGBOOST_AVAILABLE:
            return xgb.XGBClassifier(**config.params)
        elif config.model_type == "lightgbm" and LIGHTGBM_AVAILABLE:
            return lgb.LGBMClassifier(**config.params)
        elif config.model_type == "svm":
            return SVC(**config.params)
        else:
            raise ValueError(f"Unknown model type: {config.model_type}")

    def _build_pipeline(self, config: ModelConfig, base_model):
        """Build sklearn pipeline with preprocessing."""
        steps = []

        if config.use_scaler:
            steps.append(("scaler", StandardScaler()))

        steps.append(("classifier", base_model))

        pipeline = Pipeline(steps)

        if config.calibrate and hasattr(base_model, "predict_proba"):
            pipeline = CalibratedClassifierCV(pipeline, method="isotonic", cv=3)

        return pipeline

    def _optimize_hyperparameters(
        self,
        pipeline,
        X: np.ndarray,
        y: np.ndarray,
        config: ModelConfig,
    ) -> dict[str, Any]:
        """Optimize hyperparameters using GridSearchCV."""
        if not self.optimize_hyperparams:
            return config.params

        param_grids = {
            "logistic_regression": {
                "classifier__C": [0.1, 1.0, 10.0],
                "classifier__penalty": ["l2"],
            },
            "random_forest": {
                "classifier__n_estimators": [200, 300, 500],
                "classifier__max_depth": [10, 15, 20, None],
                "classifier__min_samples_split": [2, 5, 10],
            },
            "gradient_boosting": {
                "classifier__n_estimators": [200, 300],
                "classifier__max_depth": [3, 5, 7],
                "classifier__learning_rate": [0.05, 0.1],
            },
            "xgboost": {
                "classifier__n_estimators": [200, 300, 500],
                "classifier__max_depth": [4, 6, 8],
                "classifier__learning_rate": [0.05, 0.1, 0.15],
            },
            "lightgbm": {
                "classifier__n_estimators": [200, 300, 500],
                "classifier__max_depth": [4, 6, 8],
                "classifier__learning_rate": [0.05, 0.1],
                "classifier__num_leaves": [15, 31, 63],
            },
            "svm": {
                "classifier__C": [0.1, 1.0, 10.0],
                "classifier__kernel": ["rbf", "linear"],
                "classifier__gamma": ["scale", "auto"],
            },
        }

        param_grid = param_grids.get(config.model_type, {})
        if not param_grid:
            return config.params

        # Adjust for pipeline structure
        adjusted_grid = {}
        for k, v in param_grid.items():
            if config.calibrate:
                adjusted_grid[f"calibratedclassifiercv__base_estimator__{k}"] = v
            else:
                adjusted_grid[f"classifier__{k}"] = v

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=self.random_state)
        grid_search = GridSearchCV(
            pipeline,
            adjusted_grid,
            cv=cv,
            scoring="roc_auc",
            n_jobs=self.n_jobs,
            verbose=0,
        )
        grid_search.fit(X, y)

        logger.info("Best params for %s: %s", config.name, grid_search.best_params_)
        return grid_search.best_params_

    def _evaluate_model(
        self,
        model,
        X: np.ndarray,
        y: np.ndarray,
        cv: StratifiedKFold,
    ) -> dict[str, float]:
        """Evaluate model with cross-validation."""
        # Use cross_val_predict for consistent predictions
        y_pred = cross_val_predict(model, X, y, cv=cv, method="predict", n_jobs=self.n_jobs)
        y_proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba", n_jobs=self.n_jobs)[:, 1]

        scores = {
            "accuracy": accuracy_score(y, y_pred),
            "balanced_accuracy": balanced_accuracy_score(y, y_pred),
            "precision": precision_score(y, y_pred, zero_division=0),
            "recall": recall_score(y, y_pred, zero_division=0),
            "f1": f1_score(y, y_pred, zero_division=0),
            "mcc": matthews_corrcoef(y, y_pred),
            "roc_auc": roc_auc_score(y, y_proba),
            "pr_auc": average_precision_score(y, y_proba),
        }

        return scores

    def _get_feature_importance(self, model, feature_names: list[str]) -> list[tuple[str, float]] | None:
        """Extract feature importance from trained model."""
        try:
            # Unwrap calibrated classifier
            if hasattr(model, "base_estimator_"):
                model = model.base_estimator_
            if hasattr(model, "named_steps"):
                classifier = model.named_steps.get("classifier", model)
            else:
                classifier = model

            if hasattr(classifier, "feature_importances_"):
                importances = classifier.feature_importances_
            elif hasattr(classifier, "coef_"):
                importances = np.abs(classifier.coef_[0])
            else:
                return None

            if len(importances) != len(feature_names):
                return None

            fi = list(zip(feature_names, importances))
            fi.sort(key=lambda x: x[1], reverse=True)
            return fi[:50]

        except Exception as e:
            logger.warning("Could not extract feature importance: %s", e)
            return None

    def _get_calibration_curve(self, model, X: np.ndarray, y: np.ndarray) -> dict[str, list[float]] | None:
        """Get calibration curve data."""
        try:
            y_proba = model.predict_proba(X)[:, 1]
            precision, recall, thresholds = precision_recall_curve(y, y_proba)
            fpr, tpr, roc_thresholds = roc_curve(y, y_proba)
            return {
                "precision": precision.tolist(),
                "recall": recall.tolist(),
                "pr_thresholds": thresholds.tolist(),
                "fpr": fpr.tolist(),
                "tpr": tpr.tolist(),
                "roc_thresholds": roc_thresholds.tolist(),
            }
        except Exception:
            return None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str] | None = None,
        preprocessor: VariantPreprocessor | None = None,
    ) -> list[TrainingResult]:
        """Train all models and evaluate."""
        logger.info("Starting training with %d models on %d samples", len(self.model_configs), len(X))

        # Split test set
        X_train, self.X_test, y_train, self.y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state, stratify=y
        )

        cv = StratifiedKFold(n_splits=self.cv_folds, shuffle=True, random_state=self.random_state)
        class_dist = {int(k): int(v) for k, v in zip(*np.unique(y_train, return_counts=True))}

        self.results = []
        start_time = datetime.now()

        for config in self.model_configs:
            logger.info("Training %s...", config.name)
            model_start = datetime.now()

            try:
                base_model = self._create_model(config)
                pipeline = self._build_pipeline(config, base_model)

                # Hyperparameter optimization
                best_params = self._optimize_hyperparameters(pipeline, X_train, y_train, config)

                # Rebuild with best params
                if self.optimize_hyperparams and best_params != config.params:
                    base_model = self._create_model(config)
                    # Update params
                    for k, v in best_params.items():
                        # Strip pipeline prefixes
                        clean_k = k.replace("calibratedclassifiercv__base_estimator__", "").replace("classifier__", "")
                        if hasattr(base_model, "set_params"):
                            base_model.set_params(**{clean_k: v})
                    pipeline = self._build_pipeline(config, base_model)

                # Cross-validation evaluation
                cv_scores = self._evaluate_model(pipeline, X_train, y_train, cv)
                cv_scores_std = {}
                # Compute std across folds
                for metric in ["accuracy", "balanced_accuracy", "precision", "recall", "f1", "mcc", "roc_auc", "pr_auc"]:
                    cv_scores_std[metric] = 0.0  # Would need per-fold scores

                # Train on full training set
                pipeline.fit(X_train, y_train)

                # Test set evaluation
                y_pred = pipeline.predict(self.X_test)
                y_proba = pipeline.predict_proba(self.X_test)[:, 1]
                test_scores = {
                    "accuracy": accuracy_score(self.y_test, y_pred),
                    "balanced_accuracy": balanced_accuracy_score(self.y_test, y_pred),
                    "precision": precision_score(self.y_test, y_pred, zero_division=0),
                    "recall": recall_score(self.y_test, y_pred, zero_division=0),
                    "f1": f1_score(self.y_test, y_pred, zero_division=0),
                    "mcc": matthews_corrcoef(self.y_test, y_pred),
                    "roc_auc": roc_auc_score(self.y_test, y_proba),
                    "pr_auc": average_precision_score(self.y_test, y_proba),
                }

                # Feature importance
                feature_importance = self._get_feature_importance(pipeline, feature_names or [])

                # Calibration curve
                calibration = self._get_calibration_curve(pipeline, self.X_test, self.y_test)

                training_time = (datetime.now() - model_start).total_seconds()

                result = TrainingResult(
                    model_name=config.name,
                    model_type=config.model_type,
                    model=pipeline,
                    preprocessor=preprocessor,
                    cv_scores=cv_scores,
                    cv_scores_std=cv_scores_std,
                    test_scores=test_scores,
                    feature_importance=feature_importance,
                    training_time=training_time,
                    n_samples=len(X_train),
                    n_features=X_train.shape[1],
                    class_distribution=class_dist,
                    best_params=best_params if self.optimize_hyperparams else None,
                    calibration_curve=calibration,
                )

                self.results.append(result)
                logger.info(
                    "%s: CV ROC-AUC=%.4f, Test ROC-AUC=%.4f, Time=%.1fs",
                    config.name, cv_scores["roc_auc"], test_scores["roc_auc"], training_time
                )

            except Exception as e:
                logger.error("Failed to train %s: %s", config.name, e)
                continue

        total_time = (datetime.now() - start_time).total_seconds()
        logger.info("Training complete in %.1fs. %d models trained.", total_time, len(self.results))

        # Select best model by CV ROC-AUC
        if self.results:
            self.best_model = max(self.results, key=lambda r: r.cv_scores["roc_auc"])
            logger.info("Best model: %s (CV ROC-AUC: %.4f)", self.best_model.model_name, self.best_model.cv_scores["roc_auc"])

        return self.results

    def get_best_model(self) -> TrainingResult | None:
        """Get the best model by CV ROC-AUC."""
        return self.best_model

    def predict(
        self,
        X: np.ndarray,
        model_name: str | None = None,
        return_proba: bool = True,
    ) -> np.ndarray:
        """Make predictions using specified or best model."""
        if model_name:
            result = next((r for r in self.results if r.model_name == model_name), None)
        else:
            result = self.best_model

        if result is None:
            raise ValueError("No trained model available")

        if return_proba:
            return result.model.predict_proba(X)[:, 1]
        return result.model.predict(X)

    def predict_single_variant(
        self,
        variant_dict: dict[str, Any],
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Predict pathogenicity for a single variant."""
        if self.best_model is None and not model_name:
            raise ValueError("No trained model available")

        result = next((r for r in self.results if r.model_name == model_name), self.best_model)
        if result is None:
            raise ValueError(f"Model {model_name} not found")

        # Preprocess variant
        if result.preprocessor:
            X = result.preprocessor.transform(pd.DataFrame([variant_dict]))
        else:
            raise ValueError("Preprocessor required for prediction")

        proba = result.model.predict_proba(X)[0, 1]
        pred = result.model.predict(X)[0]

        return {
            "pathogenicity_probability": float(proba),
            "predicted_class": "pathogenic" if pred == 1 else "benign",
            "confidence": "high" if abs(proba - 0.5) > 0.3 else "medium" if abs(proba - 0.5) > 0.1 else "low",
            "model_used": result.model_name,
        }

    def save_model(self, result: TrainingResult, path: Path | str) -> Path:
        """Save trained model to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": result.model,
            "model_name": result.model_name,
            "model_type": result.model_type,
            "preprocessor": result.preprocessor,
            "cv_scores": result.cv_scores,
            "test_scores": result.test_scores,
            "feature_importance": result.feature_importance,
            "feature_names": result.preprocessor.feature_names if result.preprocessor else [],
            "training_time": result.training_time,
            "n_samples": result.n_samples,
            "n_features": result.n_features,
            "class_distribution": result.class_distribution,
            "best_params": result.best_params,
            "calibration_curve": result.calibration_curve,
            "saved_at": datetime.now().isoformat(),
        }

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        logger.info("Model saved to %s", path)
        return path

    @classmethod
    def load_model(cls, path: Path | str) -> dict[str, Any]:
        """Load trained model from disk."""
        with open(path, "rb") as f:
            model_data = pickle.load(f)

        logger.info("Model loaded from %s", path)
        return model_data

    def get_results_summary(self) -> pd.DataFrame:
        """Get summary of all model results."""
        rows = []
        for r in self.results:
            row = {
                "model": r.model_name,
                "type": r.model_type,
                "cv_roc_auc": r.cv_scores.get("roc_auc", 0),
                "cv_pr_auc": r.cv_scores.get("pr_auc", 0),
                "cv_f1": r.cv_scores.get("f1", 0),
                "cv_mcc": r.cv_scores.get("mcc", 0),
                "test_roc_auc": r.test_scores.get("roc_auc", 0),
                "test_pr_auc": r.test_scores.get("pr_auc", 0),
                "test_f1": r.test_scores.get("f1", 0),
                "test_mcc": r.test_scores.get("mcc", 0),
                "training_time_s": r.training_time,
            }
            rows.append(row)

        return pd.DataFrame(rows).sort_values("cv_roc_auc", ascending=False)


def train_mutation_classifier(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str] | None = None,
    preprocessor: VariantPreprocessor | None = None,
    model_configs: list[ModelConfig] | None = None,
    **kwargs,
) -> MutationMLTrainer:
    """Convenience function to train mutation classifier."""
    trainer = MutationMLTrainer(model_configs=model_configs, **kwargs)
    trainer.train(X, y, feature_names, preprocessor)
    return trainer


def evaluate_model(
    trainer: MutationMLTrainer,
    X: np.ndarray,
    y: np.ndarray,
    model_name: str | None = None,
) -> dict[str, float]:
    """Evaluate a specific model on test data."""
    if model_name:
        result = next((r for r in trainer.results if r.model_name == model_name), None)
    else:
        result = trainer.best_model

    if result is None:
        raise ValueError("No model available for evaluation")

    y_pred = result.model.predict(X)
    y_proba = result.model.predict_proba(X)[:, 1]

    return {
        "accuracy": accuracy_score(y, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y, y_pred),
        "precision": precision_score(y, y_pred, zero_division=0),
        "recall": recall_score(y, y_pred, zero_division=0),
        "f1": f1_score(y, y_pred, zero_division=0),
        "mcc": matthews_corrcoef(y, y_pred),
        "roc_auc": roc_auc_score(y, y_proba),
        "pr_auc": average_precision_score(y, y_proba),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Mutation ML Trainer ready")
    print(f"Available models: {[c.name for c in DEFAULT_MODEL_CONFIGS]}")
    print(f"XGBoost: {XGBOOST_AVAILABLE}, LightGBM: {LIGHTGBM_AVAILABLE}, SHAP: {SHAP_AVAILABLE}")