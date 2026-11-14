"""ML models for drug-target interaction prediction."""
from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score, StratifiedKFold, train_test_split
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
        confusion_matrix, classification_report
    )
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

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

from geneai.drug_target_prediction.molecular_descriptors import (
    calculate_molecular_descriptors,
    calculate_morgan_fingerprint,
    batch_calculate_descriptors,
    batch_calculate_fingerprints,
    is_rdkit_available,
)

logger = logging.getLogger(__name__)

MODEL_TYPES = {
    "random_forest": RandomForestClassifier,
    "gradient_boosting": GradientBoostingClassifier,
    "logistic_regression": LogisticRegression,
}

if XGBOOST_AVAILABLE:
    MODEL_TYPES["xgboost"] = xgb.XGBClassifier

if LIGHTGBM_AVAILABLE:
    MODEL_TYPES["lightgbm"] = lgb.LGBMClassifier

DEFAULT_RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 15,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}

DEFAULT_GB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "random_state": 42,
}

DEFAULT_XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": 1,
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "auc",
}

DEFAULT_LGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

DEFAULT_LR_PARAMS = {
    "max_iter": 2000,
    "class_weight": "balanced",
    "random_state": 42,
}


class DrugTargetPredictor:
    """Drug-target interaction prediction using ML models."""
    
    def __init__(
        self,
        model_type: str = "random_forest",
        model_params: dict[str, Any] | None = None,
        use_fingerprints: bool = True,
        fp_type: str = "morgan",
        n_fp_bits: int = 2048,
    ):
        """Initialize the predictor.
        
        Args:
            model_type: Type of ML model ("random_forest", "gradient_boosting", "logistic_regression")
            model_params: Custom parameters for the model
            use_fingerprints: Whether to use molecular fingerprints as features
            fp_type: Fingerprint type ("morgan", "maccs", "rdkit")
            n_fp_bits: Number of fingerprint bits
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn is required for ML models")
        if not is_rdkit_available():
            raise ImportError("RDKit is required for molecular feature calculation")
        
        self.model_type = model_type
        self.use_fingerprints = use_fingerprints
        self.fp_type = fp_type
        self.n_fp_bits = n_fp_bits
        self.model = None
        self.scaler = StandardScaler()
        self.imputer = SimpleImputer(strategy="median")
        self.feature_names = None
        self.is_fitted = False
        self.training_history = {}
        
        # Set model parameters
        if model_params is None:
            if model_type == "random_forest":
                model_params = DEFAULT_RF_PARAMS
            elif model_type == "gradient_boosting":
                model_params = DEFAULT_GB_PARAMS
            elif model_type == "xgboost":
                model_params = DEFAULT_XGB_PARAMS
            elif model_type == "lightgbm":
                model_params = DEFAULT_LGB_PARAMS
            elif model_type == "logistic_regression":
                model_params = DEFAULT_LR_PARAMS
            else:
                model_params = {}
        
        self.model_params = model_params
        self._build_model()
    
    def _build_model(self):
        """Build the ML pipeline."""
        model_class = MODEL_TYPES.get(self.model_type)
        if model_class is None:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        model = model_class(**self.model_params)
        
        # Tree-based models don't need scaling
        tree_models = {"random_forest", "gradient_boosting", "xgboost", "lightgbm"}
        
        if self.model_type == "logistic_regression":
            self.pipeline = Pipeline([
                ("imputer", self.imputer),
                ("scaler", self.scaler),
                ("classifier", model),
            ])
        elif self.model_type in tree_models:
            self.pipeline = Pipeline([
                ("imputer", self.imputer),
                ("classifier", model),
            ])
        else:
            # Default pipeline with scaling for unknown types
            self.pipeline = Pipeline([
                ("imputer", self.imputer),
                ("scaler", self.scaler),
                ("classifier", model),
            ])
        
        self.model = self.pipeline
    
    def _prepare_features(
        self,
        drug_smiles: list[str],
        target_features: list[dict[str, float]] | None = None,
    ) -> np.ndarray:
        """Prepare feature matrix from drug SMILES and optional target features.
        
        Args:
            drug_smiles: List of drug SMILES strings
            target_features: Optional list of target feature dictionaries
            
        Returns:
            Feature matrix (n_samples x n_features)
        """
        # Calculate molecular descriptors
        desc_df = batch_calculate_descriptors(drug_smiles)
        descriptor_cols = [c for c in desc_df.columns if c != "smiles"]
        drug_features = desc_df[descriptor_cols].values
        
        # Add fingerprints if enabled
        if self.use_fingerprints:
            fps = batch_calculate_fingerprints(drug_smiles, self.fp_type)
            if fps is not None:
                drug_features = np.hstack([drug_features, fps])
        
        # Add target features if provided
        if target_features is not None:
            target_df = pd.DataFrame(target_features)
            target_array = target_df.values
            if len(target_array) == len(drug_features):
                drug_features = np.hstack([drug_features, target_array])
        
        return drug_features
    
    def train(
        self,
        drug_smiles: list[str],
        labels: list[int],
        target_features: list[dict[str, float]] | None = None,
        validate: bool = True,
        test_size: float = 0.2,
    ) -> dict[str, Any]:
        """Train the drug-target interaction model.
        
        Args:
            drug_smiles: List of drug SMILES strings
            labels: Binary interaction labels (1=interacts, 0=no interaction)
            target_features: Optional target features for each sample
            validate: Whether to perform cross-validation
            test_size: Test set fraction for holdout validation
            
        Returns:
            Training results with metrics
        """
        X = self._prepare_features(drug_smiles, target_features)
        y = np.array(labels)
        
        # Store feature names
        n_desc = len([c for c in batch_calculate_descriptors(drug_smiles[:1]).columns if c != "smiles"])
        n_fp = self.n_fp_bits if self.use_fingerprints else 0
        self.feature_names = [f"desc_{i}" for i in range(n_desc)] + [f"fp_{i}" for i in range(n_fp)]
        if target_features and len(target_features) > 0:
            n_target = len(target_features[0])
            self.feature_names += [f"target_{i}" for i in range(n_target)]
        
        # Handle class imbalance
        pos_weight = np.sum(y == 0) / np.sum(y == 1) if np.sum(y == 1) > 0 else 1
        
        results = {
            "model_type": self.model_type,
            "n_samples": len(y),
            "n_positive": int(np.sum(y)),
            "n_negative": int(np.sum(y == 0)),
            "pos_weight": pos_weight,
        }
        
        if validate and len(y) >= 10:
            # Cross-validation
            cv = StratifiedKFold(n_splits=min(5, len(y)), shuffle=True, random_state=42)
            cv_scores = cross_val_score(self.pipeline, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
            results["cv_roc_auc_mean"] = float(np.mean(cv_scores))
            results["cv_roc_auc_std"] = float(np.std(cv_scores))
            results["cv_scores"] = cv_scores.tolist()
        
        # Train on full data
        self.pipeline.fit(X, y)
        self.is_fitted = True
        
        # Training set predictions
        y_pred = self.pipeline.predict(X)
        y_proba = self.pipeline.predict_proba(X)[:, 1]
        
        results["train_accuracy"] = float(accuracy_score(y, y_pred))
        results["train_precision"] = float(precision_score(y, y_pred, zero_division=0))
        results["train_recall"] = float(recall_score(y, y_pred, zero_division=0))
        results["train_f1"] = float(f1_score(y, y_pred, zero_division=0))
        results["train_roc_auc"] = float(roc_auc_score(y, y_proba))
        
        # Feature importance
        if hasattr(self.pipeline.named_steps["classifier"], "feature_importances_"):
            importances = self.pipeline.named_steps["classifier"].feature_importances_
            feature_importance = list(zip(self.feature_names, importances))
            feature_importance.sort(key=lambda x: x[1], reverse=True)
            results["feature_importance"] = feature_importance[:50]
        
        self.training_history = results
        logger.info("Model trained: %s samples, AUC=%.4f", len(y), results.get("train_roc_auc", 0))
        
        return results
    
    def predict(
        self,
        drug_smiles: list[str],
        target_features: list[dict[str, float]] | None = None,
        return_proba: bool = True,
    ) -> list[dict[str, Any]]:
        """Predict drug-target interactions.
        
        Args:
            drug_smiles: List of drug SMILES strings
            target_features: Optional target features for each sample
            return_proba: Whether to return probability scores
            
        Returns:
            List of prediction dictionaries
        """
        if not self.is_fitted:
            raise ValueError("Model must be trained before prediction")
        
        X = self._prepare_features(drug_smiles, target_features)
        predictions = self.pipeline.predict(X)
        probabilities = self.pipeline.predict_proba(X)[:, 1] if return_proba else None
        
        results = []
        for i, smiles in enumerate(drug_smiles):
            result = {
                "drug_smiles": smiles,
                "predicted_interaction": int(predictions[i]),
                "interaction_probability": float(probabilities[i]) if probabilities is not None else None,
                "confidence": "high" if probabilities is not None and (probabilities[i] > 0.8 or probabilities[i] < 0.2) else "medium" if probabilities is not None else "unknown",
            }
            results.append(result)
        
        return results
    
    def predict_single(
        self,
        drug_smiles: str,
        target_features: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Predict interaction for a single drug-target pair.
        
        Args:
            drug_smiles: Drug SMILES string
            target_features: Optional target features
            
        Returns:
            Prediction dictionary
        """
        return self.predict([drug_smiles], [target_features] if target_features else None)[0]
    
    def get_feature_importance(self, top_n: int = 20) -> list[dict[str, Any]]:
        """Get feature importance from trained model.
        
        Args:
            top_n: Number of top features to return
            
        Returns:
            List of feature importance dictionaries
        """
        if not self.is_fitted:
            return []
        
        classifier = self.pipeline.named_steps["classifier"]
        if not hasattr(classifier, "feature_importances_"):
            return []
        
        importances = classifier.feature_importances_
        feature_importance = list(zip(self.feature_names, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {"feature": name, "importance": float(imp), "rank": i + 1}
            for i, (name, imp) in enumerate(feature_importance[:top_n])
        ]
    
    def save_model(self, path: str | Path) -> None:
        """Save trained model to disk.
        
        Args:
            path: Path to save model
        """
        if not self.is_fitted:
            raise ValueError("Model must be trained before saving")
        
        model_data = {
            "pipeline": self.pipeline,
            "model_type": self.model_type,
            "model_params": self.model_params,
            "use_fingerprints": self.use_fingerprints,
            "fp_type": self.fp_type,
            "n_fp_bits": self.n_fp_bits,
            "feature_names": self.feature_names,
            "training_history": self.training_history,
        }
        
        with open(path, "wb") as f:
            pickle.dump(model_data, f)
        
        logger.info("Model saved to %s", path)
    
    @classmethod
    def load_model(cls, path: str | Path) -> "DrugTargetPredictor":
        """Load trained model from disk.
        
        Args:
            path: Path to model file
            
        Returns:
            Loaded DrugTargetPredictor instance
        """
        with open(path, "rb") as f:
            model_data = pickle.load(f)
        
        predictor = cls(
            model_type=model_data["model_type"],
            model_params=model_data["model_params"],
            use_fingerprints=model_data["use_fingerprints"],
            fp_type=model_data["fp_type"],
            n_fp_bits=model_data["n_fp_bits"],
        )
        
        predictor.pipeline = model_data["pipeline"]
        predictor.feature_names = model_data["feature_names"]
        predictor.training_history = model_data["training_history"]
        predictor.is_fitted = True
        
        logger.info("Model loaded from %s", path)
        return predictor


def create_sample_training_data() -> tuple[list[str], list[int]]:
    """Create sample training data for testing.
    
    Returns:
        Tuple of (SMILES list, labels)
    """
    # Known interacting pairs (positive examples)
    positive_smiles = [
        "CC(=O)OC1=CC=CC=C1C(=O)O",  # Aspirin
        "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",  # Ibuprofen
        "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",  # Caffeine
        "CCO",  # Ethanol
        "CC(=O)NCCC1=CNc2c1cc(OC)cc2",  # Serotonin-like
        "CN(C)CCOC1=CC=C(C=C1)C2=CC=CC=C2",  # Diphenhydramine-like
        "CC1=CC=C(C=C1)S(=O)(=O)N",  # Sulfonamide
        "C1=CC=C2C(=C1)C(=O)C3=CC=CC=C3C2=O",  # Fluorenone
        "CC(C)NC1=NC=NC2=NC=NC(=N2)N1",  # Aminopterin-like
        "CCCCCC(=O)OCC1=CC=CC=C1C(=O)O",  # Aspirin ester
    ]
    
    # Non-interacting / random (negative examples)
    negative_smiles = [
        "C",  # Methane
        "CC",  # Ethane
        "CCC",  # Propane
        "CCCC",  # Butane
        "CCCCC",  # Pentane
        "CCCCCC",  # Hexane
        "CCOCC",  # Diethyl ether
        "CCCCCCCC",  # Octane
        "CCCCCCCCCC",  # Decane
        "C1CCCCC1",  # Cyclohexane
    ]
    
    smiles = positive_smiles + negative_smiles
    labels = [1] * len(positive_smiles) + [0] * len(negative_smiles)
    
    return smiles, labels


def train_chembl_model(
    chembl_activities: list[dict[str, Any]],
    activity_threshold: float = 1000.0,  # nM
) -> DrugTargetPredictor:
    """Train a model from ChEMBL bioactivity data.
    
    Args:
        chembl_activities: List of ChEMBL activity records with 'canonical_smiles' and 'standard_value' (nM)
        activity_threshold: Threshold in nM for active/inactive classification
        
    Returns:
        Trained DrugTargetPredictor
    """
    smiles = []
    labels = []
    
    for act in chembl_activities:
        smi = act.get("canonical_smiles")
        value = act.get("standard_value")
        if smi and value is not None:
            smiles.append(smi)
            labels.append(1 if value <= activity_threshold else 0)
    
    if len(set(labels)) < 2:
        raise ValueError("Need both active and inactive compounds for training")
    
    predictor = DrugTargetPredictor(model_type="random_forest")
    predictor.train(smiles, labels)
    
    return predictor