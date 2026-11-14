"""Additive SQLite persistence for protein analysis (coordinates stay out of SQLite)."""
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
CREATE TABLE IF NOT EXISTS protein_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protein_records (
    record_key TEXT PRIMARY KEY,
    primary_identifier TEXT NOT NULL,
    source_database TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    gene_symbol TEXT NOT NULL DEFAULT '',
    protein_name TEXT NOT NULL DEFAULT '',
    organism TEXT NOT NULL DEFAULT '',
    function TEXT NOT NULL DEFAULT '',
    localization TEXT NOT NULL DEFAULT '',
    family_json TEXT NOT NULL,
    ec_numbers_json TEXT NOT NULL,
    interactions_json TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protein_sequences (
    sequence_id INTEGER PRIMARY KEY,
    record_key TEXT NOT NULL REFERENCES protein_records(record_key),
    sequence_sha256 TEXT NOT NULL,
    sequence_text TEXT NOT NULL,
    length_residues INTEGER NOT NULL,
    sequence_source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    UNIQUE(record_key, sequence_sha256)
);
CREATE TABLE IF NOT EXISTS protein_structures (
    structure_row_id INTEGER PRIMARY KEY,
    record_key TEXT NOT NULL REFERENCES protein_records(record_key),
    structure_id TEXT NOT NULL,
    structure_source TEXT NOT NULL,
    structure_type TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT '',
    experimental_method TEXT NOT NULL DEFAULT '',
    resolution_angstrom REAL,
    model_version TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    file_path TEXT,
    retrieved_at TEXT NOT NULL,
    UNIQUE(record_key, structure_id, structure_source)
);
CREATE TABLE IF NOT EXISTS protein_chains (
    chain_row_id INTEGER PRIMARY KEY,
    structure_row_id INTEGER NOT NULL REFERENCES protein_structures(structure_row_id) ON DELETE CASCADE,
    chain_id TEXT NOT NULL,
    residue_count INTEGER NOT NULL,
    atom_count INTEGER NOT NULL,
    sequence_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    UNIQUE(structure_row_id, chain_id)
);
CREATE TABLE IF NOT EXISTS protein_domains (
    domain_row_id INTEGER PRIMARY KEY,
    record_key TEXT NOT NULL REFERENCES protein_records(record_key),
    source_database TEXT NOT NULL,
    domain_type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_position INTEGER,
    end_position INTEGER,
    evidence_json TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protein_pockets (
    pocket_row_id INTEGER PRIMARY KEY,
    structure_row_id INTEGER NOT NULL REFERENCES protein_structures(structure_row_id) ON DELETE CASCADE,
    pocket_id TEXT NOT NULL,
    ligand_or_cofactor TEXT NOT NULL DEFAULT '',
    center_json TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    method TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(structure_row_id, pocket_id)
);
CREATE TABLE IF NOT EXISTS protein_residues (
    residue_row_id INTEGER PRIMARY KEY,
    pocket_row_id INTEGER NOT NULL REFERENCES protein_pockets(pocket_row_id) ON DELETE CASCADE,
    chain_id TEXT NOT NULL DEFAULT '',
    residue_number INTEGER,
    insertion_code TEXT NOT NULL DEFAULT '',
    residue_name TEXT NOT NULL DEFAULT '',
    distance_angstrom REAL,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protein_analysis_results (
    analysis_id TEXT PRIMARY KEY,
    record_key TEXT NOT NULL REFERENCES protein_records(record_key),
    sequence_metrics_json TEXT NOT NULL,
    structure_metrics_json TEXT NOT NULL,
    source_versions_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_protein_records_gene ON protein_records(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_protein_structures_id ON protein_structures(structure_id);
CREATE INDEX IF NOT EXISTS idx_protein_domains_record ON protein_domains(record_key);
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
        logger.exception("SQLite protein-analysis operation failed")
        raise
    finally:
        connection.close()


def initialize_protein_schema() -> None:
    """Create Phase 4.4 tables additively in the configured GeneAI database."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO protein_schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )
        connection.execute(
            "INSERT OR IGNORE INTO protein_schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )


def store_protein_analysis(result: dict[str, Any]) -> str:
    """Persist normalized annotations and metrics without storing coordinate bytes."""
    protein = result.get("protein") or {}
    record_key = protein.get("record_key")
    analysis_id = result.get("analysis_id")
    if not isinstance(record_key, str) or not record_key or not isinstance(analysis_id, str) or not analysis_id:
        raise ValueError("Protein analysis is missing a record key or analysis identifier.")
    now = result.get("retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            """INSERT INTO protein_records
               (record_key, primary_identifier, source_database, source_id, gene_symbol, protein_name,
                organism, function, localization, family_json, ec_numbers_json, interactions_json,
                source_version, source_url, retrieved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(record_key) DO UPDATE SET
                 primary_identifier=excluded.primary_identifier, source_database=excluded.source_database,
                 source_id=excluded.source_id, gene_symbol=excluded.gene_symbol,
                 protein_name=excluded.protein_name, organism=excluded.organism,
                 function=excluded.function, localization=excluded.localization,
                 family_json=excluded.family_json, ec_numbers_json=excluded.ec_numbers_json,
                 interactions_json=excluded.interactions_json, source_version=excluded.source_version,
                 source_url=excluded.source_url, retrieved_at=excluded.retrieved_at""",
            (
                record_key,
                str(protein.get("primary_accession") or protein.get("pdb_id") or record_key),
                str(protein.get("source") or "not reported"),
                str(protein.get("primary_accession") or ""),
                str(protein.get("gene_symbol") or ""),
                str(protein.get("protein_name") or ""),
                str(protein.get("organism") or ""),
                str(protein.get("function") or ""),
                str(protein.get("subcellular_location") or ""),
                _json(protein.get("family_annotations", [])),
                _json(protein.get("ec_numbers", [])),
                _json(protein.get("interactions", [])),
                str(protein.get("source_release") or ""),
                str(protein.get("source_url") or ""),
                now,
            ),
        )
        sequence = protein.get("sequence")
        sequence_metrics = result.get("sequence_analysis") or {}
        if isinstance(sequence, str) and sequence:
            connection.execute(
                """INSERT OR IGNORE INTO protein_sequences
                   (record_key, sequence_sha256, sequence_text, length_residues, sequence_source, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record_key,
                    str(sequence_metrics.get("sequence_sha256") or ""),
                    sequence,
                    int(sequence_metrics.get("length_residues") or len(sequence)),
                    str(protein.get("sequence_source") or protein.get("source") or "not reported"),
                    now,
                ),
            )
        connection.execute("DELETE FROM protein_domains WHERE record_key=?", (record_key,))
        for feature in protein.get("features", []):
            if not isinstance(feature, dict):
                continue
            connection.execute(
                """INSERT INTO protein_domains
                   (record_key, source_database, domain_type, description, start_position, end_position,
                    evidence_json, source_url, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_key,
                    str(protein.get("source") or "UniProtKB"),
                    str(feature.get("type") or ""),
                    str(feature.get("description") or ""),
                    feature.get("begin"),
                    feature.get("end"),
                    _json(feature.get("evidence", [])),
                    str(protein.get("source_url") or ""),
                    now,
                ),
            )

        structure = result.get("structure") or {}
        structure_row_id = None
        if structure.get("structure_id"):
            connection.execute(
                """INSERT INTO protein_structures
                   (record_key, structure_id, structure_source, structure_type, format, experimental_method,
                    resolution_angstrom, model_version, source_url, file_path, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(record_key, structure_id, structure_source) DO UPDATE SET
                     structure_type=excluded.structure_type, format=excluded.format,
                     experimental_method=excluded.experimental_method,
                     resolution_angstrom=excluded.resolution_angstrom, model_version=excluded.model_version,
                     source_url=excluded.source_url, retrieved_at=excluded.retrieved_at""",
                (
                    record_key,
                    str(structure.get("structure_id")),
                    str(structure.get("structure_source") or "uploaded"),
                    str(structure.get("structure_type") or "method not reported"),
                    str(structure.get("format") or ""),
                    str(structure.get("experimental_method") or ""),
                    structure.get("resolution_angstrom"),
                    str(structure.get("model_version") or ""),
                    str(structure.get("source_url") or ""),
                    None,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT structure_row_id FROM protein_structures WHERE record_key=? AND structure_id=? AND structure_source=?",
                (record_key, str(structure.get("structure_id")), str(structure.get("structure_source") or "uploaded")),
            ).fetchone()
            structure_row_id = int(row["structure_row_id"]) if row else None
        if structure_row_id is not None:
            for chain in structure.get("chains", []):
                if not isinstance(chain, dict):
                    continue
                connection.execute(
                    """INSERT INTO protein_chains
                       (structure_row_id, chain_id, residue_count, atom_count, sequence_text, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(structure_row_id, chain_id) DO UPDATE SET
                         residue_count=excluded.residue_count, atom_count=excluded.atom_count,
                         sequence_text=excluded.sequence_text, metadata_json=excluded.metadata_json""",
                    (
                        structure_row_id, str(chain.get("chain_id") or " "),
                        int(chain.get("amino_acid_residues") or 0), int(chain.get("heavy_atoms") or 0),
                        str(chain.get("sequence") or ""), _json(chain),
                    ),
                )
            for pocket in result.get("pockets", []):
                if not isinstance(pocket, dict):
                    continue
                connection.execute(
                    """INSERT INTO protein_pockets
                       (structure_row_id, pocket_id, ligand_or_cofactor, center_json, dimensions_json, method, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(structure_row_id, pocket_id) DO UPDATE SET
                         ligand_or_cofactor=excluded.ligand_or_cofactor, center_json=excluded.center_json,
                         dimensions_json=excluded.dimensions_json, method=excluded.method,
                         metadata_json=excluded.metadata_json""",
                    (
                        structure_row_id, str(pocket.get("pocket_id") or ""),
                        str(pocket.get("ligand_or_cofactor") or ""), _json(pocket.get("center_angstrom")),
                        _json(pocket.get("dimensions_angstrom")), str(pocket.get("method") or ""), _json(pocket),
                    ),
                )
                pocket_row = connection.execute(
                    "SELECT pocket_row_id FROM protein_pockets WHERE structure_row_id=? AND pocket_id=?",
                    (structure_row_id, str(pocket.get("pocket_id") or "")),
                ).fetchone()
                if pocket_row:
                    connection.execute(
                        "DELETE FROM protein_residues WHERE pocket_row_id=?",
                        (int(pocket_row["pocket_row_id"]),),
                    )
                    for residue in pocket.get("nearby_residues", []):
                        if not isinstance(residue, dict):
                            continue
                        connection.execute(
                            """INSERT INTO protein_residues
                               (pocket_row_id, chain_id, residue_number, insertion_code, residue_name,
                                distance_angstrom, metadata_json)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                int(pocket_row["pocket_row_id"]), str(residue.get("chain_id") or ""),
                                residue.get("residue_number"), str(residue.get("insertion_code") or ""),
                                str(residue.get("residue_name") or ""), residue.get("minimum_distance_angstrom"), _json(residue),
                            ),
                        )

        safe_result = {key: value for key, value in result.items() if not key.startswith("_")}
        structure_metrics = {key: value for key, value in structure.items() if key not in {"_structure_text", "_structure_bytes"}}
        connection.execute(
            """INSERT INTO protein_analysis_results
               (analysis_id, record_key, sequence_metrics_json, structure_metrics_json,
                source_versions_json, result_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(analysis_id) DO UPDATE SET
                 sequence_metrics_json=excluded.sequence_metrics_json,
                 structure_metrics_json=excluded.structure_metrics_json,
                 source_versions_json=excluded.source_versions_json,
                 result_json=excluded.result_json,
                 created_at=excluded.created_at""",
            (
                analysis_id, record_key, _json(sequence_metrics), _json(structure_metrics),
                _json(result.get("source_versions", {})), _json(safe_result), now,
            ),
        )
    return analysis_id
