"""Disease Analysis Agent: serial retrieval, normalization, and provenance."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from geneai.database.disease_schema import store_disease_analysis
from geneai.drug_discovery.disease_analysis import analyze_disease

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiseaseAnalysisRequest:
    """Validated user inputs for one sequential disease research run."""

    disease_id: str
    disease_category: str = "Not specified"
    gene_identifiers: str = ""
    mutation_id: str = ""
    protein_id: str = ""
    research_keywords: str = ""
    target_limit: int = 20
    priority_weights: dict[str, float] = field(default_factory=dict)
    vcf_preview: list[dict[str, Any]] = field(default_factory=list)


def run_disease_analysis_agent(
    request: DiseaseAnalysisRequest,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Run a single disease analysis; return evidence even if SQLite is unavailable."""
    result = analyze_disease(
        request.disease_id,
        disease_category=request.disease_category,
        gene_identifiers=request.gene_identifiers,
        mutation_id=request.mutation_id,
        protein_id=request.protein_id,
        research_keywords=request.research_keywords,
        vcf_preview=request.vcf_preview,
        target_limit=request.target_limit,
        priority_weights=request.priority_weights or None,
    )
    if not persist:
        result["storage"] = {"status": "not requested"}
        return result
    try:
        stored_id = store_disease_analysis(result)
        result["storage"] = {"status": "saved", "analysis_id": stored_id}
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.exception("Could not save disease analysis %s", result.get("analysis_id"))
        result["storage"] = {"status": "unavailable", "error": str(exc)}
        result.setdefault("limitations", []).append(
            "This analysis could not be persisted to the local SQLite database."
        )
    return result
