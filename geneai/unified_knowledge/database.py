"""Unified Biological Knowledge Database - Phase 5.3 Core."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Configuration for the unified knowledge database."""

    db_path: str = "geneai_knowledge.db"
    wal_mode: bool = True
    # Optional annotation links (for example protein -> gene) frequently arrive
    # before their referenced row, so referential integrity for those links is
    # enforced by the application layer instead of SQLite. Required foreign keys
    # (such as disease_id) are still validated in code before insertion.
    foreign_keys: bool = False
    busy_timeout: int = 30000
    cache_size: int = -32768  # 32MB
    # Connections are short-lived (one per operation) so that the database file
    # is never left locked. WAL plus ``synchronous=OFF`` avoids a filesystem
    # flush on every close, which keeps per-record writes fast. Raise this to
    # ``NORMAL`` or ``FULL`` when power-loss durability matters more than speed.
    synchronous: str = "OFF"
    journal_mode: str = "WAL"

    @property
    def path(self) -> str:
        """Backwards-compatible alias for the database path."""
        return self.db_path

    @path.setter
    def path(self, value: str) -> None:
        self.db_path = value


class _ResultSet:
    """Small materialised cursor used by :meth:`KnowledgeDatabase.execute`.

    Connections are intentionally short-lived (see
    :meth:`KnowledgeDatabase._connect`), so cursors cannot outlive the call
    that produced them. This wrapper keeps the rows and the usual cursor
    attributes available to callers.
    """

    def __init__(self, rows: list[sqlite3.Row], lastrowid: int | None = None, rowcount: int = -1):
        self._rows = list(rows)
        self._index = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self) -> sqlite3.Row | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[sqlite3.Row]:
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def __iter__(self):
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


class KnowledgeDatabase:
    """Unified knowledge database with integrated biological data.

    Connections are opened per operation and released immediately. This keeps
    the SQLite file (and its journal) unlocked between calls, which is required
    on Windows so that temporary directories and data folders can be removed.
    Bulk work should use :meth:`transaction`, which holds one connection for
    the duration of the block and can be nested through SAVEPOINTs.
    """

    _WRITE_STATEMENTS = {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER", "VACUUM"}

    def __init__(self, config: DatabaseConfig | None = None):
        self.config = config or DatabaseConfig()
        self._local = threading.local()
        self._shared_memory = self.config.db_path in (":memory:", "file::memory:", "")
        self._memory_conn: sqlite3.Connection | None = None
        if self._shared_memory:
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self._init_db()

    # -- connection lifecycle -------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        """Open a fully configured, short-lived connection."""
        conn = sqlite3.connect(
            self.config.db_path,
            timeout=max(1.0, self.config.busy_timeout / 1000),
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        self._configure_connection(conn)
        return conn

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """Apply per-connection pragmas."""
        conn.execute(f"PRAGMA foreign_keys={'ON' if self.config.foreign_keys else 'OFF'}")
        conn.execute(f"PRAGMA busy_timeout={int(self.config.busy_timeout)}")
        conn.execute(f"PRAGMA cache_size={int(self.config.cache_size)}")
        conn.execute(f"PRAGMA synchronous={self.config.synchronous}")

    def _acquire(self) -> tuple[sqlite3.Connection, bool]:
        """Return ``(connection, owned)``; ``owned`` signals who must close it."""
        if self._shared_memory:
            if self._memory_conn is None:  # pragma: no cover - defensive
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            self._configure_connection(self._memory_conn)
            return self._memory_conn, False
        return self._connect(), True

    @staticmethod
    def _release(conn: sqlite3.Connection, owned: bool) -> None:
        if owned:
            conn.close()

    def _effective_journal_mode(self) -> str:
        mode = (self.config.journal_mode or "").upper()
        if mode:
            return mode
        return "WAL" if self.config.wal_mode else "DELETE"

    def _init_db(self) -> None:
        """Initialize database schema and database-level pragmas."""
        path = self.config.db_path
        if not self._shared_memory:
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        conn, owned = self._acquire()
        try:
            journal = self._effective_journal_mode()
            if journal:
                conn.execute(f"PRAGMA journal_mode={journal}")
            self._create_tables(conn)
            self._create_indexes(conn)
            self._create_views(conn)
            conn.commit()
        finally:
            self._release(conn, owned)
        logger.info("Initialized knowledge database at %s", path)
    
    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create all database tables."""
        
        # Genes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS genes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                ensembl_id TEXT,
                entrez_id TEXT,
                name TEXT,
                description TEXT,
                chromosome TEXT,
                start_pos INTEGER,
                end_pos INTEGER,
                strand TEXT,
                biotype TEXT,
                uniprot_ids TEXT,  -- JSON array
                aliases TEXT,      -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Diseases table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS diseases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mondo_id TEXT UNIQUE,
                mesh_id TEXT,
                icd10_id TEXT,
                description TEXT,
                synonyms TEXT,  -- JSON array
                parent_ids TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Proteins table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proteins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uniprot_id TEXT NOT NULL UNIQUE,
                gene_symbol TEXT,
                name TEXT,
                sequence TEXT,
                length INTEGER,
                mass REAL,
                function TEXT,
                subcellular_location TEXT,
                domains TEXT,  -- JSON array
                pdb_ids TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gene_symbol) REFERENCES genes(symbol)
            )
        """)
        
        # Pathways table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pathways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pathway_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,  -- KEGG, Reactome, WikiPathways
                name TEXT,
                description TEXT,
                category TEXT,
                genes TEXT,  -- JSON array of gene symbols
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Drugs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drugs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chembl_id TEXT UNIQUE,
                drugbank_id TEXT UNIQUE,
                pubchem_cid TEXT UNIQUE,
                name TEXT NOT NULL,
                synonyms TEXT,  -- JSON array
                smiles TEXT,
                inchi TEXT,
                inchikey TEXT,
                molecular_formula TEXT,
                molecular_weight REAL,
                max_phase INTEGER,
                therapeutic_area TEXT,
                mechanism_of_action TEXT,
                targets TEXT,  -- JSON array of target info
                indications TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Drug-target interactions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drug_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drug_id INTEGER NOT NULL,
                target_uniprot TEXT NOT NULL,
                target_name TEXT,
                action_type TEXT,
                affinity_nM REAL,
                affinity_type TEXT,  -- Ki, Kd, IC50, EC50
                source TEXT,  -- ChEMBL, DrugBank, BindingDB
                confidence REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (drug_id) REFERENCES drugs(id)
            )
        """)
        
        # Disease-gene associations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS disease_gene_associations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                disease_id INTEGER NOT NULL,
                gene_symbol TEXT NOT NULL,
                association_type TEXT,  -- GWAS, somatic_mutation, drug_target, etc.
                score REAL,
                evidence TEXT,  -- JSON array of evidence
                source TEXT,  -- OpenTargets, DisGeNET, GWAS Catalog
                pmid TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (disease_id) REFERENCES diseases(id),
                FOREIGN KEY (gene_symbol) REFERENCES genes(symbol),
                UNIQUE(disease_id, gene_symbol, source)
            )
        """)
        
        # Protein-protein interactions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS protein_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protein_a TEXT NOT NULL,
                protein_b TEXT NOT NULL,
                interaction_type TEXT,  -- physical, genetic, predicted
                confidence REAL,
                source TEXT,  -- STRING, BioGRID, IntAct
                evidence TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (protein_a) REFERENCES proteins(uniprot_id),
                FOREIGN KEY (protein_b) REFERENCES proteins(uniprot_id)
            )
        """)
        
        # Variants table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variant_id TEXT NOT NULL UNIQUE,  -- rsID or custom
                chrom TEXT,
                pos INTEGER,
                ref TEXT,
                alt TEXT,
                gene_symbol TEXT,
                consequence TEXT,
                impact TEXT,  -- HIGH, MODERATE, LOW, MODIFIER
                clinvar_significance TEXT,
                gnomad_af REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gene_symbol) REFERENCES genes(symbol)
            )
        """)
        
        # Literature table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS literature (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT UNIQUE,
                doi TEXT,
                title TEXT,
                authors TEXT,  -- JSON array
                journal TEXT,
                year INTEGER,
                abstract TEXT,
                mesh_terms TEXT,  -- JSON array
                chemicals TEXT,  -- JSON array
                genes TEXT,  -- JSON array
                diseases TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ADMET predictions cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admet_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                smiles TEXT NOT NULL,
                inchikey TEXT,
                prediction_type TEXT,  -- absorption, distribution, metabolism, excretion, toxicity
                property_name TEXT,
                value REAL,
                unit TEXT,
                model_version TEXT,
                confidence REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(smiles, prediction_type, property_name, model_version)
            )
        """)
        
        # Biomarkers
        conn.execute("""
            CREATE TABLE IF NOT EXISTS biomarkers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                biomarker_id TEXT NOT NULL UNIQUE,
                name TEXT,
                type TEXT,  -- protein, gene, metabolite, clinical
                disease TEXT,
                sample_type TEXT,
                sensitivity REAL,
                specificity REAL,
                auc REAL,
                validation_status TEXT,
                source TEXT,
                pmid TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Clinical trials
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clinical_trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nct_id TEXT NOT NULL UNIQUE,
                title TEXT,
                status TEXT,
                phase TEXT,
                condition TEXT,
                intervention TEXT,
                sponsor TEXT,
                start_date TEXT,
                completion_date TEXT,
                enrollment INTEGER,
                locations TEXT,  -- JSON array
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Metadata table for tracking data versions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_genes_symbol ON genes(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_genes_ensembl ON genes(ensembl_id)",
            "CREATE INDEX IF NOT EXISTS idx_diseases_name ON diseases(name)",
            "CREATE INDEX IF NOT EXISTS idx_diseases_mondo ON diseases(mondo_id)",
            "CREATE INDEX IF NOT EXISTS idx_proteins_uniprot ON proteins(uniprot_id)",
            "CREATE INDEX IF NOT EXISTS idx_proteins_gene ON proteins(gene_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_pathways_source ON pathways(source)",
            "CREATE INDEX IF NOT EXISTS idx_pathways_genes ON pathways(genes)",
            "CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name)",
            "CREATE INDEX IF NOT EXISTS idx_drugs_chembl ON drugs(chembl_id)",
            "CREATE INDEX IF NOT EXISTS idx_drug_targets_drug ON drug_targets(drug_id)",
            "CREATE INDEX IF NOT EXISTS idx_drug_targets_target ON drug_targets(target_uniprot)",
            "CREATE INDEX IF NOT EXISTS idx_disease_gene_disease ON disease_gene_associations(disease_id)",
            "CREATE INDEX IF NOT EXISTS idx_disease_gene_gene ON disease_gene_associations(gene_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_ppi_protein_a ON protein_interactions(protein_a)",
            "CREATE INDEX IF NOT EXISTS idx_ppi_protein_b ON protein_interactions(protein_b)",
            "CREATE INDEX IF NOT EXISTS idx_variants_gene ON variants(gene_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_variants_chrom_pos ON variants(chrom, pos)",
            "CREATE INDEX IF NOT EXISTS idx_literature_pmid ON literature(pmid)",
            "CREATE INDEX IF NOT EXISTS idx_literature_year ON literature(year)",
            "CREATE INDEX IF NOT EXISTS idx_admet_smiles ON admet_predictions(smiles)",
            "CREATE INDEX IF NOT EXISTS idx_biomarkers_disease ON biomarkers(disease)",
            "CREATE INDEX IF NOT EXISTS idx_clinical_trials_condition ON clinical_trials(condition)",
        ]
        
        for idx in indexes:
            conn.execute(idx)
        conn.commit()
    
    def _create_views(self, conn: sqlite3.Connection) -> None:
        """Create useful database views."""
        views = [
            # Gene-disease view with details
            """
            CREATE VIEW IF NOT EXISTS v_gene_disease AS
            SELECT d.name as disease_name, d.mondo_id, g.symbol as gene_symbol, g.name as gene_name,
                   dga.association_type, dga.score, dga.source, dga.evidence, dga.pmid
            FROM disease_gene_associations dga
            JOIN diseases d ON dga.disease_id = d.id
            JOIN genes g ON dga.gene_symbol = g.symbol
            """,
            
            # Drug-target view with details
            """
            CREATE VIEW IF NOT EXISTS v_drug_target AS
            SELECT dr.name as drug_name, dr.chembl_id, dr.drugbank_id, dr.max_phase,
                   dt.target_uniprot, dt.target_name, dt.action_type, dt.affinity_nM,
                   dt.affinity_type, dt.source, dt.confidence
            FROM drug_targets dt
            JOIN drugs dr ON dt.drug_id = dr.id
            """,
            
            # Pathway-gene view
            """
            CREATE VIEW IF NOT EXISTS v_pathway_genes AS
            SELECT p.pathway_id, p.source, p.name as pathway_name, p.category,
                   json_each.value as gene_symbol
            FROM pathways p, json_each(p.genes)
            """,
        ]
        
        for view in views:
            conn.execute(view)
        conn.commit()
    
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions.

        Nested calls reuse the active connection through SAVEPOINTs so that
        higher-level operations can compose without deadlocking.
        """
        existing = getattr(self._local, "conn", None)
        if existing is not None:
            depth = getattr(self._local, "depth", 1) + 1
            self._local.depth = depth
            savepoint = f"geneai_sp_{depth}"
            existing.execute(f"SAVEPOINT {savepoint}")
            try:
                yield existing
            except Exception:
                existing.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                existing.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            else:
                existing.execute(f"RELEASE SAVEPOINT {savepoint}")
            finally:
                self._local.depth = depth - 1
            return

        conn, owned = self._acquire()
        self._local.conn = conn
        self._local.depth = 1
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._local.conn = None
            self._local.depth = 0
            self._release(conn, owned)

    def execute(self, query: str, params: tuple = ()) -> _ResultSet:
        """Execute a statement and return a materialised result set."""
        conn, owned = self._acquire()
        try:
            cursor = conn.execute(query, params)
            statement = query.strip().split(None, 1)[0].upper() if query.strip() else ""
            if statement in self._WRITE_STATEMENTS:
                conn.commit()
            rows = cursor.fetchall()
            return _ResultSet(rows, cursor.lastrowid, cursor.rowcount)
        finally:
            self._release(conn, owned)

    def fetchone(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """Fetch one row."""
        conn, owned = self._acquire()
        try:
            return conn.execute(query, params).fetchone()
        finally:
            self._release(conn, owned)

    def fetchall(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all rows."""
        conn, owned = self._acquire()
        try:
            return conn.execute(query, params).fetchall()
        finally:
            self._release(conn, owned)
    
    def insert(self, table: str, data: dict[str, Any]) -> int:
        """Insert a row and return the row ID."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self.transaction() as conn:
            cursor = conn.execute(query, tuple(data.values()))
            return cursor.lastrowid
    
    def upsert(self, table: str, data: dict[str, Any], conflict_columns: list[str]) -> int:
        """Insert or update a row."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        updates = ", ".join([f"{col}=excluded.{col}" for col in data.keys() if col not in conflict_columns])
        conflict = ", ".join(conflict_columns)
        query = f"""
            INSERT INTO {table} ({columns}) VALUES ({placeholders})
            ON CONFLICT({conflict}) DO UPDATE SET {updates}
        """
        with self.transaction() as conn:
            cursor = conn.execute(query, tuple(data.values()))
            return cursor.lastrowid
    
    def bulk_insert(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows efficiently."""
        if not rows:
            return 0
        columns = ", ".join(rows[0].keys())
        placeholders = ", ".join(["?"] * len(rows[0]))
        query = f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})"
        with self.transaction() as conn:
            cursor = conn.executemany(query, [tuple(r.values()) for r in rows])
            return cursor.rowcount
    
    def close(self) -> None:
        """Release any connection held by the current thread."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("Failed to close knowledge database connection", exc_info=True)
            self._local.conn = None
            self._local.depth = 0
        memory = getattr(self, "_memory_conn", None)
        if memory is not None:
            try:
                memory.close()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("Failed to close in-memory knowledge database", exc_info=True)
            self._memory_conn = None

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass
    
    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (list, dict, tuple)):
            return json.dumps(value, default=str)
        return value

    def _normalize_row(self, data: dict[str, Any], aliases: dict[str, str] | None = None) -> dict[str, Any]:
        aliases = aliases or {}
        row: dict[str, Any] = {}
        for key, value in data.items():
            row[aliases.get(key, key)] = self._serialize_value(value)
        return row

    def _upsert_row(self, table: str, data: dict[str, Any], conflict_column: str) -> int:
        """Insert a row or update the conflicting row, returning its primary key."""
        row = {key: value for key, value in data.items() if value is not None}
        if not row:
            raise ValueError(f"No usable columns supplied for table {table}.")
        columns = ", ".join(row)
        placeholders = ", ".join(["?"] * len(row))
        if conflict_column and conflict_column in row:
            updates = ", ".join(
                f"{column}=excluded.{column}"
                for column in row
                if column != conflict_column and column != "id"
            )
            suffix = f"ON CONFLICT({conflict_column}) DO UPDATE SET {updates}" if updates else "ON CONFLICT DO NOTHING"
        else:
            suffix = ""
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) {suffix}"
        with self.transaction() as conn:
            cursor = conn.execute(query, tuple(row.values()))
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            if conflict_column and conflict_column in row:
                existing = conn.execute(
                    f"SELECT id FROM {table} WHERE {conflict_column} = ?", (row[conflict_column],)
                ).fetchone()
                if existing:
                    return int(existing["id"])
        return 0

    # -- schema introspection -------------------------------------------
    def get_table_names(self) -> list[str]:
        """Return user table names."""
        rows = self.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> dict[str, str]:
        """Return a ``column -> type`` mapping for a table."""
        rows = self.fetchall(f"PRAGMA table_info({table})")
        return {row["name"]: row["type"] for row in rows}

    def count_rows(self, table: str) -> int:
        row = self.fetchone(f"SELECT COUNT(*) AS c FROM {table}")
        return int(row["c"]) if row else 0

    # -- genes ----------------------------------------------------------
    def insert_gene(self, data: dict[str, Any]) -> int:
        """Insert or update a gene, returning its row ID."""
        aliases = {
            "start": "start_pos",
            "end": "end_pos",
            "ensembl_gene_id": "ensembl_id",
            "ncbi_gene_id": "entrez_id",
        }
        row = self._normalize_row(data, aliases)
        row["symbol"] = str(row.get("symbol", "")).strip().upper()
        if not row["symbol"]:
            raise ValueError("Gene symbol is required.")
        return self._upsert_row("genes", row, "symbol")

    def get_gene_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        row = self.fetchone("SELECT * FROM genes WHERE symbol = ?", (symbol.strip().upper(),))
        return dict(row) if row else None

    def count_genes(self) -> int:
        return self.count_rows("genes")

    # -- diseases -------------------------------------------------------
    def insert_disease(self, data: dict[str, Any]) -> int:
        """Insert or update a disease, returning its row ID."""
        aliases = {"icd10_code": "icd10_id", "mesh": "mesh_id"}
        row = self._normalize_row(data, aliases)
        row["name"] = str(row.get("name", "")).strip()
        if not row["name"]:
            raise ValueError("Disease name is required.")
        conflict = "mondo_id" if row.get("mondo_id") else ""
        if not conflict:
            with self.transaction() as conn:
                cursor = conn.execute(
                    "INSERT INTO diseases (name, description) VALUES (?, ?)",
                    (row["name"], row.get("description")),
                )
                return int(cursor.lastrowid)
        return self._upsert_row("diseases", row, conflict)

    def get_disease_by_name(self, name: str) -> dict[str, Any] | None:
        row = self.fetchone("SELECT * FROM diseases WHERE name = ?", (name,))
        return dict(row) if row else None

    # -- proteins -------------------------------------------------------
    def insert_protein(self, data: dict[str, Any]) -> int:
        """Insert or update a protein, returning its row ID."""
        row = self._normalize_row(data)
        row["uniprot_id"] = str(row.get("uniprot_id", "")).strip()
        if not row["uniprot_id"]:
            raise ValueError("UniProt ID is required.")
        return self._upsert_row("proteins", row, "uniprot_id")

    def get_protein_by_uniprot(self, uniprot_id: str) -> dict[str, Any] | None:
        row = self.fetchone("SELECT * FROM proteins WHERE uniprot_id = ?", (uniprot_id,))
        return dict(row) if row else None

    # -- relationships --------------------------------------------------
    def insert_gene_disease_relationship(
        self,
        gene_id: int,
        disease_id: int,
        relationship_type: str = "associated",
        score: float | None = None,
        source: str = "manual",
        evidence: Any = None,
        pmid: str | None = None,
    ) -> int:
        """Create an association between an existing gene and disease."""
        gene = self.fetchone("SELECT symbol FROM genes WHERE id = ?", (gene_id,))
        disease = self.fetchone("SELECT id FROM diseases WHERE id = ?", (disease_id,))
        if gene is None:
            raise ValueError(f"Gene ID {gene_id} does not exist.")
        if disease is None:
            raise ValueError(f"Disease ID {disease_id} does not exist.")
        with self.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO disease_gene_associations
                   (disease_id, gene_symbol, association_type, score, evidence, source, pmid)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(disease_id, gene_symbol, source) DO UPDATE SET
                       association_type=excluded.association_type,
                       score=excluded.score,
                       evidence=excluded.evidence,
                       pmid=excluded.pmid""",
                (
                    disease_id,
                    gene["symbol"],
                    relationship_type,
                    score,
                    self._serialize_value(evidence) if evidence is not None else None,
                    source,
                    pmid,
                ),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            existing = conn.execute(
                """SELECT id FROM disease_gene_associations
                   WHERE disease_id = ? AND gene_symbol = ? AND source = ?""",
                (disease_id, gene["symbol"], source),
            ).fetchone()
            return int(existing["id"]) if existing else 0

    def get_gene_diseases(self, gene_id: int) -> list[dict[str, Any]]:
        """Return disease associations for a gene row ID."""
        gene = self.fetchone("SELECT symbol FROM genes WHERE id = ?", (gene_id,))
        if gene is None:
            return []
        rows = self.fetchall(
            """SELECT d.id AS disease_id, d.name AS disease_name, d.mondo_id,
                      dga.association_type AS relationship_type, dga.score,
                      dga.source, dga.evidence, dga.pmid
               FROM disease_gene_associations dga
               JOIN diseases d ON dga.disease_id = d.id
               WHERE dga.gene_symbol = ?
               ORDER BY dga.score DESC""",
            (gene["symbol"],),
        )
        return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, int]:
        """Get database statistics."""
        tables = [
            "genes", "diseases", "proteins", "pathways", "drugs",
            "drug_targets", "disease_gene_associations", "protein_interactions",
            "variants", "literature", "admet_predictions", "biomarkers", "clinical_trials"
        ]
        stats = {}
        for table in tables:
            try:
                count = self.fetchone(f"SELECT COUNT(*) as c FROM {table}")
                stats[table] = count["c"] if count else 0
            except Exception:
                stats[table] = 0
        return stats
    
    def vacuum(self) -> None:
        """Vacuum database to reclaim space."""
        conn, owned = self._acquire()
        try:
            conn.execute("VACUUM")
            conn.commit()
        finally:
            self._release(conn, owned)
        logger.info("Database vacuumed")


# Global database instance
_knowledge_db: KnowledgeDatabase | None = None


def get_knowledge_db(config: DatabaseConfig | None = None) -> KnowledgeDatabase:
    """Get global knowledge database instance."""
    global _knowledge_db
    if _knowledge_db is None:
        _knowledge_db = KnowledgeDatabase(config)
    return _knowledge_db


def init_knowledge_db(path: str = "geneai_knowledge.db") -> KnowledgeDatabase:
    """Initialize knowledge database with custom path."""
    global _knowledge_db
    if _knowledge_db is not None:
        try:
            _knowledge_db.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("Failed to close previous knowledge database", exc_info=True)
    config = DatabaseConfig(db_path=path)
    _knowledge_db = KnowledgeDatabase(config)
    return _knowledge_db