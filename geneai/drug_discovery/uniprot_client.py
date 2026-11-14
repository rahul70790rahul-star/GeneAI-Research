"""UniProt REST API client for GeneAI Research."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

UNIPROT_BASE = "https://rest.uniprot.org"
UNIPROT_UPLOADLISTS = "https://www.uniprot.org/uploadlists"
_RATE_LIMIT_SECONDS = 0.2
_last_request_time = 0.0

_UNIPROT_AC_PATTERN = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$")


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _uniprot_request(
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
        raise api_clients.DataSourceError(f"UniProt request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("UniProt entry not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"UniProt server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"UniProt HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("UniProt returned invalid JSON") from exc
    return response, payload


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize UniProt entry."""
    protein_desc = entry.get("proteinDescription", {})
    recommended = protein_desc.get("recommendedName", {})
    alternative = protein_desc.get("alternativeNames", [])

    gene_names = []
    genes = entry.get("genes", [])
    for gene in genes:
        gene_names.append(gene.get("geneName", {}).get("value"))
        for syn in gene.get("synonyms", []):
            gene_names.append(syn.get("value"))

    organism = entry.get("organism", {})
    organism_names = [organism.get("scientificName")]
    for name in organism.get("commonName", []):
        organism_names.append(name)

    uniprotkb_id = entry.get("primaryAccession")
    secondary = entry.get("secondaryAccessions", [])

    functions = []
    for comment in entry.get("comments", []):
        if comment.get("commentType") == "FUNCTION":
            for text in comment.get("texts", []):
                functions.append(text.get("value"))

    pathways = []
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref.get("database") == "Reactome":
            pathways.append(db_ref.get("id"))
        elif db_ref.get("database") == "KEGG":
            pathways.append(db_ref.get("id"))

    go_terms = []
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref.get("database") == "GO":
            go_terms.append(db_ref.get("id"))

    pdb_entries = []
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref.get("database") == "PDB":
            pdb_entries.append(db_ref.get("id"))

    drugbank_ids = []
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref.get("database") == "DrugBank":
            drugbank_ids.append(db_ref.get("id"))

    chembl_ids = []
    for db_ref in entry.get("uniProtKBCrossReferences", []):
        if db_ref.get("database") == "ChEMBL":
            chembl_ids.append(db_ref.get("id"))

    return {
        "accession": uniprotkb_id,
        "secondary_accessions": secondary,
        "entry_name": entry.get("uniProtKBCrossReferences", [{}])[0].get("id") if entry.get("uniProtKBCrossReferences") else entry.get("entryName"),
        "protein_name": recommended.get("fullName", {}).get("value"),
        "protein_short_names": [alt.get("fullName", {}).get("value") for alt in alternative if alt.get("fullName")],
        "gene_names": [g for g in gene_names if g],
        "organism": organism_names[0] if organism_names else None,
        "taxonomy_id": organism.get("taxonId"),
        "functions": functions,
        "pathways": pathways,
        "go_terms": go_terms,
        "pdb_entries": pdb_entries,
        "drugbank_ids": drugbank_ids,
        "chembl_ids": chembl_ids,
        "sequence": entry.get("sequence", {}).get("value"),
        "sequence_length": entry.get("sequence", {}).get("length"),
        "sequence_mass": entry.get("sequence", {}).get("molWeight"),
        "source": "UniProt",
        "source_url": f"https://www.uniprot.org/uniprotkb/{uniprotkb_id}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_entry_by_accession(accession: str) -> dict[str, Any] | None:
    """Retrieve UniProt entry by accession number."""
    accession = accession.strip().upper()
    if not _UNIPROT_AC_PATTERN.fullmatch(accession):
        raise ValueError("Invalid UniProt accession format")
    url = f"{UNIPROT_BASE}/uniprotkb/{accession}.json"
    _, payload = _uniprot_request("GET", url)
    if not isinstance(payload, dict):
        return None
    return _normalize_entry(payload)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_entries(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search UniProt entries by query string."""
    query = query.strip()
    if not query or len(query) > 300:
        raise ValueError("Search query must be 1-300 characters")
    url = f"{UNIPROT_BASE}/uniprotkb/search"
    params = {
        "query": query,
        "format": "json",
        "size": min(max(1, limit), 100),
        "fields": "accession,id,protein_name,gene_names,organism_name,length",
    }
    _, payload = _uniprot_request("GET", url, params=params)
    results = payload.get("results", [])
    entries = []
    for r in results:
        try:
            entries.append(_normalize_entry(r))
        except (ValueError, KeyError):
            continue
    return entries


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_entry_by_gene_name(gene_name: str, organism: str = "9606") -> list[dict[str, Any]]:
    """Search UniProt entries by gene name and organism (default human)."""
    gene_name = gene_name.strip()
    if not gene_name or len(gene_name) > 100:
        raise ValueError("Gene name must be 1-100 characters")
    query = f"gene_exact:{gene_name} AND organism_id:{organism}"
    return search_entries(query, limit=20)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_protein_features(accession: str) -> dict[str, Any]:
    """Get protein features (domains, sites, variants)."""
    accession = accession.strip().upper()
    url = f"{UNIPROT_BASE}/uniprotkb/{accession}.json"
    _, payload = _uniprot_request("GET", url)
    features = payload.get("features", [])
    domains = []
    sites = []
    variants = []
    for feat in features:
        feat_type = feat.get("type")
        location = feat.get("location", {})
        start = location.get("start", {}).get("value")
        end = location.get("end", {}).get("value")
        desc = feat.get("description", "")
        if feat_type in ("DOMAIN", "REPEAT", "MOTIF", "ZINC_FINGER"):
            domains.append({"type": feat_type, "start": start, "end": end, "description": desc})
        elif feat_type in ("ACTIVE_SITE", "BINDING_SITE", "METAL_BINDING", "SITE"):
            sites.append({"type": feat_type, "position": start, "description": desc})
        elif feat_type == "VARIANT":
            variants.append({"position": start, "description": desc, "original": feat.get("alternativeSequence", ""), "variation": feat.get("variation", "")})
    return {
        "accession": accession,
        "domains": domains,
        "sites": sites,
        "variants": variants,
        "source": "UniProt",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_cross_references(accession: str) -> dict[str, list[str]]:
    """Get cross-references to other databases."""
    accession = accession.strip().upper()
    url = f"{UNIPROT_BASE}/uniprotkb/{accession}.json"
    _, payload = _uniprot_request("GET", url)
    refs = {}
    for db_ref in payload.get("uniProtKBCrossReferences", []):
        db = db_ref.get("database")
        if db not in refs:
            refs[db] = []
        refs[db].append(db_ref.get("id"))
    return {
        "accession": accession,
        "cross_references": refs,
        "source": "UniProt",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=32)
def map_ids(from_db: str, ids: list[str], to_db: str = "UniProtKB") -> dict[str, str]:
    """Map IDs from one database to another (e.g., GeneID to UniProt)."""
    if not ids:
        return {}
    url = UNIPROT_UPLOADLISTS
    params = {
        "from": from_db,
        "to": to_db,
        "format": "json",
        "ids": ",".join(ids[:1000]),
    }
    try:
        _, payload = _uniprot_request("POST", url, data=params, expect_json=True)
    except api_clients.DataSourceError:
        return {}
    results = {}
    for item in payload.get("results", []):
        results[item.get("from")] = item.get("to")
    return results