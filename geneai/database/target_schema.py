"""Additive SQLite schema and persistence for Phase 4.3 target assessments."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)
DB_PATH = DATABASE_PATH
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS target_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS target_assessment_runs (
    analysis_id TEXT PRIMARY KEY,
    disease_source_id TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    disease_analysis_id TEXT NOT NULL DEFAULT '',
    disease_snapshot_retrieved_at TEXT NOT NULL DEFAULT '',
    weights_json TEXT NOT NULL,
    source_versions_json TEXT NOT NULL,
    network_summary_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS target_gene_rankings (
    target_ranking_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES target_assessment_runs(analysis_id) ON DELETE CASCADE,
    gene_symbol TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    priority_index REAL,
    priority_tier TEXT NOT NULL DEFAULT '',
    evidence_components_json TEXT NOT NULL,
    missing_evidence_json TEXT NOT NULL,
    protein_metadata_json TEXT NOT NULL,
    source_references_json TEXT NOT NULL,
    UNIQUE(analysis_id, gene_symbol)
);
CREATE TABLE IF NOT EXISTS target_ppi_edges (
    ppi_edge_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES target_assessment_runs(analysis_id) ON DELETE CASCADE,
    protein_a TEXT NOT NULL,
    protein_b TEXT NOT NULL,
    network_type TEXT NOT NULL,
    combined_score REAL NOT NULL,
    experimental_channel_score REAL,
    evidence_channels_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    UNIQUE(analysis_id, protein_a, protein_b, network_type)
);
CREATE TABLE IF NOT EXISTS target_ml_runs (
    model_run_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES target_assessment_runs(analysis_id) ON DELETE CASCADE,
    model_type TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_source TEXT NOT NULL,
    dataset_license TEXT NOT NULL,
    label_definition TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    gene_group_count INTEGER NOT NULL,
    feature_columns_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    feature_importance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_target_rankings_symbol ON target_gene_rankings(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_target_ppi_edges_symbols ON target_ppi_edges(protein_a, protein_b);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        logger.exception("SQLite target-assessment operation failed")
        raise
    finally:
        connection.close()


def initialize_target_schema() -> None:
    """Create target tables additively in the existing GeneAI SQLite database."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO target_schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in result.items() if not key.startswith("_") and key != "target_feature_rows"}
    clean["proteins"] = [
        {key: value for key, value in protein.items() if key != "sequence"}
        for protein in result.get("proteins", []) if isinstance(protein, dict)
    ]
    clean["targets"] = []
    for target in result.get("targets", []):
        if not isinstance(target, dict):
            continue
        item = dict(target)
        if isinstance(item.get("protein"), dict):
            item["protein"] = {key: value for key, value in item["protein"].items() if key != "sequence"}
        item.pop("go_annotations", None)
        item.pop("disease_pathway_context", None)
        clean["targets"].append(item)
    return clean


def store_target_assessment(result: dict[str, Any]) -> str:
    """Persist a target snapshot without duplicating protein sequences."""
    analysis_id = result.get("analysis_id")
    disease = result.get("disease") or {}
    disease_id = disease.get("disease_id") or disease.get("id")
    disease_name = disease.get("name")
    if not isinstance(analysis_id, str) or not analysis_id or not isinstance(disease_id, str) or not isinstance(disease_name, str):
        raise ValueError("Target result is missing its analysis ID or disease identifier.")
    now = result.get("retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO target_schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )
        connection.execute(
            """INSERT INTO target_assessment_runs
               (analysis_id, disease_source_id, disease_name, disease_analysis_id,
                disease_snapshot_retrieved_at, weights_json, source_versions_json,
                network_summary_json, result_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id, disease_id, disease_name,
                str(result.get("disease_analysis_id") or ""),
                str(result.get("disease_analysis_retrieved_at") or ""),
                _json(result.get("weights", {})), _json(result.get("source_versions", {})),
                _json({key: value for key, value in (result.get("ppi_network") or {}).items() if key != "edges"}),
                _json(_safe_result(result)), now,
            ),
        )
        for target in result.get("targets", []):
            if not isinstance(target, dict):
                continue
            protein = target.get("protein") if isinstance(target.get("protein"), dict) else {}
            connection.execute(
                """INSERT INTO target_gene_rankings
                   (analysis_id, gene_symbol, target_rank, priority_index, priority_tier,
                    evidence_components_json, missing_evidence_json, protein_metadata_json, source_references_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, str(target.get("gene_symbol") or ""), int(target.get("target_research_rank") or 0),
                    target.get("target_research_priority_index"), str(target.get("target_research_priority_tier") or ""),
                    _json(target.get("target_priority_components", {})),
                    _json(target.get("target_missing_evidence_domains", [])),
                    _json({key: value for key, value in protein.items() if key != "sequence"}),
                    _json(target.get("gene_source_references", [])),
                ),
            )
        for edge in (result.get("ppi_network") or {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            connection.execute(
                """INSERT INTO target_ppi_edges
                   (analysis_id, protein_a, protein_b, network_type, combined_score,
                    experimental_channel_score, evidence_channels_json, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, str(edge.get("protein_a") or ""), str(edge.get("protein_b") or ""),
                    str(edge.get("network_type") or "functional"), float(edge.get("combined_score") or 0),
                    edge.get("experimental_channel_score"), _json(edge.get("evidence_channel_scores", {})),
                    str(edge.get("source_url") or "https://string-db.org/"),
                ),
            )
    return analysis_id


def store_target_ml_run(analysis_id: str, model_bundle: dict[str, Any]) -> str:
    """Persist model evaluation and dataset provenance, never the fitted estimator."""
    if not isinstance(analysis_id, str) or not analysis_id:
        raise ValueError("A target assessment ID is required to store ML evaluation.")
    run_id = str(model_bundle.get("model_run_id") or f"{analysis_id}:ml:{uuid4()}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            """INSERT INTO target_ml_runs
               (model_run_id, analysis_id, model_type, model_version, dataset_source, dataset_license,
                label_definition, row_count, gene_group_count, feature_columns_json, metrics_json,
                feature_importance_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, analysis_id, str(model_bundle.get("model_type") or ""),
                str(model_bundle.get("model_version") or ""), str(model_bundle.get("dataset_source") or ""),
                str(model_bundle.get("dataset_license") or ""), str(model_bundle.get("label_definition") or ""),
                int(model_bundle.get("row_count") or 0), int(model_bundle.get("gene_group_count") or 0),
                _json(model_bundle.get("feature_columns", [])), _json(model_bundle.get("evaluation_metrics", {})),
                _json(model_bundle.get("feature_importance", [])), now,
            ),
        )
    return run_id
