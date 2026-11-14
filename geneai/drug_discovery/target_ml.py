"""Optional grouped-cross-validation models for documented target-label datasets."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from geneai.drug_discovery.target_identification import ML_FEATURE_COLUMNS

_GENE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
MODEL_TYPES = ("Logistic Regression", "Random Forest", "Gradient Boosting", "XGBoost", "LightGBM")


def train_evaluate_target_model(
    dataset: pd.DataFrame,
    *,
    model_type: str,
    dataset_source: str,
    dataset_license: str,
) -> dict[str, Any]:
    """Train only on caller-supplied binary labels with gene-grouped CV.

    The function deliberately has no built-in training labels or fabricated
    biological examples. All rows from the same gene remain in a single fold.
    """
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Model type must be one of: {', '.join(MODEL_TYPES)}.")
    if not isinstance(dataset, pd.DataFrame) or dataset.empty:
        raise ValueError("Upload a non-empty CSV of documented, externally labeled target examples.")
    required = {"gene_symbol", "label"}
    if not required.issubset(dataset.columns):
        raise ValueError("Training CSV must include gene_symbol and binary label columns.")
    source = " ".join(str(dataset_source or "").split())
    license_text = " ".join(str(dataset_license or "").split())
    if len(source) < 8 or len(source) > 500:
        raise ValueError("Provide the dataset publication, source URL, or repository (8–500 characters).")
    if len(license_text) < 3 or len(license_text) > 200:
        raise ValueError("Provide the dataset license/access conditions (3–200 characters).")

    frame = dataset.copy()
    frame["gene_symbol"] = frame["gene_symbol"].astype(str).str.strip().str.upper()
    if frame["gene_symbol"].eq("").any() or not frame["gene_symbol"].map(lambda value: bool(_GENE.fullmatch(value))).all():
        raise ValueError("Each row must contain a valid gene_symbol for grouped validation.")
    labels = pd.to_numeric(frame["label"], errors="coerce")
    if labels.isna().any() or not set(labels.unique()).issubset({0, 1}):
        raise ValueError("Labels must be complete binary integers: 0 or 1.")
    frame["label"] = labels.astype(int)
    per_gene_labels = frame.groupby("gene_symbol")["label"].nunique()
    if (per_gene_labels > 1).any():
        raise ValueError("Rows for the same gene have conflicting labels; resolve the source labels before training.")
    if len(frame) < 10:
        raise ValueError("At least 10 documented rows are required for grouped cross-validation.")
    group_labels = frame.drop_duplicates("gene_symbol").groupby("label")["gene_symbol"].nunique()
    if not {0, 1}.issubset(set(group_labels.index)) or min(int(group_labels.get(0, 0)), int(group_labels.get(1, 0))) < 2:
        raise ValueError("Need at least two distinct gene groups for each label to evaluate generalization.")

    feature_columns = [column for column in ML_FEATURE_COLUMNS if column in frame.columns]
    numeric = frame[feature_columns].apply(pd.to_numeric, errors="coerce") if feature_columns else pd.DataFrame(index=frame.index)
    usable = [column for column in numeric if not numeric[column].isna().all()]
    if len(usable) < 2:
        raise ValueError("Provide at least two non-empty numeric target feature columns from the dashboard feature set.")
    X = numeric[usable].replace([np.inf, -np.inf], np.nan)
    y = frame["label"].to_numpy(dtype=int)
    groups = frame["gene_symbol"].to_numpy()

    from sklearn import __version__ as sklearn_version
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    groups_per_label = frame.drop_duplicates("gene_symbol").groupby("label")["gene_symbol"].nunique()
    folds = min(5, int(groups_per_label.min()))
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    cv_splits = list(splitter.split(X, y, groups=groups))
    fold_group_isolation = [
        len(set(groups[train_idx]) & set(groups[test_idx])) == 0
        for train_idx, test_idx in cv_splits
    ]
    if not all(fold_group_isolation):
        raise RuntimeError("Grouped cross-validation split failed the gene-isolation check.")

    if model_type == "Logistic Regression":
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
        ])
    elif model_type == "Random Forest":
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("classifier", RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample", random_state=42, n_jobs=1)),
        ])
    elif model_type == "Gradient Boosting":
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("classifier", GradientBoostingClassifier(random_state=42)),
        ])
    elif model_type == "XGBoost":
        try:
            import xgboost as xgb
        except ImportError:
            raise ImportError("XGBoost is not installed. Install with: pip install xgboost")
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("classifier", xgb.XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, n_jobs=1, eval_metric="auc", verbosity=0
            )),
        ])
    elif model_type == "LightGBM":
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("LightGBM is not installed. Install with: pip install lightgbm")
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("classifier", lgb.LGBMClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                num_leaves=31, subsample=0.8, colsample_bytree=0.8,
                random_state=42, n_jobs=1, verbosity=-1, class_weight="balanced"
            )),
        ])
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    out_of_fold_scores = cross_val_predict(estimator, X, y, cv=cv_splits, method="predict_proba", n_jobs=1)[:, 1]
    predicted = (out_of_fold_scores >= 0.5).astype(int)
    metrics = {
        "accuracy": round(float(accuracy_score(y, predicted)), 4),
        "precision": round(float(precision_score(y, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y, predicted, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, out_of_fold_scores)), 4),
        "evaluation": "out-of-fold stratified cross-validation grouped by gene_symbol",
        "fold_count": folds,
        "gene_group_isolation_verified": all(fold_group_isolation),
    }
    estimator.fit(X, y)
    classifier = estimator.named_steps["classifier"]
    if hasattr(classifier, "feature_importances_"):
        importance_values = classifier.feature_importances_
        importance_kind = "tree impurity importance; descriptive, not causal"
    else:
        importance_values = np.abs(classifier.coef_[0])
        importance_kind = "absolute standardized logistic coefficient; descriptive, not causal"
    importances = [
        {"feature": name, "importance": round(float(value), 6), "method": importance_kind}
        for name, value in sorted(zip(usable, importance_values), key=lambda pair: -pair[1])
    ]
    return {
        "estimator": estimator,
        "model_type": model_type,
        "model_version": f"scikit-learn {sklearn_version}",
        "feature_columns": usable,
        "evaluation_metrics": metrics,
        "feature_importance": importances,
        "row_count": len(frame),
        "gene_group_count": int(frame["gene_symbol"].nunique()),
        "dataset_source": source,
        "dataset_license": license_text,
        "label_definition": "User-supplied binary label (0/1); verify the source's definition before interpretation.",
        "limitations": [
            "This model was trained only on the user-supplied labeled dataset; the application contains no built-in or fabricated biological training set.",
            "Cross-validation holds out genes to reduce gene-level leakage but does not eliminate dataset, publication, class, or assay bias.",
            "Model outputs are computational research hypotheses, not probabilities of clinical success, validated druggability, or treatment recommendations.",
            "Feature importance describes this fitted model and dataset; it is not causal explanation.",
        ],
    }


def score_target_rows(
    model_bundle: dict[str, Any],
    feature_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply a fitted model to the current target feature rows in memory."""
    estimator = model_bundle.get("estimator")
    columns = model_bundle.get("feature_columns")
    if estimator is None or not isinstance(columns, list) or not columns:
        raise ValueError("Train a validated target model before scoring current targets.")
    frame = pd.DataFrame(feature_rows)
    for column in columns:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    probabilities = estimator.predict_proba(frame[columns])[:, 1]
    predictions = estimator.predict(frame[columns])
    return [
        {
            "gene_symbol": row.get("gene_symbol"),
            "model_predicted_label": int(predictions[index]),
            "positive_class_score": round(float(probabilities[index]), 4),
            "score_interpretation": "Uncalibrated model score for the user-provided label definition; not a clinical probability.",
        }
        for index, row in enumerate(feature_rows)
    ]
