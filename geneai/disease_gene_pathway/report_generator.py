"""Report generation for disease-gene-pathway analysis."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from geneai.disease_gene_pathway.analysis_engine import DiseaseGenePathwayResult


def generate_dgp_pdf_report(
    result: DiseaseGenePathwayResult,
    run_id: str | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Generate comprehensive PDF report for DGP analysis."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1f4e79"),
    )
    
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4a4a4a"),
    )
    
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#1f4e79"),
    )
    
    subheading_style = ParagraphStyle(
        "CustomSubHeading",
        parent=styles["Heading3"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#2e75b6"),
    )
    
    normal_style = styles["Normal"]
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )
    
    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 30 * mm))
    elements.append(Paragraph("Disease-Gene-Pathway Network Analysis Report", title_style))
    elements.append(Spacer(1, 5 * mm))
    
    if run_id:
        elements.append(Paragraph(f"Run ID: {run_id}", subtitle_style))
    
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))
    elements.append(Spacer(1, 10 * mm))
    
    # Summary table
    summary = result.summary
    summary_data = [
        ["Metric", "Value"],
        ["Input Genes", str(summary.get("total_input_genes", 0))],
        ["Input Diseases", str(len(result.input_diseases))],
        ["Network Nodes", str(summary.get("network_nodes", 0))],
        ["Network Edges", str(summary.get("network_edges", 0))],
        ["Hub Genes Identified", str(summary.get("hub_genes_count", 0))],
        ["Disease Associations (OpenTargets)", str(summary.get("disease_associations_count", 0))],
        ["Disease Associations (DisGeNET)", str(summary.get("disgenet_associations_count", 0))],
        ["KEGG Pathways", str(summary.get("kegg_pathways_count", 0))],
        ["Reactome Pathways", str(summary.get("reactome_pathways_count", 0))],
        ["GO Enriched Terms", str(summary.get("go_terms_enriched", 0))],
        ["STRING Enrichment Terms", str(summary.get("string_enrichment_terms", 0))],
        ["Reactome Enriched Pathways", str(summary.get("reactome_enriched_pathways", 0))],
        ["Therapeutic Targets", str(summary.get("therapeutic_targets_count", 0))],
    ]
    
    summary_table = Table(summary_data, colWidths=[80 * mm, 40 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
    ]))
    elements.append(summary_table)
    elements.append(PageBreak())
    
    # ===== INPUT GENES =====
    elements.append(Paragraph("1. Input Genes", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if result.input_genes:
        gene_data = [["Gene Symbol"]]
        for gene in sorted(result.input_genes):
            gene_data.append([gene])
        
        # Split into columns for readability
        cols = 4
        rows = (len(gene_data) + cols - 1) // cols
        table_data = []
        for i in range(rows):
            row = []
            for j in range(cols):
                idx = i + j * rows
                if idx < len(gene_data):
                    row.append(gene_data[idx][0])
                else:
                    row.append("")
            table_data.append(row)
        
        gene_table = Table(table_data, colWidths=[40 * mm] * cols)
        gene_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(gene_table)
    else:
        elements.append(Paragraph("No input genes provided.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== HUB GENES =====
    elements.append(Paragraph("2. Hub Genes & Network Analysis", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if result.hub_genes:
        hub_data = [
            ["Gene", "Degree", "Betweenness", "Clustering", "Hub", "Diseases", "Pathways", "UniProt"],
        ]
        for hub in result.hub_genes[:30]:  # Top 30
            diseases = len(hub.disease_associations)
            pathways = len(hub.pathways)
            hub_data.append([
                hub.gene_symbol,
                str(hub.degree),
                f"{hub.betweenness_centrality:.4f}",
                f"{hub.clustering_coefficient:.4f}",
                "Yes" if hub.is_hub else "No",
                str(diseases),
                str(pathways),
                hub.uniprot_id or "N/A",
            ])
        
        hub_table = Table(hub_data, colWidths=[20*mm, 15*mm, 20*mm, 20*mm, 15*mm, 15*mm, 15*mm, 25*mm])
        hub_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(hub_table)
    else:
        elements.append(Paragraph("No hub genes identified.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== THERAPEUTIC TARGETS =====
    elements.append(Paragraph("3. Potential Therapeutic Targets", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if result.therapeutic_targets:
        target_data = [
            ["Rank", "Gene", "Score", "Degree", "Betweenness", "Diseases", "Pathways", "Key Reasons"],
        ]
        for target in result.therapeutic_targets[:20]:
            reasons = "; ".join(target.get("reasons", [])[:2])
            target_data.append([
                str(target.get("rank", "")),
                target.get("gene_symbol", ""),
                f"{target.get('score', 0):.3f}",
                str(target.get("degree", 0)),
                f"{target.get('betweenness', 0):.4f}",
                str(target.get("disease_count", 0)),
                str(target.get("pathway_count", 0)),
                reasons[:100] + "..." if len(reasons) > 100 else reasons,
            ])
        
        target_table = Table(target_data, colWidths=[10*mm, 18*mm, 15*mm, 15*mm, 20*mm, 15*mm, 15*mm, 47*mm])
        target_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(target_table)
    else:
        elements.append(Paragraph("No therapeutic targets identified.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== DISEASE ASSOCIATIONS =====
    elements.append(Paragraph("4. Disease-Gene Associations", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    # OpenTargets
    if result.disease_gene_associations:
        elements.append(Paragraph("4.1 OpenTargets Associations", subheading_style))
        ot_data = [["Disease", "Gene", "Score", "Data Sources", "Evidence Count"]]
        for assoc in sorted(result.disease_gene_associations, key=lambda x: -x.score)[:30]:
            ot_data.append([
                assoc.disease_name[:40],
                assoc.gene_symbol,
                f"{assoc.score:.3f}",
                ", ".join(assoc.datasources[:3]),
                str(assoc.evidence_count),
            ])
        
        ot_table = Table(ot_data, colWidths=[40*mm, 20*mm, 15*mm, 35*mm, 20*mm])
        ot_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(ot_table)
        elements.append(Spacer(1, 6 * mm))
    
    # DisGeNET
    if result.disgenet_associations:
        elements.append(Paragraph("4.2 DisGeNET Associations", subheading_style))
        dg_data = [["Disease", "Gene", "Score", "EI", "PMIDs", "SNPs"]]
        for assoc in sorted(result.disgenet_associations, key=lambda x: -x.score)[:30]:
            dg_data.append([
                assoc.disease_name[:40],
                assoc.gene_symbol,
                f"{assoc.score:.3f}",
                f"{assoc.ei:.3f}",
                str(assoc.n_pmids),
                str(len(assoc.snps)),
            ])
        
        dg_table = Table(dg_data, colWidths=[40*mm, 20*mm, 15*mm, 15*mm, 15*mm, 15*mm])
        dg_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(dg_table)
    
    elements.append(PageBreak())
    
    # ===== PATHWAYS =====
    elements.append(Paragraph("5. Pathway Analysis", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    # KEGG
    if result.kegg_pathways:
        elements.append(Paragraph("5.1 KEGG Pathways", subheading_style))
        kegg_data = [["Pathway ID", "Name", "Category", "Genes"]]
        for pw in result.kegg_pathways[:20]:
            kegg_data.append([
                pw.pathway_id,
                pw.name[:50],
                pw.category[:30],
                str(len(pw.genes)),
            ])
        
        kegg_table = Table(kegg_data, colWidths=[25*mm, 50*mm, 35*mm, 15*mm])
        kegg_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(kegg_table)
        elements.append(Spacer(1, 6 * mm))
    
    # Reactome
    if result.reactome_pathways:
        elements.append(Paragraph("5.2 Reactome Pathways", subheading_style))
        reactome_data = [["Pathway ID", "Name", "Species", "Genes", "P-value", "FDR"]]
        for pw in result.reactome_pathways[:20]:
            reactome_data.append([
                pw.pathway_id,
                pw.name[:50],
                pw.species[:20],
                str(len(pw.genes)),
                f"{pw.p_value:.2e}" if pw.p_value else "N/A",
                f"{pw.fdr:.2e}" if pw.fdr else "N/A",
            ])
        
        reactome_table = Table(reactome_data, colWidths=[25*mm, 45*mm, 25*mm, 15*mm, 20*mm, 20*mm])
        reactome_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(reactome_table)
    
    elements.append(PageBreak())
    
    # ===== GO ENRICHMENT =====
    elements.append(Paragraph("6. Gene Ontology Enrichment", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    aspect_names = {"P": "Biological Process", "F": "Molecular Function", "C": "Cellular Component"}
    
    for aspect, terms in result.go_enrichment.items():
        if not terms:
            continue
        elements.append(Paragraph(f"6.{list(result.go_enrichment.keys()).index(aspect)+1} {aspect_names.get(aspect, aspect)}", subheading_style))
        
        go_data = [["GO ID", "Term", "Gene Count", "Genes"]]
        for term in terms[:15]:
            go_data.append([
                term.get("go_id", ""),
                term.get("go_name", "")[:60],
                str(term.get("gene_count", 0)),
                ", ".join(term.get("genes", [])[:5]),
            ])
        
        go_table = Table(go_data, colWidths=[25*mm, 55*mm, 20*mm, 40*mm])
        go_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(go_table)
        elements.append(Spacer(1, 4 * mm))
    
    elements.append(PageBreak())
    
    # ===== STRING ENRICHMENT =====
    if result.string_enrichment:
        elements.append(Paragraph("7. STRING Functional Enrichment", heading_style))
        elements.append(Spacer(1, 2 * mm))
        
        string_data = [["Category", "Term", "Description", "P-value", "FDR", "Input Genes"]]
        for term in result.string_enrichment[:20]:
            string_data.append([
                term.get("category", ""),
                term.get("term", "")[:30],
                term.get("description", "")[:50],
                f"{term.get('p_value', 1):.2e}",
                f"{term.get('fdr', 1):.2e}",
                str(term.get("input_genes", 0)),
            ])
        
        string_table = Table(string_data, colWidths=[20*mm, 25*mm, 45*mm, 20*mm, 20*mm, 15*mm])
        string_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(string_table)
        elements.append(PageBreak())
    
    # ===== LIMITATIONS =====
    elements.append(Paragraph("8. Limitations & Disclaimers", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    limitations = [
        "This analysis is based on computational predictions and database queries, not experimental validation.",
        "Disease-gene associations from OpenTargets and DisGeNET represent literature-curated and predicted relationships with varying evidence levels.",
        "Protein-protein interactions from STRING include both experimental and predicted interactions; confidence scores should be considered.",
        "Pathway enrichment analyses use hypergeometric tests and may not account for pathway topology or gene-gene correlations.",
        "GO enrichment is computed from annotations and may be biased by annotation completeness.",
        "Therapeutic target predictions are heuristic and based on network centrality and disease associations; they do not guarantee druggability or clinical efficacy.",
        "Results should be interpreted in the context of the specific research question and validated experimentally.",
        "Database versions and API responses may change over time; results reflect data at the time of analysis.",
    ]
    
    for lim in limitations:
        elements.append(Paragraph(f"• {lim}", small_style))
        elements.append(Spacer(1, 1 * mm))
    
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        "This report is generated by GeneAI Research Platform for research purposes only. "
        "It does not provide clinical recommendations or validated therapeutic targets.",
        small_style,
    ))
    
    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    if output_path:
        Path(output_path).write_bytes(pdf_bytes)
        logger.info("DGP PDF report saved to %s", output_path)
    
    return pdf_bytes


def generate_dgp_csv_report(
    result: DiseaseGenePathwayResult,
    run_id: str | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate CSV report for DGP analysis."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Metadata
    writer.writerow(["Disease-Gene-Pathway Network Analysis Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    if run_id:
        writer.writerow(["Run ID", run_id])
    writer.writerow([])
    
    # Summary
    writer.writerow(["Summary"])
    writer.writerow(["Metric", "Value"])
    for key, value in result.summary.items():
        writer.writerow([key.replace("_", " ").title(), value])
    writer.writerow([])
    
    # Input genes
    writer.writerow(["Input Genes"])
    writer.writerow(["Gene Symbol"])
    for gene in sorted(result.input_genes):
        writer.writerow([gene])
    writer.writerow([])
    
    # Hub genes
    writer.writerow(["Hub Genes"])
    writer.writerow(["Gene", "Degree", "Betweenness", "Clustering", "Is Hub", "Disease Count", "Pathway Count", "UniProt ID"])
    for hub in result.hub_genes:
        writer.writerow([
            hub.gene_symbol,
            hub.degree,
            f"{hub.betweenness_centrality:.6f}",
            f"{hub.clustering_coefficient:.6f}",
            "Yes" if hub.is_hub else "No",
            len(hub.disease_associations),
            len(hub.pathways),
            hub.uniprot_id or "",
        ])
    writer.writerow([])
    
    # Therapeutic targets
    writer.writerow(["Therapeutic Targets"])
    writer.writerow(["Rank", "Gene", "Score", "Degree", "Betweenness", "Diseases", "Pathways", "Reasons"])
    for target in result.therapeutic_targets:
        writer.writerow([
            target.get("rank", ""),
            target.get("gene_symbol", ""),
            f"{target.get('score', 0):.6f}",
            target.get("degree", 0),
            f"{target.get('betweenness', 0):.6f}",
            target.get("disease_count", 0),
            target.get("pathway_count", 0),
            "; ".join(target.get("reasons", [])),
        ])
    writer.writerow([])
    
    # Disease associations (OpenTargets)
    writer.writerow(["OpenTargets Disease Associations"])
    writer.writerow(["Disease ID", "Disease Name", "Gene", "Score", "Data Sources", "Evidence Count"])
    for assoc in result.disease_gene_associations:
        writer.writerow([
            assoc.disease_id,
            assoc.disease_name,
            assoc.gene_symbol,
            f"{assoc.score:.6f}",
            "; ".join(assoc.datasources),
            assoc.evidence_count,
        ])
    writer.writerow([])
    
    # DisGeNET associations
    writer.writerow(["DisGeNET Associations"])
    writer.writerow(["Disease ID", "Disease Name", "Disease Type", "Gene", "Score", "EI", "PMIDs", "SNPs"])
    for assoc in result.disgenet_associations:
        writer.writerow([
            assoc.disease_id,
            assoc.disease_name,
            assoc.disease_type,
            assoc.gene_symbol,
            f"{assoc.score:.6f}",
            f"{assoc.ei:.6f}",
            assoc.n_pmids,
            "; ".join(assoc.snps),
        ])
    writer.writerow([])
    
    # KEGG pathways
    writer.writerow(["KEGG Pathways"])
    writer.writerow(["Pathway ID", "Name", "Description", "Category", "Genes"])
    for pw in result.kegg_pathways:
        writer.writerow([
            pw.pathway_id,
            pw.name,
            pw.description,
            pw.category,
            "; ".join(pw.genes),
        ])
    writer.writerow([])
    
    # Reactome pathways
    writer.writerow(["Reactome Pathways"])
    writer.writerow(["Pathway ID", "Name", "Species", "Genes", "P-value", "FDR", "Entities Found", "Entities Total", "Ratio"])
    for pw in result.reactome_pathways:
        writer.writerow([
            pw.pathway_id,
            pw.name,
            pw.species,
            "; ".join(pw.genes),
            f"{pw.p_value:.6e}" if pw.p_value else "",
            f"{pw.fdr:.6e}" if pw.fdr else "",
            pw.entities_found or "",
            pw.entities_total or "",
            f"{pw.entities_ratio:.6f}" if pw.entities_ratio else "",
        ])
    writer.writerow([])
    
    # GO enrichment
    for aspect, terms in result.go_enrichment.items():
        aspect_name = {"P": "Biological Process", "F": "Molecular Function", "C": "Cellular Component"}.get(aspect, aspect)
        writer.writerow([f"GO Enrichment - {aspect_name}"])
        writer.writerow(["GO ID", "Term", "Aspect", "Gene Count", "Genes"])
        for term in terms:
            writer.writerow([
                term.get("go_id", ""),
                term.get("go_name", ""),
                aspect,
                term.get("gene_count", 0),
                "; ".join(term.get("genes", [])),
            ])
        writer.writerow([])
    
    # STRING enrichment
    writer.writerow(["STRING Enrichment"])
    writer.writerow(["Category", "Term", "Description", "P-value", "FDR", "Input Genes", "Background Genes", "Preferred Names"])
    for term in result.string_enrichment:
        writer.writerow([
            term.get("category", ""),
            term.get("term", ""),
            term.get("description", ""),
            f"{term.get('p_value', 1):.6e}",
            f"{term.get('fdr', 1):.6e}",
            term.get("input_genes", 0),
            term.get("background_genes", 0),
            "; ".join(term.get("preferred_names", [])),
        ])
    
    csv_string = output.getvalue()
    output.close()
    
    if output_path:
        Path(output_path).write_text(csv_string, encoding="utf-8")
        logger.info("DGP CSV report saved to %s", output_path)
    
    return csv_string


def generate_dgp_json_report(
    result: DiseaseGenePathwayResult,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Generate JSON-serializable report."""
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "run_id": run_id,
            "input_genes": result.input_genes,
            "input_diseases": result.input_diseases,
        },
        "summary": result.summary,
        "hub_genes": [
            {
                "gene_symbol": h.gene_symbol,
                "gene_id": h.gene_id,
                "uniprot_id": h.uniprot_id,
                "degree": h.degree,
                "betweenness_centrality": h.betweenness_centrality,
                "clustering_coefficient": h.clustering_coefficient,
                "is_hub": h.is_hub,
                "disease_count": len(h.disease_associations),
                "pathway_count": len(h.pathways),
                "diseases": [
                    {
                        "disease_id": a.disease_id,
                        "disease_name": a.disease_name,
                        "score": a.score,
                    }
                    for a in h.disease_associations
                ],
                "pathways": h.pathways,
            }
            for h in result.hub_genes
        ],
        "therapeutic_targets": result.therapeutic_targets,
        "disease_gene_associations": [
            {
                "disease_id": a.disease_id,
                "disease_name": a.disease_name,
                "gene_symbol": a.gene_symbol,
                "gene_id": a.gene_id,
                "score": a.score,
                "datasources": a.datasources,
                "evidence_count": a.evidence_count,
            }
            for a in result.disease_gene_associations
        ],
        "disgenet_associations": [
            {
                "disease_id": a.disease_id,
                "disease_name": a.disease_name,
                "disease_type": a.disease_type,
                "gene_symbol": a.gene_symbol,
                "gene_id": a.gene_id,
                "score": a.score,
                "ei": a.ei,
                "year_initial": a.year_initial,
                "year_final": a.year_final,
                "n_pmids": a.n_pmids,
                "snps": a.snps,
            }
            for a in result.disgenet_associations
        ],
        "kegg_pathways": [
            {
                "pathway_id": p.pathway_id,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "genes": p.genes,
            }
            for p in result.kegg_pathways
        ],
        "reactome_pathways": [
            {
                "pathway_id": p.pathway_id,
                "name": p.name,
                "species": p.species,
                "genes": p.genes,
                "p_value": p.p_value,
                "fdr": p.fdr,
            }
            for p in result.reactome_pathways
        ],
        "go_enrichment": result.go_enrichment,
        "string_enrichment": result.string_enrichment,
        "network": {
            "nodes": result.gene_network.number_of_nodes(),
            "edges": result.gene_network.number_of_edges(),
        },
    }