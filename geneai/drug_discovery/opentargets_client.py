"""Open Targets Platform API client for GeneAI Research."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

OPENTARGETS_BASE = "https://api.platform.opentargets.org/api/v4"
OPENTARGETS_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"
_RATE_LIMIT_SECONDS = 0.2
_last_request_time = 0.0


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _opentargets_request(
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
        raise api_clients.DataSourceError(f"Open Targets request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("Open Targets record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"Open Targets server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"Open Targets HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("Open Targets returned invalid JSON") from exc
    return response, payload


def _opentargets_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute GraphQL query against Open Targets."""
    _rate_limit()
    headers = {
        "User-Agent": "GeneAIResearch/0.2 (scientific research client)",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        response = requests.post(OPENTARGETS_GRAPHQL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        raise api_clients.DataSourceError(f"Open Targets GraphQL request failed: {exc}") from exc

    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"Open Targets server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"Open Targets HTTP {response.status_code}: {exc}") from exc

    try:
        data = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("Open Targets returned invalid JSON") from exc

    if "errors" in data:
        raise api_clients.DataSourceError(f"Open Targets GraphQL errors: {data['errors']}")
    return data.get("data", {})


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_targets(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search targets by name or gene symbol."""
    query = query.strip()
    if not query or len(query) > 200:
        raise ValueError("Search query must be 1-200 characters")
    graphql_query = """
    query SearchTargets($queryString: String!, $page: Int!) {
        search(queryString: $queryString, page: {index: 0, size: $page}) {
            targets {
                id
                approvedSymbol
                approvedName
                biotype
                proteinIds {
                    uniprot
                }
                functionDescriptions
                tractability {
                    smallMolecule
                    antibody
                }
                associatedDiseasesCount
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"queryString": query, "page": min(max(1, limit), 50)})
    targets = data.get("search", {}).get("targets", [])
    results = []
    for t in targets:
        results.append({
            "target_id": t.get("id"),
            "approved_symbol": t.get("approvedSymbol"),
            "approved_name": t.get("approvedName"),
            "biotype": t.get("biotype"),
            "uniprot_ids": t.get("proteinIds", {}).get("uniprot", []),
            "function_descriptions": t.get("functionDescriptions", []),
            "tractability_small_molecule": t.get("tractability", {}).get("smallMolecule"),
            "tractability_antibody": t.get("tractability", {}).get("antibody"),
            "associated_diseases_count": t.get("associatedDiseasesCount"),
            "source": "Open Targets",
            "source_url": f"https://platform.opentargets.org/target/{t.get('id')}",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_target_by_id(target_id: str) -> dict[str, Any] | None:
    """Get detailed target information by Ensembl ID."""
    target_id = target_id.strip()
    if not target_id or len(target_id) > 100:
        raise ValueError("Target ID must be 1-100 characters")
    graphql_query = """
    query GetTarget($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            id
            approvedSymbol
            approvedName
            biotype
            proteinIds {
                uniprot
            }
            functionDescriptions
            tractability {
                smallMolecule
                antibody
            }
            associatedDiseasesCount
            knownDrugsCount
            targetClass
            targetFromSourceId
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"ensemblId": target_id})
    target = data.get("target")
    if not target:
        return None
    return {
        "target_id": target.get("id"),
        "approved_symbol": target.get("approvedSymbol"),
        "approved_name": target.get("approvedName"),
        "biotype": target.get("biotype"),
        "uniprot_ids": target.get("proteinIds", {}).get("uniprot", []),
        "function_descriptions": target.get("functionDescriptions", []),
        "tractability_small_molecule": target.get("tractability", {}).get("smallMolecule"),
        "tractability_antibody": target.get("tractability", {}).get("antibody"),
        "associated_diseases_count": target.get("associatedDiseasesCount"),
        "known_drugs_count": target.get("knownDrugsCount"),
        "target_class": target.get("targetClass"),
        "source": "Open Targets",
        "source_url": f"https://platform.opentargets.org/target/{target.get('id')}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_target_diseases(target_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get disease associations for a target."""
    target_id = target_id.strip()
    graphql_query = """
    query TargetDiseases($ensemblId: String!, $page: Int!) {
        target(ensemblId: $ensemblId) {
            knownDrugs {
                rows {
                    diseaseId
                    diseaseName
                    score
                    phase
                    drugId
                    drugName
                    mechanismOfAction
                }
            }
            associatedDiseases(page: {index: 0, size: $page}) {
                rows {
                    diseaseId
                    diseaseName
                    score
                }
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"ensemblId": target_id, "page": min(max(1, limit), 100)})
    target = data.get("target", {})
    results = []
    for row in target.get("associatedDiseases", {}).get("rows", []):
        results.append({
            "disease_id": row.get("diseaseId"),
            "disease_name": row.get("diseaseName"),
            "association_score": row.get("score"),
            "evidence_type": "genetic_association",
            "source": "Open Targets",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_target_drugs(target_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get known drugs for a target."""
    target_id = target_id.strip()
    graphql_query = """
    query TargetDrugs($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            knownDrugs {
                rows {
                    drugId
                    drugName
                    phase
                    mechanismOfAction
                    targetName
                    diseaseId
                    diseaseName
                    score
                }
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"ensemblId": target_id})
    target = data.get("target", {})
    results = []
    for row in target.get("knownDrugs", {}).get("rows", []):
        results.append({
            "drug_id": row.get("drugId"),
            "drug_name": row.get("drugName"),
            "phase": row.get("phase"),
            "mechanism_of_action": row.get("mechanismOfAction"),
            "target_name": row.get("targetName"),
            "disease_id": row.get("diseaseId"),
            "disease_name": row.get("diseaseName"),
            "score": row.get("score"),
            "source": "Open Targets",
            "source_url": f"https://platform.opentargets.org/drug/{row.get('drugId')}",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_diseases(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search diseases by name."""
    query = query.strip()
    if not query or len(query) > 200:
        raise ValueError("Search query must be 1-200 characters")
    graphql_query = """
    query SearchDiseases($queryString: String!, $page: Int!) {
        search(queryString: $queryString, page: {index: 0, size: $page}) {
            diseases {
                id
                name
                description
                therapeuticAreas
                parents {
                    id
                    name
                }
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"queryString": query, "page": min(max(1, limit), 50)})
    diseases = data.get("search", {}).get("diseases", [])
    results = []
    for d in diseases:
        results.append({
            "disease_id": d.get("id"),
            "disease_name": d.get("name"),
            "description": d.get("description"),
            "therapeutic_areas": d.get("therapeuticAreas", []),
            "parent_diseases": [{"id": p.get("id"), "name": p.get("name")} for p in d.get("parents", [])],
            "source": "Open Targets",
            "source_url": f"https://platform.opentargets.org/disease/{d.get('id')}",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_disease_by_id(disease_id: str) -> dict[str, Any] | None:
    """Get detailed disease information."""
    disease_id = disease_id.strip()
    if not disease_id or len(disease_id) > 100:
        raise ValueError("Disease ID must be 1-100 characters")
    graphql_query = """
    query GetDisease($efoId: String!) {
        disease(efoId: $efoId) {
            id
            name
            description
            therapeuticAreas
            knownDrugsCount
            associatedTargetsCount
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"efoId": disease_id})
    disease = data.get("disease")
    if not disease:
        return None
    return {
        "disease_id": disease.get("id"),
        "disease_name": disease.get("name"),
        "description": disease.get("description"),
        "therapeutic_areas": disease.get("therapeuticAreas", []),
        "known_drugs_count": disease.get("knownDrugsCount"),
        "associated_targets_count": disease.get("associatedTargetsCount"),
        "source": "Open Targets",
        "source_url": f"https://platform.opentargets.org/disease/{disease.get('id')}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_disease_targets(disease_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get target associations for a disease."""
    disease_id = disease_id.strip()
    graphql_query = """
    query DiseaseTargets($efoId: String!, $page: Int!) {
        disease(efoId: $efoId) {
            associatedTargets(page: {index: 0, size: $page}) {
                rows {
                    target {
                        id
                        approvedSymbol
                        approvedName
                        biotype
                    }
                    score
                }
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"efoId": disease_id, "page": min(max(1, limit), 100)})
    disease = data.get("disease", {})
    results = []
    for row in disease.get("associatedTargets", {}).get("rows", []):
        target = row.get("target", {})
        results.append({
            "target_id": target.get("id"),
            "approved_symbol": target.get("approvedSymbol"),
            "approved_name": target.get("approvedName"),
            "biotype": target.get("biotype"),
            "association_score": row.get("score"),
            "source": "Open Targets",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_drug_by_id(drug_id: str) -> dict[str, Any] | None:
    """Get drug information by ChEMBL ID."""
    drug_id = drug_id.strip()
    if not drug_id or len(drug_id) > 100:
        raise ValueError("Drug ID must be 1-100 characters")
    graphql_query = """
    query GetDrug($chemblId: String!) {
        drug(chemblId: $chemblId) {
            id
            name
            description
            drugType
            mechanismsOfAction {
                target {
                    id
                    approvedSymbol
                }
                actionType
                mechanismOfAction
            }
            indications {
                disease {
                    id
                    name
                }
                maxPhaseForInd
            }
            yearOfFirstApproval
            crossReferences {
                drugbankId
            }
        }
    }
    """
    data = _opentargets_graphql(graphql_query, {"chemblId": drug_id})
    drug = data.get("drug")
    if not drug:
        return None
    return {
        "drug_id": drug.get("id"),
        "drug_name": drug.get("name"),
        "description": drug.get("description"),
        "drug_type": drug.get("drugType"),
        "mechanisms_of_action": [
            {
                "target_id": m.get("target", {}).get("id"),
                "target_symbol": m.get("target", {}).get("approvedSymbol"),
                "action_type": m.get("actionType"),
                "mechanism": m.get("mechanismOfAction"),
            }
            for m in drug.get("mechanismsOfAction", [])
        ],
        "indications": [
            {
                "disease_id": i.get("disease", {}).get("id"),
                "disease_name": i.get("disease", {}).get("name"),
                "max_phase": i.get("maxPhaseForInd"),
            }
            for i in drug.get("indications", [])
        ],
        "year_first_approval": drug.get("yearOfFirstApproval"),
        "drugbank_id": drug.get("crossReferences", {}).get("drugbankId"),
        "source": "Open Targets",
        "source_url": f"https://platform.opentargets.org/drug/{drug.get('id')}",
    }