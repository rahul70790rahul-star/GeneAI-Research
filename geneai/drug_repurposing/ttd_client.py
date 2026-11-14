"""Therapeutic Target Database (TTD) API client for GeneAI Research."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

# TTD is not openly accessible via API without license, so we'll use web scraping approach
# or provide a placeholder for when licensed access is available
TTD_BASE = "https://db.idrblab.net/ttd"
_RATE_LIMIT_SECONDS = 2.0
_last_request_time = 0.0


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _ttd_request(
    method: str,
    url: str,
    *,
    timeout: int = 30,
    expect_json: bool = False,
    **kwargs: Any,
) -> tuple[requests.Response, Any]:
    _rate_limit()
    headers = {
        "User-Agent": "GeneAIResearch/0.2 (scientific research client)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise api_clients.DataSourceError(f"TTD request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("TTD record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"TTD server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"TTD HTTP {response.status_code}: {exc}") from exc

    if expect_json:
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise api_clients.DataSourceError("TTD returned invalid JSON") from exc
        return response, payload
    return response, response.text


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_ttd_target(query: str) -> list[dict[str, Any]]:
    """Search TTD for targets (requires licensed access - placeholder)."""
    # TTD requires licensed access for full API
    # This is a placeholder that returns empty results
    # When licensed access is available, implement actual API calls
    logger.info("TTD search requested for '%s' - licensed access required", query)
    return []


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_ttd_drug(query: str) -> list[dict[str, Any]]:
    """Search TTD for drugs (requires licensed access - placeholder)."""
    logger.info("TTD drug search requested for '%s' - licensed access required", query)
    return []


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_ttd_target_drugs(target_id: str) -> list[dict[str, Any]]:
    """Get drugs for a TTD target (requires licensed access - placeholder)."""
    logger.info("TTD target drugs requested for '%s' - licensed access required", target_id)
    return []


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_ttd_drug_targets(drug_id: str) -> list[dict[str, Any]]:
    """Get targets for a TTD drug (requires licensed access - placeholder)."""
    logger.info("TTD drug targets requested for '%s' - licensed access required", drug_id)
    return []


def ttd_access_status() -> dict[str, str]:
    """Check TTD access status."""
    return {
        "status": "not_available; TTD requires licensed access for API queries",
        "source": "Therapeutic Target Database (TTD)",
        "url": "https://db.idrblab.net/ttd/",
        "note": "Public website available but API requires subscription",
    }