"""Mutation-to-target mapping for GeneAI Research.

Connects Phase 2/3 VCF analysis output to gene-disease association and
potential drug target identification. All variant consequences are reported
as supplied in the VCF; no pathogenicity or functional effect is inferred.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.gene_identification import get_gene_information

logger = logging.getLogger(__name__)

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
_CONSEQUENCE_KEYS = ("MC", "CSQ", "ANN")


@dataclass(frozen=True)
class MutationTargetRequest:
    """Inputs for one mutation-to-target mapping run."""

    variants: list[dict[str, Any]]
    disease_id: str | None = None
    disease_name: str | None = None
    max_genes: int = 20


def _variant_consequence(variant: dict[str, Any]) -> str | None:
    info = variant.get("info") if isinstance(variant.get("info"), dict) else {}
    raw_info = variant.get("raw_info") if isinstance(variant.get("raw_info"), str) else ""
    for key in _CONSEQUENCE_KEYS:
        value = info.get(key) or ""
        if not value and raw_info:
            for item in raw_info.split(";"):
                k, _, v = item.partition("=")
                if k == key:
                    value = v
                    break
        if value:
            return str(value)
    consequence = variant.get("consequence_source_field")
    if isinstance(consequence, str) and consequence:
        return consequence
    return None


def _variant_type_label(variant: dict[str, Any]) -> str:
    vt = variant.get("variant_type") or variant.get("sv_type") or ""
    if vt:
        return str(vt)
    ref = str(variant.get("ref") or "")
    alt = str(variant.get("alt") or "")
    if len(ref) == len(alt) == 1:
        return "SNP"
    if len(ref) != len(alt):
        return "INDEL"
    return "COMPLEX"


def _is_loss_of_function(consequence: str | None) -> bool:
    if not consequence:
        return False
    text = consequence.lower()
    return any(term in text for term in ("nonsense", "frameshift", "stop_gain", "stop_lost", "splice"))


def _is_gain_of_function(consequence: str | None) -> bool:
    if not consequence:
        return False
    text = consequence.lower()
    return "missense" in text or "inframe_insertion" in text or "inframe_deletion" in text


def map_variants_to_targets(
    request: MutationTargetRequest,
) -> dict[str, Any]:
    """Map VCF variants to genes and disease-associated potential targets.

    For each variant, the gene symbol(s) embedded in the VCF are resolved to
    NCBI/Ensembl/UniProt identifiers. If a disease is supplied, Open Targets
    association evidence for that disease is attached. Variants are classified
    by consequence and variant type, but no pathogenicity is inferred.
    """
    variants = request.variants or []
    max_genes = max(1, min(int(request.max_genes or 20), 100))

    gene_symbols: list[str] = []
    seen_symbols: set[str] = set()
    variant_rows: list[dict[str, Any]] = []

    for variant in variants:
        if not isinstance(variant, dict):
            continue
        raw_gene = str(variant.get("gene_info_source_field") or variant.get("gene_symbol") or "")
        symbols = {entry.partition(":")[0].strip().upper() for entry in raw_gene.split("|")}
        symbols.add(str(variant.get("gene_symbol") or "").strip().upper())
        symbols.discard("")
        symbols = {s for s in symbols if _SYMBOL.fullmatch(s)}

        consequence = _variant_consequence(variant)
        variant_type = _variant_type_label(variant)

        row = {
            "variant_id": variant.get("id") or "",
            "chrom": variant.get("chrom") or "",
            "pos": variant.get("pos"),
            "ref": variant.get("ref") or "",
            "alt": variant.get("alt") or "",
            "variant_type": variant_type,
            "consequence": consequence,
            "gene_symbols": sorted(symbols),
            "qual": variant.get("qual"),
            "filter": variant.get("filter"),
            "is_loss_of_function": _is_loss_of_function(consequence),
            "is_gain_of_function_candidate": _is_gain_of_function(consequence),
            "source_fields": {
                "clinvar_significance": variant.get("clinvar_significance_source_field"),
                "dbsnp_rs": variant.get("dbsnp_rs_source_field"),
                "hgvs": variant.get("hgvs_source_field"),
            },
        }
        variant_rows.append(row)
        for symbol in symbols:
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                gene_symbols.append(symbol)

    gene_symbols = gene_symbols[:max_genes]

    gene_details: dict[str, dict[str, Any]] = {}
    for symbol in gene_symbols:
        try:
            gene_details[symbol] = get_gene_information(symbol)
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("Could not resolve gene %s: %s", symbol, exc)
            gene_details[symbol] = {
                "gene_symbol": symbol,
                "error": str(exc),
                "data_sources": [],
            }

    disease_associations: dict[str, Any] = {}
    if request.disease_id:
        try:
            from geneai.drug_discovery.gene_identification import search_genes_by_disease

            disease_result = search_genes_by_disease(request.disease_id, limit=max_genes)
            disease_associations = {
                "disease_id": request.disease_id,
                "disease_name": request.disease_name or disease_result.get("disease", {}).get("name", ""),
                "associated_genes": disease_result.get("genes", []),
                "data_sources": disease_result.get("data_sources", []),
            }
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("Disease association lookup unavailable: %s", exc)
            disease_associations = {
                "disease_id": request.disease_id,
                "disease_name": request.disease_name or "",
                "associated_genes": [],
                "error": str(exc),
            }

    # Cross-reference variants with disease-associated genes
    disease_gene_symbols: set[str] = set()
    for gene in disease_associations.get("associated_genes", []):
        if isinstance(gene, dict) and gene.get("gene_symbol"):
            disease_gene_symbols.add(str(gene["gene_symbol"]).upper())

    target_candidates: list[dict[str, Any]] = []
    for symbol in gene_symbols:
        detail = gene_details.get(symbol, {})
        in_disease = symbol in disease_gene_symbols
        has_lof = any(
            row["is_loss_of_function"] and symbol in row["gene_symbols"] for row in variant_rows
        )
        has_gof = any(
            row["is_gain_of_function_candidate"] and symbol in row["gene_symbols"]
            for row in variant_rows
        )

        target_candidates.append({
            "gene_symbol": symbol,
            "gene_name": detail.get("gene_name", ""),
            "ncbi_gene_id": detail.get("ncbi_gene_id", ""),
            "ensembl_gene_id": detail.get("ensembl_gene_id", ""),
            "uniprot_id": detail.get("uniprot_id", ""),
            "protein_function": detail.get("protein_function", ""),
            "subcellular_location": detail.get("subcellular_location", ""),
            "disease_associated": in_disease,
            "has_loss_of_function_variant": has_lof,
            "has_gain_of_function_candidate": has_gof,
            "variant_count": sum(1 for row in variant_rows if symbol in row["gene_symbols"]),
            "variants": [row for row in variant_rows if symbol in row["gene_symbols"]],
            "source_references": detail.get("source_references", []),
            "data_sources": detail.get("data_sources", []),
            "druggability_note": (
                "Loss-of-function or missense annotations alone do not establish "
                "a druggable target. Structural, ligand, and accessibility evidence "
                "are assessed separately in the Druggability Analysis module."
            ),
        })

    target_candidates.sort(
        key=lambda item: (
            not item["disease_associated"],
            not item["has_loss_of_function_variant"],
            -item["variant_count"],
            item["gene_symbol"],
        )
    )

    return {
        "schema_version": "4.3.1",
        "disease": disease_associations,
        "variants_mapped": variant_rows,
        "variant_count": len(variant_rows),
        "gene_count": len(gene_symbols),
        "target_candidates": target_candidates,
        "high_priority_candidates": [
            item for item in target_candidates
            if item["disease_associated"] and (item["has_loss_of_function_variant"] or item["has_gain_of_function_candidate"])
        ],
        "limitations": [
            "Variant consequence labels are reported as supplied in the VCF; they are not "
            "independently verified against a reference transcriptome.",
            "Loss-of-function or gain-of-function annotations do not imply druggability.",
            "Disease association evidence comes from Open Targets and is not clinical validation.",
            "No variant pathogenicity score is computed or implied.",
        ],
    }


# Backwards-compatible alias used by the biotech assistant tool registry.
map_mutations_to_targets = map_variants_to_targets
