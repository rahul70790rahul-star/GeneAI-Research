"""Database module for disease-gene-pathway analysis results."""
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

DGP_DB_PATH = DATABASE_PATH.parent / "geneai_disease_gene_pathway.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Analysis runs
CREATE TABLE IF NOT EXISTS dgp_analysis_runs (
    run_id TEXT PRIMARY KEY,
    input_genes_json TEXT NOT NULL,
    input_diseases_json TEXT,
    parameters_json TEXT,
    summary_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT DEFAULT 'completed'
);

-- Gene network nodes
CREATE TABLE IF NOT EXISTS dgp_network_nodes (
    node_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    gene_id TEXT,
    uniprot_id TEXT,
    degree INTEGER DEFAULT 0,
    betweenness_centrality REAL DEFAULT 0.0,
    clustering_coefficient REAL DEFAULT 0.0,
    is_hub INTEGER DEFAULT 0,
    is_input INTEGER DEFAULT 0,
    uniprot_data_json TEXT,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- Gene network edges
CREATE TABLE IF NOT EXISTS dgp_network_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_gene TEXT NOT NULL,
    target_gene TEXT NOT NULL,
    weight REAL NOT NULL,
    combined_score REAL DEFAULT 0.0,
    evidence_types_json TEXT,
    interaction_scores_json TEXT,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- Disease-gene associations
CREATE TABLE IF NOT EXISTS dgp_disease_associations (
    assoc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    disease_id TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    gene_id TEXT,
    score REAL NOT NULL,
    datasources_json TEXT,
    evidence_count INTEGER DEFAULT 0,
    source TEXT DEFAULT 'OpenTargets',
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- DisGeNET associations
CREATE TABLE IF NOT EXISTS dgp_disgenet_associations (
    assoc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    disease_id TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    disease_type TEXT,
    gene_symbol TEXT NOT NULL,
    gene_id TEXT,
    score REAL NOT NULL,
    ei REAL DEFAULT 0.0,
    year_initial INTEGER,
    year_final INTEGER,
    n_pmids INTEGER DEFAULT 0,
    snps_json TEXT,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- KEGG pathways
CREATE TABLE IF NOT EXISTS dgp_kegg_pathways (
    pathway_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    kegg_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    genes_json TEXT NOT NULL,
    gene_names_json TEXT,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- Reactome pathways
CREATE TABLE IF NOT EXISTS dgp_reactome_pathways (
    pathway_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    reactome_id TEXT NOT NULL,
    name TEXT NOT NULL,
    species TEXT,
    genes_json TEXT NOT NULL,
    gene_names_json TEXT,
    p_value REAL,
    fdr REAL,
    entities_found INTEGER,
    entities_total INTEGER,
    entities_ratio REAL,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- GO enrichment
CREATE TABLE IF NOT EXISTS dgp_go_enrichment (
    enrich_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    go_id TEXT NOT NULL,
    go_name TEXT NOT NULL,
    aspect TEXT NOT NULL,
    gene_count INTEGER NOT NULL,
    genes_json TEXT NOT NULL,
    p_value REAL,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- STRING enrichment
CREATE TABLE IF NOT EXISTS dgp_string_enrichment (
    enrich_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    term TEXT NOT NULL,
    description TEXT,
    p_value REAL NOT NULL,
    fdr REAL NOT NULL,
    input_genes INTEGER NOT NULL,
    background_genes INTEGER NOT NULL,
    preferred_names_json TEXT,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- Therapeutic targets
CREATE TABLE IF NOT EXISTS dgp_therapeutic_targets (
    target_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gene_symbol TEXT NOT NULL,
    uniprot_id TEXT,
    score REAL NOT NULL,
    reasons_json TEXT NOT NULL,
    degree INTEGER,
    betweenness REAL,
    disease_count INTEGER,
    pathway_count INTEGER,
    is_hub INTEGER DEFAULT 0,
    rank INTEGER,
    FOREIGN KEY (run_id) REFERENCES dgp_analysis_runs(run_id) ON DELETE CASCADE
);

-- Database version
CREATE TABLE IF NOT EXISTS dgp_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dgp_runs_created ON dgp_analysis_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_dgp_nodes_run ON dgp_network_nodes(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_nodes_gene ON dgp_network_nodes(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_dgp_edges_run ON dgp_network_edges(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_disease_assoc_run ON dgp_disease_associations(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_disease_assoc_gene ON dgp_disease_associations(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_dgp_disgenet_run ON dgp_disgenet_associations(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_kegg_run ON dgp_kegg_pathways(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_reactome_run ON dgp_reactome_pathways(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_go_run ON dgp_go_enrichment(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_string_run ON dgp_string_enrichment(run_id);
CREATE INDEX IF NOT EXISTS idx_dgp_targets_run ON dgp_therapeutic_targets(run_id);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DGP_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_dgp_database() -> None:
    """Create all DGP tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO dgp_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("DGP database initialized at %s", DGP_DB_PATH)
        finally:
            conn.close()


def get_dgp_db_version() -> int:
    """Get current DGP database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM dgp_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# Analysis run operations
def store_dgp_analysis_run(
    run_id: str,
    input_genes: list[str],
    input_diseases: list[str] | None,
    parameters: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    """Store a DGP analysis run."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO dgp_analysis_runs (
                    run_id, input_genes_json, input_diseases_json, parameters_json,
                    summary_json, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    summary_json=excluded.summary_json,
                    status=excluded.status
                """,
                (
                    run_id,
                    json.dumps(input_genes),
                    json.dumps(input_diseases) if input_diseases else None,
                    json.dumps(parameters),
                    json.dumps(summary),
                    now,
                    "completed",
                ),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()


def store_dgp_network(run_id: str, network_data: dict[str, Any]) -> None:
    """Store gene network nodes and edges."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            # Store nodes
            for node in network_data.get("nodes", []):
                conn.execute(
                    """
                    INSERT INTO dgp_network_nodes (
                        run_id, gene_symbol, gene_id, uniprot_id, degree,
                        betweenness_centrality, clustering_coefficient, is_hub,
                        is_input, uniprot_data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        node.get("gene_symbol"),
                        node.get("gene_id"),
                        node.get("uniprot_id"),
                        node.get("degree", 0),
                        node.get("betweenness_centrality", 0.0),
                        node.get("clustering_coefficient", 0.0),
                        1 if node.get("is_hub") else 0,
                        1 if node.get("is_input") else 0,
                        json.dumps(node.get("uniprot_data")) if node.get("uniprot_data") else None,
                    ),
                )
            
            # Store edges
            for edge in network_data.get("edges", []):
                conn.execute(
                    """
                    INSERT INTO dgp_network_edges (
                        run_id, source_gene, target_gene, weight, combined_score,
                        evidence_types_json, interaction_scores_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        edge.get("source"),
                        edge.get("target"),
                        edge.get("weight", 0.0),
                        edge.get("combined_score", 0.0),
                        json.dumps(edge.get("evidence_types", [])),
                        json.dumps({
                            "experimental": edge.get("experimental_score", 0.0),
                            "database": edge.get("database_score", 0.0),
                            "textmining": edge.get("textmining_score", 0.0),
                            "cooccurrence": edge.get("cooccurrence_score", 0.0),
                            "coexpression": edge.get("coexpression_score", 0.0),
                            "neighborhood": edge.get("neighborhood_score", 0.0),
                            "fusion": edge.get("fusion_score", 0.0),
                        }),
                    ),
                )
            
            conn.commit()
        finally:
            conn.close()


def store_dgp_disease_associations(run_id: str, associations: list[dict[str, Any]]) -> None:
    """Store disease-gene associations."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for assoc in associations:
                conn.execute(
                    """
                    INSERT INTO dgp_disease_associations (
                        run_id, disease_id, disease_name, gene_symbol, gene_id,
                        score, datasources_json, evidence_count, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        assoc.get("disease_id"),
                        assoc.get("disease_name"),
                        assoc.get("gene_symbol"),
                        assoc.get("gene_id"),
                        assoc.get("score", 0.0),
                        json.dumps(assoc.get("datasources", [])),
                        assoc.get("evidence_count", 0),
                        assoc.get("source", "OpenTargets"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_dgp_disgenet_associations(run_id: str, associations: list[dict[str, Any]]) -> None:
    """Store DisGeNET associations."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for assoc in associations:
                conn.execute(
                    """
                    INSERT INTO dgp_disgenet_associations (
                        run_id, disease_id, disease_name, disease_type, gene_symbol,
                        gene_id, score, ei, year_initial, year_final, n_pmids, snps_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        assoc.get("disease_id"),
                        assoc.get("disease_name"),
                        assoc.get("disease_type"),
                        assoc.get("gene_symbol"),
                        assoc.get("gene_id"),
                        assoc.get("score", 0.0),
                        assoc.get("ei", 0.0),
                        assoc.get("year_initial"),
                        assoc.get("year_final"),
                        assoc.get("n_pmids", 0),
                        json.dumps(assoc.get("snps", [])),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_dgp_kegg_pathways(run_id: str, pathways: list[dict[str, Any]]) -> None:
    """Store KEGG pathways."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for pw in pathways:
                conn.execute(
                    """
                    INSERT INTO dgp_kegg_pathways (
                        run_id, kegg_id, name, description, category,
                        genes_json, gene_names_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        pw.get("pathway_id"),
                        pw.get("name"),
                        pw.get("description"),
                        pw.get("category"),
                        json.dumps(pw.get("genes", [])),
                        json.dumps(pw.get("gene_names", {})),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_dgp_reactome_pathways(run_id: str, pathways: list[dict[str, Any]]) -> None:
    """Store Reactome pathways."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for pw in pathways:
                conn.execute(
                    """
                    INSERT INTO dgp_reactome_pathways (
                        run_id, reactome_id, name, species, genes_json,
                        gene_names_json, p_value, fdr, entities_found,
                        entities_total, entities_ratio
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        pw.get("pathway_id"),
                        pw.get("name"),
                        pw.get("species"),
                        json.dumps(pw.get("genes", [])),
                        json.dumps(pw.get("gene_names", {})),
                        pw.get("p_value"),
                        pw.get("fdr"),
                        pw.get("entities_found"),
                        pw.get("entities_total"),
                        pw.get("entities_ratio"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_dgp_go_enrichment(run_id: str, enrichment: dict[str, list[dict[str, Any]]]) -> None:
    """Store GO enrichment results."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for aspect, terms in enrichment.items():
                for term in terms:
                    conn.execute(
                        """
                        INSERT INTO dgp_go_enrichment (
                            run_id, go_id, go_name, aspect, gene_count,
                            genes_json, p_value
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            term.get("go_id"),
                            term.get("go_name"),
                            aspect,
                            term.get("gene_count", 0),
                            json.dumps(term.get("genes", [])),
                            term.get("p_value"),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()


def store_dgp_string_enrichment(run_id: str, enrichment: list[dict[str, Any]]) -> None:
    """Store STRING enrichment results."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for term in enrichment:
                conn.execute(
                    """
                    INSERT INTO dgp_string_enrichment (
                        run_id, category, term, description, p_value, fdr,
                        input_genes, background_genes, preferred_names_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        term.get("category"),
                        term.get("term"),
                        term.get("description"),
                        term.get("p_value", 1.0),
                        term.get("fdr", 1.0),
                        term.get("input_genes", 0),
                        term.get("background_genes", 0),
                        json.dumps(term.get("preferred_names", [])),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def store_dgp_therapeutic_targets(run_id: str, targets: list[dict[str, Any]]) -> None:
    """Store therapeutic target predictions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for i, target in enumerate(targets):
                conn.execute(
                    """
                    INSERT INTO dgp_therapeutic_targets (
                        run_id, gene_symbol, uniprot_id, score, reasons_json,
                        degree, betweenness, disease_count, pathway_count,
                        is_hub, rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        target.get("gene_symbol"),
                        target.get("uniprot_id"),
                        target.get("score", 0.0),
                        json.dumps(target.get("reasons", [])),
                        target.get("degree"),
                        target.get("betweenness"),
                        target.get("disease_count"),
                        target.get("pathway_count"),
                        1 if target.get("is_hub") else 0,
                        i + 1,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


# Query operations
def get_dgp_analysis_run(run_id: str) -> dict[str, Any] | None:
    """Get DGP analysis run by ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM dgp_analysis_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["input_genes"] = json.loads(data["input_genes_json"])
            data["input_diseases"] = json.loads(data["input_diseases_json"]) if data["input_diseases_json"] else []
            data["parameters"] = json.loads(data["parameters_json"])
            data["summary"] = json.loads(data["summary_json"])
            return data
        finally:
            conn.close()


def get_dgp_network(run_id: str) -> dict[str, Any]:
    """Get network data for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            nodes = conn.execute(
                "SELECT * FROM dgp_network_nodes WHERE run_id=?",
                (run_id,),
            ).fetchall()
            
            edges = conn.execute(
                "SELECT * FROM dgp_network_edges WHERE run_id=?",
                (run_id,),
            ).fetchall()
            
            return {
                "nodes": [dict(n) for n in nodes],
                "edges": [dict(e) for e in edges],
            }
        finally:
            conn.close()


def get_dgp_therapeutic_targets(run_id: str) -> list[dict[str, Any]]:
    """Get therapeutic targets for a run."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM dgp_therapeutic_targets WHERE run_id=? ORDER BY rank",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_recent_dgp_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent DGP analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT run_id, input_genes_json, input_diseases_json, created_at, summary_json
                FROM dgp_analysis_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["input_genes"] = json.loads(data["input_genes_json"])
                data["input_diseases"] = json.loads(data["input_diseases_json"]) if data["input_diseases_json"] else []
                data["summary"] = json.loads(data["summary_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def search_dgp_runs(
    gene_symbol: str | None = None,
    disease_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search DGP analysis runs."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM dgp_analysis_runs WHERE 1=1"
            params = []
            
            if gene_symbol:
                query += " AND input_genes_json LIKE ?"
                params.append(f'%"{gene_symbol}"%')
            if disease_name:
                query += " AND input_diseases_json LIKE ?"
                params.append(f'%"{disease_name}"%')
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["input_genes"] = json.loads(data["input_genes_json"])
                data["input_diseases"] = json.loads(data["input_diseases_json"]) if data["input_diseases_json"] else []
                data["summary"] = json.loads(data["summary_json"])
                results.append(data)
            return results
        finally:
            conn.close()


def clear_dgp_analysis_run(run_id: str) -> bool:
    """Delete a DGP analysis run and all associated data."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM dgp_analysis_runs WHERE run_id=?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# Initialize on import
initialize_dgp_database()