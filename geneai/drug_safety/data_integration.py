"""Data integration for drug safety and toxicity prediction."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from geneai.drug_discovery.cache import ttl_cache
from geneai.config import PUBMED_TIMEOUT_SECONDS
from geneai.utils import DataSourceError, RateLimiter
from geneai.utils.api_client_base import BaseAPIClient, APIClientConfig

logger = logging.getLogger(__name__)

# Create shared clients
_pubchem_client = BaseAPIClient(APIClientConfig(
    base_url="https://pubchem.ncbi.nlm.nih.gov",
    timeout=PUBMED_TIMEOUT_SECONDS,
    max_retries=3,
))

_chembl_client = BaseAPIClient(APIClientConfig(
    base_url="https://www.ebi.ac.uk",
    timeout=PUBMED_TIMEOUT_SECONDS,
    max_retries=3,
))

_admetlab_client = BaseAPIClient(APIClientConfig(
    base_url="https://admetmesh.scbdd.com",
    timeout=60,
    max_retries=3,
))

_tox21_client = BaseAPIClient(APIClientConfig(
    base_url="https://tripod.nih.gov",
    timeout=PUBMED_TIMEOUT_SECONDS,
    max_retries=3,
))


# ============================================================================
# PubChem Integration for Toxicity Data
# ============================================================================

@dataclass
class PubChemToxicity:
    """Toxicity data from PubChem."""
    cid: str
    assay_id: str
    assay_name: str
    target_name: str
    organism: str
    activity_outcome: str  # Active, Inactive, Inconclusive
    activity_score: float
    concentration_unit: str
    concentration_value: float


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_pubchem_toxicity(cid: str) -> list[PubChemToxicity]:
    """Fetch toxicity assay data from PubChem BioAssay."""
    try:
        payload = _pubchem_client.get(
            f"/rest/pug/compound/cid/{cid}/assaysummary/JSON",
        )
        
        results = []
        assay_summary = payload.get("AssaySummary", {})
        for assay in assay_summary.get("Assay", []):
            # Filter for toxicity-related assays
            assay_name = assay.get("AssayDescription", "").lower()
            if any(term in assay_name for term in ["tox", "hepat", "cardio", "nephro", "cyto", "geno", "mutagen", "carcin"]):
                results.append(PubChemToxicity(
                    cid=cid,
                    assay_id=str(assay.get("AID", "")),
                    assay_name=assay.get("AssayDescription", ""),
                    target_name=assay.get("TargetName", ""),
                    organism=assay.get("Organism", ""),
                    activity_outcome=assay.get("ActivityOutcome", ""),
                    activity_score=float(assay.get("ActivityScore", 0)),
                    concentration_unit=assay.get("ConcentrationUnit", ""),
                    concentration_value=float(assay.get("ConcentrationValue", 0)),
                ))
        return results
    except Exception as e:
        logger.warning("PubChem toxicity fetch failed for CID %s: %s", cid, e)
        return []


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_pubchem_compound_safety(cid: str) -> dict[str, Any]:
    """Fetch safety-related compound info from PubChem."""
    try:
        payload = _pubchem_client.get(
            f"/rest/pug/compound/cid/{cid}/property/IsToxic,ToxicityValue,ToxicityUnit,LD50,LC50/JSON",
        )
        
        props = payload.get("PropertyTable", {}).get("Properties", [])
        if props:
            return props[0]
        return {}
    except Exception as e:
        logger.warning("PubChem safety fetch failed for CID %s: %s", cid, e)
        return {}


# ============================================================================
# ChEMBL Integration for Safety Data
# ============================================================================

@dataclass
class ChEMBLToxicity:
    """Toxicity data from ChEMBL."""
    chembl_id: str
    assay_chembl_id: str
    assay_description: str
    target_chembl_id: str
    target_name: str
    organism: str
    standard_type: str  # IC50, EC50, LD50, etc.
    standard_value: float
    standard_unit: str
    standard_relation: str  # =, >, <, >=, <=
    data_validity_comment: str
    document_chembl_id: str


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_chembl_toxicity(chembl_id: str) -> list[ChEMBLToxicity]:
    """Fetch toxicity assay data from ChEMBL."""
    try:
        payload = _chembl_client.get(
            "/chembl/api/data/activity.json",
            params={
                "molecule_chembl_id": chembl_id,
                "assay_type": "B",
                "standard_type__in": "IC50,EC50,LD50,LC50,GI50",
                "limit": 200,
            },
        )
        
        results = []
        for act in payload.get("activities", []):
            results.append(ChEMBLToxicity(
                chembl_id=chembl_id,
                assay_chembl_id=act.get("assay_chembl_id", ""),
                assay_description=act.get("assay_description", ""),
                target_chembl_id=act.get("target_chembl_id", ""),
                target_name=act.get("target_pref_name", ""),
                organism=act.get("target_organism", ""),
                standard_type=act.get("standard_type", ""),
                standard_value=float(act.get("standard_value", 0)) if act.get("standard_value") else 0.0,
                standard_unit=act.get("standard_unit", ""),
                standard_relation=act.get("standard_relation", ""),
                data_validity_comment=act.get("data_validity_comment", ""),
                document_chembl_id=act.get("document_chembl_id", ""),
            ))
        return results
    except Exception as e:
        logger.warning("ChEMBL toxicity fetch failed for %s: %s", chembl_id, e)
        return []


# ============================================================================
# ADMETlab Integration (if accessible)
# ============================================================================

@dataclass
class ADMETlabPrediction:
    """ADMET prediction from ADMETlab."""
    smiles: str
    absorption: dict[str, float]
    distribution: dict[str, float]
    metabolism: dict[str, float]
    excretion: dict[str, float]
    toxicity: dict[str, float]
    source: str = "ADMETlab"


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def fetch_admetlab_prediction(smiles: str) -> ADMETlabPrediction | None:
    """Fetch ADMET prediction from ADMETlab (public API if available)."""
    # Note: ADMETlab 2.0 has a public API but may require registration
    # This is a placeholder for when API access is available
    try:
        # Try ADMETlab 2.0 API
        payload = _admetlab_client.post(
            "/api/predict",
            json={"smiles": smiles},
            timeout=60,
        )
        
        if payload and isinstance(payload, dict):
            return ADMETlabPrediction(
                smiles=smiles,
                absorption=payload.get("absorption", {}),
                distribution=payload.get("distribution", {}),
                metabolism=payload.get("metabolism", {}),
                excretion=payload.get("excretion", {}),
                toxicity=payload.get("toxicity", {}),
            )
    except Exception as e:
        logger.debug("ADMETlab API not accessible: %s", e)
    
    return None


# ============================================================================
# Tox21 Data Integration
# ============================================================================

@dataclass
class Tox21Assay:
    """Tox21 assay result."""
    assay_name: str
    gene_symbol: str
    compound_cid: str
    activity: str  # Active, Inactive
    concentration: float
    unit: str


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def fetch_tox21_data(gene_symbol: str | None = None, cid: str | None = None) -> list[Tox21Assay]:
    """Fetch Tox21 assay data (placeholder - requires bulk download)."""
    # Tox21 data is typically downloaded in bulk
    # This is a placeholder for local database queries
    logger.info("Tox21 data access requires local database - not implemented")
    return []


# ============================================================================
# Drug-Drug Interactions (from various sources)
# ============================================================================

@dataclass
class DrugInteraction:
    """Drug-drug interaction."""
    drug_a: str
    drug_b: str
    interaction_type: str  # PK, PD, PK/PD
    severity: str  # Major, Moderate, Minor
    description: str
    evidence_level: str
    source: str


@ttl_cache(ttl_seconds=86_400, max_entries=256)
def fetch_drug_interactions(drug_name: str) -> list[DrugInteraction]:
    """Fetch drug-drug interactions (placeholder - requires DrugBank or similar)."""
    # Would integrate with DrugBank, TWOSIDES, or similar
    # For now, return empty - requires API key
    logger.info("Drug interaction lookup requires DrugBank API key - not implemented")
    return []


# ============================================================================
# Molecular Property Calculation (using RDKit)
# ============================================================================

def calculate_toxicity_relevant_properties(smiles: str) -> dict[str, float]:
    """Calculate molecular properties relevant to toxicity."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
        from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams, FilterCatalogParams_Filters
        
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return {}
        
        props = {}
        
        # Basic properties
        props["molecular_weight"] = Descriptors.MolWt(mol)
        props["logp"] = Descriptors.MolLogP(mol)
        props["tpsa"] = Descriptors.TPSA(mol)
        props["hbd"] = Descriptors.NumHDonors(mol)
        props["hba"] = Descriptors.NumHAcceptors(mol)
        props["rotatable_bonds"] = Descriptors.NumRotatableBonds(mol)
        props["aromatic_rings"] = Descriptors.NumAromaticRings(mol)
        props["heavy_atoms"] = Descriptors.HeavyAtomCount(mol)
        props["formal_charge"] = Chem.GetFormalCharge(mol)
        
        # Toxicity-relevant structural alerts
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams_Filters.PAINS_A)
        params.AddCatalog(FilterCatalogParams_Filters.PAINS_B)
        params.AddCatalog(FilterCatalogParams_Filters.PAINS_C)
        catalog = FilterCatalog(params)
        props["pains_alerts"] = len(catalog.GetMatches(mol))
        
        # Brenk alerts
        params2 = FilterCatalogParams()
        params2.AddCatalog(FilterCatalogParams_Filters.BRENK)
        catalog2 = FilterCatalog(params2)
        props["brenk_alerts"] = len(catalog2.GetMatches(mol))
        
        # NIH alerts
        params3 = FilterCatalogParams()
        params3.AddCatalog(FilterCatalogParams_Filters.NIH)
        catalog3 = FilterCatalog(params3)
        props["nih_alerts"] = len(catalog3.GetMatches(mol))
        
        # Lipinski violations
        violations = 0
        if props["molecular_weight"] > 500: violations += 1
        if props["logp"] > 5: violations += 1
        if props["hbd"] > 5: violations += 1
        if props["hba"] > 10: violations += 1
        props["lipinski_violations"] = violations
        
        # Reactive groups (simplified)
        smarts_reactive = [
            ("aldehyde", "[CX3H1](=O)[#6]"),
            ("epoxide", "[O]1[C]1"),
            ("michael_acceptor", "[CX3]=[CX3][CX3](=O)[OX1]"),
            ("alkylating", "[Cl,Br,I][CX3]"),
            ("nitro", "[N+](=O)[O-]"),
        ]
        for name, smarts in smarts_reactive:
            patt = Chem.MolFromSmarts(smarts)
            if patt and mol.HasSubstructMatch(patt):
                props[f"alert_{name}"] = 1.0
            else:
                props[f"alert_{name}"] = 0.0
        
        return props
        
    except Exception as e:
        logger.warning("RDKit property calculation failed: %s", e)
        return {}


# ============================================================================
# Combined Safety Profile
# ============================================================================

@dataclass
class SafetyProfile:
    """Combined safety profile for a compound."""
    identifier: str  # SMILES, CID, or ChEMBL ID
    source: str
    molecular_properties: dict[str, float]
    pubchem_toxicity: list[PubChemToxicity]
    chembl_toxicity: list[ChEMBLToxicity]
    admetlab_prediction: ADMETlabPrediction | None
    drug_interactions: list[DrugInteraction]
    structural_alerts: dict[str, float]
    risk_assessment: dict[str, Any]


def build_safety_profile(
    smiles: str | None = None,
    cid: str | None = None,
    chembl_id: str | None = None,
) -> SafetyProfile:
    """Build a comprehensive safety profile from multiple sources."""
    identifier = smiles or cid or chembl_id or "unknown"
    source_parts = []
    
    # Molecular properties
    mol_props = {}
    if smiles:
        mol_props = calculate_toxicity_relevant_properties(smiles)
        source_parts.append("RDKit")
    
    # PubChem toxicity
    pubchem_tox = []
    if cid:
        pubchem_tox = fetch_pubchem_toxicity(cid)
        source_parts.append("PubChem")
    elif smiles:
        # Try to get CID from SMILES
        try:
            from geneai.admet_prediction.data_integration import get_pubchem_compound_by_smiles
            pc = get_pubchem_compound_by_smiles(smiles)
            if pc and pc.get("cid"):
                pubchem_tox = fetch_pubchem_toxicity(str(pc["cid"]))
                source_parts.append("PubChem")
        except Exception:
            pass
    
    # ChEMBL toxicity
    chembl_tox = []
    if chembl_id:
        chembl_tox = fetch_chembl_toxicity(chembl_id)
        source_parts.append("ChEMBL")
    
    # ADMETlab
    admetlab_pred = None
    if smiles:
        admetlab_pred = fetch_admetlab_prediction(smiles)
        if admetlab_pred:
            source_parts.append("ADMETlab")
    
    # Drug interactions
    interactions = []
    # Would need drug name - placeholder
    
    # Structural alerts
    structural_alerts = {k: v for k, v in mol_props.items() if k.startswith("alert_") or k.endswith("_alerts")}
    
    # Risk assessment
    risk_assessment = assess_toxicity_risk(mol_props, pubchem_tox, chembl_tox, admetlab_pred)
    
    return SafetyProfile(
        identifier=identifier,
        source="+".join(source_parts) if source_parts else "none",
        molecular_properties=mol_props,
        pubchem_toxicity=pubchem_tox,
        chembl_toxicity=chembl_tox,
        admetlab_prediction=admetlab_pred,
        drug_interactions=interactions,
        structural_alerts=structural_alerts,
        risk_assessment=risk_assessment,
    )


def assess_toxicity_risk(
    mol_props: dict[str, float],
    pubchem_tox: list[PubChemToxicity],
    chembl_tox: list[ChEMBLToxicity],
    admetlab_pred: ADMETlabPrediction | None,
) -> dict[str, Any]:
    """Assess overall toxicity risk."""
    risk_factors = []
    risk_score = 0.0
    
    # Structural alerts
    if mol_props.get("pains_alerts", 0) > 0:
        risk_factors.append(f"PAINS alerts: {mol_props['pains_alerts']}")
        risk_score += 0.2 * min(mol_props["pains_alerts"], 3)
    
    if mol_props.get("brenk_alerts", 0) > 0:
        risk_factors.append(f"Brenk alerts: {mol_props['brenk_alerts']}")
        risk_score += 0.15 * min(mol_props["brenk_alerts"], 3)
    
    if mol_props.get("nih_alerts", 0) > 0:
        risk_factors.append(f"NIH alerts: {mol_props['nih_alerts']}")
        risk_score += 0.1 * min(mol_props["nih_alerts"], 3)
    
    # Lipinski violations
    if mol_props.get("lipinski_violations", 0) > 1:
        risk_factors.append(f"Lipinski violations: {mol_props['lipinski_violations']}")
        risk_score += 0.1 * (mol_props["lipinski_violations"] - 1)
    
    # Reactive groups
    for alert in ["aldehyde", "epoxide", "michael_acceptor", "alkylating", "nitro"]:
        if mol_props.get(f"alert_{alert}", 0) > 0:
            risk_factors.append(f"Reactive group: {alert}")
            risk_score += 0.15
    
    # PubChem assay data
    active_tox_assays = [a for a in pubchem_tox if a.activity_outcome == "Active"]
    if active_tox_assays:
        risk_factors.append(f"Active toxicity assays: {len(active_tox_assays)}")
        risk_score += 0.2 * min(len(active_tox_assays), 5)
    
    # ChEMBL data
    if chembl_tox:
        # Look for low IC50/EC50 values indicating high potency toxicity
        potent_tox = [a for a in chembl_tox if a.standard_type in ("IC50", "EC50", "LD50") and a.standard_value < 10 and a.standard_unit in ("nM", "uM", "µM")]
        if potent_tox:
            risk_factors.append(f"Potent toxicity activities: {len(potent_tox)}")
            risk_score += 0.2 * min(len(potent_tox), 5)
    
    # ADMETlab predictions
    if admetlab_pred and admetlab_pred.toxicity:
        high_tox = [k for k, v in admetlab_pred.toxicity.items() if isinstance(v, (int, float)) and v > 0.7]
        if high_tox:
            risk_factors.append(f"ADMETlab high toxicity: {', '.join(high_tox)}")
            risk_score += 0.25 * len(high_tox)
    
    # Normalize risk score
    risk_score = min(risk_score, 1.0)
    
    if risk_score >= 0.7:
        risk_level = "High"
    elif risk_score >= 0.4:
        risk_level = "Moderate"
    elif risk_score >= 0.2:
        risk_level = "Low-Moderate"
    else:
        risk_level = "Low"
    
    return {
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "num_factors": len(risk_factors),
    }


# Convenience function
def predict_drug_safety(
    smiles: str | None = None,
    cid: str | None = None,
    chembl_id: str | None = None,
) -> SafetyProfile:
    """Predict drug safety profile from available identifiers."""
    return build_safety_profile(smiles=smiles, cid=cid, chembl_id=chembl_id)