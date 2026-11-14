"""Laboratory sample register (compatibility facade).

Historically this module provided a minimal sample register. The full Phase 6
laboratory management implementation lives in :mod:`geneai.lab_management`
(samples, experiments, projects, datasets, results, status history).

This module re-exports that implementation while keeping ``geneai.lab.DB_PATH``
as the configurable database location used by the Streamlit app and tests.
"""
from __future__ import annotations

from typing import Any

from geneai import lab_management as _lm
from geneai.config import DATABASE_PATH

#: Database location used by this facade. Overridable for tests/installs.
DB_PATH = DATABASE_PATH

MATERIALS = _lm.MATERIALS
SAMPLE_STATUSES = _lm.SAMPLE_STATUSES
EXPERIMENT_STATUSES = _lm.EXPERIMENT_STATUSES
RESULT_STATUSES = _lm.RESULT_STATUSES


def _sync_db_path() -> None:
    """Propagate the facade's DB_PATH to the implementation module."""
    _lm.DB_PATH = DB_PATH


def add_sample(
    name: str,
    material: str,
    project: str = "",
    notes: str = "",
    status: str = "received",
) -> str:
    """Register a sample in the local SQLite database and return its identifier."""
    _sync_db_path()
    return _lm.add_sample(name, material, project, notes, status)


def load_samples() -> list[dict[str, Any]]:
    """Return samples newest first."""
    _sync_db_path()
    return _lm.load_samples()


def get_sample(sample_id: str) -> dict[str, Any] | None:
    _sync_db_path()
    return _lm.get_sample(sample_id)


def update_sample(sample_id: str, **fields: Any) -> bool:
    _sync_db_path()
    return _lm.update_sample(sample_id, **fields)


def delete_sample(sample_id: str) -> bool:
    _sync_db_path()
    return _lm.delete_sample(sample_id)


def set_sample_status(
    sample_id: str,
    new_status: str,
    changed_by: str = "",
    reason: str = "",
) -> bool:
    _sync_db_path()
    return _lm.set_sample_status(sample_id, new_status, changed_by, reason)


def get_sample_status_history(sample_id: str) -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.get_sample_status_history(sample_id)


def create_experiment(name: str, description: str = "", project_id: str = "") -> str:
    _sync_db_path()
    return _lm.create_experiment(name, description, project_id)


def load_experiments() -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.load_experiments()


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    _sync_db_path()
    return _lm.get_experiment(experiment_id)


def update_experiment(experiment_id: str, **fields: Any) -> bool:
    _sync_db_path()
    return _lm.update_experiment(experiment_id, **fields)


def delete_experiment(experiment_id: str) -> bool:
    _sync_db_path()
    return _lm.delete_experiment(experiment_id)


def add_sample_to_experiment(experiment_id: str, sample_id: str, role: str = "input") -> bool:
    _sync_db_path()
    return _lm.add_sample_to_experiment(experiment_id, sample_id, role)


def get_experiment_samples(experiment_id: str) -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.get_experiment_samples(experiment_id)


def create_project(name: str, description: str = "", owner: str = "") -> str:
    _sync_db_path()
    return _lm.create_project(name, description, owner)


def load_projects() -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.load_projects()


def get_project(project_id: str) -> dict[str, Any] | None:
    _sync_db_path()
    return _lm.get_project(project_id)


def add_result(
    experiment_id: str,
    name: str,
    description: str = "",
    result_type: str = "observation",
    data: dict[str, Any] | None = None,
    status: str = "pending",
) -> str:
    _sync_db_path()
    return _lm.add_result(experiment_id, name, description, result_type, data, status)


def load_results(experiment_id: str | None = None) -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.load_results(experiment_id)


def register_dataset(
    name: str,
    description: str = "",
    project_id: str = "",
    file_path: str = "",
    file_type: str = "",
    row_count: int = 0,
    column_count: int = 0,
    validation_status: str = "pending",
) -> str:
    _sync_db_path()
    return _lm.register_dataset(
        name, description, project_id, file_path, file_type, row_count, column_count, validation_status
    )


def load_datasets() -> list[dict[str, Any]]:
    _sync_db_path()
    return _lm.load_datasets()


def get_lab_stats() -> dict[str, int]:
    _sync_db_path()
    return _lm.get_lab_stats()


__all__ = [
    "DB_PATH",
    "EXPERIMENT_STATUSES",
    "MATERIALS",
    "RESULT_STATUSES",
    "SAMPLE_STATUSES",
    "add_result",
    "add_sample",
    "add_sample_to_experiment",
    "create_experiment",
    "create_project",
    "delete_experiment",
    "delete_sample",
    "get_experiment",
    "get_experiment_samples",
    "get_lab_stats",
    "get_project",
    "get_sample",
    "get_sample_status_history",
    "load_datasets",
    "load_experiments",
    "load_projects",
    "load_results",
    "load_samples",
    "register_dataset",
    "set_sample_status",
    "update_experiment",
    "update_sample",
]
