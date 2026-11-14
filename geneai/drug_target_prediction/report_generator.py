"""Report generation for drug-target interaction predictions."""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from geneai.drug_target_prediction.binding_affinity import generate_affinity_report
from geneai.drug_target_prediction.molecular_descriptors import calculate_molecular_descriptors

logger = logging.getLogger(__name__)


def generate_prediction_report_csv(
    predictions: list[dict[str, Any]],
    output_path: str | Path,
    include_descriptors: bool = True,
) -> str:
    """Generate CSV report from prediction results.
    
    Args:
        predictions: List of prediction results
        output_path: Path to output CSV file
        include_descriptors: Whether to include molecular descriptors
        
    Returns:
        Path to generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for pred in predictions:
        row = {
            "drug_identifier": pred.get("drug_identifier", ""),
            "target_identifier": pred.get("target_identifier", ""),
            "drug_smiles": pred.get("drug_smiles", ""),
            "predicted_interaction": pred.get("predicted_interaction", ""),
            "interaction_probability": pred.get("interaction_probability", ""),
            "confidence": pred.get("confidence", ""),
            "success": pred.get("success", True),
            "error": pred.get("error", ""),
            "timestamp": datetime.now().isoformat(),
        }
        
        if include_descriptors and pred.get("drug_smiles"):
            desc = calculate_molecular_descriptors(pred["drug_smiles"])
            for key, value in desc.items():
                row[f"desc_{key}"] = value
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    
    logger.info("Prediction report saved to %s", output_path)
    return str(output_path)


def generate_affinity_report_csv(
    affinity_results: list[dict[str, Any]],
    output_path: str | Path,
) -> str:
    """Generate CSV report from affinity estimation results.
    
    Args:
        affinity_results: List of affinity estimation results
        output_path: Path to output CSV file
        
    Returns:
        Path to generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for result in affinity_results:
        row = {
            "drug_identifier": result.get("drug_identifier", result.get("drug_smiles", "")),
            "target_identifier": result.get("target_identifier", ""),
            "drug_smiles": result.get("drug_smiles", ""),
            "method": result.get("method", ""),
            "estimated_affinity_nm": result.get("estimated_affinity_nm", ""),
            "estimated_pkd": result.get("estimated_pkd", ""),
            "confidence": result.get("confidence", ""),
            "details": json.dumps(result.get("details", {})),
            "timestamp": datetime.now().isoformat(),
        }
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    
    logger.info("Affinity report saved to %s", output_path)
    return str(output_path)


def generate_comprehensive_report_json(
    drug_identifier: str,
    target_list: list[str],
    predictions: list[dict[str, Any]],
    affinity_results: list[dict[str, Any]] | None = None,
    model_info: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate comprehensive JSON report.
    
    Args:
        drug_identifier: Drug identifier
        target_list: List of target identifiers
        predictions: Interaction predictions
        affinity_results: Optional affinity estimates
        model_info: Optional model information
        output_path: Optional path to save JSON
        
    Returns:
        Report dictionary
    """
    # Get drug SMILES from first successful prediction
    drug_smiles = ""
    for pred in predictions:
        if pred.get("success") and pred.get("drug_smiles"):
            drug_smiles = pred["drug_smiles"]
            break
    
    # Molecular descriptors
    descriptors = calculate_molecular_descriptors(drug_smiles) if drug_smiles else {}
    
    report = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "drug_target_interaction_prediction",
            "version": "1.0",
        },
        "drug": {
            "identifier": drug_identifier,
            "smiles": drug_smiles,
            "molecular_descriptors": descriptors,
        },
        "targets": target_list,
        "interaction_predictions": predictions,
        "affinity_estimates": affinity_results or [],
        "model_information": model_info or {},
        "summary": _generate_summary(predictions, affinity_results),
    }
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("Comprehensive report saved to %s", output_path)
    
    return report


def generate_target_profile_report(
    drug_identifier: str,
    predictions: list[dict[str, Any]],
    output_path: str | Path,
    format: str = "csv",
) -> str:
    """Generate target profile report for a drug.
    
    Args:
        drug_identifier: Drug identifier
        predictions: List of predictions for different targets
        output_path: Output file path
        format: Output format ("csv", "json", "tsv")
        
    Returns:
        Path to generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Sort by probability
    sorted_preds = sorted(
        [p for p in predictions if p.get("success")],
        key=lambda x: x.get("interaction_probability", 0),
        reverse=True,
    )
    
    if format == "csv":
        return generate_prediction_report_csv(sorted_preds, output_path)
    
    elif format == "json":
        report = generate_comprehensive_report_json(
            drug_identifier,
            [p.get("target_identifier", "") for p in sorted_preds],
            sorted_preds,
            output_path=output_path,
        )
        return str(output_path)
    
    elif format == "tsv":
        generate_prediction_report_csv(sorted_preds, output_path.with_suffix(".csv"))
        df = pd.read_csv(output_path.with_suffix(".csv"))
        df.to_csv(output_path, sep="\t", index=False)
        output_path.with_suffix(".csv").unlink()
        return str(output_path)
    
    else:
        raise ValueError(f"Unknown format: {format}")


def generate_batch_screening_report(
    drug_list: list[str],
    target_identifier: str,
    predictions: list[dict[str, Any]],
    output_path: str | Path,
    top_n: int = 50,
) -> str:
    """Generate report for batch screening of drugs against a target.
    
    Args:
        drug_list: List of drug identifiers screened
        target_identifier: Target identifier
        predictions: Prediction results
        output_path: Output file path
        top_n: Number of top hits to highlight
        
    Returns:
        Path to generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Sort by probability
    successful = [p for p in predictions if p.get("success")]
    successful.sort(key=lambda x: x.get("interaction_probability", 0), reverse=True)
    
    # Prepare data
    rows = []
    for i, pred in enumerate(successful):
        row = {
            "rank": i + 1,
            "drug_identifier": pred.get("drug_identifier", ""),
            "drug_smiles": pred.get("drug_smiles", ""),
            "interaction_probability": pred.get("interaction_probability", 0),
            "predicted_interaction": "Yes" if pred.get("predicted_interaction") == 1 else "No",
            "confidence": pred.get("confidence", ""),
            "top_hit": "Yes" if i < top_n else "No",
        }
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    
    logger.info("Batch screening report saved to %s", output_path)
    return str(output_path)


def generate_model_performance_report(
    training_history: dict[str, Any],
    feature_importance: list[dict[str, Any]] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate model performance report.
    
    Args:
        training_history: Training history from model
        feature_importance: Optional feature importance
        output_path: Optional output path
        
    Returns:
        Report dictionary
    """
    report = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "model_performance",
        },
        "training_summary": {
            "model_type": training_history.get("model_type", "unknown"),
            "n_samples": training_history.get("n_samples", 0),
            "n_positive": training_history.get("n_positive", 0),
            "n_negative": training_history.get("n_negative", 0),
            "class_balance": training_history.get("n_positive", 0) / max(training_history.get("n_samples", 1), 1),
        },
        "metrics": {
            "train_accuracy": training_history.get("train_accuracy"),
            "train_precision": training_history.get("train_precision"),
            "train_recall": training_history.get("train_recall"),
            "train_f1": training_history.get("train_f1"),
            "train_roc_auc": training_history.get("train_roc_auc"),
            "cv_roc_auc_mean": training_history.get("cv_roc_auc_mean"),
            "cv_roc_auc_std": training_history.get("cv_roc_auc_std"),
        },
        "feature_importance": feature_importance[:50] if feature_importance else [],
        "interpretation": _interpret_metrics(training_history),
    }
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("Model performance report saved to %s", output_path)
    
    return report


def export_predictions_for_external_tools(
    predictions: list[dict[str, Any]],
    output_path: str | Path,
    format: str = "sdf",
) -> str:
    """Export predictions in formats for external tools (SDF, MOL2, etc.).
    
    Args:
        predictions: Prediction results
        output_path: Output file path
        format: Export format ("sdf", "csv_smiles", "tsv_smiles")
        
    Returns:
        Path to generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "csv_smiles":
        # Simple CSV with SMILES and prediction
        rows = []
        for pred in predictions:
            if pred.get("success") and pred.get("drug_smiles"):
                rows.append({
                    "SMILES": pred["drug_smiles"],
                    "ID": pred.get("drug_identifier", ""),
                    "Target": pred.get("target_identifier", ""),
                    "Probability": pred.get("interaction_probability", 0),
                    "Prediction": pred.get("predicted_interaction", ""),
                })
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)
        
    elif format == "tsv_smiles":
        rows = []
        for pred in predictions:
            if pred.get("success") and pred.get("drug_smiles"):
                rows.append({
                    "SMILES": pred["drug_smiles"],
                    "ID": pred.get("drug_identifier", ""),
                    "Target": pred.get("target_identifier", ""),
                    "Probability": pred.get("interaction_probability", 0),
                    "Prediction": pred.get("predicted_interaction", ""),
                })
        df = pd.DataFrame(rows)
        df.to_csv(output_path, sep="\t", index=False)
        
    elif format == "sdf":
        # SDF export requires RDKit
        try:
            from rdkit import Chem
            from rdkit.Chem import SDWriter
            
            writer = SDWriter(str(output_path))
            for pred in predictions:
                if pred.get("success") and pred.get("drug_smiles"):
                    mol = Chem.MolFromSmiles(pred["drug_smiles"])
                    if mol:
                        mol.SetProp("_Name", pred.get("drug_identifier", "Unknown"))
                        mol.SetProp("TARGET", pred.get("target_identifier", ""))
                        mol.SetProp("PREDICTION_PROBABILITY", str(pred.get("interaction_probability", 0)))
                        mol.SetProp("PREDICTED_INTERACTION", str(pred.get("predicted_interaction", "")))
                        mol.SetProp("CONFIDENCE", pred.get("confidence", ""))
                        writer.write(mol)
            writer.close()
        except ImportError:
            logger.warning("RDKit not available for SDF export")
            raise
    
    else:
        raise ValueError(f"Unknown export format: {format}")
    
    logger.info("Exported predictions to %s", output_path)
    return str(output_path)


def _generate_summary(
    predictions: list[dict[str, Any]],
    affinity_results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Generate summary statistics."""
    successful = [p for p in predictions if p.get("success")]
    
    if not successful:
        return {"total_predictions": len(predictions), "successful": 0}
    
    interacting = [p for p in successful if p.get("predicted_interaction") == 1]
    high_conf = [p for p in interacting if p.get("confidence") == "high"]
    
    probs = [p.get("interaction_probability", 0) for p in successful]
    
    summary = {
        "total_predictions": len(predictions),
        "successful": len(successful),
        "predicted_interacting": len(interacting),
        "high_confidence_hits": len(high_conf),
        "mean_probability": sum(probs) / len(probs) if probs else 0,
        "max_probability": max(probs) if probs else 0,
        "min_probability": min(probs) if probs else 0,
    }
    
    if affinity_results:
        valid_aff = [a for a in affinity_results if a.get("estimated_affinity_nm")]
        if valid_aff:
            aff_values = [a["estimated_affinity_nm"] for a in valid_aff]
            summary["affinity_estimates"] = len(valid_aff)
            summary["best_affinity_nm"] = min(aff_values)
            summary["mean_affinity_nm"] = sum(aff_values) / len(aff_values)
    
    return summary


def _interpret_metrics(training_history: dict[str, Any]) -> list[str]:
    """Generate human-readable interpretation of model metrics."""
    interpretations = []
    
    roc_auc = training_history.get("train_roc_auc", 0)
    if roc_auc > 0.9:
        interpretations.append("Excellent discrimination ability (ROC-AUC > 0.9)")
    elif roc_auc > 0.8:
        interpretations.append("Good discrimination ability (ROC-AUC > 0.8)")
    elif roc_auc > 0.7:
        interpretations.append("Fair discrimination ability (ROC-AUC > 0.7)")
    else:
        interpretations.append("Poor discrimination ability (ROC-AUC < 0.7)")
    
    cv_mean = training_history.get("cv_roc_auc_mean", 0)
    cv_std = training_history.get("cv_roc_auc_std", 0)
    if cv_mean > 0:
        if cv_std < 0.05:
            interpretations.append("Model generalizes well (low CV variance)")
        elif cv_std < 0.1:
            interpretations.append("Model shows moderate generalization")
        else:
            interpretations.append("Model may be overfitting (high CV variance)")
    
    n_samples = training_history.get("n_samples", 0)
    if n_samples < 100:
        interpretations.append("Small training set - consider collecting more data")
    elif n_samples < 1000:
        interpretations.append("Moderate training set size")
    else:
        interpretations.append("Large training set - good for robust models")
    
    balance = training_history.get("n_positive", 0) / max(n_samples, 1)
    if balance < 0.1 or balance > 0.9:
        interpretations.append("Highly imbalanced classes - consider resampling")
    
    return interpretations