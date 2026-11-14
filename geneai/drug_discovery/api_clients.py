"""Bounded clients for public disease, gene, protein, pathway, and literature APIs."""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import Any

import requests

from geneai.drug_discovery.cache import ttl_cache
from geneai.utils import DataSourceError, RateLimiter
from geneai.utils.rate_limiter import apply_default_rate_limits
from geneai.utils.api_client_base import BaseAPIClient, APIClientConfig

OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ENSEMBL_REST = "https://rest.ensembl.org"
UNIPROT_REST = "https://rest.uniprot.org"
QUICKGO_REST = "https://www.ebi.ac.uk/QuickGO/services"
REACTOME_ANALYSIS = "https://reactome.org/AnalysisService"
RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
STRING_BASE_URL = "https://version-12-5.string-db.org"
STRING_DATABASE_VERSION = "12.5"

TIMEOUT_SECONDS = 20
MAX_DISEASE_QUERY_LENGTH = 160
MAX_TARGETS = 50
MAX_GENE_SYMBOLS = 50
_GENE_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_EXTERNAL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]{1,63}$")

# Create a shared client for common functionality
_opentargets_client = BaseAPIClient(APIClientConfig(
    base_url="https://api.platform.opentargets.org",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))

_ncbi_client = BaseAPIClient(APIClientConfig(
    base_url="https://eutils.ncbi.nlm.nih.gov",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))

_ensembl_client = BaseAPIClient(APIClientConfig(
    base_url="https://rest.ensembl.org",
    timeout=30,
    max_retries=2,
))

_uniprot_client = BaseAPIClient(APIClientConfig(
    base_url="https://rest.uniprot.org",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))

_quickgo_client = BaseAPIClient(APIClientConfig(
    base_url="https://www.ebi.ac.uk",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))

_reactome_client = BaseAPIClient(APIClientConfig(
    base_url="https://reactome.org",
    timeout=60,
    max_retries=2,
))

_rcsb_client = BaseAPIClient(APIClientConfig(
    base_url="https://search.rcsb.org",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))

_string_client = BaseAPIClient(APIClientConfig(
    base_url="https://version-12-5.string-db.org",
    timeout=30,
    max_retries=2,
))

_pubmed_client = BaseAPIClient(APIClientConfig(
    base_url="https://eutils.ncbi.nlm.nih.gov",
    timeout=TIMEOUT_SECONDS,
    max_retries=2,
))


# URL to client mapping for backward compatibility
_CLIENT_MAP = {
    "api.platform.opentargets.org": _opentargets_client,
    "eutils.ncbi.nlm.nih.gov": _ncbi_client,
    "rest.ensembl.org": _ensembl_client,
    "rest.uniprot.org": _uniprot_client,
    "www.ebi.ac.uk": _quickgo_client,
    "reactome.org": _reactome_client,
    "search.rcsb.org": _rcsb_client,
    "version-12-5.string-db.org": _string_client,
}


def _get_client_for_url(url: str) -> BaseAPIClient:
    """Get the appropriate client for a given URL."""
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""
    return _CLIENT_MAP.get(hostname, _ncbi_client)  # Default to NCBI client


def _request(
    method: str,
    url: str,
    *,
    timeout: int = TIMEOUT_SECONDS,
    expect_json: bool = True,
    headers: dict[str, str] | None = None,
    attempts: int = 2,
    **kwargs: Any,
) -> tuple[Any, Any]:
    """Backward-compatible request function using requests directly.
    
    This function maintains API compatibility with tests that mock _request.
    Returns tuple of (response_object, payload) to match original signature.
    """
    import requests
    from urllib.parse import urlparse
    
    # Create a response-like object
    class ResponseWrapper:
        def __init__(self, resp: requests.Response):
            self.headers = dict(resp.headers)
            self.status_code = resp.status_code
            self.text = resp.text
    
    last_error: Exception | None = None
    
    for attempt in range(attempts):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
            
            # Check for rate limiting
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else None
                except (ValueError, TypeError):
                    delay = None
                if attempt < attempts - 1:
                    import time
                    time.sleep(delay or 1.0)
                    continue
            
            # Check for authentication errors
            if resp.status_code in (401, 403):
                raise DataSourceError(
                    f"Authentication failed for {urlparse(url).hostname}",
                    source=urlparse(url).hostname,
                )
            
            # Check for client errors
            if 400 <= resp.status_code < 500:
                body = resp.text[:500] if resp.text else ""
                raise DataSourceError(
                    f"{urlparse(url).hostname} returned HTTP {resp.status_code}: {body}",
                    source=urlparse(url).hostname,
                    status_code=resp.status_code,
                    response_body=resp.text,
                )
            
            # Check for server errors
            if resp.status_code >= 500:
                body = resp.text[:500] if resp.text else ""
                if attempt < attempts - 1:
                    import time
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise DataSourceError(
                    f"{urlparse(url).hostname} server error {resp.status_code}: {body}",
                    source=urlparse(url).hostname,
                    status_code=resp.status_code,
                    response_body=resp.text,
                )
            
            # Parse response
            if not expect_json:
                return ResponseWrapper(resp), resp.text
            
            try:
                payload = resp.json()
            except (ValueError, requests.JSONDecodeError) as exc:
                raise DataSourceError(
                    f"{urlparse(url).hostname} returned invalid JSON: {exc}",
                    source=urlparse(url).hostname,
                    status_code=resp.status_code,
                    response_body=resp.text[:500],
                ) from exc
            
            return ResponseWrapper(resp), payload
            
        except requests.Timeout as exc:
            last_error = exc
            if attempt < attempts - 1:
                import time
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise DataSourceError(
                f"Request to {urlparse(url).hostname} failed: timed out after {attempts} attempts",
                source=urlparse(url).hostname,
            ) from exc
        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts - 1:
                import time
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise DataSourceError(
                f"Request to {urlparse(url).hostname} failed: {exc}",
                source=urlparse(url).hostname,
            ) from exc
        except DataSourceError:
            raise
    
    raise DataSourceError(
        f"Request to {urlparse(url).hostname} failed after {attempts} attempts: {last_error}",
        source=urlparse(url).hostname,
    ) from last_error


def _rate_limit(host: str) -> None:
    """Backward-compatible rate limit function for tests.
    
    This function maintains API compatibility with tests that call _rate_limit directly.
    It uses the shared RateLimiter utility.
    """
    RateLimiter.wait_if_needed(host)


def is_valid_external_id(value: str) -> bool:
    """Return whether a user-supplied stable source ID is safe to query."""
    return isinstance(value, str) and bool(_EXTERNAL_ID.fullmatch(value.strip()))


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _opentargets_client.post(
        "/api/v4/graphql",
        json={"query": query, "variables": variables or {}},
    )
    if not isinstance(payload, dict):
        raise DataSourceError("Open Targets returned an invalid GraphQL response.")
    if payload.get("errors"):
        first_error = payload["errors"][0]
        message = first_error.get("message", "GraphQL query failed") if isinstance(first_error, dict) else "GraphQL query failed"
        raise DataSourceError(f"Open Targets: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataSourceError("Open Targets response is missing the data object.")
    return data


@ttl_cache(ttl_seconds=21_600, max_entries=8)
def get_open_targets_metadata() -> dict[str, str]:
    query = """{ meta { apiVersion { x y z suffix } dataVersion { year month iteration } } }"""
    data = _graphql(query).get("meta") or {}
    api = data.get("apiVersion") or {}
    release = data.get("dataVersion") or {}
    api_version = ".".join(str(api.get(key)) for key in ("x", "y", "z") if api.get(key) is not None)
    data_version = ".".join(
        str(release.get(key)) for key in ("year", "month", "iteration") if release.get(key) is not None
    )
    return {"api_version": api_version or "not reported", "data_version": data_version or "not reported"}


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def search_open_targets_diseases(query_text: str, limit: int = 10) -> list[dict[str, Any]]:
    query_text = query_text.strip()
    if len(query_text) < 2 or len(query_text) > MAX_DISEASE_QUERY_LENGTH:
        raise ValueError(f"Disease search must be between 2 and {MAX_DISEASE_QUERY_LENGTH} characters.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Disease suggestion limit must be between 1 and 20.")
    query = """query DiseaseSearch($queryString: String!, $page: Pagination!) {
      search(queryString: $queryString, entityNames: [\"disease\"], page: $page) {
        total
        hits { id name entity category }
      }
    }"""
    data = _graphql(query, {"queryString": query_text, "page": {"index": 0, "size": limit}})
    result = data.get("search") or {}
    hits = result.get("hits", [])
    if not isinstance(hits, list):
        raise DataSourceError("Open Targets disease search had an invalid hits field.")
    diseases = []
    seen: set[str] = set()
    for hit in hits:
        if not isinstance(hit, dict) or hit.get("entity") != "disease":
            continue
        disease_id, name = hit.get("id"), hit.get("name")
        if not isinstance(disease_id, str) or not _EXTERNAL_ID.fullmatch(disease_id):
            continue
        if not isinstance(name, str) or not name.strip() or disease_id in seen:
            continue
        seen.add(disease_id)
        categories = hit.get("category", [])
        diseases.append(
            {
                "disease_id": disease_id,
                "name": name.strip(),
                "categories": [item for item in categories if isinstance(item, str)] if isinstance(categories, list) else [],
                "source": "Open Targets Platform",
                "url": f"https://platform.opentargets.org/disease/{disease_id}/associations",
            }
        )
    return diseases


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def get_open_targets_disease(disease_id: str, limit: int = 25) -> dict[str, Any] | None:
    disease_id = disease_id.strip()
    if not _EXTERNAL_ID.fullmatch(disease_id):
        raise ValueError("Enter a valid disease identifier from the selected database record.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TARGETS:
        raise ValueError(f"Target limit must be between 1 and {MAX_TARGETS}.")
    query = """query DiseaseTargets($diseaseId: String!, $page: Pagination!) {
      disease(efoId: $diseaseId) {
        id name description
        therapeuticAreas { id name }
        associatedTargets(page: $page) {
          count
          rows {
            target { id approvedSymbol approvedName biotype }
            score
            datatypeScores { id score }
            datasourceScores { id score }
          }
        }
      }
    }"""
    data = _graphql(query, {"diseaseId": disease_id, "page": {"index": 0, "size": limit}})
    disease = data.get("disease")
    if disease is None:
        return None
    if not isinstance(disease, dict) or not isinstance(disease.get("associatedTargets"), dict):
        raise DataSourceError("Open Targets returned an incomplete disease record.")
    rows = disease["associatedTargets"].get("rows", [])
    if not isinstance(rows, list):
        raise DataSourceError("Open Targets returned an invalid target list.")
    targets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        target = row.get("target") or {}
        symbol = target.get("approvedSymbol")
        if not isinstance(symbol, str) or not _GENE_SYMBOL.fullmatch(symbol):
            continue
        score = row.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
        datatype_scores = _normalize_scores(row.get("datatypeScores"))
        datasource_scores = _normalize_scores(row.get("datasourceScores"))
        targets.append(
            {
                "ensembl_gene_id": target.get("id"),
                "gene_symbol": symbol,
                "gene_name": target.get("approvedName") or symbol,
                "biotype": target.get("biotype"),
                "association_score": score if score is not None and 0 <= score <= 1 else None,
                "datatype_scores": datatype_scores,
                "datasource_scores": datasource_scores,
                "evidence_sources": sorted(datasource_scores),
                "source": "Open Targets Platform",
                "source_url": f"https://platform.opentargets.org/target/{target.get('id', '')}/associations",
            }
        )
    return {
        "disease_id": disease.get("id"),
        "name": disease.get("name"),
        "description": disease.get("description"),
        "therapeutic_areas": [item for item in disease.get("therapeuticAreas", []) if isinstance(item, dict)],
        "association_count": disease["associatedTargets"].get("count"),
        "targets": targets,
        "source": "Open Targets Platform",
        "source_url": f"https://platform.opentargets.org/disease/{disease_id}/associations",
    }


def _normalize_scores(values: Any) -> dict[str, float]:
    if not isinstance(values, list):
        return {}
    scores: dict[str, float] = {}
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        if 0 <= score <= 1:
            scores[item["id"]] = score
    return scores


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def fetch_ncbi_gene_summaries(
    symbols: Iterable[str], gene_ids: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    clean_symbols = sorted({str(value).strip().upper() for value in symbols if _GENE_SYMBOL.fullmatch(str(value).strip())})
    clean_symbols = clean_symbols[:MAX_GENE_SYMBOLS]
    clean_ids = sorted({str(value).strip() for value in gene_ids if str(value).strip().isdigit()})[:MAX_GENE_SYMBOLS]
    ids = list(clean_ids)
    if clean_symbols:
        expression = " OR ".join(f'"{symbol}"[Gene Name]' for symbol in clean_symbols)
        _, search_payload = _ncbi_client.get(
        "/entrez/eutils/esearch.fcgi",
        params={
            "db": "gene",
            "term": f"({expression}) AND 9606[Taxonomy ID]",
            "retmode": "json",
            "retmax": MAX_GENE_SYMBOLS,
        },
    )
        result = search_payload.get("esearchresult", {}) if isinstance(search_payload, dict) else {}
        found = result.get("idlist", []) if isinstance(result, dict) else []
        ids.extend(str(value) for value in found if str(value).isdigit())
    ids = list(dict.fromkeys(ids))[:MAX_GENE_SYMBOLS]
    if not ids:
        return {}
    _, summary_payload = _ncbi_client.get(
        "/entrez/eutils/esummary.fcgi",
        params={"db": "gene", "id": ",".join(ids), "retmode": "json"},
    )
    payload = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}
    uids = payload.get("uids", []) if isinstance(payload, dict) else []
    summaries: dict[str, dict[str, Any]] = {}
    for uid in uids:
        item = payload.get(str(uid), {})
        if not isinstance(item, dict):
            continue
        organism = item.get("organism") if isinstance(item.get("organism"), dict) else {}
        genomic = item.get("genomicinfo") if isinstance(item.get("genomicinfo"), list) else []
        first_location = genomic[0] if genomic and isinstance(genomic[0], dict) else {}
        symbol = item.get("nomenclaturesymbol") or item.get("name") or ""
        summaries[str(symbol).upper()] = {
            "ncbi_gene_id": str(uid),
            "gene_symbol": str(symbol).upper(),
            "description": item.get("description") or item.get("summary") or "",
            "chromosome": first_location.get("chrloc") or item.get("chromosome"),
            "genomic_start_source_value": first_location.get("chrstart"),
            "genomic_end_source_value": first_location.get("chrstop"),
            "genomic_accession": first_location.get("chraccver"),
            "organism": organism.get("scientificname"),
            "source": "NCBI Gene",
            "source_url": f"https://www.ncbi.nlm.nih.gov/gene/{uid}",
        }
    return summaries


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def lookup_ensembl_symbols(symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
    clean = sorted({str(value).strip().upper() for value in symbols if _GENE_SYMBOL.fullmatch(str(value).strip())})
    clean = clean[:MAX_GENE_SYMBOLS]
    if not clean:
        return {}
    payload = _ensembl_client.post(
        "/lookup/symbol/homo_sapiens",
        json={"symbols": clean},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )
    if not isinstance(payload, dict):
        raise DataSourceError("Ensembl returned an invalid gene lookup response.")
    output: dict[str, dict[str, Any]] = {}
    for symbol, item in payload.items():
        if not isinstance(item, dict) or not isinstance(symbol, str):
            continue
        output[symbol.upper()] = {
            "ensembl_gene_id": item.get("id"),
            "gene_symbol": item.get("display_name") or symbol.upper(),
            "biotype": item.get("biotype"),
            "chromosome": item.get("seq_region_name"),
            "start": item.get("start"),
            "end": item.get("end"),
            "strand": item.get("strand"),
            "assembly": item.get("assembly_name"),
            "canonical_transcript": item.get("canonical_transcript"),
            "source": "Ensembl",
            "source_release": "not reported",  # Headers not available via client
            "source_url": f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={item.get('id', '')}",
        }
    return output


@ttl_cache(ttl_seconds=86_400, max_entries=4)
def get_ensembl_data_version() -> str:
    """Return the active Ensembl data release reported by its REST service."""
    payload = _ensembl_client.get(
        "/info/data",
        headers={"Accept": "application/json"},
    )
    releases = payload.get("releases") if isinstance(payload, dict) else None
    if not isinstance(releases, list) or not releases:
        raise DataSourceError("Ensembl version response did not include a release list.")
    valid = [str(value) for value in releases if isinstance(value, (str, int)) and str(value).isdigit()]
    if not valid:
        raise DataSourceError("Ensembl version response contained no valid release number.")
    return ", ".join(valid)


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def search_uniprot_proteins(symbols: Iterable[str], limit: int = 50) -> dict[str, dict[str, Any]]:
    clean = sorted({str(value).strip().upper() for value in symbols if _GENE_SYMBOL.fullmatch(str(value).strip())})
    clean = clean[:MAX_GENE_SYMBOLS]
    if not clean:
        return {}
    if not 1 <= limit <= 100:
        raise ValueError("UniProt result limit must be between 1 and 100.")
    terms = " OR ".join(f"gene_exact:{symbol}" for symbol in clean)
    # Use _request for backward compatibility with tests that mock it
    response, payload = _request(
        "GET",
        f"{UNIPROT_REST}/uniprotkb/search",
        params={"query": f"({terms}) AND organism_id:9606 AND reviewed:true", "format": "json", "size": limit},
        headers={"Accept": "application/json"},
    )
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise DataSourceError("UniProt returned an invalid search result list.")
    proteins: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        genes = row.get("genes", [])
        symbol = ""
        if isinstance(genes, list) and genes and isinstance(genes[0], dict):
            name_item = genes[0].get("geneName") or {}
            symbol = str(name_item.get("value", "")).upper()
        if not symbol or symbol not in clean or symbol in proteins:
            continue
        description = row.get("proteinDescription") or {}
        recommended = description.get("recommendedName") or {}
        protein_name = ((recommended.get("fullName") or {}).get("value"))
        if not protein_name:
            submitted = description.get("submittedName") or []
            protein_name = ((submitted[0].get("fullName") or {}).get("value")) if submitted else symbol
        function_parts: list[str] = []
        locations: list[str] = []
        for comment in row.get("comments", []) if isinstance(row.get("comments"), list) else []:
            if not isinstance(comment, dict):
                continue
            texts = comment.get("texts", [])
            values = [item.get("value") for item in texts if isinstance(item, dict) and isinstance(item.get("value"), str)] if isinstance(texts, list) else []
            if comment.get("commentType") == "FUNCTION":
                function_parts.extend(values)
            elif comment.get("commentType") == "SUBCELLULAR LOCATION":
                locations.extend(values)
        domains = []
        for feature in row.get("features", []) if isinstance(row.get("features"), list) else []:
            if isinstance(feature, dict) and str(feature.get("type", "")).lower() == "domain":
                domains.append(
                    {
                        "description": feature.get("description"),
                        "begin": (feature.get("location") or {}).get("start", {}).get("value"),
                        "end": (feature.get("location") or {}).get("end", {}).get("value"),
                    }
                )
        sequence = row.get("sequence") or {}
        pdb_refs = [xref.get("id") for xref in row.get("uniProtKBCrossReferences", []) if isinstance(xref, dict) and xref.get("database") == "PDB"]
        accession = row.get("primaryAccession")
        if not isinstance(accession, str):
            continue
        proteins[symbol] = {
            "gene_symbol": symbol,
            "uniprot_id": accession,
            "protein_name": protein_name or symbol,
            "function": " ".join(dict.fromkeys(function_parts)),
            "subcellular_location": " ".join(dict.fromkeys(locations)),
            "domains": domains,
            "sequence": sequence.get("value") if isinstance(sequence, dict) else None,
            "sequence_length": sequence.get("length") if isinstance(sequence, dict) else None,
            "pdb_ids_from_uniprot": pdb_refs,
            "review_status": row.get("entryType", "not reported"),
            "source": "UniProtKB/Swiss-Prot",
            "source_release": response.headers.get("x-uniprot-release", "not reported"),
            "source_url": f"https://www.uniprot.org/uniprotkb/{accession}/entry",
        }
    return proteins


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def fetch_quickgo_annotations(accessions: Iterable[str], limit: int = 200) -> list[dict[str, Any]]:
    clean = sorted({str(value).strip() for value in accessions if re.fullmatch(r"[A-Z0-9]{6,10}", str(value).strip())})[:20]
    if not clean:
        return []
    if not 1 <= limit <= 500:
        raise ValueError("QuickGO annotation limit must be between 1 and 500.")
    params: list[tuple[str, str]] = [("geneProductId", f"UniProtKB:{accession}") for accession in clean]
    params.extend([("taxonId", "9606"), ("limit", str(limit))])
    # Use _request for backward compatibility with tests that mock it
    response, payload = _request(
        "GET",
        f"{QUICKGO_REST}/annotation/search",
        params=params,
        headers={"Accept": "application/json"},
    )
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise DataSourceError("QuickGO returned an invalid annotation list.")
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("geneProductId", "")), str(row.get("goId", "")), str(row.get("goEvidence", "")))
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "gene_product_id": row.get("geneProductId"),
                "gene_symbol": row.get("symbol"),
                "go_id": row.get("goId"),
                "go_name": row.get("goName"),
                "aspect": row.get("goAspect"),
                "evidence_code": row.get("goEvidence"),
                "reference": row.get("reference"),
                "assigned_by": row.get("assignedBy"),
                "source": "QuickGO / Gene Ontology Annotation (GOA)",
                "source_url": f"https://www.ebi.ac.uk/QuickGO/term/{row.get('goId', '')}",
            }
        )
    return output


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def analyze_reactome_pathways(gene_symbols: Iterable[str], limit: int = 20) -> dict[str, Any]:
    clean = sorted({str(value).strip().upper() for value in gene_symbols if _GENE_SYMBOL.fullmatch(str(value).strip())})[:MAX_TARGETS]
    if len(clean) < 2:
        return {"pathways": [], "identifiers_not_found": None, "warning": "At least two gene identifiers are needed for pathway enrichment."}
    if not 1 <= limit <= 50:
        raise ValueError("Reactome pathway result limit must be between 1 and 50.")
    # Use _request for backward compatibility with tests that mock it
    response, payload = _request(
        "POST",
        f"{REACTOME_ANALYSIS}/identifiers/projection",
        params={"pageSize": limit, "page": 1},
        data="#Genes\n" + "\n".join(clean),
        headers={"Content-Type": "text/plain", "Accept": "application/json"},
        timeout=60,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("pathways", []), list):
        raise DataSourceError("Reactome returned an invalid pathway analysis response.")
    pathways = []
    for item in payload.get("pathways", []):
        if not isinstance(item, dict):
            continue
        entities = item.get("entities") if isinstance(item.get("entities"), dict) else {}
        pathways.append(
            {
                "pathway_id": item.get("stId"),
                "name": item.get("name"),
                "p_value": entities.get("pValue"),
                "fdr": entities.get("fdr"),
                "genes_found": (entities.get("found")),
                "pathway_gene_total": entities.get("total"),
                "is_disease_pathway": item.get("inDisease"),
                "source": "Reactome Analysis Service",
                "source_url": f"https://reactome.org/PathwayBrowser/#/{item.get('stId', '')}",
            }
        )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "pathways": pathways,
        "identifiers_not_found": payload.get("identifiersNotFound"),
        "identifiers_found": payload.get("pathwaysFound"),
        "analysis_token": summary.get("token"),
        "input_gene_count": len(clean),
        "warning": "Over-representation results describe this submitted target-gene set; they do not establish disease causality.",
        "source": "Reactome Analysis Service",
        "source_version": "not reported by analysis response",
    }


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def search_rcsb_structures(accessions: Iterable[str], limit: int = 10) -> list[dict[str, Any]]:
    clean = sorted({str(value).strip() for value in accessions if re.fullmatch(r"[A-Z0-9]{6,10}", str(value).strip())})[:20]
    if not clean:
        return []
    if not 1 <= limit <= 20:
        raise ValueError("Structure result limit must be between 1 and 20.")
    nodes = [
        {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                "operator": "exact_match",
                "value": accession,
            },
        }
        for accession in clean
    ]
    payload = _rcsb_client.post(
        "/rcsbsearch/v2/query",
        json={
            "query": {"type": "group", "logical_operator": "or", "nodes": nodes},
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": limit}},
        },
        headers={"Content-Type": "application/json"},
    )
    result_set = payload.get("result_set", []) if isinstance(payload, dict) else []
    if not isinstance(result_set, list):
        raise DataSourceError("RCSB returned an invalid structure search response.")
    return [
        {
            "pdb_id": row.get("identifier"),
            "match_score": row.get("score"),
            "source": "RCSB Protein Data Bank",
            "source_url": f"https://www.rcsb.org/structure/{row.get('identifier', '')}",
        }
        for row in result_set
        if isinstance(row, dict) and isinstance(row.get("identifier"), str)
    ]


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def fetch_string_interactions(
    gene_symbols: Iterable[str],
    *,
    network_type: str = "functional",
    required_score: int = 400,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve a bounded STRING human protein-association network.

    STRING functional edges are associations and are not necessarily direct
    physical interactions. Channel-specific scores are retained for review.
    """
    clean = sorted({str(value).strip().upper() for value in gene_symbols if _GENE_SYMBOL.fullmatch(str(value).strip())})
    if not clean:
        return []
    if len(clean) > 20:
        raise ValueError("STRING network inputs are limited to 20 gene symbols per request.")
    if network_type not in {"functional", "physical"}:
        raise ValueError("STRING network type must be functional or physical.")
    if isinstance(required_score, bool) or not isinstance(required_score, int) or not 0 <= required_score <= 1000:
        raise ValueError("STRING required score must be an integer from 0 to 1000.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 250:
        raise ValueError("STRING interaction limit must be between 1 and 250.")
    # Use _request for backward compatibility with tests that mock it
    response, payload = _request(
        "GET",
        f"{STRING_BASE_URL}/api/json/network",
        params={
            "identifiers": "\r".join(clean),
            "species": 9606,
            "network_type": network_type,
            "required_score": required_score,
            "add_nodes": 0,
            "caller_identity": "GeneAIResearch",
        },
        timeout=30,
    )
    if not isinstance(payload, list):
        raise DataSourceError("STRING returned an invalid network response.")
    edges = []
    score_fields = ("nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore", "textmining")
    for row in payload[:limit]:
        if not isinstance(row, dict):
            continue
        protein_a = row.get("preferredName_A")
        protein_b = row.get("preferredName_B")
        try:
            combined = float(row.get("score"))
        except (TypeError, ValueError):
            continue
        if not isinstance(protein_a, str) or not protein_a.strip() or not isinstance(protein_b, str) or not protein_b.strip() or not 0 <= combined <= 1000:
            continue
        # STRING documentation describes integer scores in the 0–1000 range,
        # while the live versioned JSON endpoint can return normalized floats.
        # Accept both encodings so a score such as 0.4 is not reduced to 0.0004.
        normalized_combined = combined if combined <= 1 else combined / 1000.0
        raw_combined = round(combined * 1000) if combined <= 1 else combined
        channels = {}
        for key in score_fields:
            try:
                value = float(row.get(key, 0) or 0)
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 1000 and value > 0:
                channels[key] = round(value if value <= 1 else value / 1000.0, 4)
        edges.append({
            "protein_a": protein_a.strip().upper(),
            "protein_b": protein_b.strip().upper(),
            "string_id_a": row.get("stringId_A"),
            "string_id_b": row.get("stringId_B"),
            "combined_score": round(normalized_combined, 4),
            "combined_score_raw": int(raw_combined),
            "evidence_channel_scores": channels,
            "experimental_channel_score": channels.get("escore"),
            "network_type": network_type,
            "interaction_interpretation": (
                "STRING functional association; not necessarily a direct physical interaction."
                if network_type == "functional"
                else "STRING physical network association; score can combine experimental and predicted evidence."
            ),
            "source": f"STRING {STRING_DATABASE_VERSION}",
            "source_url": "https://string-db.org/",
        })
    return edges


@ttl_cache(ttl_seconds=21_600, max_entries=64)
def fetch_pubmed_abstracts(pmids: Iterable[str], limit: int = 20) -> dict[str, str]:
    clean = sorted({str(value).strip() for value in pmids if str(value).strip().isdigit()})[:limit]
    if not clean:
        return {}
    text = _pubmed_client.get(
        "/entrez/eutils/efetch.fcgi",
        params={"db": "pubmed", "id": ",".join(clean), "retmode": "xml"},
        expect_json=False,
        headers={"Accept": "application/xml"},
    )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DataSourceError("PubMed returned malformed abstract XML.") from exc
    abstracts: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID")
        abstract = article.find(".//Abstract")
        if not pmid or abstract is None:
            continue
        sections = []
        for node in abstract.findall(".//AbstractText"):
            label = node.attrib.get("Label") or node.attrib.get("NlmCategory")
            value = " ".join("".join(node.itertext()).split())
            if value:
                sections.append(f"{label}: {value}" if label else value)
        if sections:
            abstracts[pmid] = " ".join(sections)
    return abstracts


@ttl_cache(ttl_seconds=86_400, max_entries=4)
def get_reactome_database_version() -> str:
    text = _reactome_client.get(
        "/ContentService/data/database/version",
        expect_json=False,
        headers={"Accept": "text/plain"},
    )
    version = str(text).strip()
    return version[:40] if version else "not reported"


def disgenet_access_status() -> dict[str, str]:
    if os.environ.get("DISGENET_API_KEY"):
        return {
            "status": "credential_detected; API adapter awaits account-specific endpoint and license configuration",
            "source": "DisGeNET",
        }
    return {
        "status": "not queried; no DISGENET_API_KEY configured",
        "source": "DisGeNET",
    }


# Apply default rate limits on module import
apply_default_rate_limits()
