"""ADMET prediction tools for the Autonomous Bioinformatics Agent.

Predictions are computed locally by :class:`ADMETPredictionEngine` from RDKit
molecular descriptors (plus optional ML models when available). Every endpoint
keeps its value, probability, confidence and provenance so a downstream consumer
can distinguish a computed estimate from a measured value.
"""
from __future__ import annotations

import logging
from typing import Any

from geneai.autonomous_agent.tools import Tool, ToolParameter, ToolSpec

logger = logging.getLogger(__name__)

_CATEGORY_FLAGS = {
    "absorption": "predict_absorption",
    "distribution": "predict_distribution",
    "metabolism": "predict_metabolism",
    "excretion": "predict_excretion",
    "toxicity": "predict_toxicity",
}


def predict_admet_properties(
    smiles: str,
    name: str | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Compute ADMET estimates for one molecule."""
    from geneai.admet_prediction.admet_engine import ADMETPredictionEngine

    smiles = str(smiles or "").strip()
    if not smiles:
        return {"error": "No SMILES provided"}

    engine = ADMETPredictionEngine()
    result = engine.predict(smiles)
    if result.warnings and not result.molecular_properties:
        return {
            "smiles": smiles,
            "name": name or "Unknown",
            "status": "invalid",
            "errors": result.warnings,
        }

    allowed = set(categories) if categories else set(_CATEGORY_FLAGS)
    properties: dict[str, dict[str, Any]] = {}
    details: list[dict[str, Any]] = []
    for prediction in result.predictions:
        if prediction.category not in allowed:
            continue
        value = prediction.value
        if value is None:
            value = prediction.probability
        if isinstance(value, (int, float)):
            value = round(float(value), 4)
        properties.setdefault(prediction.category, {})[prediction.endpoint] = value
        details.append(
            {
                "category": prediction.category,
                "endpoint": prediction.endpoint,
                "value": prediction.value,
                "probability": prediction.probability,
                "prediction": prediction.prediction,
                "confidence": prediction.confidence,
                "is_measured": prediction.is_measured,
                "source": prediction.source,
            }
        )

    return {
        "smiles": smiles,
        "name": name or "Unknown",
        "status": "ok",
        "properties": properties,
        "details": details,
        "molecular_properties": result.molecular_properties,
        "summary": result.summary,
        "model_info": {
            **result.model_info,
            "method": "RDKit descriptor heuristics"
            + (" with ML models" if result.model_info.get("used_ml_models") else ""),
            "note": (
                "Computational estimates, not experimental measurements. "
                "Use only for early-stage triage."
            ),
        },
        "warnings": result.warnings,
    }


class ADMETPredictionTool(Tool):
    """Predict ADMET properties for molecules."""

    def __init__(self):
        spec = ToolSpec(
            name="admet_prediction",
            description="Estimate ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) properties for a small molecule",
            category="admet",
            requires_approval=True,
            parameters=[
                ToolParameter("smiles", "string", "SMILES string of molecule", required=True),
                ToolParameter("name", "string", "Optional compound name", required=False),
                ToolParameter("predict_absorption", "boolean", "Predict absorption properties", required=False, default=True),
                ToolParameter("predict_distribution", "boolean", "Predict distribution properties", required=False, default=True),
                ToolParameter("predict_metabolism", "boolean", "Predict metabolism properties", required=False, default=True),
                ToolParameter("predict_excretion", "boolean", "Predict excretion properties", required=False, default=True),
                ToolParameter("predict_toxicity", "boolean", "Predict toxicity", required=False, default=True),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        categories = [
            category
            for category, flag in _CATEGORY_FLAGS.items()
            if kwargs.get(flag, True)
        ]
        return predict_admet_properties(
            kwargs.get("smiles", ""),
            name=kwargs.get("name"),
            categories=categories,
        )


class ADMETBatchTool(Tool):
    """Batch ADMET prediction for multiple molecules."""

    def __init__(self):
        spec = ToolSpec(
            name="admet_batch",
            description="Estimate ADMET properties for multiple molecules",
            category="admet",
            requires_approval=True,
            parameters=[
                ToolParameter("molecules", "array", "List of molecules with SMILES and optional names", required=True),
                ToolParameter("properties", "array", "Categories to predict", required=False, default=["absorption", "distribution", "metabolism", "excretion", "toxicity"]),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        molecules = kwargs.get("molecules", [])
        if not molecules:
            return {"error": "No molecules provided"}

        requested = kwargs.get("properties") or list(_CATEGORY_FLAGS)
        categories = [c for c in requested if c in _CATEGORY_FLAGS]

        results = [
            predict_admet_properties(
                molecule.get("smiles", ""),
                name=molecule.get("name"),
                categories=categories,
            )
            for molecule in molecules
            if molecule.get("smiles")
        ]
        return {
            "compounds_processed": len(results),
            "successful": sum(1 for result in results if result.get("status") == "ok"),
            "results": results,
        }


def register_admet_tools(registry):
    """Register ADMET tools."""
    registry.register(ADMETPredictionTool())
    registry.register(ADMETBatchTool())
