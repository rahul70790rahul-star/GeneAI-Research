"""Reproducibility & Experiment Tracking for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

REPRO_DB_PATH = DATABASE_PATH.parent / "geneai_reproducibility.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Experiments/runs
CREATE TABLE IF NOT EXISTS repro_experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    pipeline_version TEXT,
    git_commit TEXT,
    git_branch TEXT,
    git_dirty INTEGER DEFAULT 0,
    python_version TEXT,
    dependencies_json TEXT,
    environment_json TEXT,
    parameters_json TEXT,
    inputs_json TEXT,
    outputs_json TEXT,
    metrics_json TEXT,
    artifacts_json TEXT,
    status TEXT DEFAULT 'running',  -- running, completed, failed, archived
    started_at REAL NOT NULL,
    completed_at REAL,
    duration_seconds REAL,
    parent_experiment_id TEXT,
    tags_json TEXT,
    notes TEXT
);

-- Artifacts (files, models, data)
CREATE TABLE IF NOT EXISTS repro_artifacts (
    artifact_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,  -- model, data, plot, report, log, config
    path TEXT,
    size_bytes INTEGER,
    checksum_sha256 TEXT,
    metadata_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES repro_experiments(experiment_id) ON DELETE CASCADE
);

-- Pipeline steps within experiment
CREATE TABLE IF NOT EXISTS repro_steps (
    step_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    function_name TEXT,
    module TEXT,
    parameters_json TEXT,
    inputs_hash TEXT,
    outputs_hash TEXT,
    started_at REAL,
    completed_at REAL,
    duration_seconds REAL,
    status TEXT DEFAULT 'pending',  -- pending, running, completed, failed, skipped
    error_message TEXT,
    metrics_json TEXT,
    FOREIGN KEY (experiment_id) REFERENCES repro_experiments(experiment_id) ON DELETE CASCADE
);

-- Comparisons between experiments
CREATE TABLE IF NOT EXISTS repro_comparisons (
    comparison_id TEXT PRIMARY KEY,
    experiment_ids_json TEXT NOT NULL,
    comparison_type TEXT,  -- metric, parameter, artifact, full
    results_json TEXT,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS repro_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(REPRO_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_reproducibility() -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO repro_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("Reproducibility database initialized at %s", REPRO_DB_PATH)
        finally:
            conn.close()


def get_git_info() -> dict[str, Any]:
    """Get git repository information."""
    info = {
        "commit": None,
        "branch": None,
        "dirty": False,
        "remote_url": None,
    }
    try:
        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()
        
        # Get branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
        
        # Check dirty
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5
        )
        info["dirty"] = len(result.stdout.strip()) > 0
        
        # Get remote
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["remote_url"] = result.stdout.strip()
    except Exception:
        pass
    return info


def get_python_environment() -> dict[str, Any]:
    """Get Python environment information."""
    deps = {}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            packages = json.loads(result.stdout)
            deps = {p["name"]: p["version"] for p in packages}
    except Exception:
        pass
    
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": sys.platform,
        "dependencies": deps,
    }


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_data_hash(data: Any) -> str:
    """Compute hash of data structure."""
    serialized = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()[:16]


@dataclass
class Experiment:
    """Tracked experiment/run."""
    experiment_id: str
    name: str
    description: str = ""
    pipeline_version: str = "4.13"
    parameters: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    duration_seconds: float | None = None
    parent_experiment_id: str | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    
    # Auto-filled
    git_commit: str = ""
    git_branch: str = ""
    git_dirty: bool = False
    python_version: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)


class ReproducibilityTracker:
    """Track experiments for reproducibility."""
    
    def __init__(self, experiment: Experiment | None = None):
        self.experiment = experiment
        self.steps: list[dict] = []
        self._step_order = 0
    
    @classmethod
    def start(cls, name: str, description: str = "", parameters: dict | None = None,
              inputs: dict | None = None, parent_id: str | None = None,
              tags: list[str] | None = None) -> "ReproducibilityTracker":
        """Start a new tracked experiment."""
        git_info = get_git_info()
        env_info = get_python_environment()
        
        exp_id = hashlib.sha256(f"{name}{time.time()}".encode()).hexdigest()[:12]
        
        experiment = Experiment(
            experiment_id=exp_id,
            name=name,
            description=description,
            parameters=parameters or {},
            inputs=inputs or {},
            parent_experiment_id=parent_id,
            tags=tags or [],
            git_commit=git_info["commit"] or "",
            git_branch=git_info["branch"] or "",
            git_dirty=git_info["dirty"],
            python_version=env_info["python_version"],
            dependencies=env_info["dependencies"],
            environment=env_info,
        )
        
        tracker = cls(experiment)
        tracker._save_experiment()
        return tracker
    
    def _save_experiment(self) -> None:
        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO repro_experiments (
                        experiment_id, name, description, pipeline_version,
                        git_commit, git_branch, git_dirty, python_version,
                        dependencies_json, environment_json, parameters_json,
                        inputs_json, outputs_json, metrics_json, artifacts_json,
                        status, started_at, completed_at, duration_seconds,
                        parent_experiment_id, tags_json, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id) DO UPDATE SET
                        outputs_json=excluded.outputs_json,
                        metrics_json=excluded.metrics_json,
                        artifacts_json=excluded.artifacts_json,
                        status=excluded.status,
                        completed_at=excluded.completed_at,
                        duration_seconds=excluded.duration_seconds,
                        notes=excluded.notes
                    """,
                    (
                        self.experiment.experiment_id,
                        self.experiment.name,
                        self.experiment.description,
                        self.experiment.pipeline_version,
                        self.experiment.git_commit,
                        self.experiment.git_branch,
                        int(self.experiment.git_dirty),
                        self.experiment.python_version,
                        json.dumps(self.experiment.dependencies),
                        json.dumps(self.experiment.environment),
                        json.dumps(self.experiment.parameters),
                        json.dumps(self.experiment.inputs),
                        json.dumps(self.experiment.outputs),
                        json.dumps(self.experiment.metrics),
                        json.dumps(self.experiment.artifacts),
                        self.experiment.status,
                        self.experiment.started_at,
                        self.experiment.completed_at,
                        self.experiment.duration_seconds,
                        self.experiment.parent_experiment_id,
                        json.dumps(self.experiment.tags),
                        self.experiment.notes,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
    
    def log_step(self, step_name: str, function_name: str = "", module: str = "",
                 parameters: dict | None = None, inputs: Any = None, outputs: Any = None,
                 metrics: dict | None = None, status: str = "completed",
                 error: str | None = None) -> str:
        """Log a pipeline step."""
        self._step_order += 1
        step_id = f"{self.experiment.experiment_id}_step{self._step_order}"
        
        step = {
            "step_id": step_id,
            "experiment_id": self.experiment.experiment_id,
            "step_name": step_name,
            "step_order": self._step_order,
            "function_name": function_name,
            "module": module,
            "parameters_json": json.dumps(parameters or {}),
            "inputs_hash": compute_data_hash(inputs) if inputs else "",
            "outputs_hash": compute_data_hash(outputs) if outputs else "",
            "started_at": time.time(),
            "completed_at": time.time(),
            "duration_seconds": 0,
            "status": status,
            "error_message": error or "",
            "metrics_json": json.dumps(metrics or {}),
        }
        
        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO repro_steps (
                        step_id, experiment_id, step_name, step_order,
                        function_name, module, parameters_json, inputs_hash,
                        outputs_hash, started_at, completed_at, duration_seconds,
                        status, error_message, metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step["step_id"], step["experiment_id"], step["step_name"],
                        step["step_order"], step["function_name"], step["module"],
                        step["parameters_json"], step["inputs_hash"], step["outputs_hash"],
                        step["started_at"], step["completed_at"], step["duration_seconds"],
                        step["status"], step["error_message"], step["metrics_json"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        
        self.steps.append(step)
        if metrics:
            self.experiment.metrics.update(metrics)
            self._save_experiment()
        return step_id
    
    def log_artifact(self, name: str, artifact_type: str, path: str | Path,
                     metadata: dict | None = None) -> str:
        """Log an output artifact."""
        path = Path(path)
        artifact_id = hashlib.sha256(f"{name}{path}{time.time()}".encode()).hexdigest()[:12]
        
        size = path.stat().st_size if path.exists() else 0
        checksum = compute_file_hash(path) if path.exists() else ""
        
        artifact = {
            "artifact_id": artifact_id,
            "experiment_id": self.experiment.experiment_id,
            "name": name,
            "artifact_type": artifact_type,
            "path": str(path),
            "size_bytes": size,
            "checksum_sha256": checksum,
            "metadata_json": json.dumps(metadata or {}),
            "created_at": time.time(),
        }
        
        self.experiment.artifacts.append(artifact)
        
        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO repro_artifacts (
                        artifact_id, experiment_id, name, artifact_type,
                        path, size_bytes, checksum_sha256, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact["artifact_id"], artifact["experiment_id"],
                        artifact["name"], artifact["artifact_type"],
                        artifact["path"], artifact["size_bytes"],
                        artifact["checksum_sha256"], artifact["metadata_json"],
                        artifact["created_at"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        
        return artifact_id
    
    def log_metric(self, key: str, value: Any) -> None:
        """Log a metric."""
        self.experiment.metrics[key] = value
        self._save_experiment()
    
    def log_output(self, key: str, value: Any) -> None:
        """Log an output."""
        self.experiment.outputs[key] = value
        self._save_experiment()
    
    def add_note(self, note: str) -> None:
        """Add a note to the experiment."""
        if self.experiment.notes:
            self.experiment.notes += f"\n{datetime.now().isoformat()}: {note}"
        else:
            self.experiment.notes = f"{datetime.now().isoformat()}: {note}"
        self._save_experiment()
    
    def complete(self, status: str = "completed") -> None:
        """Mark experiment as complete."""
        self.experiment.status = status
        self.experiment.completed_at = time.time()
        self.experiment.duration_seconds = self.experiment.completed_at - self.experiment.started_at
        self._save_experiment()
    
    def get_experiment(self) -> Experiment:
        return self.experiment
    
    @staticmethod
    def load(experiment_id: str) -> Experiment | None:
        with _DB_LOCK:
            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM repro_experiments WHERE experiment_id=?", (experiment_id,)
                ).fetchone()
                if not row:
                    return None
                
                return Experiment(
                    experiment_id=row["experiment_id"],
                    name=row["name"],
                    description=row["description"],
                    pipeline_version=row["pipeline_version"],
                    parameters=json.loads(row["parameters_json"]),
                    inputs=json.loads(row["inputs_json"]),
                    outputs=json.loads(row["outputs_json"]),
                    metrics=json.loads(row["metrics_json"]),
                    artifacts=json.loads(row["artifacts_json"]),
                    status=row["status"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    duration_seconds=row["duration_seconds"],
                    parent_experiment_id=row["parent_experiment_id"],
                    tags=json.loads(row["tags_json"]),
                    notes=row["notes"],
                    git_commit=row["git_commit"],
                    git_branch=row["git_branch"],
                    git_dirty=bool(row["git_dirty"]),
                    python_version=row["python_version"],
                    dependencies=json.loads(row["dependencies_json"]),
                    environment=json.loads(row["environment_json"]),
                )
            finally:
                conn.close()
    
    @staticmethod
    def list_experiments(limit: int = 50, status: str | None = None) -> list[Experiment]:
        with _DB_LOCK:
            conn = _get_connection()
            try:
                query = "SELECT * FROM repro_experiments"
                params = []
                if status:
                    query += " WHERE status=?"
                    params.append(status)
                query += " ORDER BY started_at DESC LIMIT ?"
                params.append(limit)
                
                rows = conn.execute(query, params).fetchall()
                return [
                    Experiment(
                        experiment_id=r["experiment_id"],
                        name=r["name"],
                        description=r["description"],
                        pipeline_version=r["pipeline_version"],
                        parameters=json.loads(r["parameters_json"]),
                        inputs=json.loads(r["inputs_json"]),
                        outputs=json.loads(r["outputs_json"]),
                        metrics=json.loads(r["metrics_json"]),
                        artifacts=json.loads(r["artifacts_json"]),
                        status=r["status"],
                        started_at=r["started_at"],
                        completed_at=r["completed_at"],
                        duration_seconds=r["duration_seconds"],
                        parent_experiment_id=r["parent_experiment_id"],
                        tags=json.loads(r["tags_json"]),
                        notes=r["notes"],
                        git_commit=r["git_commit"],
                        git_branch=r["git_branch"],
                        git_dirty=bool(r["git_dirty"]),
                        python_version=r["python_version"],
                        dependencies=json.loads(r["dependencies_json"]),
                        environment=json.loads(r["environment_json"]),
                    ) for r in rows
                ]
            finally:
                conn.close()
    
    @staticmethod
    def compare(experiment_ids: list[str]) -> dict[str, Any]:
        """Compare multiple experiments."""
        experiments = []
        for eid in experiment_ids:
            exp = ReproducibilityTracker.load(eid)
            if exp:
                experiments.append(exp)
        
        if len(experiments) < 2:
            return {"error": "Need at least 2 experiments to compare"}
        
        # Compare parameters
        all_params = set()
        for exp in experiments:
            all_params.update(exp.parameters.keys())
        
        param_comparison = {}
        for param in sorted(all_params):
            values = {exp.experiment_id: exp.parameters.get(param) for exp in experiments}
            if len(set(values.values())) > 1:
                param_comparison[param] = values
        
        # Compare metrics
        all_metrics = set()
        for exp in experiments:
            all_metrics.update(exp.metrics.keys())
        
        metric_comparison = {}
        for metric in sorted(all_metrics):
            values = {exp.experiment_id: exp.metrics.get(metric) for exp in experiments}
            if any(v is not None for v in values.values()):
                metric_comparison[metric] = values
        
        # Compare artifacts
        artifact_comparison = {}
        for exp in experiments:
            for art in exp.artifacts:
                key = f"{art['name']} ({art['artifact_type']})"
                if key not in artifact_comparison:
                    artifact_comparison[key] = {}
                artifact_comparison[key][exp.experiment_id] = {
                    "path": art["path"],
                    "checksum": art["checksum_sha256"],
                    "size": art["size_bytes"],
                }
        
        return {
            "experiment_ids": experiment_ids,
            "parameters": param_comparison,
            "metrics": metric_comparison,
            "artifacts": artifact_comparison,
            "git_commits": {exp.experiment_id: exp.git_commit for exp in experiments},
        }
    
    @staticmethod
    def export_experiment(experiment_id: str, output_dir: Path) -> Path:
        """Export experiment with all artifacts for reproduction."""
        exp = ReproducibilityTracker.load(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save experiment metadata
        with open(output_dir / "experiment.json", "w") as f:
            json.dump(asdict(exp), f, indent=2, default=str)
        
        # Save steps
        with _DB_LOCK:
            conn = _get_connection()
            try:
                steps = conn.execute(
                    "SELECT * FROM repro_steps WHERE experiment_id=? ORDER BY step_order",
                    (experiment_id,)
                ).fetchall()
                with open(output_dir / "steps.json", "w") as f:
                    json.dump([dict(r) for r in steps], f, indent=2, default=str)
            finally:
                conn.close()
        
        # Copy artifacts
        artifacts_dir = output_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        for art in exp.artifacts:
            src = Path(art["path"])
            if src.exists():
                import shutil
                dst = artifacts_dir / src.name
                shutil.copy2(src, dst)
        
        # Generate requirements.txt
        with open(output_dir / "requirements.txt", "w") as f:
            for pkg, ver in exp.dependencies.items():
                f.write(f"{pkg}=={ver}\n")
        
        # Generate reproduction script
        script = f"""#!/usr/bin/env python
# Reproduction script for experiment {experiment_id}
# Generated: {datetime.now().isoformat()}

import json
import subprocess
import sys

def install_dependencies():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    print(f"Reproducing experiment: {exp.name}")
    print(f"Git commit: {exp.git_commit}")
    print(f"Pipeline version: {exp.pipeline_version}")
    print("Parameters:")
    for k, v in {json.dumps(exp.parameters, indent=2)}.items():
        print(f"  {k}: {v}")
    # Add your pipeline execution code here

if __name__ == "__main__":
    install_dependencies()
    main()
"""
        with open(output_dir / "reproduce.py", "w") as f:
            f.write(script)
        
        return output_dir


def track_function(func):
    """Decorator to automatically track a function as an experiment step."""
    def wrapper(*args, **kwargs):
        # This would integrate with an active tracker
        # For now, just call the function
        return func(*args, **kwargs)
    return wrapper


initialize_reproducibility()