"""Drug database schema and management for GeneAI Research."""
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

DB_PATH = DATABASE_PATH.parent / "geneai_drugs.sqlite3"

_SCHEMA_VERSION = 1

_CREATE_TABLES_SQL = """
-- Drugs table
CREATE TABLE IF NOT EXISTS drugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    drug_type TEXT,
    molecular_formula TEXT,
    molecular_weight REAL,
    canonical_smiles TEXT,
    isomeric_smiles TEXT,
    inchi TEXT,
    inchikey TEXT,
    iupac_name TEXT,
    xlogp3 REAL,
    exact_mass REAL,
    tpsa REAL,
    hbond_donor_count INTEGER,
    hbond_acceptor_count INTEGER,
    rotatable_bond_count INTEGER,
    charge INTEGER,
    complexity REAL,
    max_phase INTEGER,
    first_approval INTEGER,
    year_first_approval INTEGER,
    mechanism_of_action TEXT,
    action_type TEXT,
    source_url TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(source, source_id)
);

-- Drug identifiers
CREATE TABLE IF NOT EXISTS drug_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    UNIQUE(drug_id, identifier_type, identifier_value)
);

-- Drug synonyms
CREATE TABLE IF NOT EXISTS drug_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id INTEGER NOT NULL,
    synonym TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    UNIQUE(drug_id, synonym)
);

-- Target proteins
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT,
    gene_symbol TEXT,
    uniprot_id TEXT,
    organism TEXT,
    target_type TEXT,
    description TEXT,
    tractability_sm TEXT,
    tractability_ab TEXT,
    source_url TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(source, source_id)
);

-- Gene associations
CREATE TABLE IF NOT EXISTS gene_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    gene_symbol TEXT NOT NULL,
    gene_name TEXT,
    ensembl_id TEXT,
    ncbi_gene_id TEXT,
    association_type TEXT,
    confidence_score REAL,
    source TEXT NOT NULL,
    source_url TEXT,
    FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE
);

-- Disease associations
CREATE TABLE IF NOT EXISTS disease_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    disease_name TEXT,
    description TEXT,
    therapeutic_areas TEXT,
    known_drugs_count INTEGER,
    associated_targets_count INTEGER,
    source_url TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(source, source_id)
);

-- Drug-target interactions
CREATE TABLE IF NOT EXISTS drug_target_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    interaction_type TEXT,
    mechanism_of_action TEXT,
    action_type TEXT,
    affinity_type TEXT,
    affinity_value REAL,
    affinity_units TEXT,
    pchembl_value REAL,
    evidence_source TEXT,
    evidence_level TEXT,
    assay_id TEXT,
    assay_description TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    confidence_score REAL,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE,
    UNIQUE(drug_id, target_id, source, assay_id)
);

-- Drug-disease indications
CREATE TABLE IF NOT EXISTS drug_disease_indications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id INTEGER NOT NULL,
    disease_id INTEGER NOT NULL,
    max_phase_for_indication INTEGER,
    mesh_id TEXT,
    efo_id TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    FOREIGN KEY (disease_id) REFERENCES disease_associations(id) ON DELETE CASCADE,
    UNIQUE(drug_id, disease_id, source)
);

-- Target-disease associations
CREATE TABLE IF NOT EXISTS target_disease_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    disease_id INTEGER NOT NULL,
    association_score REAL,
    evidence_type TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE,
    FOREIGN KEY (disease_id) REFERENCES disease_associations(id) ON DELETE CASCADE,
    UNIQUE(target_id, disease_id, source)
);

-- Clinical trials
CREATE TABLE IF NOT EXISTS clinical_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nct_id TEXT NOT NULL UNIQUE,
    brief_title TEXT,
    official_title TEXT,
    overall_status TEXT,
    start_date TEXT,
    completion_date TEXT,
    primary_completion_date TEXT,
    phase TEXT,
    study_type TEXT,
    enrollment INTEGER,
    conditions TEXT,
    interventions TEXT,
    sponsor TEXT,
    collaborators TEXT,
    locations TEXT,
    primary_outcomes TEXT,
    secondary_outcomes TEXT,
    eligibility_criteria TEXT,
    healthy_volunteers TEXT,
    sex TEXT,
    minimum_age TEXT,
    maximum_age TEXT,
    source_url TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- Clinical trial drug links
CREATE TABLE IF NOT EXISTS clinical_trial_drugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_id INTEGER NOT NULL,
    drug_id INTEGER NOT NULL,
    intervention_name TEXT,
    intervention_type TEXT,
    FOREIGN KEY (trial_id) REFERENCES clinical_trials(id) ON DELETE CASCADE,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    UNIQUE(trial_id, drug_id)
);

-- Clinical trial gene links
CREATE TABLE IF NOT EXISTS clinical_trial_genes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_id INTEGER NOT NULL,
    gene_symbol TEXT NOT NULL,
    FOREIGN KEY (trial_id) REFERENCES clinical_trials(id) ON DELETE CASCADE,
    UNIQUE(trial_id, gene_symbol)
);

-- Literature references
CREATE TABLE IF NOT EXISTS literature_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pubmed_id TEXT NOT NULL UNIQUE,
    title TEXT,
    authors TEXT,
    journal TEXT,
    pub_date TEXT,
    abstract TEXT,
    doi TEXT,
    source_url TEXT,
    created_at REAL NOT NULL
);

-- Drug-literature links
CREATE TABLE IF NOT EXISTS drug_literature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id INTEGER NOT NULL,
    pubmed_id TEXT NOT NULL,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE,
    FOREIGN KEY (pubmed_id) REFERENCES literature_references(pubmed_id) ON DELETE CASCADE,
    UNIQUE(drug_id, pubmed_id)
);

-- Gene-literature links
CREATE TABLE IF NOT EXISTS gene_literature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gene_symbol TEXT NOT NULL,
    pubmed_id TEXT NOT NULL,
    FOREIGN KEY (pubmed_id) REFERENCES literature_references(pubmed_id) ON DELETE CASCADE,
    UNIQUE(gene_symbol, pubmed_id)
);

-- Cache metadata
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL UNIQUE,
    cache_value TEXT NOT NULL,
    source TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);

-- Database version
CREATE TABLE IF NOT EXISTS db_version (
    version INTEGER PRIMARY KEY,
    updated_at REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_drugs_source_id ON drugs(source, source_id);
CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
CREATE INDEX IF NOT EXISTS idx_drugs_inchikey ON drugs(inchikey);
CREATE INDEX IF NOT EXISTS idx_drug_identifiers_drug ON drug_identifiers(drug_id);
CREATE INDEX IF NOT EXISTS idx_targets_source_id ON targets(source, source_id);
CREATE INDEX IF NOT EXISTS idx_targets_gene ON targets(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_drug_target_interactions_drug ON drug_target_interactions(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_target_interactions_target ON drug_target_interactions(target_id);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_nct ON clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_conditions ON clinical_trials(conditions);
CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at);
"""

_DB_LOCK = threading.RLock()


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_database() -> None:
    """Create all tables and indexes."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO db_version (version, updated_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info("Drug database initialized at %s", DB_PATH)
        finally:
            conn.close()


def get_db_version() -> int:
    """Get current database schema version."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT version FROM db_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()


# Drug operations
def upsert_drug(drug_data: dict[str, Any]) -> int:
    """Insert or update a drug record. Returns drug_id."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO drugs (
                    source, source_id, name, description, drug_type,
                    molecular_formula, molecular_weight, canonical_smiles, isomeric_smiles,
                    inchi, inchikey, iupac_name, xlogp3, exact_mass, tpsa,
                    hbond_donor_count, hbond_acceptor_count, rotatable_bond_count,
                    charge, complexity, max_phase, first_approval, year_first_approval,
                    mechanism_of_action, action_type, source_url,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    drug_type=excluded.drug_type,
                    molecular_formula=excluded.molecular_formula,
                    molecular_weight=excluded.molecular_weight,
                    canonical_smiles=excluded.canonical_smiles,
                    isomeric_smiles=excluded.isomeric_smiles,
                    inchi=excluded.inchi,
                    inchikey=excluded.inchikey,
                    iupac_name=excluded.iupac_name,
                    xlogp3=excluded.xlogp3,
                    exact_mass=excluded.exact_mass,
                    tpsa=excluded.tpsa,
                    hbond_donor_count=excluded.hbond_donor_count,
                    hbond_acceptor_count=excluded.hbond_acceptor_count,
                    rotatable_bond_count=excluded.rotatable_bond_count,
                    charge=excluded.charge,
                    complexity=excluded.complexity,
                    max_phase=excluded.max_phase,
                    first_approval=excluded.first_approval,
                    year_first_approval=excluded.year_first_approval,
                    mechanism_of_action=excluded.mechanism_of_action,
                    action_type=excluded.action_type,
                    source_url=excluded.source_url,
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    drug_data.get("source"),
                    drug_data.get("source_id"),
                    drug_data.get("name"),
                    drug_data.get("description"),
                    drug_data.get("drug_type"),
                    drug_data.get("molecular_formula"),
                    drug_data.get("molecular_weight"),
                    drug_data.get("canonical_smiles"),
                    drug_data.get("isomeric_smiles"),
                    drug_data.get("inchi"),
                    drug_data.get("inchikey"),
                    drug_data.get("iupac_name"),
                    drug_data.get("xlogp3"),
                    drug_data.get("exact_mass"),
                    drug_data.get("tpsa"),
                    drug_data.get("hbond_donor_count"),
                    drug_data.get("hbond_acceptor_count"),
                    drug_data.get("rotatable_bond_count"),
                    drug_data.get("charge"),
                    drug_data.get("complexity"),
                    drug_data.get("max_phase"),
                    drug_data.get("first_approval"),
                    drug_data.get("year_first_approval"),
                    drug_data.get("mechanism_of_action"),
                    drug_data.get("action_type"),
                    drug_data.get("source_url"),
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            drug_id = row["id"] if row else None
            if drug_id is None:
                # Fetch existing
                row = conn.execute(
                    "SELECT id FROM drugs WHERE source=? AND source_id=?",
                    (drug_data.get("source"), drug_data.get("source_id")),
                ).fetchone()
                drug_id = row["id"] if row else 0
            conn.commit()
            return drug_id
        finally:
            conn.close()


def get_drug_by_source_id(source: str, source_id: str) -> dict[str, Any] | None:
    """Get drug by source and source_id."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM drugs WHERE source=? AND source_id=?",
                (source, source_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def search_drugs(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search drugs by name."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM drugs WHERE name LIKE ? ORDER BY name LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_drug_by_inchikey(inchikey: str) -> dict[str, Any] | None:
    """Get drug by InChIKey."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM drugs WHERE inchikey=?",
                (inchikey,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# Drug identifiers
def add_drug_identifier(drug_id: int, identifier_type: str, identifier_value: str, source: str, source_url: str | None = None) -> None:
    """Add a drug identifier."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO drug_identifiers (drug_id, identifier_type, identifier_value, source, source_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (drug_id, identifier_type, identifier_value, source, source_url),
            )
            conn.commit()
        finally:
            conn.close()


def get_drug_identifiers(drug_id: int) -> list[dict[str, Any]]:
    """Get all identifiers for a drug."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM drug_identifiers WHERE drug_id=?",
                (drug_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Drug synonyms
def add_drug_synonym(drug_id: int, synonym: str, source: str) -> None:
    """Add a drug synonym."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO drug_synonyms (drug_id, synonym, source) VALUES (?, ?, ?)",
                (drug_id, synonym, source),
            )
            conn.commit()
        finally:
            conn.close()


def get_drug_synonyms(drug_id: int) -> list[str]:
    """Get all synonyms for a drug."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT synonym FROM drug_synonyms WHERE drug_id=?",
                (drug_id,),
            ).fetchall()
            return [r["synonym"] for r in rows]
        finally:
            conn.close()


# Target operations
def upsert_target(target_data: dict[str, Any]) -> int:
    """Insert or update a target record. Returns target_id."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO targets (
                    source, source_id, name, gene_symbol, uniprot_id, organism,
                    target_type, description, tractability_sm, tractability_ab,
                    source_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    name=excluded.name,
                    gene_symbol=excluded.gene_symbol,
                    uniprot_id=excluded.uniprot_id,
                    organism=excluded.organism,
                    target_type=excluded.target_type,
                    description=excluded.description,
                    tractability_sm=excluded.tractability_sm,
                    tractability_ab=excluded.tractability_ab,
                    source_url=excluded.source_url,
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    target_data.get("source"),
                    target_data.get("source_id"),
                    target_data.get("name"),
                    target_data.get("gene_symbol"),
                    target_data.get("uniprot_id"),
                    target_data.get("organism"),
                    target_data.get("target_type"),
                    target_data.get("description"),
                    target_data.get("tractability_sm"),
                    target_data.get("tractability_ab"),
                    target_data.get("source_url"),
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            target_id = row["id"] if row else None
            if target_id is None:
                row = conn.execute(
                    "SELECT id FROM targets WHERE source=? AND source_id=?",
                    (target_data.get("source"), target_data.get("source_id")),
                ).fetchone()
                target_id = row["id"] if row else 0
            conn.commit()
            return target_id
        finally:
            conn.close()


def get_target_by_source_id(source: str, source_id: str) -> dict[str, Any] | None:
    """Get target by source and source_id."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM targets WHERE source=? AND source_id=?",
                (source, source_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def search_targets_by_gene(gene_symbol: str) -> list[dict[str, Any]]:
    """Search targets by gene symbol."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM targets WHERE gene_symbol=?",
                (gene_symbol,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Drug-target interactions
def upsert_drug_target_interaction(interaction_data: dict[str, Any]) -> int:
    """Insert or update a drug-target interaction. Returns interaction_id."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO drug_target_interactions (
                    drug_id, target_id, interaction_type, mechanism_of_action,
                    action_type, affinity_type, affinity_value, affinity_units,
                    pchembl_value, evidence_source, evidence_level, assay_id,
                    assay_description, source, source_url, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(drug_id, target_id, source, assay_id) DO UPDATE SET
                    interaction_type=excluded.interaction_type,
                    mechanism_of_action=excluded.mechanism_of_action,
                    action_type=excluded.action_type,
                    affinity_type=excluded.affinity_type,
                    affinity_value=excluded.affinity_value,
                    affinity_units=excluded.affinity_units,
                    pchembl_value=excluded.pchembl_value,
                    evidence_source=excluded.evidence_source,
                    evidence_level=excluded.evidence_level,
                    assay_description=excluded.assay_description,
                    source_url=excluded.source_url,
                    confidence_score=excluded.confidence_score
                RETURNING id
                """,
                (
                    interaction_data.get("drug_id"),
                    interaction_data.get("target_id"),
                    interaction_data.get("interaction_type"),
                    interaction_data.get("mechanism_of_action"),
                    interaction_data.get("action_type"),
                    interaction_data.get("affinity_type"),
                    interaction_data.get("affinity_value"),
                    interaction_data.get("affinity_units"),
                    interaction_data.get("pchembl_value"),
                    interaction_data.get("evidence_source"),
                    interaction_data.get("evidence_level"),
                    interaction_data.get("assay_id"),
                    interaction_data.get("assay_description"),
                    interaction_data.get("source"),
                    interaction_data.get("source_url"),
                    interaction_data.get("confidence_score", 0.5),
                ),
            )
            row = cursor.fetchone()
            interaction_id = row["id"] if row else 0
            conn.commit()
            return interaction_id
        finally:
            conn.close()


def get_drug_target_interactions(drug_id: int) -> list[dict[str, Any]]:
    """Get all target interactions for a drug."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT dti.*, t.name as target_name, t.gene_symbol, t.uniprot_id
                FROM drug_target_interactions dti
                JOIN targets t ON dti.target_id = t.id
                WHERE dti.drug_id=?
                ORDER BY dti.confidence_score DESC
                """,
                (drug_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_target_drug_interactions(target_id: int) -> list[dict[str, Any]]:
    """Get all drug interactions for a target."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT dti.*, d.name as drug_name, d.source as drug_source
                FROM drug_target_interactions dti
                JOIN drugs d ON dti.drug_id = d.id
                WHERE dti.target_id=?
                ORDER BY dti.confidence_score DESC
                """,
                (target_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Disease operations
def upsert_disease(disease_data: dict[str, Any]) -> int:
    """Insert or update a disease record. Returns disease_id."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO disease_associations (
                    source, source_id, disease_name, description, therapeutic_areas,
                    known_drugs_count, associated_targets_count, source_url,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    disease_name=excluded.disease_name,
                    description=excluded.description,
                    therapeutic_areas=excluded.therapeutic_areas,
                    known_drugs_count=excluded.known_drugs_count,
                    associated_targets_count=excluded.associated_targets_count,
                    source_url=excluded.source_url,
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    disease_data.get("source"),
                    disease_data.get("source_id"),
                    disease_data.get("disease_name"),
                    disease_data.get("description"),
                    disease_data.get("therapeutic_areas"),
                    disease_data.get("known_drugs_count"),
                    disease_data.get("associated_targets_count"),
                    disease_data.get("source_url"),
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            disease_id = row["id"] if row else None
            if disease_id is None:
                row = conn.execute(
                    "SELECT id FROM disease_associations WHERE source=? AND source_id=?",
                    (disease_data.get("source"), disease_data.get("source_id")),
                ).fetchone()
                disease_id = row["id"] if row else 0
            conn.commit()
            return disease_id
        finally:
            conn.close()


def get_disease_by_source_id(source: str, source_id: str) -> dict[str, Any] | None:
    """Get disease by source and source_id."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM disease_associations WHERE source=? AND source_id=?",
                (source, source_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# Drug-disease indications
def upsert_drug_disease_indication(indication_data: dict[str, Any]) -> None:
    """Link drug to disease indication."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO drug_disease_indications (
                    drug_id, disease_id, max_phase_for_indication, mesh_id, efo_id, source, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indication_data.get("drug_id"),
                    indication_data.get("disease_id"),
                    indication_data.get("max_phase_for_indication"),
                    indication_data.get("mesh_id"),
                    indication_data.get("efo_id"),
                    indication_data.get("source"),
                    indication_data.get("source_url"),
                ),
            )
            conn.commit()
        finally:
            conn.close()


# Target-disease associations
def upsert_target_disease_association(association_data: dict[str, Any]) -> None:
    """Link target to disease."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO target_disease_associations (
                    target_id, disease_id, association_score, evidence_type, source, source_url
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    association_data.get("target_id"),
                    association_data.get("disease_id"),
                    association_data.get("association_score"),
                    association_data.get("evidence_type"),
                    association_data.get("source"),
                    association_data.get("source_url"),
                ),
            )
            conn.commit()
        finally:
            conn.close()


# Clinical trials
def upsert_clinical_trial(trial_data: dict[str, Any]) -> int:
    """Insert or update a clinical trial. Returns trial_id."""
    now = time.time()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            columns = [
                "id", "nct_id", "brief_title", "official_title", "overall_status",
                "start_date", "completion_date", "primary_completion_date",
                "phase", "study_type", "enrollment", "conditions", "interventions",
                "sponsor", "collaborators", "locations", "primary_outcomes",
                "secondary_outcomes", "eligibility_criteria", "healthy_volunteers",
                "sex", "minimum_age", "maximum_age", "source_url", "created_at", "updated_at"
            ]
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"""
                INSERT INTO clinical_trials ({', '.join(columns)}) VALUES ({placeholders})
                ON CONFLICT(nct_id) DO UPDATE SET
                    brief_title=excluded.brief_title,
                    official_title=excluded.official_title,
                    overall_status=excluded.overall_status,
                    start_date=excluded.start_date,
                    completion_date=excluded.completion_date,
                    primary_completion_date=excluded.primary_completion_date,
                    phase=excluded.phase,
                    study_type=excluded.study_type,
                    enrollment=excluded.enrollment,
                    conditions=excluded.conditions,
                    interventions=excluded.interventions,
                    sponsor=excluded.sponsor,
                    collaborators=excluded.collaborators,
                    locations=excluded.locations,
                    primary_outcomes=excluded.primary_outcomes,
                    secondary_outcomes=excluded.secondary_outcomes,
                    eligibility_criteria=excluded.eligibility_criteria,
                    healthy_volunteers=excluded.healthy_volunteers,
                    sex=excluded.sex,
                    minimum_age=excluded.minimum_age,
                    maximum_age=excluded.maximum_age,
                    source_url=excluded.source_url,
                    updated_at=excluded.updated_at
                RETURNING id
            """
            values_tuple = (
                None,  # id (AUTOINCREMENT)
                trial_data.get("nct_id"),
                trial_data.get("brief_title"),
                trial_data.get("official_title"),
                trial_data.get("overall_status"),
                trial_data.get("start_date"),
                trial_data.get("completion_date"),
                trial_data.get("primary_completion_date"),
                trial_data.get("phase"),
                trial_data.get("study_type"),
                trial_data.get("enrollment"),
                trial_data.get("conditions"),
                trial_data.get("interventions"),
                trial_data.get("sponsor"),
                trial_data.get("collaborators"),
                trial_data.get("locations"),
                trial_data.get("primary_outcomes"),
                trial_data.get("secondary_outcomes"),
                trial_data.get("eligibility_criteria"),
                trial_data.get("healthy_volunteers"),
                trial_data.get("sex"),
                trial_data.get("minimum_age"),
                trial_data.get("maximum_age"),
                trial_data.get("source_url"),
                now,
                now,
            )
            cursor = conn.execute(sql, values_tuple)
            row = cursor.fetchone()
            trial_id = row["id"] if row else None
            if trial_id is None:
                row = conn.execute("SELECT id FROM clinical_trials WHERE nct_id=?", (trial_data.get("nct_id"),)).fetchone()
                trial_id = row["id"] if row else 0
            conn.commit()
            return trial_id
        finally:
            conn.close()


def get_clinical_trial_by_nct(nct_id: str) -> dict[str, Any] | None:
    """Get clinical trial by NCT ID."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM clinical_trials WHERE nct_id=?",
                (nct_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def search_clinical_trials(condition: str | None = None, drug_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Search clinical trials."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            if condition:
                rows = conn.execute(
                    "SELECT * FROM clinical_trials WHERE conditions LIKE ? ORDER BY start_date DESC LIMIT ?",
                    (f"%{condition}%", limit),
                ).fetchall()
            elif drug_name:
                rows = conn.execute(
                    "SELECT * FROM clinical_trials WHERE interventions LIKE ? ORDER BY start_date DESC LIMIT ?",
                    (f"%{drug_name}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM clinical_trials ORDER BY start_date DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def link_trial_drug(trial_id: int, drug_id: int, intervention_name: str, intervention_type: str) -> None:
    """Link clinical trial to drug."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO clinical_trial_drugs (trial_id, drug_id, intervention_name, intervention_type) VALUES (?, ?, ?, ?)",
                (trial_id, drug_id, intervention_name, intervention_type),
            )
            conn.commit()
        finally:
            conn.close()


def link_trial_gene(trial_id: int, gene_symbol: str) -> None:
    """Link clinical trial to gene."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO clinical_trial_genes (trial_id, gene_symbol) VALUES (?, ?)",
                (trial_id, gene_symbol),
            )
            conn.commit()
        finally:
            conn.close()


# Literature
def upsert_literature(ref_data: dict[str, Any]) -> None:
    """Insert or update literature reference."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO literature_references (pubmed_id, title, authors, journal, pub_date, abstract, doi, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pubmed_id) DO UPDATE SET
                    title=excluded.title,
                    authors=excluded.authors,
                    journal=excluded.journal,
                    pub_date=excluded.pub_date,
                    abstract=excluded.abstract,
                    doi=excluded.doi,
                    source_url=excluded.source_url
                """,
                (
                    ref_data.get("pubmed_id"),
                    ref_data.get("title"),
                    ref_data.get("authors"),
                    ref_data.get("journal"),
                    ref_data.get("pub_date"),
                    ref_data.get("abstract"),
                    ref_data.get("doi"),
                    ref_data.get("source_url"),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def link_drug_literature(drug_id: int, pubmed_id: str) -> None:
    """Link drug to literature."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO drug_literature (drug_id, pubmed_id) VALUES (?, ?)",
                (drug_id, pubmed_id),
            )
            conn.commit()
        finally:
            conn.close()


def link_gene_literature(gene_symbol: str, pubmed_id: str) -> None:
    """Link gene to literature."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO gene_literature (gene_symbol, pubmed_id) VALUES (?, ?)",
                (gene_symbol, pubmed_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_drug_literature(drug_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Get literature for a drug."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT lr.* FROM literature_references lr
                JOIN drug_literature dl ON lr.pubmed_id = dl.pubmed_id
                WHERE dl.drug_id=?
                ORDER BY lr.pub_date DESC LIMIT ?
                """,
                (drug_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_gene_literature(gene_symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get literature for a gene."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT lr.* FROM literature_references lr
                JOIN gene_literature gl ON lr.pubmed_id = gl.pubmed_id
                WHERE gl.gene_symbol=?
                ORDER BY lr.pub_date DESC LIMIT ?
                """,
                (gene_symbol, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Cache operations
def set_cache(cache_key: str, cache_value: str, source: str, ttl_seconds: int = 86400) -> None:
    """Set cache entry."""
    expires_at = time.time() + ttl_seconds
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO api_cache (cache_key, cache_value, source, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    cache_value=excluded.cache_value,
                    source=excluded.source,
                    expires_at=excluded.expires_at
                """,
                (cache_key, cache_value, source, expires_at, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def get_cache(cache_key: str) -> str | None:
    """Get cache entry if not expired."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT cache_value FROM api_cache WHERE cache_key=? AND expires_at > ?",
                (cache_key, time.time()),
            ).fetchone()
            return row["cache_value"] if row else None
        finally:
            conn.close()


def clear_expired_cache() -> int:
    """Clear expired cache entries. Returns count deleted."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM api_cache WHERE expires_at <= ?", (time.time(),))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# Initialize on import
initialize_database()