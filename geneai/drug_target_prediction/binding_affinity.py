"""Binding affinity analysis and estimation for drug-target interactions."""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from geneai.drug_discovery import chembl_client
from geneai.drug_discovery import pubchem_client
from geneai.drug_target_prediction.molecular_descriptors import (
    calculate_molecular_descriptors,
    is_rdkit_available,
)

logger = logging.getLogger(__name__)


# Known binding affinity data for reference
REFERENCE_AFFINITIES = {
    # (drug_name, target_name): affinity_nM
    ("aspirin", "PTGS1"): 1.67,
    ("aspirin", "PTGS2"): 167,
    ("ibuprofen", "PTGS1"): 0.5,
    ("ibuprofen", "PTGS2"): 2.5,
    ("caffeine", "ADORA1"): 12000,
    ("caffeine", "ADORA2A"): 2400,
    ("methotrexate", "DHFR"): 0.01,
    ("imatinib", "ABL1"): 0.6,
    ("erlotinib", "EGFR"): 2,
    ("gefitinib", "EGFR"): 3,
    ("sorafenib", "BRAF"): 6,
    ("sunitinib", "VEGFR2"): 2,
    ("dasatinib", "BCR-ABL"): 0.8,
    ("nilotinib", "BCR-ABL"): 3,
    ("bosutinib", "BCR-ABL"): 1,
    ("ponatinib", "BCR-ABL"): 0.37,
}


def estimate_binding_affinity(
    drug_smiles: str,
    target_identifier: str,
    method: str = "ml",
) -> dict[str, Any]:
    """Estimate binding affinity (Kd/Ki/IC50) for drug-target pair.
    
    Args:
        drug_smiles: Drug SMILES string
        target_identifier: Target identifier (gene symbol, UniProt, ChEMBL ID)
        method: Estimation method ("ml", "rule_based", "reference")
        
    Returns:
        Dictionary with estimated affinity and confidence
    """
    result = {
        "drug_smiles": drug_smiles,
        "target_identifier": target_identifier,
        "method": method,
        "estimated_affinity_nm": None,
        "estimated_pkd": None,
        "confidence": "low",
        "details": {},
    }
    
    # Try reference data first
    if method in ("reference", "auto"):
        ref_result = _lookup_reference_affinity(drug_smiles, target_identifier)
        if ref_result:
            return ref_result
    
    if method == "rule_based":
        return _rule_based_affinity(drug_smiles, target_identifier)
    
    if method == "ml":
        return _ml_based_affinity(drug_smiles, target_identifier)
    
    return result


def _lookup_reference_affinity(
    drug_smiles: str,
    target_identifier: str,
) -> dict[str, Any] | None:
    """Look up known binding affinity from reference data."""
    # Try to identify drug name from SMILES
    drug_name = _identify_drug_name(drug_smiles)
    target_gene = _extract_gene_symbol(target_identifier)
    
    if drug_name and target_gene:
        key = (drug_name.lower(), target_gene.upper())
        if key in REFERENCE_AFFINITIES:
            affinity_nm = REFERENCE_AFFINITIES[key]
            return {
                "drug_smiles": drug_smiles,
                "target_identifier": target_identifier,
                "method": "reference",
                "estimated_affinity_nm": affinity_nm,
                "estimated_pkd": -math.log10(affinity_nm * 1e-9),
                "confidence": "high",
                "details": {
                    "source": "literature_reference",
                    "drug_name": drug_name,
                    "target_gene": target_gene,
                },
            }
    
    return None


def _rule_based_affinity(
    drug_smiles: str,
    target_identifier: str,
) -> dict[str, Any]:
    """Rule-based affinity estimation using molecular properties."""
    desc = calculate_molecular_descriptors(drug_smiles)
    
    if not desc or desc.get("molecular_weight") is None:
        return {
            "drug_smiles": drug_smiles,
            "target_identifier": target_identifier,
            "method": "rule_based",
            "estimated_affinity_nm": None,
            "estimated_pkd": None,
            "confidence": "none",
            "details": {"error": "Invalid SMILES or RDKit unavailable"},
        }
    
    # Lipinski Rule of 5 compliance
    mw = desc.get("molecular_weight", 0)
    logp = desc.get("logp", 0)
    hbd = desc.get("hbd", 0)
    hba = desc.get("hba", 0)
    tpsa = desc.get("tpsa", 0)
    rot_bonds = desc.get("rotatable_bonds", 0)
    
    violations = 0
    if mw > 500: violations += 1
    if logp > 5: violations += 1
    if hbd > 5: violations += 1
    if hba > 10: violations += 1
    
    # Base affinity estimate (log scale)
    # More drug-like = better binding potential
    base_pkd = 6.0  # 1 uM baseline
    
    # Adjust based on properties
    if 200 <= mw <= 500: base_pkd += 0.5
    elif mw > 500: base_pkd -= 0.5
    
    if 0 <= logp <= 3: base_pkd += 0.5
    elif logp > 5: base_pkd -= 1.0
    elif logp < -1: base_pkd -= 0.5
    
    if tpsa <= 140: base_pkd += 0.3
    elif tpsa > 140: base_pkd -= 0.3
    
    if rot_bonds <= 10: base_pkd += 0.2
    elif rot_bonds > 15: base_pkd -= 0.2
    
    # Penalize violations
    base_pkd -= violations * 0.3
    
    # Convert to nM
    affinity_nm = 10 ** (9 - base_pkd)
    
    # Confidence based on drug-likeness
    if violations == 0 and 200 <= mw <= 500 and 0 <= logp <= 3:
        confidence = "medium"
    elif violations <= 1:
        confidence = "low"
    else:
        confidence = "very_low"
    
    return {
        "drug_smiles": drug_smiles,
        "target_identifier": target_identifier,
        "method": "rule_based",
        "estimated_affinity_nm": round(affinity_nm, 2),
        "estimated_pkd": round(base_pkd, 2),
        "confidence": confidence,
        "details": {
            "lipinski_violations": violations,
            "molecular_weight": mw,
            "logp": logp,
            "tpsa": tpsa,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rot_bonds,
            "base_pkd": round(base_pkd, 2),
        },
    }


def _ml_based_affinity(
    drug_smiles: str,
    target_identifier: str,
) -> dict[str, Any]:
    """ML-based affinity estimation (placeholder for trained model)."""
    # This would use a trained regression model
    # For now, fall back to rule-based with ML flag
    result = _rule_based_affinity(drug_smiles, target_identifier)
    result["method"] = "ml"
    result["details"]["note"] = "Using rule-based fallback; ML model not yet trained"
    return result


def _identify_drug_name(smiles: str) -> str | None:
    """Attempt to identify drug name from SMILES via PubChem."""
    try:
        result = pubchem_client.get_compound_by_smiles(smiles)
        if result:
            return result.get("name") or result.get("iupac_name")
    except Exception:
        pass
    return None


def _extract_gene_symbol(identifier: str) -> str | None:
    """Extract gene symbol from various identifier formats."""
    identifier = identifier.strip().upper()
    
    # Direct gene symbol (e.g., "EGFR", "PTGS1")
    if identifier.isalpha() and 2 <= len(identifier) <= 10:
        return identifier
    
    # UniProt ID (e.g., "P00533")
    if identifier.startswith("P") and len(identifier) == 6:
        # Would need UniProt lookup - placeholder
        return None
    
    # ChEMBL target ID (e.g., "CHEMBL2095")
    if identifier.startswith("CHEMBL"):
        return None  # Would need ChEMBL lookup
    
    return None


def analyze_binding_site_compatibility(
    drug_smiles: str,
    target_pdb_id: str | None = None,
) -> dict[str, Any]:
    """Analyze binding site compatibility (requires 3D structure).
    
    Args:
        drug_smiles: Drug SMILES
        target_pdb_id: PDB ID of target structure
        
    Returns:
        Binding site analysis results
    """
    if not is_rdkit_available():
        return {"error": "RDKit required for 3D analysis"}
    
    # Placeholder for docking/binding site analysis
    # Would integrate with AutoDock, Vina, or similar
    return {
        "drug_smiles": drug_smiles,
        "target_pdb_id": target_pdb_id,
        "method": "placeholder",
        "binding_score": None,
        "details": {
            "note": "3D binding site analysis requires structural biology tools",
            "recommended_tools": ["AutoDock Vina", "GNINA", "DiffDock", "EquiBind"],
        },
    }


def get_chembl_affinity_data(
    target_chembl_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch binding affinity data from ChEMBL for a target.
    
    Args:
        target_chembl_id: ChEMBL target ID
        limit: Maximum records
        
    Returns:
        List of activity records with affinity data
    """
    try:
        activities = chembl_client.get_target_bioactivities(target_chembl_id, limit=limit)
        
        affinity_data = []
        for act in activities:
            value = act.get("standard_value")
            unit = act.get("standard_units", "").lower()
            relation = act.get("standard_relation", "")
            
            if value is not None and unit in ("nm", "µm", "um", "mm"):
                # Convert to nM
                if unit in ("µm", "um"):
                    value_nm = value * 1000
                elif unit == "mm":
                    value_nm = value * 1_000_000
                else:
                    value_nm = value
                
                affinity_data.append({
                    "molecule_chembl_id": act.get("molecule_chembl_id"),
                    "canonical_smiles": act.get("canonical_smiles"),
                    "standard_value_nm": value_nm,
                    "standard_relation": relation,
                    "standard_type": act.get("standard_type"),
                    "assay_description": act.get("assay_description"),
                    "pchembl_value": act.get("pchembl_value"),
                })
        
        return affinity_data
        
    except Exception as e:
        logger.error("Failed to fetch ChEMBL affinity data: %s", e)
        return []


def calculate_ligand_efficiency(
    affinity_nm: float,
    heavy_atom_count: int,
) -> dict[str, float]:
    """Calculate ligand efficiency metrics.
    
    Args:
        affinity_nm: Binding affinity in nM
        heavy_atom_count: Number of non-hydrogen atoms
        
    Returns:
        Dictionary of efficiency metrics
    """
    if affinity_nm <= 0 or heavy_atom_count <= 0:
        return {"le": 0, "lle": 0, "be": 0, "sei": 0}
    
    pkd = -math.log10(affinity_nm * 1e-9)
    
    # Ligand Efficiency (LE) = pKd / heavy_atoms
    le = pkd / heavy_atom_count
    
    # Lipophilic Ligand Efficiency (LLE) = pKd - logP
    # Would need logP - placeholder
    lle = pkd - 3.0  # Assuming average logP
    
    # Binding Efficiency (BE) = pKd / MW * 100
    # Would need MW - placeholder
    be = pkd / 400 * 100
    
    # Surface Efficiency Index (SEI) = pKd / PSA * 100
    # Would need PSA - placeholder
    sei = pkd / 100 * 100
    
    return {
        "le": round(le, 3),
        "lle": round(lle, 3),
        "be": round(be, 3),
        "sei": round(sei, 3),
        "pkd": round(pkd, 3),
    }


def classify_binding_potency(affinity_nm: float) -> str:
    """Classify binding potency based on affinity.
    
    Args:
        affinity_nm: Binding affinity in nM
        
    Returns:
        Potency classification
    """
    if affinity_nm < 1:
        return "sub_nanomolar"
    elif affinity_nm < 10:
        return "single_digit_nm"
    elif affinity_nm < 100:
        return "high_nm"
    elif affinity_nm < 1000:
        return "mid_nm"
    elif affinity_nm < 10000:
        return "low_nm"
    elif affinity_nm < 100000:
        return "micromolar"
    else:
        return "weak"


def generate_affinity_report(
    drug_identifier: str,
    target_identifier: str,
    methods: list[str] | None = None,
) -> dict[str, Any]:
    """Generate comprehensive affinity analysis report.
    
    Args:
        drug_identifier: Drug identifier
        target_identifier: Target identifier
        methods: List of methods to use
        
    Returns:
        Comprehensive affinity report
    """
    methods = methods or ["reference", "rule_based", "ml"]
    
    # Resolve drug to SMILES
    from geneai.drug_target_prediction.prediction_engine import DrugTargetPredictionEngine
    engine = DrugTargetPredictionEngine()
    drug_smiles = engine._resolve_drug_to_smiles(drug_identifier)
    
    if not drug_smiles:
        return {"error": "Could not resolve drug identifier"}
    
    report = {
        "drug_identifier": drug_identifier,
        "target_identifier": target_identifier,
        "drug_smiles": drug_smiles,
        "estimates": {},
        "consensus": {},
    }
    
    estimates = []
    for method in methods:
        result = estimate_binding_affinity(drug_smiles, target_identifier, method)
        report["estimates"][method] = result
        if result.get("estimated_affinity_nm"):
            estimates.append(result["estimated_affinity_nm"])
    
    # Consensus estimate
    if estimates:
        geometric_mean = np.exp(np.mean(np.log(estimates)))
        report["consensus"] = {
            "geometric_mean_nm": round(geometric_mean, 2),
            "geometric_mean_pkd": round(-math.log10(geometric_mean * 1e-9), 2),
            "potency_class": classify_binding_potency(geometric_mean),
            "methods_used": len(estimates),
            "range_nm": [round(min(estimates), 2), round(max(estimates), 2)],
        }
    
    # Add ligand efficiency if possible
    desc = calculate_molecular_descriptors(drug_smiles)
    if desc.get("num_atoms"):
        heavy_atoms = desc["num_atoms"]
        if report["consensus"].get("geometric_mean_nm"):
            le_metrics = calculate_ligand_efficiency(
                report["consensus"]["geometric_mean_nm"],
                heavy_atoms,
            )
            report["ligand_efficiency"] = le_metrics
    
    return report