"""ADMET prediction module for drug design."""
from __future__ import annotations

import logging
import json
import pickle
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, AllChem, Lipinski, QED
from rdkit.Chem import rdMolHash

logger = logging.getLogger(__name__)


@dataclass
class ADMETProperty:
    """Single ADMET property prediction."""
    name: str
    value: float | str | bool
    unit: str = ""
    confidence: float = 1.0  # 0-1
    method: str = "rule_based"
    reference_range: tuple[float, float] | None = None
    interpretation: str = ""  # "favorable", "unfavorable", "neutral"


@dataclass
class ADMETResult:
    """Complete ADMET prediction result."""
    smiles: str
    properties: list[ADMETProperty] = field(default_factory=list)
    overall_score: float = 0.0
    risk_level: str = "unknown"  # "low", "moderate", "high", "unknown"
    flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    
    def get_property(self, name: str) -> ADMETProperty | None:
        """Get property by name."""
        for prop in self.properties:
            if prop.name.lower() == name.lower():
                return prop
        return None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "smiles": self.smiles,
            "properties": [
                {
                    "name": p.name,
                    "value": p.value,
                    "unit": p.unit,
                    "confidence": p.confidence,
                    "method": p.method,
                    "reference_range": p.reference_range,
                    "interpretation": p.interpretation,
                }
                for p in self.properties
            ],
            "overall_score": self.overall_score,
            "risk_level": self.risk_level,
            "flags": self.flags,
            "recommendations": self.recommendations,
        }


class ADMETPredictor:
    """
    ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) predictor.
    
    Uses rule-based, QSAR, and ML models for prediction.
    """
    
    # Reference ranges for interpretation
    REFERENCE_RANGES = {
        # Absorption
        "caco2_permeability": (0, 100),  # nm/s, higher better
        "hia": (0, 100),  # %, higher better
        "pgp_substrate": (0, 1),  # probability, lower better
        "pgp_inhibitor": (0, 1),  # probability, lower better
        "bioavailability": (0, 100),  # %, higher better
        "lipinski_violations": (0, 5),  # count, lower better
        "ghose_violations": (0, 4),
        "veber_violations": (0, 2),
        
        # Distribution
        "bbb_permeability": (-3, 1),  # logBB, higher better
        "cns_mpo": (0, 6),  # higher better
        "vdss": (0, 20),  # L/kg, lower better
        "plasma_protein_binding": (0, 100),  # %, lower better for free drug
        "volume_of_distribution": (0, 20),
        
        # Metabolism
        "cyp1a2_inhibitor": (0, 1),
        "cyp1a2_substrate": (0, 1),
        "cyp2c9_inhibitor": (0, 1),
        "cyp2c9_substrate": (0, 1),
        "cyp2c19_inhibitor": (0, 1),
        "cyp2c19_substrate": (0, 1),
        "cyp2d6_inhibitor": (0, 1),
        "cyp2d6_substrate": (0, 1),
        "cyp3a4_inhibitor": (0, 1),
        "cyp3a4_substrate": (0, 1),
        "clearance": (0, 100),  # mL/min/kg
        "half_life": (0, 100),  # hours
        
        # Excretion
        "renal_clearance": (0, 500),  # mL/min
        "total_clearance": (0, 100),
        
        # Toxicity
        "ames_mutagenicity": (0, 1),
        "hepatotoxicity": (0, 1),
        "skin_sensitization": (0, 1),
        "eye_irritation": (0, 1),
        "respiratory_toxicity": (0, 1),
        "cardiotoxicity_hERG": (0, 1),
        "acute_oral_toxicity": (0, 5),  # LD50 category
        "carcinogenicity": (0, 1),
        "reproductive_toxicity": (0, 1),
        "developmental_toxicity": (0, 1),
        "ld50": (0, 5000),  # mg/kg
        "noael": (0, 1000),  # mg/kg/day
        
        # Physicochemical
        "molecular_weight": (150, 600),
        "logp": (-2, 6),
        "logd": (-2, 6),
        "tpsa": (20, 140),
        "rotatable_bonds": (0, 15),
        "hbd": (0, 5),
        "hba": (0, 10),
        "formal_charge": (-2, 2),
        "num_rings": (0, 6),
        "aromatic_rings": (0, 4),
        "qed": (0, 1),
        "sa_score": (1, 10),
        "fsp3": (0, 1),
    }
    
    def __init__(
        self,
        use_ml_models: bool = False,
        model_dir: str | None = None,
    ):
        """
        Initialize ADMET predictor.
        
        Args:
            use_ml_models: Whether to use ML models (requires trained models)
            model_dir: Directory containing trained models
        """
        self.use_ml_models = use_ml_models
        self.model_dir = Path(model_dir) if model_dir else None
        self.models = {}
        self.logger = logging.getLogger(__name__)
        
        if use_ml_models and model_dir:
            self._load_models()
    
    def _load_models(self):
        """Load trained ML models."""
        if not self.model_dir or not self.model_dir.exists():
            self.logger.warning("Model directory not found: %s", self.model_dir)
            return
        
        # Expected model files
        model_files = {
            "caco2": "caco2_model.pkl",
            "bbb": "bbb_model.pkl",
            "cyp3a4": "cyp3a4_model.pkl",
            "cyp2d6": "cyp2d6_model.pkl",
            "hERG": "herg_model.pkl",
            "ames": "ames_model.pkl",
            "hepatotoxicity": "hepatotox_model.pkl",
            "clearance": "clearance_model.pkl",
        }
        
        for name, filename in model_files.items():
            path = self.model_dir / filename
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        self.models[name] = pickle.load(f)
                    self.logger.info("Loaded model: %s", name)
                except Exception as e:
                    self.logger.warning("Failed to load model %s: %s", name, e)
    
    def predict(self, smiles: str) -> ADMETResult:
        """
        Predict ADMET properties for a molecule.
        
        Args:
            smiles: Molecule SMILES
            
        Returns:
            ADMETResult with all predictions
        """
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return ADMETResult(
                smiles=smiles,
                flags=["Invalid SMILES"],
                risk_level="unknown",
            )
        
        result = ADMETResult(smiles=smiles)
        
        # Calculate all properties
        properties = []
        
        # Physicochemical properties (always calculated)
        properties.extend(self._predict_physicochemical(mol))
        
        # Absorption
        properties.extend(self._predict_absorption(mol))
        
        # Distribution
        properties.extend(self._predict_distribution(mol))
        
        # Metabolism
        properties.extend(self._predict_metabolism(mol))
        
        # Excretion
        properties.extend(self._predict_excretion(mol))
        
        # Toxicity
        properties.extend(self._predict_toxicity(mol))
        
        result.properties = properties
        
        # Calculate overall score and risk level
        result.overall_score = self._calculate_overall_score(result)
        result.risk_level = self._determine_risk_level(result)
        result.flags = self._generate_flags(result)
        result.recommendations = self._generate_recommendations(result)
        
        return result
    
    def _predict_physicochemical(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict physicochemical properties."""
        props = []
        
        mw = Descriptors.MolWt(mol)
        props.append(ADMETProperty(
            name="Molecular Weight",
            value=round(mw, 2),
            unit="Da",
            reference_range=self.REFERENCE_RANGES["molecular_weight"],
            interpretation=self._interpret_value(mw, "molecular_weight"),
        ))
        
        logp = Descriptors.MolLogP(mol)
        props.append(ADMETProperty(
            name="LogP",
            value=round(logp, 2),
            reference_range=self.REFERENCE_RANGES["logp"],
            interpretation=self._interpret_value(logp, "logp"),
        ))
        
        # LogD at pH 7.4 (approximate)
        logd = self._estimate_logd(mol)
        props.append(ADMETProperty(
            name="LogD (pH 7.4)",
            value=round(logd, 2),
            reference_range=self.REFERENCE_RANGES["logd"],
            interpretation=self._interpret_value(logd, "logd"),
        ))
        
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        props.append(ADMETProperty(
            name="TPSA",
            value=round(tpsa, 2),
            unit="Å²",
            reference_range=self.REFERENCE_RANGES["tpsa"],
            interpretation=self._interpret_value(tpsa, "tpsa"),
        ))
        
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        props.append(ADMETProperty(
            name="Rotatable Bonds",
            value=rot_bonds,
            reference_range=self.REFERENCE_RANGES["rotatable_bonds"],
            interpretation=self._interpret_value(rot_bonds, "rotatable_bonds"),
        ))
        
        hbd = Descriptors.NumHDonors(mol)
        props.append(ADMETProperty(
            name="H-Bond Donors",
            value=hbd,
            reference_range=self.REFERENCE_RANGES["hbd"],
            interpretation=self._interpret_value(hbd, "hbd"),
        ))
        
        hba = Descriptors.NumHAcceptors(mol)
        props.append(ADMETProperty(
            name="H-Bond Acceptors",
            value=hba,
            reference_range=self.REFERENCE_RANGES["hba"],
            interpretation=self._interpret_value(hba, "hba"),
        ))
        
        charge = Chem.GetFormalCharge(mol)
        props.append(ADMETProperty(
            name="Formal Charge",
            value=charge,
            reference_range=self.REFERENCE_RANGES["formal_charge"],
            interpretation=self._interpret_value(charge, "formal_charge"),
        ))
        
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        props.append(ADMETProperty(
            name="Number of Rings",
            value=num_rings,
            reference_range=self.REFERENCE_RANGES["num_rings"],
            interpretation=self._interpret_value(num_rings, "num_rings"),
        ))
        
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        props.append(ADMETProperty(
            name="Aromatic Rings",
            value=arom_rings,
            reference_range=self.REFERENCE_RANGES["aromatic_rings"],
            interpretation=self._interpret_value(arom_rings, "aromatic_rings"),
        ))
        
        qed_val = QED.qed(mol)
        props.append(ADMETProperty(
            name="QED",
            value=round(qed_val, 3),
            reference_range=self.REFERENCE_RANGES["qed"],
            interpretation=self._interpret_value(qed_val, "qed"),
        ))
        
        sa_score = self._calculate_sa_score(mol)
        props.append(ADMETProperty(
            name="Synthetic Accessibility",
            value=round(sa_score, 2),
            reference_range=self.REFERENCE_RANGES["sa_score"],
            interpretation=self._interpret_value(sa_score, "sa_score"),
        ))
        
        fsp3 = rdMolDescriptors.CalcFractionCSP3(mol)
        props.append(ADMETProperty(
            name="Fsp3",
            value=round(fsp3, 3),
            reference_range=self.REFERENCE_RANGES["fsp3"],
            interpretation=self._interpret_value(fsp3, "fsp3"),
        ))
        
        # Lipinski
        lipinski_violations = self._count_lipinski_violations(mol)
        props.append(ADMETProperty(
            name="Lipinski Violations",
            value=lipinski_violations,
            reference_range=self.REFERENCE_RANGES["lipinski_violations"],
            interpretation=self._interpret_value(lipinski_violations, "lipinski_violations"),
        ))
        
        return props
    
    def _predict_absorption(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict absorption properties."""
        props = []
        
        # Caco-2 permeability (rule-based)
        caco2 = self._predict_caco2(mol)
        props.append(ADMETProperty(
            name="Caco-2 Permeability",
            value=round(caco2, 1),
            unit="nm/s",
            reference_range=self.REFERENCE_RANGES["caco2_permeability"],
            interpretation=self._interpret_value(caco2, "caco2_permeability"),
            method="rule_based" if not self.use_ml_models else "ml",
        ))
        
        # Human Intestinal Absorption
        hia = self._predict_hia(mol)
        props.append(ADMETProperty(
            name="Human Intestinal Absorption",
            value=round(hia, 1),
            unit="%",
            reference_range=self.REFERENCE_RANGES["hia"],
            interpretation=self._interpret_value(hia, "hia"),
        ))
        
        # P-gp substrate
        pgp_sub = self._predict_pgp_substrate(mol)
        props.append(ADMETProperty(
            name="P-gp Substrate",
            value=round(pgp_sub, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["pgp_substrate"],
            interpretation=self._interpret_value(pgp_sub, "pgp_substrate"),
        ))
        
        # P-gp inhibitor
        pgp_inh = self._predict_pgp_inhibitor(mol)
        props.append(ADMETProperty(
            name="P-gp Inhibitor",
            value=round(pgp_inh, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["pgp_inhibitor"],
            interpretation=self._interpret_value(pgp_inh, "pgp_inhibitor"),
        ))
        
        # Bioavailability
        bioavail = self._predict_bioavailability(mol)
        props.append(ADMETProperty(
            name="Oral Bioavailability",
            value=round(bioavail, 1),
            unit="%",
            reference_range=self.REFERENCE_RANGES["bioavailability"],
            interpretation=self._interpret_value(bioavail, "bioavailability"),
        ))
        
        return props
    
    def _predict_distribution(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict distribution properties."""
        props = []
        
        # BBB permeability
        bbb = self._predict_bbb(mol)
        props.append(ADMETProperty(
            name="BBB Permeability (logBB)",
            value=round(bbb, 2),
            reference_range=self.REFERENCE_RANGES["bbb_permeability"],
            interpretation=self._interpret_value(bbb, "bbb_permeability"),
            method="rule_based" if not self.use_ml_models else "ml",
        ))
        
        # CNS MPO score
        cns_mpo = self._calculate_cns_mpo(mol)
        props.append(ADMETProperty(
            name="CNS MPO Score",
            value=round(cns_mpo, 2),
            reference_range=self.REFERENCE_RANGES["cns_mpo"],
            interpretation=self._interpret_value(cns_mpo, "cns_mpo"),
        ))
        
        # VDss
        vdss = self._predict_vdss(mol)
        props.append(ADMETProperty(
            name="Volume of Distribution (VDss)",
            value=round(vdss, 2),
            unit="L/kg",
            reference_range=self.REFERENCE_RANGES["vdss"],
            interpretation=self._interpret_value(vdss, "vdss"),
        ))
        
        # Plasma protein binding
        ppb = self._predict_ppb(mol)
        props.append(ADMETProperty(
            name="Plasma Protein Binding",
            value=round(ppb, 1),
            unit="%",
            reference_range=self.REFERENCE_RANGES["plasma_protein_binding"],
            interpretation=self._interpret_value(ppb, "plasma_protein_binding"),
        ))
        
        return props
    
    def _predict_metabolism(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict metabolism properties."""
        props = []
        
        cyp_enzymes = [
            ("CYP1A2", "cyp1a2"),
            ("CYP2C9", "cyp2c9"),
            ("CYP2C19", "cyp2c19"),
            ("CYP2D6", "cyp2d6"),
            ("CYP3A4", "cyp3a4"),
        ]
        
        for name, key in cyp_enzymes:
            # Inhibitor
            inh = self._predict_cyp_inhibitor(mol, key)
            props.append(ADMETProperty(
                name=f"{name} Inhibitor",
                value=round(inh, 3),
                unit="probability",
                reference_range=self.REFERENCE_RANGES[f"{key}_inhibitor"],
                interpretation=self._interpret_value(inh, f"{key}_inhibitor"),
                method="ml" if key in self.models else "rule_based",
            ))
            
            # Substrate
            sub = self._predict_cyp_substrate(mol, key)
            props.append(ADMETProperty(
                name=f"{name} Substrate",
                value=round(sub, 3),
                unit="probability",
                reference_range=self.REFERENCE_RANGES[f"{key}_substrate"],
                interpretation=self._interpret_value(sub, f"{key}_substrate"),
                method="ml" if key in self.models else "rule_based",
            ))
        
        # Clearance
        cl = self._predict_clearance(mol)
        props.append(ADMETProperty(
            name="Total Clearance",
            value=round(cl, 2),
            unit="mL/min/kg",
            reference_range=self.REFERENCE_RANGES["clearance"],
            interpretation=self._interpret_value(cl, "clearance"),
        ))
        
        # Half-life
        hl = self._predict_half_life(mol)
        props.append(ADMETProperty(
            name="Half-Life",
            value=round(hl, 1),
            unit="hours",
            reference_range=self.REFERENCE_RANGES["half_life"],
            interpretation=self._interpret_value(hl, "half_life"),
        ))
        
        return props
    
    def _predict_excretion(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict excretion properties."""
        props = []
        
        renal_cl = self._predict_renal_clearance(mol)
        props.append(ADMETProperty(
            name="Renal Clearance",
            value=round(renal_cl, 1),
            unit="mL/min",
            reference_range=self.REFERENCE_RANGES["renal_clearance"],
            interpretation=self._interpret_value(renal_cl, "renal_clearance"),
        ))
        
        return props
    
    def _predict_toxicity(self, mol: Chem.Mol) -> list[ADMETProperty]:
        """Predict toxicity properties."""
        props = []
        
        # Ames mutagenicity
        ames = self._predict_ames(mol)
        props.append(ADMETProperty(
            name="Ames Mutagenicity",
            value=round(ames, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["ames_mutagenicity"],
            interpretation=self._interpret_value(ames, "ames_mutagenicity"),
            method="ml" if "ames" in self.models else "rule_based",
        ))
        
        # Hepatotoxicity
        hep = self._predict_hepatotoxicity(mol)
        props.append(ADMETProperty(
            name="Hepatotoxicity",
            value=round(hep, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["hepatotoxicity"],
            interpretation=self._interpret_value(hep, "hepatotoxicity"),
            method="ml" if "hepatotoxicity" in self.models else "rule_based",
        ))
        
        # hERG cardiotoxicity
        herg = self._predict_herg(mol)
        props.append(ADMETProperty(
            name="hERG Cardiotoxicity",
            value=round(herg, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["cardiotoxicity_hERG"],
            interpretation=self._interpret_value(herg, "cardiotoxicity_hERG"),
            method="ml" if "hERG" in self.models else "rule_based",
        ))
        
        # Skin sensitization
        skin = self._predict_skin_sensitization(mol)
        props.append(ADMETProperty(
            name="Skin Sensitization",
            value=round(skin, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["skin_sensitization"],
            interpretation=self._interpret_value(skin, "skin_sensitization"),
        ))
        
        # Acute oral toxicity
        ld50_cat = self._predict_ld50_category(mol)
        props.append(ADMETProperty(
            name="Acute Oral Toxicity Category",
            value=ld50_cat,
            unit="GHS category (1-5)",
            reference_range=self.REFERENCE_RANGES["acute_oral_toxicity"],
            interpretation=self._interpret_value(ld50_cat, "acute_oral_toxicity"),
        ))
        
        # Carcinogenicity
        carc = self._predict_carcinogenicity(mol)
        props.append(ADMETProperty(
            name="Carcinogenicity",
            value=round(carc, 3),
            unit="probability",
            reference_range=self.REFERENCE_RANGES["carcinogenicity"],
            interpretation=self._interpret_value(carc, "carcinogenicity"),
        ))
        
        return props
    
    # --- Rule-based prediction methods ---
    
    def _estimate_logd(self, mol: Chem.Mol) -> float:
        """Estimate LogD at pH 7.4."""
        logp = Descriptors.MolLogP(mol)
        
        # Count ionizable groups
        acidic = 0
        basic = 0
        
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 7:  # Nitrogen
                # Check if basic (amine)
                if atom.GetTotalNumHs() > 0 or atom.GetFormalCharge() > 0:
                    basic += 1
            elif atom.GetAtomicNum() == 8:  # Oxygen
                # Check if acidic (carboxylic acid)
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() == 6:  # Carbon
                        # Check for C=O
                        for nnbr in nbr.GetNeighbors():
                            if nnbr.GetAtomicNum() == 8 and nnbr.GetIdx() != atom.GetIdx():
                                acidic += 1
                                break
        
        # Simple Henderson-Hasselbalch approximation
        # At pH 7.4, acids are deprotonated, bases are protonated
        logd = logp - 0.5 * acidic + 0.5 * basic
        
        return logd
    
    def _calculate_sa_score(self, mol: Chem.Mol) -> float:
        """Calculate synthetic accessibility score."""
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_hetero = rdMolDescriptors.CalcNumHeteroatoms(mol)
        num_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
        mw = Descriptors.MolWt(mol)
        
        complexity = num_rings * 0.5 + num_hetero * 0.1 + num_chiral * 0.3 + mw * 0.001
        return min(1.0 + complexity, 10.0)
    
    def _count_lipinski_violations(self, mol: Chem.Mol) -> int:
        """Count Lipinski violations."""
        violations = 0
        if Descriptors.MolWt(mol) > 500: violations += 1
        if Descriptors.MolLogP(mol) > 5: violations += 1
        if Descriptors.NumHDonors(mol) > 5: violations += 1
        if Descriptors.NumHAcceptors(mol) > 10: violations += 1
        return violations
    
    def _predict_caco2(self, mol: Chem.Mol) -> float:
        """Predict Caco-2 permeability (nm/s)."""
        # Rule-based: based on MW, LogP, TPSA, HBD
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        hbd = Descriptors.NumHDonors(mol)
        
        # Empirical formula
        score = 100.0
        if mw > 500: score -= 30
        if logp < 0 or logp > 5: score -= 20
        if tpsa > 140: score -= 30
        if hbd > 5: score -= 20
        
        return max(0, score)
    
    def _predict_hia(self, mol: Chem.Mol) -> float:
        """Predict Human Intestinal Absorption (%)."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        
        # Simple rules
        score = 100.0
        if mw > 500: score -= 20
        if logp < -1 or logp > 5: score -= 15
        if tpsa > 140: score -= 30
        
        return max(0, min(100, score))
    
    def _predict_pgp_substrate(self, mol: Chem.Mol) -> float:
        """Predict P-gp substrate probability."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        
        # P-gp substrates tend to be larger, more lipophilic
        prob = 0.1
        if mw > 400: prob += 0.2
        if logp > 3: prob += 0.2
        if tpsa > 80: prob += 0.1
        
        return min(1.0, prob)
    
    def _predict_pgp_inhibitor(self, mol: Chem.Mol) -> float:
        """Predict P-gp inhibitor probability."""
        # Similar to substrate but different rules
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        
        prob = 0.05
        if mw > 350: prob += 0.15
        if logp > 4: prob += 0.2
        if arom_rings >= 3: prob += 0.15
        
        return min(1.0, prob)
    
    def _predict_bioavailability(self, mol: Chem.Mol) -> float:
        """Predict oral bioavailability."""
        # Based on Lipinski + Veber
        lip_violations = self._count_lipinski_violations(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        
        score = 100.0
        score -= lip_violations * 15
        if tpsa > 140: score -= 20
        if rot_bonds > 10: score -= 15
        
        return max(0, min(100, score))
    
    def _predict_bbb(self, mol: Chem.Mol) -> float:
        """Predict BBB permeability (logBB)."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        charge = Chem.GetFormalCharge(mol)
        hbd = Descriptors.NumHDonors(mol)
        
        # logBB = 0.15 - 0.014*TPSA + 0.152*logP - 0.011*MW + ...
        logbb = 0.15 - 0.014 * tpsa + 0.152 * logp - 0.011 * mw
        logbb -= 0.1 * abs(charge)
        logbb -= 0.05 * hbd
        
        return logbb
    
    def _calculate_cns_mpo(self, mol: Chem.Mol) -> float:
        """Calculate CNS MPO score (0-6)."""
        # 6 parameters: MW, logP, TPSA, HBD, pKa, logD
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        hbd = Descriptors.NumHDonors(mol)
        logd = self._estimate_logd(mol)
        
        # Desirability functions
        def desirability(val, low, high, target_low, target_high):
            if val < low or val > high:
                return 0.0
            if target_low <= val <= target_high:
                return 1.0
            # Linear interpolation
            if val < target_low:
                return (val - low) / (target_low - low)
            return (high - val) / (high - target_high)
        
        d1 = desirability(mw, 200, 500, 300, 400)
        d2 = desirability(logp, 0, 5, 2, 3.5)
        d3 = desirability(tpsa, 20, 120, 40, 90)
        d4 = desirability(hbd, 0, 5, 0, 3)
        d5 = desirability(logd, -1, 4, 1, 3)
        
        # pKa desirability (simplified)
        d6 = 0.5  # placeholder
        
        return (d1 + d2 + d3 + d4 + d5 + d6) * 6 / 5  # Normalize to 6
    
    def _predict_vdss(self, mol: Chem.Mol) -> float:
        """Predict volume of distribution at steady state."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        charge = abs(Chem.GetFormalCharge(mol))
        
        # Simple empirical
        vdss = 0.1 * mw + 0.5 * logp + 0.02 * tpsa + 0.5 * charge
        
        return max(0.1, min(20, vdss))
    
    def _predict_ppb(self, mol: Chem.Mol) -> float:
        """Predict plasma protein binding."""
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        
        # Higher logP and aromaticity = higher binding
        ppb = 50 + 8 * logp - 0.2 * tpsa + 3 * arom_rings
        
        return max(0, min(100, ppb))
    
    def _predict_cyp_inhibitor(self, mol: Chem.Mol, cyp: str) -> float:
        """Predict CYP inhibitor probability."""
        # Simplified: use general features
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        num_n = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 7)
        num_o = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 8)
        
        # CYP inhibitors often have: aromatic rings, N/O heteroatoms, moderate MW
        prob = 0.1
        if 250 < mw < 550: prob += 0.15
        if 2 < logp < 5: prob += 0.15
        if arom_rings >= 2: prob += 0.1
        if num_n >= 1: prob += 0.1
        if num_o >= 2: prob += 0.05
        
        # CYP-specific adjustments
        if cyp == "cyp3a4" and mw > 400:
            prob += 0.1
        elif cyp == "cyp2d6" and num_n >= 1:
            prob += 0.1
        
        return min(1.0, prob)
    
    def _predict_cyp_substrate(self, mol: Chem.Mol, cyp: str) -> float:
        """Predict CYP substrate probability."""
        # Similar to inhibitor but slightly different rules
        return self._predict_cyp_inhibitor(mol, cyp) * 0.8
    
    def _predict_clearance(self, mol: Chem.Mol) -> float:
        """Predict total clearance."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        
        # High clearance: low MW, high logP, low TPSA
        cl = 10 + 0.05 * mw + 2 * logp - 0.1 * tpsa
        
        return max(1, min(100, cl))
    
    def _predict_half_life(self, mol: Chem.Mol) -> float:
        """Predict half-life."""
        cl = self._predict_clearance(mol)
        vdss = self._predict_vdss(mol)
        
        # t1/2 = 0.693 * Vd / CL
        hl = 0.693 * vdss / max(cl, 0.1)
        
        return max(0.1, min(100, hl))
    
    def _predict_renal_clearance(self, mol: Chem.Mol) -> float:
        """Predict renal clearance."""
        mw = Descriptors.MolWt(mol)
        charge = Chem.GetFormalCharge(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        
        # Renal clearance: lower MW, charged, polar
        if mw > 500:
            return 0.0
        
        rc = 120 * (1 - mw / 500) + 10 * abs(charge) - 0.1 * tpsa
        
        return max(0, min(500, rc))
    
    def _predict_ames(self, mol: Chem.Mol) -> float:
        """Predict Ames mutagenicity."""
        # Check for structural alerts
        alerts = 0
        
        # Aromatic amines
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[NH2]c1ccccc1")):
            alerts += 1
        
        # Nitro aromatics
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[N+](=O)[O-]c")):
            alerts += 1
        
        # Azo compounds
        if mol.HasSubstructMatch(Chem.MolFromSmarts("N=Nc")):
            alerts += 1
        
        # Heterocyclic amines
        if mol.HasSubstructMatch(Chem.MolFromSmarts("n1ccccc1[N]")):
            alerts += 1
        
        prob = min(0.9, alerts * 0.25)
        
        # If ML model available
        if "ames" in self.models:
            try:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
                prob = self.models["ames"].predict_proba([fp])[0][1]
            except Exception:
                pass
        
        return prob
    
    def _predict_hepatotoxicity(self, mol: Chem.Mol) -> float:
        """Predict hepatotoxicity."""
        alerts = 0
        
        # Anilines
        if mol.HasSubstructMatch(Chem.MolFromSmarts("Nc1ccccc1")):
            alerts += 1
        
        # Quinones
        if mol.HasSubstructMatch(Chem.MolFromSmarts("O=c1ccccc1=O")):
            alerts += 1
        
        # Halogenated aromatics
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[Cl,Br,I]c")):
            alerts += 1
        
        prob = min(0.8, alerts * 0.2)
        
        if "hepatotoxicity" in self.models:
            try:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
                prob = self.models["hepatotoxicity"].predict_proba([fp])[0][1]
            except Exception:
                pass
        
        return prob
    
    def _predict_herg(self, mol: Chem.Mol) -> float:
        """Predict hERG cardiotoxicity."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        num_n = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 7)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        
        # hERG blockers: basic amines, lipophilic, aromatic
        prob = 0.05
        if mw > 300: prob += 0.1
        if logp > 3: prob += 0.15
        if num_n >= 1: prob += 0.15
        if arom_rings >= 2: prob += 0.1
        
        if "hERG" in self.models:
            try:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
                prob = self.models["hERG"].predict_proba([fp])[0][1]
            except Exception:
                pass
        
        return min(1.0, prob)
    
    def _predict_skin_sensitization(self, mol: Chem.Mol) -> float:
        """Predict skin sensitization."""
        # Michael acceptors, SN2 electrophiles
        alerts = 0
        
        # Alpha,beta-unsaturated carbonyl
        if mol.HasSubstructMatch(Chem.MolFromSmarts("C=CC(=O)")):
            alerts += 1
        
        # Epoxides
        if mol.HasSubstructMatch(Chem.MolFromSmarts("C1OC1")):
            alerts += 1
        
        # Alkyl halides
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[Cl,Br,I][CH2]")):
            alerts += 1
        
        return min(0.8, alerts * 0.25)
    
    def _predict_ld50_category(self, mol: Chem.Mol) -> int:
        """Predict GHS acute oral toxicity category (1-5)."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        
        # Very rough estimation
        if mw < 200 and logp < 0:
            return 5  # Low toxicity
        elif mw < 300 and logp < 2:
            return 4
        elif mw < 400 and logp < 4:
            return 3
        elif mw < 500:
            return 2
        else:
            return 1  # High toxicity
    
    def _predict_carcinogenicity(self, mol: Chem.Mol) -> float:
        """Predict carcinogenicity."""
        alerts = 0
        
        # Aromatic amines
        if mol.HasSubstructMatch(Chem.MolFromSmarts("Nc1ccccc1")):
            alerts += 1
        
        # Nitro aromatics
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[N+](=O)[O-]c")):
            alerts += 1
        
        # Aflatoxin-like
        if mol.HasSubstructMatch(Chem.MolFromSmarts("O=c1oc2ccccc2c1")):
            alerts += 1
        
        return min(0.7, alerts * 0.2)
    
    # --- Interpretation helpers ---
    
    def _interpret_value(self, value: float, key: str) -> str:
        """Interpret a value based on reference range."""
        if key not in self.REFERENCE_RANGES:
            return "neutral"
        
        low, high = self.REFERENCE_RANGES[key]
        
        # For properties where higher is better
        higher_better = key in ["caco2_permeability", "hia", "bioavailability", 
                                "bbb_permeability", "cns_mpo", "qed", "fsp3",
                                "logp", "logd"]
        
        # For properties where lower is better
        lower_better = key in ["lipinski_violations", "ghose_violations", "veber_violations",
                               "pgp_substrate", "pgp_inhibitor", "vdss", "plasma_protein_binding",
                               "clearance", "half_life", "renal_clearance",
                               "ames_mutagenicity", "hepatotoxicity", "skin_sensitization",
                               "cardiotoxicity_hERG", "acute_oral_toxicity", "carcinogenicity",
                               "sa_score", "tpsa", "rotatable_bonds", "hbd", "hba",
                               "formal_charge", "num_rings", "aromatic_rings",
                               "molecular_weight"]
        
        if value < low:
            return "favorable" if lower_better else "unfavorable"
        elif value > high:
            return "unfavorable" if lower_better else "favorable"
        else:
            return "favorable"  # Within range
    
    def _calculate_overall_score(self, result: ADMETResult) -> float:
        """Calculate overall ADMET score (0-1)."""
        if not result.properties:
            return 0.0
        
        score = 0.0
        weight_sum = 0.0
        
        # Weights for different categories
        weights = {
            "absorption": 0.25,
            "distribution": 0.15,
            "metabolism": 0.20,
            "excretion": 0.10,
            "toxicity": 0.30,
        }
        
        # Categorize properties
        absorption_props = ["caco2", "hia", "pgp", "bioavailability", "lipinski"]
        distribution_props = ["bbb", "cns_mpo", "vdss", "plasma_protein"]
        metabolism_props = ["cyp", "clearance", "half_life"]
        excretion_props = ["renal_clearance"]
        toxicity_props = ["ames", "hepatotox", "herg", "skin", "ld50", "carcinogen"]
        
        for prop in result.properties:
            name_lower = prop.name.lower()
            w = 1.0
            cat = "other"
            
            if any(k in name_lower for k in absorption_props):
                cat = "absorption"
                w = weights["absorption"]
            elif any(k in name_lower for k in distribution_props):
                cat = "distribution"
                w = weights["distribution"]
            elif any(k in name_lower for k in metabolism_props):
                cat = "metabolism"
                w = weights["metabolism"]
            elif any(k in name_lower for k in excretion_props):
                cat = "excretion"
                w = weights["excretion"]
            elif any(k in name_lower for k in toxicity_props):
                cat = "toxicity"
                w = weights["toxicity"]
            
            # Convert interpretation to score
            if prop.interpretation == "favorable":
                prop_score = 1.0
            elif prop.interpretation == "unfavorable":
                prop_score = 0.0
            else:
                prop_score = 0.5
            
            score += prop_score * w * prop.confidence
            weight_sum += w * prop.confidence
        
        return round(score / weight_sum if weight_sum > 0 else 0.0, 3)
    
    def _determine_risk_level(self, result: ADMETResult) -> str:
        """Determine overall risk level."""
        if result.overall_score >= 0.7:
            return "low"
        elif result.overall_score >= 0.4:
            return "moderate"
        elif result.overall_score >= 0.2:
            return "high"
        else:
            return "very_high"
    
    def _generate_flags(self, result: ADMETResult) -> list[str]:
        """Generate warning flags."""
        flags = []
        
        for prop in result.properties:
            if prop.interpretation == "unfavorable":
                flags.append(f"{prop.name}: {prop.value} {prop.unit} (unfavorable)")
        
        # Specific critical flags
        ames = result.get_property("Ames Mutagenicity")
        if ames and ames.value > 0.5:
            flags.append("⚠️ HIGH: Potential mutagenicity (Ames positive)")
        
        herg = result.get_property("hERG Cardiotoxicity")
        if herg and herg.value > 0.5:
            flags.append("⚠️ HIGH: Potential cardiotoxicity (hERG blockade)")
        
        hep = result.get_property("Hepatotoxicity")
        if hep and hep.value > 0.5:
            flags.append("⚠️ HIGH: Potential hepatotoxicity")
        
        lip = result.get_property("Lipinski Violations")
        if lip and lip.value > 2:
            flags.append(f"⚠️ {lip.value} Lipinski violations")
        
        return flags
    
    def _generate_recommendations(self, result: ADMETResult) -> list[str]:
        """Generate optimization recommendations."""
        recs = []
        
        mw = result.get_property("Molecular Weight")
        if mw and mw.value > 500:
            recs.append("Reduce molecular weight below 500 Da")
        
        logp = result.get_property("LogP")
        if logp and (logp.value > 5 or logp.value < 0):
            recs.append("Optimize LogP to 0-5 range")
        
        tpsa = result.get_property("TPSA")
        if tpsa and tpsa.value > 140:
            recs.append("Reduce TPSA below 140 Å² for better permeability")
        
        rot = result.get_property("Rotatable Bonds")
        if rot and rot.value > 10:
            recs.append("Reduce rotatable bonds to ≤10 for better oral bioavailability")
        
        pgp_sub = result.get_property("P-gp Substrate")
        if pgp_sub and pgp_sub.value > 0.5:
            recs.append("Consider structural modifications to reduce P-gp efflux")
        
        herg = result.get_property("hERG Cardiotoxicity")
        if herg and herg.value > 0.3:
            recs.append("Reduce basic amine character to mitigate hERG risk")
        
        ames = result.get_property("Ames Mutagenicity")
        if ames and ames.value > 0.3:
            recs.append("Avoid aromatic amines and nitroaromatics to reduce mutagenicity risk")
        
        if not recs:
            recs.append("ADMET profile appears favorable for drug development")
        
        return recs
    
    def batch_predict(self, smiles_list: list[str]) -> list[ADMETResult]:
        """Predict ADMET for multiple molecules."""
        return [self.predict(smi) for smi in smiles_list]
    
    def filter_by_admet(
        self,
        smiles_list: list[str],
        max_risk: str = "moderate",
        required_properties: dict[str, tuple] | None = None,
    ) -> list[tuple[str, ADMETResult]]:
        """Filter molecules by ADMET criteria."""
        risk_order = {"low": 0, "moderate": 1, "high": 2, "very_high": 3, "unknown": 4}
        max_risk_level = risk_order.get(max_risk, 1)
        
        results = self.batch_predict(smiles_list)
        
        filtered = []
        for smi, result in zip(smiles_list, results):
            if risk_order.get(result.risk_level, 4) <= max_risk_level:
                if required_properties:
                    passes = True
                    for prop_name, (min_val, max_val) in required_properties.items():
                        prop = result.get_property(prop_name)
                        if prop and not (min_val <= prop.value <= max_val):
                            passes = False
                            break
                    if not passes:
                        continue
                filtered.append((smi, result))
        
        return filtered


def predict_admet(smiles: str, **kwargs) -> ADMETResult:
    """Convenience function for ADMET prediction."""
    predictor = ADMETPredictor(**kwargs)
    return predictor.predict(smiles)