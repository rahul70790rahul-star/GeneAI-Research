"""Universal Dataset Registry - Step 5 of execution strategy.

Provides the DatasetRegistry class for discovering, indexing, validating,
and tracking biological datasets. Persists entries to the unified knowledge
database for durability and cross-module access.

No dataset records are fabricated. All entries are created from verifiable
source metadata supplied by the caller or discovered from public APIs.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from geneai.dataset_registry.models import (
    DatasetEntry,
    DatasetMetadata,
    DataType,
    LicenseType,
    ProcessingStatus,
)
from geneai.unified_knowledge.database import get_knowledge_db, DatabaseConfig

logger = logging.getLogger(__name__)

_REGISTRY_TABLE = "dataset_registry"


def _utc_now() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _generate_dataset_id(
    source: str, name: str, version: str, organism: str
) -> str:
    """Generate a deterministic dataset ID from key attributes."""
    namespace = uuid.UUID(
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    )
    key = f"{source}|{name}|{version}|{organism}"
    return str(uuid.uuid5(namespace, key))


class DatasetRegistry:
    """Registry for biological datasets used by GeneAI Research.

    Provides register, get, list, update, and quality-scoring operations.
    Entries are persisted in the unified knowledge database under the
    ``dataset_registry`` table.
    """

    def __init__(self, db_path: str = "geneai_knowledge.db"):
        self.db = get_knowledge_db(DatabaseConfig(db_path=db_path))
        self._ensure_table()

    # ------------------------------------------------------------------
    # Table management
    # ------------------------------------------------------------------
    def _ensure_table(self) -> None:
        """Create the dataset_registry table if it does not exist."""
        self.db.execute(
            f"""CREATE TABLE IF NOT EXISTS {_REGISTRY_TABLE} (
                dataset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                version TEXT NOT NULL,
                download_date TEXT NOT NULL,
                organism TEXT NOT NULL,
                data_type TEXT NOT NULL,
                genome_assembly TEXT,
                license TEXT NOT NULL,
                license_url TEXT,
                citation TEXT,
                provenance_url TEXT,
                record_count INTEGER,
                size_bytes INTEGER,
                checksum_sha256 TEXT,
                quality_score REAL NOT NULL DEFAULT 0.0,
                processing_status TEXT NOT NULL DEFAULT 'pending',
                validation_issues TEXT,
                duplicate_records INTEGER DEFAULT 0,
                missing_value_summary TEXT,
                last_validated TEXT,
                compatible_with TEXT,
                conflicting_with TEXT,
                attributes TEXT
            )"""
        )
        self.db.execute(
            f"""CREATE INDEX IF NOT EXISTS idx_dataset_source
            ON {_REGISTRY_TABLE}(source)"""
        )
        self.db.execute(
            f"""CREATE INDEX IF NOT EXISTS idx_dataset_organism
            ON {_REGISTRY_TABLE}(organism)"""
        )
        self.db.execute(
            f"""CREATE INDEX IF NOT EXISTS idx_dataset_status
            ON {_REGISTRY_TABLE}(processing_status)"""
        )

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _entry_to_row(entry: DatasetEntry) -> dict[str, Any]:
        """Convert a DatasetEntry to a database row dictionary."""
        import json

        return {
            "dataset_id": entry.dataset_id,
            "name": entry.metadata.name,
            "source": entry.metadata.source,
            "version": entry.metadata.version,
            "download_date": entry.metadata.download_date,
            "organism": entry.metadata.organism,
            "data_type": entry.metadata.data_type.value,
            "genome_assembly": entry.metadata.genome_assembly,
            "license": entry.metadata.license.value,
            "license_url": entry.metadata.license_url,
            "citation": entry.metadata.citation,
            "provenance_url": entry.metadata.provenance_url,
            "record_count": entry.metadata.record_count,
            "size_bytes": entry.metadata.size_bytes,
            "checksum_sha256": entry.metadata.checksum_sha256,
            "quality_score": entry.quality_score,
            "processing_status": entry.processing_status.value,
            "validation_issues": json.dumps(entry.validation_issues),
            "duplicate_records": entry.duplicate_records,
            "missing_value_summary": json.dumps(entry.missing_value_summary),
            "last_validated": entry.last_validated,
            "compatible_with": json.dumps(entry.compatible_with),
            "conflicting_with": json.dumps(entry.conflicting_with),
            "attributes": json.dumps(entry.metadata.attributes),
        }

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> DatasetEntry:
        """Convert a database row to a DatasetEntry."""
        import json

        metadata = DatasetMetadata(
            name=row["name"],
            source=row["source"],
            version=row["version"],
            download_date=row["download_date"],
            organism=row["organism"],
            data_type=DataType(row.get("data_type", "other")),
            genome_assembly=row.get("genome_assembly"),
            license=LicenseType(row.get("license", "unknown")),
            license_url=row.get("license_url"),
            citation=row.get("citation"),
            provenance_url=row.get("provenance_url"),
            record_count=row.get("record_count"),
            size_bytes=row.get("size_bytes"),
            checksum_sha256=row.get("checksum_sha256"),
            attributes=json.loads(row.get("attributes") or "{}"),
        )
        return DatasetEntry(
            dataset_id=row["dataset_id"],
            metadata=metadata,
            quality_score=row.get("quality_score", 0.0),
            processing_status=ProcessingStatus(
                row.get("processing_status", "pending")
            ),
            validation_issues=json.loads(row.get("validation_issues") or "[]"),
            duplicate_records=row.get("duplicate_records", 0) or 0,
            missing_value_summary=json.loads(row.get("missing_value_summary") or "{}"),
            last_validated=row.get("last_validated"),
            compatible_with=json.loads(row.get("compatible_with") or "[]"),
            conflicting_with=json.loads(row.get("conflicting_with") or "[]"),
        )

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        source: str,
        version: str,
        download_date: str | None = None,
        organism: str = "Homo sapiens",
        data_type: DataType = DataType.OTHER,
        genome_assembly: str | None = None,
        license: LicenseType = LicenseType.UNKNOWN,
        license_url: str | None = None,
        citation: str | None = None,
        provenance_url: str | None = None,
        record_count: int | None = None,
        size_bytes: int | None = None,
        checksum_sha256: str | None = None,
        attributes: dict[str, Any] | None = None,
        quality_score: float = 0.0,
        processing_status: ProcessingStatus = ProcessingStatus.PENDING,
    ) -> DatasetEntry:
        """Register a new dataset and return its DatasetEntry.

        If a dataset with the same source/name/version/organism already
        exists, the existing entry is returned (idempotent).
        """
        download_date = download_date or _utc_now()
        dataset_id = _generate_dataset_id(source, name, version, organism)

        existing = self.get(dataset_id)
        if existing is not None:
            logger.info(
                "Dataset already registered: %s (%s)", dataset_id, name
            )
            return existing

        metadata = DatasetMetadata(
            name=name,
            source=source,
            version=version,
            download_date=download_date,
            organism=organism,
            data_type=data_type,
            genome_assembly=genome_assembly,
            license=license,
            license_url=license_url,
            citation=citation,
            provenance_url=provenance_url,
            record_count=record_count,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            attributes=attributes or {},
        )
        entry = DatasetEntry(
            dataset_id=dataset_id,
            metadata=metadata,
            quality_score=quality_score,
            processing_status=processing_status,
        )

        row = self._entry_to_row(entry)
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        self.db.execute(
            f"INSERT INTO {_REGISTRY_TABLE} ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        logger.info("Registered dataset: %s (%s)", dataset_id, name)
        return entry

    def get(self, dataset_id: str) -> DatasetEntry | None:
        """Retrieve a dataset entry by ID. Returns None if not found."""
        row = self.db.fetchone(
            f"SELECT * FROM {_REGISTRY_TABLE} WHERE dataset_id = ?",
            (dataset_id,),
        )
        if row is None:
            return None
        return self._row_to_entry(dict(row))

    def list(
        self,
        source: str | None = None,
        status: ProcessingStatus | None = None,
    ) -> list[DatasetEntry]:
        """List all dataset entries, optionally filtered by source or status."""
        conditions: list[str] = []
        params: list[Any] = []
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        if status is not None:
            conditions.append("processing_status = ?")
            params.append(status.value)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.db.fetchall(
            f"SELECT * FROM {_REGISTRY_TABLE} {where} ORDER BY name",
            tuple(params),
        )
        return [self._row_to_entry(dict(r)) for r in rows]

    def update(self, entry: DatasetEntry) -> None:
        """Update an existing dataset entry in the registry."""
        if self.get(entry.dataset_id) is None:
            raise ValueError(f"Dataset not found: {entry.dataset_id}")
        row = self._entry_to_row(entry)
        set_clause = ", ".join(f"{k} = ?" for k in row.keys() if k != "dataset_id")
        values = [v for k, v in row.items() if k != "dataset_id"]
        values.append(entry.dataset_id)
        self.db.execute(
            f"UPDATE {_REGISTRY_TABLE} SET {set_clause} WHERE dataset_id = ?",
            tuple(values),
        )
        logger.info("Updated dataset: %s", entry.dataset_id)

    def remove(self, dataset_id: str) -> bool:
        """Remove a dataset entry. Returns True if removed, False if not found."""
        if self.get(dataset_id) is None:
            return False
        self.db.execute(
            f"DELETE FROM {_REGISTRY_TABLE} WHERE dataset_id = ?",
            (dataset_id,),
        )
        logger.info("Removed dataset: %s", dataset_id)
        return True

    # ------------------------------------------------------------------
    # Quality scoring
    # ------------------------------------------------------------------
    def compute_quality_score(
        self,
        entry: DatasetEntry,
        *,
        missing_value_penalty: float = 0.3,
        duplicate_penalty: float = 0.2,
        completeness_bonus: float = 0.2,
        provenance_bonus: float = 0.2,
        validation_penalty: float = 0.3,
    ) -> float:
        """Compute a quality score (0.0 to 1.0) for a dataset entry.

        The score is based on observable attributes only:
        - Missing values reduce the score.
        - Duplicate records reduce the score.
        - Complete metadata (citation, provenance, checksum) increases it.
        - Validated status increases it.
        - Validation issues decrease it.

        No biological data quality is inferred; only structural metrics
        are used.
        """
        score = 0.0

        # Base score for having any record count
        if entry.metadata.record_count and entry.metadata.record_count > 0:
            score += 0.2

        # Missing value penalty
        total_missing = sum(entry.missing_value_summary.values())
        if entry.metadata.record_count and entry.metadata.record_count > 0:
            missing_ratio = total_missing / (
                entry.metadata.record_count * max(len(entry.missing_value_summary), 1)
            )
            score -= missing_ratio * missing_value_penalty

        # Duplicate penalty
        if entry.metadata.record_count and entry.metadata.record_count > 0:
            dup_ratio = entry.duplicate_records / entry.metadata.record_count
            score -= dup_ratio * duplicate_penalty

        # Completeness bonus
        complete_fields = sum(
            1
            for f in (
                entry.metadata.citation,
                entry.metadata.provenance_url,
                entry.metadata.checksum_sha256,
                entry.metadata.license_url,
            )
            if f
        )
        score += (complete_fields / 4.0) * completeness_bonus

        # Provenance bonus
        if entry.metadata.citation or entry.metadata.provenance_url:
            score += provenance_bonus

        # Validation penalty
        score -= len(entry.validation_issues) * validation_penalty * 0.1

        # Status bonus
        if entry.processing_status == ProcessingStatus.READY:
            score += 0.1

        return max(0.0, min(1.0, round(score, 4)))

    def set_quality_score(self, dataset_id: str, score: float) -> None:
        """Set the quality score for a dataset entry."""
        entry = self.get(dataset_id)
        if entry is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        entry.quality_score = max(0.0, min(1.0, score))
        self.update(entry)

    def set_processing_status(
        self, dataset_id: str, status: ProcessingStatus
    ) -> None:
        """Set the processing status for a dataset entry."""
        entry = self.get(dataset_id)
        if entry is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        entry.processing_status = status
        if status == ProcessingStatus.READY:
            entry.last_validated = _utc_now()
        self.update(entry)

    # ------------------------------------------------------------------
    # Compatibility / conflict tracking
    # ------------------------------------------------------------------
    def mark_compatible(self, dataset_id_a: str, dataset_id_b: str) -> None:
        """Mark two datasets as compatible (can be combined)."""
        for src, dst in ((dataset_id_a, dataset_id_b), (dataset_id_b, dataset_id_a)):
            entry = self.get(src)
            if entry is None:
                continue
            if dst not in entry.compatible_with:
                entry.compatible_with.append(dst)
                self.update(entry)

    def mark_conflicting(self, dataset_id_a: str, dataset_id_b: str) -> None:
        """Mark two datasets as conflicting (should not be combined)."""
        for src, dst in ((dataset_id_a, dataset_id_b), (dataset_id_b, dataset_id_a)):
            entry = self.get(src)
            if entry is None:
                continue
            if dst not in entry.conflicting_with:
                entry.conflicting_with.append(dst)
                self.update(entry)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the registry."""
        total = len(self.list())
        by_status: dict[str, int] = {}
        for status in ProcessingStatus:
            by_status[status.value] = len(self.list(status=status))
        by_source: dict[str, int] = {}
        for entry in self.list():
            by_source[entry.metadata.source] = (
                by_source.get(entry.metadata.source, 0) + 1
            )
        return {
            "total_datasets": total,
            "by_status": by_status,
            "by_source": by_source,
        }