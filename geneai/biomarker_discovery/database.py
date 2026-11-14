"""Database module for biomarker discovery results."""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

BD_DB_PATH = DATABASE_PATH.parent / "geneai_biomarker_discovery.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Analysis runs
CREATE TABLE IF NOT EXISTS bd_analysis_runs (
    run_id TEXT PRIMARY KEY,
    dataset_name TEXT,
    n_samples INTEGER,
    n_features INTEGER,
    class_distribution_json TEXT,
    feature_selection_method TEXT,
    biomarker_type TEXT,
    best_model TEXT,
    best_model_auc REAL,
    cv_summary_json TEXT,
    dataset_info_json TEXT,
    warnings_json TEXT,
    created_at REAL NOT NULL,
    status TEXT DEFAULT 'completed'
);

-- Biomarker candidates
CREATE TABLE IF NOT EXISTS bd_biomarker_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    feature_importance REAL,
    p_value REAL,
    fold_change REAL,
    auc_score REAL,
    cv_auc_mean REAL,
    cv_auc_std REAL,
    expression_stats_json TEXT,
    biomarker_type TEXT,
    confidence TEXT,
    validation_status TEXT,
    rank INTEGER,
    FOREIGN KEY (run_id) REFERENCES bd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Model performance
CREATE TABLE IF NOT EXISTS bd_model_performance (
    perf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    cv_auc_mean REAL,
    cv_auc_std REAL,
    cv_scores_json TEXT,
    test_auc REAL,
    FOREIGN KEY (run_id) REFERENCES bd_analysis_runs(run_id) ON DELETE CASCADE
);

-- ROC curves
CREATE TABLE IF NOT EXISTS bd_roc_curves (
    roc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    fpr_json TEXT NOT NULL,
    tpr_json TEXT NOT NULL,
    thresholds_json TEXT,
    auc REAL,
    FOREIGN KEY (run_id) REFERENCES bd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Feature ranking
CREATE TABLE IF NOT EXISTS bd_feature_ranking (
    rank_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    mean_importance REAL,
    std_importance REAL,
    median_importance REAL,
    max_importance REAL,
    models_agreeing INTEGER,
    rank INTEGER,
    FOREIGN KEY (run_id) REFERENCES bd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Differential expression
CREATE TABLE IF NOT EXISTS bd_differential_expression (
    de_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    fold_change REAL,
    log2_fold_change REAL,
    p_value REAL,
    mean_class_0 REAL,
    mean_class_1 REAL,
    t_statistic REAL,
    FOREIGN KEY (run_id) REFERENCES bd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Dataset info
CREATE TABLE IF NOT EXISTS bd_datasets (
    dataset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    source TEXT,  # GEO, local, etc.
    accession TEXT,
    n_samples INTEGER,
    n_features INTEGER,
    description TEXT,
    metadata_json TEXT,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS bd_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_bd_runs_created ON bd_analysis_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_bd_candidates_run ON bd_biomarker_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_bd_candidates_gene ON bd_biomarker_candidates(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_bd_model_run ON bd_model_performance(run_id);
CREATE INDEX IF NOT EXISTS idx_bd_roc_run ON bd_roc_curves(run_id);
CREATE INDEX IF NOT EXISTS idx_bd_ranking_run ON bd_feature_ranking(run_id);
CREATE INDEX IF NOT EXISTS idx_bd_de_run ON bd_differential_expression(run_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(BD_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_bd_database() -> None:
    """Create all BD tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO bd_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("BD database initialized at %s", BD_DB_PATH)
        finally:
            conn.close()


def get_bd_db_version() -> int:
    """Get current BD database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM bd_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# Analysis run operations
def store_bd_analysis_run(
    run_id: str,
    dataset_name: str | None,
    dataset_info: dict[str, Any],
    best_model: str,
    best_model_auc: float,
    cv_summary: dict[str, Any],
    warnings: list[str],
) -> str:
    """Store a biomarker discovery analysis run."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO bd_analysis_runs (
                    run_id, dataset_name, n_samples, n_features,
                    class_distribution_json, feature_selection_method,
                    biomarker_type, best_model, best_model_auc,
                    cv_summary_json, dataset_info_json, warnings_json,
                    created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    best_model=excluded.best_model,
                    best_model_auc=excluded.best_model_auc,
                    cv_summary_json=excluded.cv_summary_json,
                    status=excluded.status
                """,
                (
                    run_id,
                    dataset_name,
                    dataset_info.get("n_samples", 0),
                    dataset_info.get("n_features_selected", 0),
                    json.dumps(dataset_info.get("class_distribution", {})),
                    dataset_info.get("feature_selection_method", ""),
                    "diagnostic",  # Default
                    best_model,
                    best_model_auc,
                    json.dumps(cv_summary),
                    json.dumps(dataset_info),
                    json.dumps(warnings),
                    now,
                    "completed",
                ),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()


def store_bd_candidates(run_id: str, candidates: list[dict[str, Any]]) -> None:
    """Store biomarker candidates."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for i, cand in enumerate(candidates):
                conn.execute(
                    """
                    INSERT INTO bd_biomarker_candidates (
                        run_id, gene_symbol, feature_importance, p_value,
                        fold_change, auc_score, cv_auc_mean, cv_auc_std,
                        expression_stats_json, biomarker_type, confidence,
                        validation_status, rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        cand.get("gene_symbol"),
                        cand.get("feature_importance", 0.0),
                        cand.get("p_value", 1.0),
                        cand.get("fold_change", 0.0),
                        cand.get("auc_score", 0.5),
                        cand.get("cv_auc_mean", 0.5),
                        cand.get("cv_auc_std", 0.0),
                        json.dumps(cand.get("expression_stats", {})),
                        cand.get("biomarker_type", "diagnostic"),
                        cand.get("confidence", "low"),
                        cand.get("validation_status", "research"),
                        i + 1,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_bd_model_performance(run_id: str, models: dict[str, Any]) -> None:
    """Store model performance."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for name, result in models.items():
                if "error" in result:
                    continue
                conn.execute(
                    """
                    INSERT INTO bd_model_performance (
                        run_id, model_name, cv_auc_mean, cv_auc_std,
                        cv_scores_json, test_auc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        name,
                        result.get("cv_auc_mean", 0.0),
                        result.get("cv_auc_std", 0.0),
                        json.dumps(result.get("cv_scores", [])),
                        result.get("test_auc", 0.0),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_bd_roc_curves(run_id: str, roc_curves: dict[str, Any]) -> None:
    """Store ROC curves."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for name, curve in roc_curves.items():
                conn.execute(
                    """
                    INSERT INTO bd_roc_curves (
                        run_id, model_name, fpr_json, tpr_json,
                        thresholds_json, auc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        name,
                        json.dumps(curve.get("fpr", [])),
                        json.dumps(curve.get("tpr", [])),
                        json.dumps(curve.get("thresholds", [])),
                        curve.get("auc", 0.0),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_bd_feature_ranking(run_id: str, ranking: list[dict[str, Any]]) -> None:
    """Store feature ranking."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for i, item in enumerate(ranking):
                conn.execute(
                    """
                    INSERT INTO bd_feature_ranking (
                        run_id, gene_symbol, mean_importance, std_importance,
                        median_importance, max_importance, models_agreeing, rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        item.get("gene"),
                        item.get("mean_importance", 0.0),
                        item.get("std_importance", 0.0),
                        item.get("median_importance", 0.0),
                        item.get("max_importance", 0.0),
                        item.get("models_agreeing", 0),
                        i + 1,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_bd_differential_expression(run_id: str, de_results: dict[str, Any]) -> None:
    """Store differential expression results."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for gene, de in de_results.items():
                conn.execute(
                    """
                    INSERT INTO bd_differential_expression (
                        run_id, gene_symbol, fold_change, log2_fold_change,
                        p_value, mean_class_0, mean_class_1, t_statistic
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        gene,
                        de.get("fold_change", 0.0),
                        de.get("log2_fold_change", 0.0),
                        de.get("p_value", 1.0),
                        de.get("mean_class_0", 0.0),
                        de.get("mean_class_1", 0.0),
                        de.get("t_statistic", 0.0),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_bd_dataset(
    name: str,
    source: str,
    accession: str | None,
    n_samples: int,
    n_features: int,
    description: str,
    metadata: dict[str, Any],
) -> int:
    """Store dataset metadata."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO bd_datasets (
                    name, source, accession, n_samples, n_features,
                    description, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    n_samples=excluded.n_samples,
                    n_features=excluded.n_features,
                    metadata_json=excluded.metadata_json
                """,
                (
                    name, source, accession, n_samples, n_features,
                    description, json.dumps(metadata), now,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


# Query operations
def get_bd_analysis_run(run_id: str) -> dict[str, Any] | None:
    """Get BD analysis run by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM bd_analysis_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["class_distribution", "cv_summary", "dataset_info", "warnings"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_bd_candidates(run_id: str) -> list[dict[str, Any]]:
    """Get biomarker candidates for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM bd_biomarker_candidates WHERE run_id=? ORDER BY rank",
                (run_id,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("expression_stats_json"):
                    data["expression_stats"] = json.loads(data["expression_stats_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def get_bd_model_performance(run_id: str) -> list[dict[str, Any]]:
    """Get model performance for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM bd_model_performance WHERE run_id=?",
                (run_id,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("cv_scores_json"):
                    data["cv_scores"] = json.loads(data["cv_scores_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def get_bd_roc_curves(run_id: str) -> dict[str, Any]:
    """Get ROC curves for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM bd_roc_curves WHERE run_id=?",
                (run_id,),
            ).fetchall()
            curves = {}
            for row in rows:
                data = dict(row)
                curves[data["model_name"]] = {
                    "fpr": json.loads(data["fpr_json"]),
                    "tpr": json.loads(data["tpr_json"]),
                    "thresholds": json.loads(data["thresholds_json"]) if data["thresholds_json"] else [],
                    "auc": data["auc"],
                }
            return curves
        finally:
            conn.close()


def get_bd_feature_ranking(run_id: str) -> list[dict[str, Any]]:
    """Get feature ranking for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM bd_feature_ranking WHERE run_id=? ORDER BY rank",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_bd_differential_expression(run_id: str) -> dict[str, Any]:
    """Get differential expression for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM bd_differential_expression WHERE run_id=?",
                (run_id,),
            ).fetchall()
            return {row["gene_symbol"]: dict(row) for row in rows}
        finally:
            conn.close()


def get_recent_bd_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent BD analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT run_id, dataset_name, n_samples, n_features,
                       best_model, best_model_auc, created_at
                FROM bd_analysis_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def search_bd_runs(
    gene_symbol: str | None = None,
    biomarker_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search BD analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM bd_analysis_runs WHERE 1=1"
            params = []
            
            if biomarker_type:
                query += " AND biomarker_type = ?"
                params.append(biomarker_type)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["class_distribution"] = json.loads(data["class_distribution_json"])
                data["cv_summary"] = json.loads(data["cv_summary_json"])
                data["dataset_info"] = json.loads(data["dataset_info_json"])
                data["warnings"] = json.loads(data["warnings_json"])
                results.append(data)
            
            # Filter by gene if specified
            if gene_symbol:
                filtered = []
                for run in results:
                    candidates = get_bd_candidates(run["run_id"])
                    if any(c["gene_symbol"] == gene_symbol for c in candidates):
                        filtered.append(run)
                return filtered
            
            return results
        finally:
            conn.close()


def clear_bd_analysis_run(run_id: str) -> bool:
    """Delete a BD analysis run and all associated data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM bd_analysis_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# Initialize on import (commented out to avoid import-time errors)
# initialize_bd_database()