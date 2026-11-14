"""Literature API clients for PubMed, Europe PMC, Crossref, and OpenAlex."""
from __future__ import annotations

import logging
import re
import time
import threading
from typing import Any
from urllib.parse import urlparse

import requests

from geneai.drug_discovery.cache import ttl_cache
from geneai.config import PUBMED_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
CROSSREF_BASE = "https://api.crossref.org"
OPENALEX_BASE = "https://api.openalex.org"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_RATE_INTERVALS = {
    "eutils.ncbi.nlm.nih.gov": 0.36,
    "www.ebi.ac.uk": 0.15,
    "api.crossref.org": 0.1,
    "api.openalex.org": 0.1,
}
_rate_lock = threading.Lock()
_last_request_at: dict[str, float] = {}


class LiteratureSourceError(RuntimeError):
    """A literature data source returned an unusable response."""


def _rate_limit(host: str) -> None:
    interval = _RATE_INTERVALS.get(host, 0.0)
    if not interval:
        return
    with _rate_lock:
        now = time.monotonic()
        wait = interval - (now - _last_request_at.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_request_at[host] = time.monotonic()


def _request(
    method: str,
    url: str,
    *,
    timeout: int = PUBMED_TIMEOUT_SECONDS,
    expect_json: bool = True,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
    **kwargs: Any,
) -> tuple[requests.Response, Any]:
    """Request with bounded retries, throttling, and validation."""
    host = urlparse(url).hostname or ""
    request_headers = {
        "User-Agent": "GeneAIResearch/0.3 (literature analysis; contact not configured)",
        **(headers or {}),
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        _rate_limit(host)
        try:
            response = requests.request(
                method,
                url,
                headers=request_headers,
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
                continue
            raise LiteratureSourceError(f"Request to {host} failed: {exc}") from exc

        if response.status_code in _RETRY_STATUS and attempt + 1 < attempts:
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(5.0, max(0.0, float(retry_after)))
            except ValueError:
                delay = 0.5 * (2**attempt)
            time.sleep(delay)
            continue
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text[:240].replace("\n", " ")
            raise LiteratureSourceError(
                f"{host} returned HTTP {response.status_code}: {body or response.reason}"
            ) from exc
        if not expect_json:
            return response, response.text
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise LiteratureSourceError(f"{host} returned invalid JSON.") from exc
        if not isinstance(payload, (dict, list)):
            raise LiteratureSourceError(f"{host} returned an unexpected JSON value.")
        return response, payload

    raise LiteratureSourceError(f"Request to {host} failed: {last_error or 'retry limit reached'}")


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_europe_pmc(
    query: str,
    limit: int = 20,
    result_type: str = "lite",
) -> list[dict[str, Any]]:
    """Search Europe PMC for papers."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    _, payload = _request(
        "GET",
        f"{EUROPE_PMC_BASE}/search",
        params={
            "query": query,
            "pageSize": limit,
            "resultType": result_type,
            "format": "json",
        },
    )

    hit_list = payload.get("hitList", {}) if isinstance(payload, dict) else {}
    hits = hit_list.get("hit", []) if isinstance(hit_list, dict) else []
    if not isinstance(hits, list):
        raise LiteratureSourceError("Europe PMC returned invalid hit list.")

    papers = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        pmid = hit.get("pmid")
        pmcid = hit.get("pmcid")
        doi = hit.get("doi")
        papers.append({
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "title": hit.get("title", "").strip(),
            "abstract": hit.get("abstractText", "").strip() if hit.get("abstractText") else None,
            "authors": hit.get("authorString", "").strip() if hit.get("authorString") else None,
            "journal": hit.get("journalTitle", "").strip() if hit.get("journalTitle") else None,
            "year": hit.get("pubYear", "").strip() if hit.get("pubYear") else None,
            "source": "Europe PMC",
            "url": f"https://europepmc.org/article/MED/{pmid}" if pmid else (
                f"https://europepmc.org/article/PMC/{pmcid}" if pmcid else (
                    f"https://doi.org/{doi}" if doi else ""
                )
            ),
            "is_open_access": hit.get("isOpenAccess", "N") == "Y",
        })
    return papers


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_europe_pmc_fulltext(pmcid: str) -> str | None:
    """Retrieve full text from Europe PMC (open access only)."""
    pmcid = pmcid.strip().upper()
    if not re.match(r"^PMC\d+$", pmcid):
        raise ValueError("Invalid PMCID format.")
    _, text = _request(
        "GET",
        f"{EUROPE_PMC_BASE}/{pmcid}/fullTextXML",
        expect_json=False,
        headers={"Accept": "application/xml"},
    )
    return text if isinstance(text, str) and text.strip() else None


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_crossref(
    query: str,
    limit: int = 20,
    filter_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Search Crossref for papers."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    params = {"query": query, "rows": limit}
    if filter_params:
        params["filter"] = ",".join(f"{k}:{v}" for k, v in filter_params.items())

    _, payload = _request(
        "GET",
        f"{CROSSREF_BASE}/works",
        params=params,
    )

    items = payload.get("message", {}).get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise LiteratureSourceError("Crossref returned invalid items list.")

    papers = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = item.get("DOI", "")
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""
        authors = []
        for author in item.get("author", []) if isinstance(item.get("author"), list) else []:
            given = author.get("given", "")
            family = author.get("family", "")
            if given or family:
                authors.append(f"{given} {family}".strip())
        journal = item.get("container-title", [""])[0] if item.get("container-title") else ""
        year = None
        if "published-print" in item and isinstance(item["published-print"], dict):
            date_parts = item["published-print"].get("date-parts", [[]])
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
        elif "published-online" in item and isinstance(item["published-online"], dict):
            date_parts = item["published-online"].get("date-parts", [[]])
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
        papers.append({
            "doi": doi,
            "title": title.strip(),
            "authors": ", ".join(authors) if authors else None,
            "journal": journal.strip(),
            "year": year,
            "source": "Crossref",
            "url": f"https://doi.org/{doi}" if doi else "",
            "is_open_access": item.get("is-referenced-by-count", 0) > 0,
            "type": item.get("type", ""),
            "citation_count": item.get("is-referenced-by-count", 0),
        })
    return papers


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_openalex(
    query: str,
    limit: int = 20,
    filter_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Search OpenAlex for papers."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if not 1 <= limit <= 200:
        raise ValueError("Limit must be between 1 and 200.")

    params = {"search": query, "per-page": limit}
    if filter_params:
        for k, v in filter_params.items():
            params[f"filter[{k}]"] = v

    _, payload = _request(
        "GET",
        f"{OPENALEX_BASE}/works",
        params=params,
    )

    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(results, list):
        raise LiteratureSourceError("OpenAlex returned invalid results list.")

    papers = []
    for item in results:
        if not isinstance(item, dict):
            continue
        doi = item.get("doi", "")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[16:]
        title = item.get("display_name", "")
        authors = []
        for auth in item.get("authorships", []) if isinstance(item.get("authorships"), list) else []:
            author = auth.get("author", {}) if isinstance(auth, dict) else {}
            name = author.get("display_name", "")
            if name:
                authors.append(name)
        journal = ""
        host_venue = item.get("host_venue", {}) if isinstance(item.get("host_venue"), dict) else {}
        if host_venue:
            journal = host_venue.get("display_name", "")
        year = item.get("publication_year")
        papers.append({
            "doi": doi,
            "title": title.strip(),
            "authors": ", ".join(authors) if authors else None,
            "journal": journal.strip(),
            "year": str(year) if year else None,
            "source": "OpenAlex",
            "url": item.get("id", ""),
            "is_open_access": item.get("open_access", {}).get("is_oa", False) if isinstance(item.get("open_access"), dict) else False,
            "open_access_url": item.get("open_access", {}).get("oa_url", "") if isinstance(item.get("open_access"), dict) else "",
            "type": item.get("type", ""),
            "citation_count": item.get("cited_by_count", 0),
            "concepts": [c.get("display_name", "") for c in item.get("concepts", []) if isinstance(c, dict) and c.get("display_name")],
        })
    return papers


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_openalex_work(openalex_id: str) -> dict[str, Any] | None:
    """Get detailed work from OpenAlex."""
    openalex_id = openalex_id.strip()
    if not openalex_id.startswith("W"):
        raise ValueError("Invalid OpenAlex work ID.")
    _, payload = _request(
        "GET",
        f"{OPENALEX_BASE}/works/{openalex_id}",
    )
    item = payload if isinstance(payload, dict) else {}
    if not item:
        return None
    doi = item.get("doi", "")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[16:]
    title = item.get("display_name", "")
    authors = []
    for auth in item.get("authorships", []) if isinstance(item.get("authorships"), list) else []:
        author = auth.get("author", {}) if isinstance(auth, dict) else {}
        name = author.get("display_name", "")
        if name:
            authors.append(name)
    journal = ""
    host_venue = item.get("host_venue", {}) if isinstance(item.get("host_venue"), dict) else {}
    if host_venue:
        journal = host_venue.get("display_name", "")
    year = item.get("publication_year")
    return {
        "doi": doi,
        "openalex_id": item.get("id", ""),
        "title": title.strip(),
        "authors": ", ".join(authors) if authors else None,
        "journal": journal.strip(),
        "year": str(year) if year else None,
        "source": "OpenAlex",
        "url": item.get("id", ""),
        "is_open_access": item.get("open_access", {}).get("is_oa", False) if isinstance(item.get("open_access"), dict) else False,
        "open_access_url": item.get("open_access", {}).get("oa_url", "") if isinstance(item.get("open_access"), dict) else "",
        "type": item.get("type", ""),
        "citation_count": item.get("cited_by_count", 0),
        "concepts": [c.get("display_name", "") for c in item.get("concepts", []) if isinstance(c, dict) and c.get("display_name")],
        "referenced_works": item.get("referenced_works", []),
        "related_works": item.get("related_works", []),
    }


def search_all_sources(
    query: str,
    limit: int = 20,
    sources: list[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Search all available literature sources."""
    sources = sources or ["pubmed", "europe_pmc", "crossref", "openalex"]
    results = {}

    filter_params = {}
    if year_from:
        filter_params["from-pub-date" if "crossref" in sources else "publication_year"] = str(year_from)
    if year_to:
        filter_params["until-pub-date" if "crossref" in sources else "publication_year"] = str(year_to)

    if "pubmed" in sources:
        try:
            from geneai.research import search_pubmed
            results["pubmed"] = search_pubmed(query, min(limit, 100))
        except Exception as e:
            logger.warning("PubMed search failed: %s", e)
            results["pubmed"] = []

    if "europe_pmc" in sources:
        try:
            results["europe_pmc"] = search_europe_pmc(query, min(limit, 100))
        except Exception as e:
            logger.warning("Europe PMC search failed: %s", e)
            results["europe_pmc"] = []

    if "crossref" in sources:
        try:
            results["crossref"] = search_crossref(query, min(limit, 100), filter_params if filter_params else None)
        except Exception as e:
            logger.warning("Crossref search failed: %s", e)
            results["crossref"] = []

    if "openalex" in sources:
        try:
            results["openalex"] = search_openalex(query, min(limit, 200), filter_params if filter_params else None)
        except Exception as e:
            logger.warning("OpenAlex search failed: %s", e)
            results["openalex"] = []

    return results