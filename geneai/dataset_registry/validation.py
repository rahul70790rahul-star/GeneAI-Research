"""Dataset quality validation for the Universal Dataset Registry.

Provides functions to validate registered datasets for missing values,
duplicate records, and structural issues. Reuses existing GeneAI
validation infrastructure (geneai.data_management, geneai.quality_assurance).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from geneai.data_management import validate_dataset, detect_duplicates, detect_missing_values
from geneai.dataset_registry.models import DatasetEntry

logger = logging.getLogger(__name__)


def validate_entry_against_dataframe(
    entry: DatasetEntry,
    df: pd.DataFrame,
) -> DatasetEntry:
    """Validate a dataset entry against its DataFrame and update quality metrics.

    Checks for:
    - Missing values per column
    - Duplicate rows
    - Required biological ID columns

    Returns the updated DatasetEntry with validation results.
    """
    report = validate_dataset(df)

    # Update missing value summary
    missing_summary: dict[str, int] = {}
    for col, count in report.missing_values.items():
        missing_summary[col] = int(count)

    # Count duplicates
    dup_df = detect_duplicates(df)
    duplicate_count = len(dup_df)

    # Collect validation issues
    issues: list[str] = []
    issues.extend(report.issues)
    issues.extend(report.warnings)
    if duplicate_count > 0:
        issues.append(f"{duplicate_count} duplicate row(s) detected")

    # Update the entry
    entry.missing_value_summary = missing_summary
    entry.duplicate_records = duplicate_count
    entry.validation_issues = issues
    entry.last_validated = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()

    # Determine processing status
    if report.is_valid and duplicate_count == 0:
        entry.processing_status = __import__("geneai.dataset_registry.models", fromlist=["ProcessingStatus"]).ProcessingStatus.READY
    else:
        entry.processing_status = __import__("geneai.dataset_registry.models", fromlist=["ProcessingStatus"]).ProcessingStatus.ERROR

    logger.info(
        "Validated dataset %s: valid=%s, duplicates=%d, missing_cols=%d",
        entry.dataset_id,
        report.is_valid,
        duplicate_count,
        len(missing_summary),
    )
    return entry


def validate_dataframe_quality(df: pd.DataFrame) -> dict[str, Any]:
    """Run quality validation on a DataFrame and return a summary dict.

    Does not modify any registry entry. Useful for pre-registration
    quality assessment.
    """
    report = validate_dataset(df)
    dup_df = detect_duplicates(df)
    missing_detail = detect_missing_values(df)

    return {
        "is_valid": report.is_valid,
        "row_count": report.row_count,
        "column_count": report.column_count,
        "columns": report.columns,
        "missing_values": report.missing_values,
        "missing_value_detail": missing_detail,
        "duplicate_rows": int(len(dup_df)),
        "duplicate_columns": report.duplicate_columns,
        "issues": report.issues,
        "warnings": report.warnings,
        "biological_ids_found": report.biological_ids_found,
    }