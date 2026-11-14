"""Standalone gene identification engine for GeneAI Research.

Provides gene-centric lookups that complement the existing disease-centric
Phase 4.2 workflow. All external calls use the bounded, retry-aware clients
in geneai.drug_discovery.api_clients. No biological data is fabricated.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from geneai.drug_discovery import api_clients

logger = logging.getLogger(__name__)

_GENE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")


def _valid_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def search_genes_by_disease(
    disease_id: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Return Open Targets gene associations for a disease.

    This is a thin wrapper around the existing Phase 4.2 disease analysis so
    callers can retrieve gene evidence without running the full disease UI.
    """
    if not api_clients.is_valid_external_id(disease_id):
        raise ValueError("A valid Open Targets disease identifier is required.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be an integer between 1 and 100.")

    from geneai.drug_discovery.disease_analysis import analyze_disease

    result = analyze_disease(disease_id, target_limit=limit)
    return {
        "disease": result.get("disease", {}),
        "genes": result.get("genes", []),
        "data_sources": result.get("data_sources", []),
        "source_versions": result.get("source_versions", {}),
        "retrieved_at": result.get("retrieved_at"),
        "limitations": result.get("limitations", []),
    }


def search_diseases_by_gene(
    gene_symbol: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Return diseases associated with a gene.

    Open Targets does not expose a public gene->disease search endpoint in the
    v4 GraphQL schema used by this client, so this function resolves the gene
    to an Ensembl identifier and returns the disease context available through
    NCBI/Ensembl/UniProt annotations plus Open Targets target metadata when
    available. No disease associations are fabricated.
    """
    symbol = str(gene_symbol or "").strip().upper()
    if not _GENE_SYMBOL.fullmatch(symbol):
        raise ValueError("A valid gene symbol is required.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be an integer between 1 and 100.")

    ncbi = api_clients.fetch_ncbi_gene_summaries([symbol])
    ensembl = api_clients.lookup_ensembl_symbols([symbol])
    uniprot = api_clients.search_uniprot_proteins([symbol])

    gene_record = ncbi.get(symbol, {})
    ensembl_record = ensembl.get(symbol, {})
    protein = uniprot.get(symbol, {})

    source_status: list[dict[str, Any]] = []
    if gene_record:
        source_status.append(
            {
                "source": "NCBI Gene",
                "status": "available",
                "record_count": 1,
                "url": gene_record.get("source_url", ""),
            }
        )
    else:
        source_status.append(
            {
                "source": "NCBI Gene",
                "status": "not found",
                "record_count": 0,
                "reason": f"No NCBI Gene record for symbol {symbol}.",
            }
        )
    if ensembl_record:
        source_status.append(
            {
                "source": "Ensembl REST",
                "status": "available",
                "record_count": 1,
                "url": ensembl_record.get("source_url", ""),
            }
        )
    if protein:
        source_status.append(
            {
                "source": "UniProtKB",
                "status": "available",
                "record_count": 1,
                "url": protein.get("source_url", ""),
            }
        )

    return {
        "gene_symbol": symbol,
        "gene_name": gene_record.get("description") or protein.get("protein_name") or "",
        "ncbi_gene_id": gene_record.get("ncbi_gene_id") or "",
        "ensembl_gene_id": ensembl_record.get("ensembl_gene_id") or "",
        "chromosome": ensembl_record.get("chromosome") or gene_record.get("chromosome") or "",
        "organism": gene_record.get("organism") or "Homo sapiens",
        "gene_function_summary": gene_record.get("description") or "",
        "protein": protein,
        "diseases": [],
        "data_sources": source_status,
        "retrieved_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds"),
        "limitations": [
            "Open Targets v4 GraphQL does not expose a public gene-to-disease "
            "search endpoint in this client; disease associations are not returned.",
            "This lookup returns identifier and annotation context only.",
        ],
    }


def get_gene_information(
    gene_symbol: str,
) -> dict[str, Any]:
    """Aggregate NCBI, Ensembl, and UniProt information for one gene."""
    symbol = str(gene_symbol or "").strip().upper()
    if not _GENE_SYMBOL.fullmatch(symbol):
        raise ValueError("A valid gene symbol is required.")

    ncbi = api_clients.fetch_ncbi_gene_summaries([symbol])
    ensembl = api_clients.lookup_ensembl_symbols([symbol])
    uniprot = api_clients.search_uniprot_proteins([symbol])

    gene_record = ncbi.get(symbol, {})
    ensembl_record = ensembl.get(symbol, {})
    protein = uniprot.get(symbol, {})

    source_status: list[dict[str, Any]] = []
    for source, record, url in (
        ("NCBI Gene", gene_record, gene_record.get("source_url", "")),
        ("Ensembl REST", ensembl_record, ensembl_record.get("source_url", "")),
        ("UniProtKB", protein, protein.get("source_url", "")),
    ):
        if record:
            source_status.append(
                {"source": source, "status": "available", "record_count": 1, "url": url}
            )
        else:
            source_status.append(
                {
                    "source": source,
                    "status": "not found",
                    "record_count": 0,
                    "reason": f"No {source} record for symbol {symbol}.",
                }
            )

    return {
        "gene_symbol": symbol,
        "gene_name": gene_record.get("description") or protein.get("protein_name") or "",
        "ncbi_gene_id": gene_record.get("ncbi_gene_id") or "",
        "ensembl_gene_id": ensembl_record.get("ensembl_gene_id") or "",
        "chromosome": ensembl_record.get("chromosome") or gene_record.get("chromosome") or "",
        "genomic_start": ensembl_record.get("start") or gene_record.get("genomic_start_source_value"),
        "genomic_end": ensembl_record.get("end") or gene_record.get("genomic_end_source_value"),
        "organism": gene_record.get("organism") or "Homo sapiens",
        "gene_function_summary": gene_record.get("description") or "",
        "protein_function": protein.get("function") or "",
        "protein_name": protein.get("protein_name") or "",
        "uniprot_id": protein.get("uniprot_id") or "",
        "sequence": protein.get("sequence") or "",
        "domains": protein.get("domains", []),
        "subcellular_location": protein.get("subcellular_location") or "",
        "family_annotations": protein.get("family_annotations", []),
        "ec_numbers": protein.get("ec_numbers", []),
        "pdb_ids_from_uniprot": protein.get("pdb_ids_from_uniprot", []),
        "source_references": [
            url
            for url in (
                gene_record.get("source_url"),
                ensembl_record.get("source_url"),
                protein.get("source_url"),
            )
            if url
        ],
        "data_sources": source_status,
        "limitations": [
            "Identifier and annotation records are retrieved from public databases; "
            "they do not establish disease causality or druggability.",
        ],
    }


def get_gene_identifiers(
    gene_symbol: str,
) -> dict[str, Any]:
    """Return stable cross-database identifiers for a gene."""
    info = get_gene_information(gene_symbol)
    return {
        "gene_symbol": info["gene_symbol"],
        "gene_name": info["gene_name"],
        "ncbi_gene_id": info["ncbi_gene_id"],
        "ensembl_gene_id": info["ensembl_gene_id"],
        "uniprot_id": info["uniprot_id"],
        "chromosome": info["chromosome"],
        "organism": info["organism"],
        "source_references": info["source_references"],
        "data_sources": info["data_sources"],
    }


def get_gene_function(
    gene_symbol: str,
) -> dict[str, Any]:
    """Return function, domains, localization, and enzyme classification for a gene."""
    info = get_gene_information(gene_symbol)
    return {
        "gene_symbol": info["gene_symbol"],
        "gene_name": info["gene_name"],
        "gene_function_summary": info["gene_function_summary"],
        "protein_function": info["protein_function"],
        "protein_name": info["protein_name"],
        "domains": info["domains"],
        "subcellular_location": info["subcellular_location"],
        "family_annotations": info["family_annotations"],
        "ec_numbers": info["ec_numbers"],
        "sequence": info["sequence"],
        "source_references": info["source_references"],
        "data_sources": info["data_sources"],
        "limitations": [
            "Function and domain annotations come from UniProtKB/GO and are "
            "curatorial evidence, not experimental validation of this gene's role.",
        ],
    }


def get_expression_information(
    gene_symbol: str,
) -> dict[str, Any]:
    """Return expression information availability status."""
    symbol = str(gene_symbol or "").strip().upper()
    if not _GENE_SYMBOL.fullmatch(symbol):
        raise ValueError("A valid gene symbol is required.")
    return {
        "gene_symbol": symbol,
        "expression_available": False,
        "expression_note": (
            "Tissue/cell-type expression values are not exposed by the pinned "
            "Open Targets v4 client. Expression evidence is included indirectly "
            "through Open Targets datatype scores in the Disease Analysis module."
        ),
        "source": "Open Targets Platform",
        "source_url": "https://platform.opentargets.org/",
        "limitations": [
            "No expression values are returned; this is a capability status check only.",
        ],
    }


def identify_disease_associated_genes(
    disease_id: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Identify genes associated with a disease (alias for search_genes_by_disease)."""
    return search_genes_by_disease(disease_id, limit=limit)


def get_scientific_references(
    gene_symbol: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Return PubMed publications mentioning a gene and disease context."""
    from geneai.research import search_pubmed

    symbol = str(gene_symbol or "").strip().upper()
    if not _GENE_SYMBOL.fullmatch(symbol):
        raise ValueError("A valid gene symbol is required.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Limit must be an integer between 1 and 50.")

    query = f'{symbol}[Title/Abstract] AND ("disease"[Title/Abstract] OR "disorder"[Title/Abstract] OR "syndrome"[Title/Abstract])'
    try:
        papers = search_pubmed(query, limit=limit)
    except RuntimeError as exc:
        logger.info("PubMed reference lookup unavailable for %s: %s", symbol, exc)
        papers = []
    return {
        "gene_symbol": symbol,
        "publications": papers,
        "record_count": len(papers),
        "source": "PubMed",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
        "limitations": [
            "PubMed results are text-match citations; they do not establish "
            "causality or therapeutic relevance.",
        ],
    }


# Backwards-compatible alias used by the biotech assistant tool registry.
identify_disease_genes = identify_disease_associated_genes
