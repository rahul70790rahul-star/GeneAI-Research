"""ML engine for biomarker discovery."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import (
    SelectFromModel,
    SelectKBest,
    f_classif,
    mutual_info_classif,
)
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
from sklearn.svm import SVC

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


@dataclass
class BiomarkerCandidate:
    """Biomarker candidate with scoring."""
    gene_symbol: str
    feature_importance: float
    p_value: float
    fold_change: float
    auc_score: float
    cv_auc_mean: float
    cv_auc_std: float
    expression_stats: dict[str, float]
    biomarker_type: str  # diagnostic, prognostic, therapeutic
    confidence: str  # high, medium, low
    validation_status: str  # research, validated, clinical


@dataclass
class BiomarkerResult:
    """Complete biomarker discovery result."""
    candidates: list[BiomarkerCandidate]
    best_model: str
    best_model_auc: float
    roc_curves: dict[str, dict[str, list[float]]]
    feature_ranking: list[dict[str, Any]]
    cross_validation: dict[str, Any]
    dataset_info: dict[str, Any]
    warnings: list[str]


class BiomarkerDiscoveryEngine:
    """ML-based biomarker discovery engine."""
    
    def __init__(
        self,
        test_size: float = 0.2,
        cv_folds: int = 5,
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        self.test_size = test_size
        self.cv_folds = cv_folds
        self.random_state = random_state
        self.n_jobs = n_jobs
        
        # Define models
        self.models = {
            "RandomForest": RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=random_state,
                n_jobs=n_jobs,
                class_weight="balanced",
            ),
            "GradientBoosting": GradientBoostingClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                random_state=random_state,
            ),
            "LogisticRegression": LogisticRegression(
                C=1.0,
                penalty="l2",
                solver="lbfgs",
                max_iter=1000,
                random_state=random_state,
                class_weight="balanced",
                n_jobs=n_jobs,
            ),
            "SVM": SVC(
                C=1.0,
                kernel="rbf",
                probability=True,
                random_state=random_state,
                class_weight="balanced",
            ),
        }

        if XGBOOST_AVAILABLE:
            self.models["XGBoost"] = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
                eval_metric="auc",
                n_jobs=n_jobs,
                verbosity=0,
            )

        if LIGHTGBM_AVAILABLE:
            self.models["LightGBM"] = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                num_leaves=31,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
                class_weight="balanced",
                n_jobs=n_jobs,
                verbosity=-1,
            )
    
    def validate_dataset(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        min_samples_per_class: int = 5,
        max_missing_ratio: float = 0.3,
    ) -> tuple[pd.DataFrame, pd.Series, list[str]]:
        """Validate and clean dataset."""
        warnings_list = []
        
        # Check for missing values
        missing_ratio = X.isnull().sum() / len(X)
        high_missing = missing_ratio[missing_ratio > max_missing_ratio].index.tolist()
        if high_missing:
            warnings_list.append(f"Dropping {len(high_missing)} features with >{max_missing_ratio*100}% missing values")
            X = X.drop(columns=high_missing)
        
        # Impute remaining missing values
        if X.isnull().any().any():
            X = X.fillna(X.median())
            warnings_list.append("Imputed missing values with median")
        
        # Check class balance
        class_counts = y.value_counts()
        if len(class_counts) < 2:
            raise ValueError("Target must have at least 2 classes")
        
        min_class = class_counts.min()
        if min_class < min_samples_per_class:
            warnings_list.append(f"Minority class has only {min_class} samples (recommended: {min_samples_per_class}+)")
        
        # Remove zero-variance features
        zero_var = X.columns[X.var() == 0].tolist()
        if zero_var:
            X = X.drop(columns=zero_var)
            warnings_list.append(f"Removed {len(zero_var)} zero-variance features")
        
        # Check for duplicate samples
        dup_rows = X.duplicated().sum()
        if dup_rows > 0:
            X = X.drop_duplicates()
            y = y.loc[X.index]
            warnings_list.append(f"Removed {dup_rows} duplicate samples")
        
        return X, y, warnings_list
    
    def select_features(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        method: str = "mutual_info",
        k: int = 50,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Select top features."""
        if method == "mutual_info":
            selector = SelectKBest(mutual_info_classif, k=min(k, X.shape[1]))
        elif method == "f_classif":
            selector = SelectKBest(f_classif, k=min(k, X.shape[1]))
        elif method == "model_based":
            selector = SelectFromModel(
                RandomForestClassifier(n_estimators=100, random_state=self.random_state),
                threshold="median",
            )
        else:
            raise ValueError(f"Unknown feature selection method: {method}")
        
        X_selected = selector.fit_transform(X, y)
        selected_features = X.columns[selector.get_support()].tolist()
        
        return pd.DataFrame(X_selected, columns=selected_features, index=X.index), selected_features
    
    def train_and_evaluate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        feature_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Train all models and evaluate with cross-validation."""
        results = {}
        
        # Scale features for SVM and Logistic Regression
        scaler = StandardScaler()
        X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns, index=X.index)
        
        cv = StratifiedKFold(n_splits=self.cv_folds, shuffle=True, random_state=self.random_state)
        
        for name, model in self.models.items():
            # Use scaled data for SVM and LR
            X_model = X_scaled if name in ("SVM", "LogisticRegression") else X
            
            try:
                # Cross-validation
                cv_scores = cross_val_score(
                    model, X_model, y, cv=cv, scoring="roc_auc", n_jobs=self.n_jobs
                )
                
                # Train on full data for feature importance
                model.fit(X_model, y)
                
                # Get feature importance
                if hasattr(model, "feature_importances_"):
                    importance = model.feature_importances_
                elif hasattr(model, "coef_"):
                    importance = np.abs(model.coef_[0])
                else:
                    importance = np.zeros(X.shape[1])
                
                feature_importance = dict(zip(X.columns, importance))
                
                results[name] = {
                    "model": model,
                    "cv_auc_mean": cv_scores.mean(),
                    "cv_auc_std": cv_scores.std(),
                    "cv_scores": cv_scores.tolist(),
                    "feature_importance": feature_importance,
                    "scaler": scaler if name in ("SVM", "LogisticRegression") else None,
                }
                
            except Exception as e:
                logger.warning("Model %s failed: %s", name, e)
                results[name] = {"error": str(e)}
        
        return results
    
    def get_roc_curves(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        models: dict[str, Any],
    ) -> dict[str, dict[str, list[float]]]:
        """Compute ROC curves for all models."""
        scaler = StandardScaler()
        X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns, index=X.index)
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state, stratify=y
        )
        X_train_scaled, X_test_scaled = train_test_split(
            X_scaled, test_size=self.test_size, random_state=self.random_state, stratify=y
        )
        
        roc_curves = {}
        
        for name, result in models.items():
            if "error" in result:
                continue
            
            model = result["model"]
            X_train_model = X_train_scaled if name in ("SVM", "LogisticRegression") else X_train
            X_test_model = X_test_scaled if name in ("SVM", "LogisticRegression") else X_test
            
            try:
                y_proba = model.predict_proba(X_test_model)[:, 1]
                fpr, tpr, thresholds = roc_curve(y_test, y_proba)
                roc_auc = auc(fpr, tpr)
                
                roc_curves[name] = {
                    "fpr": fpr.tolist(),
                    "tpr": tpr.tolist(),
                    "thresholds": thresholds.tolist(),
                    "auc": roc_auc,
                }
            except Exception as e:
                logger.warning("ROC curve for %s failed: %s", name, e)
        
        return roc_curves
    
    def rank_biomarkers(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        models: dict[str, Any],
        feature_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank biomarker candidates by multiple criteria."""
        # Aggregate feature importance across models
        importance_dict: dict[str, list[float]] = {}
        
        for name, result in models.items():
            if "error" in result:
                continue
            for feat, imp in result["feature_importance"].items():
                importance_dict.setdefault(feat, []).append(imp)
        
        # Compute statistics
        ranking = []
        for feat, imps in importance_dict.items():
            ranking.append({
                "gene": feat,
                "mean_importance": np.mean(imps),
                "std_importance": np.std(imps),
                "median_importance": np.median(imps),
                "max_importance": np.max(imps),
                "models_agreeing": len(imps),
            })
        
        # Sort by mean importance
        ranking.sort(key=lambda x: x["mean_importance"], reverse=True)
        
        return ranking
    
    def analyze_differential_expression(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        class_labels: tuple = (0, 1),
    ) -> dict[str, dict[str, float]]:
        """Analyze differential expression between classes."""
        from scipy import stats
        
        class_0 = X[y == class_labels[0]]
        class_1 = X[y == class_labels[1]]
        
        de_results = {}
        
        for gene in X.columns:
            vals_0 = class_0[gene].dropna()
            vals_1 = class_1[gene].dropna()
            
            if len(vals_0) < 3 or len(vals_1) < 3:
                continue
            
            # T-test
            t_stat, p_val = stats.ttest_ind(vals_1, vals_0, equal_var=False)
            
            # Fold change (log2)
            mean_0 = vals_0.mean()
            mean_1 = vals_1.mean()
            
            if mean_0 > 0:
                fold_change = np.log2((mean_1 + 1e-10) / (mean_0 + 1e-10))
            else:
                fold_change = np.log2(mean_1 + 1e-10) - np.log2(mean_0 + 1e-10) if mean_0 > 0 else 0
            
            de_results[gene] = {
                "fold_change": fold_change,
                "log2_fold_change": fold_change,
                "p_value": p_val,
                "mean_class_0": mean_0,
                "mean_class_1": mean_1,
                "t_statistic": t_stat,
            }
        
        return de_results
    
    def run_discovery(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        feature_selection: str = "mutual_info",
        n_features: int = 50,
        biomarker_type: str = "diagnostic",
    ) -> BiomarkerResult:
        """Run complete biomarker discovery pipeline."""
        # Validate dataset
        X_clean, y_clean, val_warnings = self.validate_dataset(X, y)
        
        if X_clean.shape[1] == 0:
            raise ValueError("No valid features after cleaning")
        
        # Feature selection
        X_selected, selected_features = self.select_features(
            X_clean, y_clean, method=feature_selection, k=n_features
        )
        
        # Train and evaluate models
        models = self.train_and_evaluate(X_selected, y_clean, selected_features)
        
        # Find best model
        valid_models = {k: v for k, v in models.items() if "error" not in v}
        if not valid_models:
            raise RuntimeError("All models failed")
        
        best_model_name = max(valid_models.keys(), key=lambda k: valid_models[k]["cv_auc_mean"])
        best_model_result = valid_models[best_model_name]
        
        # ROC curves
        roc_curves = self.get_roc_curves(X_selected, y_clean, valid_models)
        
        # Feature ranking
        ranking = self.rank_biomarkers(X_selected, y_clean, valid_models, selected_features)
        
        # Differential expression
        de_results = self.analyze_differential_expression(X_clean, y_clean)
        
        # Build biomarker candidates
        candidates = []
        for rank_item in ranking[:30]:  # Top 30
            gene = rank_item["gene"]
            
            de = de_results.get(gene, {})
            p_val = de.get("p_value", 1.0)
            fold_change = de.get("fold_change", 0.0)
            
            # Get AUC for this gene alone (univariate)
            try:
                from sklearn.model_selection import cross_val_score
                from sklearn.linear_model import LogisticRegression
                X_gene = X_clean[[gene]].fillna(X_clean[gene].median())
                clf = LogisticRegression(random_state=self.random_state, max_iter=1000)
                cv_auc = cross_val_score(clf, X_gene, y_clean, cv=self.cv_folds, scoring="roc_auc").mean()
            except Exception:
                cv_auc = 0.5
            
            # Determine confidence
            if rank_item["mean_importance"] > 0.1 and p_val < 0.05 and cv_auc > 0.7:
                confidence = "high"
            elif rank_item["mean_importance"] > 0.05 and p_val < 0.1 and cv_auc > 0.65:
                confidence = "medium"
            else:
                confidence = "low"
            
            candidates.append(BiomarkerCandidate(
                gene_symbol=gene,
                feature_importance=rank_item["mean_importance"],
                p_value=p_val,
                fold_change=fold_change,
                auc_score=roc_curves.get(best_model_name, {}).get("auc", 0.5),
                cv_auc_mean=cv_auc,
                cv_auc_std=0.0,  # Would need per-gene CV
                expression_stats={
                    "mean_class_0": de.get("mean_class_0", 0),
                    "mean_class_1": de.get("mean_class_1", 0),
                    "fold_change": fold_change,
                },
                biomarker_type=biomarker_type,
                confidence=confidence,
                validation_status="research",  # Default to research
            ))
        
        # Cross-validation summary
        cv_summary = {}
        for name, result in valid_models.items():
            cv_summary[name] = {
                "mean_auc": result["cv_auc_mean"],
                "std_auc": result["cv_auc_std"],
                "scores": result["cv_scores"],
            }
        
        return BiomarkerResult(
            candidates=candidates,
            best_model=best_model_name,
            best_model_auc=best_model_result["cv_auc_mean"],
            roc_curves=roc_curves,
            feature_ranking=ranking,
            cross_validation=cv_summary,
            dataset_info={
                "n_samples": len(y_clean),
                "n_features_original": X.shape[1],
                "n_features_selected": len(selected_features),
                "class_distribution": y_clean.value_counts().to_dict(),
                "feature_selection_method": feature_selection,
            },
            warnings=val_warnings,
        )


def run_biomarker_discovery(
    X: pd.DataFrame,
    y: pd.Series,
    **kwargs: Any,
) -> BiomarkerResult:
    """Convenience function for biomarker discovery."""
    engine = BiomarkerDiscoveryEngine()
    return engine.run_discovery(X, y, **kwargs)


def compare_biomarker_sets(
    results: list[BiomarkerResult],
    names: list[str],
) -> dict[str, Any]:
    """Compare multiple biomarker discovery results."""
    if len(results) != len(names):
        raise ValueError("Results and names must have same length")
    
    comparison = {}
    
    # Compare candidate overlap
    all_genes = set()
    for r in results:
        all_genes.update(c.gene_symbol for c in r.candidates)
    
    gene_matrix = {}
    for name, result in zip(names, results):
        gene_matrix[name] = {c.gene_symbol: c for c in result.candidates}
    
    # Find common and unique biomarkers
    common = set()
    for gene in all_genes:
        if all(gene in gene_matrix[name] for name in names):
            common.add(gene)
    
    comparison["common_biomarkers"] = list(common)
    comparison["unique_per_dataset"] = {}
    
    for name in names:
        unique = set(gene_matrix[name].keys()) - common
        comparison["unique_per_dataset"][name] = list(unique)
    
    # Model performance comparison
    comparison["model_performance"] = {
        name: {
            "best_model": r.best_model,
            "best_auc": r.best_model_auc,
            "n_candidates": len(r.candidates),
        }
        for name, r in zip(names, results)
    }
    
    return comparison