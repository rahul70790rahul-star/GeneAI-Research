"""Data integration for biomarker discovery (GEO, NCBI, Ensembl, UniProt)."""
from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from geneai.drug_discovery.cache import ttl_cache
from geneai.config import PUBMED_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# API endpoints
GEO_API = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ENSEMBL_API = "https://rest.ensembl.org"
UNIPROT_API = "https://rest.uniprot.org"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_RATE_INTERVALS = {
    "www.ncbi.nlm.nih.gov": 0.34,  # 3 requests/second for NCBI
    "eutils.ncbi.nlm.nih.gov": 0.34,
    "rest.ensembl.org": 0.1,
    "rest.uniprot.org": 0.15,
}
_rate_lock = threading.Lock()
_last_request_at: dict[str, float] = {}


class DataSourceError(RuntimeError):
    """A data source returned an unusable response."""


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
        "User-Agent": "GeneAIResearch/0.4 (Biomarker Discovery; contact not configured)",
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
            raise DataSourceError(f"Request to {host} failed: {exc}") from exc

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
            raise DataSourceError(
                f"{host} returned HTTP {response.status_code}: {body or response.reason}"
            ) from exc
        if not expect_json:
            return response, response.text
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise DataSourceError(f"{host} returned invalid JSON.") from exc
        if not isinstance(payload, (dict, list)):
            raise DataSourceError(f"{host} returned an unexpected JSON value.")
        return response, payload

    raise DataSourceError(f"Request to {host} failed: {last_error or 'retry limit reached'}")


# ============================================================================
# GEO (Gene Expression Omnibus) Integration
# ============================================================================

@dataclass
class GEODataset:
    """GEO dataset metadata."""
    accession: str
    title: str
    summary: str
    organism: str
    experiment_type: str
    samples: int
    platform: str
    pubmed_id: str
    submission_date: str
    last_update: str
    supplementary_files: list[str]


@dataclass
class GEOSample:
    """GEO sample metadata."""
    accession: str
    title: str
    source_name: str
    organism: str
    characteristics: dict[str, str]
    molecule: str
    label: str
    description: str


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def fetch_geo_dataset(accession: str) -> GEODataset | None:
    """Fetch GEO dataset metadata."""
    try:
        # Use NCBI E-utilities to search for GEO dataset
        _, payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "gds",
                "term": accession,
                "retmode": "json",
            },
        )
        
        id_list = payload.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return None
        
        gds_id = id_list[0]
        
        # Fetch summary
        _, summary_payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esummary.fcgi",
            params={
                "db": "gds",
                "id": gds_id,
                "retmode": "json",
            },
        )
        
        result = summary_payload.get("result", {}).get(gds_id, {})
        if not result:
            return None
        
        return GEODataset(
            accession=accession,
            title=result.get("title", ""),
            summary=result.get("summary", ""),
            organism=result.get("taxon", ""),
            experiment_type=result.get("gdsType", ""),
            samples=int(result.get("n_samples", 0)),
            platform=result.get("platform", ""),
            pubmed_id=result.get("pubmedId", ""),
            submission_date=result.get("submissionDate", ""),
            last_update=result.get("lastUpdateDate", ""),
            supplementary_files=result.get("supplementaryFile", "").split(";") if result.get("supplementaryFile") else [],
        )
    except Exception as e:
        logger.warning("GEO dataset fetch failed for %s: %s", accession, e)
        return None


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_geo_datasets(query: str, max_results: int = 20) -> list[GEODataset]:
    """Search GEO datasets by query."""
    try:
        _, payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "gds",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
            },
        )
        
        id_list = payload.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []
        
        # Fetch summaries for all IDs
        _, summary_payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esummary.fcgi",
            params={
                "db": "gds",
                "id": ",".join(id_list),
                "retmode": "json",
            },
        )
        
        datasets = []
        for gds_id in id_list:
            result = summary_payload.get("result", {}).get(gds_id, {})
            if result:
                datasets.append(GEODataset(
                    accession=result.get("accession", gds_id),
                    title=result.get("title", ""),
                    summary=result.get("summary", "")[:200],
                    organism=result.get("taxon", ""),
                    experiment_type=result.get("gdsType", ""),
                    samples=int(result.get("n_samples", 0)),
                    platform=result.get("platform", ""),
                    pubmed_id=result.get("pubmedId", ""),
                    submission_date=result.get("submissionDate", ""),
                    last_update=result.get("lastUpdateDate", ""),
                    supplementary_files=[],
                ))
        return datasets
    except Exception as e:
        logger.warning("GEO search failed: %s", e)
        return []


# ============================================================================
# NCBI Gene Integration
# ============================================================================

@dataclass
class NCBIGene:
    """NCBI Gene entry."""
    gene_id: str
    symbol: str
    name: str
    description: str
    organism: str
    chromosome: str
    map_location: str
    gene_type: str
    aliases: list[str]
    pubmed_ids: list[str]
    pathways: list[str]
    go_terms: list[str]


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_ncbi_gene(gene_symbol: str, organism: str = "human") -> NCBIGene | None:
    """Fetch NCBI Gene entry by symbol."""
    try:
        # Search for gene
        _, payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "gene",
                "term": f"{gene_symbol}[SYM] AND {organism}[ORGN]",
                "retmode": "json",
            },
        )
        
        id_list = payload.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return None
        
        gene_id = id_list[0]
        
        # Fetch summary
        _, summary_payload = _request(
            "GET",
            f"{NCBI_EUTILS}/esummary.fcgi",
            params={
                "db": "gene",
                "id": gene_id,
                "retmode": "json",
            },
        )
        
        result = summary_payload.get("result", {}).get(gene_id, {})
        if not result:
            return None
        
        return NCBIGene(
            gene_id=gene_id,
            symbol=result.get("name", gene_symbol),
            name=result.get("description", ""),
            description=result.get("description", "")[:500],
            organism=result.get("organism", {}).get("scientificname", ""),
            chromosome=result.get("chromosome", ""),
            map_location=result.get("maplocation", ""),
            gene_type=result.get("genetype", ""),
            aliases=result.get("otheraliases", "").split("|") if result.get("otheraliases") else [],
            pubmed_ids=[],
            pathways=[],
            go_terms=[],
        )
    except Exception as e:
        logger.warning("NCBI Gene fetch failed for %s: %s", gene_symbol, e)
        return None


# ============================================================================
# Ensembl Integration
# ============================================================================

@dataclass
class EnsemblGene:
    """Ensembl gene entry."""
    gene_id: str
    symbol: str
    name: str
    biotype: str
    chromosome: str
    start: int
    end: int
    strand: int
    description: str
    transcripts: list[dict[str, Any]]
    orthologs: list[dict[str, Any]]
    regulatory_features: list[dict[str, Any]]


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_ensembl_gene(gene_symbol: str, species: str = "homo_sapiens") -> EnsemblGene | None:
    """Fetch Ensembl gene entry."""
    try:
        _, payload = _request(
            "GET",
            f"{ENSEMBL_API}/xrefs/symbol/{species}/{gene_symbol}",
            headers={"Content-Type": "application/json"},
        )
        
        if not payload or not isinstance(payload, list):
            return None
        
        # Get the gene ID
        gene_id = None
        for xref in payload:
            if xref.get("type") == "gene":
                gene_id = xref.get("id")
                break
        
        if not gene_id:
            return None
        
        # Fetch gene details
        _, gene_payload = _request(
            "GET",
            f"{ENSEMBL_API}/lookup/id/{gene_id}",
            params={"expand": 1},
            headers={"Content-Type": "application/json"},
        )
        
        if not gene_payload:
            return None
        
        return EnsemblGene(
            gene_id=gene_id,
            symbol=gene_payload.get("display_name", gene_symbol),
            name=gene_payload.get("display_name", gene_symbol),
            biotype=gene_payload.get("biotype", ""),
            chromosome=gene_payload.get("seq_region_name", ""),
            start=gene_payload.get("start", 0),
            end=gene_payload.get("end", 0),
            strand=gene_payload.get("strand", 0),
            description=gene_payload.get("description", ""),
            transcripts=gene_payload.get("Transcript", []),
            orthologs=[],
            regulatory_features=[],
        )
    except Exception as e:
        logger.warning("Ensembl gene fetch failed for %s: %s", gene_symbol, e)
        return None


# ============================================================================
# UniProt Integration (for protein-level biomarker info)
# ============================================================================

@dataclass
class UniProtBiomarkerInfo:
    """UniProt entry with biomarker-relevant info."""
    uniprot_id: str
    gene_symbol: str
    protein_name: str
    organism: str
    function: str
    subcellular_location: str
    tissue_specificity: str
    disease_variants: list[dict[str, Any]]
    ptms: list[dict[str, Any]]
    interactions: list[str]
    pathways: list[str]
    go_terms: list[str]
    secreted: bool
    transmembrane: bool


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_uniprot_biomarker_info(identifier: str) -> UniProtBiomarkerInfo | None:
    """Fetch UniProt entry with biomarker-relevant annotations."""
    try:
        _, payload = _request(
            "GET",
            f"{UNIPROT_API}/uniprotkb/search",
            params={
                "query": f"gene:{identifier} OR id:{identifier}",
                "format": "json",
                "size": 1,
            },
        )
        
        results = payload.get("results", [])
        if not results:
            return None
        
        entry = results[0]
        uniprot_id = entry.get("primaryAccession", "")
        
        # Get detailed entry
        _, detail = _request("GET", f"{UNIPROT_API}/uniprotkb/{uniprot_id}.json")
        
        # Extract gene symbol
        genes = detail.get("genes", [])
        gene_symbol = ""
        if genes:
            gene_name = genes[0].get("geneName", {})
            gene_symbol = gene_name.get("value", "")
        
        # Protein name
        protein_desc = detail.get("proteinDescription", {})
        rec_name = protein_desc.get("recommendedName", {})
        full_name = rec_name.get("fullName", {})
        protein_name = full_name.get("value", "")
        
        # Organism
        organism_obj = detail.get("organism", {})
        organism = organism_obj.get("scientificName", "")
        
        # Function
        function = ""
        for comment in detail.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                for text in comment.get("texts", []):
                    function += text.get("value", "") + " "
        
        # Subcellular location
        location = ""
        for comment in detail.get("comments", []):
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for text in comment.get("texts", []):
                    location += text.get("value", "") + " "
        
        # Tissue specificity
        tissue = ""
        for comment in detail.get("comments", []):
            if comment.get("commentType") == "TISSUE SPECIFICITY":
                for text in comment.get("texts", []):
                    tissue += text.get("value", "") + " "
        
        # Disease variants
        disease_variants = []
        for feature in detail.get("features", []):
            if feature.get("type") == "VARIANT":
                disease_variants.append({
                    "position": feature.get("location", {}).get("start", {}).get("value"),
                    "original": feature.get("original"),
                    "variation": feature.get("variation"),
                    "description": feature.get("description", ""),
                })
        
        # PTMs
        ptms = []
        for feature in detail.get("features", []):
            if feature.get("type") in ("MOD_RES", "LIPID", "CARBOHYD", "CROSSLNK", "DISULFID"):
                ptms.append({
                    "type": feature.get("type"),
                    "position": feature.get("location", {}).get("start", {}).get("value"),
                    "description": feature.get("description", ""),
                })
        
        # Interactions (from cross-references)
        interactions = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") in ("IntAct", "BioGRID", "STRING"):
                interactions.append(xref.get("id", ""))
        
        # Pathways
        pathways = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") in ("Reactome", "KEGG", "WikiPathways"):
                pathways.append(xref.get("id", ""))
        
        # GO terms
        go_terms = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") == "GO":
                go_terms.append(xref.get("id", ""))
        
        # Check if secreted or transmembrane
        secreted = False
        transmembrane = False
        for comment in detail.get("comments", []):
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for loc in comment.get("subcellularLocations", []):
                    location = loc.get("location", {}).get("value", "").lower()
                    if "secreted" in location:
                        secreted = True
                    if "transmembrane" in location or "membrane" in location:
                        transmembrane = True
        
        return UniProtBiomarkerInfo(
            uniprot_id=uniprot_id,
            gene_symbol=gene_symbol,
            protein_name=protein_name,
            organism=organism,
            function=function.strip(),
            subcellular_location=location.strip(),
            tissue_specificity=tissue.strip(),
            disease_variants=disease_variants,
            ptms=ptms,
            interactions=interactions,
            pathways=pathways,
            go_terms=go_terms,
            secreted=secreted,
            transmembrane=transmembrane,
        )
    except Exception as e:
        logger.warning("UniProt biomarker info fetch failed for %s: %s", identifier, e)
        return None