"""AI Candidate Ranking for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import json
import logging
import pickle
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from geneai.config import DATABASE_PATH

logger = logging.getLogger(__name__)

RANKING_DB_PATH = DATABASE_PATH.parent / "geneai_ai_ranking.sqlite3"
MODEL_PATH = DATABASE_PATH.parent / "ai_ranking_models"

MODEL_PATH.mkdir(parents=True, exist_ok=True)

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    warnings.warn("scikit-learn not available; ML ranking will use heuristic scoring")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False


@dataclass
class CandidateFeatures:
    """Feature vector for a drug candidate."""
    # Molecular properties
    mw: float = 0.0
    logp: float = 0.0
    tpsa: float = 0.0
    hbd: int = 0
    hba: int = 0
    rotatable_bonds: int = 0
    aromatic_rings: int = 0
    
    # ADMET scores
    absorption: float = 0.0
    distribution: float = 0.0
    metabolism: float = 0.0
    excretion: float = 0.0
    toxicity: float = 0.0
    overall_admet: float = 0.0
    
    # Safety
    safety_risk_score: float = 0.0
    structural_alerts: int = 0
    risk_factors: int = 0
    
    # Binding
    avg_binding_affinity: float = 0.0
    max_binding_affinity: float = 0.0
    n_targets: int = 0
    
    # Clinical
    max_phase: int = 0
    n_indications: int = 0
    is_approved: int = 0
    
    # Knowledge graph
    kg_path_length: float = 0.0
    kg_path_count: int = 0
    kg_centrality: float = 0.0
    
    # Disease relevance
    disease_association_score: float = 0.0
    gene_disease_link_strength: float = 0.0
    
    # Repurposing
    repurposing_evidence_count: int = 0
    
    # Literature
    literature_support_count: int = 0
    
    def to_array(self) -> np.ndarray:
        return np.array([
            self.mw, self.logp, self.tpsa, self.hbd, self.hba,
            self.rotatable_bonds, self.aromatic_rings,
            self.absorption, self.distribution, self.metabolism,
            self.excretion, self.toxicity, self.overall_admet,
            self.safety_risk_score, self.structural_alerts, self.risk_factors,
            self.avg_binding_affinity, self.max_binding_affinity, self.n_targets,
            self.max_phase, self.n_indications, self.is_approved,
            self.kg_path_length, self.kg_path_count, self.kg_centrality,
            self.disease_association_score, self.gene_disease_link_strength,
            self.repurposing_evidence_count, self.literature_support_count,
        ], dtype=np.float32)
    
    @classmethod
    def feature_names(cls) -> list[str]:
        return [
            "mw", "logp", "tpsa", "hbd", "hba", "rotatable_bonds", "aromatic_rings",
            "absorption", "distribution", "metabolism", "excretion", "toxicity", "overall_admet",
            "safety_risk_score", "structural_alerts", "risk_factors",
            "avg_binding_affinity", "max_binding_affinity", "n_targets",
            "max_phase", "n_indications", "is_approved",
            "kg_path_length", "kg_path_count", "kg_centrality",
            "disease_association_score", "gene_disease_link_strength",
            "repurposing_evidence_count", "literature_support_count",
        ]


@dataclass
class RankingResult:
    """Result of candidate ranking."""
    candidate_id: str
    rank: int
    score: float
    confidence: float
    feature_contributions: dict[str, float]
    explanation: str


class AICandidateRanker:
    """ML-based multi-criteria drug candidate ranking."""
    
    def __init__(self, model_type: str = "gradient_boosting"):
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.feature_names = CandidateFeatures.feature_names()
        self.is_trained = False
        self.training_history = []
    
    def _create_model(self):
        if not SKLEARN_AVAILABLE:
            return None
        
        if self.model_type == "random_forest":
            return RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
        elif self.model_type == "gradient_boosting":
            return GradientBoostingRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42)
        elif self.model_type == "xgboost" and XGBOOST_AVAILABLE:
            return xgb.XGBRegressor(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, n_jobs=-1, verbosity=0
            )
        elif self.model_type == "lightgbm" and LIGHTGBM_AVAILABLE:
            return lgb.LGBMRegressor(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                num_leaves=31, subsample=0.8, colsample_bytree=0.8,
                random_state=42, n_jobs=-1, verbosity=-1
            )
        elif self.model_type == "linear":
            return Ridge(alpha=1.0)
        else:
            return GradientBoostingRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42)
    
    def train(self, 
              features_list: list[CandidateFeatures], 
              targets: list[float],
              validation_split: float = 0.2) -> dict[str, Any]:
        """Train the ranking model."""
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not available; cannot train ML model")
            return {"error": "sklearn not available"}
        
        X = np.array([f.to_array() for f in features_list])
        y = np.array(targets)
        
        if len(X) < 10:
            logger.warning("Insufficient training data (<10 samples)")
            return {"error": "insufficient data"}
        
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42
        )
        
        self.model = self._create_model()
        self.model.fit(X_train, y_train)
        
        # Validation
        train_score = self.model.score(X_train, y_train)
        val_score = self.model.score(X_val, y_val)
        
        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y, cv=min(5, len(X)), scoring='r2')
        
        self.is_trained = True
        
        history = {
            "train_r2": train_score,
            "val_r2": val_score,
            "cv_r2_mean": float(np.mean(cv_scores)),
            "cv_r2_std": float(np.std(cv_scores)),
            "n_samples": len(X),
            "model_type": self.model_type,
        }
        self.training_history.append(history)
        
        logger.info(f"Model trained: R²={val_score:.3f}, CV R²={np.mean(cv_scores):.3f}±{np.std(cv_scores):.3f}")
        
        return history
    
    def predict(self, features: CandidateFeatures) -> tuple[float, float]:
        """Predict score and confidence for a candidate."""
        if not self.is_trained or not SKLEARN_AVAILABLE:
            return self._heuristic_score(features)
        
        X = features.to_array().reshape(1, -1)
        score = float(self.model.predict(X)[0])
        
        # Estimate confidence from prediction variance (simplified)
        confidence = 0.8  # Would use ensemble variance in production
        
        return score, confidence
    
    def predict_batch(self, features_list: list[CandidateFeatures]) -> list[tuple[float, float]]:
        """Predict scores for multiple candidates."""
        if not self.is_trained or not SKLEARN_AVAILABLE:
            return [self._heuristic_score(f) for f in features_list]
        
        X = np.array([f.to_array() for f in features_list])
        scores = self.model.predict(X)
        
        return [(float(s), 0.8) for s in scores]
    
    def _heuristic_score(self, features: CandidateFeatures) -> tuple[float, float]:
        """Fallback heuristic scoring when ML not available."""
        score = 0.0
        
        # ADMET (30%)
        score += features.overall_admet * 0.3
        
        # Safety (25%) - lower risk = higher score
        safety_map = {"Low": 1.0, "Low-Moderate": 0.7, "Moderate": 0.4, "High": 0.1}
        # Use safety_risk_score (0-1, lower is better)
        score += (1.0 - features.safety_risk_score) * 0.25
        
        # Binding (20%)
        if features.n_targets > 0:
            norm_affinity = min(max((features.avg_binding_affinity - 5) / 5, 0), 1)
            score += norm_affinity * 0.2
        
        # Clinical validation (15%)
        if features.max_phase > 0:
            score += min(features.max_phase / 4.0, 1.0) * 0.15
        
        # Disease relevance (10%)
        score += features.disease_association_score * 0.1
        
        return score, 0.6
    
    def explain(self, features: CandidateFeatures) -> dict[str, float]:
        """Explain feature contributions to score."""
        if not self.is_trained or not SKLEARN_AVAILABLE:
            return self._heuristic_explanation(features)
        
        # Get feature importances from model
        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
        elif hasattr(self.model, "coef_"):
            importances = np.abs(self.model.coef_)
        else:
            return self._heuristic_explanation(features)
        
        X = features.to_array()
        contributions = {}
        for i, name in enumerate(self.feature_names):
            contributions[name] = float(importances[i] * X[i])
        
        # Normalize
        total = sum(abs(v) for v in contributions.values())
        if total > 0:
            contributions = {k: v/total for k, v in contributions.items()}
        
        return contributions
    
    def _heuristic_explanation(self, features: CandidateFeatures) -> dict[str, float]:
        """Heuristic feature contributions."""
        contribs = {
            "overall_admet": features.overall_admet * 0.3,
            "safety": (1.0 - features.safety_risk_score) * 0.25,
            "binding": min(max((features.avg_binding_affinity - 5) / 5, 0), 1) * 0.2 if features.n_targets > 0 else 0,
            "clinical": min(features.max_phase / 4.0, 1.0) * 0.15 if features.max_phase > 0 else 0,
            "disease_relevance": features.disease_association_score * 0.1,
        }
        total = sum(contribs.values())
        if total > 0:
            contribs = {k: v/total for k, v in contribs.items()}
        return contribs
    
    def save_model(self, path: str | None = None) -> str:
        """Save trained model to disk."""
        if path is None:
            path = str(MODEL_PATH / f"ranker_{self.model_type}.pkl")
        
        if not SKLEARN_AVAILABLE:
            return path
        
        with open(path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "scaler": self.scaler,
                "model_type": self.model_type,
                "feature_names": self.feature_names,
                "is_trained": self.is_trained,
                "training_history": self.training_history,
            }, f)
        
        return path
    
    def load_model(self, path: str | None = None) -> bool:
        """Load trained model from disk."""
        if path is None:
            path = str(MODEL_PATH / f"ranker_{self.model_type}.pkl")
        
        if not Path(path).exists():
            return False
        
        if not SKLEARN_AVAILABLE:
            return False
        
        with open(path, "rb") as f:
            data = pickle.load(f)
        
        self.model = data["model"]
        self.scaler = data["scaler"]
        self.model_type = data["model_type"]
        self.feature_names = data["feature_names"]
        self.is_trained = data["is_trained"]
        self.training_history = data.get("training_history", [])
        
        return True


def extract_candidate_features(candidate: Any, 
                                context: dict[str, Any] | None = None) -> CandidateFeatures:
    """Extract features from a drug candidate object."""
    features = CandidateFeatures()
    context = context or {}
    
    # Molecular properties (from SMILES)
    if hasattr(candidate, "smiles") and candidate.smiles:
        # In production, would use RDKit to calculate
        pass
    
    # ADMET
    if hasattr(candidate, "admet_score") and candidate.admet_score:
        features.overall_admet = candidate.admet_score
    if hasattr(candidate, "admet_details"):
        details = candidate.admet_details
        features.absorption = details.get("absorption", 0)
        features.distribution = details.get("distribution", 0)
        features.metabolism = details.get("metabolism", 0)
        features.excretion = details.get("excretion", 0)
        features.toxicity = details.get("toxicity", 0)
    
    # Safety
    if hasattr(candidate, "safety_risk"):
        risk_map = {"Low": 0.0, "Low-Moderate": 0.25, "Moderate": 0.5, "High": 0.8}
        features.safety_risk_score = risk_map.get(candidate.safety_risk, 0.5)
    if hasattr(candidate, "structural_alerts"):
        features.structural_alerts = candidate.structural_alerts
    if hasattr(candidate, "risk_factors"):
        features.risk_factors = candidate.risk_factors
    
    # Binding
    if hasattr(candidate, "binding_affinities") and candidate.binding_affinities:
        affinities = list(candidate.binding_affinities.values())
        features.avg_binding_affinity = sum(affinities) / len(affinities)
        features.max_binding_affinity = max(affinities)
        features.n_targets = len(candidate.binding_affinities)
    
    # Clinical
    if hasattr(candidate, "phase"):
        features.max_phase = candidate.phase
        features.is_approved = 1 if candidate.phase >= 4 else 0
    if hasattr(candidate, "indications"):
        features.n_indications = len(candidate.indications)
    
    # Knowledge graph
    if hasattr(candidate, "knowledge_graph_path"):
        features.kg_path_count = len(candidate.knowledge_graph_path)
        if candidate.knowledge_graph_path:
            features.kg_path_length = np.mean([len(p) for p in candidate.knowledge_graph_path])
    if hasattr(candidate, "kg_centrality"):
        features.kg_centrality = candidate.kg_centrality
    
    # Disease relevance
    if context.get("disease_association_score"):
        features.disease_association_score = context["disease_association_score"]
    if context.get("gene_disease_link_strength"):
        features.gene_disease_link_strength = context["gene_disease_link_strength"]
    
    # Repurposing
    if hasattr(candidate, "repurposing_evidence"):
        features.repurposing_evidence_count = len(candidate.repurposing_evidence)
    
    # Literature
    if hasattr(candidate, "literature_support"):
        features.literature_support_count = len(candidate.literature_support)
    
    return features


def rank_candidates(candidates: list[Any], 
                    context: dict[str, Any] | None = None,
                    model_type: str = "gradient_boosting",
                    pretrained_path: str | None = None) -> list[RankingResult]:
    """Rank a list of candidates using AI model."""
    ranker = AICandidateRanker(model_type)
    
    # Try to load pretrained model
    if pretrained_path:
        ranker.load_model(pretrained_path)
    else:
        ranker.load_model()  # Try default path
    
    # Extract features
    features_list = [extract_candidate_features(c, context) for c in candidates]
    
    # Predict scores
    predictions = ranker.predict_batch(features_list)
    
    # Build results
    results = []
    for i, (candidate, (score, confidence)) in enumerate(zip(candidates, predictions)):
        candidate_id = getattr(candidate, "drug_id", getattr(candidate, "id", f"cand_{i}"))
        
        contributions = ranker.explain(features_list[i])
        
        # Generate explanation text
        top_features = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        explanation = f"Top factors: {', '.join(f'{k} ({v:.2f})' for k, v in top_features)}"
        
        results.append(RankingResult(
            candidate_id=candidate_id,
            rank=0,  # Will set after sorting
            score=score,
            confidence=confidence,
            feature_contributions=contributions,
            explanation=explanation,
        ))
    
    # Sort by score and assign ranks
    results.sort(key=lambda r: r.score, reverse=True)
    for i, r in enumerate(results):
        r.rank = i + 1
    
    return results


def create_training_data_from_historical(historical_results: list[dict]) -> tuple[list[CandidateFeatures], list[float]]:
    """Create training data from historical ranking results."""
    features_list = []
    targets = []
    
    for result in historical_results:
        # This would extract features and known outcomes from past analyses
        # For now, return empty
        pass
    
    return features_list, targets