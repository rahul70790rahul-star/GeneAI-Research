"""Quality Assurance - Phase 6."""
from __future__ import annotations
import logging, re, sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ValidationResult:
    check_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"check_name": self.check_name, "severity": self.severity.value,
                "passed": self.passed, "message": self.message, "details": self.details}

@dataclass
class QAReport:
    results: list[ValidationResult] = field(default_factory=list)
    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL))
    @property
    def errors(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)]
    @property
    def warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.severity == ValidationSeverity.WARNING]
    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "total_checks": len(self.results),
                "passed_checks": sum(1 for r in self.results if r.passed),
                "errors": [r.to_dict() for r in self.errors],
                "warnings": [r.to_dict() for r in self.warnings],
                "all_results": [r.to_dict() for r in self.results]}

GENE_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
VARIANT_ID_PATTERN = re.compile(r"^(chr)?[\dXYM]+:(\d+):([ACGT]+):([ACGT]+)$")
PROTEIN_CHANGE_PATTERN = re.compile(r"^p\.[A-Za-z]{3}\d+[A-Za-z\*]$")
SAMPLE_ID_PATTERN = re.compile(r"^GAR-[A-Z0-9]{10}$")
EXPERIMENT_ID_PATTERN = re.compile(r"^EXP-[A-Z0-9]{10}$")
PROJECT_ID_PATTERN = re.compile(r"^PRJ-[A-Z0-9]{10}$")
def validate_gene_symbol(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("gene_symbol", ValidationSeverity.ERROR, False,
                                "Gene symbol is required and must be a string")
    if not GENE_SYMBOL_PATTERN.match(value.strip()):
        return ValidationResult("gene_symbol", ValidationSeverity.ERROR, False,
                                f"Invalid gene symbol format: {value}")
    return ValidationResult("gene_symbol", ValidationSeverity.INFO, True,
                            f"Gene symbol '{value}' is valid")

def validate_variant_id(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("variant_id", ValidationSeverity.ERROR, False,
                                "Variant ID is required and must be a string")
    if not VARIANT_ID_PATTERN.match(value.strip()):
        return ValidationResult("variant_id", ValidationSeverity.ERROR, False,
                                f"Invalid variant ID format: {value}. Expected chr:pos:ref:alt")
    return ValidationResult("variant_id", ValidationSeverity.INFO, True,
                            f"Variant ID '{value}' is valid")

def validate_protein_change(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("protein_change", ValidationSeverity.ERROR, False,
                                "Protein change is required and must be a string")
    if not PROTEIN_CHANGE_PATTERN.match(value.strip()):
        return ValidationResult("protein_change", ValidationSeverity.WARNING, False,
                                f"Protein change format may be non-standard: {value}")
    return ValidationResult("protein_change", ValidationSeverity.INFO, True,
                            f"Protein change '{value}' is valid")

def validate_sample_id(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("sample_id", ValidationSeverity.ERROR, False,
                                "Sample ID is required and must be a string")
    if not SAMPLE_ID_PATTERN.match(value.strip()):
        return ValidationResult("sample_id", ValidationSeverity.ERROR, False,
                                f"Invalid sample ID format: {value}. Expected GAR-XXXXXXXXXX")
    return ValidationResult("sample_id", ValidationSeverity.INFO, True,
                            f"Sample ID '{value}' is valid")

def validate_experiment_id(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("experiment_id", ValidationSeverity.ERROR, False,
                                "Experiment ID is required and must be a string")
    if not EXPERIMENT_ID_PATTERN.match(value.strip()):
        return ValidationResult("experiment_id", ValidationSeverity.ERROR, False,
                                f"Invalid experiment ID format: {value}. Expected EXP-XXXXXXXXXX")
    return ValidationResult("experiment_id", ValidationSeverity.INFO, True,
                            f"Experiment ID '{value}' is valid")

def validate_project_id(value: str) -> ValidationResult:
    if not value or not isinstance(value, str):
        return ValidationResult("project_id", ValidationSeverity.ERROR, False,
                                "Project ID is required and must be a string")
    if not PROJECT_ID_PATTERN.match(value.strip()):
        return ValidationResult("project_id", ValidationSeverity.ERROR, False,
                                f"Invalid project ID format: {value}. Expected PRJ-XXXXXXXXXX")
    return ValidationResult("project_id", ValidationSeverity.INFO, True,
                            f"Project ID '{value}' is valid")
def validate_api_response(response: dict[str, Any]) -> ValidationResult:
    if not isinstance(response, dict):
        return ValidationResult("api_response", ValidationSeverity.ERROR, False,
                                "API response must be a dictionary")
    if "success" not in response:
        return ValidationResult("api_response", ValidationSeverity.ERROR, False,
                                "API response missing 'success' field")
    if not isinstance(response["success"], bool):
        return ValidationResult("api_response", ValidationSeverity.ERROR, False,
                                "API response 'success' must be boolean")
    return ValidationResult("api_response", ValidationSeverity.INFO, True,
                            "API response structure is valid")

def validate_api_endpoint(endpoint: str) -> ValidationResult:
    if not endpoint or not isinstance(endpoint, str):
        return ValidationResult("api_endpoint", ValidationSeverity.ERROR, False,
                                "Endpoint is required and must be a string")
    if not endpoint.startswith("/"):
        return ValidationResult("api_endpoint", ValidationSeverity.ERROR, False,
                                f"Endpoint must start with '/': {endpoint}")
    return ValidationResult("api_endpoint", ValidationSeverity.INFO, True,
                            f"Endpoint '{endpoint}' is valid")

def validate_database_integrity(db_path: str | Path) -> QAReport:
    report = QAReport()
    db_path = Path(db_path)
    if not db_path.exists():
        report.results.append(ValidationResult(
            "database_exists", ValidationSeverity.CRITICAL, False,
            f"Database file not found: {db_path}"))
        return report
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            report.results.append(ValidationResult(
                "database_integrity",
                ValidationSeverity.CRITICAL if integrity != "ok" else ValidationSeverity.INFO,
                integrity == "ok",
                f"Database integrity check: {integrity}"))
            fk_count = conn.execute("PRAGMA foreign_key_check").fetchall()
            report.results.append(ValidationResult(
                "foreign_key_integrity",
                ValidationSeverity.ERROR if fk_count else ValidationSeverity.INFO,
                len(fk_count) == 0,
                f"Foreign key violations: {len(fk_count)}",
                details={"violations": [list(v) for v in fk_count]}))
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            report.results.append(ValidationResult(
                "database_tables", ValidationSeverity.INFO,
                len(tables) > 0,
                f"Found {len(tables)} table(s)",
                details={"tables": [t[0] for t in tables]}))
            table_counts = {}
            for (table_name,) in tables:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    table_counts[table_name] = count
                except sqlite3.Error:
                    table_counts[table_name] = "error"
            report.results.append(ValidationResult(
                "table_row_counts", ValidationSeverity.INFO, True,
                "Row counts retrieved", details=table_counts))
        finally:
            conn.close()
    except sqlite3.Error as exc:
        report.results.append(ValidationResult(
            "database_access", ValidationSeverity.CRITICAL, False,
            f"Cannot access database: {exc}"))
    return report
def check_data_integrity(df, required_columns: list[str] | None = None) -> QAReport:
    import pandas as pd
    if not isinstance(df, pd.DataFrame):
        return QAReport(results=[ValidationResult(
            "dataframe_type", ValidationSeverity.ERROR, False,
            "Input must be a pandas DataFrame")])
    report = QAReport()
    report.results.append(ValidationResult(
        "non_empty", ValidationSeverity.ERROR,
        len(df) > 0,
        f"DataFrame has {len(df)} row(s)",
        details={"rows": len(df), "columns": len(df.columns)}))
    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        report.results.append(ValidationResult(
            "required_columns",
            ValidationSeverity.ERROR if missing else ValidationSeverity.INFO,
            len(missing) == 0,
            f"Required columns present: {len(required_columns) - len(missing)}/{len(required_columns)}",
            details={"missing": missing}))
    dup_count = int(df.duplicated().sum())
    report.results.append(ValidationResult(
        "no_duplicate_rows",
        ValidationSeverity.WARNING if dup_count > 0 else ValidationSeverity.INFO,
        dup_count == 0,
        f"Found {dup_count} duplicate row(s)",
        details={"duplicate_count": dup_count}))
    missing_counts = df.isna().sum()
    total_missing = int(missing_counts.sum())
    report.results.append(ValidationResult(
        "no_critical_missing",
        ValidationSeverity.WARNING if total_missing > 0 else ValidationSeverity.INFO,
        total_missing == 0,
        f"Found {total_missing} missing value(s)",
        details={"missing_by_column": missing_counts.to_dict()}))
    return report

def run_system_qa(db_paths: list[str | Path] | None = None) -> QAReport:
    report = QAReport()
    try:
        import geneai
        report.results.append(ValidationResult(
            "geneai_import", ValidationSeverity.INFO, True,
            "geneai package imports successfully"))
    except ImportError as exc:
        report.results.append(ValidationResult(
            "geneai_import", ValidationSeverity.CRITICAL, False,
            f"geneai package import failed: {exc}"))
    if db_paths:
        for db_path in db_paths:
            db_report = validate_database_integrity(db_path)
            report.results.extend(db_report.results)
    try:
        from geneai.config import DATABASE_PATH, MAX_UPLOAD_BYTES
        report.results.append(ValidationResult(
            "config_loaded", ValidationSeverity.INFO, True,
            f"Configuration loaded: DB={DATABASE_PATH}, MaxUpload={MAX_UPLOAD_BYTES} bytes"))
    except ImportError as exc:
        report.results.append(ValidationResult(
            "config_loaded", ValidationSeverity.ERROR, False,
            f"Configuration import failed: {exc}"))
    return report

def log_qa_report(report: QAReport, logger_name: str = "geneai.qa") -> None:
    qa_logger = logging.getLogger(logger_name)
    qa_logger.info("QA Report: %s checks, passed=%s",
                   report.to_dict()["total_checks"], report.passed)
    for result in report.errors:
        qa_logger.error("QA FAIL [%s]: %s", result.check_name, result.message)
    for result in report.warnings:
        qa_logger.warning("QA WARN [%s]: %s", result.check_name, result.message)