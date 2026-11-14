"""Multi-objective optimizer for drug discovery using Optuna."""
from __future__ import annotations

import logging
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)

# Try to import Optuna
try:
    import optuna
    from optuna.samplers import TPESampler, CmaEsSampler, RandomSampler, NSGAIISampler
    from optuna.pruners import MedianPruner, HyperbandPruner, NopPruner
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    optuna = None
    TPESampler = CmaEsSampler = RandomSampler = NSGAIISampler = None
    MedianPruner = HyperbandPruner = NopPruner = None


@dataclass
class OptimizationConfig:
    """Configuration for optimization run."""
    n_trials: int = 100
    n_startup_trials: int = 10
    sampler: str = "nsga2"  # "tpe", "cmaes", "random", "nsga2"
    pruner: str = "median"  # "median", "hyperband", "none"
    seed: int | None = 42
    n_jobs: int = 1
    timeout: float | None = None  # seconds
    # Multi-objective
    directions: list[str] | None = None  # "minimize" or "maximize" per objective
    # Constraints
    constraints: list[Callable] | None = None
    # Storage
    storage_url: str | None = None  # e.g., "sqlite:///optuna.db"
    study_name: str | None = None
    load_if_exists: bool = False
    # Output
    save_every: int = 10  # Save checkpoint every N trials
    checkpoint_path: str | None = None


@dataclass
class OptimizationResult:
    """Result of optimization run."""
    best_trials: list[dict[str, Any]]  # Pareto front
    all_trials: list[dict[str, Any]]
    n_trials: int
    n_complete: int
    n_pruned: int
    n_failed: int
    study: Any | None = None  # Optuna study object
    config: OptimizationConfig | None = None
    history: list[dict[str, Any]] = field(default_factory=list)  # Trial history


class DrugOptimizer:
    """
    Multi-objective optimizer for drug discovery.
    
    Uses Optuna for hyperparameter optimization with support for:
    - NSGA-II (multi-objective Pareto optimization)
    - TPE (Tree-structured Parzen Estimator)
    - CMA-ES (Covariance Matrix Adaptation Evolution Strategy)
    - Random search
    """
    
    def __init__(
        self,
        objective_evaluator: Callable[[dict[str, float]], dict[str, float]],
        parameter_space: dict[str, tuple],
        config: OptimizationConfig | None = None,
    ):
        """
        Initialize optimizer.
        
        Args:
            objective_evaluator: Function that takes parameters dict and returns objectives dict
            parameter_space: Dict of parameter_name -> (min, max) or (choices) for categorical
            config: Optimization configuration
        """
        if not OPTUNA_AVAILABLE:
            raise ImportError("Optuna is required for DrugOptimizer. Install with: pip install optuna")
        
        self.objective_evaluator = objective_evaluator
        self.parameter_space = parameter_space
        self.config = config or OptimizationConfig()
        self.study = None
        self.logger = logging.getLogger(__name__)
        
        # History tracking
        self.trial_history: list[dict[str, Any]] = []
    
    def _create_sampler(self):
        """Create Optuna sampler based on config."""
        if self.config.sampler == "tpe":
            return TPESampler(seed=self.config.seed, n_startup_trials=self.config.n_startup_trials)
        elif self.config.sampler == "cmaes":
            return CmaEsSampler(seed=self.config.seed)
        elif self.config.sampler == "random":
            return RandomSampler(seed=self.config.seed)
        elif self.config.sampler == "nsga2":
            return NSGAIISampler(seed=self.config.seed)
        else:
            return TPESampler(seed=self.config.seed)
    
    def _create_pruner(self):
        """Create Optuna pruner based on config."""
        if self.config.pruner == "median":
            return MedianPruner(n_startup_trials=self.config.n_startup_trials, n_warmup_steps=5)
        elif self.config.pruner == "hyperband":
            return HyperbandPruner()
        else:
            return NopPruner()
    
    def _suggest_parameters(self, trial) -> dict[str, Any]:
        """Suggest parameters for a trial."""
        params = {}
        
        for name, space in self.parameter_space.items():
            if isinstance(space, tuple) and len(space) == 2:
                # Continuous or integer range
                low, high = space
                if isinstance(low, int) and isinstance(high, int):
                    params[name] = trial.suggest_int(name, low, high)
                else:
                    params[name] = trial.suggest_float(name, low, high)
            elif isinstance(space, (list, tuple)) and len(space) > 2:
                # Categorical
                params[name] = trial.suggest_categorical(name, list(space))
            else:
                # Fixed value
                params[name] = space
        
        return params
    
    def _objective(self, trial) -> list[float]:
        """Optuna objective function."""
        # Suggest parameters
        params = self._suggest_parameters(trial)
        
        # Evaluate objectives
        try:
            objectives = self.objective_evaluator(params)
            
            # Store in history
            trial_data = {
                "number": trial.number,
                "params": params,
                "objectives": objectives,
                "state": "complete",
            }
            self.trial_history.append(trial_data)
            
            # Return values for Optuna (in order of directions)
            if self.config.directions:
                return [objectives.get(f"obj_{i}", 0) for i in range(len(self.config.directions))]
            else:
                # Single objective: return first value
                return list(objectives.values())[0] if objectives else 0.0
                
        except Exception as e:
            self.logger.warning("Trial %d failed: %s", trial.number, e)
            trial_data = {
                "number": trial.number,
                "params": params,
                "objectives": {},
                "state": "fail",
                "error": str(e),
            }
            self.trial_history.append(trial_data)
            raise optuna.TrialPruned() if "prune" in str(e).lower() else e
    
    def optimize(self) -> OptimizationResult:
        """Run optimization."""
        # Determine directions
        if self.config.directions is None:
            # Infer from first evaluation
            test_params = {k: (v[0] + v[1]) / 2 if isinstance(v, tuple) and len(v) == 2 
                          else v[0] if isinstance(v, (list, tuple)) else v 
                          for k, v in self.parameter_space.items()}
            test_objectives = self.objective_evaluator(test_params)
            self.config.directions = ["minimize"] * len(test_objectives)
        
        # Create study
        self.study = optuna.create_study(
            directions=self.config.directions,
            sampler=self._create_sampler(),
            pruner=self._create_pruner(),
            storage=self.config.storage_url,
            study_name=self.config.study_name,
            load_if_exists=self.config.load_if_exists,
        )
        
        # Add constraints if provided
        if self.config.constraints:
            for constraint in self.config.constraints:
                self.study.add_constraint(constraint)
        
        # Run optimization
        self.study.optimize(
            self._objective,
            n_trials=self.config.n_trials,
            timeout=self.config.timeout,
            n_jobs=self.config.n_jobs,
            callbacks=[self._checkpoint_callback] if self.config.checkpoint_path else None,
        )
        
        # Extract results
        return self._extract_results()
    
    def _checkpoint_callback(self, study, trial):
        """Callback to save checkpoint."""
        if trial.number % self.config.save_every == 0 and self.config.checkpoint_path:
            self.save_checkpoint(self.config.checkpoint_path)
    
    def _extract_results(self) -> OptimizationResult:
        """Extract results from study."""
        # Get Pareto front (for multi-objective) or best trials
        if len(self.config.directions) > 1:
            # Multi-objective: get Pareto front
            best_trials = []
            for trial in self.study.best_trials:
                best_trials.append({
                    "number": trial.number,
                    "params": trial.params,
                    "values": trial.values,
                    "objectives": self._get_trial_objectives(trial),
                })
        else:
            # Single objective: get best
            best_trial = self.study.best_trial
            best_trials = [{
                "number": best_trial.number,
                "params": best_trial.params,
                "values": [best_trial.value],
                "objectives": self._get_trial_objectives(best_trial),
            }]
        
        # All trials
        all_trials = []
        for trial in self.study.trials:
            all_trials.append({
                "number": trial.number,
                "params": trial.params,
                "values": trial.values,
                "state": str(trial.state),
                "objectives": self._get_trial_objectives(trial) if trial.values else {},
            })
        
        # Count states
        n_complete = sum(1 for t in self.study.trials if t.state == optuna.trial.TrialState.COMPLETE)
        n_pruned = sum(1 for t in self.study.trials if t.state == optuna.trial.TrialState.PRUNED)
        n_failed = sum(1 for t in self.study.trials if t.state == optuna.trial.TrialState.FAIL)
        
        return OptimizationResult(
            best_trials=best_trials,
            all_trials=all_trials,
            n_trials=len(self.study.trials),
            n_complete=n_complete,
            n_pruned=n_pruned,
            n_failed=n_failed,
            study=self.study,
            config=self.config,
            history=self.trial_history,
        )
    
    def _get_trial_objectives(self, trial) -> dict[str, float]:
        """Get objective names and values for a trial."""
        # This would need to be tracked during evaluation
        for h in self.trial_history:
            if h["number"] == trial.number:
                return h.get("objectives", {})
        return {}
    
    def save_checkpoint(self, path: str):
        """Save optimization checkpoint."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "config": self.config.__dict__ if self.config else {},
            "history": self.trial_history,
            "study_pickle": None,  # Can't pickle study easily
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_checkpoint(self, path: str):
        """Load optimization checkpoint."""
        with open(path, "r") as f:
            data = json.load(f)
        
        self.trial_history = data.get("history", [])
    
    def get_pareto_front(self) -> list[dict[str, Any]]:
        """Get current Pareto front."""
        if self.study is None:
            return []
        
        if len(self.config.directions) > 1:
            return [
                {
                    "params": t.params,
                    "values": t.values,
                    "objectives": self._get_trial_objectives(t),
                }
                for t in self.study.best_trials
            ]
        else:
            best = self.study.best_trial
            return [{
                "params": best.params,
                "values": [best.value],
                "objectives": self._get_trial_objectives(best),
            }]
    
    def get_parameter_importance(self) -> dict[str, float]:
        """Get parameter importance (for completed trials)."""
        if self.study is None or len(self.study.trials) < 10:
            return {}
        
        try:
            importance = optuna.importance.get_param_importances(self.study)
            return importance
        except Exception:
            return {}


def create_molecular_optimizer(
    objective_evaluator: Callable,
    parameter_space: dict[str, tuple],
    config: OptimizationConfig | None = None,
) -> DrugOptimizer:
    """Create optimizer for molecular design."""
    return DrugOptimizer(objective_evaluator, parameter_space, config)


# Predefined parameter spaces for common use cases
MOLECULAR_PARAMETER_SPACES = {
    "fragment_based": {
        "num_fragments": (2, 6),
        "fragment_library_size": (10, 100),
        "linker_length": (0, 4),
        "rigid_linkers": (True, False),
    },
    "scaffold_hopping": {
        "scaffold_similarity_threshold": (0.3, 0.8),
        "r_group_diversity": (0.5, 1.0),
        "num_r_groups": (1, 4),
        "property_weight": (0.5, 2.0),
    },
    "r_group_enum": {
        "core_scaffold": ["benzene", "pyridine", "pyrimidine", "indole"],
        "r1_library": ["methyl", "ethyl", "propyl", "fluorophenyl", "chlorophenyl"],
        "r2_library": ["H", "methyl", "OH", "NH2", "CN", "CF3"],
        "r3_library": ["H", "methyl", "F", "Cl"],
    },
    "property_optimization": {
        "target_mw": (300, 500),
        "target_logp": (1.0, 4.0),
        "target_tpsa": (40, 100),
        "target_hbd": (0, 3),
        "target_hba": (2, 7),
        "target_rotatable": (0, 7),
    },
}