"""Database for Integrated Precision Drug Discovery."""
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

IPDD_DB_PATH = DATABASE_PATH.parent / "geneai_integrated_precision.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Integrated analysis runs
CREATE TABLE IF NOT EXISTS ipdd_analysis_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    input_json TEXT NOT NULL,
    mutation_analysis_json TEXT,
    disease_gene_analysis_json TEXT,
    target_identification_json TEXT,
    drug_discovery_json TEXT,
    safety_admet_json TEXT,
    literature_analysis_json TEXT,
    candidate_ranking_json TEXT,
    summary_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT DEFAULT 'completed'
);

-- Candidate rankings
CREATE TABLE IF NOT EXISTS ipdd_candidate_rankings (
    rank_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    drug_name TEXT,
    smiles TEXT,
    score REAL NOT NULL,
    reasons_json TEXT,
    admet_score REAL,
    safety_risk TEXT,
    binding_affinities_json TEXT,
    FOREIGN KEY (run_id) REFERENCES ipdd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Mutation analysis details
CREATE TABLE IF NOT EXISTS ipdd_mutations (
    mut_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    variant_id TEXT,
    chrom TEXT,
    pos INTEGER,
    ref TEXT,
    alt TEXT,
    gene TEXT,
    impact TEXT,
    consequence TEXT,
    interpretation TEXT,
    FOREIGN KEY (run_id) REFERENCES ipdd_analysis_runs(run_id) ON DELETE CASCADE
);

-- Database version
CREATE TABLE IF NOT EXISTS ipdd_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ipdd_runs_created ON ipdd_analysis_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_ipdd_rankings_run ON ipdd_candidate_rankings(run_id);
CREATE INDEX IF NOT EXISTS idx_ipdd_mutations_run ON ipdd_mutations(run_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(IPDD_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_ipdd_database() -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO ipdd_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("IPDD database initialized at %s", IPDD_DB_PATH)
        finally:
            conn.close()


def get_ipdd_db_version() -> int:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM ipdd_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


def store_ipdd_analysis_run(
    run_id: str,
    timestamp: str,
    input_data: dict[str, Any],
    mutation_analysis: dict[str, Any] | None,
    disease_gene_analysis: dict[str, Any] | None,
    target_identification: dict[str, Any] | None,
    drug_discovery: dict[str, Any] | None,
    safety_admet: dict[str, Any] | None,
    literature_analysis: dict[str, Any] | None,
    candidate_ranking: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ipdd_analysis_runs (
                    run_id, timestamp, input_json, mutation_analysis_json,
                    disease_gene_analysis_json, target_identification_json,
                    drug_discovery_json, safety_admet_json, literature_analysis_json,
                    candidate_ranking_json, summary_json, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    candidate_ranking_json=excluded.candidate_ranking_json,
                    summary_json=excluded.summary_json,
                    status=excluded.status
                """,
                (
                    run_id, timestamp,
                    json.dumps(input_data),
                    json.dumps(mutation_analysis) if mutation_analysis else None,
                    json.dumps(disease_gene_analysis) if disease_gene_analysis else None,
                    json.dumps(target_identification) if target_identification else None,
                    json.dumps(drug_discovery) if drug_discovery else None,
                    json.dumps(safety_admet) if safety_admet else None,
                    json.dumps(literature_analysis) if literature_analysis else None,
                    json.dumps(candidate_ranking),
                    json.dumps(summary),
                    now, "completed",
                ),
            )
            
            # Store candidate rankings
            for cand in candidate_ranking:
                conn.execute(
                    """
                    INSERT INTO ipdd_candidate_rankings (
                        run_id, rank, drug_name, smiles, score, reasons_json,
                        admet_score, safety_risk, binding_affinities_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        cand.get("rank", 0),
                        cand.get("drug", ""),
                        cand.get("smiles", ""),
                        cand.get("score", 0.0),
                        json.dumps(cand.get("reasons", [])),
                        cand.get("admet_score"),
                        cand.get("safety_risk"),
                        json.dumps(cand.get("binding_affinities", [])),
                    ),
                )
            
            # Store mutations
            if mutation_analysis and mutation_analysis.get("mutation_interpretations"):
                for mut in mutation_analysis["mutation_interpretations"]:
                    conn.execute(
                        """
                        INSERT INTO ipdd_mutations (
                            run_id, variant_id, chrom, pos, ref, alt, gene, impact, consequence, interpretation
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            mut.get("variant", ""),
                            "", "", 0, "", "",  # Would parse from variant string
                            mut.get("gene", ""),
                            mut.get("impact", ""),
                            mut.get("consequence", ""),
                            mut.get("interpretation", ""),
                        ),
                    )
            
            conn.commit()
            return run_id
        finally:
            conn.close()


def get_ipdd_analysis_run(run_id: str) -> dict[str, Any] | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM ipdd_analysis_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["input", "mutation_analysis", "disease_gene_analysis", "target_identification",
                       "drug_discovery", "safety_admet", "literature_analysis", "candidate_ranking", "summary"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_ipdd_candidate_rankings(run_id: str) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute("SELECT * FROM ipdd_candidate_rankings WHERE run_id=? ORDER BY rank", (run_id,)).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                for key in ["reasons", "binding_affinities"]:
                    json_key = f"{key}_json"
                    if data.get(json_key):
                        data[key] = json.loads(data[json_key])
                results.append(data)
            return results
        finally:
            conn.close()


def get_recent_ipdd_runs(limit: int = 50) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT run_id, timestamp, summary_json, created_at FROM ipdd_analysis_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("summary_json"):
                    data["summary"] = json.loads(data["summary_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def search_ipdd_runs(
    gene_symbol: str | None = None,
    drug_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM ipdd_analysis_runs WHERE 1=1"
            params = []
            
            if gene_symbol:
                query += " AND (input_json LIKE ? OR mutation_analysis_json LIKE ? OR disease_gene_analysis_json LIKE ?)"
                params.extend([f'%"{gene_symbol}"%'] * 3)
            if drug_name:
                query += " AND (input_json LIKE ? OR drug_discovery_json LIKE ?)"
                params.extend([f'%"{drug_name}"%'] * 2)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("summary_json"):
                    data["summary"] = json.loads(data["summary_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def clear_ipdd_analysis_run(run_id: str) -> bool:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM ipdd_analysis_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


initialize_ipdd_database()