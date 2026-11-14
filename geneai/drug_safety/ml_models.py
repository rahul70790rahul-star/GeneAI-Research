"""ML models for drug toxicity prediction."""
from __future__ import annotations

import logging
import pickle
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    auc,
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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

warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

# Toxicity endpoints to predict
TOXICITY_ENDPOINTS = [
    # Hepatotoxicity
    "hepatotoxicity",
    "dili",  # Drug-induced liver injury
    "cholestasis",
    "steatosis",
    # Cardiotoxicity
    "cardiotoxicity_herg",
    "cardiotoxicity_arrhythmia",
    "cardiotoxicity_heart_failure",
    # Nephrotoxicity
    "nephrotoxicity",
    "aki",  # Acute kidney injury
    # Neurotoxicity
    "neurotoxicity",
    "seizure",
    # Genotoxicity/Carcinogenicity
    "ames_mutagenicity",
    "carcinogenicity",
    "clastogenicity",
    # Other
    "skin_sensitization",
    "eye_irritation",
    "respiratory_toxicity",
    "reproductive_toxicity",
    "developmental_toxicity",
]

# Default model directory
MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


@dataclass
class ToxicityModel:
    """A trained toxicity prediction model."""
    endpoint: str
    model_type: str
    model: Any
    scaler: StandardScaler | None
    feature_names: list[str]
    cv_auc: float
    cv_auc_std: float
    train_auc: float
    params: dict[str, Any]
    version: str = "1.0"
    training_samples: int = 0
    training_date: str = ""


@dataclass
class ToxicityPrediction:
    """Prediction result for a toxicity endpoint."""
    endpoint: str
    probability: float
    prediction: str  # "Toxic" or "Non-toxic"
    confidence: str  # "high", "medium", "low"
    model_used: str
    details: dict[str, Any] = field(default_factory=dict)


class ToxicityModelManager:
    """Manage multiple toxicity prediction models."""
    
    def __init__(self, model_dir: Path | str = MODEL_DIR):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.models: dict[str, ToxicityModel] = {}
        self._load_all_models()
    
    def _load_all_models(self) -> None:
        """Load all available models from disk."""
        for model_file in self.model_dir.glob("toxicity_*.pkl"):
            try:
                with open(model_file, "rb") as f:
                    model = pickle.load(f)
                if isinstance(model, ToxicityModel):
                    self.models[model.endpoint] = model
                    logger.info("Loaded model for %s (%s)", model.endpoint, model.model_type)
            except Exception as e:
                logger.warning("Failed to load %s: %s", model_file, e)
    
    def train_model(
        self,
        endpoint: str,
        X: pd.DataFrame,
        y: pd.Series,
        model_type: str = "RandomForest",
        optimize: bool = True,
        cv_folds: int = 5,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> ToxicityModel:
        """Train a model for a specific toxicity endpoint."""
        logger.info("Training %s model for %s", model_type, endpoint)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Define model
        if model_type == "RandomForest":
            base_model = RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=random_state,
                class_weight="balanced",
                n_jobs=-1,
            )
            param_grid = {
                "n_estimators": [100, 200, 300],
                "max_depth": [5, 10, 15, None],
                "min_samples_split": [2, 5, 10],
            }
        elif model_type == "GradientBoosting":
            base_model = GradientBoostingClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                random_state=random_state,
            )
            param_grid = {
                "n_estimators": [100, 200],
                "max_depth": [3, 5, 7],
                "learning_rate": [0.05, 0.1, 0.15],
            }
        elif model_type == "XGBoost" and XGBOOST_AVAILABLE:
            base_model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
                eval_metric="auc",
                n_jobs=-1,
                verbosity=0,
            )
            param_grid = {
                "n_estimators": [100, 200, 300],
                "max_depth": [4, 6, 8],
                "learning_rate": [0.05, 0.1, 0.15],
                "subsample": [0.7, 0.8, 0.9],
            }
        elif model_type == "LightGBM" and LIGHTGBM_AVAILABLE:
            base_model = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                num_leaves=31,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
                class_weight="balanced",
                n_jobs=-1,
                verbosity=-1,
            )
            param_grid = {
                "n_estimators": [100, 200, 300],
                "max_depth": [4, 6, 8],
                "learning_rate": [0.05, 0.1, 0.15],
                "num_leaves": [15, 31, 63],
            }
        elif model_type == "LogisticRegression":
            base_model = LogisticRegression(
                C=1.0,
                penalty="l2",
                solver="lbfgs",
                max_iter=1000,
                random_state=random_state,
                class_weight="balanced",
                n_jobs=-1,
            )
            param_grid = {
                "C": [0.1, 1.0, 10.0],
                "penalty": ["l2"],
            }
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Hyperparameter optimization
        best_params = base_model.get_params()
        if optimize:
            cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
            grid_search = GridSearchCV(
                base_model, param_grid, cv=cv, scoring="roc_auc", n_jobs=-1, verbose=0
            )
            grid_search.fit(X_train_scaled, y_train)
            best_model = grid_search.best_estimator_
            best_params = grid_search.best_params_
            logger.info("Best params for %s: %s", endpoint, best_params)
        else:
            best_model = base_model
            best_model.fit(X_train_scaled, y_train)
        
        # Cross-validation
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
        cv_scores = cross_val_score(best_model, X_train_scaled, y_train, cv=cv, scoring="roc_auc", n_jobs=-1)
        
        # Test set evaluation
        y_pred_proba = best_model.predict_proba(X_test_scaled)[:, 1]
        test_auc = roc_auc_score(y_test, y_pred_proba)
        
        # Create model object
        model_obj = ToxicityModel(
            endpoint=endpoint,
            model_type=model_type,
            model=best_model,
            scaler=scaler,
            feature_names=X.columns.tolist(),
            cv_auc=cv_scores.mean(),
            cv_auc_std=cv_scores.std(),
            train_auc=test_auc,
            params=best_params,
            training_samples=len(X_train),
            training_date=pd.Timestamp.now().isoformat(),
        )
        
        # Save model
        model_path = self.model_dir / f"toxicity_{endpoint}_{model_type}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model_obj, f)
        
        self.models[endpoint] = model_obj
        logger.info("Saved model for %s to %s (CV AUC: %.4f±%.4f)", endpoint, model_path, cv_scores.mean(), cv_scores.std())
        
        return model_obj
    
    def predict(
        self,
        X: pd.DataFrame,
        endpoints: list[str] | None = None,
    ) -> list[ToxicityPrediction]:
        """Predict toxicity for multiple endpoints."""
        if endpoints is None:
            endpoints = list(self.models.keys())
        
        predictions = []
        for endpoint in endpoints:
            if endpoint not in self.models:
                predictions.append(ToxicityPrediction(
                    endpoint=endpoint,
                    probability=0.5,
                    prediction="Unknown",
                    confidence="low",
                    model_used="none",
                    details={"error": "Model not trained"},
                ))
                continue
            
            model_obj = self.models[endpoint]
            
            # Ensure features match
            missing_features = set(model_obj.feature_names) - set(X.columns)
            extra_features = set(X.columns) - set(model_obj.feature_names)
            if missing_features:
                for feat in missing_features:
                    X[feat] = 0.0
            
            X_ordered = X[model_obj.feature_names]
            
            # Scale
            X_scaled = model_obj.scaler.transform(X_ordered)
            
            # Predict
            try:
                proba = model_obj.model.predict_proba(X_scaled)[:, 1]
                pred = model_obj.model.predict(X_scaled)
                
                for i in range(len(X)):
                    p = float(proba[i])
                    predictions.append(ToxicityPrediction(
                        endpoint=endpoint,
                        probability=p,
                        prediction="Toxic" if pred[i] == 1 else "Non-toxic",
                        confidence=self._get_confidence(p, model_obj.cv_auc),
                        model_used=f"{model_obj.model_type}_v{model_obj.version}",
                        details={
                            "cv_auc": model_obj.cv_auc,
                            "cv_auc_std": model_obj.cv_auc_std,
                        },
                    ))
            except Exception as e:
                logger.warning("Prediction failed for %s: %s", endpoint, e)
                predictions.append(ToxicityPrediction(
                    endpoint=endpoint,
                    probability=0.5,
                    prediction="Error",
                    confidence="low",
                    model_used=model_obj.model_type,
                    details={"error": str(e)},
                ))
        
        return predictions
    
    def _get_confidence(self, probability: float, cv_auc: float) -> str:
        """Determine prediction confidence."""
        # High confidence: probability far from 0.5 AND good model performance
        prob_conf = abs(probability - 0.5) * 2  # 0 to 1
        model_conf = cv_auc  # 0.5 to 1.0
        
        combined = (prob_conf + model_conf) / 2
        
        if combined >= 0.75:
            return "high"
        elif combined >= 0.55:
            return "medium"
        else:
            return "low"
    
    def get_available_endpoints(self) -> list[str]:
        """Get list of endpoints with trained models."""
        return list(self.models.keys())
    
    def get_model_info(self, endpoint: str) -> dict[str, Any] | None:
        """Get model metadata."""
        if endpoint not in self.models:
            return None
        m = self.models[endpoint]
        return {
            "endpoint": m.endpoint,
            "model_type": m.model_type,
            "cv_auc": m.cv_auc,
            "cv_auc_std": m.cv_auc_std,
            "train_auc": m.train_auc,
            "feature_count": len(m.feature_names),
            "training_samples": m.training_samples,
            "training_date": m.training_date,
            "params": m.params,
        }


def create_synthetic_toxicity_data(n_samples: int = 1000, n_features: int = 50) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Create synthetic toxicity data for testing (when real data unavailable)."""
    np.random.seed(42)
    
    # Generate molecular descriptors
    feature_names = [
        f"desc_{i}" for i in range(n_features)
    ]
    
    # Base features
    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=feature_names,
    )
    
    # Add some structure to make it learnable
    # Correlate some features with toxicity
    for endpoint in TOXICITY_ENDPOINTS[:5]:  # Just first 5 for demo
        # Create a synthetic target based on a subset of features
        toxic_features = feature_names[:10]
        y_score = X[toxic_features].sum(axis=1) + np.random.randn(n_samples) * 0.5
        y = (y_score > y_score.median()).astype(int)
        
        yield endpoint, X, pd.Series(y, name=endpoint)


# Pretrained model loading (placeholder for future real models)
def load_pretrained_models(model_dir: Path | str = MODEL_DIR) -> ToxicityModelManager:
    """Load or create a model manager with pretrained models."""
    manager = ToxicityModelManager(model_dir)
    
    # If no models exist, create placeholder info
    if not manager.models:
        logger.info("No pretrained models found. Models need to be trained on real toxicity data.")
        logger.info("Available endpoints: %s", TOXICITY_ENDPOINTS)
    
    return manager