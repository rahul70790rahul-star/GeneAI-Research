"""Explainable target evidence features and configurable research prioritisation."""
from __future__ import annotations

import re
from typing import Any

DEFAULT_TARGET_WEIGHTS = {
    "disease_association": 1.0,
    "genetic_evidence": 1.5,
    "literature_evidence": 1.0,
    "protein_interaction_support": 0.5,
}
_GENETIC_EVIDENCE_TYPES = {
    "genetic_association", "genetic_literature", "somatic_mutation", "animal_model",
}
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")


def _valid_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def build_target_feature_rows(
    disease_result: dict[str, Any],
    ppi_network: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Join disease genes to Phase 4.2 protein/pathway/GO/VCF and Phase 4.3 PPI context."""
    genes = disease_result.get("genes")
    if not isinstance(genes, list):
        raise ValueError("Run Drug Discovery · Disease Analysis first so its retrieved gene evidence is available.")
    proteins = {
        str(item.get("gene_symbol", "")).upper(): item
        for item in disease_result.get("proteins", [])
        if isinstance(item, dict) and item.get("gene_symbol")
    }
    annotations: dict[str, list[dict[str, Any]]] = {}
    for item in disease_result.get("go_annotations", []):
        if isinstance(item, dict) and item.get("gene_symbol"):
            annotations.setdefault(str(item["gene_symbol"]).upper(), []).append(item)
    ppi_nodes = {
        str(item.get("gene_symbol", "")).upper(): item
        for item in (ppi_network or {}).get("nodes", [])
        if isinstance(item, dict) and item.get("gene_symbol")
    }
    ppi_edges = (ppi_network or {}).get("edges", [])
    edge_count_by_gene: dict[str, int] = {}
    for edge in ppi_edges:
        if not isinstance(edge, dict):
            continue
        for key in ("protein_a", "protein_b"):
            symbol = str(edge.get(key) or "").upper()
            if symbol:
                edge_count_by_gene[symbol] = edge_count_by_gene.get(symbol, 0) + 1
    mutation_count_by_gene: dict[str, int] = {}
    mutation_rows_by_gene: dict[str, list[dict[str, Any]]] = {}
    for variant in disease_result.get("mutations", []):
        if not isinstance(variant, dict):
            continue
        info = str(variant.get("gene_info_source_field") or "")
        symbols = {entry.partition(":")[0].strip().upper() for entry in info.split("|")}
        symbols.update({str(variant.get("gene_symbol") or "").strip().upper()})
        for symbol in symbols:
            if _SYMBOL.fullmatch(symbol):
                mutation_count_by_gene[symbol] = mutation_count_by_gene.get(symbol, 0) + 1
                mutation_rows_by_gene.setdefault(symbol, []).append(variant)
    output = []
    seen: set[str] = set()
    for raw in genes:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("gene_symbol") or "").strip().upper()
        if not _SYMBOL.fullmatch(symbol) or symbol in seen:
            continue
        seen.add(symbol)
        protein = proteins.get(symbol, {})
        genetic_components = {
            key: value
            for key, value in (raw.get("datatype_scores") or {}).items()
            if key in _GENETIC_EVIDENCE_TYPES and _valid_score(value) is not None
        }
        genetic_score = max((_valid_score(value) for value in genetic_components.values()), default=None)
        pdb_ids = sorted({str(value).upper() for value in protein.get("pdb_ids_from_uniprot", []) if isinstance(value, str)})
        ppi_node = ppi_nodes.get(symbol, {})
        interaction_score = _valid_score(ppi_node.get("max_combined_score"))
        pathway_rows = (disease_result.get("pathways") or {}).get("pathways", [])
        output.append({
            **raw,
            "gene_symbol": symbol,
            "protein": protein,
            "disease_association_evidence_score": _valid_score(raw.get("association_score")),
            "genetic_evidence_score": genetic_score,
            "genetic_evidence_components": genetic_components,
            "literature_evidence_score": _valid_score((raw.get("datatype_scores") or {}).get("literature")),
            "ppi_network_score": interaction_score,
            "ppi_interaction_count": edge_count_by_gene.get(symbol, 0),
            "ppi_degree_centrality": ppi_node.get("degree_centrality"),
            "ppi_max_experimental_channel_score": ppi_node.get("max_experimental_channel_score"),
            "vcf_preview_variant_count": mutation_count_by_gene.get(symbol, 0),
            "vcf_preview_variants": mutation_rows_by_gene.get(symbol, []),
            "protein_function": protein.get("function"),
            "protein_subcellular_location": protein.get("subcellular_location"),
            "uniprot_id": protein.get("uniprot_id"),
            "protein_domain_count": len(protein.get("domains", [])),
            "pdb_ids_from_uniprot": pdb_ids,
            "go_annotations": annotations.get(symbol, []),
            "go_annotation_count": len(annotations.get(symbol, [])),
            "disease_pathway_context_count": len(pathway_rows),
            "disease_pathway_context": pathway_rows,
            "gene_source_references": [
                url for url in (raw.get("source_url"), raw.get("ncbi_source_url"), raw.get("ensembl_source_url")) if url
            ],
            "target_evidence_limitations": [
                "Variant entries are displayed only as supplied in the Phase 3 VCF preview; their presence does not imply pathogenicity or functional effect.",
                "Reactome enrichment is returned for the disease gene set, not as per-gene pathway evidence.",
                "Protein structure availability and STRING associations are context and are not validated druggability evidence.",
            ],
        })
    return output


def normalize_target_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    normalized = dict(DEFAULT_TARGET_WEIGHTS)
    for key, value in (weights or {}).items():
        if key not in normalized:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Target evidence weight {key} must be numeric.") from exc
        if not 0 <= number <= 10:
            raise ValueError(f"Target evidence weight {key} must be between 0 and 10.")
        normalized[key] = number
    if not any(normalized.values()):
        raise ValueError("At least one evidence weight must be greater than zero.")
    return normalized


def rank_target_evidence(
    feature_rows: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Calculate a configurable evidence index, not probability or druggability."""
    normalized_weights = normalize_target_weights(weights)
    score_keys = {
        "disease_association": "disease_association_evidence_score",
        "genetic_evidence": "genetic_evidence_score",
        "literature_evidence": "literature_evidence_score",
        "protein_interaction_support": "ppi_network_score",
    }
    ranked = []
    for raw in feature_rows:
        row = dict(raw)
        components: dict[str, dict[str, float]] = {}
        missing = []
        for label, field in score_keys.items():
            weight = normalized_weights[label]
            if weight <= 0:
                continue
            score = _valid_score(row.get(field))
            if score is None:
                missing.append(label)
            else:
                components[label] = {"score": score, "weight": weight}
        denominator = sum(value["weight"] for value in components.values())
        index = (
            100.0 * sum(value["score"] * value["weight"] for value in components.values()) / denominator
            if denominator > 0 else None
        )
        tier = (
            "High research-priority shortlist" if index is not None and index >= 67
            else "Medium research-priority shortlist" if index is not None and index >= 34
            else "Low research-priority shortlist" if index is not None
            else "Not scored"
        )
        row.update({
            "target_research_priority_index": round(index, 2) if index is not None else None,
            "target_research_priority_tier": tier,
            "target_priority_components": components,
            "target_missing_evidence_domains": missing,
            "target_priority_method": "Weighted mean of available 0–1 source scores; missing domains are excluded and remaining weights renormalized. This is an explainable research index, not probability of druggability or clinical success.",
        })
        ranked.append(row)
    ranked.sort(key=lambda row: (
        row.get("target_research_priority_index") is None,
        -(row.get("target_research_priority_index") or 0.0),
        -(row.get("association_score") or 0.0),
        row.get("gene_symbol", ""),
    ))
    for rank, row in enumerate(ranked, 1):
        row["target_research_rank"] = rank
    return ranked, normalized_weights


def build_ml_feature_rows(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select numeric features for an optional model trained on user-supplied labels."""
    features = (
        "association_score",
        "genetic_evidence_score",
        "literature_evidence_score",
        "ppi_network_score",
        "ppi_degree_centrality",
        "ppi_max_experimental_channel_score",
        "vcf_preview_variant_count",
        "uniprot_annotation_present",
        "protein_domain_count",
        "pdb_structure_count",
        "go_annotation_count",
        "string_interaction_count",
    )
    rows = []
    for target in targets:
        protein = target.get("protein") or {}
        rows.append({
            "gene_symbol": target.get("gene_symbol"),
            "association_score": target.get("disease_association_evidence_score"),
            "genetic_evidence_score": target.get("genetic_evidence_score"),
            "literature_evidence_score": target.get("literature_evidence_score"),
            "ppi_network_score": target.get("ppi_network_score"),
            "ppi_degree_centrality": target.get("ppi_degree_centrality"),
            "ppi_max_experimental_channel_score": target.get("ppi_max_experimental_channel_score"),
            "vcf_preview_variant_count": target.get("vcf_preview_variant_count"),
            "uniprot_annotation_present": int(bool(protein)),
            "protein_domain_count": target.get("protein_domain_count"),
            "pdb_structure_count": len(target.get("pdb_ids_from_uniprot", [])),
            "go_annotation_count": target.get("go_annotation_count"),
            "string_interaction_count": target.get("ppi_interaction_count"),
        })
    return rows


ML_FEATURE_COLUMNS = (
    "association_score",
    "genetic_evidence_score",
    "literature_evidence_score",
    "ppi_network_score",
    "ppi_degree_centrality",
    "ppi_max_experimental_channel_score",
    "vcf_preview_variant_count",
    "uniprot_annotation_present",
    "protein_domain_count",
    "pdb_structure_count",
    "go_annotation_count",
    "string_interaction_count",
)
