"""Universal Dataset Registry - Step 5 of execution strategy.

Public API for registering, discovering, and tracking biological datasets.
"""

from __future__ import annotations

from geneai.dataset_registry.models import (
    DatasetEntry,
    DatasetMetadata,
    DataType,
    LicenseType,
    ProcessingStatus,
)
from geneai.dataset_registry.registry import DatasetRegistry
from geneai.dataset_registry.discovery import DatasetDiscovery
from geneai.dataset_registry.validation import validate_dataframe_quality, validate_entry_against_dataframe
from geneai.dataset_registry.ui import (
    render_dataset_registry,
    render_data_quality_validator,
)

__all__ = [
    "DatasetEntry",
    "DatasetMetadata",
    "DataType",
    "LicenseType",
    "ProcessingStatus",
    "DatasetRegistry",
    "DatasetDiscovery",
    "validate_dataframe_quality",
    "validate_entry_against_dataframe",
    "render_dataset_registry",
    "render_data_quality_validator",
]

__version__ = "1.0.0"