"""Sequential Phase 4.3 target evidence workflow using existing Phase 4.2/4.4 results."""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from geneai.database.target_schema import store_target_assessment
from geneai.drug_discovery import api_clients
from geneai.drug_discovery.ppi_analysis import summarize_ppi_network
from geneai.drug_discovery.target_identification import (
    build_ml_feature_rows,
    build_target_feature_rows,
    normalize_target_weights,
    rank_target_evidence,
)

logger = logging.getLogger(__name__)
_GENE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")


@dataclass(frozen=True)
class TargetIdentificationRequest:
    """Options for one target-ranking run based on a retrieved Phase 4.2 result."""

    disease_analysis_result: dict[str, Any]
    network_type: str = "functional"
    required_score: int = 400
    weights: dict[str, float] = field(default_factory=dict)


def run_target_identification_agent(
    request: TargetIdentificationRequest,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Run source-based target ranking; STRING failure does not discard gene evidence."""
    disease_result = request.disease_analysis_result
    disease = disease_result.get("disease") if isinstance(disease_result, dict) else None
    targets = disease_result.get("genes") if isinstance(disease_result, dict) else None
    if not isinstance(disease, dict) or not disease.get("disease_id") or not isinstance(targets, list):
        raise ValueError("Run Drug Discovery · Disease Analysis first; a retrieved disease and gene list are required.")
    if request.network_type not in {"functional", "physical"}:
        raise ValueError("STRING network type must be functional or physical.")
    if isinstance(request.required_score, bool) or not isinstance(request.required_score, int) or not 0 <= request.required_score <= 1000:
        raise ValueError("STRING required score must be an integer from 0 to 1000.")
    weights = normalize_target_weights(request.weights)
    valid_symbols = list(dict.fromkeys(
        str(item.get("gene_symbol") or "").strip().upper()
        for item in targets
        if isinstance(item, dict) and item.get("gene_symbol")
    ))
    valid_symbols = [symbol for symbol in valid_symbols if _GENE_SYMBOL.fullmatch(symbol)]
    symbols = valid_symbols[:20]
    if not symbols:
        raise ValueError("The current disease analysis contains no valid gene symbols to assess.")
    limitations = [
        "This workflow reuses the current Phase 4.2 disease-analysis snapshot; rerun Disease Analysis to refresh its evidence.",
        "The target research-priority index is a transparent weighted summary of available evidence, not druggability probability, clinical success, or a validated target score.",
        "Reactome enrichment is disease-gene-set level in the existing API response; it is not treated as per-gene pathway support.",
        "Expression, known drug/ligand evidence, and experimentally validated target accessibility are unavailable from this workflow and are not imputed.",
        "VCF rows are shown only when the source preview contains matching annotations; the engine does not infer variant pathogenicity or functional effect.",
    ]
    source_status = list(disease_result.get("data_sources", []))
    ppi_edges: list[dict[str, Any]] = []
    if len(symbols) >= 2:
        try:
            ppi_edges = api_clients.fetch_string_interactions(
                symbols,
                network_type=request.network_type,
                required_score=request.required_score,
                limit=250,
            )
            source_status.append({
                "source": f"STRING {api_clients.STRING_DATABASE_VERSION}",
                "status": "available",
                "record_count": len(ppi_edges),
                "version": api_clients.STRING_DATABASE_VERSION,
                "url": "https://string-db.org/",
                "network_type": request.network_type,
            })
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("STRING network retrieval unavailable: %s", exc)
            source_status.append({
                "source": f"STRING {api_clients.STRING_DATABASE_VERSION}",
                "status": "unavailable",
                "record_count": 0,
                "version": api_clients.STRING_DATABASE_VERSION,
                "error": str(exc),
            })
            limitations.append(f"STRING network retrieval was unavailable: {exc}. Ranking continues with the other retrieved evidence.")
    else:
        source_status.append({
            "source": f"STRING {api_clients.STRING_DATABASE_VERSION}",
            "status": "not run",
            "record_count": 0,
            "reason": "At least two disease-associated gene symbols are required for this network request.",
        })

    network = summarize_ppi_network(ppi_edges, symbols)
    feature_rows = build_target_feature_rows(disease_result, network)
    ranked, normalized_weights = rank_target_evidence(feature_rows, weights)
    ml_features = build_ml_feature_rows(ranked)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {
        "schema_version": "4.3.0",
        "analysis_id": str(uuid4()),
        "retrieved_at": retrieved_at,
        "disease_analysis_id": disease_result.get("analysis_id"),
        "disease_analysis_retrieved_at": disease_result.get("retrieved_at"),
        "disease": disease,
        "targets": ranked,
        "target_feature_rows": ml_features,
        "ppi_network": network,
        "pathways": disease_result.get("pathways") or {"pathways": [], "warning": "No Phase 4.2 pathway data was available."},
        "go_annotations": disease_result.get("go_annotations", []),
        "mutations_from_vcf_preview": disease_result.get("mutations", []),
        "proteins": disease_result.get("proteins", []),
        "publications": disease_result.get("publications", []),
        "weights": normalized_weights,
        "priority_method": "Weighted mean of available Open Targets disease-association/genetic/literature scores and STRING network association support; missing domains are excluded and remaining weights renormalized. Scores are a research shortlist index only.",
        "data_sources": source_status,
        "source_versions": {
            **(disease_result.get("source_versions") or {}),
            "STRING": api_clients.STRING_DATABASE_VERSION,
        },
        "limitations": limitations,
        "research_only_disclaimer": "Research use only. The output is not a clinical diagnosis, treatment recommendation, experimentally validated druggability assessment, or probability of clinical success.",
        "storage": {"status": "not requested"},
    }
    if len(valid_symbols) > len(symbols):
        result["limitations"].append("STRING network input was capped at the first 20 valid disease-associated gene symbols.")
    if persist:
        try:
            store_target_assessment(result)
            result["storage"] = {"status": "saved", "analysis_id": result["analysis_id"]}
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.exception("Could not save target assessment %s", result["analysis_id"])
            result["storage"] = {"status": "unavailable", "error": str(exc)}
            result["limitations"].append("Target-assessment output remains available in this session but could not be saved to SQLite.")
    return result
