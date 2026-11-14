"""ADMET Prediction Engine - Module 2: Core ADMET prediction pipelines."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geneai.admet_prediction.molecular_properties import (
    calculate_molecular_properties,
    is_rdkit_available,
)
from geneai.admet_prediction.ml_models import ADMETModelManager

logger = logging.getLogger(__name__)

# ADMET Categories
ADMET_CATEGORIES = [
    "absorption",
    "distribution",
    "metabolism",
    "excretion",
    "toxicity",
]

# Default prediction thresholds
DEFAULT_THRESHOLDS = {
    "absorption": {
        "water_solubility": -4.0,  # logS
        "hia": 0.5,
        "caco2": 0.5,
        "bioavailability": 0.5,
    },
    "distribution": {
        "bbb_penetration": 0.5,
        "ppb": 0.9,
        "vdss": 0.5,
    },
    "metabolism": {
        "cyp1a2_inhibitor": 0.5,
        "cyp2c9_inhibitor": 0.5,
        "cyp2c19_inhibitor": 0.5,
        "cyp2d6_inhibitor": 0.5,
        "cyp3a4_inhibitor": 0.5,
        "cyp1a2_substrate": 0.5,
        "cyp2c9_substrate": 0.5,
        "cyp2c19_substrate": 0.5,
        "cyp2d6_substrate": 0.5,
        "cyp3a4_substrate": 0.5,
        "metabolic_stability": 0.5,
    },
    "excretion": {
        "total_clearance": 0.5,
        "renal_clearance": 0.5,
    },
    "toxicity": {
        "hepatotoxicity": 0.5,
        "cardiotoxicity": 0.5,
        "ames_mutagenicity": 0.5,
        "general_toxicity": 0.5,
    },
}


@dataclass
class ADMETPrediction:
    """Single ADMET prediction result."""
    endpoint: str
    category: str
    value: float | None
    probability: float | None
    prediction: str | None
    confidence: str
    method: str = "rule_based"
    is_measured: bool = False
    source: str = "computational"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.details and isinstance(self.details.get("method"), str):
            self.method = self.details["method"]


@dataclass
class ADMETResult:
    """Complete ADMET prediction result for a compound."""
    smiles: str
    molecular_properties: dict[str, Any]
    predictions: list[ADMETPrediction] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    model_info: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ADMETPredictionEngine:
    """Main ADMET prediction engine."""
    
    def __init__(
        self,
        use_ml_models: bool = True,
        confidence_threshold: float = 0.5,
    ):
        """Initialize the ADMET prediction engine.
        
        Args:
            use_ml_models: Whether to use ML models (if available)
            confidence_threshold: Minimum probability for positive prediction
        """
        self.use_ml_models = use_ml_models
        self.confidence_threshold = confidence_threshold
        self.model_manager = None
        
        if use_ml_models:
            try:
                self.model_manager = ADMETModelManager()
            except Exception as e:
                logger.warning("ML models not available: %s", e)
                self.use_ml_models = False
    
    def predict(self, smiles: str) -> ADMETResult:
        """Run complete ADMET prediction for a SMILES string.
        
        Args:
            smiles: SMILES string of the compound
            
        Returns:
            ADMETResult with all predictions
        """
        # Calculate molecular properties
        mol_props = calculate_molecular_properties(smiles)
        
        if "error" in mol_props:
            return ADMETResult(
                smiles=smiles,
                molecular_properties={},
                warnings=[mol_props["error"]],
            )
        
        # Check drug-likeness
        from geneai.admet_prediction.molecular_properties import assess_drug_likeness
        drug_likeness = assess_drug_likeness(mol_props)
        
        # Run predictions for each category
        predictions = []
        
        # Absorption
        predictions.extend(self._predict_absorption(smiles, mol_props))
        
        # Distribution
        predictions.extend(self._predict_distribution(smiles, mol_props))
        
        # Metabolism
        predictions.extend(self._predict_metabolism(smiles, mol_props))
        
        # Excretion
        predictions.extend(self._predict_excretion(smiles, mol_props))
        
        # Toxicity
        predictions.extend(self._predict_toxicity(smiles, mol_props))
        
        # Generate summary
        summary = self._generate_summary(predictions, drug_likeness)
        
        # Model info
        model_info = {
            "used_ml_models": self.use_ml_models,
            "model_version": "1.0",
            "prediction_count": len(predictions),
        }
        
        return ADMETResult(
            smiles=smiles,
            molecular_properties=mol_props,
            predictions=predictions,
            summary=summary,
            model_info=model_info,
        )
    
    def _predict_absorption(self, smiles: str, mol_props: dict) -> list[ADMETPrediction]:
        """Predict absorption properties."""
        predictions = []
        
        # Water solubility (logS) - using ESOL-like estimation
        logp = mol_props.get("logp", 0)
        mw = mol_props.get("molecular_weight", 0)
        tpsa = mol_props.get("tpsa", 0)
        
        # Simplified ESOL equation
        logS = 0.16 - 0.63 * logp - 0.0062 * mw + 0.066 * tpsa
        logS = round(logS, 2)
        
        predictions.append(ADMETPrediction(
            endpoint="water_solubility",
            category="absorption",
            value=logS,
            probability=None,
            prediction="High" if logS > -4 else "Low",
            confidence="medium",
            details={"method": "ESOL-like estimation", "logS": logS},
        ))
        
        # Human Intestinal Absorption (HIA)
        hia_prob = self._estimate_hia(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="human_intestinal_absorption",
            category="absorption",
            value=None,
            probability=hia_prob,
            prediction="High" if hia_prob > self.confidence_threshold else "Low",
            confidence="high" if abs(hia_prob - 0.5) > 0.3 else "medium",
            details={"method": "Rule-based + ML"},
        ))
        
        # Caco-2 Permeability
        caco2_prob = self._estimate_caco2(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="caco2_permeability",
            category="absorption",
            value=None,
            probability=caco2_prob,
            prediction="High" if caco2_prob > self.confidence_threshold else "Low",
            confidence="high" if abs(caco2_prob - 0.5) > 0.3 else "medium",
            details={"method": "Rule-based + ML"},
        ))
        
        # Bioavailability
        f_prob = self._estimate_bioavailability(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="oral_bioavailability",
            category="absorption",
            value=None,
            probability=f_prob,
            prediction="High" if f_prob > self.confidence_threshold else "Low",
            confidence="medium",
            details={"method": "Rule-based + ML"},
        ))
        
        return predictions
    
    def _predict_distribution(self, smiles: str, mol_props: dict) -> list[ADMETPrediction]:
        """Predict distribution properties."""
        predictions = []
        
        # BBB Penetration
        bbb_prob = self._estimate_bbb(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="bbb_penetration",
            category="distribution",
            value=None,
            probability=bbb_prob,
            prediction="Penetrant" if bbb_prob > self.confidence_threshold else "Non-penetrant",
            confidence="high" if abs(bbb_prob - 0.5) > 0.3 else "medium",
            details={"method": "Rule-based + ML"},
        ))
        
        # Plasma Protein Binding
        ppb_prob = self._estimate_ppb(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="plasma_protein_binding",
            category="distribution",
            value=None,
            probability=ppb_prob,
            prediction="High (>90%)" if ppb_prob > 0.9 else "Moderate" if ppb_prob > 0.5 else "Low",
            confidence="medium",
            details={"method": "Rule-based estimation"},
        ))
        
        # Volume of Distribution
        vdss_prob = self._estimate_vdss(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="volume_of_distribution",
            category="distribution",
            value=None,
            probability=vdss_prob,
            prediction="High" if vdss_prob > self.confidence_threshold else "Low",
            confidence="low",
            details={"method": "Simplified estimation"},
        ))
        
        return predictions
    
    def _predict_metabolism(self, smiles: str, mol_props: dict) -> list[ADMETPrediction]:
        """Predict metabolism properties (CYP interactions)."""
        predictions = []
        
        # CYP inhibition predictions
        cyp_enzymes = ["cyp1a2", "cyp2c9", "cyp2c19", "cyp2d6", "cyp3a4"]
        
        for cyp in cyp_enzymes:
            # Inhibitor prediction
            inh_prob = self._estimate_cyp_inhibition(cyp, mol_props)
            predictions.append(ADMETPrediction(
                endpoint=f"{cyp}_inhibitor",
                category="metabolism",
                value=None,
                probability=inh_prob,
                prediction="Inhibitor" if inh_prob > self.confidence_threshold else "Non-inhibitor",
                confidence="medium",
                details={"enzyme": cyp.upper(), "type": "inhibition"},
            ))
            
            # Substrate prediction
            sub_prob = self._estimate_cyp_substrate(cyp, mol_props)
            predictions.append(ADMETPrediction(
                endpoint=f"{cyp}_substrate",
                category="metabolism",
                value=None,
                probability=sub_prob,
                prediction="Substrate" if sub_prob > self.confidence_threshold else "Non-substrate",
                confidence="medium",
                details={"enzyme": cyp.upper(), "type": "substrate"},
            ))
        
        # Metabolic stability
        stability_prob = self._estimate_metabolic_stability(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="metabolic_stability",
            category="metabolism",
            value=None,
            probability=stability_prob,
            prediction="Stable" if stability_prob > self.confidence_threshold else "Unstable",
            confidence="medium",
            details={"method": "Rule-based + ML"},
        ))
        
        return predictions
    
    def _predict_excretion(self, smiles: str, mol_props: dict) -> list[ADMETPrediction]:
        """Predict excretion properties."""
        predictions = []
        
        # Total Clearance
        cl_prob = self._estimate_clearance(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="total_clearance",
            category="excretion",
            value=None,
            probability=cl_prob,
            prediction="High" if cl_prob > self.confidence_threshold else "Low",
            confidence="low",
            details={"method": "Simplified estimation"},
        ))
        
        # Renal Clearance
        renal_prob = self._estimate_renal_clearance(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="renal_clearance",
            category="excretion",
            value=None,
            probability=renal_prob,
            prediction="Significant" if renal_prob > self.confidence_threshold else "Minimal",
            confidence="low",
            details={"method": "Simplified estimation"},
        ))
        
        return predictions
    
    def _predict_toxicity(self, smiles: str, mol_props: dict) -> list[ADMETPrediction]:
        """Predict toxicity properties."""
        predictions = []
        
        # Hepatotoxicity
        hepato_prob = self._estimate_hepatotoxicity(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="hepatotoxicity",
            category="toxicity",
            value=None,
            probability=hepato_prob,
            prediction="Toxic" if hepato_prob > self.confidence_threshold else "Non-toxic",
            confidence="medium",
            details={"method": "Rule-based + ML"},
        ))
        
        # Cardiotoxicity (hERG)
        cardio_prob = self._estimate_cardiotoxicity(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="cardiotoxicity_herg",
            category="toxicity",
            value=None,
            probability=cardio_prob,
            prediction="Risk" if cardio_prob > self.confidence_threshold else "Low Risk",
            confidence="high" if abs(cardio_prob - 0.5) > 0.3 else "medium",
            details={"method": "Rule-based + ML", "target": "hERG"},
        ))
        
        # AMES Mutagenicity
        ames_prob = self._estimate_ames(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="ames_mutagenicity",
            category="toxicity",
            value=None,
            probability=ames_prob,
            prediction="Mutagenic" if ames_prob > self.confidence_threshold else "Non-mutagenic",
            confidence="high" if abs(ames_prob - 0.5) > 0.3 else "medium",
            details={"method": "Rule-based + ML"},
        ))
        
        # General Toxicity
        gen_tox_prob = self._estimate_general_toxicity(mol_props)
        predictions.append(ADMETPrediction(
            endpoint="general_toxicity",
            category="toxicity",
            value=None,
            probability=gen_tox_prob,
            prediction="Toxic" if gen_tox_prob > self.confidence_threshold else "Non-toxic",
            confidence="medium",
            details={"method": "Rule-based + ML"},
        ))
        
        return predictions
    
    # Estimation methods (rule-based + ML fallback)
    def _estimate_hia(self, mol_props: dict) -> float:
        """Estimate Human Intestinal Absorption."""
        # Rule-based: high TPSA and high HBD reduce absorption
        tpsa = mol_props.get("tpsa", 0)
        hbd = mol_props.get("hbd", 0)
        logp = mol_props.get("logp", 0)
        
        prob = 0.8  # Base probability
        
        if tpsa > 140:
            prob -= 0.3
        elif tpsa > 90:
            prob -= 0.15
        
        if hbd > 5:
            prob -= 0.2
        elif hbd > 3:
            prob -= 0.1
        
        if logp > 5:
            prob -= 0.15
        elif logp < 0:
            prob -= 0.1
        
        # ML model override if available
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("hia", mol_props)
                if ml_prob is not None:
                    prob = 0.6 * ml_prob + 0.4 * prob  # Blend
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_caco2(self, mol_props: dict) -> float:
        """Estimate Caco-2 permeability."""
        logp = mol_props.get("logp", 0)
        tpsa = mol_props.get("tpsa", 0)
        mw = mol_props.get("molecular_weight", 0)
        
        prob = 0.5
        
        # Lipinski-like rules for permeability
        if 0 < logp < 3:
            prob += 0.2
        elif logp > 5:
            prob -= 0.2
        
        if tpsa < 90:
            prob += 0.2
        elif tpsa > 140:
            prob -= 0.2
        
        if mw < 400:
            prob += 0.1
        elif mw > 500:
            prob -= 0.15
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("caco2", mol_props)
                if ml_prob is not None:
                    prob = 0.6 * ml_prob + 0.4 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_bioavailability(self, mol_props: dict) -> float:
        """Estimate oral bioavailability."""
        # Use Lipinski + Veber rules
        from geneai.admet_prediction.molecular_properties import check_lipinski_rule_of_five, check_veber_rules
        
        lipinski = check_lipinski_rule_of_five(mol_props)
        veber = check_veber_rules(mol_props)
        
        prob = 0.5
        
        if lipinski["passes"]:
            prob += 0.2
        else:
            prob -= 0.1 * lipinski["violation_count"]
        
        if veber["passes"]:
            prob += 0.15
        else:
            prob -= 0.1 * veber["violation_count"]
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("bioavailability", mol_props)
                if ml_prob is not None:
                    prob = 0.6 * ml_prob + 0.4 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_bbb(self, mol_props: dict) -> float:
        """Estimate BBB penetration."""
        logp = mol_props.get("logp", 0)
        tpsa = mol_props.get("tpsa", 0)
        mw = mol_props.get("molecular_weight", 0)
        hbd = mol_props.get("hbd", 0)
        
        prob = 0.3  # Base (most drugs don't cross BBB)
        
        # Rules for BBB penetration
        if logp > 2 and logp < 5:
            prob += 0.2
        elif logp >= 5:
            prob -= 0.1
        
        if tpsa < 70:
            prob += 0.25
        elif tpsa > 90:
            prob -= 0.15
        
        if mw < 400:
            prob += 0.15
        elif mw > 500:
            prob -= 0.1
        
        if hbd < 3:
            prob += 0.1
        elif hbd > 5:
            prob -= 0.15
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("bbb", mol_props)
                if ml_prob is not None:
                    prob = 0.7 * ml_prob + 0.3 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_ppb(self, mol_props: dict) -> float:
        """Estimate plasma protein binding."""
        logp = mol_props.get("logp", 0)
        
        # Higher logP generally correlates with higher PPB
        if logp < 1:
            return 0.3
        elif logp < 2:
            return 0.5
        elif logp < 3:
            return 0.7
        elif logp < 4:
            return 0.85
        elif logp < 5:
            return 0.92
        else:
            return 0.95
    
    def _estimate_vdss(self, mol_props: dict) -> float:
        """Estimate volume of distribution."""
        logp = mol_props.get("logp", 0)
        tpsa = mol_props.get("tpsa", 0)
        
        # High logP, low TPSA -> high Vd
        prob = 0.5
        
        if logp > 3:
            prob += 0.2
        if tpsa < 80:
            prob += 0.15
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_cyp_inhibition(self, cyp: str, mol_props: dict) -> float:
        """Estimate CYP inhibition probability."""
        logp = mol_props.get("logp", 0)
        mw = mol_props.get("molecular_weight", 0)
        aromatic_rings = mol_props.get("aromatic_rings", 0)
        
        # General features that increase CYP inhibition
        prob = 0.2
        
        if logp > 3:
            prob += 0.15
        if mw > 300:
            prob += 0.1
        if aromatic_rings >= 2:
            prob += 0.15
        
        # CYP-specific adjustments
        if cyp == "cyp3a4":
            prob += 0.1  # CYP3A4 most promiscuous
        elif cyp == "cyp2d6":
            prob += 0.05
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single(f"{cyp}_inhibition", mol_props)
                if ml_prob is not None:
                    prob = 0.7 * ml_prob + 0.3 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_cyp_substrate(self, cyp: str, mol_props: dict) -> float:
        """Estimate CYP substrate probability."""
        logp = mol_props.get("logp", 0)
        mw = mol_props.get("molecular_weight", 0)
        
        prob = 0.25
        
        if 2 < logp < 5:
            prob += 0.15
        if 200 < mw < 500:
            prob += 0.1
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single(f"{cyp}_substrate", mol_props)
                if ml_prob is not None:
                    prob = 0.7 * ml_prob + 0.3 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_metabolic_stability(self, mol_props: dict) -> float:
        """Estimate metabolic stability."""
        logp = mol_props.get("logp", 0)
        tpsa = mol_props.get("tpsa", 0)
        rotatable = mol_props.get("rotatable_bonds", 0)
        
        prob = 0.5
        
        if logp < 3:
            prob += 0.15
        if tpsa > 80:
            prob += 0.1
        if rotatable < 5:
            prob += 0.1
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("metabolic_stability", mol_props)
                if ml_prob is not None:
                    prob = 0.6 * ml_prob + 0.4 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_clearance(self, mol_props: dict) -> float:
        """Estimate total clearance."""
        mw = mol_props.get("molecular_weight", 0)
        logp = mol_props.get("logp", 0)
        
        prob = 0.5
        
        if mw < 300:
            prob += 0.15
        if logp < 2:
            prob += 0.1
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_renal_clearance(self, mol_props: dict) -> float:
        """Estimate renal clearance."""
        mw = mol_props.get("molecular_weight", 0)
        logp = mol_props.get("logp", 0)
        charge = mol_props.get("formal_charge", 0)
        
        prob = 0.3
        
        if mw < 300:
            prob += 0.2
        if logp < 1:
            prob += 0.15
        if charge != 0:
            prob += 0.1
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_hepatotoxicity(self, mol_props: dict) -> float:
        """Estimate hepatotoxicity."""
        logp = mol_props.get("logp", 0)
        mw = mol_props.get("molecular_weight", 0)
        aromatic_rings = mol_props.get("aromatic_rings", 0)
        
        prob = 0.15
        
        if logp > 4:
            prob += 0.2
        if mw > 400:
            prob += 0.1
        if aromatic_rings >= 3:
            prob += 0.15
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("hepatotoxicity", mol_props)
                if ml_prob is not None:
                    prob = 0.7 * ml_prob + 0.3 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_cardiotoxicity(self, mol_props: dict) -> float:
        """Estimate cardiotoxicity (hERG)."""
        logp = mol_props.get("logp", 0)
        aromatic_rings = mol_props.get("aromatic_rings", 0)
        hba = mol_props.get("hba", 0)
        formal_charge = mol_props.get("formal_charge", 0)
        
        prob = 0.1
        
        # Known hERG risk factors
        if logp > 3:
            prob += 0.25
        if aromatic_rings >= 2:
            prob += 0.15
        if hba >= 4:
            prob += 0.1
        if formal_charge > 0:
            prob += 0.2
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("cardiotoxicity", mol_props)
                if ml_prob is not None:
                    prob = 0.8 * ml_prob + 0.2 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_ames(self, mol_props: dict) -> float:
        """Estimate AMES mutagenicity."""
        aromatic_rings = mol_props.get("aromatic_rings", 0)
        nitro_groups = 0  # Would need substructure search
        
        prob = 0.05
        
        if aromatic_rings >= 3:
            prob += 0.2
        
        # Structural alerts would go here
        # For now, simplified
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("ames", mol_props)
                if ml_prob is not None:
                    prob = 0.7 * ml_prob + 0.3 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _estimate_general_toxicity(self, mol_props: dict) -> float:
        """Estimate general toxicity."""
        logp = mol_props.get("logp", 0)
        mw = mol_props.get("molecular_weight", 0)
        
        prob = 0.1
        
        if logp > 4:
            prob += 0.15
        if mw > 500:
            prob += 0.1
        
        if self.use_ml_models and self.model_manager:
            try:
                ml_prob = self.model_manager.predict_single("general_toxicity", mol_props)
                if ml_prob is not None:
                    prob = 0.6 * ml_prob + 0.4 * prob
            except Exception:
                pass
        
        return max(0.0, min(1.0, prob))
    
    def _generate_summary(self, predictions: list[ADMETPrediction], drug_likeness: dict) -> dict[str, Any]:
        """Generate summary of ADMET predictions."""
        category_counts = {}
        risk_counts = {"high": 0, "medium": 0, "low": 0}
        
        for pred in predictions:
            cat = pred.category
            if cat not in category_counts:
                category_counts[cat] = {"total": 0, "positive": 0, "negative": 0}
            
            category_counts[cat]["total"] += 1
            
            if pred.prediction and pred.prediction in ["High", "Penetrant", "Inhibitor", "Substrate", "Toxic", "Risk", "Mutagenic", "Significant"]:
                category_counts[cat]["positive"] += 1
                if pred.confidence == "high":
                    risk_counts["high"] += 1
                elif pred.confidence == "medium":
                    risk_counts["medium"] += 1
                else:
                    risk_counts["low"] += 1
            else:
                category_counts[cat]["negative"] += 1
        
        # Overall risk assessment
        total_high_risk = risk_counts["high"]
        if total_high_risk >= 3:
            overall_risk = "High"
        elif total_high_risk >= 1:
            overall_risk = "Moderate"
        else:
            overall_risk = "Low"
        
        return {
            "category_breakdown": category_counts,
            "risk_distribution": risk_counts,
            "overall_risk": overall_risk,
            "drug_likeness_score": drug_likeness.get("overall_score", 0),
            "drug_likeness_assessment": drug_likeness.get("assessment", "Unknown"),
            "total_predictions": len(predictions),
            "warnings": [],
        }


def create_admet_engine(use_ml: bool = True) -> ADMETPredictionEngine:
    """Factory function to create ADMET engine."""
    return ADMETPredictionEngine(use_ml_models=use_ml)


# Backward-compatibility alias
ADMETEngine = ADMETPredictionEngine


# Convenience function for backward compatibility
_engine_instance = None


def predict_admet(smiles: str) -> ADMETResult:
    """Convenience function to run ADMET prediction."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = create_admet_engine()
    return _engine_instance.predict(smiles)