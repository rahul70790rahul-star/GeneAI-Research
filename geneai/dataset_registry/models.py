"""Data models for the Universal Dataset Registry.

Defines DatasetEntry and DatasetMetadata dataclasses that capture
provenance, quality, and processing information for every biological
dataset registered with GeneAI Research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProcessingStatus(Enum):
    """Processing status of a registered dataset."""

    PENDING = "pending"
    VALIDATING = "validating"
    READY = "ready"
    ERROR = "error"
    DEPRECATED = "deprecated"


class DataType(Enum):
    """Biological data type categories."""

    GENOMIC_VARIANT = "genomic_variant"
    GENE_EXPRESSION = "gene_expression"
    PROTEIN_SEQUENCE = "protein_sequence"
    PROTEIN_STRUCTURE = "protein_structure"
    DISEASE_ASSOCIATION = "disease_association"
    DRUG_TARGET = "drug_target"
    PATHWAY = "pathway"
    LITERATURE = "literature"
    CLINICAL = "clinical"
    POPULATION_FREQUENCY = "population_frequency"
    FUNCTIONAL_ANNOTATION = "functional_annotation"
    OTHER = "other"


class LicenseType(Enum):
    """Common biological data license categories."""

    PUBLIC_DOMAIN = "public_domain"
    CC0 = "cc0"
    CC_BY = "cc_by"
    CC_BY_NC = "cc_by_nc"
    CC_BY_SA = "cc_by_sa"
    APACHE_2 = "apache_2"
    MIT = "mit"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


@dataclass
class DatasetMetadata:
    """Core metadata describing a biological dataset.

    All fields are populated from verifiable source information.
    No values are fabricated or inferred without evidence.
    """

    name: str
    source: str
    version: str
    download_date: str
    organism: str
    data_type: DataType
    genome_assembly: str | None = None
    license: LicenseType = LicenseType.UNKNOWN
    license_url: str | None = None
    citation: str | None = None
    provenance_url: str | None = None
    record_count: int | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise metadata to a plain dictionary."""
        return {
            "name": self.name,
            "source": self.source,
            "version": self.version,
            "download_date": self.download_date,
            "organism": self.organism,
            "data_type": self.data_type.value,
            "genome_assembly": self.genome_assembly,
            "license": self.license.value,
            "license_url": self.license_url,
            "citation": self.citation,
            "provenance_url": self.provenance_url,
            "record_count": self.record_count,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetMetadata":
        """Reconstruct metadata from a dictionary."""
        return cls(
            name=data["name"],
            source=data["source"],
            version=data["version"],
            download_date=data["download_date"],
            organism=data["organism"],
            data_type=DataType(data.get("data_type", "other")),
            genome_assembly=data.get("genome_assembly"),
            license=LicenseType(data.get("license", "unknown")),
            license_url=data.get("license_url"),
            citation=data.get("citation"),
            provenance_url=data.get("provenance_url"),
            record_count=data.get("record_count"),
            size_bytes=data.get("size_bytes"),
            checksum_sha256=data.get("checksum_sha256"),
            attributes=data.get("attributes", {}),
        )


@dataclass
class DatasetEntry:
    """A registered dataset entry in the Universal Dataset Registry.

    Combines metadata with quality scoring and processing status.
    """

    dataset_id: str
    metadata: DatasetMetadata
    quality_score: float = 0.0
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    validation_issues: list[str] = field(default_factory=list)
    duplicate_records: int = 0
    missing_value_summary: dict[str, int] = field(default_factory=dict)
    last_validated: str | None = None
    compatible_with: list[str] = field(default_factory=list)
    conflicting_with: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the entry to a plain dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "metadata": self.metadata.to_dict(),
            "quality_score": self.quality_score,
            "processing_status": self.processing_status.value,
            "validation_issues": self.validation_issues,
            "duplicate_records": self.duplicate_records,
            "missing_value_summary": self.missing_value_summary,
            "last_validated": self.last_validated,
            "compatible_with": self.compatible_with,
            "conflicting_with": self.conflicting_with,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetEntry":
        """Reconstruct an entry from a dictionary."""
        return cls(
            dataset_id=data["dataset_id"],
            metadata=DatasetMetadata.from_dict(data["metadata"]),
            quality_score=data.get("quality_score", 0.0),
            processing_status=ProcessingStatus(data.get("processing_status", "pending")),
            validation_issues=data.get("validation_issues", []),
            duplicate_records=data.get("duplicate_records", 0),
            missing_value_summary=data.get("missing_value_summary", {}),
            last_validated=data.get("last_validated"),
            compatible_with=data.get("compatible_with", []),
            conflicting_with=data.get("conflicting_with", []),
        )

    @property
    def is_ready(self) -> bool:
        """Return True if the dataset is validated and ready for use."""
        return self.processing_status == ProcessingStatus.READY

    @property
    def has_conflicts(self) -> bool:
        """Return True if the dataset has known conflicts with other datasets."""
        return len(self.conflicting_with) > 0