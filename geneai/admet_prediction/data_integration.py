"""Data Integration - Module 4: Integration with scientific data sources."""
from __future__ import annotations

import logging
import time
import threading
from typing import Any
from urllib.parse import urlparse

import requests

from geneai.drug_discovery.cache import ttl_cache
from geneai.config import PUBMED_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
UNIPROT_BASE = "https://rest.uniprot.org"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_RATE_INTERVALS = {
    "pubchem.ncbi.nlm.nih.gov": 0.2,
    "www.ebi.ac.uk": 0.15,
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
        "User-Agent": "GeneAIResearch/0.4 (ADMET prediction; contact not configured)",
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


@ttl_cache(ttl_seconds=86_400, max_entries=512)
def get_pubchem_compound_by_cid(cid: str) -> dict[str, Any] | None:
    """Get compound data from PubChem by CID."""
    cid = cid.strip()
    if not cid.isdigit():
        raise ValueError("CID must be numeric")
    
    try:
        _, payload = _request(
            "GET",
            f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
            "MolecularWeight,LogP,TPSA,HBD,HBA,RotatableBondCount,"
            "MolecularFormula,ExactMass,Charge,IUPACName,CanonicalSMILES,IsomericSMILES,InChI,InChIKey/JSON",
        )
        
        props = payload.get("PropertyTable", {}).get("Properties", [])
        if not props:
            return None
        
        prop = props[0]
        return {
            "cid": prop.get("CID"),
            "molecular_weight": prop.get("MolecularWeight"),
            "logp": prop.get("LogP"),
            "tpsa": prop.get("TPSA"),
            "hbd": prop.get("HBD"),
            "hba": prop.get("HBA"),
            "rotatable_bonds": prop.get("RotatableBondCount"),
            "molecular_formula": prop.get("MolecularFormula"),
            "exact_mass": prop.get("ExactMass"),
            "charge": prop.get("Charge"),
            "iupac_name": prop.get("IUPACName"),
            "canonical_smiles": prop.get("CanonicalSMILES"),
            "isomeric_smiles": prop.get("IsomericSMILES"),
            "inchi": prop.get("InChI"),
            "inchikey": prop.get("InChIKey"),
            "source": "PubChem",
            "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        }
    except Exception as e:
        logger.warning("PubChem CID lookup failed for %s: %s", cid, e)
        return None


@ttl_cache(ttl_seconds=86_400, max_entries=512)
def get_pubchem_compound_by_smiles(smiles: str) -> dict[str, Any] | None:
    """Get compound data from PubChem by SMILES."""
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("SMILES cannot be empty")
    
    try:
        _, payload = _request(
            "POST",
            f"{PUBCHEM_BASE}/compound/smiles/property/"
            "MolecularWeight,LogP,TPSA,HBD,HBA,RotatableBondCount,"
            "MolecularFormula,ExactMass,Charge,IUPACName,CanonicalSMILES,IsomericSMILES,InChI,InChIKey/JSON",
            data={"smiles": smiles},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        props = payload.get("PropertyTable", {}).get("Properties", [])
        if not props:
            return None
        
        prop = props[0]
        return {
            "cid": prop.get("CID"),
            "molecular_weight": prop.get("MolecularWeight"),
            "logp": prop.get("LogP"),
            "tpsa": prop.get("TPSA"),
            "hbd": prop.get("HBD"),
            "hba": prop.get("HBA"),
            "rotatable_bonds": prop.get("RotatableBondCount"),
            "molecular_formula": prop.get("MolecularFormula"),
            "exact_mass": prop.get("ExactMass"),
            "charge": prop.get("Charge"),
            "iupac_name": prop.get("IUPACName"),
            "canonical_smiles": prop.get("CanonicalSMILES"),
            "isomeric_smiles": prop.get("IsomericSMILES"),
            "inchi": prop.get("InChI"),
            "inchikey": prop.get("InChIKey"),
            "source": "PubChem",
            "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{prop.get('CID')}",
        }
    except Exception as e:
        logger.warning("PubChem SMILES lookup failed: %s", e)
        return None


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def search_pubchem_by_name(name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search PubChem by compound name."""
    name = name.strip()
    if not name:
        raise ValueError("Name cannot be empty")
    
    try:
        _, payload = _request(
            "GET",
            f"{PUBCHEM_BASE}/compound/name/{name}/cids/JSON",
        )
        
        cids = payload.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return []
        
        results = []
        for cid in cids[:limit]:
            compound = get_pubchem_compound_by_cid(str(cid))
            if compound:
                compound["search_name"] = name
                results.append(compound)
        
        return results
    except Exception as e:
        logger.warning("PubChem name search failed for %s: %s", name, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_chembl_molecule_by_chembl_id(chembl_id: str) -> dict[str, Any] | None:
    """Get molecule data from ChEMBL by ChEMBL ID."""
    chembl_id = chembl_id.strip().upper()
    if not chembl_id.startswith("CHEMBL"):
        raise ValueError("Invalid ChEMBL ID format")
    
    try:
        _, payload = _request(
            "GET",
            f"{CHEMBL_BASE}/molecule/{chembl_id}.json",
        )
        
        molecule = payload.get("molecule_properties", {}) if isinstance(payload, dict) else {}
        if not molecule:
            return None
        
        # Get parent molecule if exists
        parent_chembl_id = molecule.get("parent_chembl_id")
        if parent_chembl_id and parent_chembl_id != chembl_id:
            parent_data = get_chembl_molecule_by_chembl_id(parent_chembl_id)
            if parent_data:
                return parent_data
        
        return {
            "chembl_id": chembl_id,
            "pref_name": molecule.get("pref_name"),
            "molecular_weight": molecule.get("molecular_weight"),
            "logp": molecule.get("alogp"),
            "tpsa": molecule.get("psa"),
            "hbd": molecule.get("hbd"),
            "hba": molecule.get("hba"),
            "rotatable_bonds": molecule.get("rtb"),
            "molecular_formula": molecule.get("molecular_formula"),
            "canonical_smiles": molecule.get("canonical_smiles"),
            "standard_inchi": molecule.get("standard_inchi"),
            "standard_inchikey": molecule.get("standard_inchikey"),
            "max_phase": molecule.get("max_phase"),
            "therapeutic_flag": molecule.get("therapeutic_flag"),
            "natural_product": molecule.get("natural_product"),
            "source": "ChEMBL",
            "source_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
        }
    except Exception as e:
        logger.warning("ChEMBL lookup failed for %s: %s", chembl_id, e)
        return None


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def search_chembl_by_smiles(smiles: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search ChEMBL by SMILES."""
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("SMILES cannot be empty")
    
    try:
        _, payload = _request(
            "GET",
            f"{CHEMBL_BASE}/similarity/{smiles}/80.json",
            params={"limit": limit},
        )
        
        molecules = payload.get("molecules", []) if isinstance(payload, dict) else []
        results = []
        
        for mol in molecules:
            mol_props = mol.get("molecule_properties", {}) if isinstance(mol, dict) else {}
            chembl_id = mol_props.get("chembl_id")
            if chembl_id:
                compound = get_chembl_molecule_by_chembl_id(chembl_id)
                if compound:
                    compound["similarity"] = mol.get("similarity")
                    results.append(compound)
        
        return results
    except Exception as e:
        logger.warning("ChEMBL SMILES search failed: %s", e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def get_uniprot_entry(uniprot_id: str) -> dict[str, Any] | None:
    """Get UniProt entry by ID."""
    uniprot_id = uniprot_id.strip()
    if not uniprot_id:
        raise ValueError("UniProt ID cannot be empty")
    
    try:
        _, payload = _request(
            "GET",
            f"{UNIPROT_BASE}/uniprotkb/{uniprot_id}.json",
        )
        
        if not isinstance(payload, dict):
            return None
        
        # Extract relevant info
        sequence = payload.get("sequence", {})
        genes = payload.get("genes", [])
        gene_symbol = ""
        if genes and isinstance(genes[0], dict):
            gene_name = genes[0].get("geneName", {})
            gene_symbol = gene_name.get("value", "")
        
        return {
            "uniprot_id": uniprot_id,
            "gene_symbol": gene_symbol,
            "protein_name": (
                payload.get("proteinDescription", {})
                .get("recommendedName", {})
                .get("fullName", {})
                .get("value", "")
            ),
            "sequence": sequence.get("value", ""),
            "sequence_length": sequence.get("length", 0),
            "organism": (
                payload.get("organism", {})
                .get("scientificName", "")
            ),
            "function": _extract_function(payload),
            "subcellular_location": _extract_location(payload),
            "source": "UniProt",
            "source_url": f"https://www.uniprot.org/uniprotkb/{uniprot_id}/entry",
        }
    except Exception as e:
        logger.warning("UniProt lookup failed for %s: %s", uniprot_id, e)
        return None


def _extract_function(payload: dict) -> str:
    """Extract function from UniProt entry."""
    functions = []
    for comment in payload.get("comments", []) if isinstance(payload.get("comments"), list) else []:
        if comment.get("commentType") == "FUNCTION":
            texts = comment.get("texts", [])
            for text in texts:
                if isinstance(text, dict) and text.get("value"):
                    functions.append(text["value"])
    return " ".join(functions)


def _extract_location(payload: dict) -> str:
    """Extract subcellular location from UniProt entry."""
    locations = []
    for comment in payload.get("comments", []) if isinstance(payload.get("comments"), list) else []:
        if comment.get("commentType") == "SUBCELLULAR LOCATION":
            texts = comment.get("texts", [])
            for text in texts:
                if isinstance(text, dict) and text.get("value"):
                    locations.append(text["value"])
    return " ".join(locations)


def merge_compound_data(
    pubchem_data: dict[str, Any] | None,
    chembl_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge compound data from multiple sources, prioritizing measured values."""
    merged = {
        "sources": [],
        "data_quality": "predicted",
    }
    
    # Priority: ChEMBL (curated) > PubChem (computed/measured)
    primary = chembl_data or pubchem_data
    secondary = pubchem_data if primary is chembl_data else chembl_data
    
    if primary:
        merged["sources"].append(primary.get("source", "unknown"))
        merged["data_quality"] = "measured" if primary.get("source") == "ChEMBL" else "computed"
        
        # Copy primary data
        for key, value in primary.items():
            if key not in ("source", "source_url", "search_name", "similarity"):
                merged[key] = value
    
    if secondary:
        if secondary.get("source") not in merged["sources"]:
            merged["sources"].append(secondary.get("source", "unknown"))
        
        # Fill missing values from secondary
        for key, value in secondary.items():
            if key not in ("source", "source_url", "search_name", "similarity"):
                if key not in merged or merged[key] is None:
                    merged[key] = value
    
    return merged


def fetch_admet_training_data(
    endpoint: str,
    source: str = "chembl",
    limit: int = 1000,
) -> tuple[list[str], list[int]]:
    """Fetch training data for ADMET endpoint from public sources.
    
    This is a placeholder for integration with public ADMET datasets.
    In production, this would connect to:
    - ChEMBL bioactivity assays for CYP endpoints
    - PubChem AID assays for toxicity endpoints
    - ADMETlab/admetSAR databases
    - Literature curated datasets
    
    Args:
        endpoint: ADMET endpoint name
        source: Data source
        limit: Maximum records
        
    Returns:
        Tuple of (SMILES list, labels)
    """
    # Placeholder - would need actual data pipeline
    logger.warning("Training data fetch not implemented for %s from %s", endpoint, source)
    return [], []