"""Machine Learning Models - Module 3: ML architecture for ADMET prediction."""
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

from geneai.admet_prediction.molecular_properties import (
    calculate_molecular_properties,
    is_rdkit_available,
)

logger = logging.getLogger(__name__)

# Available ADMET endpoints for ML models
ADMET_ENDPOINTS = [
    "hia",  # Human Intestinal Absorption
    "caco2",  # Caco-2 Permeability
    "bioavailability",  # Oral Bioavailability
    "bbb",  # BBB Penetration
    "cyp1a2_inhibition", "cyp2c9_inhibition", "cyp2c19_inhibition", "cyp2d6_inhibition", "cyp3a4_inhibition",
    "cyp1a2_substrate", "cyp2c9_substrate", "cyp2c19_substrate", "cyp2d6_substrate", "cyp3a4_substrate",
    "metabolic_stability",
    "hepatotoxicity",
    "cardiotoxicity",
    "ames",
    "general_toxicity",
]

DEFAULT_RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 15,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": 1,
}

DEFAULT_GB_PARAMS = {
    "n_estimators": 150,
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
    "n_jobs": 1,
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
    "n_jobs": 1,
    "verbose": -1,
}

DEFAULT_LR_PARAMS = {
    "max_iter": 2000,
    "class_weight": "balanced",
    "random_state": 42,
}

MODEL_TYPES = {
    "random_forest": RandomForestClassifier,
    "gradient_boosting": GradientBoostingClassifier,
    "logistic_regression": LogisticRegression,
}

if XGBOOST_AVAILABLE:
    MODEL_TYPES["xgboost"] = xgb.XGBClassifier

if LIGHTGBM_AVAILABLE:
    MODEL_TYPES["lightgbm"] = lgb.LGBMClassifier


class ADMETModel:
    """Individual ADMET endpoint model."""
    
    def __init__(
        self,
        endpoint: str,
        model_type: str = "random_forest",
        model_params: dict[str, Any] | None = None,
    ):
        """Initialize model for specific endpoint.
        
        Args:
            endpoint: ADMET endpoint name
            model_type: Type of ML model
            model_params: Model parameters
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn is required for ML models")
        if not is_rdkit_available():
            raise ImportError("RDKit is required for molecular features")
        
        self.endpoint = endpoint
        self.model_type = model_type
        self.is_fitted = False
        self.feature_names = None
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
        self._build_pipeline()
    
    def _build_pipeline(self):
        """Build the ML pipeline."""
        model_class = MODEL_TYPES.get(self.model_type)
        if model_class is None:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        model = model_class(**self.model_params)
        
        # Tree-based models don't need scaling
        tree_models = {"random_forest", "gradient_boosting", "xgboost", "lightgbm"}
        
        if self.model_type == "logistic_regression":
            self.pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("classifier", model),
            ])
        elif self.model_type in tree_models:
            self.pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("classifier", model),
            ])
        else:
            # Default pipeline with scaling for unknown types
            self.pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("classifier", model),
            ])
    
    def _prepare_features(self, mol_props_list: list[dict]) -> np.ndarray:
        """Prepare feature matrix from molecular properties."""
        # Extract relevant features
        feature_keys = [
            "molecular_weight", "logp", "tpsa", "hbd", "hba",
            "rotatable_bonds", "aromatic_rings", "aliphatic_rings",
            "heteroatoms", "fraction_csp3", "labute_asa",
            "exact_molecular_weight", "num_atoms", "num_bonds",
            "total_rings", "num_chiral_centers", "num_spiro_atoms",
            "num_bridgehead_atoms", "bertz_ct", "formal_charge",
        ]
        
        features = []
        for props in mol_props_list:
            row = []
            for key in feature_keys:
                val = props.get(key)
                if val is None:
                    val = np.nan
                row.append(val)
            features.append(row)
        
        self.feature_names = feature_keys
        return np.array(features, dtype=float)
    
    def train(
        self,
        smiles_list: list[str],
        labels: list[int],
        validate: bool = True,
    ) -> dict[str, Any]:
        """Train the model.
        
        Args:
            smiles_list: List of SMILES strings
            labels: Binary labels
            validate: Whether to perform cross-validation
            
        Returns:
            Training results
        """
        # Calculate molecular properties for all SMILES
        mol_props_list = [calculate_molecular_properties(smi) for smi in smiles_list]
        
        # Filter out failed calculations
        valid_data = [(props, label) for props, label in zip(mol_props_list, labels) 
                      if "error" not in props]
        
        if len(valid_data) < 10:
            raise ValueError(f"Insufficient valid data: {len(valid_data)} samples")
        
        mol_props_list, labels = zip(*valid_data)
        
        X = self._prepare_features(mol_props_list)
        y = np.array(labels)
        
        results = {
            "endpoint": self.endpoint,
            "model_type": self.model_type,
            "n_samples": len(y),
            "n_positive": int(np.sum(y)),
            "n_negative": int(np.sum(y == 0)),
        }
        
        if validate and len(y) >= 10:
            cv = StratifiedKFold(n_splits=min(5, len(y)), shuffle=True, random_state=42)
            cv_scores = cross_val_score(self.pipeline, X, y, cv=cv, scoring="roc_auc", n_jobs=1)
            results["cv_roc_auc_mean"] = float(np.mean(cv_scores))
            results["cv_roc_auc_std"] = float(np.std(cv_scores))
            results["cv_scores"] = cv_scores.tolist()
        
        # Train on full data
        self.pipeline.fit(X, y)
        self.is_fitted = True
        
        # Training metrics
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
            results["feature_importance"] = feature_importance[:20]
        
        self.training_history = results
        logger.info("Model trained for %s: %s samples, AUC=%.4f", self.endpoint, len(y), results.get("train_roc_auc", 0))
        
        return results
    
    def predict_proba(self, mol_props: dict) -> float | None:
        """Predict probability for a single compound."""
        if not self.is_fitted:
            return None
        
        try:
            X = self._prepare_features([mol_props])
            proba = self.pipeline.predict_proba(X)[0, 1]
            return float(proba)
        except Exception as e:
            logger.warning("Prediction failed for %s: %s", self.endpoint, e)
            return None
    
    def save(self, path: str | Path) -> None:
        """Save model to disk."""
        if not self.is_fitted:
            raise ValueError("Model must be trained before saving")
        
        model_data = {
            "endpoint": self.endpoint,
            "model_type": self.model_type,
            "model_params": self.model_params,
            "pipeline": self.pipeline,
            "feature_names": self.feature_names,
            "training_history": self.training_history,
        }
        
        with open(path, "wb") as f:
            pickle.dump(model_data, f)
        
        logger.info("Model saved for %s to %s", self.endpoint, path)
    
    @classmethod
    def load(cls, path: str | Path) -> "ADMETModel":
        """Load model from disk."""
        with open(path, "rb") as f:
            model_data = pickle.load(f)
        
        model = cls(
            endpoint=model_data["endpoint"],
            model_type=model_data["model_type"],
            model_params=model_data["model_params"],
        )
        
        model.pipeline = model_data["pipeline"]
        model.feature_names = model_data["feature_names"]
        model.training_history = model_data["training_history"]
        model.is_fitted = True
        
        logger.info("Model loaded for %s from %s", model_data["endpoint"], path)
        return model


class ADMETModelManager:
    """Manager for multiple ADMET models."""
    
    def __init__(self, model_dir: str | Path | None = None):
        """Initialize model manager.
        
        Args:
            model_dir: Directory containing trained models
        """
        self.models: dict[str, ADMETModel] = {}
        self.model_dir = Path(model_dir) if model_dir else None
        
        if self.model_dir:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self._load_models()
    
    def _load_models(self):
        """Load all models from directory."""
        if not self.model_dir or not self.model_dir.exists():
            return
        
        for model_file in self.model_dir.glob("*.pkl"):
            try:
                endpoint = model_file.stem
                model = ADMETModel.load(model_file)
                self.models[endpoint] = model
                logger.info("Loaded model for %s", endpoint)
            except Exception as e:
                logger.warning("Failed to load model %s: %s", model_file, e)
    
    def get_model(self, endpoint: str) -> ADMETModel | None:
        """Get model for endpoint."""
        return self.models.get(endpoint)
    
    def train_model(
        self,
        endpoint: str,
        smiles_list: list[str],
        labels: list[int],
        model_type: str = "random_forest",
    ) -> dict[str, Any]:
        """Train a model for an endpoint.
        
        Args:
            endpoint: ADMET endpoint
            smiles_list: Training SMILES
            labels: Training labels
            model_type: Model type
            
        Returns:
            Training results
        """
        model = ADMETModel(endpoint=endpoint, model_type=model_type)
        results = model.train(smiles_list, labels)
        
        self.models[endpoint] = model
        
        # Save if directory configured
        if self.model_dir:
            model.save(self.model_dir / f"{endpoint}.pkl")
        
        return results
    
    def predict_single(self, endpoint: str, mol_props: dict) -> float | None:
        """Predict for a single endpoint."""
        model = self.models.get(endpoint)
        if model is None:
            return None
        return model.predict_proba(mol_props)
    
    def predict_all(self, mol_props: dict) -> dict[str, float]:
        """Predict all endpoints."""
        results = {}
        for endpoint, model in self.models.items():
            prob = model.predict_proba(mol_props)
            if prob is not None:
                results[endpoint] = prob
        return results
    
    def get_available_endpoints(self) -> list[str]:
        """Get list of available trained endpoints."""
        return list(self.models.keys())
    
    def get_model_info(self) -> dict[str, Any]:
        """Get information about all loaded models."""
        info = {}
        for endpoint, model in self.models.items():
            info[endpoint] = {
                "model_type": model.model_type,
                "is_fitted": model.is_fitted,
                "training_history": model.training_history,
            }
        return info


def create_sample_training_data() -> dict[str, tuple[list[str], list[int]]]:
    """Create sample training data for testing (placeholder).
    
    In production, this should be replaced with real data from:
    - ChEMBL bioactivity data
    - PubChem assays
    - Literature curated datasets
    - Public ADMET databases (e.g., ADMETlab, admetSAR)
    
    Returns:
        Dictionary mapping endpoint to (SMILES, labels)
    """
    # This is a placeholder - real implementation would load from data files
    return {}


def train_models_from_data(
    data: dict[str, tuple[list[str], list[int]]],
    model_dir: str | Path,
    model_type: str = "random_forest",
) -> dict[str, Any]:
    """Train all models from data.
    
    Args:
        data: Dictionary mapping endpoint to (SMILES, labels)
        model_dir: Directory to save models
        model_type: Model type to use
        
    Returns:
        Training results for all endpoints
    """
    manager = ADMETModelManager(model_dir)
    results = {}
    
    for endpoint, (smiles, labels) in data.items():
        try:
            logger.info("Training model for %s...", endpoint)
            result = manager.train_model(endpoint, smiles, labels, model_type)
            results[endpoint] = result
        except Exception as e:
            logger.error("Failed to train %s: %s", endpoint, e)
            results[endpoint] = {"error": str(e)}
    
    return results