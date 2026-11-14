"""ADMET Database - Module 8: Database integration for ADMET predictions."""
from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ADMET database path
ADMET_DB_PATH = DATABASE_PATH.parent / "geneai_admet.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- ADMET prediction runs
CREATE TABLE IF NOT EXISTS admet_prediction_runs (
    run_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,
    canonical_smiles TEXT,
    inchikey TEXT,
    molecular_properties_json TEXT NOT NULL,
    drug_likeness_json TEXT,
    created_at REAL NOT NULL,
    model_version TEXT NOT NULL
);

-- Individual ADMET predictions
CREATE TABLE IF NOT EXISTS admet_predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    category TEXT NOT NULL,
    raw_value REAL,
    probability REAL,
    prediction TEXT,
    confidence TEXT,
    is_measured INTEGER DEFAULT 0,
    source TEXT,
    details_json TEXT,
    FOREIGN KEY (run_id) REFERENCES admet_prediction_runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, endpoint)
);

-- ADMET scores
CREATE TABLE IF NOT EXISTS admet_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    overall_score REAL NOT NULL,
    risk_classification TEXT NOT NULL,
    drug_likeness_score REAL,
    category_scores_json TEXT NOT NULL,
    summary_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES admet_prediction_runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id)
);

-- Compound registry (links to drug_discovery database)
CREATE TABLE IF NOT EXISTS admet_compounds (
    compound_id INTEGER PRIMARY KEY AUTOINCREMENT,
    smiles TEXT NOT NULL UNIQUE,
    canonical_smiles TEXT,
    inchikey TEXT,
    name TEXT,
    source TEXT,
    source_id TEXT,
    created_at REAL NOT NULL
);

-- Prediction history for compounds
CREATE TABLE IF NOT EXISTS admet_prediction_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    overall_score REAL,
    risk_classification TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (compound_id) REFERENCES admet_compounds(compound_id) ON DELETE CASCADE
);

-- Model metadata
CREATE TABLE IF NOT EXISTS admet_models (
    model_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    model_type TEXT NOT NULL,
    model_version TEXT NOT NULL,
    training_data_hash TEXT,
    training_samples INTEGER,
    cv_roc_auc REAL,
    train_roc_auc REAL,
    feature_names_json TEXT,
    model_params_json TEXT,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS admet_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_admet_runs_smiles ON admet_prediction_runs(smiles);
CREATE INDEX IF NOT EXISTS idx_admet_runs_inchikey ON admet_prediction_runs(inchikey);
CREATE INDEX IF NOT EXISTS idx_admet_predictions_run ON admet_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_admet_scores_run ON admet_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_admet_compounds_smiles ON admet_compounds(smiles);
CREATE INDEX IF NOT EXISTS idx_admet_compounds_inchikey ON admet_compounds(inchikey);
CREATE INDEX IF NOT EXISTS idx_admet_history_compound ON admet_prediction_history(compound_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(ADMET_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_admet_database() -> None:
    """Create all ADMET tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO admet_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("ADMET database initialized at %s", ADMET_DB_PATH)
        finally:
            conn.close()


def get_admet_db_version() -> int:
    """Get current ADMET database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM admet_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# ADMET Prediction Run operations
def store_admet_prediction_run(
    run_id: str,
    smiles: str,
    canonical_smiles: str | None,
    inchikey: str | None,
    molecular_properties: dict[str, Any],
    drug_likeness: dict[str, Any] | None,
    model_version: str = "1.0",
) -> str:
    """Store an ADMET prediction run."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            conn.execute(
                """
                INSERT INTO admet_prediction_runs (
                    run_id, smiles, canonical_smiles, inchikey,
                    molecular_properties_json, drug_likeness_json,
                    created_at, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    molecular_properties_json=excluded.molecular_properties_json,
                    drug_likeness_json=excluded.drug_likeness_json,
                    model_version=excluded.model_version
                """,
                (
                    run_id,
                    smiles,
                    canonical_smiles,
                    inchikey,
                    json.dumps(molecular_properties),
                    json.dumps(drug_likeness) if drug_likeness else None,
                    now,
                    model_version,
                ),
            )
            
            # Register compound
            if canonical_smiles:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO admet_compounds (smiles, canonical_smiles, inchikey, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (smiles, canonical_smiles, inchikey, "user_input", now),
                )
            
            conn.commit()
            return run_id
        finally:
            conn.close()


def store_admet_predictions(run_id: str, predictions: list[dict[str, Any]]) -> None:
    """Store individual ADMET predictions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            for pred in predictions:
                conn.execute(
                    """
                    INSERT INTO admet_predictions (
                        run_id, endpoint, category, raw_value, probability,
                        prediction, confidence, is_measured, source, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, endpoint) DO UPDATE SET
                        raw_value=excluded.raw_value,
                        probability=excluded.probability,
                        prediction=excluded.prediction,
                        confidence=excluded.confidence,
                        is_measured=excluded.is_measured,
                        source=excluded.source,
                        details_json=excluded.details_json
                    """,
                    (
                        run_id,
                        pred.get("endpoint"),
                        pred.get("category"),
                        pred.get("value"),
                        pred.get("probability"),
                        pred.get("prediction"),
                        pred.get("confidence"),
                        1 if pred.get("is_measured") else 0,
                        pred.get("source", "computational"),
                        json.dumps(pred.get("details", {})),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_admet_score(run_id: str, score_data: dict[str, Any]) -> None:
    """Store ADMET score."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            conn.execute(
                """
                INSERT INTO admet_scores (
                    run_id, overall_score, risk_classification, drug_likeness_score,
                    category_scores_json, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    overall_score=excluded.overall_score,
                    risk_classification=excluded.risk_classification,
                    drug_likeness_score=excluded.drug_likeness_score,
                    category_scores_json=excluded.category_scores_json,
                    summary_json=excluded.summary_json
                """,
                (
                    run_id,
                    score_data.get("overall_score"),
                    score_data.get("risk_classification"),
                    score_data.get("drug_likeness_score"),
                    json.dumps(score_data.get("category_scores", {})),
                    json.dumps(score_data.get("summary", {})),
                    now,
                ),
            )
            
            # Add to history
            conn.execute(
                """
                INSERT INTO admet_prediction_history (compound_id, run_id, overall_score, risk_classification, created_at)
                SELECT c.compound_id, ?, ?, ?, ?
                FROM admet_compounds c
                JOIN admet_prediction_runs r ON r.canonical_smiles = c.canonical_smiles
                WHERE r.run_id = ?
                """,
                (run_id, score_data.get("overall_score"), score_data.get("risk_classification"), now, run_id),
            )
            
            conn.commit()
        finally:
            conn.close()


def store_admet_model(model_data: dict[str, Any]) -> str:
    """Store trained model metadata."""
    now = time.time()
    model_id = model_data.get("model_id") or f"{model_data['endpoint']}_{model_data['model_type']}_{int(now)}"
    
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            conn.execute(
                """
                INSERT INTO admet_models (
                    model_id, endpoint, model_type, model_version, training_data_hash,
                    training_samples, cv_roc_auc, train_roc_auc, feature_names_json,
                    model_params_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    model_version=excluded.model_version,
                    training_samples=excluded.training_samples,
                    cv_roc_auc=excluded.cv_roc_auc,
                    train_roc_auc=excluded.train_roc_auc
                """,
                (
                    model_id,
                    model_data.get("endpoint"),
                    model_data.get("model_type"),
                    model_data.get("model_version", "1.0"),
                    model_data.get("training_data_hash"),
                    model_data.get("training_samples"),
                    model_data.get("cv_roc_auc"),
                    model_data.get("train_roc_auc"),
                    json.dumps(model_data.get("feature_names", [])),
                    json.dumps(model_data.get("model_params", {})),
                    now,
                ),
            )
            conn.commit()
            return model_id
        finally:
            conn.close()


# Query operations
def get_admet_prediction_run(run_id: str) -> dict[str, Any] | None:
    """Get ADMET prediction run by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            row = conn.execute(
                "SELECT * FROM admet_prediction_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            
            data = dict(row)
            data["molecular_properties"] = json.loads(data["molecular_properties_json"])
            if data["drug_likeness_json"]:
                data["drug_likeness"] = json.loads(data["drug_likeness_json"])
            return data
        finally:
            conn.close()


def get_admet_predictions(run_id: str) -> list[dict[str, Any]]:
    """Get all predictions for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            rows = conn.execute(
                "SELECT * FROM admet_predictions WHERE run_id=? ORDER BY category, endpoint",
                (run_id,),
            ).fetchall()
            
            results = []
            for row in rows:
                data = dict(row)
                if data["details_json"]:
                    data["details"] = json.loads(data["details_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def get_admet_score(run_id: str) -> dict[str, Any] | None:
    """Get ADMET score for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            row = conn.execute(
                "SELECT * FROM admet_scores WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            
            data = dict(row)
            data["category_scores"] = json.loads(data["category_scores_json"])
            if data["summary_json"]:
                data["summary"] = json.loads(data["summary_json"])
            return data
        finally:
            conn.close()


def get_compound_history(canonical_smiles: str) -> list[dict[str, Any]]:
    """Get prediction history for a compound."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT h.*, r.smiles, r.created_at as run_created_at
                FROM admet_prediction_history h
                JOIN admet_compounds c ON h.compound_id = c.compound_id
                JOIN admet_prediction_runs r ON h.run_id = r.run_id
                WHERE c.canonical_smiles = ?
                ORDER BY h.created_at DESC
                """,
                (canonical_smiles,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent prediction runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT run_id, smiles, canonical_smiles, created_at, model_version
                FROM admet_prediction_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_model_metadata(endpoint: str | None = None) -> list[dict[str, Any]]:
    """Get model metadata."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            if endpoint:
                rows = conn.execute(
                    "SELECT * FROM admet_models WHERE endpoint=?",
                    (endpoint,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM admet_models").fetchall()
            
            results = []
            for row in rows:
                data = dict(row)
                data["feature_names"] = json.loads(data["feature_names_json"])
                data["model_params"] = json.loads(data["model_params_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def search_admet_runs(
    smiles: str | None = None,
    inchikey: str | None = None,
    risk_classification: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search ADMET prediction runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            import json
            query = "SELECT * FROM admet_prediction_runs WHERE 1=1"
            params = []
            
            if smiles:
                query += " AND smiles LIKE ?"
                params.append(f"%{smiles}%")
            if inchikey:
                query += " AND inchikey = ?"
                params.append(inchikey)
            if risk_classification:
                query += " AND run_id IN (SELECT run_id FROM admet_scores WHERE risk_classification = ?)"
                params.append(risk_classification)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def clear_admet_prediction_run(run_id: str) -> bool:
    """Delete an ADMET prediction run and all associated data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM admet_prediction_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# Initialize on import
initialize_admet_database()