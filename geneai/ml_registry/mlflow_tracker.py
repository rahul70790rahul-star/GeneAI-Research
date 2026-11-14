"""MLflow Model Registry and Experiment Tracking - Phase 5 Enhancement."""
from __future__ import annotations

import logging
import os
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    from mlflow.models import infer_signature
    from mlflow.pyfunc import PyFuncModel
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

try:
    import mlflow.sklearn
    import mlflow.xgboost
    import mlflow.lightgbm
    import mlflow.pytorch
    MLFLOW_FLAVORS_AVAILABLE = True
except ImportError:
    MLFLOW_FLAVORS_AVAILABLE = False

# Lazy imports for optional GeneAI modules - will be imported inside methods
# These are set to None and imported on-demand
_ADMETModel = None
_ADMETModelManager = None
_ToxicityModelManager = None
_ToxicityModel = None
_BiomarkerDiscoveryEngine = None
_BiomarkerResult = None
_AICandidateRanker = None
_CandidateFeatures = None
_DrugTargetPredictor = None
_train_evaluate_target_model = None
_GNNModel = None
_MolecularMLP = None
_train_gnn_model = None
_train_mlp_model = None
_OptimizationResult = None
_torch = None
_pd = None

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


@dataclass
class ExperimentConfig:
    """Configuration for MLflow experiment."""
    experiment_name: str = "geneai_experiment"
    tracking_uri: str | None = None  # None = local file store
    artifact_location: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Configuration for MLflow run."""
    run_name: str | None = None
    run_id: str | None = None
    nested: bool = False
    tags: dict[str, str] = field(default_factory=dict)
    log_model: bool = True
    model_name: str | None = None  # For model registry


class MLflowTracker:
    """MLflow experiment tracking and model registry for GeneAI."""

    def __init__(self, config: ExperimentConfig | None = None):
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow is required. Install with: pip install mlflow")

        self.config = config or ExperimentConfig()
        self.client = None
        self._init_tracking()

    def _init_tracking(self):
        """Initialize MLflow tracking."""
        if self.config.tracking_uri:
            mlflow.set_tracking_uri(self.config.tracking_uri)

        # Create or get experiment
        experiment = mlflow.get_experiment_by_name(self.config.experiment_name)
        if experiment is None:
            experiment_id = mlflow.create_experiment(
                self.config.experiment_name,
                artifact_location=self.config.artifact_location,
                tags=self.config.tags,
            )
        else:
            experiment_id = experiment.experiment_id

        mlflow.set_experiment(self.config.experiment_name)
        self.client = MlflowClient()
        logger.info(f"MLflow experiment: {self.config.experiment_name} (ID: {experiment_id})")

    @contextmanager
    def start_run(self, run_config: RunConfig | None = None):
        """Start MLflow run as context manager."""
        run_config = run_config or RunConfig()

        run = mlflow.start_run(
            run_id=run_config.run_id,
            run_name=run_config.run_name,
            nested=run_config.nested,
        )

        # Add tags
        for key, value in run_config.tags.items():
            mlflow.set_tag(key, value)

        try:
            yield run
        except Exception as e:
            mlflow.end_run(status="FAILED")
            raise
        else:
            mlflow.end_run(status="FINISHED")

    def log_params(self, params: dict[str, Any]):
        """Log parameters."""
        for key, value in params.items():
            if isinstance(value, (dict, list)):
                import json
                mlflow.log_param(key, json.dumps(value))
            else:
                mlflow.log_param(key, value)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None):
        """Log metrics."""
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and not np.isnan(value):
                mlflow.log_metric(key, value, step=step)

    def log_metric(self, key: str, value: float, step: int | None = None):
        """Log single metric."""
        if isinstance(value, (int, float)) and not np.isnan(value):
            mlflow.log_metric(key, value, step=step)

    def log_artifact(self, local_path: str | Path, artifact_path: str | None = None):
        """Log artifact."""
        mlflow.log_artifact(str(local_path), artifact_path)

    def log_artifacts(self, local_dir: str | Path, artifact_path: str | None = None):
        """Log directory of artifacts."""
        mlflow.log_artifacts(str(local_dir), artifact_path)

    def log_figure(self, figure, artifact_file: str):
        """Log matplotlib figure."""
        mlflow.log_figure(figure, artifact_file)

    def log_dict(self, dictionary: dict, artifact_file: str):
        """Log dictionary as JSON artifact."""
        mlflow.log_dict(dictionary, artifact_file)

    def set_tag(self, key: str, value: str):
        """Set tag."""
        mlflow.set_tag(key, value)

    def get_run(self, run_id: str):
        """Get run by ID."""
        return self.client.get_run(run_id)

    def search_runs(self, experiment_names: list[str] | None = None, filter_string: str = "", max_results: int = 100):
        """Search runs."""
        exp_ids = []
        if experiment_names:
            for name in experiment_names:
                exp = mlflow.get_experiment_by_name(name)
                if exp:
                    exp_ids.append(exp.experiment_id)
        else:
            exp = mlflow.get_experiment_by_name(self.config.experiment_name)
            if exp:
                exp_ids.append(exp.experiment_id)

        return self.client.search_runs(
            experiment_ids=exp_ids,
            filter_string=filter_string,
            max_results=max_results,
            order_by=["attributes.start_time DESC"],
        )

    def get_best_run(self, metric: str = "val_roc_auc", ascending: bool = False) -> Any | None:
        """Get best run by metric."""
        runs = self.search_runs(max_results=1000)
        valid_runs = [r for r in runs if metric in r.data.metrics]
        if not valid_runs:
            return None
        return max(valid_runs, key=lambda r: r.data.metrics[metric]) if not ascending else min(valid_runs, key=lambda r: r.data.metrics[metric])


class ModelRegistry:
    """MLflow Model Registry operations."""

    def __init__(self, tracker: MLflowTracker):
        self.tracker = tracker
        self.client = tracker.client

    def register_model(
        self,
        model_uri: str,
        name: str,
        tags: dict[str, str] | None = None,
        description: str | None = None,
    ) -> Any:
        """Register model in registry."""
        model_version = mlflow.register_model(model_uri, name, tags=tags)

        if description:
            self.client.update_model_version(name, model_version.version, description)

        logger.info(f"Registered model {name} version {model_version.version}")
        return model_version

    def transition_model_stage(
        self,
        name: str,
        version: int,
        stage: str,  # "Staging", "Production", "Archived"
        archive_existing_versions: bool = False,
    ):
        """Transition model version to stage."""
        self.client.transition_model_version_stage(
            name=name,
            version=version,
            stage=stage,
            archive_existing_versions=archive_existing_versions,
        )
        logger.info(f"Model {name} v{version} transitioned to {stage}")

    def get_model_version(self, name: str, version: int):
        """Get model version details."""
        return self.client.get_model_version(name, version)

    def get_latest_model_version(self, name: str, stage: str = "Production"):
        """Get latest model version in stage."""
        versions = self.client.get_latest_versions(name, stages=[stage])
        return versions[0] if versions else None

    def list_model_versions(self, name: str):
        """List all versions of a model."""
        return self.client.search_model_versions(f"name='{name}'")

    def set_model_tag(self, name: str, key: str, value: str):
        """Set tag on registered model."""
        self.client.set_registered_model_tag(name, key, value)

    def delete_model_version(self, name: str, version: int):
        """Delete model version."""
        self.client.delete_model_version(name, version)

    def delete_registered_model(self, name: str):
        """Delete registered model and all versions."""
        self.client.delete_registered_model(name)


class GeneAIModelLogger:
    """High-level model logging for GeneAI modules."""

    def __init__(self, tracker: MLflowTracker):
        self.tracker = tracker

    def _import_admet(self):
        global _ADMETModel, _ADMETModelManager
        if _ADMETModel is None:
            try:
                from geneai.admet_prediction.ml_models import ADMETModel, ADMETModelManager
                _ADMETModel = ADMETModel
                _ADMETModelManager = ADMETModelManager
            except ImportError:
                _ADMETModel = object
                _ADMETModelManager = object
        return _ADMETModel

    def _import_safety(self):
        global _ToxicityModelManager, _ToxicityModel
        if _ToxicityModel is None:
            try:
                from geneai.drug_safety.ml_models import ToxicityModelManager, ToxicityModel
                _ToxicityModelManager = ToxicityModelManager
                _ToxicityModel = ToxicityModel
            except ImportError:
                _ToxicityModel = object
                _ToxicityModelManager = object
        return _ToxicityModel

    def _import_biomarker(self):
        global _BiomarkerDiscoveryEngine, _BiomarkerResult
        if _BiomarkerResult is None:
            try:
                from geneai.biomarker_discovery.ml_engine import BiomarkerDiscoveryEngine, BiomarkerResult
                _BiomarkerDiscoveryEngine = BiomarkerDiscoveryEngine
                _BiomarkerResult = BiomarkerResult
            except ImportError:
                _BiomarkerResult = object
                _BiomarkerDiscoveryEngine = object
        return _BiomarkerResult

    def _import_ranking(self):
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

    def _import_drug_target(self):
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

    def _import_deep_learning(self):
        global _GNNModel, _MolecularMLP, _train_gnn_model, _train_mlp_model, _torch
        if _GNNModel is None:
            try:
                import torch
                from geneai.deep_learning.molecular_gnn import GNNModel, MolecularMLP, train_gnn_model, train_mlp_model
                _torch = torch
                _GNNModel = GNNModel
                _MolecularMLP = MolecularMLP
                _train_gnn_model = train_gnn_model
                _train_mlp_model = train_mlp_model
            except ImportError:
                _GNNModel = object
                _MolecularMLP = object
                _train_gnn_model = None
                _train_mlp_model = None
                _torch = None
        return _GNNModel

    def _import_optimization(self):
        global _OptimizationResult
        if _OptimizationResult is None:
            try:
                from geneai.ml_optimization.optuna_optimizer import OptimizationResult
                _OptimizationResult = OptimizationResult
            except ImportError:
                _OptimizationResult = object
        return _OptimizationResult

    def log_admet_model(
        self,
        model: Any,  # ADMETModel
        training_results: dict[str, Any],
        run_config: RunConfig | None = None,
    ) -> str:
        """Log ADMET model with MLflow."""
        with self.tracker.start_run(run_config) as run:
            # Log parameters
            self.tracker.log_params({
                "endpoint": getattr(model, "endpoint", "unknown"),
                "model_type": getattr(model, "model_type", "unknown"),
                "model_params": getattr(model, "model_params", {}),
            })

            # Log metrics
            self.tracker.log_metrics({
                "train_accuracy": training_results.get("train_accuracy", 0),
                "train_precision": training_results.get("train_precision", 0),
                "train_recall": training_results.get("train_recall", 0),
                "train_f1": training_results.get("train_f1", 0),
                "train_roc_auc": training_results.get("train_roc_auc", 0),
                "cv_roc_auc_mean": training_results.get("cv_roc_auc_mean", 0),
                "cv_roc_auc_std": training_results.get("cv_roc_auc_std", 0),
                "n_samples": training_results.get("n_samples", 0),
            })

            # Log feature importance
            if "feature_importance" in training_results:
                self.tracker.log_dict(
                    dict(training_results["feature_importance"]),
                    "feature_importance.json",
                )

            # Log model
            if run_config and run_config.log_model and MLFLOW_FLAVORS_AVAILABLE:
                # For sklearn pipeline
                mlflow.sklearn.log_model(
                    getattr(model, "pipeline", model),
                    "model",
                    registered_model_name=run_config.model_name,
                    signature=infer_signature(
                        np.zeros((1, len(getattr(model, "feature_names", [1])))),
                        np.zeros(1),
                    ),
                )

            return run.info.run_id

    def log_safety_model(
        self,
        model: Any,  # ToxicityModel
        run_config: RunConfig | None = None,
    ) -> str:
        """Log toxicity model with MLflow."""
        with self.tracker.start_run(run_config) as run:
            self.tracker.log_params({
                "endpoint": getattr(model, "endpoint", "unknown"),
                "model_type": getattr(model, "model_type", "unknown"),
                "params": getattr(model, "params", {}),
            })

            self.tracker.log_metrics({
                "cv_auc": getattr(model, "cv_auc", 0),
                "cv_auc_std": getattr(model, "cv_auc_std", 0),
                "train_auc": getattr(model, "train_auc", 0),
                "training_samples": getattr(model, "training_samples", 0),
            })

            if run_config and run_config.log_model and MLFLOW_FLAVORS_AVAILABLE:
                mlflow.sklearn.log_model(
                    getattr(model, "model", model),
                    "model",
                    registered_model_name=run_config.model_name,
                )

            return run.info.run_id

    def log_biomarker_result(
        self,
        result: Any,  # BiomarkerResult
        run_config: RunConfig | None = None,
    ) -> str:
        """Log biomarker discovery result."""
        with self.tracker.start_run(run_config) as run:
            candidates = getattr(result, "candidates", [])
            dataset_info = getattr(result, "dataset_info", {})

            self.tracker.log_params({
                "best_model": getattr(result, "best_model", "unknown"),
                "feature_selection": dataset_info.get("feature_selection_method"),
                "n_features_original": dataset_info.get("n_features_original"),
                "n_features_selected": dataset_info.get("n_features_selected"),
                "biomarker_type": candidates[0].biomarker_type if candidates else "unknown",
            })

            self.tracker.log_metrics({
                "best_model_auc": getattr(result, "best_model_auc", 0),
                "n_candidates": len(candidates),
                "n_high_confidence": sum(1 for c in candidates if getattr(c, "confidence", "") == "high"),
                "n_medium_confidence": sum(1 for c in candidates if getattr(c, "confidence", "") == "medium"),
            })

            # Log candidates as artifact
            candidates_data = [
                {
                    "gene": getattr(c, "gene_symbol", "unknown"),
                    "importance": getattr(c, "feature_importance", 0),
                    "p_value": getattr(c, "p_value", 1.0),
                    "fold_change": getattr(c, "fold_change", 0),
                    "auc": getattr(c, "auc_score", 0),
                    "confidence": getattr(c, "confidence", "low"),
                }
                for c in candidates
            ]
            self.tracker.log_dict({"candidates": candidates_data}, "candidates.json")

            # Log cross-validation
            self.tracker.log_dict(getattr(result, "cross_validation", {}), "cross_validation.json")

            return run.info.run_id

    def log_ranking_model(
        self,
        ranker: Any,  # AICandidateRanker
        training_history: dict[str, Any],
        run_config: RunConfig | None = None,
    ) -> str:
        """Log candidate ranking model."""
        with self.tracker.start_run(run_config) as run:
            self.tracker.log_params({
                "model_type": getattr(ranker, "model_type", "unknown"),
                "n_features": len(getattr(ranker, "feature_names", [])),
            })

            self.tracker.log_metrics({
                "train_r2": training_history.get("train_r2", 0),
                "val_r2": training_history.get("val_r2", 0),
                "cv_r2_mean": training_history.get("cv_r2_mean", 0),
                "cv_r2_std": training_history.get("cv_r2_std", 0),
            })

            if run_config and run_config.log_model and MLFLOW_FLAVORS_AVAILABLE:
                mlflow.sklearn.log_model(
                    getattr(ranker, "model", ranker),
                    "model",
                    registered_model_name=run_config.model_name,
                )

            return run.info.run_id

    def log_drug_target_model(
        self,
        predictor: Any,  # DrugTargetPredictor
        training_results: dict[str, Any],
        run_config: RunConfig | None = None,
    ) -> str:
        """Log drug-target prediction model."""
        with self.tracker.start_run(run_config) as run:
            self.tracker.log_params({
                "model_type": getattr(predictor, "model_type", "unknown"),
                "use_fingerprints": getattr(predictor, "use_fingerprints", False),
                "fp_type": getattr(predictor, "fp_type", "morgan"),
                "n_fp_bits": getattr(predictor, "n_fp_bits", 2048),
            })

            self.tracker.log_metrics({
                "train_accuracy": training_results.get("train_accuracy", 0),
                "train_roc_auc": training_results.get("train_roc_auc", 0),
                "cv_roc_auc_mean": training_results.get("cv_roc_auc_mean", 0),
                "cv_roc_auc_std": training_results.get("cv_roc_auc_std", 0),
            })

            if run_config and run_config.log_model and MLFLOW_FLAVORS_AVAILABLE:
                mlflow.sklearn.log_model(
                    getattr(predictor, "pipeline", predictor),
                    "model",
                    registered_model_name=run_config.model_name,
                )

            return run.info.run_id

    def log_optimization_result(
        self,
        result: Any,  # OptimizationResult
        run_config: RunConfig | None = None,
    ) -> str:
        """Log Optuna optimization result."""
        with self.tracker.start_run(run_config) as run:
            self.tracker.log_params(getattr(result, "best_params", {}))
            self.tracker.log_metrics({
                "best_score": getattr(result, "best_score", 0),
                "n_trials": getattr(result, "n_trials", 0),
            })

            # Log optimization history
            self.tracker.log_dict(
                {"history": getattr(result, "optimization_history", [])},
                "optimization_history.json",
            )

            return run.info.run_id

    def log_deep_learning_model(
        self,
        model: Any,  # torch.nn.Module
        config: dict,
        metrics: dict[str, float],
        run_config: RunConfig | None = None,
    ) -> str:
        """Log PyTorch model."""
        with self.tracker.start_run(run_config) as run:
            self.tracker.log_params(config)
            self.tracker.log_metrics(metrics)

            if run_config and run_config.log_model and MLFLOW_FLAVORS_AVAILABLE:
                mlflow.pytorch.log_model(
                    model,
                    "model",
                    registered_model_name=run_config.model_name,
                )

            return run.info.run_id


def auto_log_geneai_model(
    model_type: str,
    model: Any,
    metrics: dict[str, float],
    params: dict[str, Any] | None = None,
    tags: dict[str, str] | None = None,
    experiment_name: str = "geneai_auto",
) -> str:
    """Auto-log any GeneAI model with minimal configuration."""
    if not MLFLOW_AVAILABLE:
        raise ImportError("MLflow required")

    tracker = MLflowTracker(ExperimentConfig(experiment_name=experiment_name))
    logger = GeneAIModelLogger(tracker)

    run_config = RunConfig(
        run_name=f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        tags=tags or {},
        log_model=True,
        model_name=f"geneai_{model_type}",
    )

    if model_type == "admet":
        return logger.log_admet_model(model, metrics, run_config)
    elif model_type == "safety":
        return logger.log_safety_model(model, run_config)
    elif model_type == "biomarker":
        return logger.log_biomarker_result(model, run_config)
    elif model_type == "ranking":
        return logger.log_ranking_model(model, metrics, run_config)
    elif model_type == "drug_target":
        return logger.log_drug_target_model(model, metrics, run_config)
    elif model_type == "optimization":
        return logger.log_optimization_result(model, run_config)
    elif model_type == "deep_learning":
        return logger.log_deep_learning_model(model, params or {}, metrics, run_config)
    else:
        # Generic logging
        with tracker.start_run(run_config) as run:
            if params:
                tracker.log_params(params)
            tracker.log_metrics(metrics)
            return run.info.run_id


def load_production_model(model_name: str, stage: str = "Production") -> Any:
    """Load model from MLflow registry for production inference."""
    if not MLFLOW_AVAILABLE:
        raise ImportError("MLflow required")

    model_uri = f"models:/{model_name}/{stage}"

    # Determine flavor from model name
    if "admet" in model_name or "safety" in model_name or "drug_target" in model_name:
        return mlflow.sklearn.load_model(model_uri)
    elif "ranking" in model_name:
        return mlflow.sklearn.load_model(model_uri)
    elif "deep" in model_name or "gnn" in model_name:
        return mlflow.pytorch.load_model(model_uri)
    else:
        return mlflow.pyfunc.load_model(model_uri)


def compare_model_versions(
    model_name: str,
    versions: list[int],
    metric: str = "val_roc_auc",
) -> Any:
    """Compare model versions in registry."""
    if not MLFLOW_AVAILABLE:
        raise ImportError("MLflow required")

    global _pd
    if _pd is None:
        import pandas as pd
        _pd = pd

    client = MlflowClient()
    results = []

    for version in versions:
        mv = client.get_model_version(model_name, version)
        run = client.get_run(mv.run_id)
        results.append({
            "version": version,
            "stage": mv.current_stage,
            "metric_value": run.data.metrics.get(metric, None),
            "run_id": mv.run_id,
            "created": mv.creation_timestamp,
        })

    return _pd.DataFrame(results).sort_values("version")


if __name__ == "__main__":
    print("MLflow Model Registry Module")
    print("Available:", MLFLOW_AVAILABLE)
    if MLFLOW_AVAILABLE:
        print(f"MLflow version: {mlflow.__version__}")