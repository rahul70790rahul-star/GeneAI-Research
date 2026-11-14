"""NCBI Entrez API client for GeneAI Research."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_RATE_LIMIT_SECONDS = 0.34
_last_request_time = 0.0

_EMAIL = "geneai.research@example.com"
_TOOL = "GeneAIResearch"


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _ncbi_request(
    method: str,
    url: str,
    *,
    timeout: int = 30,
    expect_xml: bool = False,
    **kwargs: Any,
) -> tuple[requests.Response, Any]:
    _rate_limit()
    headers = {"User-Agent": f"{_TOOL}/0.2 (mailto:{_EMAIL})"}
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise api_clients.DataSourceError(f"NCBI request failed: {exc}") from exc

    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"NCBI server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"NCBI HTTP {response.status_code}: {exc}") from exc

    if expect_xml:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("NCBI returned invalid JSON") from exc
    return response, payload


def _parse_gene_summary(xml_text: str) -> dict[str, Any]:
    """Parse gene summary from XML."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    docsum = root.find(".//DocumentSummary")
    if docsum is None:
        return {}
    return {
        "gene_id": docsum.findtext("Id"),
        "symbol": docsum.findtext("Name"),
        "description": docsum.findtext("Description"),
        "summary": docsum.findtext("Summary"),
        "chromosome": docsum.findtext("Chromosome"),
        "map_location": docsum.findtext("MapLocation"),
        "gene_type": docsum.findtext("TypeOfGene"),
        "symbol_from_nomenclature": docsum.findtext("SymbolFromNomenclature"),
        "full_name_from_nomenclature": docsum.findtext("FullNameFromNomenclature"),
        "nomenclature_status": docsum.findtext("NomenclatureStatus"),
        "other_aliases": docsum.findtext("OtherAliases"),
        "source": "NCBI Gene",
    }


def _parse_pubmed_summary(xml_text: str) -> list[dict[str, Any]]:
    """Parse PubMed summaries from XML."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    results = []
    for docsum in root.findall(".//DocumentSummary"):
        results.append({
            "pubmed_id": docsum.findtext("Id"),
            "title": docsum.findtext("Title"),
            "authors": [a.text for a in docsum.findall(".//Author/Name") if a.text],
            "journal": docsum.findtext("FullJournalName"),
            "pub_date": docsum.findtext("PubDate"),
            "abstract": docsum.findtext("AbstractText"),
            "doi": docsum.findtext("DOI"),
            "source": "PubMed",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def search_gene(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search NCBI Gene database."""
    query = query.strip()
    if not query or len(query) > 300:
        raise ValueError("Search query must be 1-300 characters")
    url = f"{NCBI_BASE}/esearch.fcgi"
    params = {
        "db": "gene",
        "term": query,
        "retmax": min(max(1, limit), 100),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    id_list = payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []
    return fetch_gene_summaries(id_list)


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_gene_summaries(gene_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch gene summaries by IDs."""
    if not gene_ids:
        return []
    url = f"{NCBI_BASE}/esummary.fcgi"
    params = {
        "db": "gene",
        "id": ",".join(gene_ids[:100]),
        "retmode": "xml",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, xml_text = _ncbi_request("GET", url, params=params, expect_xml=True)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    results = []
    for docsum in root.findall(".//DocumentSummary"):
        results.append(_parse_gene_summary(ET.tostring(docsum, encoding="unicode")))
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_gene_by_symbol(symbol: str, organism: str = "human") -> list[dict[str, Any]]:
    """Search gene by official symbol."""
    symbol = symbol.strip()
    if not symbol or len(symbol) > 100:
        raise ValueError("Gene symbol must be 1-100 characters")
    query = f"{symbol}[Gene Name] AND {organism}[Organism]"
    return search_gene(query, limit=20)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_gene_by_id(gene_id: str) -> dict[str, Any] | None:
    """Get gene by NCBI Gene ID."""
    gene_id = gene_id.strip()
    if not gene_id.isdigit():
        raise ValueError("Gene ID must be numeric")
    results = fetch_gene_summaries([gene_id])
    return results[0] if results else None


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_pubmed(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search PubMed database."""
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError("Search query must be 1-500 characters")
    url = f"{NCBI_PUBMED_BASE}/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": min(max(1, limit), 100),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    id_list = payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []
    return fetch_pubmed_summaries(id_list)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def fetch_pubmed_summaries(pubmed_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch PubMed summaries by IDs."""
    if not pubmed_ids:
        return []
    url = f"{NCBI_PUBMED_BASE}/esummary.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pubmed_ids[:100]),
        "retmode": "xml",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, xml_text = _ncbi_request("GET", url, params=params, expect_xml=True)
    return _parse_pubmed_summary(xml_text)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_gene_publications(gene_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get publications associated with a gene."""
    gene_id = gene_id.strip()
    if not gene_id.isdigit():
        raise ValueError("Gene ID must be numeric")
    query = f"{gene_id}[Gene ID]"
    return search_pubmed(query, limit=limit)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_protein(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search NCBI Protein database."""
    query = query.strip()
    if not query or len(query) > 300:
        raise ValueError("Search query must be 1-300 characters")
    url = f"{NCBI_BASE}/esearch.fcgi"
    params = {
        "db": "protein",
        "term": query,
        "retmax": min(max(1, limit), 100),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    id_list = payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []
    return fetch_protein_summaries(id_list)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def fetch_protein_summaries(protein_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch protein summaries by IDs."""
    if not protein_ids:
        return []
    url = f"{NCBI_BASE}/esummary.fcgi"
    params = {
        "db": "protein",
        "id": ",".join(protein_ids[:100]),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    results = []
    for uid, docsum in payload.get("result", {}).items():
        if uid == "uids":
            continue
        results.append({
            "protein_id": uid,
            "title": docsum.get("title"),
            "organism": docsum.get("organism"),
            "length": docsum.get("length"),
            "source": "NCBI Protein",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_nucleotide(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search NCBI Nucleotide database."""
    query = query.strip()
    if not query or len(query) > 300:
        raise ValueError("Search query must be 1-300 characters")
    url = f"{NCBI_BASE}/esearch.fcgi"
    params = {
        "db": "nucleotide",
        "term": query,
        "retmax": min(max(1, limit), 100),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    id_list = payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []
    return fetch_nucleotide_summaries(id_list)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def fetch_nucleotide_summaries(nucleotide_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch nucleotide summaries by IDs."""
    if not nucleotide_ids:
        return []
    url = f"{NCBI_BASE}/esummary.fcgi"
    params = {
        "db": "nucleotide",
        "id": ",".join(nucleotide_ids[:100]),
        "retmode": "json",
        "email": _EMAIL,
        "tool": _TOOL,
    }
    _, payload = _ncbi_request("GET", url, params=params)
    results = []
    for uid, docsum in payload.get("result", {}).items():
        if uid == "uids":
            continue
        results.append({
            "nucleotide_id": uid,
            "title": docsum.get("title"),
            "organism": docsum.get("organism"),
            "length": docsum.get("length"),
            "source": "NCBI Nucleotide",
        })
    return results