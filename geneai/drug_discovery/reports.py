"""Downloadable disease research exports without extra runtime dependencies."""
from __future__ import annotations

import csv
import io
import json
import re
import textwrap
import unicodedata
from datetime import datetime, timezone
from typing import Any


def disease_report_json(result: dict[str, Any]) -> bytes:
    """Serialize a complete retrieved evidence snapshot as UTF-8 JSON."""
    return json.dumps(result, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def disease_report_csv(result: dict[str, Any]) -> bytes:
    """Export one row per associated gene, including source-backed evidence fields."""
    output = io.StringIO(newline="")
    columns = [
        "disease_id", "disease_name", "disease_category", "gene_symbol", "gene_name",
        "ncbi_gene_id", "ensembl_gene_id", "chromosome", "association_score",
        "research_priority_index", "research_priority_tier", "evidence_sources", "source_url",
    ]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    disease = result.get("disease") or {}
    for gene in result.get("genes", []):
        writer.writerow(
            {
                "disease_id": disease.get("disease_id"),
                "disease_name": disease.get("name"),
                "disease_category": result.get("inputs", {}).get("disease_category"),
                "gene_symbol": gene.get("gene_symbol"),
                "gene_name": gene.get("gene_name"),
                "ncbi_gene_id": gene.get("ncbi_gene_id"),
                "ensembl_gene_id": gene.get("ensembl_gene_id"),
                "chromosome": gene.get("chromosome"),
                "association_score": gene.get("association_score"),
                "research_priority_index": gene.get("research_priority_index"),
                "research_priority_tier": gene.get("research_priority_tier"),
                "evidence_sources": "; ".join(gene.get("evidence_sources", [])),
                "source_url": gene.get("source_url"),
            }
        )
    return output.getvalue().encode("utf-8-sig")


def disease_report_text(result: dict[str, Any]) -> str:
    """Build a source-attributed, research-only report body."""
    disease = result.get("disease") or {}
    lines = [
        "GeneAI Research — Disease Analysis Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Analysis ID: {result.get('analysis_id', 'Not available')}",
        "",
        "Research use only. This report is not a diagnosis, treatment recommendation, or clinical interpretation.",
        "",
        "1. Disease overview",
        f"Disease: {disease.get('name', 'Not available')}",
        f"Disease ID: {disease.get('disease_id', disease.get('id', 'Not available'))}",
        f"Category: {result.get('inputs', {}).get('disease_category', 'Not specified')}",
        f"Description: {disease.get('description') or 'Not provided by the selected source.'}",
        f"Source: {disease.get('source', 'Open Targets Platform')} — {disease.get('source_url', '')}",
        "",
        "2. Associated genes and target evidence",
    ]
    genes = result.get("genes", [])
    if not genes:
        lines.append("No matching genes were returned for the selected filters and result limit.")
    for gene in genes:
        lines.append(
            f"{gene.get('gene_symbol', 'Unknown')} — {gene.get('gene_name', '')}; "
            f"NCBI Gene: {gene.get('ncbi_gene_id') or 'not available'}; "
            f"Ensembl: {gene.get('ensembl_gene_id') or 'not available'}; "
            f"association score: {gene.get('association_score') if gene.get('association_score') is not None else 'not available'}; "
            f"research index: {gene.get('research_priority_index') if gene.get('research_priority_index') is not None else 'not scored'}"
        )
        lines.append(f"  Evidence sources: {', '.join(gene.get('evidence_sources', [])) or 'not reported'}")
        lines.append(f"  Source record: {gene.get('source_url', '')}")
        if gene.get("gene_function_summary"):
            lines.append(f"  NCBI Gene summary: {gene['gene_function_summary']}")
    lines.extend(["", "3. Associated proteins"])
    proteins = result.get("proteins", [])
    if not proteins:
        lines.append("No reviewed UniProt proteins were returned for the selected targets.")
    for protein in proteins:
        lines.append(
            f"{protein.get('gene_symbol', '')} — {protein.get('protein_name', 'Not available')} "
            f"({protein.get('uniprot_id', 'accession not available')}); length: {protein.get('sequence_length') or 'not available'} aa"
        )
        if protein.get("function"):
            lines.append(f"  UniProt function: {protein['function']}")
        if protein.get("subcellular_location"):
            lines.append(f"  UniProt location: {protein['subcellular_location']}")
        lines.append(f"  Source record: {protein.get('source_url', '')}")
    lines.extend(["", "4. Mutations reported in supplied Phase 3 preview"])
    variants = result.get("mutations", [])
    if not variants:
        lines.append("No matching variant was present in the current VCF preview. No external mutation assertion was inferred.")
    for variant in variants:
        lines.append(
            f"{variant.get('chrom')}:{variant.get('pos')} {variant.get('ref')}>{variant.get('alt')} "
            f"ID={variant.get('id')}; source annotation={variant.get('clinvar_significance_source_field') or 'not present'}"
        )
    lines.extend(["", "5. Pathway enrichment"])
    pathways = result.get("pathways", {}).get("pathways", [])
    if not pathways:
        lines.append("No Reactome enrichment results are available.")
    for pathway in pathways:
        lines.append(
            f"{pathway.get('name', 'Unnamed pathway')} ({pathway.get('pathway_id', 'ID unavailable')}); "
            f"p-value={pathway.get('p_value')}; FDR={pathway.get('fdr')}; "
            f"genes found={pathway.get('genes_found')}; {pathway.get('source_url', '')}"
        )
    lines.append(result.get("pathways", {}).get("warning", "Pathway results are source-reported enrichment and do not establish mechanism."))
    lines.extend(["", "6. Gene Ontology annotations"])
    annotations = result.get("go_annotations", [])
    if not annotations:
        lines.append("No QuickGO annotations were available.")
    for annotation in annotations:
        lines.append(
            f"{annotation.get('gene_symbol', '')}: {annotation.get('go_id', '')} "
            f"({annotation.get('aspect', '')}); evidence={annotation.get('evidence_code', '')}; "
            f"reference={annotation.get('reference', '')}; {annotation.get('source_url', '')}"
        )
    lines.extend(["", "7. Protein structures"])
    structures = result.get("structures", [])
    if not structures:
        lines.append("No RCSB structure records were returned for the retrieved protein accessions.")
    for structure in structures:
        lines.append(f"{structure.get('pdb_id')}: {structure.get('source_url', '')}")
    lines.extend(["", "8. Research publications"])
    publications = result.get("publications", [])
    if not publications:
        lines.append("No PubMed records were returned for the generated query.")
    for paper in publications:
        lines.append(
            f"PMID {paper.get('pmid')}; {paper.get('title', 'Title unavailable')}; "
            f"{paper.get('authors', '')}; {paper.get('year', '')}; {paper.get('url', '')}"
        )
        if paper.get("abstract"):
            lines.append(f"  Abstract retrieved from PubMed: {paper['abstract']}")
    lines.extend(["", "9. Mechanism evidence and interpretation limits"])
    for evidence in result.get("mechanism_evidence", [])[:100]:
        lines.append(
            f"{evidence.get('gene_symbol')} — {evidence.get('evidence_type')}: "
            f"source score {evidence.get('source_score')}; {evidence.get('interpretation')} {evidence.get('source_url', '')}"
        )
    lines.extend(["", "10. Potential research targets"])
    lines.append("Genes are ordered by a configurable research-priority heuristic based on the available Open Targets datatype scores.")
    lines.append("The heuristic is not druggability, efficacy, safety, or clinical confidence.")
    lines.extend(["", "11. Data source status and versions"])
    for source in result.get("data_sources", []):
        lines.append(f"{source.get('source')}: {source.get('status')}; version={source.get('version', 'not reported')}; records={source.get('record_count', 0)}")
        if source.get("error"):
            lines.append(f"  Error: {source['error']}")
    lines.extend(["", "12. Limitations"])
    for limitation in result.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.extend(["", result.get("research_only_disclaimer", "Research use only."), ""])
    return "\n".join(lines)


def disease_report_pdf(result: dict[str, Any]) -> bytes:
    """Create a compact, dependency-free text PDF suitable for an 8 GB laptop."""
    text = disease_report_text(result)
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(raw_line, width=96, break_long_words=True, break_on_hyphens=False) or [""])
    page_lines = [wrapped[index:index + 52] for index in range(0, len(wrapped), 52)] or [["GeneAI Research Disease Report"]]

    objects: list[bytes] = []
    page_object_ids = [4 + 2 * index for index in range(len(page_lines))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_lines)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for index, lines in enumerate(page_lines):
        page_object_id = page_object_ids[index]
        stream_object_id = page_object_id + 1
        commands = ["BT", "/F1 9 Tf", "50 756 Td", "12 TL"]
        for line in lines:
            normalized = unicodedata.normalize("NFKD", line)
            safe = normalized.encode("cp1252", errors="replace").decode("cp1252")
            safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({safe}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("cp1252", errors="replace")
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_object_id} 0 R >>"
        ).encode("ascii")
        objects.extend([page, b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"])

    pdf = bytearray(b"%PDF-1.4\n%GeneAI\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def report_filename(disease_name: str, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", disease_name.lower()).strip("_") or "disease_analysis"
    extension = extension.lstrip(".").lower()
    if extension not in {"pdf", "csv", "json"}:
        raise ValueError("Report format must be PDF, CSV, or JSON.")
    return f"geneai_{slug}_disease_report.{extension}"
