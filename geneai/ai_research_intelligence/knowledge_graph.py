"""Biomedical Knowledge Graph for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

KG_DB_PATH = DATABASE_PATH.parent / "geneai_knowledge_graph.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Nodes: genes, proteins, diseases, drugs, pathways, variants, publications
CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,  -- gene, protein, disease, drug, pathway, variant, publication, target
    identifier TEXT NOT NULL,  -- e.g., ENSG00000141510, TP53, CHEMBL123, GO:0006915
    name TEXT,
    properties_json TEXT,  -- additional properties as JSON
    source TEXT,  -- data source: opentargets, string, kegg, reactome, pubmed, chembl, uniprot, clinvar, gnomad
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Edges: relationships between nodes
CREATE TABLE IF NOT EXISTS kg_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- associated_with, interacts_with, treats, causes, regulates, participates_in, binds_to, inhibits, activates
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 1.0,
    properties_json TEXT,  -- evidence, scores, etc.
    source TEXT,  -- data source
    created_at REAL NOT NULL,
    FOREIGN KEY (source_node_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE
);

-- Node indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_identifier ON kg_nodes(identifier);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_source ON kg_nodes(source);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_type ON kg_edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source_target ON kg_edges(source_node_id, target_node_id);

-- Graph analysis results
CREATE TABLE IF NOT EXISTS kg_analysis_results (
    analysis_id TEXT PRIMARY KEY,
    analysis_type TEXT NOT NULL,  -- shortest_path, centrality, community, enrichment, propagation
    parameters_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS kg_db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(KG_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_knowledge_graph() -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO kg_db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("Knowledge Graph database initialized at %s", KG_DB_PATH)
        finally:
            conn.close()


def get_kg_version() -> int:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM kg_db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


@dataclass
class KGNode:
    node_id: str
    node_type: str
    identifier: str
    name: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class KGEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float = 1.0
    confidence: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    created_at: float = field(default_factory=time.time)


def add_node(node: KGNode) -> str:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO kg_nodes (node_id, node_type, identifier, name, properties_json, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    name=excluded.name,
                    properties_json=excluded.properties_json,
                    updated_at=excluded.updated_at
                """,
                (
                    node.node_id, node.node_type, node.identifier, node.name,
                    json.dumps(node.properties), node.source,
                    node.created_at, node.updated_at,
                ),
            )
            conn.commit()
            return node.node_id
        finally:
            conn.close()


def add_edge(edge: KGEdge) -> str:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO kg_edges (edge_id, source_node_id, target_node_id, edge_type, weight, confidence, properties_json, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    source_node_id=excluded.source_node_id,
                    target_node_id=excluded.target_node_id,
                    edge_type=excluded.edge_type,
                    weight=excluded.weight,
                    confidence=excluded.confidence,
                    properties_json=excluded.properties_json
                """,
                (
                    edge.edge_id, edge.source_node_id, edge.target_node_id,
                    edge.edge_type, edge.weight, edge.confidence,
                    json.dumps(edge.properties), edge.source, edge.created_at,
                ),
            )
            conn.commit()
            return edge.edge_id
        finally:
            conn.close()


def get_node(node_id: str) -> KGNode | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM kg_nodes WHERE node_id=?", (node_id,)).fetchone()
            if not row:
                return None
            return KGNode(
                node_id=row["node_id"],
                node_type=row["node_type"],
                identifier=row["identifier"],
                name=row["name"],
                properties=json.loads(row["properties_json"]) if row["properties_json"] else {},
                source=row["source"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            conn.close()


def get_nodes_by_type(node_type: str, limit: int = 1000) -> list[KGNode]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute("SELECT * FROM kg_nodes WHERE node_type=? LIMIT ?", (node_type, limit)).fetchall()
            return [
                KGNode(
                    node_id=r["node_id"], node_type=r["node_type"], identifier=r["identifier"],
                    name=r["name"], properties=json.loads(r["properties_json"]) if r["properties_json"] else {},
                    source=r["source"], created_at=r["created_at"], updated_at=r["updated_at"],
                ) for r in rows
            ]
        finally:
            conn.close()


def find_nodes(identifier: str | None = None, name: str | None = None, node_type: str | None = None, limit: int = 100) -> list[KGNode]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = "SELECT * FROM kg_nodes WHERE 1=1"
            params = []
            if identifier:
                query += " AND identifier=?"
                params.append(identifier)
            if name:
                query += " AND name LIKE ?"
                params.append(f"%{name}%")
            if node_type:
                query += " AND node_type=?"
                params.append(node_type)
            query += " LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [
                KGNode(
                    node_id=r["node_id"], node_type=r["node_type"], identifier=r["identifier"],
                    name=r["name"], properties=json.loads(r["properties_json"]) if r["properties_json"] else {},
                    source=r["source"], created_at=r["created_at"], updated_at=r["updated_at"],
                ) for r in rows
            ]
        finally:
            conn.close()


def get_neighbors(node_id: str, edge_types: list[str] | None = None, direction: str = "both", limit: int = 500) -> list[tuple[KGEdge, KGNode]]:
    """Get neighboring nodes and edges."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conditions = []
            params = []
            if direction in ("out", "both"):
                conditions.append("e.source_node_id = ?")
                params.append(node_id)
            if direction in ("in", "both"):
                conditions.append("e.target_node_id = ?")
                params.append(node_id)
            
            if edge_types:
                placeholders = ",".join("?" * len(edge_types))
                conditions.append(f"e.edge_type IN ({placeholders})")
                params.extend(edge_types)
            
            where_clause = " OR ".join(conditions)
            
            query = f"""
                SELECT e.*, n.* FROM kg_edges e
                JOIN kg_nodes n ON (
                    (e.source_node_id = ? AND n.node_id = e.target_node_id) OR
                    (e.target_node_id = ? AND n.node_id = e.source_node_id)
                )
                WHERE {where_clause}
                LIMIT ?
            """
            params = [node_id, node_id] + params + [limit]
            rows = conn.execute(query, params).fetchall()
            
            results = []
            for r in rows:
                edge = KGEdge(
                    edge_id=r["edge_id"], source_node_id=r["source_node_id"],
                    target_node_id=r["target_node_id"], edge_type=r["edge_type"],
                    weight=r["weight"], confidence=r["confidence"],
                    properties=json.loads(r["properties_json"]) if r["properties_json"] else {},
                    source=r["source"], created_at=r["created_at"],
                )
                node = KGNode(
                    node_id=r["node_id"], node_type=r["node_type"],
                    identifier=r["identifier"], name=r["name"],
                    properties=json.loads(r["properties_json"]) if r["properties_json"] else {},
                    source=r["source"], created_at=r["created_at"], updated_at=r["updated_at"],
                )
                results.append((edge, node))
            return results
        finally:
            conn.close()


def shortest_path(source_id: str, target_id: str, max_depth: int = 6) -> list[KGNode] | None:
    """Find shortest path between two nodes using BFS."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            # Build adjacency for BFS
            adj = {}
            rows = conn.execute(
                "SELECT source_node_id, target_node_id FROM kg_edges"
            ).fetchall()
            for r in rows:
                adj.setdefault(r["source_node_id"], []).append(r["target_node_id"])
                adj.setdefault(r["target_node_id"], []).append(r["source_node_id"])
            
            # BFS
            from collections import deque
            queue = deque([(source_id, [source_id])])
            visited = {source_id}
            
            while queue:
                current, path = queue.popleft()
                if current == target_id:
                    # Get node objects for path
                    placeholders = ",".join("?" * len(path))
                    node_rows = conn.execute(
                        f"SELECT * FROM kg_nodes WHERE node_id IN ({placeholders})", path
                    ).fetchall()
                    node_map = {r["node_id"]: r for r in node_rows}
                    return [
                        KGNode(
                            node_id=node_map[nid]["node_id"],
                            node_type=node_map[nid]["node_type"],
                            identifier=node_map[nid]["identifier"],
                            name=node_map[nid]["name"],
                            properties=json.loads(node_map[nid]["properties_json"]) if node_map[nid]["properties_json"] else {},
                            source=node_map[nid]["source"],
                            created_at=node_map[nid]["created_at"],
                            updated_at=node_map[nid]["updated_at"],
                        ) for nid in path if nid in node_map
                    ]
                
                if len(path) >= max_depth:
                    continue
                
                for neighbor in adj.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor]))
            
            return None
        finally:
            conn.close()


def compute_centrality(node_type: str | None = None, top_k: int = 50) -> list[dict[str, Any]]:
    """Compute degree centrality for nodes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            query = """
                SELECT n.node_id, n.node_type, n.identifier, n.name, 
                       COUNT(e.edge_id) as degree
                FROM kg_nodes n
                LEFT JOIN kg_edges e ON n.node_id = e.source_node_id OR n.node_id = e.target_node_id
            """
            params = []
            if node_type:
                query += " WHERE n.node_type = ?"
                params.append(node_type)
            query += " GROUP BY n.node_id ORDER BY degree DESC LIMIT ?"
            params.append(top_k)
            
            rows = conn.execute(query, params).fetchall()
            return [
                {"node_id": r["node_id"], "node_type": r["node_type"],
                 "identifier": r["identifier"], "name": r["name"], "degree": r["degree"]}
                for r in rows
            ]
        finally:
            conn.close()


def store_analysis_result(analysis_id: str, analysis_type: str, parameters: dict[str, Any], results: dict[str, Any]) -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO kg_analysis_results (analysis_id, analysis_type, parameters_json, results_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id) DO UPDATE SET results_json=excluded.results_json
                """,
                (analysis_id, analysis_type, json.dumps(parameters), json.dumps(results), time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def get_analysis_result(analysis_id: str) -> dict[str, Any] | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM kg_analysis_results WHERE analysis_id=?", (analysis_id,)).fetchone()
            if not row:
                return None
            return {
                "analysis_id": row["analysis_id"],
                "analysis_type": row["analysis_type"],
                "parameters": json.loads(row["parameters_json"]),
                "results": json.loads(row["results_json"]),
                "created_at": row["created_at"],
            }
        finally:
            conn.close()


def bulk_load_from_opentargets(disease_gene_associations: list[dict], drug_target_interactions: list[dict]) -> int:
    """Bulk load OpenTargets data into knowledge graph."""
    count = 0
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for assoc in disease_gene_associations:
                gene_id = assoc.get("gene_id") or assoc.get("target_id")
                disease_id = assoc.get("disease_id")
                if not gene_id or not disease_id:
                    continue
                
                gene_node_id = f"gene:{gene_id}"
                disease_node_id = f"disease:{disease_id}"
                
                # Add gene node
                conn.execute(
                    """INSERT OR IGNORE INTO kg_nodes (node_id, node_type, identifier, name, properties_json, source, created_at, updated_at)
                       VALUES (?, 'gene', ?, ?, '{}', 'opentargets', ?, ?)""",
                    (gene_node_id, gene_id, assoc.get("gene_symbol", gene_id), time.time(), time.time()),
                )
                
                # Add disease node
                conn.execute(
                    """INSERT OR IGNORE INTO kg_nodes (node_id, node_type, identifier, name, properties_json, source, created_at, updated_at)
                       VALUES (?, 'disease', ?, ?, '{}', 'opentargets', ?, ?)""",
                    (disease_node_id, disease_id, assoc.get("disease_name", disease_id), time.time(), time.time()),
                )
                
                # Add edge
                edge_id = f"edge:{gene_node_id}:associated_with:{disease_node_id}"
                conn.execute(
                    """INSERT OR IGNORE INTO kg_edges (edge_id, source_node_id, target_node_id, edge_type, weight, confidence, properties_json, source, created_at)
                       VALUES (?, ?, ?, 'associated_with', ?, ?, '{}', 'opentargets', ?)""",
                    (edge_id, gene_node_id, disease_node_id, assoc.get("score", 0.5), assoc.get("score", 0.5), time.time()),
                )
                count += 1
            
            for inter in drug_target_interactions:
                drug_id = inter.get("drug_id") or inter.get("chembl_id")
                target_id = inter.get("target_id") or inter.get("gene_id")
                if not drug_id or not target_id:
                    continue
                
                drug_node_id = f"drug:{drug_id}"
                target_node_id = f"gene:{target_id}"
                
                conn.execute(
                    """INSERT OR IGNORE INTO kg_nodes (node_id, node_type, identifier, name, properties_json, source, created_at, updated_at)
                       VALUES (?, 'drug', ?, ?, '{}', 'chembl', ?, ?)""",
                    (drug_node_id, drug_id, inter.get("drug_name", drug_id), time.time(), time.time()),
                )
                
                conn.execute(
                    """INSERT OR IGNORE INTO kg_nodes (node_id, node_type, identifier, name, properties_json, source, created_at, updated_at)
                       VALUES (?, 'gene', ?, ?, '{}', 'opentargets', ?, ?)""",
                    (target_node_id, target_id, inter.get("target_name", target_id), time.time(), time.time()),
                )
                
                edge_id = f"edge:{drug_node_id}:treats:{target_node_id}"
                conn.execute(
                    """INSERT OR IGNORE INTO kg_edges (edge_id, source_node_id, target_node_id, edge_type, weight, confidence, properties_json, source, created_at)
                       VALUES (?, ?, ?, 'treats', ?, ?, '{}', 'chembl', ?)""",
                    (edge_id, drug_node_id, target_node_id, inter.get("affinity", 0.5), inter.get("confidence", 0.5), time.time()),
                )
                count += 1
            
            conn.commit()
            return count
        finally:
            conn.close()


def get_subgraph(node_ids: list[str], max_hops: int = 2) -> dict[str, Any]:
    """Extract subgraph around given nodes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            # Get all nodes within max_hops
            all_nodes = set(node_ids)
            current_frontier = set(node_ids)
            
            for _ in range(max_hops):
                if not current_frontier:
                    break
                placeholders = ",".join("?" * len(current_frontier))
                rows = conn.execute(
                    f"SELECT source_node_id, target_node_id FROM kg_edges WHERE source_node_id IN ({placeholders}) OR target_node_id IN ({placeholders})",
                    list(current_frontier)
                ).fetchall()
                next_frontier = set()
                for r in rows:
                    next_frontier.add(r["source_node_id"])
                    next_frontier.add(r["target_node_id"])
                new_nodes = next_frontier - all_nodes
                all_nodes.update(new_nodes)
                current_frontier = new_nodes
            
            # Get all nodes and edges in subgraph
            placeholders = ",".join("?" * len(all_nodes))
            node_rows = conn.execute(
                f"SELECT * FROM kg_nodes WHERE node_id IN ({placeholders})", list(all_nodes)
            ).fetchall()
            
            edge_rows = conn.execute(
                f"SELECT * FROM kg_edges WHERE source_node_id IN ({placeholders}) AND target_node_id IN ({placeholders})", 
                list(all_nodes) * 2
            ).fetchall()
            
            nodes = {
                r["node_id"]: {
                    "node_id": r["node_id"], "node_type": r["node_type"],
                    "identifier": r["identifier"], "name": r["name"],
                    "properties": json.loads(r["properties_json"]) if r["properties_json"] else {},
                    "source": r["source"],
                } for r in node_rows
            }
            
            edges = [
                {
                    "edge_id": r["edge_id"], "source_node_id": r["source_node_id"],
                    "target_node_id": r["target_node_id"], "edge_type": r["edge_type"],
                    "weight": r["weight"], "confidence": r["confidence"],
                    "properties": json.loads(r["properties_json"]) if r["properties_json"] else {},
                    "source": r["source"],
                } for r in edge_rows
            ]
            
            return {"nodes": nodes, "edges": edges}
        finally:
            conn.close()


initialize_knowledge_graph()