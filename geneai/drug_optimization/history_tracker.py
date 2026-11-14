"""History tracking for optimization runs."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrialRecord:
    """Single trial record."""
    trial_number: int
    timestamp: str
    parameters: dict[str, Any]
    objectives: dict[str, float]
    state: str  # "complete", "pruned", "fail"
    error: str | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationSession:
    """Complete optimization session record."""
    session_id: str
    start_time: str
    end_time: str | None
    config: dict[str, Any]
    trials: list[TrialRecord] = field(default_factory=list)
    best_trials: list[dict[str, Any]] = field(default_factory=list)
    pareto_front: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # "running", "completed", "failed", "interrupted"
    metadata: dict[str, Any] = field(default_factory=dict)


class HistoryTracker:
    """
    Track optimization history for reproducibility and analysis.
    """
    
    def __init__(self, session_id: str | None = None, save_path: str | None = None):
        self.session_id = session_id or f"opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.save_path = Path(save_path) if save_path else Path.cwd() / "optimization_history"
        self.save_path.mkdir(parents=True, exist_ok=True)
        
        self.session = OptimizationSession(
            session_id=self.session_id,
            start_time=datetime.now().isoformat(),
            config={},
        )
        self.logger = logging.getLogger(__name__)
    
    def set_config(self, config: dict[str, Any]):
        """Set optimization configuration."""
        self.session.config = config
    
    def add_trial(self, trial: TrialRecord):
        """Add trial to history."""
        self.session.trials.append(trial)
        
        # Auto-save every 10 trials
        if len(self.session.trials) % 10 == 0:
            self.save()
    
    def record_trial(
        self,
        trial_number: int,
        parameters: dict[str, Any],
        objectives: dict[str, float],
        state: str = "complete",
        error: str | None = None,
        duration: float | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Record a trial."""
        trial = TrialRecord(
            trial_number=trial_number,
            timestamp=datetime.now().isoformat(),
            parameters=parameters,
            objectives=objectives,
            state=state,
            error=error,
            duration_seconds=duration,
            metadata=metadata or {},
        )
        self.add_trial(trial)
    
    def finalize(self, best_trials: list[dict[str, Any]] | None = None, pareto_front: list[dict[str, Any]] | None = None):
        """Finalize session."""
        self.session.end_time = datetime.now().isoformat()
        self.session.status = "completed"
        if best_trials:
            self.session.best_trials = best_trials
        if pareto_front:
            self.session.pareto_front = pareto_front
        self.save()
    
    def save(self):
        """Save history to disk."""
        file_path = self.save_path / f"{self.session_id}.json"
        
        data = {
            "session_id": self.session.session_id,
            "start_time": self.session.start_time,
            "end_time": self.session.end_time,
            "config": self.session.config,
            "status": self.session.status,
            "metadata": self.session.metadata,
            "trials": [
                {
                    "trial_number": t.trial_number,
                    "timestamp": t.timestamp,
                    "parameters": t.parameters,
                    "objectives": t.objectives,
                    "state": t.state,
                    "error": t.error,
                    "duration_seconds": t.duration_seconds,
                    "metadata": t.metadata,
                }
                for t in self.session.trials
            ],
            "best_trials": self.session.best_trials,
            "pareto_front": self.session.pareto_front,
        }
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load(self, session_id: str) -> OptimizationSession | None:
        """Load history from disk."""
        file_path = self.save_path / f"{session_id}.json"
        
        if not file_path.exists():
            return None
        
        with open(file_path, "r") as f:
            data = json.load(f)
        
        session = OptimizationSession(
            session_id=data["session_id"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            config=data["config"],
            status=data["status"],
            metadata=data["metadata"],
        )
        
        session.trials = [
            TrialRecord(
                trial_number=t["trial_number"],
                timestamp=t["timestamp"],
                parameters=t["parameters"],
                objectives=t["objectives"],
                state=t["state"],
                error=t["error"],
                duration_seconds=t["duration_seconds"],
                metadata=t["metadata"],
            )
            for t in data["trials"]
        ]
        
        session.best_trials = data.get("best_trials", [])
        session.pareto_front = data.get("pareto_front", [])
        
        self.session = session
        return session
    
    def get_trial_dataframe(self) -> list[dict[str, Any]]:
        """Get trials as list of dicts for DataFrame."""
        return [
            {
                "trial": t.trial_number,
                **t.parameters,
                **t.objectives,
                "state": t.state,
                "timestamp": t.timestamp,
            }
            for t in self.session.trials
        ]
    
    def get_objective_history(self, objective_name: str) -> list[tuple[int, float]]:
        """Get history of specific objective."""
        history = []
        for t in self.session.trials:
            if objective_name in t.objectives:
                history.append((t.trial_number, t.objectives[objective_name]))
        return history
    
    def get_best_objective_value(self, objective_name: str, minimize: bool = True) -> float | None:
        """Get best value for an objective."""
        values = [
            t.objectives[objective_name]
            for t in self.session.trials
            if objective_name in t.objectives and t.state == "complete"
        ]
        
        if not values:
            return None
        
        return min(values) if minimize else max(values)


class DecisionLogger:
    """
    Log optimization decisions for audit trail.
    """
    
    def __init__(self, session_id: str, log_path: str | None = None):
        self.session_id = session_id
        self.log_path = Path(log_path) if log_path else Path.cwd() / "decision_logs"
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        self.decisions: list[dict[str, Any]] = []
    
    def log_decision(
        self,
        decision_type: str,
        description: str,
        context: dict[str, Any] | None = None,
        rationale: str | None = None,
        alternatives: list[str] | None = None,
    ):
        """Log a decision."""
        decision = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "decision_type": decision_type,
            "description": description,
            "context": context or {},
            "rationale": rationale,
            "alternatives": alternatives or [],
        }
        
        self.decisions.append(decision)
        self._write_log(decision)
    
    def _write_log(self, decision: dict[str, Any]):
        """Write decision to log file."""
        log_file = self.log_path / f"{self.session_id}_decisions.jsonl"
        
        with open(log_file, "a") as f:
            f.write(json.dumps(decision, default=str) + "\n")
    
    def log_parameter_change(self, param_name: str, old_value: Any, new_value: Any, reason: str):
        """Log parameter change."""
        self.log_decision(
            decision_type="parameter_change",
            description=f"Changed {param_name} from {old_value} to {new_value}",
            context={"parameter": param_name, "old": old_value, "new": new_value},
            rationale=reason,
        )
    
    def log_objective_change(self, obj_name: str, old_target: Any, new_target: Any, reason: str):
        """Log objective target change."""
        self.log_decision(
            decision_type="objective_change",
            description=f"Changed target for {obj_name} from {old_target} to {new_target}",
            context={"objective": obj_name, "old_target": old_target, "new_target": new_target},
            rationale=reason,
        )
    
    def log_constraint_addition(self, constraint: str, reason: str):
        """Log constraint addition."""
        self.log_decision(
            decision_type="constraint_added",
            description=f"Added constraint: {constraint}",
            context={"constraint": constraint},
            rationale=reason,
        )
    
    def log_pruning(self, trial_number: int, reason: str):
        """Log trial pruning."""
        self.log_decision(
            decision_type="trial_pruned",
            description=f"Trial {trial_number} pruned: {reason}",
            context={"trial_number": trial_number, "reason": reason},
        )
    
    def get_decisions(self) -> list[dict[str, Any]]:
        """Get all decisions."""
        return self.decisions
    
    def export_decisions(self, output_path: str):
        """Export decisions to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(self.decisions, f, indent=2, default=str)


def create_history_tracker(session_id: str | None = None, **kwargs) -> HistoryTracker:
    """Create history tracker."""
    return HistoryTracker(session_id, **kwargs)


def create_decision_logger(session_id: str, **kwargs) -> DecisionLogger:
    """Create decision logger."""
    return DecisionLogger(session_id, **kwargs)