"""Molecular property calculation module."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, Lipinski, Crippen
from rdkit.Chem import AllChem
from rdkit.Chem import rdMolAlign
from rdkit.Chem import rdDistGeom

logger = logging.getLogger(__name__)


@dataclass
class MolecularProperties:
    """Comprehensive molecular properties."""
    # Basic properties
    smiles: str
    molecular_weight: float
    exact_mass: float
    formula: str
    
    # Lipinski properties
    logp: float
    hbd: int
    hba: int
    tpsa: float
    rotatable_bonds: int
    
    # Extended properties
    logd_ph74: float | None = None
    logd_ph55: float | None = None
    logd_ph95: float | None = None
    
    # Structural properties
    heavy_atoms: int = 0
    aromatic_rings: int = 0
    aliphatic_rings: int = 0
    saturated_rings: int = 0
    heteroatoms: int = 0
    formal_charge: int = 0
    num_rings: int = 0
    num_bridges: int = 0
    num_spiro: int = 0
    
    # 3D properties (if conformer available)
    radius_of_gyration: float | None = None
    principal_moments: list[float] = field(default_factory=list)
    asphericity: float | None = None
    eccentricity: float | None = None
    inertial_shape_factor: float | None = None
    
    # Electronic properties
    refractivity: float | None = None
    polarizability: float | None = None
    dipole_moment: float | None = None
    
    # Drug-likeness scores
    qed: float | None = None
    sa_score: float | None = None
    lipinski_violations: int = 0
    ghose_violations: int = 0
    veber_violations: int = 0
    egan_violations: int = 0
    muegge_violations: int = 0
    
    # Toxicity alerts
    pains_alerts: list[str] = field(default_factory=list)
    structural_alerts: list[str] = field(default_factory=list)
    
    # Fingerprints
    morgan_fp: str | None = None
    rdkit_fp: str | None = None
    maccs_fp: str | None = None
    
    # Conformer info
    num_conformers: int = 0
    min_energy: float | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style access for backwards compatibility with display code."""
        aliases = {
            "mw": "molecular_weight",
            "molecular_weight": "molecular_weight",
            "logp": "logp",
            "logd": "logd_ph74",
            "hbd": "hbd",
            "hba": "hba",
            "tpsa": "tpsa",
            "rotatable_bonds": "rotatable_bonds",
            "qed": "qed",
            "sa_score": "sa_score",
        }
        return getattr(self, aliases.get(key, key), default)

    def to_dict(self) -> dict[str, Any]:
        """Return all properties as a plain dictionary."""
        from dataclasses import asdict

        return asdict(self)


class PropertyCalculator:
    """
    Calculate comprehensive molecular properties.
    
    Capabilities:
    - All RDKit descriptors
    - Lipinski, Ghose, Veber, Egan, Muegge rule checking
    - 3D properties (requires conformer generation)
    - PAINS and structural alert detection
    - Fingerprint generation
    - QED and SA score calculation
    """
    
    # PAINS SMARTS patterns (subset)
    PAINS_PATTERNS = {
        "azo_dye": "[N]=[N]c1ccccc1",
        "quinone": "O=c1ccccc1=O",
        "rhodanine": "C1=C(NC(=O)SC1)C(=O)O",
        "thiazolidinedione": "C1C(=O)NC(=O)S1",
        "enone": "C=CC(=O)C",
        "michael_acceptor": "C=C[C,N,O,S]",
        "catechol": "Oc1ccccc1O",
        "hydroquinone": "Oc1ccc(O)cc1",
    }
    
    # Structural alert patterns
    STRUCTURAL_ALERTS = {
        "alkylating_agent": "[Cl,Br,I][CH2,CH]",
        "epoxide": "C1OC1",
        "aziridine": "C1NC1",
        "nitroso": "N=O",
        "nitro": "[N+](=O)[O-]",
        "aldehyde": "[CX3H1]=O",
        "epoxide_like": "O1CC1",
        "Michael_acceptor_alpha_beta": "C=CC(=O)[C,N,O,S]",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_properties(
        self,
        smiles: str,
        generate_3d: bool = False,
        num_conformers: int = 10,
    ) -> MolecularProperties:
        """
        Calculate all molecular properties.
        
        Args:
            smiles: SMILES string
            generate_3d: Whether to generate 3D conformers
            num_conformers: Number of conformers to generate
            
        Returns:
            MolecularProperties object
        """
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            raise ValueError(f"Invalid SMILES: {smiles}")
        
        # Add hydrogens for accurate calculations
        mol = Chem.AddHs(mol)
        
        # Generate 3D conformers if requested
        conformers = []
        if generate_3d:
            conformers = self._generate_conformers(mol, num_conformers)
        
        props = MolecularProperties(
            smiles=smiles,
            molecular_weight=Descriptors.MolWt(mol),
            exact_mass=Descriptors.ExactMolWt(mol),
            formula=rdMolDescriptors.CalcMolFormula(mol),
            logp=Descriptors.MolLogP(mol),
            hbd=Descriptors.NumHDonors(mol),
            hba=Descriptors.NumHAcceptors(mol),
            tpsa=rdMolDescriptors.CalcTPSA(mol),
            rotatable_bonds=Descriptors.NumRotatableBonds(mol),
            heavy_atoms=mol.GetNumHeavyAtoms(),
            aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol),
            aliphatic_rings=rdMolDescriptors.CalcNumAliphaticRings(mol),
            saturated_rings=rdMolDescriptors.CalcNumSaturatedRings(mol),
            heteroatoms=rdMolDescriptors.CalcNumHeteroatoms(mol),
            formal_charge=Chem.GetFormalCharge(mol),
            num_rings=rdMolDescriptors.CalcNumRings(mol),
            num_bridges=rdMolDescriptors.CalcNumBridgeheadAtoms(mol),
            num_spiro=rdMolDescriptors.CalcNumSpiroAtoms(mol),
            refractivity=Descriptors.MolMR(mol),
        )
        
        # Calculate LogD at different pH (approximate)
        props.logd_ph74 = self._estimate_logd(props.logp, mol, 7.4)
        props.logd_ph55 = self._estimate_logd(props.logp, mol, 5.5)
        props.logd_ph95 = self._estimate_logd(props.logp, mol, 9.5)
        
        # 3D properties from conformers
        if conformers:
            props.num_conformers = len(conformers)
            props = self._calculate_3d_properties(props, conformers)
        
        # Drug-likeness scores
        props.qed = self._calculate_qed(mol)
        props.sa_score = self._calculate_sa_score(mol)
        
        # Rule violations
        props.lipinski_violations = self._check_lipinski(props)
        props.ghose_violations = self._check_ghose(props)
        props.veber_violations = self._check_veber(props)
        props.egan_violations = self._check_egan(props)
        props.muegge_violations = self._check_muegge(props)
        
        # Alerts
        props.pains_alerts = self._check_pains(mol)
        props.structural_alerts = self._check_structural_alerts(mol)
        
        # Fingerprints
        props.morgan_fp = self._get_fingerprint_hex(mol, "morgan")
        props.rdkit_fp = self._get_fingerprint_hex(mol, "rdkit")
        props.maccs_fp = self._get_fingerprint_hex(mol, "maccs")
        
        return props
    
    def _generate_conformers(self, mol: Chem.Mol, num_conformers: int) -> list[Chem.Mol]:
        """Generate 3D conformers."""
        try:
            # Embed multiple conformers
            cids = rdDistGeom.EmbedMultipleConfs(
                mol,
                numConfs=num_conformers,
                randomSeed=42,
                pruneRmsThresh=0.5,
            )
            
            # Optimize with MMFF
            for cid in cids:
                AllChem.MMFFOptimizeMolecule(mol, confId=cid)
            
            return [mol.GetConformer(int(cid)) for cid in cids]
        except Exception as e:
            self.logger.warning("Conformer generation failed: %s", e)
            return []
    
    def _calculate_3d_properties(
        self,
        props: MolecularProperties,
        conformers: list[Chem.Conformer],
    ) -> MolecularProperties:
        """Calculate 3D properties from conformers."""
        try:
            # Use first conformer for properties
            conf = conformers[0]
            mol = conf.GetOwningMol()
            
            # Principal moments of inertia
            from rdkit.Chem import rdMolDescriptors
            pm = rdMolDescriptors.CalcPrincipalMomentsOfInertia(mol, confId=conf.GetId())
            props.principal_moments = list(pm)
            
            if len(pm) == 3:
                I1, I2, I3 = sorted(pm)
                if I3 > 0:
                    props.asphericity = (I3 - (I1 + I2) / 2) / I3
                    props.eccentricity = (I2 - I1) / I3
                    props.inertial_shape_factor = 3 * I1 * I2 / (I3 ** 2) if I3 > 0 else 0
            
            # Radius of gyration
            props.radius_of_gyration = rdMolDescriptors.CalcRadiusOfGyration(mol, confId=conf.GetId())
            
            # Dipole moment (approximate from partial charges)
            # Would need charge calculation
            
        except Exception as e:
            self.logger.warning("3D property calculation failed: %s", e)
        
        return props
    
    def _estimate_logd(self, logp: float, mol: Chem.Mol, ph: float) -> float:
        """Estimate LogD at given pH (simplified)."""
        # Very simplified - real implementation would use pKa prediction
        # For now, return logP with small correction for ionizable groups
        
        # Count basic and acidic groups
        basic_pattern = Chem.MolFromSmarts("[NX3;H2,H1;!$(NC=O)]")
        acidic_pattern = Chem.MolFromSmarts("[CX3](=O)[OX2H1]")
        
        basic_count = len(mol.GetSubstructMatches(basic_pattern)) if basic_pattern else 0
        acidic_count = len(mol.GetSubstructMatches(acidic_pattern)) if acidic_pattern else 0
        
        # Simplified Henderson-Hasselbalch
        logd = logp
        if basic_count > 0:
            # Basic groups protonated at low pH
            if ph < 7:
                logd -= 0.5 * basic_count
        if acidic_count > 0:
            # Acidic groups deprotonated at high pH
            if ph > 7:
                logd -= 0.5 * acidic_count
        
        return logd
    
    def _calculate_qed(self, mol: Chem.Mol) -> float:
        """Calculate QED (Quantitative Estimate of Drug-likeness)."""
        try:
            from rdkit.Chem import QED
            return QED.qed(mol)
        except Exception:
            return 0.0
    
    def _calculate_sa_score(self, mol: Chem.Mol) -> float:
        """Calculate Synthetic Accessibility Score (simplified)."""
        # Simplified based on molecular complexity
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_hetero = rdMolDescriptors.CalcNumHeteroatoms(mol)
        num_chiral = Chem.CalcNumAtomStereoCenters(mol)
        mw = Descriptors.MolWt(mol)
        
        # Complexity penalty
        complexity = num_rings * 0.5 + num_hetero * 0.1 + num_chiral * 0.3 + mw * 0.001
        return min(1.0 + complexity, 10.0)
    
    def _check_lipinski(self, props: MolecularProperties) -> int:
        """Check Lipinski Rule of Five violations."""
        violations = 0
        if props.molecular_weight > 500:
            violations += 1
        if props.logp > 5:
            violations += 1
        if props.hbd > 5:
            violations += 1
        if props.hba > 10:
            violations += 1
        return violations
    
    def _check_ghose(self, props: MolecularProperties) -> int:
        """Check Ghose filter violations."""
        violations = 0
        if not (160 <= props.molecular_weight <= 480):
            violations += 1
        if not (-0.4 <= props.logp <= 5.6):
            violations += 1
        if not (20 <= props.heavy_atoms <= 70):
            violations += 1
        # Molar refractivity check (approximate)
        if props.refractivity is not None and not (40 <= props.refractivity <= 130):
            violations += 1
        return violations
    
    def _check_veber(self, props: MolecularProperties) -> int:
        """Check Veber rules violations."""
        violations = 0
        if props.rotatable_bonds > 10:
            violations += 1
        if props.tpsa > 140:
            violations += 1
        return violations
    
    def _check_egan(self, props: MolecularProperties) -> int:
        """Check Egan filter violations."""
        violations = 0
        if props.logp > 5.88:
            violations += 1
        if props.tpsa > 131.6:
            violations += 1
        return violations
    
    def _check_muegge(self, props: MolecularProperties) -> int:
        """Check Muegge filter violations."""
        violations = 0
        if not (200 <= props.molecular_weight <= 600):
            violations += 1
        if not (-2 <= props.logp <= 5):
            violations += 1
        if props.tpsa > 150:
            violations += 1
        if props.rotatable_bonds > 15:
            violations += 1
        if props.aromatic_rings > 4:
            violations += 1
        if props.heavy_atoms > 50:
            violations += 1
        return violations
    
    def _check_pains(self, mol: Chem.Mol) -> list[str]:
        """Check for PAINS alerts."""
        alerts = []
        for name, smarts in self.PAINS_PATTERNS.items():
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
    
    def _get_fingerprint_hex(self, mol: Chem.Mol, fp_type: str) -> str:
        """Get fingerprint as hex string."""
        try:
            if fp_type == "morgan":
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
            elif fp_type == "rdkit":
                fp = Chem.RDKFingerprint(mol)
            elif fp_type == "maccs":
                from rdkit.Chem import MACCSkeys
                fp = MACCSkeys.GenMACCSKeys(mol)
            else:
                return ""
            
            return fp.ToBitString()
        except Exception:
            return ""


def calculate_properties(
    smiles: str,
    generate_3d: bool = False,
    num_conformers: int = 10,
) -> MolecularProperties:
    """Convenience function for property calculation."""
    calculator = PropertyCalculator()
    return calculator.calculate_properties(smiles, generate_3d, num_conformers)


def calculate_drug_likeness(smiles: str) -> dict[str, Any]:
    """Summarise drug-likeness rule violations for a SMILES string."""
    props = PropertyCalculator().calculate_properties(smiles)
    return {
        "lipinski_violations": props.lipinski_violations,
        "ghose_violations": props.ghose_violations,
        "veber_violations": props.veber_violations,
        "egan_violations": props.egan_violations,
        "muegge_violations": props.muegge_violations,
        "qed": props.qed,
        "sa_score": props.sa_score,
        "drug_like": props.lipinski_violations <= 1 and props.veber_violations == 0,
    }


def calculate_pains_alerts(smiles: str) -> list[str]:
    """Return PAINS substructure alerts for a SMILES string."""
    return PropertyCalculator().calculate_properties(smiles).pains_alerts


def calculate_structural_alerts(smiles: str) -> list[str]:
    """Return generic structural alerts for a SMILES string."""
    return PropertyCalculator().calculate_properties(smiles).structural_alerts


def calculate_all_properties(smiles: str, generate_3d: bool = False) -> dict[str, Any]:
    """Return every computed property plus drug-likeness and alert summaries."""
    props = PropertyCalculator().calculate_properties(smiles, generate_3d=generate_3d)
    data = props.to_dict()
    data["drug_likeness"] = {
        "lipinski_violations": props.lipinski_violations,
        "ghose_violations": props.ghose_violations,
        "veber_violations": props.veber_violations,
        "egan_violations": props.egan_violations,
        "muegge_violations": props.muegge_violations,
        "qed": props.qed,
        "sa_score": props.sa_score,
        "drug_like": props.lipinski_violations <= 1 and props.veber_violations == 0,
    }
    return data
