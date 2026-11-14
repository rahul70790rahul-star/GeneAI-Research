"""PubChem REST API client for GeneAI Research."""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote

import requests

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
PUBCHEM_PUG_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_RATE_LIMIT_SECONDS = 0.2
_last_request_time = 0.0

_CID_PATTERN = re.compile(r"^\d+$")
_SID_PATTERN = re.compile(r"^\d+$")
_INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _pubchem_request(
    method: str,
    url: str,
    *,
    timeout: int = 30,
    expect_json: bool = True,
    **kwargs: Any,
) -> tuple[requests.Response, Any]:
    _rate_limit()
    headers = {"User-Agent": "GeneAIResearch/0.2 (scientific research client)"}
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise api_clients.DataSourceError(f"PubChem request failed: {exc}") from exc

    if response.status_code == 404:
        raise api_clients.DataSourceError("PubChem record not found")
    if response.status_code >= 500:
        raise api_clients.DataSourceError(f"PubChem server error: {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise api_clients.DataSourceError(f"PubChem HTTP {response.status_code}: {exc}") from exc

    if not expect_json:
        return response, response.text
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise api_clients.DataSourceError("PubChem returned invalid JSON") from exc
    return response, payload


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_compound_by_cid(cid: str | int) -> dict[str, Any] | None:
    """Retrieve compound record by PubChem CID."""
    cid_str = str(cid)
    if not _CID_PATTERN.fullmatch(cid_str):
        raise ValueError("CID must be numeric")
    url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,InChI,InChIKey,IUPACName,XLogP3,ExactMass,TopologicalPolarSurfaceArea,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,Charge,Complexity/JSON"
    _, payload = _pubchem_request("GET", url)
    props = payload.get("PropertyTable", {}).get("Properties", [])
    if not props:
        return None
    prop = props[0]
    return {
        "cid": int(prop.get("CID", cid_str)),
        "molecular_formula": prop.get("MolecularFormula"),
        "molecular_weight": prop.get("MolecularWeight"),
        "canonical_smiles": prop.get("CanonicalSMILES"),
        "isomeric_smiles": prop.get("IsomericSMILES"),
        "inchi": prop.get("InChI"),
        "inchikey": prop.get("InChIKey"),
        "iupac_name": prop.get("IUPACName"),
        "xlogp3": prop.get("XLogP3"),
        "exact_mass": prop.get("ExactMass"),
        "tpsa": prop.get("TopologicalPolarSurfaceArea"),
        "hbond_donor_count": prop.get("HBondDonorCount"),
        "hbond_acceptor_count": prop.get("HBondAcceptorCount"),
        "rotatable_bond_count": prop.get("RotatableBondCount"),
        "charge": prop.get("Charge"),
        "complexity": prop.get("Complexity"),
        "source": "PubChem",
        "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid_str}",
    }


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_compound_by_name(name: str) -> list[dict[str, Any]]:
    """Search compounds by name (returns list of CIDs then fetches details)."""
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Compound name must be 1-200 characters")
    url = f"{PUBCHEM_BASE}/compound/name/{quote(name)}/cids/JSON"
    _, payload = _pubchem_request("GET", url)
    cids = payload.get("IdentifierList", {}).get("CID", [])
    results = []
    for cid in cids[:10]:
        try:
            compound = get_compound_by_cid(cid)
            if compound:
                results.append(compound)
        except api_clients.DataSourceError:
            continue
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_compound_by_inchikey(inchikey: str) -> dict[str, Any] | None:
    """Retrieve compound by InChIKey."""
    inchikey = inchikey.strip().upper()
    if not _INCHIKEY_PATTERN.fullmatch(inchikey):
        raise ValueError("Invalid InChIKey format")
    url = f"{PUBCHEM_BASE}/compound/inchikey/{inchikey}/cids/JSON"
    _, payload = _pubchem_request("GET", url)
    cids = payload.get("IdentifierList", {}).get("CID", [])
    if not cids:
        return None
    return get_compound_by_cid(cids[0])


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def get_compound_by_smiles(smiles: str) -> dict[str, Any] | None:
    """Retrieve compound by SMILES (via fastsubstructure search)."""
    smiles = smiles.strip()
    if not smiles or len(smiles) > 500:
        raise ValueError("SMILES must be 1-500 characters")
    url = f"{PUBCHEM_BASE}/compound/fastsubstructure_2d/smiles/{quote(smiles)}/cids/JSON"
    try:
        _, payload = _pubchem_request("POST", url, data={"smiles": smiles})
    except api_clients.DataSourceError:
        return None
    cids = payload.get("IdentifierList", {}).get("CID", [])
    if not cids:
        return None
    return get_compound_by_cid(cids[0])


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_compound_synonyms(cid: str | int) -> list[str]:
    """Get compound synonyms."""
    cid_str = str(cid)
    url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/synonyms/JSON"
    _, payload = _pubchem_request("GET", url)
    info = payload.get("InformationList", {}).get("Information", [])
    if info:
        return info[0].get("Synonym", [])[:50]
    return []


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_compound_assays(cid: str | int, limit: int = 20) -> list[dict[str, Any]]:
    """Get bioassay summaries for a compound."""
    cid_str = str(cid)
    url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/assaysummary/JSON"
    _, payload = _pubchem_request("GET", url)
    assays = payload.get("AssaySummary", {}).get("Assay", [])
    results = []
    for assay in assays[:limit]:
        results.append({
            "aid": assay.get("AID"),
            "name": assay.get("Name"),
            "description": assay.get("Description"),
            "target": assay.get("Target"),
            "source": "PubChem BioAssay",
            "source_url": f"https://pubchem.ncbi.nlm.nih.gov/assay/{assay.get('AID')}",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_compound_targets(cid: str | int) -> list[dict[str, Any]]:
    """Get protein targets from PubChem bioassays."""
    cid_str = str(cid)
    url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/targets/JSON"
    try:
        _, payload = _pubchem_request("GET", url)
    except api_clients.DataSourceError:
        return []
    targets = payload.get("Target", {}).get("Target", [])
    results = []
    for target in targets[:50]:
        results.append({
            "target_id": target.get("TargetID"),
            "target_name": target.get("TargetName"),
            "organism": target.get("Organism"),
            "gene_symbol": target.get("GeneSymbol"),
            "uniprot_id": target.get("UniProtID"),
            "source": "PubChem Target",
        })
    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_compound_patents(cid: str | int, limit: int = 20) -> list[dict[str, Any]]:
    """Get patent information for a compound."""
    cid_str = str(cid)
    url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/patents/JSON"
    try:
        _, payload = _pubchem_request("GET", url)
    except api_clients.DataSourceError:
        return []
    patents = payload.get("PatentList", {}).get("Patent", [])
    results = []
    for patent in patents[:limit]:
        results.append({
            "patent_id": patent.get("PatentID"),
            "title": patent.get("Title"),
            "country": patent.get("Country"),
            "source": "PubChem Patent",
        })
    return results