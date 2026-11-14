"""Property prediction for optimization using ensemble models."""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, AllChem, QED

logger = logging.getLogger(__name__)


@dataclass
class PropertyPrediction:
    """Single property prediction with uncertainty."""
    name: str
    value: float
    uncertainty: float = 0.0  # Standard deviation
    model: str = "rule_based"
    confidence: float = 1.0


class PropertyPredictor:
    """
    Predict molecular properties for optimization.
    
    Supports:
    - Rule-based (RDKit descriptors)
    - ML models (if trained models available)
    - Ensemble predictions with uncertainty
    """
    
    def __init__(
        self,
        use_ml_models: bool = False,
        model_dir: str | None = None,
    ):
        self.use_ml_models = use_ml_models
        self.model_dir = Path(model_dir) if model_dir else None
        self.models: dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        
        if use_ml_models and model_dir:
            self._load_models()
    
    def _load_models(self):
        """Load trained ML models."""
        if not self.model_dir or not self.model_dir.exists():
            self.logger.warning("Model directory not found: %s", self.model_dir)
            return
        
        model_files = {
            "caco2": "caco2_model.pkl",
            "bbb": "bbb_model.pkl",
            "cyp3a4": "cyp3a4_model.pkl",
            "cyp2d6": "cyp2d6_model.pkl",
            "herg": "herg_model.pkl",
            "ames": "ames_model.pkl",
            "hepatotoxicity": "hepatotox_model.pkl",
            "clearance": "clearance_model.pkl",
            "solubility": "solubility_model.pkl",
            "binding_affinity": "affinity_model.pkl",
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
    
    def predict_all(self, smiles: str) -> dict[str, PropertyPrediction]:
        """Predict all properties for a molecule."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return {}
        
        predictions = {}
        
        # Rule-based predictions (always available)
        predictions.update(self._predict_rule_based(mol))
        
        # ML predictions (if available)
        if self.use_ml_models:
            predictions.update(self._predict_ml(mol))
        
        return predictions
    
    def _predict_rule_based(self, mol: Chem.Mol) -> dict[str, PropertyPrediction]:
        """Predict using RDKit descriptors and rules."""
        preds = {}
        
        # Physicochemical
        mw = Descriptors.MolWt(mol)
        preds["mw"] = PropertyPrediction("mw", mw, model="rdkit")
        
        logp = Descriptors.MolLogP(mol)
        preds["logp"] = PropertyPrediction("logp", logp, model="rdkit")
        
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        preds["tpsa"] = PropertyPrediction("tpsa", tpsa, model="rdkit")
        
        hbd = Descriptors.NumHDonors(mol)
        preds["hbd"] = PropertyPrediction("hbd", float(hbd), model="rdkit")
        
        hba = Descriptors.NumHAcceptors(mol)
        preds["hba"] = PropertyPrediction("hba", float(hba), model="rdkit")
        
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        preds["rotatable_bonds"] = PropertyPrediction("rotatable_bonds", float(rot_bonds), model="rdkit")
        
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        preds["aromatic_rings"] = PropertyPrediction("aromatic_rings", float(arom_rings), model="rdkit")
        
        charge = Chem.GetFormalCharge(mol)
        preds["formal_charge"] = PropertyPrediction("formal_charge", float(charge), model="rdkit")
        
        fsp3 = rdMolDescriptors.CalcFractionCSP3(mol)
        preds["fsp3"] = PropertyPrediction("fsp3", fsp3, model="rdkit")
        
        # QED
        qed_val = QED.qed(mol)
        preds["qed"] = PropertyPrediction("qed", qed_val, model="rdkit")
        
        # SA Score (simplified)
        sa_score = self._calc_sa_score(mol)
        preds["sa_score"] = PropertyPrediction("sa_score", sa_score, model="rdkit")
        
        # Lipinski
        lip_violations = self._count_lipinski_violations(mol)
        preds["lipinski_violations"] = PropertyPrediction("lipinski_violations", float(lip_violations), model="rdkit")
        
        # ADMET approximations
        preds.update(self._predict_admet_approx(mol))
        
        return preds
    
    def _calc_sa_score(self, mol: Chem.Mol) -> float:
        """Calculate synthetic accessibility score."""
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_hetero = rdMolDescriptors.CalcNumHeteroatoms(mol)
        num_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
        mw = Descriptors.MolWt(mol)
        
        complexity = num_rings * 0.5 + num_hetero * 0.1 + num_chiral * 0.3 + mw * 0.001
        return min(1.0 + complexity, 10.0)
    
    def _count_lipinski_violations(self, mol: Chem.Mol) -> int:
        violations = 0
        if Descriptors.MolWt(mol) > 500: violations += 1
        if Descriptors.MolLogP(mol) > 5: violations += 1
        if Descriptors.NumHDonors(mol) > 5: violations += 1
        if Descriptors.NumHAcceptors(mol) > 10: violations += 1
        return violations
    
    def _predict_admet_approx(self, mol: Chem.Mol) -> dict[str, PropertyPrediction]:
        """Approximate ADMET predictions using rules."""
        preds = {}
        
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        num_n = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 7)
        num_o = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 8)
        
        # Caco-2 permeability
        caco2 = 100.0
        if mw > 500: caco2 -= 30
        if logp < 0 or logp > 5: caco2 -= 20
        if tpsa > 140: caco2 -= 30
        if hbd > 5: caco2 -= 20
        preds["caco2"] = PropertyPrediction("caco2", max(0, caco2), model="rule_based")
        
        # HIA
        hia = 100.0
        if mw > 500: hia -= 20
        if logp < -1 or logp > 5: hia -= 15
        if tpsa > 140: hia -= 30
        preds["hia"] = PropertyPrediction("hia", max(0, min(100, hia)), model="rule_based")
        
        # BBB
        bbb = 0.15 - 0.014 * tpsa + 0.152 * logp - 0.011 * mw
        bbb -= 0.1 * abs(Chem.GetFormalCharge(mol))
        bbb -= 0.05 * hbd
        preds["bbb"] = PropertyPrediction("bbb", bbb, model="rule_based")
        
        # CNS MPO
        cns_mpo = self._calc_cns_mpo(mol)
        preds["cns_mpo"] = PropertyPrediction("cns_mpo", cns_mpo, model="rule_based")
        
        # CYP inhibition (simplified)
        cyp_prob = 0.1
        if 250 < mw < 550: cyp_prob += 0.15
        if 2 < logp < 5: cyp_prob += 0.15
        if arom_rings >= 2: cyp_prob += 0.1
        if num_n >= 1: cyp_prob += 0.1
        if num_o >= 2: cyp_prob += 0.05
        
        preds["cyp3a4_inhibitor"] = PropertyPrediction("cyp3a4_inhibitor", min(1.0, cyp_prob + (0.1 if mw > 400 else 0)), model="rule_based")
        preds["cyp2d6_inhibitor"] = PropertyPrediction("cyp2d6_inhibitor", min(1.0, cyp_prob + (0.1 if num_n >= 1 else 0)), model="rule_based")
        preds["cyp2c9_inhibitor"] = PropertyPrediction("cyp2c9_inhibitor", min(1.0, cyp_prob), model="rule_based")
        preds["cyp2c19_inhibitor"] = PropertyPrediction("cyp2c19_inhibitor", min(1.0, cyp_prob), model="rule_based")
        preds["cyp1a2_inhibitor"] = PropertyPrediction("cyp1a2_inhibitor", min(1.0, cyp_prob), model="rule_based")
        
        # hERG
        herg_prob = 0.05
        if mw > 300: herg_prob += 0.1
        if logp > 3: herg_prob += 0.15
        if num_n >= 1: herg_prob += 0.15
        if arom_rings >= 2: herg_prob += 0.1
        preds["herg"] = PropertyPrediction("herg", min(1.0, herg_prob), model="rule_based")
        
        # Ames
        ames_prob = 0.0
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[NH2]c1ccccc1")):
            ames_prob += 0.25
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[N+](=O)[O-]c")):
            ames_prob += 0.25
        if mol.HasSubstructMatch(Chem.MolFromSmarts("N=Nc")):
            ames_prob += 0.25
        preds["ames"] = PropertyPrediction("ames", min(0.9, ames_prob), model="rule_based")
        
        # Hepatotoxicity
        hep_prob = 0.0
        if mol.HasSubstructMatch(Chem.MolFromSmarts("Nc1ccccc1")):
            hep_prob += 0.2
        if mol.HasSubstructMatch(Chem.MolFromSmarts("O=c1ccccc1=O")):
            hep_prob += 0.2
        if mol.HasSubstructMatch(Chem.MolFromSmarts("[Cl,Br,I]c")):
            hep_prob += 0.15
        preds["hepatotoxicity"] = PropertyPrediction("hepatotoxicity", min(0.8, hep_prob), model="rule_based")
        
        # Clearance (simplified)
        cl = 10 + 0.05 * mw + 2 * logp - 0.1 * tpsa
        preds["clearance"] = PropertyPrediction("clearance", max(1, min(100, cl)), model="rule_based")
        
        # Solubility (logS approximation)
        logs = -0.5 * logp - 0.01 * mw + 0.5
        preds["solubility"] = PropertyPrediction("solubility", logs, model="rule_based")
        
        return preds
    
    def _calc_cns_mpo(self, mol: Chem.Mol) -> float:
        """Calculate CNS MPO score."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        hbd = Descriptors.NumHDonors(mol)
        
        def desirability(val, low, high, target_low, target_high):
            if val < low or val > high:
                return 0.0
            if target_low <= val <= target_high:
                return 1.0
            if val < target_low:
                return (val - low) / (target_low - low)
            return (high - val) / (high - target_high)
        
        d1 = desirability(mw, 200, 500, 300, 400)
        d2 = desirability(logp, 0, 5, 2, 3.5)
        d3 = desirability(tpsa, 20, 120, 40, 90)
        d4 = desirability(hbd, 0, 5, 0, 3)
        
        return (d1 + d2 + d3 + d4) * 6 / 4
    
    def _predict_ml(self, mol: Chem.Mol) -> dict[str, PropertyPrediction]:
        """Predict using ML models."""
        preds = {}
        
        # Generate fingerprint
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        fp_array = np.array(fp)
        
        for name, model in self.models.items():
            try:
                if hasattr(model, "predict_proba"):
                    prob = model.predict_proba([fp_array])[0][1]
                    preds[name] = PropertyPrediction(name, prob, model="ml", confidence=0.8)
                elif hasattr(model, "predict"):
                    pred = model.predict([fp_array])[0]
                    preds[name] = PropertyPrediction(name, float(pred), model="ml", confidence=0.7)
            except Exception as e:
                self.logger.warning("ML prediction failed for %s: %s", name, e)
        
        return preds
    
    def predict_batch(self, smiles_list: list[str]) -> list[dict[str, PropertyPrediction]]:
        """Predict for multiple molecules."""
        return [self.predict_all(smi) for smi in smiles_list]


class EnsemblePredictor:
    """Ensemble of multiple predictors for uncertainty estimation."""
    
    def __init__(self, predictors: list[PropertyPredictor]):
        self.predictors = predictors
        self.logger = logging.getLogger(__name__)
    
    def predict(self, smiles: str) -> dict[str, PropertyPrediction]:
        """Predict with ensemble, returning mean and std."""
        all_preds = []
        
        for predictor in self.predictors:
            preds = predictor.predict_all(smiles)
            all_preds.append(preds)
        
        # Aggregate
        ensemble_preds = {}
        property_names = set()
        for preds in all_preds:
            property_names.update(preds.keys())
        
        for prop_name in property_names:
            values = []
            for preds in all_preds:
                if prop_name in preds:
                    values.append(preds[prop_name].value)
            
            if values:
                ensemble_preds[prop_name] = PropertyPrediction(
                    name=prop_name,
                    value=np.mean(values),
                    uncertainty=np.std(values) if len(values) > 1 else 0.0,
                    model="ensemble",
                    confidence=1.0 - min(np.std(values) / (abs(np.mean(values)) + 1e-6), 1.0) if len(values) > 1 else 1.0,
                )
        
        return ensemble_preds


def create_property_predictor(**kwargs) -> PropertyPredictor:
    """Create property predictor."""
    return PropertyPredictor(**kwargs)