"""ADMET Scoring - Module 5: Scoring and risk classification."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from geneai.admet_prediction.admet_engine import ADMETPrediction, ADMETResult

logger = logging.getLogger(__name__)

# Scoring weights for different endpoints within each category
CATEGORY_WEIGHTS = {
    "absorption": {
        "water_solubility": 0.15,
        "human_intestinal_absorption": 0.35,
        "caco2_permeability": 0.25,
        "oral_bioavailability": 0.25,
    },
    "distribution": {
        "bbb_penetration": 0.4,
        "plasma_protein_binding": 0.3,
        "volume_of_distribution": 0.3,
    },
    "metabolism": {
        "cyp1a2_inhibitor": 0.08,
        "cyp2c9_inhibitor": 0.08,
        "cyp2c19_inhibitor": 0.08,
        "cyp2d6_inhibitor": 0.08,
        "cyp3a4_inhibitor": 0.12,
        "cyp1a2_substrate": 0.07,
        "cyp2c9_substrate": 0.07,
        "cyp2c19_substrate": 0.07,
        "cyp2d6_substrate": 0.07,
        "cyp3a4_substrate": 0.10,
        "metabolic_stability": 0.20,
    },
    "excretion": {
        "total_clearance": 0.6,
        "renal_clearance": 0.4,
    },
    "toxicity": {
        "hepatotoxicity": 0.3,
        "cardiotoxicity_herg": 0.3,
        "ames_mutagenicity": 0.25,
        "general_toxicity": 0.15,
    },
}

# Risk thresholds
RISK_THRESHOLDS = {
    "absorption": {"high_risk": 0.4, "moderate_risk": 0.6},
    "distribution": {"high_risk": 0.5, "moderate_risk": 0.7},
    "metabolism": {"high_risk": 0.5, "moderate_risk": 0.7},
    "excretion": {"high_risk": 0.6, "moderate_risk": 0.8},
    "toxicity": {"high_risk": 0.3, "moderate_risk": 0.5},
}

# Desirable prediction directions (True = higher probability is better)
DESIRABLE_DIRECTION = {
    "water_solubility": True,  # Higher solubility is better
    "human_intestinal_absorption": True,
    "caco2_permeability": True,
    "oral_bioavailability": True,
    "bbb_penetration": False,  # Context-dependent, but generally lower for peripherally acting drugs
    "plasma_protein_binding": False,  # Lower is often better for free drug
    "volume_of_distribution": None,  # Context-dependent
    "cyp1a2_inhibitor": False,
    "cyp2c9_inhibitor": False,
    "cyp2c19_inhibitor": False,
    "cyp2d6_inhibitor": False,
    "cyp3a4_inhibitor": False,
    "cyp1a2_substrate": None,  # Context-dependent
    "cyp2c9_substrate": None,
    "cyp2c19_substrate": None,
    "cyp2d6_substrate": None,
    "cyp3a4_substrate": None,
    "metabolic_stability": True,
    "total_clearance": False,  # Lower clearance often better
    "renal_clearance": None,
    "hepatotoxicity": False,
    "cardiotoxicity_herg": False,
    "ames_mutagenicity": False,
    "general_toxicity": False,
}


@dataclass
class ADMETScore:
    """Score for a single ADMET endpoint."""
    endpoint: str
    category: str
    raw_score: float  # 0-1 probability
    normalized_score: float  # 0-1, adjusted for desirable direction
    weight: float
    is_favorable: bool
    confidence: str


@dataclass
class CategoryScore:
    """Aggregate score for an ADMET category."""
    category: str
    score: float  # 0-1 weighted average
    risk_level: str  # "High", "Moderate", "Low"
    endpoint_scores: list[ADMETScore] = field(default_factory=list)
    favorable_count: int = 0
    total_count: int = 0


@dataclass
class OverallADMETScore:
    """Overall ADMET assessment."""
    overall_score: float  # 0-1
    risk_classification: str  # "Favorable", "Acceptable", "Concerning", "High Risk"
    category_scores: dict[str, CategoryScore] = field(default_factory=dict)
    drug_likeness_score: float = 0.0
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


def calculate_endpoint_score(prediction: ADMETPrediction) -> ADMETScore:
    """Calculate normalized score for a single endpoint.
    
    Args:
        prediction: ADMET prediction
        
    Returns:
        ADMETScore with normalized scoring
    """
    endpoint = prediction.endpoint
    category = prediction.category
    probability = prediction.probability if prediction.probability is not None else 0.5
    confidence = prediction.confidence
    
    # Get weight
    weight = CATEGORY_WEIGHTS.get(category, {}).get(endpoint, 1.0)
    
    # Get desirable direction
    desirable = DESIRABLE_DIRECTION.get(endpoint)
    
    if desirable is True:
        # Higher probability is better
        normalized = probability
        is_favorable = probability >= 0.5
    elif desirable is False:
        # Lower probability is better
        normalized = 1.0 - probability
        is_favorable = probability < 0.5
    else:
        # Context-dependent - neutral scoring
        normalized = 0.5
        is_favorable = True  # Neutral
    
    # Adjust for confidence
    confidence_multiplier = {"high": 1.0, "medium": 0.8, "low": 0.5, "unknown": 0.3}
    normalized *= confidence_multiplier.get(confidence, 0.5)
    
    return ADMETScore(
        endpoint=endpoint,
        category=category,
        raw_score=round(probability, 3),
        normalized_score=round(normalized, 3),
        weight=weight,
        is_favorable=is_favorable,
        confidence=confidence,
    )


def calculate_category_score(predictions: list[ADMETPrediction], category: str) -> CategoryScore:
    """Calculate aggregate score for an ADMET category.
    
    Args:
        predictions: All predictions
        category: Category name
        
    Returns:
        CategoryScore
    """
    cat_predictions = [p for p in predictions if p.category == category]
    
    if not cat_predictions:
        return CategoryScore(category=category, score=0.5, risk_level="Unknown")
    
    endpoint_scores = [calculate_endpoint_score(p) for p in cat_predictions]
    
    # Weighted average
    total_weight = sum(es.weight for es in endpoint_scores)
    if total_weight > 0:
        weighted_score = sum(es.normalized_score * es.weight for es in endpoint_scores) / total_weight
    else:
        weighted_score = 0.5
    
    favorable_count = sum(1 for es in endpoint_scores if es.is_favorable)
    total_count = len(endpoint_scores)
    
    # Determine risk level
    thresholds = RISK_THRESHOLDS.get(category, {"high_risk": 0.4, "moderate_risk": 0.6})
    
    if weighted_score < thresholds["high_risk"]:
        risk_level = "High"
    elif weighted_score < thresholds["moderate_risk"]:
        risk_level = "Moderate"
    else:
        risk_level = "Low"
    
    return CategoryScore(
        category=category,
        score=round(weighted_score, 3),
        risk_level=risk_level,
        endpoint_scores=endpoint_scores,
        favorable_count=favorable_count,
        total_count=total_count,
    )


def calculate_overall_admet_score(result: ADMETResult) -> OverallADMETScore:
    """Calculate overall ADMET score from prediction result.
    
    Args:
        result: ADMET prediction result
        
    Returns:
        OverallADMETScore
    """
    # A compound without predictions has no evidence either way. Report a
    # neutral score and the corresponding "Concerning" classification rather
    # than implying favourable properties.
    if not result.predictions:
        limitations = [
            "No ADMET predictions were available for this compound",
            "Score reflects absence of evidence, not a favourable profile",
        ]
        return OverallADMETScore(
            overall_score=0.5,
            risk_classification="Concerning",
            category_scores={},
            drug_likeness_score=result.molecular_properties.get("drug_likeness", {}).get("overall_score", 0.0),
            summary={"limitations": limitations, "total_endpoints": 0},
            limitations=limitations,
        )

    # Calculate category scores
    category_scores = {}
    for category in ["absorption", "distribution", "metabolism", "excretion", "toxicity"]:
        category_scores[category] = calculate_category_score(result.predictions, category)
    
    # Overall weighted score
    category_weights = {
        "absorption": 0.25,
        "distribution": 0.15,
        "metabolism": 0.20,
        "excretion": 0.10,
        "toxicity": 0.30,
    }
    
    overall_score = sum(
        category_scores[cat].score * category_weights[cat]
        for cat in category_weights
    )
    
    # Overall risk classification
    if overall_score >= 0.75:
        risk_classification = "Favorable"
    elif overall_score >= 0.60:
        risk_classification = "Acceptable"
    elif overall_score >= 0.40:
        risk_classification = "Concerning"
    else:
        risk_classification = "High Risk"
    
    # Drug-likeness from molecular properties
    drug_likeness = result.molecular_properties.get("drug_likeness", {})
    drug_likeness_score = drug_likeness.get("overall_score", 0.0)
    
    # Summary
    summary = {
        "total_endpoints": len(result.predictions),
        "favorable_endpoints": sum(1 for cat in category_scores.values() for es in cat.endpoint_scores if es.is_favorable),
        "high_risk_categories": sum(1 for cat in category_scores.values() if cat.risk_level == "High"),
        "moderate_risk_categories": sum(1 for cat in category_scores.values() if cat.risk_level == "Moderate"),
        "low_risk_categories": sum(1 for cat in category_scores.values() if cat.risk_level == "Low"),
        "category_scores": {cat: round(cs.score, 3) for cat, cs in category_scores.items()},
        "category_risk_levels": {cat: cs.risk_level for cat, cs in category_scores.items()},
    }
    
    # Limitations
    limitations = [
        "Predictions are computational estimates, not experimentally validated",
        "Rule-based predictions have limited accuracy compared to experimental assays",
        "ML models may not generalize to novel chemical space",
        "Confidence varies by endpoint and chemical domain",
        "Drug-likeness rules are guidelines, not absolute criteria",
        "BBB penetration assessment depends on therapeutic intent",
        "CYP predictions do not account for time-dependent inhibition or induction",
        "Clearance predictions are simplified and species-dependent",
    ]
    summary["limitations"] = limitations
    
    return OverallADMETScore(
        overall_score=round(overall_score, 3),
        risk_classification=risk_classification,
        category_scores=category_scores,
        drug_likeness_score=drug_likeness_score,
        summary=summary,
        limitations=limitations,
    )


def compare_compounds(
    results: list[ADMETResult],
    names: list[str] | None = None,
) -> dict[str, Any]:
    """Compare multiple compounds' ADMET profiles.
    
    Args:
        results: List of ADMET results
        names: Optional compound names
        
    Returns:
        Comparison dictionary
    """
    if names is None:
        names = [f"Compound {i+1}" for i in range(len(results))]
    
    if len(results) != len(names):
        raise ValueError("Results and names length mismatch")
    
    # Calculate scores for each compound
    scores = [calculate_overall_admet_score(r) for r in results]
    
    # Compare category scores
    categories = ["absorption", "distribution", "metabolism", "excretion", "toxicity"]
    category_comparison = {}
    
    for cat in categories:
        category_comparison[cat] = {
            name: scores[i].category_scores[cat].score
            for i, name in enumerate(names)
        }
    
    # Rank compounds
    ranked = sorted(zip(names, scores), key=lambda x: x[1].overall_score, reverse=True)
    ranking = [{"rank": i+1, "name": name, "overall_score": score.overall_score, "risk": score.risk_classification}
               for i, (name, score) in enumerate(ranked)]
    
    # Find best/worst per category
    best_per_category = {}
    worst_per_category = {}
    for cat in categories:
        cat_scores = [(name, scores[i].category_scores[cat].score) for i, name in enumerate(names)]
        best_per_category[cat] = max(cat_scores, key=lambda x: x[1])[0]
        worst_per_category[cat] = min(cat_scores, key=lambda x: x[1])[0]
    
    return {
        "compounds": names,
        "ranking": ranking,
        "category_comparison": category_comparison,
        "best_per_category": best_per_category,
        "worst_per_category": worst_per_category,
        "overall_scores": {name: scores[i].overall_score for i, name in enumerate(names)},
        "risk_classifications": {name: scores[i].risk_classification for i, name in enumerate(names)},
    }


def generate_risk_report(score: OverallADMETScore) -> str:
    """Generate human-readable risk report.
    
    Args:
        score: Overall ADMET score
        
    Returns:
        Formatted risk report
    """
    lines = [
        "=" * 60,
        "ADMET RISK ASSESSMENT REPORT",
        "=" * 60,
        "",
        f"Overall Score: {score.overall_score:.3f} ({score.risk_classification})",
        f"Drug-Likeness Score: {score.drug_likeness_score:.3f}",
        "",
        "Category Breakdown:",
        "-" * 40,
    ]
    
    for cat, cat_score in score.category_scores.items():
        lines.append(
            f"  {cat.capitalize():15s}: {cat_score.score:.3f} "
            f"[{cat_score.risk_level:8s}] "
            f"({cat_score.favorable_count}/{cat_score.total_count} favorable)"
        )
        
        # Show individual endpoints
        for es in cat_score.endpoint_scores:
            status = "✓" if es.is_favorable else "✗"
            conf = es.confidence[0].upper()
            lines.append(
                f"    {status} {es.endpoint:30s}: "
                f"raw={es.raw_score:.2f} norm={es.normalized_score:.2f} "
                f"w={es.weight:.2f} conf={conf}"
            )
    
    lines.extend([
        "",
        "Key Findings:",
        "-" * 40,
    ])
    
    # High risk items
    high_risk = []
    for cat, cat_score in score.category_scores.items():
        for es in cat_score.endpoint_scores:
            if not es.is_favorable and es.confidence in ("high", "medium"):
                high_risk.append(f"  - {cat}/{es.endpoint}: unfavorable (confidence: {es.confidence})")
    
    if high_risk:
        lines.append("High Confidence Unfavorable Predictions:")
        lines.extend(high_risk[:10])  # Limit to top 10
    else:
        lines.append("  No high-confidence unfavorable predictions")
    
    lines.extend([
        "",
        "Limitations:",
        "-" * 40,
    ])
    for lim in score.limitations:
        lines.append(f"  - {lim}")
    
    lines.extend([
        "",
        "=" * 60,
        "End of Report",
        "=" * 60,
    ])
    
    return "\n".join(lines)