"""Optuna Hyperparameter Optimization Module for ML Models - Phase 5 Enhancement."""
from __future__ import annotations

import logging
import pickle
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import optuna
    from optuna.samplers import TPESampler
    from optuna.pruners import MedianPruner
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False

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

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

# Lazy imports for optional GeneAI modules
_ADMETModel = None
_ToxicityModelManager = None
_TOXICITY_ENDPOINTS = None
_BiomarkerDiscoveryEngine = None
_AICandidateRanker = None
_CandidateFeatures = None
_DrugTargetPredictor = None
_train_evaluate_target_model = None

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


def _import_admet():
    global _ADMETModel
    if _ADMETModel is None:
        try:
            from geneai.admet_prediction.ml_models import ADMETModel
            _ADMETModel = ADMETModel
        except ImportError:
            _ADMETModel = object
    return _ADMETModel


def _import_safety():
    global _ToxicityModelManager, _TOXICITY_ENDPOINTS
    if _ToxicityModelManager is None:
        try:
            from geneai.drug_safety.ml_models import ToxicityModelManager, TOXICITY_ENDPOINTS
            _ToxicityModelManager = ToxicityModelManager
            _TOXICITY_ENDPOINTS = TOXICITY_ENDPOINTS
        except ImportError:
            _ToxicityModelManager = object
            _TOXICITY_ENDPOINTS = {}
    return _ToxicityModelManager, _TOXICITY_ENDPOINTS


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
    return _AICandidateRanker, _CandidateFeatures


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


@dataclass
class OptimizationConfig:
    """Configuration for hyperparameter optimization."""
    n_trials: int = 100
    timeout: int | None = None  # seconds
    cv_folds: int = 5
    scoring: str = "roc_auc"  # or "accuracy", "f1", "r2", "neg_mse"
    direction: str = "maximize"  # or "minimize"
    sampler: str = "tpe"  # "tpe", "random", "cmaes"
    pruner: str = "median"  # "median", "hyperband", "none"
    n_startup_trials: int = 10
    n_jobs: int = 1
    seed: int = 42


@dataclass
class OptimizationResult:
    """Result of hyperparameter optimization."""
    best_params: dict[str, Any]
    best_score: float
    best_trial_number: int
    n_trials: int
    study_name: str
    optimization_history: list[dict[str, Any]]
    feature_importance: dict[str, float] | None = None


class HyperparameterOptimizer:
    """Optuna-based hyperparameter optimizer for ML models."""

    def __init__(self, config: OptimizationConfig | None = None):
        if not OPTUNA_AVAILABLE:
            raise ImportError("Optuna is required. Install with: pip install optuna")

        self.config = config or OptimizationConfig()
        self.study = None
        self.best_pipeline = None
        self.best_model_type = None
        self._setup_study()

    def _setup_study(self):
        """Create and configure Optuna study."""
        # Sampler
        if self.config.sampler == "tpe":
            sampler = TPESampler(seed=self.config.seed)
        elif self.config.sampler == "cmaes":
            try:
                from optuna.samplers import CmaEsSampler
                sampler = CmaEsSampler(seed=self.config.seed)
            except ImportError:
                sampler = TPESampler(seed=self.config.seed)
        else:
            from optuna.samplers import RandomSampler
            sampler = RandomSampler(seed=self.config.seed)

        # Pruner
        if self.config.pruner == "median":
            pruner = MedianPruner(n_startup_trials=self.config.n_startup_trials)
        elif self.config.pruner == "hyperband":
            from optuna.pruners import HyperbandPruner
            pruner = HyperbandPruner()
        else:
            from optuna.pruners import NopPruner
            pruner = NopPruner()

        study_name = f"geneai_opt_{self.config.seed}"
        self.study = optuna.create_study(
            direction=self.config.direction,
            sampler=sampler,
            pruner=pruner,
            study_name=study_name,
        )

    def _get_scorer(self):
        """Get scoring function."""
        scorers = {
            "roc_auc": lambda y_true, y_pred: roc_auc_score(y_true, y_pred) if len(np.unique(y_true)) > 1 else 0.5,
            "accuracy": accuracy_score,
            "f1": f1_score,
            "r2": r2_score,
            "neg_mse": lambda y_true, y_pred: -mean_squared_error(y_true, y_pred),
        }
        return scorers.get(self.config.scoring, roc_auc_score)

    def _create_pipeline(self, model_type: str, params: dict[str, Any]) -> Pipeline:
        """Create sklearn pipeline with model and preprocessing."""
        # Preprocessing
        preprocessor = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ])

        # Model
        if model_type == "xgboost" and XGBOOST_AVAILABLE:
            model = xgb.XGBClassifier(**params, random_state=self.config.seed, use_label_encoder=False, eval_metric="logloss")
        elif model_type == "lightgbm" and LIGHTGBM_AVAILABLE:
            model = lgb.LGBMClassifier(**params, random_state=self.config.seed, verbose=-1)
        elif model_type == "random_forest":
            model = RandomForestClassifier(**params, random_state=self.config.seed)
        elif model_type == "gradient_boosting":
            model = GradientBoostingClassifier(**params, random_state=self.config.seed)
        elif model_type == "logistic_regression":
            model = LogisticRegression(**params, random_state=self.config.seed, max_iter=1000)
        elif model_type == "ridge":
            model = Ridge(**params, random_state=self.config.seed)
        else:
            model = RandomForestClassifier(**params, random_state=self.config.seed)

        return Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", model),
        ])

    def _suggest_params(self, trial: optuna.Trial, model_type: str) -> dict[str, Any]:
        """Suggest hyperparameters for model type."""
        if model_type == "xgboost":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "gamma": trial.suggest_float("gamma", 0, 5),
                "reg_alpha": trial.suggest_float("reg_alpha", 0, 10),
                "reg_lambda": trial.suggest_float("reg_lambda", 0, 10),
            }
        elif model_type == "lightgbm":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 15),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 20, 150),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "reg_alpha": trial.suggest_float("reg_alpha", 0, 10),
                "reg_lambda": trial.suggest_float("reg_lambda", 0, 10),
            }
        elif model_type == "random_forest":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 20),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
                "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", None]),
                "bootstrap": trial.suggest_categorical("bootstrap", [True, False]),
            }
        elif model_type == "gradient_boosting":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            }
        elif model_type == "logistic_regression":
            return {
                "C": trial.suggest_float("C", 0.01, 100, log=True),
                "penalty": trial.suggest_categorical("penalty", ["l2"]),
                "solver": trial.suggest_categorical("solver", ["lbfgs", "saga"]),
            }
        elif model_type == "ridge":
            return {
                "alpha": trial.suggest_float("alpha", 0.01, 100, log=True),
            }
        return {}

    def optimize(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = "random_forest",
        cv: int | None = None,
    ) -> OptimizationResult:
        """Run hyperparameter optimization."""
        cv = cv or self.config.cv_folds
        scorer = self._get_scorer()

        def objective(trial: optuna.Trial) -> float:
            params = self._suggest_params(trial, model_type)
            pipeline = self._create_pipeline(model_type, params)

            # Cross-validation
            if self.config.scoring in ["roc_auc", "accuracy", "f1"]:
                cv_splitter = StratifiedKFold(n_splits=cv, shuffle=True, random_state=self.config.seed)
            else:
                cv_splitter = KFold(n_splits=cv, shuffle=True, random_state=self.config.seed)

            scores = cross_val_score(pipeline, X, y, cv=cv_splitter, scoring=self.config.scoring, n_jobs=self.config.n_jobs)
            return np.mean(scores)

        self.study.optimize(
            objective,
            n_trials=self.config.n_trials,
            timeout=self.config.timeout,
            n_jobs=self.config.n_jobs,
        )

        # Build best pipeline
        best_params = self.study.best_params
        self.best_pipeline = self._create_pipeline(model_type, best_params)
        self.best_pipeline.fit(X, y)
        self.best_model_type = model_type

        # Feature importance
        feature_importance = None
        if hasattr(self.best_pipeline.named_steps["classifier"], "feature_importances_"):
            importances = self.best_pipeline.named_steps["classifier"].feature_importances_
            feature_importance = dict(zip([f"feature_{i}" for i in range(len(importances))], importances))

        history = []
        for trial in self.study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                history.append({
                    "number": trial.number,
                    "value": trial.value,
                    "params": trial.params,
                })

        return OptimizationResult(
            best_params=best_params,
            best_score=self.study.best_value,
            best_trial_number=self.study.best_trial.number,
            n_trials=len(self.study.trials),
            study_name=self.study.study_name,
            optimization_history=history,
            feature_importance=feature_importance,
        )

    def get_best_pipeline(self) -> Pipeline | None:
        """Get the best fitted pipeline."""
        return self.best_pipeline

    def save_study(self, path: str | Path):
        """Save study to disk."""
        with open(path, "wb") as f:
            pickle.dump(self.study, f)

    def load_study(self, path: str | Path):
        """Load study from disk."""
        with open(path, "rb") as f:
            self.study = pickle.load(f)


def optimize_admet_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "xgboost",
) -> OptimizationResult:
    """Optimize ADMET model hyperparameters."""
    _import_admet()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


def optimize_safety_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "lightgbm",
) -> OptimizationResult:
    """Optimize safety model hyperparameters."""
    _import_safety()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


def optimize_biomarker_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "random_forest",
) -> OptimizationResult:
    """Optimize biomarker model hyperparameters."""
    _import_biomarker()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


def optimize_ranking_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "gradient_boosting",
) -> OptimizationResult:
    """Optimize ranking model hyperparameters."""
    _import_ranking()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


def optimize_drug_target_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "xgboost",
) -> OptimizationResult:
    """Optimize drug-target model hyperparameters."""
    _import_drug_target()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


def optimize_target_model(
    X: np.ndarray,
    y: np.ndarray,
    config: OptimizationConfig | None = None,
    model_type: str = "lightgbm",
) -> OptimizationResult:
    """Optimize target identification model hyperparameters."""
    _import_drug_target()
    optimizer = HyperparameterOptimizer(config)
    return optimizer.optimize(X, y, model_type=model_type)


if __name__ == "__main__":
    print("Optuna Hyperparameter Optimization Module")
    print("Available:", OPTUNA_AVAILABLE)
    if OPTUNA_AVAILABLE:
        print(f"Optuna version: {optuna.__version__}")
    print(f"XGBoost: {XGBOOST_AVAILABLE}")
    print(f"LightGBM: {LIGHTGBM_AVAILABLE}")