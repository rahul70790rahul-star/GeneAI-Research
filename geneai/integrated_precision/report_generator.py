"""Report generator for Integrated Precision Drug Discovery."""
from __future__ import annotations

import io
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from geneai.integrated_precision.workflow_engine import IntegratedDrugDiscoveryResult


def generate_integrated_precision_pdf(result: IntegratedDrugDiscoveryResult, run_id: str) -> bytes:
    """Generate comprehensive PDF report for integrated analysis."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )
    styles = getSampleStyleSheet()
    elements = []
    
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"], fontSize=18, spaceAfter=6,
        alignment=TA_CENTER, textColor=colors.HexColor("#1f4e79")
    )
    heading_style = ParagraphStyle(
        "CustomHeading", parent=styles["Heading2"], fontSize=13,
        spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#1f4e79")
    )
    normal_style = styles["Normal"]
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666666"))
    
    # Title page
    elements.append(Spacer(1, 30*mm))
    elements.append(Paragraph("Integrated Precision Drug Discovery Report", title_style))
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(f"Run ID: {run_id}", styles["Normal"]))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(
        "Unified workflow: Variants → Genes → Pathways → Targets → Drugs → ADMET → Safety → Ranking",
        styles["Normal"]
    ))
    elements.append(PageBreak())
    
    # Executive Summary
    elements.append(Paragraph("Executive Summary", heading_style))
    summary = result.summary
    exec_text = (
        f"This report presents the results of an integrated precision drug discovery analysis. "
        f"The pipeline analyzed {summary.get('variants_analyzed', 0)} variants, "
        f"identified {summary.get('therapeutic_targets', 0)} therapeutic targets, "
        f"found {summary.get('drugs_found', 0)} drugs, predicted {summary.get('binding_affinities', 0)} "
        f"binding affinities, and ranked {summary.get('candidates_ranked', 0)} candidates. "
        f"Pipeline steps completed: {', '.join(summary.get('steps_completed', []))}."
    )
    elements.append(Paragraph(exec_text, normal_style))
    elements.append(Spacer(1, 4*mm))
    
    top = summary.get("top_candidate")
    if top:
        elements.append(Paragraph(f"Top candidate: <b>{top.get('drug', 'N/A')}</b> "
            f"(score: {top.get('score', 0):.3f}, ADMET: {top.get('admet_score', 'N/A')}, "
            f"Safety: {top.get('safety_risk', 'N/A')})", normal_style))
    elements.append(PageBreak())
    
    # Pipeline Summary Table
    elements.append(Paragraph("Pipeline Summary", heading_style))
    steps_info = [
        ("Mutation Analysis", "variants_analyzed", "pathogenic_variants"),
        ("Disease-Gene-Pathway", "disease_associations", "therapeutic_targets"),
        ("Target Identification", "targets_identified", "druggable_targets"),
        ("Drug Discovery", "drugs_found", "binding_affinities"),
        ("ADMET/Safety", "admet_predictions", "safety_profiles"),
        ("Literature Analysis", "papers_analyzed", ""),
    ]
    
    summary_data = [["Pipeline Step", "Status", "Key Metrics"]]
    for name, metric1, metric2 in steps_info:
        completed = name.lower().replace(" ", "_").replace("-", "_") in [s.lower().replace(" ", "_").replace("-", "_") for s in summary.get("steps_completed", [])]
        status = "✅ Completed" if completed else "⏭️ Skipped"
        metrics = []
        if metric1 and metric1 in summary:
            metrics.append(f"{metric1.replace('_', ' ').title()}: {summary[metric1]}")
        if metric2 and metric2 in summary:
            metrics.append(f"{metric2.replace('_', ' ').title()}: {summary[metric2]}")
        summary_data.append([name, status, "; ".join(metrics)])
    
    t = Table(summary_data, colWidths=[45*mm, 30*mm, 105*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(t)
    elements.append(PageBreak())
    
    # Mutation Analysis
    if result.mutation_analysis:
        elements.append(Paragraph("Mutation Analysis Details", heading_style))
        ma = result.mutation_analysis
        
        elements.append(Paragraph(f"Total Variants Analyzed: {ma.variants_analyzed}", normal_style))
        elements.append(Paragraph(f"Pathogenic/Likely Pathogenic: {len(ma.pathogenic_variants)}", normal_style))
        elements.append(Paragraph(f"Affected Genes: {len(ma.affected_genes)}", normal_style))
        
        if ma.affected_genes:
            elements.append(Paragraph(f"Genes: {', '.join(sorted(ma.affected_genes))}", normal_style))
        
        if ma.mutation_interpretations:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Key Variant Interpretations:", normal_style))
            interp_data = [["Variant", "Gene", "Impact", "Consequence", "Interpretation"]]
            for interp in ma.mutation_interpretations[:20]:
                interp_data.append([
                    interp.get("variant", "")[:30],
                    interp.get("gene", ""),
                    interp.get("impact", "").capitalize(),
                    interp.get("consequence", "")[:30],
                    interp.get("interpretation", "")[:50],
                ])
            t = Table(interp_data, colWidths=[25*mm, 15*mm, 15*mm, 25*mm, 100*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 8),
            ]))
            elements.append(t)
        elements.append(PageBreak())
    
    # Disease-Gene-Pathway Analysis
    if result.disease_gene_analysis:
        elements.append(Paragraph("Disease-Gene-Pathway Analysis", heading_style))
        dg = result.disease_gene_analysis
        
        elements.append(Paragraph(f"Disease-Gene Associations: {len(dg.disease_gene_associations)}", normal_style))
        elements.append(Paragraph(f"Hub Genes: {len(dg.hub_genes)}", normal_style))
        elements.append(Paragraph(f"Pathways: {len(dg.pathways)}", normal_style))
        elements.append(Paragraph(f"Therapeutic Targets: {len(dg.therapeutic_targets)}", normal_style))
        
        if dg.therapeutic_targets:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Therapeutic Targets:", normal_style))
            target_data = [["Gene", "Score", "Reasons"]]
            for t in dg.therapeutic_targets[:15]:
                target_data.append([t["gene_symbol"], f"{t['score']:.3f}", "; ".join(t["reasons"][:2])])
            t = Table(target_data, colWidths=[25*mm, 20*mm, 135*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 9),
            ]))
            elements.append(t)
        elements.append(PageBreak())
    
    # Target Identification
    if result.target_identification:
        elements.append(Paragraph("Target Identification & Ranking", heading_style))
        ti = result.target_identification
        
        elements.append(Paragraph(f"Targets Identified: {len(ti.targets)}", normal_style))
        elements.append(Paragraph(f"Druggable Targets: {len(ti.druggable_targets)}", normal_style))
        
        if ti.target_ranking:
            elements.append(Spacer(1, 3*mm))
            rank_data = [["Rank", "Gene", "Druggability", "Type", "Druggable"]]
            for i, t in enumerate(ti.target_ranking[:20]):
                rank_data.append([
                    str(i+1), t["gene_symbol"],
                    f"{t.get('druggability_score', 0):.2f}",
                    t.get("target_type", ""),
                    "✅" if t in ti.druggable_targets else "❌"
                ])
            t = Table(rank_data, colWidths=[15*mm, 25*mm, 20*mm, 25*mm, 20*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 9),
            ]))
            elements.append(t)
        elements.append(PageBreak())
    
    # Drug Discovery
    if result.drug_discovery:
        elements.append(Paragraph("Drug Discovery & Target Prediction", heading_style))
        dd = result.drug_discovery
        
        elements.append(Paragraph(f"Drugs Found: {len(dd.drugs_found)}", normal_style))
        elements.append(Paragraph(f"Drug-Target Interactions: {len(dd.drug_target_interactions)}", normal_style))
        elements.append(Paragraph(f"Binding Affinities Predicted: {len(dd.binding_affinities)}", normal_style))
        elements.append(Paragraph(f"Repurposing Candidates: {len(dd.repurposing_candidates)}", normal_style))
        
        if dd.binding_affinities:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Predicted Binding Affinities:", normal_style))
            ba_data = [["Drug", "Target", "Affinity (pKi/pIC50)"]]
            for ba in dd.binding_affinities[:20]:
                ba_data.append([ba.get("drug", "")[:30], ba.get("target", ""), f"{ba.get('affinity', 0):.2f}"])
            t = Table(ba_data, colWidths=[40*mm, 30*mm, 40*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 9),
            ]))
            elements.append(t)
        elements.append(PageBreak())
    
    # ADMET/Safety
    if result.safety_admet:
        elements.append(Paragraph("ADMET & Safety Analysis", heading_style))
        sa = result.safety_admet
        
        elements.append(Paragraph(f"ADMET Predictions: {len(sa.admet_predictions)}", normal_style))
        elements.append(Paragraph(f"Safety Profiles: {len(sa.safety_profiles)}", normal_style))
        
        if sa.admet_predictions:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("ADMET Predictions:", normal_style))
            admet_data = [["Compound", "Overall Score", "Risk", "Absorption", "Distribution", "Metabolism", "Excretion", "Toxicity"]]
            for a in sa.admet_predictions[:15]:
                cs = a.get("category_scores", {})
                admet_data.append([
                    a.get("smiles", "")[:30],
                    f"{a.get('overall_score', 0):.3f}",
                    a.get("risk_classification", ""),
                    f"{cs.get('absorption', 0):.2f}",
                    f"{cs.get('distribution', 0):.2f}",
                    f"{cs.get('metabolism', 0):.2f}",
                    f"{cs.get('excretion', 0):.2f}",
                    f"{cs.get('toxicity', 0):.2f}",
                ])
            t = Table(admet_data, colWidths=[25*mm, 18*mm, 18*mm, 15*mm, 15*mm, 15*mm, 15*mm, 15*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 8),
            ]))
            elements.append(t)
        
        if sa.safety_profiles:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Safety Profiles:", normal_style))
            safety_data = [["Compound", "Risk Level", "Risk Score", "Risk Factors", "Structural Alerts"]]
            for s in sa.safety_profiles[:15]:
                safety_data.append([
                    s.get("smiles", "")[:30],
                    s.get("risk_level", ""),
                    f"{s.get('risk_score', 0):.3f}",
                    str(s.get("risk_factors", 0)),
                    str(s.get("structural_alerts", 0)),
                ])
            t = Table(safety_data, colWidths=[35*mm, 20*mm, 20*mm, 20*mm, 20*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
                ("FONTSIZE", (0,0), (-1,-1), 9),
            ]))
            elements.append(t)
        elements.append(PageBreak())
    
    # Ranked Candidates
    elements.append(Paragraph("Ranked Drug Candidates", heading_style))
    cand_data = [["Rank", "Drug", "Score", "ADMET", "Safety", "Key Reasons"]]
    for c in result.candidate_ranking[:30]:
        cand_data.append([
            str(c.get("rank", "")),
            c.get("drug", "")[:30],
            f"{c.get('score', 0):.3f}",
            f"{c.get('admet_score', 0):.2f}" if c.get("admet_score") else "N/A",
            c.get("safety_risk", "N/A"),
            "; ".join(c.get("reasons", [])[:2]),
        ])
    
    t = Table(cand_data, colWidths=[12*mm, 30*mm, 15*mm, 15*mm, 18*mm, 90*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(t)
    elements.append(PageBreak())
    
    # Literature Analysis
    if result.literature_analysis:
        elements.append(Paragraph("Literature Analysis", heading_style))
        la = result.literature_analysis
        
        elements.append(Paragraph(f"Papers Analyzed: {la.papers_analyzed}", normal_style))
        elements.append(Paragraph(f"Total Entities Extracted: {la.total_entities}", normal_style))
        elements.append(Paragraph(f"Drug-Target Relations: {len(la.drug_target_relations)}", normal_style))
        elements.append(Paragraph(f"Pathway Mentions: {len(la.pathway_mentions)}", normal_style))
        
        if la.key_findings:
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Key Findings:", normal_style))
            for finding in la.key_findings[:10]:
                elements.append(Paragraph(f"• {finding}", normal_style))
        elements.append(PageBreak())
    
    # Limitations
    elements.append(Paragraph("Limitations & Disclaimers", heading_style))
    limitations = [
        "All computational predictions require experimental validation before clinical application.",
        "Drug-target interactions are predicted from structural modeling and ML, not experimentally confirmed.",
        "ADMET/Safety models are trained on limited chemical space; out-of-domain predictions may be unreliable.",
        "Literature analysis uses automated text mining and may miss context or contain extraction errors.",
        "Candidate ranking uses heuristic multi-criteria weights, not clinical outcome data.",
        "Gene-disease associations from databases may not reflect causal relationships.",
        "Pathway enrichment uses statistical over-representation; functional relevance not guaranteed.",
        "This tool is for research purposes only and not intended for clinical decision-making.",
    ]
    for lim in limitations:
        elements.append(Paragraph(f"• {lim}", small_style))
    
    doc.build(elements)
    return buffer.getvalue()


def generate_integrated_precision_csv(result: IntegratedDrugDiscoveryResult, run_id: str) -> str:
    """Generate CSV report."""
    import io
    import csv
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Integrated Precision Drug Discovery Report"])
    writer.writerow(["Run ID", run_id])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow([])
    
    writer.writerow(["Pipeline Summary"])
    for k, v in result.summary.items():
        writer.writerow([k, v])
    writer.writerow([])
    
    writer.writerow(["Ranked Candidates"])
    writer.writerow(["Rank", "Drug", "SMILES", "Score", "ADMET", "Safety", "Reasons", "Binding Affinities"])
    for c in result.candidate_ranking:
        writer.writerow([
            c.get("rank"), c.get("drug"), c.get("smiles", ""),
            f"{c.get('score', 0):.3f}",
            f"{c.get('admet_score', 0):.3f}" if c.get("admet_score") else "",
            c.get("safety_risk", ""),
            "; ".join(c.get("reasons", [])),
            "; ".join(f"{ba['target']}:{ba['affinity']:.2f}" for ba in c.get("binding_affinities", [])),
        ])
    
    return output.getvalue()


def generate_integrated_precision_json(result: IntegratedDrugDiscoveryResult, run_id: str) -> dict[str, Any]:
    """Generate JSON report."""
    return {
        "metadata": {
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(),
            "pipeline_version": "4.12",
        },
        "summary": result.summary,
        "candidate_ranking": result.candidate_ranking,
        "mutation_analysis": asdict(result.mutation_analysis) if result.mutation_analysis else None,
        "disease_gene_analysis": asdict(result.disease_gene_analysis) if result.disease_gene_analysis else None,
        "target_identification": asdict(result.target_identification) if result.target_identification else None,
        "drug_discovery": asdict(result.drug_discovery) if result.drug_discovery else None,
        "safety_admet": asdict(result.safety_admet) if result.safety_admet else None,
        "literature_analysis": asdict(result.literature_analysis) if result.literature_analysis else None,
    }