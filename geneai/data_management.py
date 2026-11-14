"""Data Management - Phase 6."""
from __future__ import annotations
import json, logging, os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import pandas as pd
logger = logging.getLogger(__name__)

BIOLOGICAL_ID_COLUMNS = {
    "gene_symbol", "gene", "symbol", "hgnc_symbol", "ensembl_gene_id",
    "entrez_id", "ncbi_gene_id", "uniprot_id", "protein_id",
    "chrom", "chromosome", "pos", "position", "start", "end",
    "ref", "alt", "allele", "variant", "rsid", "dbSNP",
    "sample_id", "sample_name", "sample", "subject_id",
}
REQUIRED_VARIANT_COLUMNS = {"chrom", "pos", "ref", "alt"}

@dataclass
class ValidationReport:
    is_valid: bool
    row_count: int
    column_count: int
    columns: list[str]
    missing_values: dict[str, int] = field(default_factory=dict)
    duplicate_rows: int = 0
    duplicate_columns: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    biological_ids_found: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid, "row_count": self.row_count,
            "column_count": self.column_count, "columns": self.columns,
            "missing_values": self.missing_values,
            "duplicate_rows": self.duplicate_rows,
            "duplicate_columns": self.duplicate_columns,
            "issues": self.issues, "warnings": self.warnings,
            "biological_ids_found": self.biological_ids_found,
        }

def _detect_file_type(file_path: str | Path) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv": return "csv"
    if suffix in (".xlsx", ".xls"): return "excel"
    if suffix == ".json": return "json"
    raise ValueError(f"Unsupported file type: {suffix}")
def import_dataset(file_path: str | Path, *, sheet_name: str | int = 0, **kwargs: Any) -> tuple[pd.DataFrame, ValidationReport]:
    """Import a dataset from CSV, Excel, or JSON."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    file_type = _detect_file_type(file_path)
    if file_type == "csv":
        df = pd.read_csv(file_path, **kwargs)
    elif file_type == "excel":
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, **kwargs)
        except ImportError as exc:
            raise ImportError(
                "Excel import requires openpyxl. Install with: pip install openpyxl"
            ) from exc
    elif file_type == "json":
        df = pd.read_json(file_path, **kwargs)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
    report = validate_dataset(df)
    return df, report

def validate_dataset(df: pd.DataFrame) -> ValidationReport:
    """Validate a biological dataset and return a validation report."""
    columns = df.columns.tolist()
    column_count = len(columns)
    row_count = len(df)
    missing_values = {}
    for col in columns:
        missing = int(df[col].isna().sum())
        if missing > 0:
            missing_values[col] = missing
    duplicate_rows = int(df.duplicated().sum())
    seen = set()
    duplicate_columns = []
    for col in columns:
        if col in seen:
            duplicate_columns.append(col)
        seen.add(col)
    lower_cols = {c.lower() for c in columns}
    biological_ids_found = sorted(col for col in columns if col.lower() in BIOLOGICAL_ID_COLUMNS)
    issues: list[str] = []
    warnings: list[str] = []
    if duplicate_columns:
        issues.append(f"Duplicate column names found: {duplicate_columns}")
    if duplicate_rows > 0:
        warnings.append(f"{duplicate_rows} duplicate row(s) detected")
    if missing_values:
        total_missing = sum(missing_values.values())
        warnings.append(f"{total_missing} missing value(s) across {len(missing_values)} column(s)")
    has_variant_cols = REQUIRED_VARIANT_COLUMNS.issubset(lower_cols)
    if has_variant_cols:
        warnings.append("Dataset appears to contain variant data (chrom, pos, ref, alt)")
    is_valid = len(issues) == 0 and row_count > 0
    return ValidationReport(
        is_valid=is_valid, row_count=row_count, column_count=column_count,
        columns=columns, missing_values=missing_values,
        duplicate_rows=duplicate_rows, duplicate_columns=duplicate_columns,
        issues=issues, warnings=warnings, biological_ids_found=biological_ids_found,
    )
def clean_dataset(df: pd.DataFrame, *, remove_duplicates: bool = True,
                  fill_missing: str | None = None,
                  drop_missing_columns: list[str] | None = None,
                  drop_missing_rows: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean a dataset with configurable operations."""
    df = df.copy()
    operations: dict[str, Any] = {}
    original_rows = len(df)
    original_cols = len(df.columns)
    if remove_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        operations["duplicates_removed"] = before - len(df)
    if drop_missing_columns:
        before_cols = len(df.columns)
        df = df.drop(columns=[c for c in drop_missing_columns if c in df.columns], errors="ignore")
        operations["columns_dropped"] = before_cols - len(df.columns)
    if drop_missing_rows:
        before = len(df)
        df = df.dropna()
        operations["rows_dropped_for_missing"] = before - len(df)
    if fill_missing is not None:
        missing_before = int(df.isna().sum().sum())
        if fill_missing == "mean":
            df = df.fillna(df.mean(numeric_only=True))
        elif fill_missing == "median":
            df = df.fillna(df.median(numeric_only=True))
        elif fill_missing == "mode":
            for col in df.columns:
                mode_val = df[col].mode()
                if len(mode_val) > 0:
                    df[col] = df[col].fillna(mode_val.iloc[0])
        elif fill_missing == "forward":
            df = df.fillna(method="ffill")
        elif fill_missing == "backward":
            df = df.fillna(method="bfill")
        else:
            df = df.fillna(fill_missing)
        missing_after = int(df.isna().sum().sum())
        operations["missing_values_filled"] = missing_before - missing_after
    operations["original_rows"] = original_rows
    operations["original_columns"] = original_cols
    operations["final_rows"] = len(df)
    operations["final_columns"] = len(df.columns)
    return df, operations

def export_dataset(df: pd.DataFrame, file_path: str | Path, *, index: bool = False, **kwargs: Any) -> str:
    """Export a dataset to CSV, Excel, or JSON."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_type = _detect_file_type(file_path)
    if file_type == "csv":
        df.to_csv(file_path, index=index, **kwargs)
    elif file_type == "excel":
        try:
            df.to_excel(file_path, index=index, **kwargs)
        except ImportError as exc:
            raise ImportError(
                "Excel export requires openpyxl. Install with: pip install openpyxl"
            ) from exc
    elif file_type == "json":
        df.to_json(file_path, index=index, **kwargs)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
    logger.info("Exported dataset to %s (%d rows, %d columns)", file_path, len(df), len(df.columns))
    return str(file_path)

def detect_duplicates(df: pd.DataFrame, subset: list[str] | None = None) -> pd.DataFrame:
    """Return duplicate rows from a dataset."""
    return df[df.duplicated(subset=subset, keep=False)].sort_index()

def detect_missing_values(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Return detailed missing value information per column."""
    result: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        missing = df[col].isna()
        count = int(missing.sum())
        if count > 0:
            result[col] = {
                "count": count,
                "percentage": round(count / len(df) * 100, 2) if len(df) > 0 else 0.0,
                "row_indices": df.index[missing].tolist(),
            }
    return result

def validate_variant_dataset(df: pd.DataFrame) -> ValidationReport:
    """Validate a variant dataset (VCF-like) with biological checks."""
    report = validate_dataset(df)
    lower_cols = {c.lower() for c in df.columns}
    if not REQUIRED_VARIANT_COLUMNS.issubset(lower_cols):
        missing = REQUIRED_VARIANT_COLUMNS - lower_cols
        report.issues.append(f"Missing required variant columns: {sorted(missing)}")
        report.is_valid = False
    chrom_col = next((c for c in df.columns if c.lower() == "chrom"), None)
    if chrom_col and chrom_col in df.columns:
        unique_chroms = df[chrom_col].dropna().unique()
        report.warnings.append(
            f"Unique chromosomes found: {sorted(str(c) for c in unique_chroms)[:20]}"
        )
    pos_col = next((c for c in df.columns if c.lower() == "pos"), None)
    if pos_col and pos_col in df.columns:
        try:
            pd.to_numeric(df[pos_col], errors="raise")
        except (ValueError, TypeError):
            non_numeric = df[pd.to_numeric(df[pos_col], errors="coerce").isna()][pos_col]
            report.warnings.append(
                f"Position column has {len(non_numeric)} non-numeric value(s)"
            )
    return report