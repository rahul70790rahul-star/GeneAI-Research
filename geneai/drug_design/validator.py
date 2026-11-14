"""Molecule validator module for drug design."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, AllChem
from rdkit.Chem import Lipinski
from rdkit.Chem import QED
from rdkit.Chem import FilterCatalog
from rdkit.Chem.FilterCatalog import FilterCatalogParams

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of molecule validation."""
    smiles: str
    is_valid: bool
    validity_issues: list[str] = field(default_factory=list)
    
    # Drug-likeness
    passes_lipinski: bool = False
    passes_ghose: bool = False
    passes_veber: bool = False
    passes_egan: bool = False
    passes_muegge: bool = False
    
    # Scores
    qed: float = 0.0
    sa_score: float = 0.0
    lipinski_violations: int = 0
    ghose_violations: int = 0
    veber_violations: int = 0
    egan_violations: int = 0
    muegge_violations: int = 0
    
    # Toxicity
    pains_alerts: list[str] = field(default_factory=list)
    structural_alerts: list[str] = field(default_factory=list)
    
    # Synthesizability
    retrosynthesis_score: float | None = None
    building_blocks_available: bool = False
    
    # Overall assessment
    overall_score: float = 0.0
    recommendation: str = "unknown"  # "excellent", "good", "moderate", "poor", "reject"


class MoleculeValidator:
    """
    Validate molecules for drug-likeness, synthesizability, and safety.
    
    Checks:
    - Chemical validity (valence, aromaticity, etc.)
    - Drug-likeness rules (Lipinski, Ghose, Veber, Egan, Muegge)
    - QED and SA scores
    - PAINS and structural alerts
    - Synthesizability (retrosynthetic analysis)
    - Building block availability
    """
    
    # PAINS patterns
    PAINS_SMARTS = {
        "azo_dye": "[N]=[N]c1ccccc1",
        "quinone": "O=c1ccccc1=O",
        "rhodanine": "C1=C(NC(=O)SC1)C(=O)O",
        "thiazolidinedione": "C1C(=O)NC(=O)S1",
        "catechol": "Oc1ccccc1O",
        "hydroquinone": "Oc1ccc(O)cc1",
        "enone": "C=CC(=O)C",
        "michael_acceptor": "C=C[C,N,O,S]",
    }
    
    # Structural alerts
    STRUCTURAL_ALERTS = {
        "alkylating_agent": "[Cl,Br,I][CH2,CH]",
        "epoxide": "C1OC1",
        "aziridine": "C1NC1",
        "nitroso": "N=O",
        "nitro_aromatic": "[N+](=O)[O-]c",
        "aldehyde": "[CX3H1]=O",
        "epoxide_like": "O1CC1",
        "acyl_halide": "[CX3](=O)[Cl,Br,I]",
        "sulfonyl_halide": "[SX4](=O)(=O)[Cl,Br,I]",
        "isocyanate": "[NX2]=[C]=O",
        "thioisocyanate": "[NX2]=[C]=S",
        "carbodiimide": "[NX2]=[C]=[NX2]",
    }
    
    # Known reactive groups
    REACTIVE_GROUPS = {
        "epoxide": "C1OC1",
        "aziridine": "C1NC1",
        "epoxide_like": "O1CC1",
        "azete": "C1NCC1",
        "beta_lactam": "C1C(=O)NC1",
        "alpha_halo_ketone": "[Cl,Br,I][CH2][CX3](=O)",
        "alpha_halo_amide": "[Cl,Br,I][CH2][CX3](=O)[N]",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_pains_catalog()
    
    def _init_pains_catalog(self):
        """Initialize PAINS filter catalog."""
        try:
            params = FilterCatalogParams()
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_C)
            self.pains_catalog = FilterCatalog(params)
        except Exception as e:
            self.logger.warning("Failed to initialize PAINS catalog: %s", e)
            self.pains_catalog = None
    
    def validate(self, smiles: str) -> ValidationResult:
        """
        Comprehensive molecule validation.
        
        Args:
            smiles: SMILES string to validate
            
        Returns:
            ValidationResult with all checks
        """
        result = ValidationResult(smiles=smiles)
        
        # Parse molecule
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            result.is_valid = False
            result.validity_issues.append("Invalid SMILES - could not parse")
            result.recommendation = "reject"
            return result
        
        # Check chemical validity
        validity_issues = self._check_chemical_validity(mol)
        result.validity_issues = validity_issues
        result.is_valid = len(validity_issues) == 0
        
        if not result.is_valid:
            result.recommendation = "reject"
            return result
        
        # Calculate properties
        props = self._calculate_properties(mol)
        
        # Drug-likeness rules
        result.passes_lipinski = self._check_lipinski(props)
        result.passes_ghose = self._check_ghose(props)
        result.passes_veber = self._check_veber(props)
        result.passes_egan = self._check_egan(props)
        result.passes_muegge = self._check_muegge(props)
        
        # Violation counts
        result.lipinski_violations = self._count_lipinski_violations(props)
        result.ghose_violations = self._count_ghose_violations(props)
        result.veber_violations = self._count_veber_violations(props)
        result.egan_violations = self._count_egan_violations(props)
        result.muegge_violations = self._count_muegge_violations(props)
        
        # Scores
        result.qed = self._calculate_qed(mol)
        result.sa_score = self._calculate_sa_score(mol)
        
        # Alerts
        result.pains_alerts = self._check_pains(mol)
        result.structural_alerts = self._check_structural_alerts(mol)
        
        # Synthesizability
        result.retrosynthesis_score = self._estimate_retrosynthesis(mol)
        result.building_blocks_available = self._check_building_blocks(mol)
        
        # Overall assessment
        result.overall_score = self._calculate_overall_score(result)
        result.recommendation = self._get_recommendation(result)
        
        return result
    
    def _check_chemical_validity(self, mol: Chem.Mol) -> list[str]:
        """Check chemical validity of molecule."""
        issues = []
        
        # Sanitization check
        try:
            Chem.SanitizeMol(mol)
        except Exception as e:
            issues.append(f"Sanitization failed: {e}")
        
        # Valence check
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() > 1:  # Not hydrogen
                valence = atom.GetExplicitValence()
                max_valence = atom.GetDefaultValence()
                if valence > max_valence:
                    issues.append(f"Atom {atom.GetIdx()} ({atom.GetSymbol()}) exceeds max valence: {valence} > {max_valence}")
        
        # Aromaticity check
        for ring in mol.GetRingInfo().AtomRings():
            aromatic_atoms = sum(1 for idx in ring if mol.GetAtomWithIdx(idx).GetIsAromatic())
            if aromatic_atoms > 0 and aromatic_atoms != len(ring):
                issues.append(f"Ring {list(ring)} has mixed aromatic/non-aromatic atoms")
        
        # Charge check
        total_charge = Chem.GetFormalCharge(mol)
        if abs(total_charge) > 2:
            issues.append(f"High formal charge: {total_charge}")
        
        # Stereochemistry check
        chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
        if len(chiral_centers) > 10:
            issues.append(f"Many chiral centers ({len(chiral_centers)}) - may complicate synthesis")
        
        return issues
    
    def _calculate_properties(self, mol: Chem.Mol) -> dict[str, float]:
        """Calculate key molecular properties."""
        return {
            "mw": Descriptors.MolWt(mol),
            "logp": Descriptors.MolLogP(mol),
            "hbd": Descriptors.NumHDonors(mol),
            "hba": Descriptors.NumHAcceptors(mol),
            "tpsa": rdMolDescriptors.CalcTPSA(mol),
            "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "num_rings": rdMolDescriptors.CalcNumRings(mol),
            "formal_charge": Chem.GetFormalCharge(mol),
            "refractivity": Descriptors.MolMR(mol),
            "num_heteroatoms": rdMolDescriptors.CalcNumHeteroatoms(mol),
        }
    
    def _check_lipinski(self, props: dict[str, float]) -> bool:
        """Check Lipinski Rule of Five."""
        return (
            props["mw"] <= 500 and
            props["logp"] <= 5 and
            props["hbd"] <= 5 and
            props["hba"] <= 10
        )
    
    def _count_lipinski_violations(self, props: dict[str, float]) -> int:
        violations = 0
        if props["mw"] > 500: violations += 1
        if props["logp"] > 5: violations += 1
        if props["hbd"] > 5: violations += 1
        if props["hba"] > 10: violations += 1
        return violations
    
    def _check_ghose(self, props: dict[str, float]) -> bool:
        """Check Ghose filter."""
        return (
            160 <= props["mw"] <= 480 and
            -0.4 <= props["logp"] <= 5.6 and
            20 <= props["heavy_atoms"] <= 70 and
            (props["refractivity"] is None or 40 <= props["refractivity"] <= 130)
        )
    
    def _count_ghose_violations(self, props: dict[str, float]) -> int:
        violations = 0
        if not (160 <= props["mw"] <= 480): violations += 1
        if not (-0.4 <= props["logp"] <= 5.6): violations += 1
        if not (20 <= props["heavy_atoms"] <= 70): violations += 1
        if props["refractivity"] is not None and not (40 <= props["refractivity"] <= 130): violations += 1
        return violations
    
    def _check_veber(self, props: dict[str, float]) -> bool:
        """Check Veber rules."""
        return (
            props["rotatable_bonds"] <= 10 and
            props["tpsa"] <= 140
        )
    
    def _count_veber_violations(self, props: dict[str, float]) -> int:
        violations = 0
        if props["rotatable_bonds"] > 10: violations += 1
        if props["tpsa"] > 140: violations += 1
        return violations
    
    def _check_egan(self, props: dict[str, float]) -> bool:
        """Check Egan filter."""
        return (
            props["logp"] <= 5.88 and
            props["tpsa"] <= 131.6
        )
    
    def _count_egan_violations(self, props: dict[str, float]) -> int:
        violations = 0
        if props["logp"] > 5.88: violations += 1
        if props["tpsa"] > 131.6: violations += 1
        return violations
    
    def _check_muegge(self, props: dict[str, float]) -> bool:
        """Check Muegge filter."""
        return (
            200 <= props["mw"] <= 600 and
            -2 <= props["logp"] <= 5 and
            props["tpsa"] <= 150 and
            props["rotatable_bonds"] <= 15 and
            props["aromatic_rings"] <= 4 and
            props["heavy_atoms"] <= 50
        )
    
    def _count_muegge_violations(self, props: dict[str, float]) -> int:
        violations = 0
        if not (200 <= props["mw"] <= 600): violations += 1
        if not (-2 <= props["logp"] <= 5): violations += 1
        if props["tpsa"] > 150: violations += 1
        if props["rotatable_bonds"] > 15: violations += 1
        if props["aromatic_rings"] > 4: violations += 1
        if props["heavy_atoms"] > 50: violations += 1
        return violations
    
    def _calculate_qed(self, mol: Chem.Mol) -> float:
        """Calculate QED score."""
        try:
            return QED.qed(mol)
        except Exception:
            return 0.0
    
    def _calculate_sa_score(self, mol: Chem.Mol) -> float:
        """Calculate Synthetic Accessibility Score (simplified)."""
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_heteroatoms = rdMolDescriptors.CalcNumHeteroatoms(mol)
        num_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
        mw = Descriptors.MolWt(mol)
        
        complexity = num_rings * 0.5 + num_heteroatoms * 0.1 + num_chiral * 0.3 + mw * 0.001
        return min(1.0 + complexity, 10.0)
    
    def _check_pains(self, mol: Chem.Mol) -> list[str]:
        """Check for PAINS alerts."""
        alerts = []
        
        if self.pains_catalog:
            matches = self.pains_catalog.GetMatches(mol)
            for match in matches:
                alerts.append(match.GetDescription())
        else:
            # Fallback to SMARTS patterns
            for name, smarts in self.PAINS_SMARTS.items():
                pattern = Chem.MolFromSmarts(smarts)
                if pattern and mol.HasSubstructMatch(pattern):
                    alerts.append(name)
        
        return alerts
    
    def _check_structural_alerts(self, mol: Chem.Mol) -> list[str]:
        """Check for structural alerts."""
        alerts = []
        for name, smarts in self.STRUCTURAL_ALERTS.items():
            pattern = Chem.MolFromSmarts(smarts)
            if pattern and mol.HasSubstructMatch(pattern):
                alerts.append(name)
        return alerts
    
    def _estimate_retrosynthesis(self, mol: Chem.Mol) -> float:
        """Estimate retrosynthetic difficulty (0-1, higher = easier)."""
        # Simplified heuristic
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_hetero = rdMolDescriptors.CalcNumHeteroatoms(mol)
        num_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
        mw = Descriptors.MolWt(mol)
        
        # More complex = harder synthesis
        difficulty = num_rings * 0.15 + num_hetero * 0.05 + num_chiral * 0.1 + mw * 0.0005
        return max(0.0, 1.0 - difficulty)
    
    def _check_building_blocks(self, mol: Chem.Mol) -> bool:
        """Check if likely synthesizable from available building blocks."""
        # Simplified: check if BRICS fragments are common
        try:
            fragments = list(BRICS.BRICSDecompose(mol))
            # If all fragments are small and common, likely synthesizable
            return all(len(Chem.MolFromSmiles(f).GetAtoms()) < 20 for f in fragments if f)
        except Exception:
            return True  # Default to True if can't check
    
    def _calculate_overall_score(self, result: ValidationResult) -> float:
        """Calculate overall drug-likeness score (0-1)."""
        score = 0.0
        
        # Rule compliance (40% weight)
        rules_passed = sum([
            result.passes_lipinski,
            result.passes_ghose,
            result.passes_veber,
            result.passes_egan,
            result.passes_muegge,
        ])
        score += (rules_passed / 5) * 0.4
        
        # QED (30% weight)
        score += result.qed * 0.3
        
        # SA score (20% weight) - inverted (lower SA = better)
        sa_normalized = max(0, 1 - (result.sa_score - 1) / 9)
        score += sa_normalized * 0.2
        
        # Alerts penalty (10% weight)
        alert_penalty = min(1.0, (len(result.pains_alerts) + len(result.structural_alerts)) * 0.2)
        score += (1 - alert_penalty) * 0.1
        
        return round(score, 3)
    
    def _get_recommendation(self, result: ValidationResult) -> str:
        """Get overall recommendation."""
        if not result.is_valid:
            return "reject"
        
        if result.overall_score >= 0.8:
            return "excellent"
        elif result.overall_score >= 0.6:
            return "good"
        elif result.overall_score >= 0.4:
            return "moderate"
        elif result.overall_score >= 0.2:
            return "poor"
        else:
            return "reject"
    
    def batch_validate(self, smiles_list: list[str]) -> list[ValidationResult]:
        """Validate multiple molecules."""
        return [self.validate(smi) for smi in smiles_list]
    
    def filter_library(
        self,
        smiles_list: list[str],
        min_score: float = 0.5,
        require_lipinski: bool = True,
        max_pains: int = 0,
    ) -> list[ValidationResult]:
        """Filter a library by validation criteria."""
        results = self.batch_validate(smiles_list)
        
        filtered = []
        for r in results:
            if r.overall_score < min_score:
                continue
            if require_lipinski and not r.passes_lipinski:
                continue
            if len(r.pains_alerts) > max_pains:
                continue
            filtered.append(r)
        
        return filtered


def validate_molecule(smiles: str) -> ValidationResult:
    """Convenience function for molecule validation."""
    validator = MoleculeValidator()
    return validator.validate(smiles)