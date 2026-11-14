"""Source-attributed CSV, JSON, and compact PDF exports for Phase 4.3."""
from __future__ import annotations

import csv
import io
import json
import re
import textwrap
import unicodedata
from datetime import datetime, timezone
from typing import Any


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Drop runtime-only private payloads and model objects before export."""
    clean = {key: value for key, value in result.items() if not key.startswith("_")}
    model = clean.get("ml_evaluation")
    if isinstance(model, dict):
        clean["ml_evaluation"] = {key: value for key, value in model.items() if key != "estimator"}
    return clean


def target_report_json(result: dict[str, Any]) -> bytes:
    return json.dumps(_public_result(result), ensure_ascii=False, indent=2, default=str).encode("utf-8")


def target_report_csv(result: dict[str, Any]) -> bytes:
    fields = [
        "research_rank", "gene_symbol", "gene_name", "ensembl_gene_id", "ncbi_gene_id",
        "research_priority_index", "research_priority_tier", "disease_association_score",
        "genetic_evidence_score", "literature_evidence_score", "ppi_network_score",
        "ppi_interaction_count", "ppi_degree_centrality", "ppi_max_experimental_channel_score",
        "vcf_preview_variant_count", "vcf_preview_variant_ids", "vcf_preview_variant_types",
        "uniprot_id", "protein_name", "protein_function",
        "protein_subcellular_location", "protein_domain_count", "pdb_ids_from_uniprot",
        "go_annotation_count", "source_references", "missing_evidence_domains", "source_url",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in result.get("targets", []):
        if not isinstance(row, dict):
            continue
        protein = row.get("protein") or {}
        writer.writerow({
            "research_rank": row.get("target_research_rank"),
            "gene_symbol": row.get("gene_symbol"),
            "gene_name": row.get("gene_name"),
            "ensembl_gene_id": row.get("ensembl_gene_id"),
            "ncbi_gene_id": row.get("ncbi_gene_id"),
            "research_priority_index": row.get("target_research_priority_index"),
            "research_priority_tier": row.get("target_research_priority_tier"),
            "disease_association_score": row.get("disease_association_evidence_score"),
            "genetic_evidence_score": row.get("genetic_evidence_score"),
            "literature_evidence_score": row.get("literature_evidence_score"),
            "ppi_network_score": row.get("ppi_network_score"),
            "ppi_interaction_count": row.get("ppi_interaction_count"),
            "ppi_degree_centrality": row.get("ppi_degree_centrality"),
            "ppi_max_experimental_channel_score": row.get("ppi_max_experimental_channel_score"),
            "vcf_preview_variant_count": row.get("vcf_preview_variant_count"),
            "vcf_preview_variant_ids": ";".join(str(variant.get("id", "")) for variant in row.get("vcf_preview_variants", []) if isinstance(variant, dict)),
            "vcf_preview_variant_types": ";".join(str(variant.get("variant_type", "")) for variant in row.get("vcf_preview_variants", []) if isinstance(variant, dict)),
            "uniprot_id": protein.get("uniprot_id"),
            "protein_name": protein.get("protein_name"),
            "protein_function": protein.get("function"),
            "protein_subcellular_location": protein.get("subcellular_location"),
            "protein_domain_count": len(protein.get("domains", [])),
            "pdb_ids_from_uniprot": ";".join(protein.get("pdb_ids_from_uniprot", [])),
            "go_annotation_count": row.get("go_annotation_count", 0),
            "source_references": ";".join(row.get("gene_source_references", [])),
            "missing_evidence_domains": ";".join(row.get("target_missing_evidence_domains", [])),
            "source_url": row.get("source_url"),
        })
    return output.getvalue().encode("utf-8-sig")


def target_report_text(result: dict[str, Any]) -> str:
    disease = result.get("disease") or {}
    lines = [
        "GeneAI Research — Drug Target Identification Research Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Assessment ID: {result.get('analysis_id', 'Not available')}",
        f"Disease: {disease.get('name', 'Not available')} ({disease.get('disease_id', 'ID not provided')})",
        f"Reused Phase 4.2 analysis: {result.get('disease_analysis_id') or 'not recorded'}; retrieved {result.get('disease_analysis_retrieved_at') or 'time not reported'}",
        "",
        "Target ranking method",
        str(result.get("priority_method", "Evidence-weighted research index; not validated druggability.")),
        f"Configured weights: {json.dumps(result.get('weights', {}), ensure_ascii=False)}",
        "",
        "Ranked gene and protein evidence",
    ]
    for target in result.get("targets", []):
        if not isinstance(target, dict):
            continue
        protein = target.get("protein") or {}
        lines.extend([
            f"{target.get('target_research_rank')}. {target.get('gene_symbol')} — {target.get('gene_name') or 'name unavailable'}; research index={target.get('target_research_priority_index')}; tier={target.get('target_research_priority_tier')}.",
            f"   Disease association={target.get('disease_association_evidence_score')}; genetic evidence={target.get('genetic_evidence_score')}; literature={target.get('literature_evidence_score')}; STRING support={target.get('ppi_network_score')}.",
            f"   NCBI Gene={target.get('ncbi_gene_id')}; Ensembl={target.get('ensembl_gene_id')}; UniProt={protein.get('uniprot_id')}; protein={protein.get('protein_name')}.",
            f"   Protein function={protein.get('function') or 'not returned'}; localization={protein.get('subcellular_location') or 'not returned'}; UniProt PDB references={protein.get('pdb_ids_from_uniprot', [])}.",
            f"   VCF preview overlaps={target.get('vcf_preview_variant_count', 0)}; these are source annotations, not interpreted effects.",
            f"   Missing evidence domains={target.get('target_missing_evidence_domains', [])}; source={target.get('source_url', '')}",
        ])
    network = result.get("ppi_network") or {}
    lines.extend([
        "",
        "STRING protein-association network",
        f"Network type={network.get('network_type') or (network.get('edges') or [{}])[0].get('network_type', 'not reported')}; nodes={network.get('node_count', 0)}; edges={network.get('edge_count', 0)}; hubs={network.get('hub_candidates', [])}.",
        str(network.get("interpretation", "STRING evidence is an association, not proof of a direct interaction.")),
        "Experimental channel scores are reported separately from the combined STRING score.",
        "",
        "Disease pathway context",
    ])
    pathways = (result.get("pathways") or {}).get("pathways", [])
    if pathways:
        for pathway in pathways:
            lines.append(f"{pathway.get('name')} ({pathway.get('pathway_id')}); p={pathway.get('p_value')}; FDR={pathway.get('fdr')}; source={pathway.get('source_url')}")
        lines.append("Reactome results describe the submitted disease gene set; they are not gene-specific target pathway scores.")
    else:
        lines.append("No Reactome pathway result was available in the reused disease analysis.")
    lines.extend(["", "VCF preview mutation-to-gene matches"])
    variants = result.get("mutations_from_vcf_preview", [])
    if variants:
        for variant in variants[:500]:
            lines.append(
                "Variant record=" + json.dumps({
                    key: variant.get(key) for key in (
                        "chrom", "pos", "id", "ref", "alt", "variant_type",
                        "gene_info_source_field", "consequence_source_field", "hgvs_source_field",
                        "clinvar_significance_source_field", "dbsnp_rs_source_field",
                    ) if key in variant
                }, ensure_ascii=False, default=str)
            )
        if len(variants) > 500:
            lines.append(f"PDF detail capped at 500 of {len(variants)} preview records; JSON retains the complete analysis result.")
        lines.append("These are fields carried in the Phase 3 VCF preview; this report does not infer pathogenicity or variant effects.")
    else:
        lines.append("No matching VCF-preview variant records were supplied in the disease analysis.")
    lines.extend(["", "Gene Ontology annotations"])
    annotations = [annotation for target in result.get("targets", []) if isinstance(target, dict) for annotation in target.get("go_annotations", []) if isinstance(annotation, dict)]
    if annotations:
        for annotation in annotations[:500]:
            lines.append(
                f"{annotation.get('gene_symbol', 'Gene unavailable')}: {annotation.get('go_id', 'GO ID unavailable')} "
                f"{annotation.get('go_name', annotation.get('name', 'term unavailable'))}; "
                f"evidence={annotation.get('evidence_code', 'not reported')}; source={annotation.get('source_url', '')}"
            )
        if len(annotations) > 500:
            lines.append(f"PDF annotation detail capped at 500 of {len(annotations)} records.")
    else:
        lines.append("No GO annotations were available in the reused disease analysis.")
    lines.extend(["", "Scientific publications"])
    publications = result.get("publications", [])
    if publications:
        for paper in publications[:100]:
            if not isinstance(paper, dict):
                continue
            lines.append(
                f"PMID {paper.get('pmid', 'unavailable')} · {paper.get('year') or paper.get('publication_date') or 'date unavailable'} · "
                f"{paper.get('title', 'Title unavailable')} · {paper.get('authors', 'authors unavailable')} · {paper.get('url', '')}"
            )
        if len(publications) > 100:
            lines.append(f"PDF publication detail capped at 100 of {len(publications)} records; JSON retains all returned records.")
    else:
        lines.append("No PubMed publication records were available in the reused disease analysis.")
    lines.extend(["", "Model evaluation"])
    model = result.get("ml_evaluation") or {}
    if model:
        lines.append(f"Model={model.get('model_type')}; version={model.get('model_version')}; metrics={model.get('evaluation_metrics')}; dataset={model.get('dataset_source')}; license={model.get('dataset_license')}.")
        lines.append("Model results are computational predictions and are not experimental validation or clinical probabilities.")
    else:
        lines.append("No supervised model was trained for this assessment. The app does not bundle a fabricated labeled training dataset.")
    lines.extend(["", "Sources and retrieval status"])
    for source in result.get("data_sources", []):
        lines.append(f"{source.get('source')}: {source.get('status')}; version={source.get('version', 'not reported')}; records={source.get('record_count', 0)}; {source.get('error') or source.get('reason') or ''}")
    lines.extend(["", "Limitations"])
    lines.extend(f"- {item}" for item in result.get("limitations", []))
    lines.extend(["", result.get("research_only_disclaimer", "Research use only."), ""])
    return "\n".join(lines)


def target_report_pdf(result: dict[str, Any]) -> bytes:
    text = target_report_text(result)
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        wrapped.extend(textwrap.wrap(raw_line, width=96, break_long_words=True, break_on_hyphens=False) or [""])
    pages = [wrapped[index:index + 52] for index in range(0, len(wrapped), 52)] or [["GeneAI Research Target Report"]]
    page_ids = [4 + 2 * index for index in range(len(pages))]
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for index, page in enumerate(pages):
        commands = ["BT", "/F1 9 Tf", "50 756 Td", "12 TL"]
        for line in page:
            safe = unicodedata.normalize("NFKD", line).encode("cp1252", errors="replace").decode("cp1252")
            safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({safe}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("cp1252", errors="replace")
        page_id = page_ids[index]
        objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode("ascii"),
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ])
    output = bytearray(b"%PDF-1.4\n%GeneAI\n")
    offsets = [0]
    for object_id, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def target_report_filename(disease_name: str, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(disease_name).lower()).strip("_") or "disease_targets"
    extension = extension.lstrip(".").lower()
    if extension not in {"pdf", "csv", "json"}:
        raise ValueError("Report format must be PDF, CSV, or JSON.")
    return f"geneai_{slug}_target_identification.{extension}"
