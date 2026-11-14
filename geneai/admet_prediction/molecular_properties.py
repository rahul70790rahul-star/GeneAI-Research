"""Molecular Property Engine - Module 1: Core molecular descriptor calculations."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors, Lipinski, QED
    from rdkit.Chem.rdMolDescriptors import (
        CalcNumRotatableBonds, CalcTPSA, CalcNumHBD, CalcNumHBA,
        CalcNumAromaticRings, CalcNumAliphaticRings,
        CalcNumHeteroatoms, CalcFractionCSP3, CalcLabuteASA
    )
    # Exact molecular weight: prefer rdMolDescriptors.CalcExactMW, fall back to Descriptors.ExactMolWt
    try:
        from rdkit.Chem.rdMolDescriptors import CalcExactMW
    except ImportError:
        CalcExactMW = None
    RDKit_AVAILABLE = True
except ImportError:
    RDKit_AVAILABLE = False

logger = logging.getLogger(__name__)

# Lipinski Rule of Five thresholds
LIPINSKI_THRESHOLDS = {
    "molecular_weight": 500,
    "logp": 5,
    "hbd": 5,
    "hba": 10,
}

# Extended drug-likeness rules (Veber, Egan, etc.)
VEBER_THRESHOLDS = {
    "rotatable_bonds": 10,
    "tpsa": 140,
}

EGAN_THRESHOLDS = {
    "logp": 5.88,
    "tpsa": 131.6,
}


def is_rdkit_available() -> bool:
    """Check if RDKit is available."""
    return RDKit_AVAILABLE


def validate_smiles(smiles: str) -> tuple[bool, Any]:
    """Validate a SMILES string and return parsed molecule or error."""
    if not RDKit_AVAILABLE:
        return False, "RDKit not available"

    if not smiles or not isinstance(smiles, str) or not smiles.strip():
        return False, "Empty or invalid SMILES string"

    cleaned = smiles.strip()
    try:
        mol = Chem.MolFromSmiles(cleaned)
        if mol is None:
            return False, f"Invalid SMILES: {smiles}"
        return True, mol
    except Exception as e:
        return False, f"SMILES parsing error: {e}"


def _safe(func, default=None, *args, **kwargs):
    """Evaluate an optional descriptor without failing the whole record."""
    try:
        return func(*args, **kwargs)
    except Exception:  # pragma: no cover - descriptor availability varies
        logger.debug("Optional descriptor %s failed", getattr(func, "__name__", func), exc_info=True)
        return default


def calculate_molecular_properties(smiles: str) -> dict[str, Any]:
    """Calculate comprehensive molecular properties from SMILES.

    Args:
        smiles: SMILES string of the molecule

    Returns:
        Dictionary containing all molecular properties

    Raises:
        ValueError: If the SMILES string is empty or cannot be parsed.
    """
    if not RDKit_AVAILABLE:
        raise ValueError("RDKit is not available; molecular properties cannot be calculated")

    is_valid, mol_or_error = validate_smiles(smiles)
    if not is_valid:
        raise ValueError(str(mol_or_error))

    cleaned = smiles.strip()
    mol = mol_or_error

    try:
        properties: dict[str, Any] = {"smiles": cleaned}

        # Structure identifiers
        properties["canonical_smiles"] = Chem.MolToSmiles(mol)
        properties["inchikey"] = _safe(Chem.MolToInchiKey, "", mol)
        properties["inchi"] = _safe(Chem.MolToInchi, "", mol)

        # Basic properties (descriptors below are additive and use implicit H)
        properties["molecular_weight"] = round(Descriptors.MolWt(mol), 2)
        properties["exact_molecular_weight"] = round(
            CalcExactMW(mol) if CalcExactMW else Descriptors.ExactMolWt(mol), 2
        )
        properties["logp"] = round(Descriptors.MolLogP(mol), 2)
        properties["tpsa"] = round(CalcTPSA(mol), 2)
        properties["hbd"] = Lipinski.NumHDonors(mol)
        # Lipinski's Rule of Five defines H-bond acceptors as the sum of N and O
        # atoms. RDKit's ``CalcNumHBA`` uses a stricter pharmacophore SMARTS
        # (for example, it excludes amide nitrogens), so it is not used here.
        properties["hba"] = sum(
            1 for atom in mol.GetAtoms() if atom.GetAtomicNum() in (7, 8)
        )
        properties["rotatable_bonds"] = CalcNumRotatableBonds(mol)

        # Ring properties
        properties["aromatic_rings"] = CalcNumAromaticRings(mol)
        properties["aliphatic_rings"] = CalcNumAliphaticRings(mol)
        properties["total_rings"] = mol.GetRingInfo().NumRings()

        # Atom/bond counts
        properties["num_atoms"] = mol.GetNumAtoms()
        properties["num_heavy_atoms"] = mol.GetNumHeavyAtoms()
        properties["num_bonds"] = mol.GetNumBonds()

        # Heteroatoms
        properties["num_carbons"] = sum(
            1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6
        )
        properties["heteroatoms"] = CalcNumHeteroatoms(mol)

        # Fraction CSP3
        properties["fraction_csp3"] = round(CalcFractionCSP3(mol), 3)

        # Surface area
        properties["labute_asa"] = round(CalcLabuteASA(mol), 2)

        # Molar refractivity (used by the Ghose filter)
        crippen = _safe(rdMolDescriptors.CalcCrippenDescriptors, None, mol)
        properties["molar_refractivity"] = round(crippen[1], 2) if crippen else None

        # Additional descriptors
        properties["molecular_formula"] = rdMolDescriptors.CalcMolFormula(mol)
        properties["num_chiral_centers"] = _safe(
            rdMolDescriptors.CalcNumAtomStereoCenters, 0, mol
        )
        properties["num_undefined_chiral_centers"] = _safe(
            rdMolDescriptors.CalcNumUnspecifiedAtomStereoCenters, 0, mol
        )
        properties["num_spiro_atoms"] = _safe(Descriptors.NumSpiroAtoms, 0, mol)
        properties["num_bridgehead_atoms"] = _safe(Descriptors.NumBridgeheadAtoms, 0, mol)

        # Charge
        properties["formal_charge"] = Chem.GetFormalCharge(mol)

        # Complexity
        properties["bertz_ct"] = round(Descriptors.BertzCT(mol), 2)

        # QED (Quantitative Estimate of Drug-likeness)
        properties["qed"] = round(_safe(QED.qed, 0.0, mol), 3)

        # Rule-based drug-likeness assessment
        properties["drug_likeness"] = assess_drug_likeness(properties)

        return properties

    except ValueError:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Property calculation failed for SMILES %s: %s", smiles, e)
        raise ValueError(f"Property calculation failed: {e}") from e


def check_lipinski_rule_of_five(properties: dict[str, Any]) -> dict[str, Any]:
    """Check Lipinski Rule of Five compliance.
    
    Args:
        properties: Dictionary of molecular properties
        
    Returns:
        Dictionary with compliance results
    """
    violations = []
    
    mw = properties.get("molecular_weight")
    if mw is not None and mw > LIPINSKI_THRESHOLDS["molecular_weight"]:
        violations.append(f"Molecular weight ({mw}) > {LIPINSKI_THRESHOLDS['molecular_weight']}")
    
    logp = properties.get("logp")
    if logp is not None and logp > LIPINSKI_THRESHOLDS["logp"]:
        violations.append(f"LogP ({logp}) > {LIPINSKI_THRESHOLDS['logp']}")
    
    hbd = properties.get("hbd")
    if hbd is not None and hbd > LIPINSKI_THRESHOLDS["hbd"]:
        violations.append(f"HBD ({hbd}) > {LIPINSKI_THRESHOLDS['hbd']}")
    
    hba = properties.get("hba")
    if hba is not None and hba > LIPINSKI_THRESHOLDS["hba"]:
        violations.append(f"HBA ({hba}) > {LIPINSKI_THRESHOLDS['hba']}")
    
    return {
        "passes": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "thresholds": LIPINSKI_THRESHOLDS,
    }


def check_veber_rules(properties: dict[str, Any]) -> dict[str, Any]:
    """Check Veber rules for oral bioavailability.
    
    Args:
        properties: Dictionary of molecular properties
        
    Returns:
        Dictionary with compliance results
    """
    violations = []
    
    rot_bonds = properties.get("rotatable_bonds")
    if rot_bonds is not None and rot_bonds > VEBER_THRESHOLDS["rotatable_bonds"]:
        violations.append(f"Rotatable bonds ({rot_bonds}) > {VEBER_THRESHOLDS['rotatable_bonds']}")
    
    tpsa = properties.get("tpsa")
    if tpsa is not None and tpsa > VEBER_THRESHOLDS["tpsa"]:
        violations.append(f"TPSA ({tpsa}) > {VEBER_THRESHOLDS['tpsa']}")
    
    return {
        "passes": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "thresholds": VEBER_THRESHOLDS,
    }


def check_egan_rules(properties: dict[str, Any]) -> dict[str, Any]:
    """Check Egan rules for brain penetration.
    
    Args:
        properties: Dictionary of molecular properties
        
    Returns:
        Dictionary with compliance results
    """
    violations = []
    
    logp = properties.get("logp")
    if logp is not None and logp > EGAN_THRESHOLDS["logp"]:
        violations.append(f"LogP ({logp}) > {EGAN_THRESHOLDS['logp']}")
    
    tpsa = properties.get("tpsa")
    if tpsa is not None and tpsa > EGAN_THRESHOLDS["tpsa"]:
        violations.append(f"TPSA ({tpsa}) > {EGAN_THRESHOLDS['tpsa']}")
    
    return {
        "passes": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "thresholds": EGAN_THRESHOLDS,
    }


def check_ghose_filter(properties: dict[str, Any]) -> dict[str, Any]:
    """Check the Ghose filter for drug-like chemical space.

    Ghose et al. (1999): -0.4 <= logP <= 5.6, 160 <= MW <= 480,
    40 <= molar refractivity <= 130, and 20 <= atom count <= 70.
    """
    violations = []
    logp = properties.get("logp")
    mw = properties.get("molecular_weight")
    mr = properties.get("molar_refractivity")
    atoms = properties.get("num_atoms")

    if logp is not None and not (-0.4 <= logp <= 5.6):
        violations.append(f"LogP ({logp}) outside [-0.4, 5.6]")
    if mw is not None and not (160 <= mw <= 480):
        violations.append(f"Molecular weight ({mw}) outside [160, 480]")
    if mr is not None and not (40 <= mr <= 130):
        violations.append(f"Molar refractivity ({mr}) outside [40, 130]")
    if atoms is not None and not (20 <= atoms <= 70):
        violations.append(f"Atom count ({atoms}) outside [20, 70]")

    return {
        "passes": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
    }


def check_muegge_filter(properties: dict[str, Any]) -> dict[str, Any]:
    """Check the Muegge (BMS) drug-likeness filter.

    Muegge et al. (2001): 200 <= MW <= 600, -2 <= logP <= 5,
    TPSA <= 150, HBD <= 5, HBA <= 10, rotatable bonds <= 15,
    rings <= 7, and at least 4 carbon atoms.
    """
    violations = []
    mw = properties.get("molecular_weight")
    logp = properties.get("logp")
    tpsa = properties.get("tpsa")
    hbd = properties.get("hbd")
    hba = properties.get("hba")
    rot = properties.get("rotatable_bonds")
    rings = properties.get("total_rings")
    carbons = properties.get("num_carbons")

    if mw is not None and not (200 <= mw <= 600):
        violations.append(f"Molecular weight ({mw}) outside [200, 600]")
    if logp is not None and not (-2 <= logp <= 5):
        violations.append(f"LogP ({logp}) outside [-2, 5]")
    if tpsa is not None and tpsa > 150:
        violations.append(f"TPSA ({tpsa}) > 150")
    if hbd is not None and hbd > 5:
        violations.append(f"HBD ({hbd}) > 5")
    if hba is not None and hba > 10:
        violations.append(f"HBA ({hba}) > 10")
    if rot is not None and rot > 15:
        violations.append(f"Rotatable bonds ({rot}) > 15")
    if rings is not None and rings > 7:
        violations.append(f"Ring count ({rings}) > 7")
    if carbons is not None and carbons < 4:
        violations.append(f"Carbon count ({carbons}) < 4")

    return {
        "passes": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
    }


def assess_drug_likeness(properties: dict[str, Any]) -> dict[str, Any]:
    """Comprehensive drug-likeness assessment.

    Args:
        properties: Dictionary of molecular properties

    Returns:
        Dictionary with drug-likeness assessment
    """
    lipinski = check_lipinski_rule_of_five(properties)
    veber = check_veber_rules(properties)
    egan = check_egan_rules(properties)
    ghose = check_ghose_filter(properties)
    muegge = check_muegge_filter(properties)

    # Count total violations
    total_violations = (
        lipinski["violation_count"] +
        veber["violation_count"] +
        egan["violation_count"] +
        ghose["violation_count"] +
        muegge["violation_count"]
    )
    
    # Determine overall assessment
    if total_violations == 0:
        assessment = "Excellent"
        score = 1.0
    elif total_violations <= 2:
        assessment = "Good"
        score = 0.75
    elif total_violations <= 4:
        assessment = "Moderate"
        score = 0.5
    else:
        assessment = "Poor"
        score = 0.25
    
    # Use QED if available
    qed = properties.get("qed")
    if qed is not None:
        # Blend rule-based and QED scores
        score = round(0.6 * score + 0.4 * qed, 3)
    
    return {
        "overall_score": score,
        "assessment": assessment,
        "lipinski": lipinski,
        "veber": veber,
        "egan": egan,
        "ghose": ghose,
        "muegge": muegge,
        "qed": qed,
        "total_violations": total_violations,
    }


def calculate_all_properties(smiles: str) -> dict[str, Any]:
    """Calculate all molecular properties and assessments.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Complete property dictionary
    """
    properties = calculate_molecular_properties(smiles)
    
    if "error" in properties:
        return properties
    
    drug_likeness = assess_drug_likeness(properties)
    
    return {
        "smiles": smiles,
        "properties": properties,
        "drug_likeness": drug_likeness,
    }


def batch_calculate_properties(smiles_list: list[str]) -> list[dict[str, Any]]:
    """Calculate properties for multiple SMILES strings.
    
    Args:
        smiles_list: List of SMILES strings
        
    Returns:
        List of property dictionaries
    """
    results = []
    for smiles in smiles_list:
        results.append(calculate_all_properties(smiles))
    return results