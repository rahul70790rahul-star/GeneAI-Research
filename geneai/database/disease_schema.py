"""Versioned SQLite schema and persistence for disease analyses.

The tables share the configured GeneAI database file used by the existing lab
sample register. Scientific API payloads retain source IDs and retrieval times.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)
DB_PATH = DATABASE_PATH
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS geneai_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diseases (
    disease_id INTEGER PRIMARY KEY,
    source_database TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    data_version TEXT NOT NULL DEFAULT '',
    UNIQUE(source_database, source_id)
);
CREATE TABLE IF NOT EXISTS disease_analyses (
    analysis_id TEXT PRIMARY KEY,
    disease_id INTEGER NOT NULL REFERENCES diseases(disease_id),
    input_json TEXT NOT NULL,
    priority_weights_json TEXT NOT NULL,
    source_versions_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disease_genes (
    disease_gene_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    gene_symbol TEXT NOT NULL,
    gene_name TEXT NOT NULL DEFAULT '',
    ncbi_gene_id TEXT NOT NULL DEFAULT '',
    ensembl_gene_id TEXT NOT NULL DEFAULT '',
    chromosome TEXT NOT NULL DEFAULT '',
    association_score REAL,
    research_priority_index REAL,
    research_priority_tier TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    UNIQUE(analysis_id, gene_symbol)
);
CREATE TABLE IF NOT EXISTS disease_proteins (
    disease_protein_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    gene_symbol TEXT NOT NULL DEFAULT '',
    uniprot_id TEXT NOT NULL,
    protein_name TEXT NOT NULL DEFAULT '',
    sequence TEXT NOT NULL DEFAULT '',
    annotation_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    UNIQUE(analysis_id, uniprot_id)
);
CREATE TABLE IF NOT EXISTS disease_pathways (
    disease_pathway_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    source_database TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    p_value REAL,
    fdr REAL,
    pathway_metadata_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    UNIQUE(analysis_id, source_database, source_id)
);
CREATE TABLE IF NOT EXISTS disease_mutations (
    disease_mutation_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    variant_id TEXT NOT NULL DEFAULT '',
    gene_symbol TEXT NOT NULL DEFAULT '',
    chromosome TEXT NOT NULL DEFAULT '',
    position INTEGER,
    reference_allele TEXT NOT NULL DEFAULT '',
    alternate_allele TEXT NOT NULL DEFAULT '',
    mutation_metadata_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disease_evidence (
    disease_evidence_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    gene_symbol TEXT NOT NULL DEFAULT '',
    evidence_type TEXT NOT NULL,
    source_database TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    score REAL,
    evidence_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disease_publications (
    disease_publication_id INTEGER PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES disease_analyses(analysis_id) ON DELETE CASCADE,
    pmid TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    publication_date TEXT NOT NULL DEFAULT '',
    abstract TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    UNIQUE(analysis_id, pmid)
);
CREATE INDEX IF NOT EXISTS idx_disease_genes_symbol ON disease_genes(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_disease_pathways_fdr ON disease_pathways(fdr);
CREATE INDEX IF NOT EXISTS idx_disease_publications_pmid ON disease_publications(pmid);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 15000")
    try:
        yield db
        db.commit()
    except sqlite3.Error:
        db.rollback()
        logger.exception("SQLite disease-analysis operation failed")
        raise
    finally:
        db.close()


def initialize_disease_schema() -> None:
    """Create additive disease tables without touching existing sample rows."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.executescript(_SCHEMA)
        db.execute(
            "INSERT OR IGNORE INTO geneai_schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )


def store_disease_analysis(result: dict[str, Any]) -> str:
    """Persist one retrieved evidence snapshot and return its analysis ID."""
    disease = result.get("disease") or {}
    analysis_id = result.get("analysis_id")
    disease_source_id = disease.get("disease_id") or disease.get("id")
    disease_name = disease.get("name")
    if not isinstance(analysis_id, str) or not analysis_id or not isinstance(disease_source_id, str) or not isinstance(disease_name, str):
        raise ValueError("Analysis result is missing its analysis or disease identifier.")
    now = result.get("retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    category = str(result.get("inputs", {}).get("disease_category") or "")
    source_versions = result.get("source_versions") or {}
    with _connect() as db:
        db.executescript(_SCHEMA)
        db.execute(
            """INSERT INTO diseases(source_database, source_id, name, category, description, retrieved_at, data_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_database, source_id) DO UPDATE SET
                 name=excluded.name, category=excluded.category, description=excluded.description,
                 retrieved_at=excluded.retrieved_at, data_version=excluded.data_version""",
            (
                "Open Targets Platform",
                disease_source_id,
                disease_name,
                category,
                str(disease.get("description") or ""),
                now,
                str(source_versions.get("Open Targets", "")),
            ),
        )
        disease_row = db.execute(
            "SELECT disease_id FROM diseases WHERE source_database=? AND source_id=?",
            ("Open Targets Platform", disease_source_id),
        ).fetchone()
        if disease_row is None:
            raise sqlite3.IntegrityError("Disease row was not created.")
        db.execute(
            """INSERT INTO disease_analyses
               (analysis_id, disease_id, input_json, priority_weights_json, source_versions_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                analysis_id,
                int(disease_row["disease_id"]),
                _json(result.get("inputs", {})),
                _json(result.get("priority_weights", {})),
                _json(source_versions),
                now,
            ),
        )
        for gene in result.get("genes", []):
            db.execute(
                """INSERT INTO disease_genes
                   (analysis_id, gene_symbol, gene_name, ncbi_gene_id, ensembl_gene_id, chromosome,
                    association_score, research_priority_index, research_priority_tier, evidence_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(gene.get("gene_symbol") or ""),
                    str(gene.get("gene_name") or ""),
                    str(gene.get("ncbi_gene_id") or ""),
                    str(gene.get("ensembl_gene_id") or ""),
                    str(gene.get("chromosome") or ""),
                    gene.get("association_score"),
                    gene.get("research_priority_index"),
                    str(gene.get("research_priority_tier") or ""),
                    _json(gene),
                    str(gene.get("source_url") or ""),
                    now,
                ),
            )
        for protein in result.get("proteins", []):
            db.execute(
                """INSERT INTO disease_proteins
                   (analysis_id, gene_symbol, uniprot_id, protein_name, sequence, annotation_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(protein.get("gene_symbol") or ""),
                    str(protein.get("uniprot_id") or ""),
                    str(protein.get("protein_name") or ""),
                    str(protein.get("sequence") or ""),
                    _json(protein),
                    str(protein.get("source_url") or ""),
                    now,
                ),
            )
        for pathway in result.get("pathways", {}).get("pathways", []):
            db.execute(
                """INSERT INTO disease_pathways
                   (analysis_id, source_database, source_id, name, p_value, fdr, pathway_metadata_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(pathway.get("source") or "Reactome Analysis Service"),
                    str(pathway.get("pathway_id") or ""),
                    str(pathway.get("name") or ""),
                    pathway.get("p_value"),
                    pathway.get("fdr"),
                    _json(pathway),
                    str(pathway.get("source_url") or ""),
                    now,
                ),
            )
        for variant in result.get("mutations", []):
            raw_gene_info = str(variant.get("gene_info_source_field") or "")
            gene_symbol = raw_gene_info.split("|", 1)[0].partition(":")[0].strip().upper()
            db.execute(
                """INSERT INTO disease_mutations
                   (analysis_id, variant_id, gene_symbol, chromosome, position, reference_allele, alternate_allele,
                    mutation_metadata_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(variant.get("id") or ""),
                    gene_symbol,
                    str(variant.get("chrom") or ""),
                    variant.get("pos"),
                    str(variant.get("ref") or ""),
                    str(variant.get("alt") or ""),
                    _json(variant),
                    "",
                    now,
                ),
            )
        for evidence in result.get("mechanism_evidence", []):
            db.execute(
                """INSERT INTO disease_evidence
                   (analysis_id, gene_symbol, evidence_type, source_database, source_id, score, evidence_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(evidence.get("gene_symbol") or ""),
                    str(evidence.get("evidence_type") or ""),
                    str(evidence.get("source") or ""),
                    "",
                    evidence.get("source_score"),
                    _json(evidence),
                    str(evidence.get("source_url") or ""),
                    now,
                ),
            )
        for go_item in result.get("go_annotations", []):
            db.execute(
                """INSERT INTO disease_evidence
                   (analysis_id, gene_symbol, evidence_type, source_database, source_id, score, evidence_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(go_item.get("gene_symbol") or ""),
                    f"Gene Ontology {go_item.get('aspect') or 'annotation'}",
                    "QuickGO / GOA",
                    str(go_item.get("go_id") or ""),
                    None,
                    _json(go_item),
                    str(go_item.get("source_url") or ""),
                    now,
                ),
            )
        for paper in result.get("publications", []):
            db.execute(
                """INSERT INTO disease_publications
                   (analysis_id, pmid, title, authors, publication_date, abstract, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    str(paper.get("pmid") or ""),
                    str(paper.get("title") or ""),
                    str(paper.get("authors") or ""),
                    str(paper.get("year") or ""),
                    str(paper.get("abstract") or ""),
                    str(paper.get("url") or ""),
                    now,
                ),
            )
    return analysis_id


def count_saved_analyses() -> int:
    """Return the number of persisted disease analysis snapshots."""
    initialize_disease_schema()
    with _connect() as db:
        row = db.execute("SELECT COUNT(*) AS count FROM disease_analyses").fetchone()
        return int(row["count"] if row else 0)
