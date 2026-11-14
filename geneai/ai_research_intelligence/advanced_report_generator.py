"""Advanced Report Generator for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, inch
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    Image, KeepTogether, ListFlowable, ListItem
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart

logger = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """A section of the report."""
    title: str
    content: str | list[Any]  # string or list of flowables
    level: int = 1  # 1=heading, 2=subheading, etc.


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    title: str = "AI Research Intelligence Report"
    subtitle: str = ""
    author: str = "GeneAI Research Platform"
    institution: str = ""
    include_toc: bool = True
    include_methods: bool = True
    include_limitations: bool = True
    include_references: bool = True
    page_size: tuple = A4
    margins: tuple = (25*mm, 25*mm, 25*mm, 25*mm)  # left, right, top, bottom


class AdvancedReportGenerator:
    """Generate publication-ready scientific reports."""
    
    def __init__(self, config: ReportConfig | None = None):
        self.config = config or ReportConfig()
        self.sections: list[ReportSection] = []
        self.styles = self._create_styles()
        self.references: list[dict[str, str]] = []
        self.figures: list[dict[str, Any]] = []
        self.tables: list[dict[str, Any]] = []
    
    def _create_styles(self) -> dict[str, ParagraphStyle]:
        styles = getSampleStyleSheet()
        custom = {}
        
        custom['title'] = ParagraphStyle(
            'CustomTitle', parent=styles['Title'],
            fontSize=22, spaceAfter=12, alignment=TA_CENTER,
            textColor=colors.HexColor("#1a3c5e"), fontName='Helvetica-Bold'
        )
        custom['subtitle'] = ParagraphStyle(
            'CustomSubtitle', parent=styles['Normal'],
            fontSize=13, spaceAfter=6, alignment=TA_CENTER,
            textColor=colors.HexColor("#4a6fa5"), fontName='Helvetica-Oblique'
        )
        custom['heading1'] = ParagraphStyle(
            'Heading1Custom', parent=styles['Heading1'],
            fontSize=16, spaceBefore=18, spaceAfter=8,
            textColor=colors.HexColor("#1a3c5e"), fontName='Helvetica-Bold',
            borderWidth=0, borderPadding=0, borderColor=colors.HexColor("#1a3c5e")
        )
        custom['heading2'] = ParagraphStyle(
            'Heading2Custom', parent=styles['Heading2'],
            fontSize=13, spaceBefore=14, spaceAfter=6,
            textColor=colors.HexColor("#2d5a8a"), fontName='Helvetica-Bold'
        )
        custom['heading3'] = ParagraphStyle(
            'Heading3Custom', parent=styles['Heading3'],
            fontSize=11, spaceBefore=10, spaceAfter=4,
            textColor=colors.HexColor("#3d7ab5"), fontName='Helvetica-Bold'
        )
        custom['body'] = ParagraphStyle(
            'BodyCustom', parent=styles['Normal'],
            fontSize=10, spaceAfter=6, alignment=TA_JUSTIFY,
            leading=13, fontName='Helvetica'
        )
        custom['bullet'] = ParagraphStyle(
            'BulletCustom', parent=styles['Normal'],
            fontSize=10, spaceAfter=3, leftIndent=20, bulletIndent=8,
            leading=13
        )
        custom['small'] = ParagraphStyle(
            'SmallCustom', parent=styles['Normal'],
            fontSize=8, textColor=colors.HexColor("#666666"), leading=10
        )
        custom['caption'] = ParagraphStyle(
            'CaptionCustom', parent=styles['Normal'],
            fontSize=9, spaceBefore=4, spaceAfter=8, alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"), fontName='Helvetica-Oblique'
        )
        custom['code'] = ParagraphStyle(
            'CodeCustom', parent=styles['Code'],
            fontSize=8, fontName='Courier', leftIndent=20,
            backgroundColor=colors.HexColor("#f5f5f5")
        )
        custom['ref'] = ParagraphStyle(
            'RefCustom', parent=styles['Normal'],
            fontSize=9, spaceAfter=4, leftIndent=24, firstLineIndent=-24,
            leading=11
        )
        
        return custom
    
    def add_section(self, title: str, content: str | list, level: int = 1) -> None:
        """Add a section to the report."""
        self.sections.append(ReportSection(title=title, content=content, level=level))
    
    def add_methods(self, methods: list[str]) -> None:
        """Add methods section."""
        content = []
        for i, method in enumerate(methods, 1):
            content.append(Paragraph(f"{i}. {method}", self.styles['body']))
        self.add_section("Methods", content, level=1)
    
    def add_limitations(self, limitations: list[str]) -> None:
        """Add limitations section."""
        content = []
        for lim in limitations:
            content.append(Paragraph(f"• {lim}", self.styles['bullet']))
        self.add_section("Limitations", content, level=1)
    
    def add_references(self, references: list[dict[str, str]]) -> None:
        """Add references."""
        self.references.extend(references)
    
    def add_figure(self, image_path: str, caption: str, width: float = 150*mm) -> None:
        """Add a figure."""
        self.figures.append({"path": image_path, "caption": caption, "width": width})
    
    def add_table(self, title: str, headers: list[str], data: list[list], 
                  col_widths: list[float] | None = None) -> None:
        """Add a table."""
        self.tables.append({
            "title": title, "headers": headers, "data": data, "col_widths": col_widths
        })
    
    def generate_pdf(self, output_path: str | Path) -> Path:
        """Generate PDF report."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        doc = SimpleDocTemplate(
            str(output_path), pagesize=self.config.page_size,
            leftMargin=self.config.margins[0], rightMargin=self.config.margins[1],
            topMargin=self.config.margins[2], bottomMargin=self.config.margins[3],
        )
        
        elements = []
        
        # Title page
        elements.extend(self._build_title_page())
        elements.append(PageBreak())
        
        # Table of contents placeholder
        if self.config.include_toc:
            elements.append(Paragraph("Table of Contents", self.styles['heading1']))
            elements.append(Paragraph("[Auto-generated in full implementation]", self.styles['small']))
            elements.append(PageBreak())
        
        # Sections
        for section in self.sections:
            elements.extend(self._build_section(section))
        
        # References
        if self.config.include_references and self.references:
            elements.append(PageBreak())
            elements.extend(self._build_references())
        
        # Build
        doc.build(elements)
        logger.info(f"Report generated: {output_path}")
        return output_path
    
    def _build_title_page(self) -> list:
        elements = []
        elements.append(Spacer(1, 60*mm))
        elements.append(Paragraph(self.config.title, self.styles['title']))
        elements.append(Spacer(1, 8*mm))
        
        if self.config.subtitle:
            elements.append(Paragraph(self.config.subtitle, self.styles['subtitle']))
            elements.append(Spacer(1, 12*mm))
        
        # Metadata table
        meta_data = [
            ["Author:", self.config.author],
            ["Institution:", self.config.institution or "GeneAI Research"],
            ["Date:", datetime.now().strftime("%B %d, %Y")],
            ["Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["Pipeline Version:", "4.13"],
        ]
        
        meta_table = Table(meta_data, colWidths=[40*mm, 100*mm])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#4a6fa5")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta_table)
        
        elements.append(Spacer(1, 30*mm))
        
        # Disclaimer
        disclaimer = Paragraph(
            "<b>Disclaimer:</b> This report presents computational analyses and predictions "
            "generated by the GeneAI Research Intelligence platform. All findings require "
            "experimental validation and expert review before clinical application. "
            "This software is for research purposes only.",
            self.styles['small']
        )
        elements.append(disclaimer)
        
        return elements
    
    def _build_section(self, section: ReportSection) -> list:
        elements = []
        
        # Heading
        style_key = f'heading{min(section.level, 3)}'
        elements.append(Paragraph(section.title, self.styles[style_key]))
        elements.append(Spacer(1, 3*mm))
        
        # Content
        if isinstance(section.content, str):
            # Split by paragraphs
            paragraphs = section.content.split('\n\n')
            for p in paragraphs:
                if p.strip():
                    elements.append(Paragraph(p.strip(), self.styles['body']))
        elif isinstance(section.content, list):
            for item in section.content:
                if isinstance(item, str):
                    elements.append(Paragraph(item, self.styles['body']))
                else:
                    # Assume it's a flowable
                    elements.append(item)
        
        elements.append(Spacer(1, 4*mm))
        return elements
    
    def _build_references(self) -> list:
        elements = []
        elements.append(Paragraph("References", self.styles['heading1']))
        elements.append(Spacer(1, 4*mm))
        
        for i, ref in enumerate(self.references, 1):
            ref_text = self._format_reference(ref, i)
            elements.append(Paragraph(ref_text, self.styles['ref']))
        
        return elements
    
    def _format_reference(self, ref: dict[str, str], number: int) -> str:
        """Format a reference."""
        authors = ref.get('authors', '')
        title = ref.get('title', '')
        journal = ref.get('journal', '')
        year = ref.get('year', '')
        doi = ref.get('doi', '')
        pmid = ref.get('pmid', '')
        
        parts = []
        if authors:
            parts.append(authors)
        if title:
            parts.append(f"<i>{title}</i>")
        if journal:
            parts.append(f"<b>{journal}</b>")
        if year:
            parts.append(f"({year})")
        if doi:
            parts.append(f"doi:{doi}")
        if pmid:
            parts.append(f"PMID:{pmid}")
        
        return f"{number}. {' '.join(parts)}."
    
    def generate_html(self, output_path: str | Path) -> Path:
        """Generate HTML report."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        html_parts = [
            "<!DOCTYPE html>",
            "<html><head>",
            f"<title>{self.config.title}</title>",
            "<meta charset='utf-8'>",
            "<style>",
            self._get_html_css(),
            "</style>",
            "</head><body>",
            "<div class='container'>",
        ]
        
        # Title
        html_parts.append(f"<h1 class='title'>{self.config.title}</h1>")
        if self.config.subtitle:
            html_parts.append(f"<h2 class='subtitle'>{self.config.subtitle}</h2>")
        
        # Metadata
        html_parts.append("<div class='metadata'>")
        html_parts.append(f"<p><strong>Author:</strong> {self.config.author}</p>")
        html_parts.append(f"<p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>")
        html_parts.append(f"<p><strong>Pipeline Version:</strong> 4.13</p>")
        html_parts.append("</div>")
        
        # Sections
        for section in self.sections:
            html_parts.append(f"<h{min(section.level, 3)} class='section-title'>{section.title}</h{hh}>")
            if isinstance(section.content, str):
                for p in section.content.split('\n\n'):
                    if p.strip():
                        html_parts.append(f"<p>{p.strip()}</p>")
            elif isinstance(section.content, list):
                for item in section.content:
                    if isinstance(item, str):
                        html_parts.append(f"<p>{item}</p>")
        
        # References
        if self.references:
            html_parts.append("<h2>References</h2>")
            html_parts.append("<ol class='references'>")
            for i, ref in enumerate(self.references, 1):
                html_parts.append(f"<li>{self._format_reference_html(ref)}</li>")
            html_parts.append("</ol>")
        
        html_parts.extend(["</div>", "</body></html>"])
        
        with open(output_path, "w") as f:
            f.write("\n".join(html_parts))
        
        return output_path
    
    def _get_html_css(self) -> str:
        return """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 2rem; color: #333; }
        .container { background: white; }
        .title { color: #1a3c5e; border-bottom: 3px solid #1a3c5e; padding-bottom: 0.5rem; }
        .subtitle { color: #4a6fa5; font-weight: normal; margin-top: 0; }
        .metadata { background: #f5f7fa; padding: 1rem; border-radius: 8px; margin: 1.5rem 0; }
        .metadata p { margin: 0.3rem 0; }
        .section-title { color: #1a3c5e; margin-top: 2rem; }
        h3.section-title { color: #2d5a8a; }
        .references { font-size: 0.9rem; }
        .references li { margin-bottom: 0.5rem; }
        .disclaimer { font-size: 0.85rem; color: #666; border-top: 1px solid #ddd; 
                      padding-top: 1rem; margin-top: 2rem; font-style: italic; }
        table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #1a3c5e; color: white; }
        tr:nth-child(even) { background: #f2f7fb; }
        """
    
    def _format_reference_html(self, ref: dict[str, str]) -> str:
        parts = []
        if ref.get('authors'):
            parts.append(ref['authors'])
        if ref.get('title'):
            parts.append(f"<i>{ref['title']}</i>")
        if ref.get('journal'):
            parts.append(f"<b>{ref['journal']}</b>")
        if ref.get('year'):
            parts.append(f"({ref['year']})")
        if ref.get('doi'):
            parts.append(f"doi:{ref['doi']}")
        if ref.get('pmid'):
            parts.append(f"PMID:{ref['pmid']}")
        return " ".join(parts)
    
    def generate_markdown(self, output_path: str | Path) -> Path:
        """Generate Markdown report."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        md = []
        md.append(f"# {self.config.title}")
        if self.config.subtitle:
            md.append(f"## {self.config.subtitle}")
        
        md.append(f"\n**Author:** {self.config.author}  ")
        md.append(f"**Date:** {datetime.now().strftime('%B %d, %Y')}  ")
        md.append(f"**Pipeline Version:** 4.13  ")
        
        md.append("\n---\n")
        
        for section in self.sections:
            md.append(f"{'#' * min(section.level + 1, 4)} {section.title}")
            if isinstance(section.content, str):
                md.append(section.content)
            elif isinstance(section.content, list):
                for item in section.content:
                    if isinstance(item, str):
                        md.append(item)
                    elif hasattr(item, "text"):
                        md.append(item.text)
                    else:
                        md.append(str(item))
            md.append("")
        
        if self.references:
            md.append("## References")
            for i, ref in enumerate(self.references, 1):
                md.append(f"{i}. {self._format_reference_html(ref).replace('<i>', '*').replace('</i>', '*').replace('<b>', '**').replace('</b>', '**')}")
        
        md.append("\n---\n")
        md.append("*Disclaimer: This report presents computational analyses and predictions generated by the GeneAI Research Intelligence platform. All findings require experimental validation and expert review before clinical application.*")
        
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        
        return out_p


def create_mutation_to_drug_report(result: Any, config: ReportConfig | None = None) -> AdvancedReportGenerator:
    """Create a report from mutation-to-drug workflow result."""
    config = config or ReportConfig(
        title="Mutation-to-Drug Discovery Report",
        subtitle=f"Workflow ID: {getattr(result, 'workflow_id', 'N/A')}"
    )
    
    generator = AdvancedReportGenerator(config)
    
    # Executive Summary
    summary = getattr(result, 'summary', {})
    exec_text = (
        f"This report presents the results of an end-to-end mutation-to-drug discovery analysis. "
        f"The workflow analyzed {summary.get('variants_analyzed', 0)} variants, "
        f"linked {summary.get('genes_linked', 0)} genes to {summary.get('diseases_linked', 0)} diseases, "
        f"prioritized {summary.get('targets_prioritized', 0)} therapeutic targets, "
        f"and discovered {summary.get('candidates_discovered', 0)} drug candidates. "
        f"The top candidate is {summary.get('top_drug', 'N/A')}."
    )
    generator.add_section("Executive Summary", exec_text)
    
    # Input Variants
    variants = getattr(result, 'input_variants', [])
    if variants:
        var_data = [["Variant", "Gene", "Impact", "Consequence", "Pathogenicity"]]
        for v in variants[:20]:
            var_data.append([
                getattr(v, 'variant_id', '')[:30],
                getattr(v, 'gene', ''),
                getattr(v, 'impact', ''),
                getattr(v, 'consequence', ''),
                f"{getattr(v, 'pathogenicity_score', 0):.2f}",
            ])
        generator.add_table("Input Variants", var_data[0], var_data[1:])
        generator.add_section("Input Variants", "See table above.")
    
    # Gene-Disease Links
    links = getattr(result, 'gene_disease_links', [])
    if links:
        link_data = [["Gene", "Disease", "Score", "Evidence"]]
        for l in links[:20]:
            link_data.append([
                l.gene_symbol, l.disease_name, f"{l.score:.3f}",
                ", ".join(l.evidence_types[:2])
            ])
        generator.add_table("Gene-Disease Associations", link_data[0], link_data[1:])
        generator.add_section("Gene-Disease Associations", "See table above.")
    
    # Top Candidates
    top = getattr(result, 'top_candidates', [])
    if top:
        cand_data = [["Rank", "Drug", "Targets", "ADMET", "Safety", "Phase", "Key Evidence"]]
        for c in top[:15]:
            cand_data.append([
                str(getattr(c, 'rank', '')),
                getattr(c, 'name', ''),
                ", ".join(getattr(c, 'targets', [])[:3]),
                f"{getattr(c, 'admet_score', 0):.2f}" if getattr(c, 'admet_score', None) else "N/A",
                getattr(c, 'safety_risk', 'N/A'),
                str(getattr(c, 'phase', 0)),
                "; ".join(getattr(c, 'repurposing_evidence', [])[:2]),
            ])
        generator.add_table("Top Ranked Candidates", cand_data[0], cand_data[1:])
        generator.add_section("Top Drug Candidates", "See table above.")
    
    # Knowledge Graph Paths
    kg = getattr(result, 'knowledge_graph_subgraph', {})
    if kg.get('paths'):
        generator.add_section("Knowledge Graph Paths", 
            f"Found {kg.get('path_count', 0)} paths connecting variants to drug candidates. "
            f"Top paths involve {len(kg.get('subgraph', {}).get('nodes', {}))} nodes.")
    
    # Methods
    generator.add_methods([
        "Variant annotation using VEP/ClinVar/gnomAD (simulated)",
        "Gene-disease association via OpenTargets Platform",
        "Target prioritization using network centrality and variant impact",
        "Drug candidate discovery via ChEMBL and drug repurposing databases",
        "ADMET prediction using ML models (absorption, distribution, metabolism, excretion, toxicity)",
        "Safety profiling using structural alerts and toxicity classifiers",
        "Binding affinity prediction via drug-target interaction models",
        "Multi-criteria candidate ranking using gradient boosting regressor",
        "Knowledge graph path analysis using biomedical knowledge graph",
    ])
    
    # Limitations
    generator.add_limitations([
        "Variant pathogenicity scores are heuristic; clinical classification requires ACMG guidelines",
        "Gene-disease associations from databases may not indicate causality",
        "ADMET/safety predictions are computational; experimental validation required",
        "Drug-target binding affinities are predicted, not experimentally measured",
        "Candidate ranking uses heuristic weights; not validated against clinical outcomes",
        "Knowledge graph coverage depends on integrated data sources",
        "Repurposing evidence is literature-based; clinical efficacy not confirmed",
    ])
    
    # References (placeholder)
    generator.add_references([
        {"authors": "GeneAI Research Platform", "title": "Integrated Precision Drug Discovery Pipeline", 
         "journal": "GeneAI Technical Report", "year": "2026", "doi": "10.5281/zenodo.xxxxxx"},
    ])
    
    return generator


def create_integrated_analysis_report(result: Any, config: ReportConfig | None = None) -> AdvancedReportGenerator:
    """Create a report from integrated precision drug discovery result."""
    config = config or ReportConfig(
        title="Integrated Precision Drug Discovery Report",
        subtitle=f"Run ID: {getattr(result, 'run_id', 'N/A')}"
    )
    
    generator = AdvancedReportGenerator(config)
    
    # Use the existing report generator from integrated_precision
    # This is a wrapper that creates an AdvancedReportGenerator
    return generator


def generate_comparative_report(experiment_ids: list[str], output_path: str | Path) -> Path:
    """Generate a comparative report across multiple experiments."""
    from geneai.ai_research_intelligence.reproducibility import ReproducibilityTracker
    
    comparison = ReproducibilityTracker.compare(experiment_ids)
    
    config = ReportConfig(
        title="Comparative Experiment Analysis",
        subtitle=f"Comparing {len(experiment_ids)} experiments"
    )
    generator = AdvancedReportGenerator(config)
    
    generator.add_section("Overview", 
        f"This report compares {len(experiment_ids)} experiments: {', '.join(experiment_ids)}.")
    
    if comparison.get('parameters'):
        generator.add_section("Parameter Differences", 
            "The following parameters differed across experiments:")
        for param, values in comparison['parameters'].items():
            generator.add_section(param, "\n".join([f"• {k}: {v}" for k, v in values.items()]), level=2)
    
    if comparison.get('metrics'):
        generator.add_section("Metric Comparison", 
            "Key metrics across experiments:")
        for metric, values in comparison['metrics'].items():
            generator.add_section(metric, "\n".join([f"• {k}: {v}" for k, v in values.items()]), level=2)
    
    return generator.generate_pdf(output_path)