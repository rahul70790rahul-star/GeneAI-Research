"""DGIdb (Drug Gene Interaction Database) API client for GeneAI Research."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

DGIDB_BASE = "https://dgidb.org/api/v2"
_RATE_LIMIT_SECONDS = 0.5
_last_request_time = 0.0


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _dgidb_request(
    method: str,
    url: str,
    *,
    timeout: int = 30,
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
        raise api_clients.DataSourceError(f"DGIdb request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("DGIdb record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"DGIdb server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"DGIdb HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("DGIdb returned invalid JSON") from exc
    return response, payload


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_dgidb_genes(genes: list[str], limit: int = 50) -> list[dict[str, Any]]:
    """Search DGIdb for gene-drug interactions."""
    if not genes:
        return []
    clean_genes = [g.strip().upper() for g in genes if g.strip()][:20]
    if not clean_genes:
        return []

    gene_param = ",".join(clean_genes)
    url = f"{DGIDB_BASE}/interactions.json"
    params = {
        "genes": gene_param,
        "limit": min(max(1, limit), 500),
    }
    try:
        _, payload = _dgidb_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []

    interactions = payload.get("matchedTerms", []) if isinstance(payload, dict) else []
    results = []
    for term in interactions:
        if not isinstance(term, dict):
            continue
        for interaction in term.get("interactions", []):
            if not isinstance(interaction, dict):
                continue
            drug = interaction.get("drugName") or interaction.get("drugConceptId")
            results.append({
                "gene": term.get("searchTerm"),
                "drug_name": drug,
                "drug_concept_id": interaction.get("drugConceptId"),
                "interaction_score": interaction.get("score"),
                "interaction_types": interaction.get("interactionTypes", []),
                "sources": interaction.get("sources", []),
                "pmids": interaction.get("pmids", []),
                "source": "DGIdb",
                "source_url": f"https://dgidb.org/search?query={drug}",
            })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_dgidb_drug(drug_name: str) -> dict[str, Any] | None:
    """Get drug information from DGIdb."""
    drug_name = drug_name.strip()
    if not drug_name:
        return None

    url = f"{DGIDB_BASE}/interactions.json"
    params = {"genes": "", "drugs": drug_name, "limit": 100}
    try:
        _, payload = _dgidb_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return None

    interactions = payload.get("matchedTerms", []) if isinstance(payload, dict) else []
    if not interactions:
        return None

    drug_info = interactions[0]
    return {
        "drug_name": drug_info.get("searchTerm"),
        "drug_concept_id": drug_info.get("drugConceptId"),
        "interactions": drug_info.get("interactions", []),
        "source": "DGIdb",
        "source_url": f"https://dgidb.org/search?query={drug_name}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_dgidb_categories() -> list[dict[str, Any]]:
    """Get DGIdb interaction categories."""
    url = f"{DGIDB_BASE}/categories.json"
    try:
        _, payload = _dgidb_request("GET", url)
    except api_clients.DataSourceError:
        return []
    categories = payload.get("categories", []) if isinstance(payload, dict) else []
    return [{"name": c.get("name"), "description": c.get("description")} for c in categories if isinstance(c, dict)]


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_dgidb_sources() -> list[dict[str, Any]]:
    """Get DGIdb data sources."""
    url = f"{DGIDB_BASE}/sources.json"
    try:
        _, payload = _dgidb_request("GET", url)
    except api_clients.DataSourceError:
        return []
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    return [{"name": s.get("sourceName"), "description": s.get("description"), "url": s.get("sourceUrl")} for s in sources if isinstance(s, dict)]