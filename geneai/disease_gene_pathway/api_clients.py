"""API clients for disease-gene-pathway analysis."""
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
OPENTARGETS_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"
DISGENET_API = "https://www.disgenet.org/api/v1"
STRING_API = "https://version-12-0.string-db.org/api"
KEGG_API = "https://rest.kegg.jp"
REACTOME_API = "https://reactome.org/ContentService"
GO_API = "https://www.ebi.ac.uk/QuickGO/services/ontology/go"
UNIPROT_API = "https://rest.uniprot.org"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_RATE_INTERVALS = {
    "api.platform.opentargets.org": 0.5,
    "www.disgenet.org": 1.0,
    "version-12-0.string-db.org": 0.2,
    "rest.kegg.jp": 0.1,
    "reactome.org": 0.2,
    "www.ebi.ac.uk": 0.2,
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
        "User-Agent": "GeneAIResearch/0.4 (Disease-Gene-Pathway analysis; contact not configured)",
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
# OpenTargets API
# ============================================================================

@dataclass
class DiseaseGeneAssociation:
    """Disease-gene association from OpenTargets."""
    disease_id: str
    disease_name: str
    gene_symbol: str
    gene_id: str
    score: float
    datasources: list[str]
    evidence_count: int


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_opentargets_disease_genes(disease_id: str, min_score: float = 0.1, limit: int = 100) -> list[DiseaseGeneAssociation]:
    """Fetch disease-associated genes from OpenTargets."""
    query = """
    query AssociatedGenes($diseaseId: String!, $minScore: Float, $size: Int) {
        disease(efoId: $diseaseId) {
            id
            name
            associatedTargets(page: {size: $size, index: 0}, minScore: $minScore) {
                rows {
                    target {
                        id
                        approvedSymbol
                    }
                    score
                    datasourceScores {
                        id
                        score
                    }
                }
                count
            }
        }
    }
    """
    try:
        _, payload = _request(
            "POST",
            OPENTARGETS_GRAPHQL,
            json={"query": query, "variables": {"diseaseId": disease_id, "minScore": min_score, "size": limit}},
        )
        data = payload.get("data", {})
        disease = data.get("disease")
        if not disease:
            return []
        
        associations = []
        for row in disease.get("associatedTargets", {}).get("rows", []):
            target = row.get("target", {})
            associations.append(DiseaseGeneAssociation(
                disease_id=disease_id,
                disease_name=disease.get("name", ""),
                gene_symbol=target.get("approvedSymbol", ""),
                gene_id=target.get("id", ""),
                score=row.get("score", 0.0),
                datasources=[ds.get("id", "") for ds in row.get("datasourceScores", [])],
                evidence_count=len(row.get("datasourceScores", [])),
            ))
        return associations
    except Exception as e:
        logger.warning("OpenTargets query failed for %s: %s", disease_id, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_opentargets_gene_diseases(gene_symbol: str, min_score: float = 0.1, limit: int = 100) -> list[DiseaseGeneAssociation]:
    """Fetch diseases associated with a gene from OpenTargets."""
    # First get target ID from gene symbol
    query = """
    query TargetSearch($symbol: String!) {
        targetSearch(query: $symbol, page: {size: 1}) {
            targets {
                id
                approvedSymbol
            }
        }
    }
    """
    try:
        _, payload = _request("POST", OPENTARGETS_GRAPHQL, json={"query": query, "variables": {"symbol": gene_symbol}})
        targets = payload.get("data", {}).get("targetSearch", {}).get("targets", [])
        if not targets:
            return []
        
        target_id = targets[0]["id"]
        
        # Now get associated diseases
        query2 = """
        query AssociatedDiseases($targetId: String!, $minScore: Float, $size: Int) {
            target(ensemblId: $targetId) {
                id
                approvedSymbol
                associatedDiseases(page: {size: $size, index: 0}, minScore: $minScore) {
                    rows {
                        disease {
                            id
                            name
                        }
                        score
                        datasourceScores {
                            id
                            score
                        }
                    }
                    count
                }
            }
        }
        """
        _, payload2 = _request(
            "POST",
            OPENTARGETS_GRAPHQL,
            json={"query": query2, "variables": {"targetId": target_id, "minScore": min_score, "size": limit}},
        )
        target_data = payload2.get("data", {}).get("target", {})
        associations = []
        for row in target_data.get("associatedDiseases", {}).get("rows", []):
            disease = row.get("disease", {})
            associations.append(DiseaseGeneAssociation(
                disease_id=disease.get("id", ""),
                disease_name=disease.get("name", ""),
                gene_symbol=target_data.get("approvedSymbol", gene_symbol),
                gene_id=target_id,
                score=row.get("score", 0.0),
                datasources=[ds.get("id", "") for ds in row.get("datasourceScores", [])],
                evidence_count=len(row.get("datasourceScores", [])),
            ))
        return associations
    except Exception as e:
        logger.warning("OpenTargets gene-disease query failed for %s: %s", gene_symbol, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_opentargets_diseases(query_term: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search diseases in OpenTargets."""
    query = """
    query DiseaseSearch($query: String!, $size: Int) {
        diseaseSearch(query: $query, page: {size: $size}) {
            diseases {
                id
                name
                description
                therapeuticAreas
            }
        }
    }
    """
    try:
        _, payload = _request(
            "POST",
            OPENTARGETS_GRAPHQL,
            json={"query": query, "variables": {"query": query_term, "size": limit}},
        )
        diseases = payload.get("data", {}).get("diseaseSearch", {}).get("diseases", [])
        return [
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "description": d.get("description", "")[:200] if d.get("description") else "",
                "therapeutic_areas": d.get("therapeuticAreas", []),
            }
            for d in diseases
        ]
    except Exception as e:
        logger.warning("OpenTargets disease search failed: %s", e)
        return []


# ============================================================================
# DisGeNET API (requires API key for full access, using public endpoints)
# ============================================================================

@dataclass
class DisGeNETAssociation:
    """Disease-gene association from DisGeNET."""
    disease_id: str
    disease_name: str
    disease_type: str
    gene_symbol: str
    gene_id: str
    score: float
    ei: float  # Evidence Index
    year_initial: int
    year_final: int
    n_pmids: int
    snps: list[str]
    source: str


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_disgenet_gene_diseases(gene_symbol: str, limit: int = 100) -> list[DisGeNETAssociation]:
    """Fetch diseases for a gene from DisGeNET (public endpoint)."""
    # DisGeNET public API - requires registration for full access
    # Using a simplified approach with available public data
    try:
        _, payload = _request(
            "GET",
            f"{DISGENET_API}/gda/gene/{gene_symbol}",
            params={"limit": limit, "format": "json"},
        )
        associations = []
        for item in payload if isinstance(payload, list) else []:
            associations.append(DisGeNETAssociation(
                disease_id=str(item.get("diseaseId", "")),
                disease_name=item.get("diseaseName", ""),
                disease_type=item.get("diseaseType", ""),
                gene_symbol=item.get("geneSymbol", gene_symbol),
                gene_id=str(item.get("geneId", "")),
                score=float(item.get("score", 0.0)),
                ei=float(item.get("EI", 0.0)),
                year_initial=int(item.get("yearInitial", 0)),
                year_final=int(item.get("yearFinal", 0)),
                n_pmids=int(item.get("nPmids", 0)),
                snps=item.get("snps", "").split("|") if item.get("snps") else [],
                source="DisGeNET",
            ))
        return associations
    except Exception as e:
        logger.warning("DisGeNET query failed for %s: %s", gene_symbol, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_disgenet_disease_genes(disease_id: str, limit: int = 100) -> list[DisGeNETAssociation]:
    """Fetch genes for a disease from DisGeNET."""
    try:
        _, payload = _request(
            "GET",
            f"{DISGENET_API}/gda/disease/{disease_id}",
            params={"limit": limit, "format": "json"},
        )
        associations = []
        for item in payload if isinstance(payload, list) else []:
            associations.append(DisGeNETAssociation(
                disease_id=str(item.get("diseaseId", disease_id)),
                disease_name=item.get("diseaseName", ""),
                disease_type=item.get("diseaseType", ""),
                gene_symbol=item.get("geneSymbol", ""),
                gene_id=str(item.get("geneId", "")),
                score=float(item.get("score", 0.0)),
                ei=float(item.get("EI", 0.0)),
                year_initial=int(item.get("yearInitial", 0)),
                year_final=int(item.get("yearFinal", 0)),
                n_pmids=int(item.get("nPmids", 0)),
                snps=item.get("snps", "").split("|") if item.get("snps") else [],
                source="DisGeNET",
            ))
        return associations
    except Exception as e:
        logger.warning("DisGeNET disease query failed for %s: %s", disease_id, e)
        return []


# ============================================================================
# STRING PPI API
# ============================================================================

@dataclass
class PPIInteraction:
    """Protein-protein interaction from STRING."""
    protein1: str
    protein2: str
    score: float
    combined_score: float
    experimental_score: float
    database_score: float
    textmining_score: float
    cooccurrence_score: float
    coexpression_score: float
    neighborhood_score: float
    fusion_score: float
    cooccurrence: bool
    coexpression: bool
    experimental: bool
    database: bool
    textmining: bool
    neighborhood: bool
    fusion: bool


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_string_interactions(
    gene_symbols: list[str],
    species: int = 9606,
    min_score: float = 0.4,
    limit: int = 500,
) -> list[PPIInteraction]:
    """Fetch PPI network from STRING."""
    if not gene_symbols:
        return []
    
    identifiers = "%0d".join(gene_symbols)
    try:
        _, payload = _request(
            "GET",
            f"{STRING_API}/tsv/network",
            params={
                "identifiers": identifiers,
                "species": species,
                "required_score": int(min_score * 1000),
                "limit": limit,
                "network_flavor": "evidence",
            },
            headers={"Accept": "text/tab-separated-values"},
        )
        
        # Parse TSV response
        interactions = []
        lines = payload.strip().split("\n") if isinstance(payload, str) else []
        for line in lines[1:]:  # Skip header
            parts = line.split("\t")
            if len(parts) >= 15:
                interactions.append(PPIInteraction(
                    protein1=parts[0],
                    protein2=parts[1],
                    score=float(parts[2]) if parts[2] else 0.0,
                    combined_score=float(parts[3]) if parts[3] else 0.0,
                    experimental_score=float(parts[4]) if parts[4] else 0.0,
                    database_score=float(parts[5]) if parts[5] else 0.0,
                    textmining_score=float(parts[6]) if parts[6] else 0.0,
                    cooccurrence_score=float(parts[7]) if parts[7] else 0.0,
                    coexpression_score=float(parts[8]) if parts[8] else 0.0,
                    neighborhood_score=float(parts[9]) if parts[9] else 0.0,
                    fusion_score=float(parts[10]) if parts[10] else 0.0,
                    cooccurrence=parts[11] == "1",
                    coexpression=parts[12] == "1",
                    experimental=parts[13] == "1",
                    database=parts[14] == "1",
                    textmining=parts[15] == "1" if len(parts) > 15 else False,
                    neighborhood=parts[16] == "1" if len(parts) > 16 else False,
                    fusion=parts[17] == "1" if len(parts) > 17 else False,
                ))
        return interactions
    except Exception as e:
        logger.warning("STRING PPI query failed: %s", e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def fetch_string_enrichment(
    gene_symbols: list[str],
    species: int = 9606,
    category: str = "Process",
) -> list[dict[str, Any]]:
    """Fetch functional enrichment from STRING."""
    if not gene_symbols:
        return []
    
    identifiers = "%0d".join(gene_symbols)
    try:
        _, payload = _request(
            "GET",
            f"{STRING_API}/tsv/enrichment",
            params={
                "identifiers": identifiers,
                "species": species,
                "caller_identity": "GeneAIResearch",
            },
            headers={"Accept": "text/tab-separated-values"},
        )
        
        results = []
        lines = payload.strip().split("\n") if isinstance(payload, str) else []
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) >= 10 and parts[1] == category:
                results.append({
                    "category": parts[1],
                    "term": parts[2],
                    "description": parts[3],
                    "p_value": float(parts[4]) if parts[4] else 1.0,
                    "fdr": float(parts[5]) if parts[5] else 1.0,
                    "input_genes": int(parts[6]) if parts[6] else 0,
                    "background_genes": int(parts[7]) if parts[7] else 0,
                    "preferred_names": parts[8].split(",") if parts[8] else [],
                })
        return results
    except Exception as e:
        logger.warning("STRING enrichment query failed: %s", e)
        return []


# ============================================================================
# KEGG Pathway API
# ============================================================================

@dataclass
class KEGGPathway:
    """KEGG pathway entry."""
    pathway_id: str
    name: str
    description: str
    category: str
    genes: list[str]
    gene_names: dict[str, str]


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_kegg_pathways_for_genes(gene_symbols: list[str], organism: str = "hsa") -> list[KEGGPathway]:
    """Find KEGG pathways containing the given genes."""
    if not gene_symbols:
        return []
    
    # Get gene IDs for symbols
    gene_ids = []
    for symbol in gene_symbols:
        try:
            _, payload = _request("GET", f"{KEGG_API}/find/genes/{organism}:{symbol}")
            lines = payload.strip().split("\n")
            for line in lines:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[1].startswith(symbol):
                    gene_ids.append(parts[0])
        except Exception:
            continue
    
    if not gene_ids:
        return []
    
    # Get pathways for each gene
    pathway_map: dict[str, dict] = {}
    for gene_id in gene_ids:
        try:
            _, payload = _request("GET", f"{KEGG_API}/link/pathway/{gene_id}")
            lines = payload.strip().split("\n")
            for line in lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    pathway_id = parts[1].replace("path:", "")
                    if pathway_id not in pathway_map:
                        pathway_map[pathway_id] = {"genes": [], "gene_names": {}}
                    pathway_map[pathway_id]["genes"].append(gene_id)
        except Exception:
            continue
    
    # Get pathway details
    pathways = []
    for pathway_id, data in pathway_map.items():
        try:
            _, payload = _request("GET", f"{KEGG_API}/get/{organism}{pathway_id}")
            name = ""
            description = ""
            category = ""
            for line in payload.strip().split("\n"):
                if line.startswith("NAME"):
                    name = line[12:].strip()
                elif line.startswith("DESCRIPTION"):
                    description = line[13:].strip()
                elif line.startswith("CLASS"):
                    category = line[12:].split(";")[0].strip()
            
            pathways.append(KEGGPathway(
                pathway_id=f"{organism}{pathway_id}",
                name=name,
                description=description,
                category=category,
                genes=data["genes"],
                gene_names=data["gene_names"],
            ))
        except Exception:
            continue
    
    return pathways


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def search_kegg_pathways(query: str, organism: str = "hsa") -> list[dict[str, Any]]:
    """Search KEGG pathways by keyword."""
    try:
        _, payload = _request("GET", f"{KEGG_API}/find/pathway/{query}")
        pathways = []
        for line in payload.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                pathways.append({
                    "pathway_id": parts[0],
                    "name": parts[1],
                })
        return pathways
    except Exception as e:
        logger.warning("KEGG search failed: %s", e)
        return []


# ============================================================================
# Reactome Pathway API
# ============================================================================

@dataclass
class ReactomePathway:
    """Reactome pathway entry."""
    pathway_id: str
    name: str
    species: str
    genes: list[str]
    gene_names: dict[str, str]


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_reactome_pathways_for_genes(gene_symbols: list[str], species: str = "Homo sapiens") -> list[ReactomePathway]:
    """Find Reactome pathways containing the given genes."""
    if not gene_symbols:
        return []
    
    pathway_map: dict[str, dict] = {}
    
    for symbol in gene_symbols:
        try:
            _, payload = _request(
                "GET",
                f"{REACTOME_API}/data/query/enhancedParticipatingEntities",
                params={"name": symbol, "species": species},
            )
            for item in payload if isinstance(payload, list) else []:
                pathway_id = item.get("pathwayId", "")
                if pathway_id:
                    if pathway_id not in pathway_map:
                        pathway_map[pathway_id] = {"name": "", "species": species, "genes": [], "gene_names": {}}
                    pathway_map[pathway_id]["genes"].append(symbol)
        except Exception:
            continue
    
    # Get pathway details
    pathways = []
    for pathway_id, data in pathway_map.items():
        try:
            _, payload = _request("GET", f"{REACTOME_API}/data/pathway/{pathway_id}/details")
            pathways.append(ReactomePathway(
                pathway_id=pathway_id,
                name=payload.get("displayName", ""),
                species=payload.get("species", {}).get("name", species),
                genes=data["genes"],
                gene_names=data["gene_names"],
            ))
        except Exception:
            continue
    
    return pathways


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_reactome_pathway_analysis(
    gene_symbols: list[str],
    species: str = "Homo sapiens",
    p_value: float = 0.05,
) -> list[dict[str, Any]]:
    """Perform Reactome pathway enrichment analysis."""
    if not gene_symbols:
        return []
    
    identifiers = ",".join(gene_symbols)
    try:
        _, payload = _request(
            "POST",
            f"{REACTOME_API}/analysis/token",
            data={"identifiers": identifiers, "species": species},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        token = payload.get("token")
        if not token:
            return []
        
        # Poll for results
        for _ in range(10):
            time.sleep(1)
            _, result = _request("GET", f"{REACTOME_API}/analysis/result", params={"token": token})
            if result.get("status") == "complete":
                pathways = []
                for pathway in result.get("pathways", []):
                    entities = pathway.get("entities", {})
                    pathways.append({
                        "pathway_id": pathway.get("stId"),
                        "name": pathway.get("name"),
                        "p_value": entities.get("pValue", 1.0),
                        "fdr": entities.get("fdr", 1.0),
                        "entities_found": entities.get("entitiesFound", 0),
                        "entities_total": entities.get("entitiesTotal", 0),
                        "entities_ratio": entities.get("entitiesRatio", 0.0),
                        "genes": [e.get("name") for e in entities.get("entities", [])],
                    })
                return [p for p in pathways if p["p_value"] <= p_value]
    except Exception as e:
        logger.warning("Reactome analysis failed: %s", e)
    
    return []


# ============================================================================
# Gene Ontology API
# ============================================================================

@dataclass
class GOAnnotation:
    """Gene Ontology annotation."""
    gene_symbol: str
    go_id: str
    go_name: str
    go_aspect: str  # P, F, C
    evidence_code: str
    qualifier: str
    assigned_by: str
    annotation_extension: str
    gene_product_form: str


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_go_annotations(gene_symbol: str, limit: int = 200) -> list[GOAnnotation]:
    """Fetch GO annotations for a gene from QuickGO."""
    try:
        _, payload = _request(
            "GET",
            f"{GO_API}/annotations",
            params={
                "geneProductId": gene_symbol,
                "limit": limit,
                "page": 1,
            },
        )
        
        annotations = []
        for item in payload.get("results", []):
            annotations.append(GOAnnotation(
                gene_symbol=gene_symbol,
                go_id=item.get("goId", ""),
                go_name=item.get("goName", ""),
                go_aspect=item.get("goAspect", ""),
                evidence_code=item.get("evidence", {}).get("code", ""),
                qualifier=",".join(item.get("qualifier", [])),
                assigned_by=item.get("assignedBy", ""),
                annotation_extension=item.get("annotationExtension", ""),
                gene_product_form=item.get("geneProductForm", ""),
            ))
        return annotations
    except Exception as e:
        logger.warning("QuickGO query failed for %s: %s", gene_symbol, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_go_enrichment(
    gene_symbols: list[str],
    go_aspect: str = "P",  # P=Process, F=Function, C=Component
    p_value: float = 0.05,
) -> list[dict[str, Any]]:
    """Perform GO enrichment analysis (using QuickGO's enrichment service)."""
    if not gene_symbols:
        return []
    
    # QuickGO doesn't have a direct enrichment endpoint, so we use a different approach
    # Collect all annotations and compute enrichment locally
    all_annotations = []
    for symbol in gene_symbols:
        annots = fetch_go_annotations(symbol)
        all_annotations.extend(annots)
    
    # Group by GO term
    term_counts: dict[str, dict] = {}
    for annot in all_annotations:
        if annot.go_aspect != go_aspect:
            continue
        key = f"{annot.go_id}:{annot.go_name}"
        if key not in term_counts:
            term_counts[key] = {"go_id": annot.go_id, "go_name": annot.go_name, "genes": set()}
        term_counts[key]["genes"].add(annot.gene_symbol)
    
    # Simple enrichment: terms with multiple genes from our list
    enriched = []
    for key, data in term_counts.items():
        if len(data["genes"]) >= 2:  # At least 2 genes from our list
            enriched.append({
                "go_id": data["go_id"],
                "go_name": data["go_name"],
                "aspect": go_aspect,
                "gene_count": len(data["genes"]),
                "genes": list(data["genes"]),
            })
    
    return sorted(enriched, key=lambda x: x["gene_count"], reverse=True)[:50]


# ============================================================================
# UniProt Integration
# ============================================================================

@dataclass
class UniProtEntry:
    """UniProt entry for a gene/protein."""
    uniprot_id: str
    gene_symbol: str
    protein_name: str
    organism: str
    sequence: str
    length: int
    function: str
    subcellular_location: str
    pathways: list[str]
    diseases: list[str]
    go_terms: list[str]


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_uniprot_entry(identifier: str) -> UniProtEntry | None:
    """Fetch UniProt entry by ID or gene symbol."""
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
        
        # Extract info
        genes = detail.get("genes", [])
        gene_symbol = ""
        if genes:
            gene_name = genes[0].get("geneName", {})
            gene_symbol = gene_name.get("value", "")
        
        protein_desc = detail.get("proteinDescription", {})
        rec_name = protein_desc.get("recommendedName", {})
        full_name = rec_name.get("fullName", {})
        protein_name = full_name.get("value", "")
        
        organism_obj = detail.get("organism", {})
        organism = organism_obj.get("scientificName", "")
        
        sequence_obj = detail.get("sequence", {})
        sequence = sequence_obj.get("value", "")
        length = sequence_obj.get("length", 0)
        
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
        
        # Pathways
        pathways = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") == "Reactome":
                pathways.append(xref.get("id", ""))
            elif xref.get("database") == "KEGG":
                pathways.append(xref.get("id", ""))
        
        # Diseases
        diseases = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") in ("MIM", "Orphanet"):
                diseases.append(xref.get("id", ""))
        
        # GO terms
        go_terms = []
        for xref in detail.get("uniProtKBCrossReferences", []):
            if xref.get("database") == "GO":
                go_terms.append(xref.get("id", ""))
        
        return UniProtEntry(
            uniprot_id=uniprot_id,
            gene_symbol=gene_symbol,
            protein_name=protein_name,
            organism=organism,
            sequence=sequence,
            length=length,
            function=function.strip(),
            subcellular_location=location.strip(),
            pathways=pathways,
            diseases=diseases,
            go_terms=go_terms,
        )
    except Exception as e:
        logger.warning("UniProt query failed for %s: %s", identifier, e)
        return None