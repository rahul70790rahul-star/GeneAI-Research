"""ClinicalTrials.gov API client for GeneAI Research."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

CT_GOV_BASE = "https://clinicaltrials.gov/api/v2"
CT_GOV_LEGACY_BASE = "https://clinicaltrials.gov/ct2"
_RATE_LIMIT_SECONDS = 0.3
_last_request_time = 0.0

_NCT_PATTERN = re.compile(r"^NCT\d{8}$")


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _ctgov_request(
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
        raise api_clients.DataSourceError(f"ClinicalTrials.gov request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("Clinical trial not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"ClinicalTrials.gov server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"ClinicalTrials.gov HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("ClinicalTrials.gov returned invalid JSON") from exc
    return response, payload


def _normalize_study(study: dict[str, Any]) -> dict[str, Any]:
    """Normalize ClinicalTrials.gov study record."""
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    conditions = protocol.get("conditionsModule", {})
    interventions = protocol.get("interventionsModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    outcomes = protocol.get("outcomesModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    contacts = protocol.get("contactsLocationsModule", {})

    return {
        "nct_id": identification.get("nctId"),
        "brief_title": identification.get("briefTitle"),
        "official_title": identification.get("officialTitle"),
        "overall_status": status.get("overallStatus"),
        "start_date": status.get("startDateStruct", {}).get("date"),
        "completion_date": status.get("completionDateStruct", {}).get("date"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "phase": design.get("phases", []),
        "study_type": design.get("studyType"),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "conditions": conditions.get("conditions", []),
        "keywords": conditions.get("keywords", []),
        "interventions": [
            {
                "type": iv.get("type"),
                "name": iv.get("name"),
                "description": iv.get("description"),
            }
            for iv in interventions.get("interventions", [])
        ],
        "sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "collaborators": [c.get("name") for c in sponsor.get("collaborators", [])],
        "locations": [
            {
                "facility": loc.get("facility"),
                "city": loc.get("city"),
                "state": loc.get("state"),
                "country": loc.get("country"),
                "status": loc.get("status"),
            }
            for loc in contacts.get("locations", [])
        ],
        "primary_outcomes": [
            {
                "measure": oc.get("measure"),
                "description": oc.get("description"),
                "time_frame": oc.get("timeFrame"),
            }
            for oc in outcomes.get("primaryOutcomes", [])
        ],
        "secondary_outcomes": [
            {
                "measure": oc.get("measure"),
                "description": oc.get("description"),
                "time_frame": oc.get("timeFrame"),
            }
            for oc in outcomes.get("secondaryOutcomes", [])
        ],
        "eligibility_criteria": eligibility.get("eligibilityCriteria"),
        "healthy_volunteers": eligibility.get("healthyVolunteers"),
        "sex": eligibility.get("sex"),
        "minimum_age": eligibility.get("minimumAge"),
        "maximum_age": eligibility.get("maximumAge"),
        "source": "ClinicalTrials.gov",
        "source_url": f"https://clinicaltrials.gov/ct2/show/{identification.get('nctId')}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_study_by_nct_id(nct_id: str) -> dict[str, Any] | None:
    """Retrieve clinical trial by NCT ID."""
    nct_id = nct_id.strip().upper()
    if not _NCT_PATTERN.fullmatch(nct_id):
        raise ValueError("NCT ID must be in format NCTxxxxxxxx")
    url = f"{CT_GOV_BASE}/studies/{nct_id}"
    try:
        _, payload = _ctgov_request("GET", url)
    except api_clients.DataSourceError:
        return None
    if not isinstance(payload, dict):
        return None
    return _normalize_study(payload)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_studies_by_condition(condition: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search clinical trials by condition/disease name."""
    condition = condition.strip()
    if not condition or len(condition) > 200:
        raise ValueError("Condition must be 1-200 characters")
    url = f"{CT_GOV_BASE}/studies"
    params = {
        "query.cond": condition,
        "pageSize": min(max(1, limit), 100),
        "filter.overallStatus": "Recruiting,Not yet recruiting,Active, not recruiting,Enrolling by invitation",
    }
    _, payload = _ctgov_request("GET", url, params=params)
    studies = payload.get("studies", [])
    results = []
    for study in studies:
        try:
            results.append(_normalize_study(study))
        except (ValueError, KeyError):
            continue
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_studies_by_intervention(intervention: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search clinical trials by intervention (drug) name."""
    intervention = intervention.strip()
    if not intervention or len(intervention) > 200:
        raise ValueError("Intervention must be 1-200 characters")
    url = f"{CT_GOV_BASE}/studies"
    params = {
        "query.intr": intervention,
        "pageSize": min(max(1, limit), 100),
    }
    _, payload = _ctgov_request("GET", url, params=params)
    studies = payload.get("studies", [])
    results = []
    for study in studies:
        try:
            results.append(_normalize_study(study))
        except (ValueError, KeyError):
            continue
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_studies_by_term(term: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search clinical trials by general term."""
    term = term.strip()
    if not term or len(term) > 200:
        raise ValueError("Search term must be 1-200 characters")
    url = f"{CT_GOV_BASE}/studies"
    params = {
        "query.term": term,
        "pageSize": min(max(1, limit), 100),
    }
    _, payload = _ctgov_request("GET", url, params=params)
    studies = payload.get("studies", [])
    results = []
    for study in studies:
        try:
            results.append(_normalize_study(study))
        except (ValueError, KeyError):
            continue
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_studies_by_drug_name(drug_name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get clinical trials for a specific drug name."""
    return search_studies_by_intervention(drug_name, limit=limit)


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_studies_by_target_gene(gene_symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get clinical trials targeting a specific gene."""
    gene_symbol = gene_symbol.strip()
    if not gene_symbol or len(gene_symbol) > 50:
        raise ValueError("Gene symbol must be 1-50 characters")
    return search_studies_by_term(f"{gene_symbol} gene", limit=limit)