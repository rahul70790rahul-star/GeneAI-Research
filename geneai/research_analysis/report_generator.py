"""Advanced report generation for research paper analysis."""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem

from geneai.research_analysis.paper_analyzer import (
    PaperMetadata,
    ExtractedEntities,
    StructuredSummary,
    DrugTargetRelationship,
)
from geneai.research_analysis.gap_identification import GapAnalysisResult, ResearchGap
from geneai.research_analysis.paper_comparison import PaperComparison

logger = logging.getLogger(__name__)


def generate_analysis_report_csv(
    analyzed_papers: list[dict[str, Any]],
    output_path: str | Path,
) -> str:
    """Generate CSV report from analyzed papers."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for paper in analyzed_papers:
        metadata = paper.get("metadata", {})
        entities = paper.get("entities", {})
        summary = paper.get("summary", {})
        dt_rels = paper.get("drug_target_relationships", [])

        row = {
            "pmid": metadata.get("pmid", ""),
            "pmcid": metadata.get("pmcid", ""),
            "doi": metadata.get("doi", ""),
            "openalex_id": metadata.get("openalex_id", ""),
            "title": metadata.get("title", ""),
            "authors": metadata.get("authors", ""),
            "journal": metadata.get("journal", ""),
            "year": metadata.get("year", ""),
            "source": metadata.get("source", ""),
            "url": metadata.get("url", ""),
            "is_open_access": metadata.get("is_open_access", False),
            "citation_count": metadata.get("citation_count", 0),
            "concepts": "; ".join(metadata.get("concepts", [])),
            "abstract": metadata.get("abstract", "")[:500] if metadata.get("abstract") else "",
            "objectives": "; ".join(summary.get("objectives", [])),
            "methodology": "; ".join(summary.get("methodology", [])),
            "key_findings": "; ".join(summary.get("key_findings", [])),
            "results": "; ".join(summary.get("results", [])),
            "conclusions": "; ".join(summary.get("conclusions", [])),
            "limitations": "; ".join(summary.get("limitations", [])),
            "future_work": "; ".join(summary.get("future_work", [])),
            "experimental_models": "; ".join(summary.get("experimental_models", [])),
            "sample_sizes": "; ".join(summary.get("sample_sizes", [])),
            "statistical_methods": "; ".join(summary.get("statistical_methods", [])),
            "genes": "; ".join([g.get("symbol", "") for g in entities.get("genes", [])]),
            "proteins": "; ".join([p.get("name", "") for p in entities.get("proteins", [])]),
            "diseases": "; ".join([d.get("name", "") for d in entities.get("diseases", [])]),
            "drugs": "; ".join([d.get("name", "") for d in entities.get("drugs", [])]),
            "pathways": "; ".join([p.get("name", "") for p in entities.get("pathways", [])]),
            "mutations": "; ".join([m.get("variant", "") for m in entities.get("mutations", [])]),
            "biomarkers": "; ".join([b.get("name", "") for b in entities.get("biomarkers", [])]),
            "drug_target_relationships": "; ".join([
                f"{r.get('drug_name', '')}->{r.get('target_name', '')} ({r.get('relationship_type', '')})"
                for r in dt_rels
            ]),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    logger.info("CSV report saved to %s", output_path)
    return str(output_path)


def generate_analysis_report_json(
    analyzed_papers: list[dict[str, Any]],
    output_path: str | Path,
    include_full_text: bool = False,
) -> str:
    """Generate JSON report from analyzed papers."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "research_paper_analysis",
            "version": "1.0",
            "total_papers": len(analyzed_papers),
        },
        "papers": [],
    }

    for paper in analyzed_papers:
        paper_data = paper.copy()
        if not include_full_text:
            paper_data.pop("metadata", {}).pop("full_text", None)
        report["papers"].append(paper_data)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("JSON report saved to %s", output_path)
    return str(output_path)


def generate_gap_report_csv(
    gap_analysis: GapAnalysisResult,
    output_path: str | Path,
) -> str:
    """Generate CSV report from gap analysis."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for gap in gap_analysis.gaps:
        rows.append({
            "gap_type": gap.gap_type,
            "description": gap.description,
            "entities_involved": "; ".join(gap.entities_involved),
            "supporting_papers": "; ".join(gap.supporting_papers),
            "confidence": gap.confidence,
            "evidence_summary": gap.evidence_summary,
            "suggested_experiments": "; ".join(gap.suggested_experiments),
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    logger.info("Gap analysis CSV report saved to %s", output_path)
    return str(output_path)


def generate_comparison_report_csv(
    comparison: PaperComparison,
    output_path: str | Path,
) -> str:
    """Generate CSV report from paper comparison."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if comparison.comparison_table is not None:
        comparison.comparison_table.to_csv(output_path, index=False)
    else:
        # Create a basic CSV from similarities/differences
        rows = []
        for key, items in comparison.similarities.items():
            for item in items:
                rows.append({
                    "category": "similarity",
                    "subcategory": key,
                    "detail": str(item),
                })
        for key, paper_items in comparison.differences.items():
            for paper, items in paper_items.items():
                for item in items:
                    rows.append({
                        "category": "difference",
                        "subcategory": key,
                        "paper": paper,
                        "detail": item,
                    })
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)

    logger.info("Comparison CSV report saved to %s", output_path)
    return str(output_path)


def generate_pdf_report(
    analyzed_papers: list[dict[str, Any]],
    gap_analysis: GapAnalysisResult | None = None,
    comparison: PaperComparison | None = None,
    output_path: str | Path = "research_analysis_report.pdf",
    title: str = "GeneAI Research Paper Analysis Report",
) -> str:
    """Generate professional PDF report."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        spaceBefore=12,
    )
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=12,
        spaceAfter=8,
        spaceBefore=8,
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontSize=10,
        leftIndent=20,
        spaceAfter=4,
    )

    story = []

    # Title page
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}",
        styles['Normal']
    ))
    story.append(Paragraph(
        f"Total Papers Analyzed: {len(analyzed_papers)}",
        styles['Normal']
    ))
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "<b>Disclaimer:</b> This report is a computational analysis aid. "
        "It does not provide validated scientific conclusions, clinical recommendations, "
        "or treatment guidance. All findings require expert review and experimental validation.",
        ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
    ))
    story.append(PageBreak())

    # Table of Contents
    story.append(Paragraph("Table of Contents", heading_style))
    story.append(Spacer(1, 12))
    toc_items = [
        "1. Paper Summaries",
        "2. Extracted Biological Entities",
        "3. Drug-Target Relationships",
        "4. Structured Summaries",
    ]
    if gap_analysis:
        toc_items.append("5. Research Gap Analysis")
    if comparison:
        toc_items.append("6. Multi-Paper Comparison")
    for item in toc_items:
        story.append(Paragraph(item, bullet_style))
    story.append(PageBreak())

    # 1. Paper Summaries
    story.append(Paragraph("1. Paper Summaries", heading_style))
    story.append(Spacer(1, 12))

    for i, paper in enumerate(analyzed_papers, 1):
        metadata = paper.get("metadata", {})
        story.append(Paragraph(f"Paper {i}: {metadata.get('title', 'Untitled')}", subheading_style))

        meta_data = [
            ["PMID", metadata.get("pmid", "N/A")],
            ["DOI", metadata.get("doi", "N/A")],
            ["PMCID", metadata.get("pmcid", "N/A")],
            ["Authors", metadata.get("authors", "N/A")[:200] if metadata.get("authors") else "N/A"],
            ["Journal", metadata.get("journal", "N/A")],
            ["Year", metadata.get("year", "N/A")],
            ["Source", metadata.get("source", "N/A")],
            ["Open Access", "Yes" if metadata.get("is_open_access") else "No"],
            ["Citations", str(metadata.get("citation_count", 0))],
            ["URL", metadata.get("url", "N/A")],
        ]

        table = Table(meta_data, colWidths=[1.5*inch, 4.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

        # Abstract
        if metadata.get("abstract"):
            story.append(Paragraph("<b>Abstract:</b>", body_style))
            story.append(Paragraph(metadata["abstract"][:1000], body_style))
            story.append(Spacer(1, 8))

    story.append(PageBreak())

    # 2. Extracted Biological Entities
    story.append(Paragraph("2. Extracted Biological Entities", heading_style))
    story.append(Spacer(1, 12))

    entity_types = [
        ("Genes", "genes", "symbol"),
        ("Proteins", "proteins", "name"),
        ("Diseases", "diseases", "name"),
        ("Drugs/Compounds", "drugs", "name"),
        ("Pathways", "pathways", "name"),
        ("Mutations", "mutations", "variant"),
        ("Biomarkers", "biomarkers", "name"),
    ]

    for label, entity_key, name_key in entity_types:
        all_entities = []
        for paper in analyzed_papers:
            for entity in paper.get("entities", {}).get(entity_key, []):
                name = entity.get(name_key, "")
                if name and name not in all_entities:
                    all_entities.append(name)

        if all_entities:
            story.append(Paragraph(f"{label} ({len(all_entities)} unique)", subheading_style))
            # Create a table with entities and their paper references
            entity_data = [["Entity", "Found In (PMIDs)"]]
            for entity_name in all_entities[:30]:  # Limit to 30
                pmids = []
                for paper in analyzed_papers:
                    for entity in paper.get("entities", {}).get(entity_key, []):
                        if entity.get(name_key, "") == entity_name:
                            pmid = paper.get("metadata", {}).get("pmid")
                            if pmid:
                                pmids.append(pmid)
                entity_data.append([entity_name, ", ".join(pmids[:5])])

            if len(entity_data) > 1:
                table = Table(entity_data, colWidths=[2*inch, 4*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(table)
            story.append(Spacer(1, 8))

    story.append(PageBreak())

    # 3. Drug-Target Relationships
    story.append(Paragraph("3. Drug-Target Relationships", heading_style))
    story.append(Spacer(1, 12))

    all_relationships = []
    for paper in analyzed_papers:
        for rel in paper.get("drug_target_relationships", []):
            rel["source_paper"] = paper.get("metadata", {}).get("title", "")[:60]
            rel["pmid"] = paper.get("metadata", {}).get("pmid", "")
            all_relationships.append(rel)

    if all_relationships:
        rel_data = [["Drug", "Target", "Relationship", "Evidence Type", "Confidence", "Source (PMID)"]]
        for rel in all_relationships[:30]:
            rel_data.append([
                rel.get("drug_name", ""),
                rel.get("target_name", ""),
                rel.get("relationship_type", ""),
                rel.get("evidence_type", ""),
                rel.get("confidence", ""),
                rel.get("pmid", ""),
            ])

        table = Table(rel_data, colWidths=[1*inch, 1*inch, 1*inch, 1*inch, 0.8*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No drug-target relationships extracted.", body_style))

    story.append(PageBreak())

    # 4. Structured Summaries
    story.append(Paragraph("4. Structured Summaries", heading_style))
    story.append(Spacer(1, 12))

    summary_sections = [
        ("Objectives", "objectives"),
        ("Methodology", "methodology"),
        ("Key Findings", "key_findings"),
        ("Results", "results"),
        ("Conclusions", "conclusions"),
        ("Limitations", "limitations"),
        ("Future Work", "future_work"),
    ]

    for section_label, section_key in summary_sections:
        story.append(Paragraph(section_label, subheading_style))
        all_items = []
        for paper in analyzed_papers:
            for item in paper.get("summary", {}).get(section_key, []):
                pmid = paper.get("metadata", {}).get("pmid", "N/A")
                all_items.append(f"[PMID: {pmid}] {item}")

        if all_items:
            for item in all_items[:20]:
                story.append(Paragraph(item, bullet_style))
        else:
            story.append(Paragraph("No items extracted.", body_style))
        story.append(Spacer(1, 8))

    story.append(PageBreak())

    # 5. Research Gap Analysis
    if gap_analysis:
        story.append(Paragraph("5. Research Gap Analysis", heading_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph(
            f"Total Gaps Identified: {len(gap_analysis.gaps)}",
            body_style
        ))
        story.append(Spacer(1, 8))

        gap_data = [["Gap Type", "Description", "Entities", "Confidence", "Suggested Experiments"]]
        for gap in gap_analysis.gaps[:20]:
            gap_data.append([
                gap.gap_type.replace("_", " ").title(),
                gap.description[:100],
                ", ".join(gap.entities_involved[:3]),
                gap.confidence,
                "; ".join(gap.suggested_experiments[:2]),
            ])

        table = Table(gap_data, colWidths=[1*inch, 2*inch, 1*inch, 0.8*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(table)

        # Conflicting findings
        if gap_analysis.conflicting_findings:
            story.append(Spacer(1, 12))
            story.append(Paragraph("Conflicting Findings", subheading_style))
            for conflict in gap_analysis.conflicting_findings[:10]:
                story.append(Paragraph(
                    f"<b>{conflict['topic']}</b>: {conflict['description']}",
                    bullet_style
                ))

        story.append(PageBreak())

    # 6. Multi-Paper Comparison
    if comparison:
        story.append(Paragraph("6. Multi-Paper Comparison", heading_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph(comparison.evidence_summary, body_style))
        story.append(Spacer(1, 12))

        if comparison.comparison_table is not None:
            story.append(Paragraph("Detailed Comparison Table", subheading_style))
            # Convert DataFrame to table
            df = comparison.comparison_table
            table_data = [df.columns.tolist()] + df.values.tolist()
            col_widths = [1.5*inch] + [4.5*inch / len(df.columns)] * len(df.columns)
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(table)

    # Build PDF
    doc.build(story)
    logger.info("PDF report saved to %s", output_path)
    return str(output_path)


def generate_executive_summary(
    analyzed_papers: list[dict[str, Any]],
    gap_analysis: GapAnalysisResult | None = None,
) -> str:
    """Generate a markdown executive summary."""
    lines = [
        "# Executive Summary",
        "",
        f"**Analysis Date:** {datetime.now().strftime('%B %d, %Y')}",
        f"**Papers Analyzed:** {len(analyzed_papers)}",
        "",
        "## Key Findings",
        "",
    ]

    # Aggregate key findings
    all_findings = []
    for paper in analyzed_papers:
        all_findings.extend(paper.get("summary", {}).get("key_findings", []))
        all_findings.extend(paper.get("summary", {}).get("results", []))

    for finding in all_findings[:10]:
        lines.append(f"- {finding}")

    lines.extend(["", "## Top Biological Entities", ""])

    # Count entities
    entity_counts = {}
    for paper in analyzed_papers:
        for entity_type in ["genes", "proteins", "diseases", "drugs", "pathways"]:
            for entity in paper.get("entities", {}).get(entity_type, []):
                name = entity.get("symbol") or entity.get("name") or entity.get("variant", "")
                if name:
                    entity_counts[name] = entity_counts.get(name, 0) + 1

    for entity, count in sorted(entity_counts.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"- **{entity}**: mentioned in {count} papers")

    if gap_analysis:
        lines.extend(["", "## Research Gaps Identified", "", f"Total: {len(gap_analysis.gaps)} gaps", ""])
        for gap in gap_analysis.gaps[:5]:
            lines.append(f"- **{gap.gap_type.replace('_', ' ').title()}**: {gap.description}")

    lines.extend(["", "---", "*This summary is generated computationally and requires expert validation.*"])

    return "\n".join(lines)