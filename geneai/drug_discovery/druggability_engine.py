"""Explainable druggability assessment engine for GeneAI Research.

Combines disease association, genetic evidence, protein function, pathway
relevance, PPI network context, structural information, and known ligand
evidence into a transparent target prioritization score. The score is a
research shortlist index -- not a probability of clinical success or
experimentally validated druggability.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from geneai.drug_discovery import api_clients

logger = logging.getLogger(__name__)

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")

DEFAULT_DRUGGABILITY_WEIGHTS = {
    "disease_association": 1.0,
    "genetic_evidence": 1.5,
    "protein_function": 0.75,
    "pathway_relevance": 0.5,
    "ppi_network": 0.5,
    "structural_info": 0.5,
    "ligand_evidence": 0.5,
    "target_accessibility": 0.5,
}

_ACCESSIBLE_LOCALIZATIONS = {
    "plasma membrane",
    "cell membrane",
    "membrane",
    "cell surface",
    "extracellular",
    "secreted",
    "lysosome",
    "endoplasmic reticulum",
    "golgi apparatus",
}

_DRUGGABLE_EC_CLASSES = {
    "1.", "2.", "3.", "4.", "5.", "6.", "7.",
}


@dataclass(frozen=True)
class DruggabilityRequest:
    """Inputs for one druggability assessment run."""

    target: dict[str, Any]
    weights: dict[str, float] = field(default_factory=dict)


def _valid_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def _normalize_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    normalized = dict(DEFAULT_DRUGGABILITY_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key not in normalized:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Druggability weight {key} must be numeric.") from exc
            if not 0 <= number <= 10:
                raise ValueError(f"Druggability weight {key} must be between 0 and 10.")
            normalized[key] = number
    if not any(normalized.values()):
        raise ValueError("At least one druggability weight must be greater than zero.")
    return normalized


def _protein_accessibility_score(
    protein: dict[str, Any],
) -> tuple[float | None, list[str]]:
    """Assess target accessibility from subcellular localization and family.

    Returns (score_or_none, rationale). Score is None when no localization
    evidence is available, so it is excluded from the weighted mean.
    """
    rationale: list[str] = []
    location = str(protein.get("subcellular_location") or "").lower()
    family = " ".join(protein.get("family_annotations", []) or []).lower()
    ec_numbers = protein.get("ec_numbers", []) or []

    if not location and not family and not ec_numbers:
        return None, ["No localization, family, or enzyme-class evidence available."]

    score_components: list[float] = []

    if location:
        accessible = any(term in location for term in _ACCESSIBLE_LOCALIZATIONS)
        if accessible:
            score_components.append(0.8)
            rationale.append(f"Subcellular location '{location}' is potentially accessible.")
        else:
            score_components.append(0.3)
            rationale.append(f"Subcellular location '{location}' may limit direct target access.")
    else:
        rationale.append("No subcellular localization reported.")

    if ec_numbers:
        score_components.append(0.7)
        rationale.append(
            f"Enzyme classification {', '.join(str(e) for e in ec_numbers[:3])} "
            "suggests potential small-molecule modulation."
        )
    else:
        rationale.append("No enzyme classification reported.")

    if family:
        score_components.append(0.5)
        rationale.append(f"Protein family annotation: {family[:120]}.")
    else:
        rationale.append("No protein family annotation reported.")

    if not score_components:
        return None, rationale
    return sum(score_components) / len(score_components), rationale


def _structural_evidence_score(
    protein: dict[str, Any],
) -> tuple[float | None, list[str]]:
    """Score available structural information (PDB, AlphaFold).

    Returns (score_or_none, rationale). Experimental structures score higher
    than predicted models, but both are context only.
    """
    rationale: list[str] = []
    pdb_ids = protein.get("pdb_ids_from_uniprot", []) or []
    alpha_fold = protein.get("alpha_fold_models") or []
    structure_count = len(pdb_ids) + len(alpha_fold)

    if structure_count == 0:
        rationale.append("No experimental structure or predicted model available.")
        return None, rationale

    if pdb_ids:
        rationale.append(
            f"{len(pdb_ids)} experimental PDB structure(s): {', '.join(pdb_ids[:5])}."
        )
    if alpha_fold:
        rationale.append(
            f"{len(alpha_fold)} AlphaFold predicted model(s) available "
            "(computational, not experimental)."
        )

    experimental_weight = 0.8 if pdb_ids else 0.0
    predicted_weight = 0.4 if alpha_fold else 0.0
    score = min(1.0, experimental_weight + predicted_weight)
    return score, rationale


def _ligand_evidence_score(
    protein: dict[str, Any],
) -> tuple[float | None, list[str]]:
    """Assess known ligand/cofactor evidence from UniProt cross-references.

    Ligand presence suggests a binding site may exist but does not imply
    druggability or therapeutic effect.
    """
    rationale: list[str] = []
    interactions = protein.get("interactions", []) or []
    ec_numbers = protein.get("ec_numbers", []) or []
    sequence = protein.get("sequence") or ""

    ligand_indicators = 0
    for item in interactions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        if any(term in name for term in ("ligand", "inhibitor", "substrate", "cofactor", "drug", "compound")):
            ligand_indicators += 1

    if ligand_indicators:
        rationale.append(
            f"{ligand_indicators} known ligand/cofactor/copper-binding interaction(s) "
            "annotated in UniProt."
        )
    if ec_numbers:
        rationale.append(
            f"Enzyme classification {', '.join(str(e) for e in ec_numbers[:3])} "
            "suggests catalytic activity with potential ligand binding."
        )

    if not ligand_indicators and not ec_numbers:
        rationale.append("No known ligand or enzyme-class evidence reported.")
        return None, rationale

    score = min(1.0, 0.4 * ligand_indicators + 0.3 * bool(ec_numbers))
    return score, rationale


def assess_druggability(
    request: DruggabilityRequest,
) -> dict[str, Any]:
    """Compute an explainable druggability assessment for a single target.

    The output is a weighted index over available evidence domains. Missing
    domains are excluded and remaining weights renormalized. The score is NOT
    a probability of clinical success or experimentally validated druggability.
    """
    target = request.target or {}
    if not isinstance(target, dict):
        raise ValueError("A target record is required.")
    gene_symbol = str(target.get("gene_symbol") or "").strip().upper()
    if not _SYMBOL.fullmatch(gene_symbol):
        raise ValueError("A valid gene_symbol is required in the target record.")

    weights = _normalize_weights(request.weights)
    protein = target.get("protein") if isinstance(target.get("protein"), dict) else {}

    components: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    rationale: list[str] = []

    # 1. Disease association evidence
    disease_score = _valid_score(target.get("disease_association_evidence_score"))
    if disease_score is not None and weights["disease_association"] > 0:
        components["disease_association"] = {
            "score": disease_score,
            "weight": weights["disease_association"],
        }
        rationale.append(f"Disease association evidence score: {disease_score:.2f}.")
    else:
        missing.append("disease_association")
        rationale.append("No disease association evidence score available.")

    # 2. Genetic evidence
    genetic_score = _valid_score(target.get("genetic_evidence_score"))
    if genetic_score is not None and weights["genetic_evidence"] > 0:
        components["genetic_evidence"] = {
            "score": genetic_score,
            "weight": weights["genetic_evidence"],
        }
        rationale.append(f"Genetic evidence score: {genetic_score:.2f}.")
    else:
        missing.append("genetic_evidence")
        rationale.append("No genetic evidence score available.")

    # 3. Protein function evidence
    has_function = bool(protein.get("function") or target.get("protein_function"))
    has_domains = bool(protein.get("domains"))
    protein_function_score: float | None = None
    if has_function or has_domains:
        protein_function_score = 0.6 if has_function else 0.3
        if has_domains:
            protein_function_score = min(1.0, protein_function_score + 0.2)
        components["protein_function"] = {
            "score": protein_function_score,
            "weight": weights["protein_function"],
        }
        rationale.append(
            f"Protein function annotation present: {bool(has_function)}; "
            f"domains: {len(protein.get('domains', []) or [])}."
        )
    else:
        missing.append("protein_function")
        rationale.append("No protein function or domain annotation available.")

    # 4. Pathway relevance
    pathway_count = len(target.get("disease_pathway_context", []) or [])
    go_count = len(target.get("go_annotations", []) or [])
    pathway_score: float | None = None
    if pathway_count > 0 or go_count > 0:
        pathway_score = min(1.0, 0.4 * min(pathway_count, 3) / 3 + 0.3 * min(go_count, 3) / 3)
        components["pathway_relevance"] = {
            "score": pathway_score,
            "weight": weights["pathway_relevance"],
        }
        rationale.append(f"Pathway context: {pathway_count} pathway(s), {go_count} GO annotation(s).")
    else:
        missing.append("pathway_relevance")
        rationale.append("No pathway or GO annotation evidence available.")

    # 5. PPI network
    ppi_score = _valid_score(target.get("ppi_network_score"))
    interaction_count = int(target.get("ppi_interaction_count") or 0)
    if ppi_score is not None and weights["ppi_network"] > 0:
        components["ppi_network"] = {
            "score": ppi_score,
            "weight": weights["ppi_network"],
        }
        rationale.append(f"STRING network association score: {ppi_score:.2f} ({interaction_count} interaction(s)).")
    elif interaction_count > 0 and weights["ppi_network"] > 0:
        components["ppi_network"] = {
            "score": min(1.0, 0.3 + 0.1 * interaction_count),
            "weight": weights["ppi_network"],
        }
        rationale.append(f"Protein interaction network: {interaction_count} interaction(s) retrieved.")
    else:
        missing.append("ppi_network")
        rationale.append("No protein-protein interaction evidence available.")

    # 6. Structural information
    structural_score, structural_rationale = _structural_evidence_score(protein)
    rationale.extend(structural_rationale)
    if structural_score is not None and weights["structural_info"] > 0:
        components["structural_info"] = {
            "score": structural_score,
            "weight": weights["structural_info"],
        }

    # 7. Ligand evidence
    ligand_score, ligand_rationale = _ligand_evidence_score(protein)
    rationale.extend(ligand_rationale)
    if ligand_score is not None and weights["ligand_evidence"] > 0:
        components["ligand_evidence"] = {
            "score": ligand_score,
            "weight": weights["ligand_evidence"],
        }

    # 8. Target accessibility
    accessibility_score, accessibility_rationale = _protein_accessibility_score(protein)
    rationale.extend(accessibility_rationale)
    if accessibility_score is not None and weights["target_accessibility"] > 0:
        components["target_accessibility"] = {
            "score": accessibility_score,
            "weight": weights["target_accessibility"],
        }

    denominator = sum(component["weight"] for component in components.values())
    if denominator <= 0:
        index = None
    else:
        index = (
            100.0
            * sum(component["score"] * component["weight"] for component in components.values())
            / denominator
        )

    tier = (
        "High druggability research-priority"
        if index is not None and index >= 70
        else "Medium druggability research-priority"
        if index is not None and index >= 40
        else "Low druggability research-priority"
        if index is not None
        else "Not scored"
    )

    return {
        "gene_symbol": gene_symbol,
        "gene_name": target.get("gene_name") or "",
        "druggability_index": round(index, 2) if index is not None else None,
        "druggability_tier": tier,
        "druggability_components": components,
        "druggability_missing_domains": missing,
        "druggability_rationale": rationale,
        "druggability_weights": weights,
        "structural_evidence": {
            "pdb_ids": protein.get("pdb_ids_from_uniprot", []) or [],
            "alpha_fold_models": protein.get("alpha_fold_models") or [],
            "has_experimental_structure": bool(protein.get("pdb_ids_from_uniprot")),
        },
        "ligand_evidence": {
            "interaction_count": len(protein.get("interactions", []) or []),
            "ec_numbers": protein.get("ec_numbers", []) or [],
        },
        "target_accessibility": {
            "subcellular_location": protein.get("subcellular_location") or "",
            "protein_family": protein.get("family_annotations", []) or [],
        },
        "protein": {
            "uniprot_id": protein.get("uniprot_id") or "",
            "protein_name": protein.get("protein_name") or "",
            "function": protein.get("function") or "",
        },
        "source_references": target.get("gene_source_references", []),
        "data_sources": target.get("data_sources", []),
        "score_interpretation": (
            "Weighted mean of available 0-1 evidence scores; missing domains are excluded "
            "and remaining weights are renormalized. This is an explainable research "
            "shortlist index, NOT a probability of druggability, clinical success, or "
            "experimental validation."
        ),
        "limitations": [
            "Druggability requires experimental binding assays, structural ligand-bound "
            "structures, and cellular/organismal validation; none of those are performed here.",
            "Protein accessibility heuristics are based on localization annotations and do not "
            "measure membrane permeability, blood-brain barrier penetration, or target engagement.",
            "Known ligand annotations from UniProt are curatorial and may not reflect druggable "
            "chemistry or therapeutic relevance.",
        ],
    }