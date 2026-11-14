"""ChEMBL REST API client for GeneAI Research."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
CHEMBL_WS_BASE = "https://www.ebi.ac.uk/chemblws"
_RATE_LIMIT_SECONDS = 0.15
_last_request_time = 0.0

_CHEMBL_ID_PATTERN = re.compile(r"^CHEMBL\d+$")


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _chembl_request(
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
        raise api_clients.DataSourceError(f"ChEMBL request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("ChEMBL record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"ChEMBL server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"ChEMBL HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("ChEMBL returned invalid JSON") from exc
    return response, payload


def _normalize_molecule(mol: dict[str, Any]) -> dict[str, Any]:
    """Normalize ChEMBL molecule record."""
    return {
        "chembl_id": mol.get("molecule_chembl_id"),
        "pref_name": mol.get("pref_name"),
        "molecule_type": mol.get("molecule_type"),
        "max_phase": mol.get("max_phase"),
        "first_approval": mol.get("first_approval"),
        "oral": mol.get("oral"),
        "parenteral": mol.get("parenteral"),
        "topical": mol.get("topical"),
        "black_box_warning": mol.get("black_box_warning"),
        "natural_product": mol.get("natural_product"),
        "first_in_class": mol.get("first_in_class"),
        "molecular_formula": mol.get("molecular_formula"),
        "molecular_weight": mol.get("molecular_weight"),
        "canonical_smiles": mol.get("molecule_structures", {}).get("canonical_smiles") if mol.get("molecule_structures") else None,
        "standard_inchi": mol.get("molecule_structures", {}).get("standard_inchi") if mol.get("molecule_structures") else None,
        "standard_inchikey": mol.get("molecule_structures", {}).get("standard_inchikey") if mol.get("molecule_structures") else None,
        "alogp": mol.get("molecule_properties", {}).get("alogp") if mol.get("molecule_properties") else None,
        "psa": mol.get("molecule_properties", {}).get("psa") if mol.get("molecule_properties") else None,
        "hba": mol.get("molecule_properties", {}).get("hba") if mol.get("molecule_properties") else None,
        "hbd": mol.get("molecule_properties", {}).get("hbd") if mol.get("molecule_properties") else None,
        "rtb": mol.get("molecule_properties", {}).get("rtb") if mol.get("molecule_properties") else None,
        "ro3_pass": mol.get("molecule_properties", {}).get("ro3_pass") if mol.get("molecule_properties") else None,
        "num_ro5_violations": mol.get("num_ro5_violations"),
        "source": "ChEMBL",
        "source_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{mol.get('molecule_chembl_id')}/",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_molecule_by_chembl_id(chembl_id: str) -> dict[str, Any] | None:
    """Retrieve molecule record by ChEMBL ID."""
    chembl_id = chembl_id.strip().upper()
    if not _CHEMBL_ID_PATTERN.fullmatch(chembl_id):
        raise ValueError("ChEMBL ID must be in format CHEMBLxxxxxx")
    url = f"{CHEMBL_BASE}/molecule/{chembl_id}.json"
    _, payload = _chembl_request("GET", url)
    if not isinstance(payload, dict):
        return None
    return _normalize_molecule(payload)


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def search_molecules_by_name(name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search molecules by name (partial match)."""
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Molecule name must be 1-200 characters")
    url = f"{CHEMBL_BASE}/molecule.json"
    params = {
        "pref_name__icontains": name,
        "limit": min(max(1, limit), 100),
    }
    _, payload = _chembl_request("GET", url, params=params)
    molecules = payload.get("molecules", [])
    results = []
    for mol in molecules:
        try:
            results.append(_normalize_molecule(mol))
        except (ValueError, KeyError):
            continue
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_molecule_by_inchikey(inchikey: str) -> dict[str, Any] | None:
    """Retrieve molecule by InChIKey."""
    inchikey = inchikey.strip().upper()
    if not re.fullmatch(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$", inchikey):
        raise ValueError("Invalid InChIKey format")
    url = f"{CHEMBL_BASE}/molecule.json"
    params = {"molecule_structures__standard_inchikey": inchikey, "limit": 1}
    _, payload = _chembl_request("GET", url, params=params)
    molecules = payload.get("molecules", [])
    if not molecules:
        return None
    return _normalize_molecule(molecules[0])


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_molecule_by_smiles(smiles: str) -> dict[str, Any] | None:
    """Retrieve molecule by SMILES (exact match via structure search)."""
    smiles = smiles.strip()
    if not smiles or len(smiles) > 500:
        raise ValueError("SMILES must be 1-500 characters")
    url = f"{CHEMBL_BASE}/molecule.json"
    params = {"molecule_structures__canonical_smiles": smiles, "limit": 1}
    _, payload = _chembl_request("GET", url, params=params)
    molecules = payload.get("molecules", [])
    if not molecules:
        return None
    return _normalize_molecule(molecules[0])


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_molecule_synonyms(chembl_id: str) -> list[str]:
    """Get molecule synonyms."""
    chembl_id = chembl_id.strip().upper()
    url = f"{CHEMBL_BASE}/molecule/{chembl_id}/synonyms.json"
    _, payload = _chembl_request("GET", url)
    synonyms = payload.get("molecule_synonyms", [])
    return [s.get("molecule_synonym") for s in synonyms if s.get("molecule_synonym")][:50]


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_molecule_activities(chembl_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get bioactivity data for a molecule."""
    chembl_id = chembl_id.strip().upper()
    url = f"{CHEMBL_BASE}/activity.json"
    params = {
        "molecule_chembl_id": chembl_id,
        "limit": min(max(1, limit), 500),
        "order_by": "-pchembl_value",
    }
    _, payload = _chembl_request("GET", url, params=params)
    activities = payload.get("activities", [])
    results = []
    for act in activities:
        results.append({
            "activity_id": act.get("activity_id"),
            "assay_chembl_id": act.get("assay_chembl_id"),
            "target_chembl_id": act.get("target_chembl_id"),
            "standard_type": act.get("standard_type"),
            "standard_value": act.get("standard_value"),
            "standard_units": act.get("standard_units"),
            "standard_relation": act.get("standard_relation"),
            "pchembl_value": act.get("pchembl_value"),
            "assay_type": act.get("assay_type"),
            "assay_description": act.get("assay_description"),
            "target_name": act.get("target_pref_name"),
            "organism": act.get("target_organism"),
            "source": "ChEMBL Activity",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_molecule_targets(chembl_id: str) -> list[dict[str, Any]]:
    """Get protein targets for a molecule from activities."""
    activities = get_molecule_activities(chembl_id, limit=500)
    targets = {}
    for act in activities:
        target_id = act.get("target_chembl_id")
        if not target_id:
            continue
        if target_id not in targets:
            targets[target_id] = {
                "target_chembl_id": target_id,
                "target_name": act.get("target_name"),
                "organism": act.get("organism"),
                "activities": [],
            }
        targets[target_id]["activities"].append({
            "type": act.get("standard_type"),
            "value": act.get("standard_value"),
            "units": act.get("standard_units"),
            "pchembl": act.get("pchembl_value"),
            "relation": act.get("standard_relation"),
        })
    return list(targets.values())


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_target_by_chembl_id(target_chembl_id: str) -> dict[str, Any] | None:
    """Retrieve target record by ChEMBL target ID."""
    target_chembl_id = target_chembl_id.strip().upper()
    if not re.fullmatch(r"^CHEMBL\d+$", target_chembl_id):
        raise ValueError("ChEMBL target ID must be in format CHEMBLxxxxxx")
    url = f"{CHEMBL_BASE}/target/{target_chembl_id}.json"
    try:
        _, payload = _chembl_request("GET", url)
    except api_clients.DataSourceError:
        return None
    if not isinstance(payload, dict):
        return None
    target_components = payload.get("target_components", [])
    uniprot_ids = []
    gene_symbols = []
    for comp in target_components:
        if isinstance(comp, dict):
            uniprot_ids.append(comp.get("accession"))
            gene_symbols.append(comp.get("symbol"))
    return {
        "target_chembl_id": payload.get("target_chembl_id"),
        "pref_name": payload.get("pref_name"),
        "target_type": payload.get("target_type"),
        "organism": payload.get("organism"),
        "uniprot_ids": [u for u in uniprot_ids if u],
        "gene_symbols": [g for g in gene_symbols if g],
        "description": payload.get("description"),
        "source": "ChEMBL Target",
        "source_url": f"https://www.ebi.ac.uk/chembl/target_report_card/{target_chembl_id}/",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def search_targets_by_name(name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search targets by name."""
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Target name must be 1-200 characters")
    url = f"{CHEMBL_BASE}/target.json"
    params = {
        "pref_name__icontains": name,
        "limit": min(max(1, limit), 100),
    }
    _, payload = _chembl_request("GET", url, params=params)
    targets = payload.get("targets", [])
    results = []
    for t in targets:
        results.append({
            "target_chembl_id": t.get("target_chembl_id"),
            "pref_name": t.get("pref_name"),
            "target_type": t.get("target_type"),
            "organism": t.get("organism"),
            "source": "ChEMBL Target",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_drug_indications(chembl_id: str) -> list[dict[str, Any]]:
    """Get drug indications (disease associations) for a molecule."""
    chembl_id = chembl_id.strip().upper()
    url = f"{CHEMBL_BASE}/drug_indication.json"
    params = {"molecule_chembl_id": chembl_id, "limit": 100}
    try:
        _, payload = _chembl_request("GET", url, params=params)
    except api_clients.DataSourceError:
        return []
    indications = payload.get("drug_indications", [])
    results = []
    for ind in indications:
        results.append({
            "indication_ref": ind.get("indication_ref"),
            "mesh_id": ind.get("mesh_id"),
            "mesh_heading": ind.get("mesh_heading"),
            "efo_id": ind.get("efo_id"),
            "efo_term": ind.get("efo_term"),
            "max_phase_for_ind": ind.get("max_phase_for_ind"),
            "source": "ChEMBL Drug Indication",
        })
    return results