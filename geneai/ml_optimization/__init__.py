"""GeneAI ML Optimization - Phase 5 Enhancement."""
from __future__ import annotations

# Optuna is an optional dependency - import lazily
try:
    from geneai.ml_optimization.optuna_optimizer import (
        HyperparameterOptimizer,
        OptimizationConfig,
        OptimizationResult,
        optimize_admet_model,
        optimize_safety_model,
        optimize_biomarker_model,
        optimize_ranking_model,
        optimize_drug_target_model,
        optimize_target_model,
        OPTUNA_AVAILABLE,
    )
    _OPTUNA_IMPORTED = True
except ImportError:
    HyperparameterOptimizer = None
    OptimizationConfig = None
    OptimizationResult = None
    optimize_admet_model = None
    optimize_safety_model = None
    optimize_biomarker_model = None
    optimize_ranking_model = None
    optimize_drug_target_model = None
    optimize_target_model = None
    OPTUNA_AVAILABLE = False
    _OPTUNA_IMPORTED = False

__all__ = [
    "HyperparameterOptimizer",
    "OptimizationConfig",
    "OptimizationResult",
    "optimize_admet_model",
    "optimize_safety_model",
    "optimize_biomarker_model",
    "optimize_ranking_model",
    "optimize_drug_target_model",
    "optimize_target_model",
    "OPTUNA_AVAILABLE",
]

__version__ = "5.13.0"