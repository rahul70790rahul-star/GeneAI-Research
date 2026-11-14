"""Drug comparison module for GeneAI Research."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import drug_search
from geneai.drug_discovery import drug_target_analysis
from geneai.drug_discovery.drug_search import get_drug_details

logger = logging.getLogger(__name__)

# Re-export for test patching compatibility
__all__ = ["get_drug_details", "compare_drugs_detailed"]


def compare_drugs_detailed(drug_identifiers: list[tuple[str, str]]) -> dict[str, Any]:
    """Detailed comparison of multiple drugs."""
    if len(drug_identifiers) < 2:
        raise ValueError("At least 2 drugs required for comparison")
    if len(drug_identifiers) > 10:
        raise ValueError("Maximum 10 drugs for comparison")

    comparison = drug_target_analysis.compare_drugs(drug_identifiers)

    # Add detailed analysis
    comparison["pairwise_similarity"] = _calculate_pairwise_similarity(comparison["drugs"])
    comparison["property_ranges"] = _calculate_property_ranges(comparison["drugs"])
    comparison["target_overlap_matrix"] = _build_target_overlap_matrix(comparison["drugs"])
    comparison["indication_overlap_matrix"] = _build_indication_overlap_matrix(comparison["drugs"])

    return comparison


def _calculate_pairwise_similarity(drugs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate similarity between drug pairs."""
    similarities = []
    for i, drug1 in enumerate(drugs):
        for j, drug2 in enumerate(drugs[i+1:], i+1):
            sim = _compute_drug_similarity(drug1, drug2)
            similarities.append({
                "drug1": drug1.get("identifier"),
                "drug2": drug2.get("identifier"),
                "drug1_name": drug1.get("name"),
                "drug2_name": drug2.get("name"),
                **sim,
            })
    return similarities


def _compute_drug_similarity(drug1: dict[str, Any], drug2: dict[str, Any]) -> dict[str, float]:
    """Compute similarity metrics between two drugs."""
    # Target overlap
    targets1 = set(t.get("target_id") or t.get("target_symbol") for t in drug1.get("targets", []))
    targets2 = set(t.get("target_id") or t.get("target_symbol") for t in drug2.get("targets", []))
    target_jaccard = len(targets1 & targets2) / len(targets1 | targets2) if targets1 | targets2 else 0

    # Indication overlap
    inds1 = set(i.get("disease_name") or i.get("disease_id") for i in drug1.get("indications", []))
    inds2 = set(i.get("disease_name") or i.get("disease_id") for i in drug2.get("indications", []))
    indication_jaccard = len(inds1 & inds2) / len(inds1 | inds2) if inds1 | inds2 else 0

    # Property similarity (Tanimoto-like for continuous properties)
    props1 = drug1.get("properties", {})
    props2 = drug2.get("properties", {})
    common_props = set(props1.keys()) & set(props2.keys())
    prop_similarities = []
    for prop in common_props:
        v1, v2 = props1[prop], props2[prop]
        if v1 is not None and v2 is not None and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            if v1 == 0 and v2 == 0:
                prop_similarities.append(1.0)
            else:
                diff = abs(v1 - v2) / max(abs(v1), abs(v2), 1e-10)
                prop_similarities.append(1.0 - min(diff, 1.0))
    prop_similarity = sum(prop_similarities) / len(prop_similarities) if prop_similarities else 0

    # Overall weighted similarity
    overall = 0.5 * target_jaccard + 0.3 * indication_jaccard + 0.2 * prop_similarity

    return {
        "target_jaccard": round(target_jaccard, 3),
        "indication_jaccard": round(indication_jaccard, 3),
        "property_similarity": round(prop_similarity, 3),
        "overall_similarity": round(overall, 3),
        "shared_targets": list(targets1 & targets2),
        "shared_indications": list(inds1 & inds2),
    }


def _calculate_property_ranges(drugs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Calculate min/max/mean for each property across drugs."""
    all_props = {}
    for drug in drugs:
        for prop, value in drug.get("properties", {}).items():
            if isinstance(value, (int, float)):
                if prop not in all_props:
                    all_props[prop] = []
                all_props[prop].append(value)

    ranges = {}
    for prop, values in all_props.items():
        if values:
            ranges[prop] = {
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "count": len(values),
                "values": {drug.get("identifier"): drug.get("properties", {}).get(prop) for drug in drugs},
            }
    return ranges


def _build_target_overlap_matrix(drugs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build target overlap matrix."""
    drug_ids = [d.get("identifier") for d in drugs]
    drug_names = [d.get("name") for d in drugs]

    all_targets = set()
    drug_targets = {}
    for drug in drugs:
        targets = set(t.get("target_id") or t.get("target_symbol") for t in drug.get("targets", []))
        drug_targets[drug.get("identifier")] = targets
        all_targets.update(targets)

    matrix = []
    for target in sorted(all_targets):
        row = {"target": target}
        for did in drug_ids:
            row[did] = target in drug_targets.get(did, set())
        matrix.append(row)

    return {
        "drugs": drug_ids,
        "drug_names": drug_names,
        "targets": sorted(all_targets),
        "matrix": matrix,
    }


def _build_indication_overlap_matrix(drugs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build indication overlap matrix."""
    drug_ids = [d.get("identifier") for d in drugs]
    drug_names = [d.get("name") for d in drugs]

    all_indications = set()
    drug_indications = {}
    for drug in drugs:
        inds = set(i.get("disease_id") or i.get("disease_name") for i in drug.get("indications", []))
        drug_indications[drug.get("identifier")] = inds
        all_indications.update(inds)

    matrix = []
    for ind in sorted(all_indications):
        row = {"indication": ind}
        for did in drug_ids:
            row[did] = ind in drug_indications.get(did, set())
        matrix.append(row)

    return {
        "drugs": drug_ids,
        "drug_names": drug_names,
        "indications": sorted(all_indications),
        "matrix": matrix,
    }


def generate_comparison_report(drug_identifiers: list[tuple[str, str]]) -> str:
    """Generate a text-based comparison report."""
    comparison = compare_drugs_detailed(drug_identifiers)

    lines = [
        "=" * 80,
        "DRUG COMPARISON REPORT",
        "=" * 80,
        f"Generated: {len(comparison['drugs'])} drugs compared",
        "",
    ]

    # Drug summary table
    lines.append("DRUG SUMMARY")
    lines.append("-" * 80)
    for drug in comparison["drugs"]:
        lines.append(f"  {drug.get('identifier')} ({drug.get('id_type')}): {drug.get('name')}")
        props = drug.get("properties", {})
        if props:
            prop_str = ", ".join(f"{k}={v}" for k, v in list(props.items())[:5])
            lines.append(f"    Properties: {prop_str}")
        lines.append(f"    Targets: {len(drug.get('targets', []))}")
        lines.append(f"    Indications: {len(drug.get('indications', []))}")
        lines.append(f"    Clinical Trials: {drug.get('clinical_trials_count', 0)}")
        lines.append(f"    Sources: {', '.join(drug.get('sources', []))}")
        lines.append("")

    # Pairwise similarities
    lines.append("PAIRWISE SIMILARITIES")
    lines.append("-" * 80)
    for sim in comparison["pairwise_similarity"]:
        lines.append(
            f"  {sim['drug1_name']} vs {sim['drug2_name']}: "
            f"Overall={sim['overall_similarity']:.2f}, "
            f"Targets={sim['target_jaccard']:.2f}, "
            f"Indications={sim['indication_jaccard']:.2f}, "
            f"Properties={sim['property_similarity']:.2f}"
        )
        if sim["shared_targets"]:
            lines.append(f"    Shared targets: {', '.join(sim['shared_targets'])}")
        if sim["shared_indications"]:
            lines.append(f"    Shared indications: {', '.join(sim['shared_indications'])}")
        lines.append("")

    # Common targets
    if comparison["common_targets"]:
        lines.append("COMMON TARGETS (2+ drugs)")
        lines.append("-" * 80)
        for ct in comparison["common_targets"]:
            lines.append(f"  {ct['target']}: {', '.join(ct['drugs'])}")
        lines.append("")

    # Common indications
    if comparison["common_indications"]:
        lines.append("COMMON INDICATIONS (2+ drugs)")
        lines.append("-" * 80)
        for ci in comparison["common_indications"]:
            lines.append(f"  {ci['disease']}: {', '.join(ci['drugs'])}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)


def find_similar_drugs(reference_drug: tuple[str, str], candidate_drugs: list[tuple[str, str]], top_n: int = 5) -> list[dict[str, Any]]:
    """Find drugs most similar to a reference drug."""
    all_drugs = [reference_drug] + candidate_drugs
    comparison = compare_drugs_detailed(all_drugs)

    ref_id = reference_drug[0]
    similarities = []

    for sim in comparison["pairwise_similarity"]:
        if sim["drug1"] == ref_id:
            similarities.append({
                "drug_identifier": sim["drug2"],
                "drug_name": sim["drug2_name"],
                "similarity": sim["overall_similarity"],
                "target_similarity": sim["target_jaccard"],
                "indication_similarity": sim["indication_jaccard"],
                "property_similarity": sim["property_similarity"],
                "shared_targets": sim["shared_targets"],
                "shared_indications": sim["shared_indications"],
            })
        elif sim["drug2"] == ref_id:
            similarities.append({
                "drug_identifier": sim["drug1"],
                "drug_name": sim["drug1_name"],
                "similarity": sim["overall_similarity"],
                "target_similarity": sim["target_jaccard"],
                "indication_similarity": sim["indication_jaccard"],
                "property_similarity": sim["property_similarity"],
                "shared_targets": sim["shared_targets"],
                "shared_indications": sim["shared_indications"],
            })

    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    return similarities[:top_n]