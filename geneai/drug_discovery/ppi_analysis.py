"""STRING edge normalization and lightweight protein-association network metrics."""
from __future__ import annotations

import re
from typing import Any

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")


def summarize_ppi_network(
    edges: list[dict[str, Any]],
    input_gene_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Deduplicate edges and calculate transparent degree-based hub measures.

    STRING may report functional associations, which need not be direct physical
    interactions. Metrics describe the retrieved network only.
    """
    inputs = {str(value).strip().upper() for value in (input_gene_symbols or []) if _SYMBOL.fullmatch(str(value).strip().upper())}
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in edges:
        if not isinstance(raw, dict):
            continue
        left = str(raw.get("protein_a") or "").strip().upper()
        right = str(raw.get("protein_b") or "").strip().upper()
        if not _SYMBOL.fullmatch(left) or not _SYMBOL.fullmatch(right) or left == right:
            continue
        try:
            score = float(raw.get("combined_score"))
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 1:
            continue
        key = tuple(sorted((left, right)))
        prior = normalized.get(key)
        if prior and prior["combined_score"] >= score:
            continue
        edge = {**raw, "protein_a": key[0], "protein_b": key[1], "combined_score": score}
        normalized[key] = edge

    edge_rows = list(normalized.values())
    nodes: dict[str, dict[str, Any]] = {}
    for symbol in inputs:
        nodes[symbol] = {
            "gene_symbol": symbol,
            "string_id": None,
            "is_input_gene": True,
            "interaction_count": 0,
            "degree_centrality": 0.0,
            "weighted_degree": 0.0,
            "max_combined_score": None,
            "max_experimental_channel_score": None,
        }
    for edge in edge_rows:
        channel = edge.get("evidence_channel_scores") if isinstance(edge.get("evidence_channel_scores"), dict) else {}
        for symbol, string_id in ((edge["protein_a"], edge.get("string_id_a")), (edge["protein_b"], edge.get("string_id_b"))):
            node = nodes.setdefault(symbol, {
                "gene_symbol": symbol,
                "string_id": string_id,
                "is_input_gene": symbol in inputs,
                "interaction_count": 0,
                "degree_centrality": 0.0,
                "weighted_degree": 0.0,
                "max_combined_score": None,
                "max_experimental_channel_score": None,
            })
            node["interaction_count"] += 1
            node["weighted_degree"] += edge["combined_score"]
            prior_score = node.get("max_combined_score")
            if prior_score is None or edge["combined_score"] > prior_score:
                node["max_combined_score"] = edge["combined_score"]
            experimental = channel.get("escore", edge.get("experimental_channel_score"))
            if isinstance(experimental, (int, float)):
                prior_experimental = node.get("max_experimental_channel_score")
                if prior_experimental is None or experimental > prior_experimental:
                    node["max_experimental_channel_score"] = float(experimental)
            if string_id and not node.get("string_id"):
                node["string_id"] = string_id

    node_count = len(nodes)
    denominator = max(node_count - 1, 1)
    for node in nodes.values():
        node["degree_centrality"] = round(node["interaction_count"] / denominator, 4)
        node["weighted_degree"] = round(node["weighted_degree"], 4)
        node["max_combined_score"] = round(node["max_combined_score"], 4) if node["max_combined_score"] is not None else None
        if node["max_experimental_channel_score"] is not None:
            node["max_experimental_channel_score"] = round(node["max_experimental_channel_score"], 4)
    node_rows = sorted(nodes.values(), key=lambda row: (-row["interaction_count"], row["gene_symbol"]))
    return {
        "nodes": node_rows,
        "edges": edge_rows,
        "node_count": node_count,
        "edge_count": len(edge_rows),
        "input_gene_symbols": sorted(inputs),
        "hub_candidates": [row["gene_symbol"] for row in node_rows[:10] if row["interaction_count"] > 0],
        "centrality_method": "Degree centrality = interaction count divided by (retrieved nodes - 1); weighted degree sums STRING combined scores.",
        "interpretation": "STRING network edges represent database associations. Experimental-channel scores are retained separately and do not prove a direct interaction or disease mechanism.",
    }
