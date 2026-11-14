"""Database for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

ARI_DB_PATH = DATABASE_PATH.parent / "geneai_ai_research_intelligence.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Mutation-to-Drug workflow runs
CREATE TABLE IF NOT EXISTS ari_mtd_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    input_json TEXT NOT NULL,
    variants_json TEXT,
    gene_disease_links_json TEXT,
    prioritized_targets_json TEXT,
    candidates_json TEXT,
    top_candidates_json TEXT,
    kg_subgraph_json TEXT,
    summary_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT DEFAULT 'completed'
);

-- AI Candidate Ranking runs
CREATE TABLE IF NOT EXISTS ari_ranking_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    model_type TEXT,
    candidates_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- Research Assistant sessions
CREATE TABLE IF NOT EXISTS ari_research_sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    context_json TEXT,
    questions_json TEXT,
    answers_json TEXT
);

-- Reports generated
CREATE TABLE IF NOT EXISTS ari_reports (
    report_id TEXT PRIMARY KEY,
    run_id TEXT,
    report_type TEXT,  -- pdf, html, markdown, comparative
    title TEXT,
    content_hash TEXT,
    file_path TEXT,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS ari_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ari_mtd_created ON ari_mtd_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_ari_ranking_created ON ari_ranking_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_ari_session_updated ON ari_research_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_ari_reports_created ON ari_reports(created_at);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(ARI_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_ari_database() -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO ari_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("AI Research Intelligence database initialized at %s", ARI_DB_PATH)
        finally:
            conn.close()


def get_ari_db_version() -> int:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM ari_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# Mutation-to-Drug runs
def store_mtd_run(
    run_id: str,
    timestamp: str,
    input_data: dict[str, Any],
    variants: list[dict] | None,
    gene_disease_links: list[dict] | None,
    prioritized_targets: list[str] | None,
    candidates: list[dict] | None,
    top_candidates: list[dict] | None,
    kg_subgraph: dict | None,
    summary: dict[str, Any],
) -> str:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ari_mtd_runs (
                    run_id, timestamp, input_json, variants_json,
                    gene_disease_links_json, prioritized_targets_json,
                    candidates_json, top_candidates_json, kg_subgraph_json,
                    summary_json, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    top_candidates_json=excluded.top_candidates_json,
                    summary_json=excluded.summary_json,
                    status=excluded.status
                """,
                (
                    run_id, timestamp,
                    json.dumps(input_data),
                    json.dumps(variants) if variants else None,
                    json.dumps(gene_disease_links) if gene_disease_links else None,
                    json.dumps(prioritized_targets) if prioritized_targets else None,
                    json.dumps(candidates) if candidates else None,
                    json.dumps(top_candidates) if top_candidates else None,
                    json.dumps(kg_subgraph) if kg_subgraph else None,
                    json.dumps(summary),
                    time.time(), "completed",
                ),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()


def get_mtd_run(run_id: str) -> dict[str, Any] | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM ari_mtd_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["input", "variants", "gene_disease_links", "prioritized_targets",
                       "candidates", "top_candidates", "kg_subgraph", "summary"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_recent_mtd_runs(limit: int = 50) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT run_id, timestamp, summary_json, created_at FROM ari_mtd_runs ORDER BY created_at DESC LIMIT ?",
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


# AI Ranking runs
def store_ranking_run(
    run_id: str,
    timestamp: str,
    model_type: str,
    candidates: list[dict],
    results: list[dict],
) -> str:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ari_ranking_runs (
                    run_id, timestamp, model_type, candidates_json, results_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    results_json=excluded.results_json
                """,
                (
                    run_id, timestamp, model_type,
                    json.dumps(candidates), json.dumps(results), time.time(),
                ),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()


def get_ranking_run(run_id: str) -> dict[str, Any] | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM ari_ranking_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["candidates", "results"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


def get_recent_ranking_runs(limit: int = 50) -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT run_id, timestamp, model_type, created_at FROM ari_ranking_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Research Assistant sessions
def store_research_session(session_id: str, context: dict, questions: list, answers: list) -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ari_research_sessions (
                    session_id, created_at, updated_at, context_json, questions_json, answers_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    context_json=excluded.context_json,
                    questions_json=excluded.questions_json,
                    answers_json=excluded.answers_json
                """,
                (
                    session_id, time.time(), time.time(),
                    json.dumps(context), json.dumps(questions), json.dumps(answers),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_research_session(session_id: str) -> dict | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM ari_research_sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for key in ["context", "questions", "answers"]:
                json_key = f"{key}_json"
                if data.get(json_key):
                    data[key] = json.loads(data[json_key])
            return data
        finally:
            conn.close()


# Reports
def store_report(report_id: str, run_id: str, report_type: str, title: str, 
                 content_hash: str, file_path: str) -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO ari_reports (report_id, run_id, report_type, title, content_hash, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, run_id, report_type, title, content_hash, file_path, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def get_reports_for_run(run_id: str) -> list[dict]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute("SELECT * FROM ari_reports WHERE run_id=? ORDER BY created_at DESC", (run_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Search
def search_mtd_runs(
    gene_symbol: str | None = None,
    drug_name: str | None = None,
    disease_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM ari_mtd_runs WHERE 1=1"
            params = []
            
            if gene_symbol:
                query += " AND (input_json LIKE ? OR variants_json LIKE ? OR gene_disease_links_json LIKE ?)"
                params.extend([f'%"{gene_symbol}"%'] * 3)
            if drug_name:
                query += " AND (candidates_json LIKE ? OR top_candidates_json LIKE ?)"
                params.extend([f'%"{drug_name}"%'] * 2)
            if disease_name:
                query += " AND (input_json LIKE ? OR gene_disease_links_json LIKE ?)"
                params.extend([f'%"{disease_name}"%'] * 2)
            
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


def clear_mtd_run(run_id: str) -> bool:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM ari_mtd_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


initialize_ari_database()