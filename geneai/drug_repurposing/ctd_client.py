"""CTD (Comparative Toxicogenomics Database) API client for GeneAI Research."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

CTD_BASE = "https://ctdbase.org/tools/batchQuery"
CTD_API_BASE = "https://ctdbase.org/tools/api"
_RATE_LIMIT_SECONDS = 1.0
_last_request_time = 0.0


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _ctd_request(
    method: str,
    url: str,
    *,
    timeout: int = 60,
    expect_json: bool = True,
    **kwargs: Any,
) -> tuple[requests.Response, Any]:
    _rate_limit()
    headers = {
        "User-Agent": "GeneAIResearch/0.2 (scientific research client)",
        "Accept": "application/json",
    }
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise api_clients.DataSourceError(f"CTD request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("CTD record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"CTD server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"CTD HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        # CTD may return TSV or other formats
        raise api_clients.DataSourceError("CTD returned invalid JSON") from exc
    return response, payload


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_ctd_chemical_gene(chemical_name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search CTD for chemical-gene interactions."""
    chemical_name = chemical_name.strip()
    if not chemical_name:
        return []

    # CTD batch query for chemical-gene interactions
    url = f"{CTD_BASE}.go"
    params = {
        "inputType": "chemical",
        "inputTerms": chemical_name,
        "report": "chemical_gene_interactions",
        "format": "JSON",
    }
    try:
        _, payload = _ctd_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []

    results = []
    if isinstance(payload, list):
        for row in payload[:limit]:
            if not isinstance(row, dict):
                continue
            results.append({
                "chemical_name": row.get("ChemicalName"),
                "chemical_id": row.get("ChemicalID"),
                "gene_symbol": row.get("GeneSymbol"),
                "gene_id": row.get("GeneID"),
                "interaction": row.get("Interaction"),
                "interaction_actions": row.get("InteractionActions", "").split("|") if row.get("InteractionActions") else [],
                "organism": row.get("Organism"),
                "pubmed_ids": row.get("PubMedIDs", "").split("|") if row.get("PubMedIDs") else [],
                "source": "CTD",
                "source_url": f"https://ctdbase.org/detail.go?type=chem-gene-interaction&chem={row.get('ChemicalID')}&gene={row.get('GeneID')}",
            })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_ctd_disease_chemical(disease_name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search CTD for disease-chemical associations."""
    disease_name = disease_name.strip()
    if not disease_name:
        return []

    url = f"{CTD_BASE}.go"
    params = {
        "inputType": "disease",
        "inputTerms": disease_name,
        "report": "disease_chemicals",
        "format": "JSON",
    }
    try:
        _, payload = _ctd_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []

    results = []
    if isinstance(payload, list):
        for row in payload[:limit]:
            if not isinstance(row, dict):
                continue
            results.append({
                "disease_name": row.get("DiseaseName"),
                "disease_id": row.get("DiseaseID"),
                "chemical_name": row.get("ChemicalName"),
                "chemical_id": row.get("ChemicalID"),
                "inference_score": row.get("InferenceScore"),
                "direct_evidence": row.get("DirectEvidence"),
                "inference_gene_symbol": row.get("InferenceGeneSymbol"),
                "organism": row.get("Organism"),
                "pubmed_ids": row.get("PubMedIDs", "").split("|") if row.get("PubMedIDs") else [],
                "source": "CTD",
                "source_url": f"https://ctdbase.org/detail.go?type=disease-chemical&disease={row.get('DiseaseID')}&chem={row.get('ChemicalID')}",
            })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_ctd_gene_disease(gene_symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search CTD for gene-disease associations."""
    gene_symbol = gene_symbol.strip().upper()
    if not gene_symbol:
        return []

    url = f"{CTD_BASE}.go"
    params = {
        "inputType": "gene",
        "inputTerms": gene_symbol,
        "report": "gene_diseases",
        "format": "JSON",
    }
    try:
        _, payload = _ctd_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []

    results = []
    if isinstance(payload, list):
        for row in payload[:limit]:
            if not isinstance(row, dict):
                continue
            results.append({
                "gene_symbol": row.get("GeneSymbol"),
                "gene_id": row.get("GeneID"),
                "disease_name": row.get("DiseaseName"),
                "disease_id": row.get("DiseaseID"),
                "inference_score": row.get("InferenceScore"),
                "direct_evidence": row.get("DirectEvidence"),
                "inference_chemical_name": row.get("InferenceChemicalName"),
                "organism": row.get("Organism"),
                "pubmed_ids": row.get("PubMedIDs", "").split("|") if row.get("PubMedIDs") else [],
                "source": "CTD",
                "source_url": f"https://ctdbase.org/detail.go?type=gene-disease&gene={row.get('GeneID')}&disease={row.get('DiseaseID')}",
            })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_ctd_pathways(chemical_name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search CTD for chemical-pathway associations."""
    chemical_name = chemical_name.strip()
    if not chemical_name:
        return []

    url = f"{CTD_BASE}.go"
    params = {
        "inputType": "chemical",
        "inputTerms": chemical_name,
        "report": "chemical_pathways",
        "format": "JSON",
    }
    try:
        _, payload = _ctd_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []

    results = []
    if isinstance(payload, list):
        for row in payload[:limit]:
            if not isinstance(row, dict):
                continue
            results.append({
                "chemical_name": row.get("ChemicalName"),
                "chemical_id": row.get("ChemicalID"),
                "pathway_name": row.get("PathwayName"),
                "pathway_id": row.get("PathwayID"),
                "source": "CTD",
                "source_url": f"https://ctdbase.org/detail.go?type=chemical-pathway&chem={row.get('ChemicalID')}&pathway={row.get('PathwayID')}",
            })
    return results