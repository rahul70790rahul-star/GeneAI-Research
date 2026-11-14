"""GeneAI ML Registry (MLflow) - Phase 5 Enhancement."""
from __future__ import annotations

# MLflow is an optional dependency - import lazily
try:
    from geneai.ml_registry.mlflow_tracker import (
        MLflowTracker,
        ExperimentConfig,
        RunConfig,
        ModelRegistry,
        GeneAIModelLogger,
        auto_log_geneai_model,
        load_production_model,
        compare_model_versions,
        MLFLOW_AVAILABLE,
        MLFLOW_FLAVORS_AVAILABLE,
    )
    _MLFLOW_IMPORTED = True
except ImportError:
    MLflowTracker = None
    ExperimentConfig = None
    RunConfig = None
    ModelRegistry = None
    GeneAIModelLogger = None
    auto_log_geneai_model = None
    load_production_model = None
    compare_model_versions = None
    MLFLOW_AVAILABLE = False
    MLFLOW_FLAVORS_AVAILABLE = False
    _MLFLOW_IMPORTED = False

__all__ = [
    "MLflowTracker",
    "ExperimentConfig",
    "RunConfig",
    "ModelRegistry",
    "GeneAIModelLogger",
    "auto_log_geneai_model",
    "load_production_model",
    "compare_model_versions",
    "MLFLOW_AVAILABLE",
    "MLFLOW_FLAVORS_AVAILABLE",
]

__version__ = "5.13.0"