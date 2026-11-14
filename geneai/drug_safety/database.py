"""Database module for drug safety and toxicity prediction."""
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

DS_DB_PATH = DATABASE_PATH.parent / "geneai_drug_safety.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Analysis runs
CREATE TABLE IF NOT EXISTS ds_analysis_runs (
    run_id TEXT PRIMARY KEY,
    identifier TEXT NOT NULL,  -- SMILES, CID, or ChEMBL ID
    identifier_type TEXT NOT NULL,  -- smiles, cid, chembl_id
    molecular_properties_json TEXT,
    structural_alerts_json TEXT,
    risk_assessment_json TEXT,
    data_sources_json TEXT,
    created_at REAL NOT NULL,
    status TEXT DEFAULT 'completed'
);

-- PubChem toxicity data
CREATE TABLE IF NOT EXISTS ds_pubchem_toxicity (
    tox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    cid TEXT NOT NULL,
    assay_id TEXT,
    assay_name TEXT,
    target_name TEXT,
    organism TEXT,
    activity_outcome TEXT,
    activity_score REAL,
    concentration_unit TEXT,
    concentration_value REAL,
    FOREIGN KEY (run_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- ChEMBL toxicity data
CREATE TABLE IF NOT EXISTS ds_chembl_toxicity (
    tox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    chembl_id TEXT NOT NULL,
    assay_chembl_id TEXT,
    assay_description TEXT,
    target_chembl_id TEXT,
    target_name TEXT,
    organism TEXT,
    standard_type TEXT,
    standard_value REAL,
    standard_unit TEXT,
    standard_relation TEXT,
    data_validity_comment TEXT,
    document_chembl_id TEXT,
    FOREIGN KEY (run_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- ADMETlab predictions
CREATE TABLE IF NOT EXISTS ds_admetlab_predictions (
    pred_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    smiles TEXT NOT NULL,
    absorption_json TEXT,
    distribution_json TEXT,
    metabolism_json TEXT,
    excretion_json TEXT,
    toxicity_json TEXT,
    FOREIGN KEY (run_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- ML model predictions
CREATE TABLE IF NOT EXISTS ds_ml_predictions (
    pred_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    probability REAL NOT NULL,
    prediction TEXT NOT NULL,
    confidence TEXT NOT NULL,
    model_used TEXT,
    details_json TEXT,
    FOREIGN KEY (run_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- Drug interactions
CREATE TABLE IF NOT EXISTS ds_drug_interactions (
    interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    drug_a TEXT NOT NULL,
    drug_b TEXT NOT NULL,
    interaction_type TEXT,
    severity TEXT,
    description TEXT,
    evidence_level TEXT,
    source TEXT,
    FOREIGN KEY (run_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- Model metadata
CREATE TABLE IF NOT EXISTS ds_models (
    model_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    model_type TEXT NOT NULL,
    cv_auc REAL,
    cv_auc_std REAL,
    train_auc REAL,
    feature_names_json TEXT,
    params_json TEXT,
    training_samples INTEGER,
    training_date TEXT,
    version TEXT,
    FOREIGN KEY (model_id) REFERENCES ds_analysis_runs(run_id) ON DELETE CASCADE
);

-- Database version
CREATE TABLE IF NOT EXISTS ds_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ds_runs_created ON ds_analysis_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_ds_runs_identifier ON ds_analysis_runs(identifier);
CREATE INDEX IF NOT EXISTS idx_ds_pubchem_run ON ds_pubchem_toxicity(run_id);
CREATE INDEX IF NOT EXISTS idx_ds_chembl_run ON ds_chembl_toxicity(run_id);
CREATE INDEX IF NOT EXISTS idx_ds_admetlab_run ON ds_admetlab_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_ds_ml_run ON ds_ml_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_ds_ml_endpoint ON ds_ml_predictions(endpoint);
CREATE INDEX IF NOT EXISTS idx_ds_interactions_run ON ds_drug_interactions(run_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DS_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_ds_database() -> None:
    """Create all DS tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO ds_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("Drug Safety database initialized at %s", DS_DB_PATH)
        finally:
            conn.close()


def get_ds_db_version() -> int:
    """Get current DS database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM ds_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# Analysis run operations
def store_ds_analysis_run(
    run_id: str,
    identifier: str,
    identifier_type: str,
    molecular_properties: dict[str, Any],
    structural_alerts: dict[str, float],
    risk_assessment: dict[str, Any],
    data_sources: list[str],
) -> str:
    """Store a drug safety analysis run."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ds_analysis_runs (
                    run_id, identifier, identifier_type,
                    molecular_properties_json, structural_alerts_json,
                    risk_assessment_json, data_sources_json,
                    created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    molecular_properties_json=excluded.molecular_properties_json,
                    structural_alerts_json=excluded.structural_alerts_json,
                    risk_assessment_json=excluded.risk_assessment_json,
                    data_sources_json=excluded.data_sources_json,
                    status=excluded.status
                """,
                (
                    run_id,
                    identifier,
                    identifier_type,
                    json.dumps(molecular_properties),
                    json.dumps(structural_alerts),
                    json.dumps(risk_assessment),
                    json.dumps(data_sources),
                    now,
                    "completed",
                ),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()


def store_ds_pubchem_toxicity(run_id: str, toxicity_data: list[dict[str, Any]]) -> None:
    """Store PubChem toxicity data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for tox in toxicity_data:
                conn.execute(
                    """
                    INSERT INTO ds_pubchem_toxicity (
                        run_id, cid, assay_id, assay_name, target_name,
                        organism, activity_outcome, activity_score,
                        concentration_unit, concentration_value
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        tox.get("cid", ""),
                        tox.get("assay_id", ""),
                        tox.get("assay_name", ""),
                        tox.get("target_name", ""),
                        tox.get("organism", ""),
                        tox.get("activity_outcome", ""),
                        tox.get("activity_score", 0.0),
                        tox.get("concentration_unit", ""),
                        tox.get("concentration_value", 0.0),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_ds_chembl_toxicity(run_id: str, toxicity_data: list[dict[str, Any]]) -> None:
    """Store ChEMBL toxicity data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for tox in toxicity_data:
                conn.execute(
                    """
                    INSERT INTO ds_chembl_toxicity (
                        run_id, chembl_id, assay_chembl_id, assay_description,
                        target_chembl_id, target_name, organism,
                        standard_type, standard_value, standard_unit,
                        standard_relation, data_validity_comment,
                        document_chembl_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        tox.get("chembl_id", ""),
                        tox.get("assay_chembl_id", ""),
                        tox.get("assay_description", ""),
                        tox.get("target_chembl_id", ""),
                        tox.get("target_name", ""),
                        tox.get("organism", ""),
                        tox.get("standard_type", ""),
                        tox.get("standard_value", 0.0),
                        tox.get("standard_unit", ""),
                        tox.get("standard_relation", ""),
                        tox.get("data_validity_comment", ""),
                        tox.get("document_chembl_id", ""),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_ds_admetlab_prediction(run_id: str, prediction: dict[str, Any]) -> None:
    """Store ADMETlab prediction."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ds_admetlab_predictions (
                    run_id, smiles, absorption_json, distribution_json,
                    metabolism_json, excretion_json, toxicity_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    prediction.get("smiles", ""),
                    json.dumps(prediction.get("absorption", {})),
                    json.dumps(prediction.get("distribution", {})),
                    json.dumps(prediction.get("metabolism", {})),
                    json.dumps(prediction.get("excretion", {})),
                    json.dumps(prediction.get("toxicity", {})),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def store_ds_ml_predictions(run_id: str, predictions: list[dict[str, Any]]) -> None:
    """Store ML model predictions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for pred in predictions:
                conn.execute(
                    """
                    INSERT INTO ds_ml_predictions (
                        run_id, endpoint, probability, prediction,
                        confidence, model_used, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        pred.get("endpoint", ""),
                        pred.get("probability", 0.5),
                        pred.get("prediction", "Unknown"),
                        pred.get("confidence", "low"),
                        pred.get("model_used", ""),
                        json.dumps(pred.get("details", {})),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_ds_drug_interactions(run_id: str, interactions: list[dict[str, Any]]) -> None:
    """Store drug-drug interactions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for inter in interactions:
                conn.execute(
                    """
                    INSERT INTO ds_drug_interactions (
                        run_id, drug_a, drug_b, interaction_type,
                        severity, description, evidence_level, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        inter.get("drug_a", ""),
                        inter.get("drug_b", ""),
                        inter.get("interaction_type", ""),
                        inter.get("severity", ""),
                        inter.get("description", ""),
                        inter.get("evidence_level", ""),
                        inter.get("source", ""),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_ds_model_metadata(run_id: str, models: dict[str, Any]) -> None:
    """Store trained model metadata."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for endpoint, model_info in models.items():
                model_id = f"{run_id}_{endpoint}"
                conn.execute(
                    """
                    INSERT INTO ds_models (
                        model_id, endpoint, model_type, cv_auc, cv_auc_std,
                        train_auc, feature_names_json, params_json,
                        training_samples, training_date, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_id) DO UPDATE SET
                        cv_auc=excluded.cv_auc,
                        cv_auc_std=excluded.cv_auc_std,
                        train_auc=excluded.train_auc
                    """,
                    (
                        model_id,
                        endpoint,
                        model_info.get("model_type", ""),
                        model_info.get("cv_auc", 0.0),
                        model_info.get("cv_auc_std", 0.0),
                        model_info.get("train_auc", 0.0),
                        json.dumps(model_info.get("feature_names", [])),
                        json.dumps(model_info.get("params", {})),
                        model_info.get("training_samples", 0),
                        model_info.get("training_date", ""),
                        model_info.get("version", "1.0"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


# Query operations
def get_ds_analysis_run(run_id: str) -> dict[str, Any] | None:
    """Get DS analysis run by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM ds_analysis_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["molecular_properties", "structural_alerts", "risk_assessment", "data_sources"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_ds_pubchem_toxicity(run_id: str) -> list[dict[str, Any]]:
    """Get PubChem toxicity for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM ds_pubchem_toxicity WHERE run_id=?",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_ds_chembl_toxicity(run_id: str) -> list[dict[str, Any]]:
    """Get ChEMBL toxicity for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM ds_chembl_toxicity WHERE run_id=?",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_ds_admetlab_prediction(run_id: str) -> dict[str, Any] | None:
    """Get ADMETlab prediction for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM ds_admetlab_predictions WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["absorption", "distribution", "metabolism", "excretion", "toxicity"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_ds_ml_predictions(run_id: str) -> list[dict[str, Any]]:
    """Get ML predictions for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM ds_ml_predictions WHERE run_id=? ORDER BY endpoint",
                (run_id,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("details_json"):
                    data["details"] = json.loads(data["details_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def get_ds_drug_interactions(run_id: str) -> list[dict[str, Any]]:
    """Get drug interactions for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM ds_drug_interactions WHERE run_id=?",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_ds_models() -> list[dict[str, Any]]:
    """Get all stored model metadata."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute("SELECT * FROM ds_models").fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("feature_names_json"):
                    data["feature_names"] = json.loads(data["feature_names_json"])
                if data.get("params_json"):
                    data["params"] = json.loads(data["params_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def get_recent_ds_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent DS analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT run_id, identifier, identifier_type, created_at, risk_assessment_json
                FROM ds_analysis_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("risk_assessment_json"):
                    data["risk_assessment"] = json.loads(data["risk_assessment_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def search_ds_runs(
    identifier: str | None = None,
    risk_level: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search DS analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM ds_analysis_runs WHERE 1=1"
            params = []
            
            if identifier:
                query += " AND identifier LIKE ?"
                params.append(f"%{identifier}%")
            if risk_level:
                query += " AND risk_assessment_json LIKE ?"
                params.append(f'%"{risk_level}"%')
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("risk_assessment_json"):
                    data["risk_assessment"] = json.loads(data["risk_assessment_json"])
                if data.get("molecular_properties_json"):
                    data["molecular_properties"] = json.loads(data["molecular_properties_json"])
                if data.get("structural_alerts_json"):
                    data["structural_alerts"] = json.loads(data["structural_alerts_json"])
                if data.get("data_sources_json"):
                    data["data_sources"] = json.loads(data["data_sources_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def clear_ds_analysis_run(run_id: str) -> bool:
    """Delete a DS analysis run and all associated data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM ds_analysis_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# Initialize on import
initialize_ds_database()