"""Molecular descriptor and fingerprint calculation for drug-target interaction prediction."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors, rdFingerprintGenerator, Lipinski
    from rdkit.Chem.rdMolDescriptors import CalcNumRotatableBonds, CalcTPSA, CalcNumHBD, CalcNumHBA
    from rdkit.Chem.rdMolDescriptors import CalcExactMW, CalcNumAromaticRings, CalcNumAliphaticRings
    from rdkit.Chem.rdMolDescriptors import CalcNumHeteroatoms, CalcFractionCSP3, CalcLabuteASA
    RDKit_AVAILABLE = True
except ImportError:
    RDKit_AVAILABLE = False

logger = logging.getLogger(__name__)


DESCRIPTOR_NAMES = [
    "molecular_weight",
    "logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "aromatic_rings",
    "aliphatic_rings",
    "heteroatoms",
    "fraction_csp3",
    "labute_asa",
    "exact_mw",
    "num_atoms",
    "num_bonds",
    "num_rings",
    "num_heterocycles",
    "num_saturated_rings",
    "num_bridgehead_atoms",
    "num_spiro_atoms",
    "bertz_ct",
    "hall_kier_alpha",
    "kappa1",
    "kappa2",
    "kappa3",
    "chi0",
    "chi1",
    "chi0v",
    "chi1v",
]


def calculate_molecular_descriptors(smiles: str) -> dict[str, float | None]:
    """Calculate comprehensive molecular descriptors from SMILES string.
    
    Args:
        smiles: SMILES representation of the molecule
        
    Returns:
        Dictionary of descriptor names to values (None if calculation fails)
    """
    if not RDKit_AVAILABLE:
        logger.warning("RDKit not available, returning empty descriptors")
        return {name: None for name in DESCRIPTOR_NAMES}
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("Invalid SMILES: %s", smiles)
            return {name: None for name in DESCRIPTOR_NAMES}
        
        mol = Chem.AddHs(mol)
        
        descriptors = {}
        
        # Basic properties
        descriptors["molecular_weight"] = Descriptors.MolWt(mol)
        descriptors["logp"] = Descriptors.MolLogP(mol)
        descriptors["tpsa"] = CalcTPSA(mol)
        descriptors["hbd"] = CalcNumHBD(mol)
        descriptors["hba"] = CalcNumHBA(mol)
        descriptors["rotatable_bonds"] = CalcNumRotatableBonds(mol)
        descriptors["aromatic_rings"] = CalcNumAromaticRings(mol)
        descriptors["aliphatic_rings"] = CalcNumAliphaticRings(mol)
        descriptors["heteroatoms"] = CalcNumHeteroatoms(mol)
        descriptors["fraction_csp3"] = CalcFractionCSP3(mol)
        descriptors["labute_asa"] = CalcLabuteASA(mol)
        descriptors["exact_mw"] = CalcExactMW(mol)
        
        # Count-based descriptors
        descriptors["num_atoms"] = mol.GetNumAtoms()
        descriptors["num_bonds"] = mol.GetNumBonds()
        
        # Ring descriptors
        ri = mol.GetRingInfo()
        descriptors["num_rings"] = ri.NumRings()
        
        # Lipinski
        descriptors["num_heterocycles"] = Lipinski.NumHeterocycles(mol)
        descriptors["num_saturated_rings"] = Lipinski.NumSaturatedRings(mol)
        
        # Topological
        descriptors["num_bridgehead_atoms"] = Descriptors.NumBridgeheadAtoms(mol)
        descriptors["num_spiro_atoms"] = Descriptors.NumSpiroAtoms(mol)
        descriptors["bertz_ct"] = Descriptors.BertzCT(mol)
        descriptors["hall_kier_alpha"] = Descriptors.HallKierAlpha(mol)
        descriptors["kappa1"] = Descriptors.Kappa1(mol)
        descriptors["kappa2"] = Descriptors.Kappa2(mol)
        descriptors["kappa3"] = Descriptors.Kappa3(mol)
        descriptors["chi0"] = Descriptors.Chi0(mol)
        descriptors["chi1"] = Descriptors.Chi1(mol)
        descriptors["chi0v"] = Descriptors.Chi0v(mol)
        descriptors["chi1v"] = Descriptors.Chi1v(mol)
        
        return descriptors
        
    except Exception as e:
        logger.error("Descriptor calculation failed for SMILES %s: %s", smiles, e)
        return {name: None for name in DESCRIPTOR_NAMES}


def calculate_morgan_fingerprint(smiles: str, radius: int = 2, n_bits: int = 2048) -> np.ndarray | None:
    """Calculate Morgan fingerprint (ECFP) for a molecule.
    
    Args:
        smiles: SMILES string
        radius: Fingerprint radius (default 2 for ECFP4)
        n_bits: Number of bits in fingerprint
        
    Returns:
        Numpy array of fingerprint bits or None if failed
    """
    if not RDKit_AVAILABLE:
        logger.warning("RDKit not available, cannot calculate fingerprint")
        return None
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        fp_gen = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=n_bits)
        fp = fp_gen.GetFingerprint(mol)
        return np.array(fp, dtype=np.uint8)
        
    except Exception as e:
        logger.error("Morgan fingerprint calculation failed: %s", e)
        return None


def calculate_maccs_keys(smiles: str) -> np.ndarray | None:
    """Calculate MACCS keys fingerprint.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Numpy array of 166 MACCS keys or None if failed
    """
    if not RDKit_AVAILABLE:
        logger.warning("RDKit not available, cannot calculate MACCS keys")
        return None
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        fp_gen = rdFingerprintGenerator.GetRDKitFPGenerator(fpSize=166)
        fp = fp_gen.GetFingerprint(mol)
        return np.array(fp, dtype=np.uint8)
        
    except Exception as e:
        logger.error("MACCS keys calculation failed: %s", e)
        return None


def calculate_rdkit_fingerprint(smiles: str, n_bits: int = 2048) -> np.ndarray | None:
    """Calculate RDKit topological fingerprint.
    
    Args:
        smiles: SMILES string
        n_bits: Number of bits
        
    Returns:
        Numpy array of fingerprint bits or None if failed
    """
    if not RDKit_AVAILABLE:
        logger.warning("RDKit not available, cannot calculate RDKit fingerprint")
        return None
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        fp_gen = rdFingerprintGenerator.GetRDKitFPGenerator(fpSize=n_bits)
        fp = fp_gen.GetFingerprint(mol)
        return np.array(fp, dtype=np.uint8)
        
    except Exception as e:
        logger.error("RDKit fingerprint calculation failed: %s", e)
        return None


def calculate_all_fingerprints(smiles: str) -> dict[str, np.ndarray]:
    """Calculate all available fingerprints for a molecule.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Dictionary of fingerprint name to numpy array
    """
    fingerprints = {}
    
    morgan = calculate_morgan_fingerprint(smiles)
    if morgan is not None:
        fingerprints["morgan_ecfp4"] = morgan
    
    maccs = calculate_maccs_keys(smiles)
    if maccs is not None:
        fingerprints["maccs_keys"] = maccs
    
    rdkit_fp = calculate_rdkit_fingerprint(smiles)
    if rdkit_fp is not None:
        fingerprints["rdkit_fp"] = rdkit_fp
    
    return fingerprints


def smiles_to_features(smiles: str, include_fingerprints: bool = True) -> dict[str, Any]:
    """Convert SMILES to feature dictionary for ML models.
    
    Args:
        smiles: SMILES string
        include_fingerprints: Whether to include fingerprint features
        
    Returns:
        Dictionary with descriptors and optionally fingerprints
    """
    features = calculate_molecular_descriptors(smiles)
    features["smiles"] = smiles
    
    if include_fingerprints:
        fps = calculate_all_fingerprints(smiles)
        for name, fp in fps.items():
            features[name] = fp
    
    return features


def batch_calculate_descriptors(smiles_list: list[str]) -> pd.DataFrame:
    """Calculate descriptors for a batch of SMILES strings.
    
    Args:
        smiles_list: List of SMILES strings
        
    Returns:
        DataFrame with one row per molecule and descriptor columns
    """
    results = []
    for smiles in smiles_list:
        desc = calculate_molecular_descriptors(smiles)
        desc["smiles"] = smiles
        results.append(desc)
    
    return pd.DataFrame(results)


def batch_calculate_fingerprints(smiles_list: list[str], fp_type: str = "morgan") -> np.ndarray | None:
    """Calculate fingerprint matrix for a batch of SMILES.
    
    Args:
        smiles_list: List of SMILES strings
        fp_type: Type of fingerprint ("morgan", "maccs", "rdkit")
        
    Returns:
        2D numpy array (n_samples x n_bits) or None if failed
    """
    if not RDKit_AVAILABLE:
        return None
    
    fingerprints = []
    for smiles in smiles_list:
        if fp_type == "morgan":
            fp = calculate_morgan_fingerprint(smiles)
        elif fp_type == "maccs":
            fp = calculate_maccs_keys(smiles)
        elif fp_type == "rdkit":
            fp = calculate_rdkit_fingerprint(smiles)
        else:
            fp = calculate_morgan_fingerprint(smiles)
        
        if fp is not None:
            fingerprints.append(fp)
        else:
            fingerprints.append(np.zeros(2048 if fp_type != "maccs" else 166, dtype=np.uint8))
    
    return np.vstack(fingerprints) if fingerprints else None


def get_descriptor_names() -> list[str]:
    """Get list of available descriptor names."""
    return DESCRIPTOR_NAMES.copy()


def is_rdkit_available() -> bool:
    """Check if RDKit is available."""
    return RDKit_AVAILABLE