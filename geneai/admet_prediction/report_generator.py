"""ADMET Report Generation - Module 7: PDF and CSV report generation."""
from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from geneai.admet_prediction.admet_engine import ADMETPrediction, ADMETResult
from geneai.admet_prediction.admet_scoring import (
    ADMETScore,
    CategoryScore,
    OverallADMETScore,
    calculate_overall_admet_score,
)

logger = logging.getLogger(__name__)


def generate_admet_pdf_report(
    result: ADMETResult,
    score: OverallADMETScore | None = None,
    compound_name: str | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Generate a comprehensive PDF report for ADMET predictions.
    
    Args:
        result: ADMET prediction result
        score: Overall ADMET score (calculated if not provided)
        compound_name: Optional compound name
        output_path: Optional file path to save PDF
        
    Returns:
        PDF bytes
    """
    if score is None:
        score = calculate_overall_admet_score(result)
    
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
        borderWidth=0,
        borderPadding=0,
        borderColor=colors.HexColor("#1f4e79"),
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
    elements.append(Paragraph("ADMET Prediction Report", title_style))
    elements.append(Spacer(1, 5 * mm))
    
    if compound_name:
        elements.append(Paragraph(f"Compound: {compound_name}", subtitle_style))
    
    smiles = result.smiles
    if len(smiles) > 80:
        smiles = smiles[:77] + "..."
    elements.append(Paragraph(f"SMILES: {smiles}", subtitle_style))
    elements.append(Spacer(1, 10 * mm))
    
    # Overall assessment box
    risk_color = {
        "Favorable": colors.HexColor("#548235"),
        "Acceptable": colors.HexColor("#bf8f00"),
        "Concerning": colors.HexColor("#c00000"),
        "High Risk": colors.HexColor("#7030a0"),
    }.get(score.risk_classification, colors.HexColor("#4a4a4a"))
    
    overall_data = [
        ["Overall ADMET Score", f"{score.overall_score:.3f}"],
        ["Risk Classification", score.risk_classification],
        ["Drug-Likeness Score", f"{score.drug_likeness_score:.3f}"],
        ["Total Endpoints Evaluated", str(score.summary.get("total_endpoints", 0))],
        ["Favorable Endpoints", str(score.summary.get("favorable_endpoints", 0))],
        ["Report Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Model Version", "1.0"],
    ]
    
    overall_table = Table(overall_data, colWidths=[60 * mm, 60 * mm])
    overall_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d6e4f0")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f2f7fb")),
    ]))
    
    # Highlight risk classification row
    for i, row in enumerate(overall_data):
        if row[0] == "Risk Classification":
            overall_table.setStyle(TableStyle([
                ("BACKGROUND", (1, i), (1, i), risk_color),
                ("TEXTCOLOR", (1, i), (1, i), colors.white),
                ("FONTNAME", (1, i), (1, i), "Helvetica-Bold"),
            ]))
    
    elements.append(overall_table)
    elements.append(PageBreak())
    
    # ===== MOLECULAR PROPERTIES =====
    elements.append(Paragraph("1. Molecular Properties", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    props = result.molecular_properties
    prop_data = [
        ["Property", "Value", "Rule of Five", "Status"],
    ]
    
    mw = props.get("molecular_weight", 0)
    prop_data.append(["Molecular Weight", f"{mw:.2f} Da", "≤ 500", "✓" if mw <= 500 else "✗"])
    
    logp = props.get("logp", 0)
    prop_data.append(["LogP (XLogP3)", f"{logp:.2f}", "≤ 5", "✓" if logp <= 5 else "✗"])
    
    hbd = props.get("hbd", 0)
    prop_data.append(["H-Bond Donors", str(hbd), "≤ 5", "✓" if hbd <= 5 else "✗"])
    
    hba = props.get("hba", 0)
    prop_data.append(["H-Bond Acceptors", str(hba), "≤ 10", "✓" if hba <= 10 else "✗"])
    
    tpsa = props.get("tpsa", 0)
    prop_data.append(["Topological PSA", f"{tpsa:.2f} Å²", "≤ 140", "✓" if tpsa <= 140 else "✗"])
    
    rotb = props.get("rotatable_bonds", 0)
    prop_data.append(["Rotatable Bonds", str(rotb), "≤ 10", "✓" if rotb <= 10 else "✗"])
    
    prop_table = Table(prop_data, colWidths=[45 * mm, 30 * mm, 30 * mm, 25 * mm])
    prop_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
    ]))
    elements.append(prop_table)
    elements.append(Spacer(1, 4 * mm))
    
    # Drug-likeness assessment
    dl = props.get("drug_likeness", {})
    if dl:
        elements.append(Paragraph("Drug-Likeness Assessment", subheading_style))
        dl_data = [
            ["Rule", "Pass", "Criteria"],
        ]
        for rule_name, passed in [
            ("Lipinski (Rule of Five)", dl.get("lipinski", {}).get("passes", False)),
            ("Veber Rule", dl.get("veber", {}).get("passes", False)),
            ("Egan Rule", dl.get("egan", {}).get("passes", False)),
            ("Ghose Filter", dl.get("ghose", {}).get("passes", False)),
            ("Muegge Filter", dl.get("muegge", {}).get("passes", False)),
        ]:
            dl_data.append([rule_name, "✓ PASS" if passed else "✗ FAIL", ""])
        
        dl_table = Table(dl_data, colWidths=[50 * mm, 25 * mm, 55 * mm])
        dl_table.setStyle(TableStyle([
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
        elements.append(dl_table)
        elements.append(PageBreak())
    
    # ===== ADMET PREDICTIONS BY CATEGORY =====
    elements.append(Paragraph("2. ADMET Predictions by Category", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    category_order = ["absorption", "distribution", "metabolism", "excretion", "toxicity"]
    category_names = {
        "absorption": "Absorption",
        "distribution": "Distribution",
        "metabolism": "Metabolism",
        "excretion": "Excretion",
        "toxicity": "Toxicity",
    }
    
    for cat in category_order:
        cat_score = score.category_scores.get(cat)
        if not cat_score or not cat_score.endpoint_scores:
            continue
        
        elements.append(Paragraph(f"2.{category_order.index(cat)+1} {category_names[cat]}", subheading_style))
        elements.append(Spacer(1, 1 * mm))
        
        # Category summary
        cat_summary = [
            ["Category Score", f"{cat_score.score:.3f}"],
            ["Risk Level", cat_score.risk_level],
            ["Favorable Endpoints", f"{cat_score.favorable_count}/{cat_score.total_count}"],
        ]
        cat_table = Table(cat_summary, colWidths=[40 * mm, 30 * mm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d6e4f0")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(cat_table)
        elements.append(Spacer(1, 2 * mm))
        
        # Endpoint details
        ep_data = [
            ["Endpoint", "Prediction", "Probability", "Confidence", "Favorable"],
        ]
        
        for es in cat_score.endpoint_scores:
            pred_obj = next((p for p in result.predictions if p.endpoint == es.endpoint), None)
            prediction_text = pred_obj.prediction if pred_obj else "N/A"
            
            ep_data.append([
                es.endpoint.replace("_", " ").title(),
                prediction_text,
                f"{es.raw_score:.3f}",
                es.confidence.capitalize(),
                "✓" if es.is_favorable else "✗",
            ])
        
        ep_table = Table(ep_data, colWidths=[35 * mm, 30 * mm, 20 * mm, 20 * mm, 15 * mm])
        ep_table.setStyle(TableStyle([
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
        elements.append(ep_table)
        elements.append(Spacer(1, 6 * mm))
    
    elements.append(PageBreak())
    
    # ===== KEY FINDINGS =====
    elements.append(Paragraph("3. Key Findings & Risk Assessment", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    # High confidence unfavorable
    unfavorable = []
    for cat, cat_score in score.category_scores.items():
        for es in cat_score.endpoint_scores:
            if not es.is_favorable and es.confidence in ("high", "medium"):
                unfavorable.append({
                    "category": cat,
                    "endpoint": es.endpoint,
                    "prediction": next((p.prediction for p in result.predictions if p.endpoint == es.endpoint), ""),
                    "probability": es.raw_score,
                    "confidence": es.confidence,
                })
    
    if unfavorable:
        elements.append(Paragraph("High/Medium Confidence Unfavorable Predictions", subheading_style))
        unfav_data = [["Category", "Endpoint", "Prediction", "Probability", "Confidence"]]
        for u in unfavorable[:15]:
            unfav_data.append([
                u["category"].capitalize(),
                u["endpoint"].replace("_", " ").title(),
                u["prediction"],
                f"{u['probability']:.3f}",
                u["confidence"].capitalize(),
            ])
        
        unfav_table = Table(unfav_data, colWidths=[25 * mm, 30 * mm, 35 * mm, 20 * mm, 20 * mm])
        unfav_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c00000")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fce4ec"), colors.white]),
        ]))
        elements.append(unfav_table)
    else:
        elements.append(Paragraph("No high/medium confidence unfavorable predictions identified.", normal_style))
    
    elements.append(Spacer(1, 6 * mm))
    
    # ===== LIMITATIONS =====
    elements.append(Paragraph("4. Limitations & Disclaimers", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    for lim in score.limitations:
        elements.append(Paragraph(f"• {lim}", small_style))
        elements.append(Spacer(1, 1 * mm))
    
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        "This report is generated by computational prediction models and should not be used "
        "as a substitute for experimental validation. All predictions carry uncertainty and "
        "should be interpreted in the context of the specific drug development program.",
        small_style,
    ))
    
    # Build PDF
    doc.build(elements)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    if output_path:
        Path(output_path).write_bytes(pdf_bytes)
        logger.info("PDF report saved to %s", output_path)
    
    return pdf_bytes


def generate_admet_csv_report(
    result: ADMETResult,
    score: OverallADMETScore | None = None,
    compound_name: str | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate CSV report for ADMET predictions.
    
    Args:
        result: ADMET prediction result
        score: Overall ADMET score
        compound_name: Optional compound name
        output_path: Optional file path to save CSV
        
    Returns:
        CSV string
    """
    if score is None:
        score = calculate_overall_admet_score(result)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header metadata
    writer.writerow(["ADMET Prediction Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Compound Name", compound_name or ""])
    writer.writerow(["SMILES", result.smiles])
    writer.writerow(["Overall Score", f"{score.overall_score:.3f}"])
    writer.writerow(["Risk Classification", score.risk_classification])
    writer.writerow(["Drug-Likeness Score", f"{score.drug_likeness_score:.3f}"])
    writer.writerow([])
    
    # Molecular properties
    writer.writerow(["Molecular Properties"])
    writer.writerow(["Property", "Value", "Unit"])
    props = result.molecular_properties
    writer.writerow(["Molecular Weight", f"{props.get('molecular_weight', 0):.2f}", "Da"])
    writer.writerow(["LogP", f"{props.get('logp', 0):.2f}", ""])
    writer.writerow(["H-Bond Donors", props.get("hbd", 0), ""])
    writer.writerow(["H-Bond Acceptors", props.get("hba", 0), ""])
    writer.writerow(["TPSA", f"{props.get('tpsa', 0):.2f}", "Å²"])
    writer.writerow(["Rotatable Bonds", props.get("rotatable_bonds", 0), ""])
    writer.writerow(["Molecular Formula", props.get("molecular_formula", ""), ""])
    writer.writerow([])
    
    # Drug-likeness
    dl = props.get("drug_likeness", {})
    writer.writerow(["Drug-Likeness Rules"])
    writer.writerow(["Rule", "Passes"])
    for rule in ["lipinski", "veber", "egan", "ghose", "muegge"]:
        rule_data = dl.get(rule, {})
        writer.writerow([rule.capitalize(), "Yes" if rule_data.get("passes") else "No"])
    writer.writerow([])
    
    # Predictions by category
    writer.writerow(["ADMET Predictions"])
    writer.writerow(["Category", "Endpoint", "Prediction", "Probability", "Confidence", "Favorable"])
    
    for cat in ["absorption", "distribution", "metabolism", "excretion", "toxicity"]:
        cat_score = score.category_scores.get(cat)
        if not cat_score:
            continue
        for es in cat_score.endpoint_scores:
            pred_obj = next((p for p in result.predictions if p.endpoint == es.endpoint), None)
            writer.writerow([
                cat.capitalize(),
                es.endpoint,
                pred_obj.prediction if pred_obj else "",
                f"{es.raw_score:.4f}",
                es.confidence,
                "Yes" if es.is_favorable else "No",
            ])
    writer.writerow([])
    
    # Category scores
    writer.writerow(["Category Scores"])
    writer.writerow(["Category", "Score", "Risk Level", "Favorable/Total"])
    for cat, cat_score in score.category_scores.items():
        writer.writerow([
            cat.capitalize(),
            f"{cat_score.score:.4f}",
            cat_score.risk_level,
            f"{cat_score.favorable_count}/{cat_score.total_count}",
        ])
    writer.writerow([])
    
    # Summary
    writer.writerow(["Summary"])
    writer.writerow(["Metric", "Value"])
    for key, value in score.summary.items():
        writer.writerow([key.replace("_", " ").title(), value])
    
    csv_string = output.getvalue()
    output.close()
    
    if output_path:
        Path(output_path).write_text(csv_string, encoding="utf-8")
        logger.info("CSV report saved to %s", output_path)
    
    return csv_string


def generate_admet_json_report(
    result: ADMETResult,
    score: OverallADMETScore | None = None,
    compound_name: str | None = None,
) -> dict[str, Any]:
    """Generate JSON-serializable report.
    
    Args:
        result: ADMET prediction result
        score: Overall ADMET score
        compound_name: Optional compound name
        
    Returns:
        Dictionary with full report data
    """
    if score is None:
        score = calculate_overall_admet_score(result)
    
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "compound_name": compound_name,
            "smiles": result.smiles,
            "model_version": "1.0",
        },
        "molecular_properties": result.molecular_properties,
        "overall_assessment": {
            "overall_score": score.overall_score,
            "risk_classification": score.risk_classification,
            "drug_likeness_score": score.drug_likeness_score,
        },
        "category_scores": {
            cat: {
                "score": cs.score,
                "risk_level": cs.risk_level,
                "favorable_count": cs.favorable_count,
                "total_count": cs.total_count,
                "endpoints": [
                    {
                        "endpoint": es.endpoint,
                        "raw_score": es.raw_score,
                        "normalized_score": es.normalized_score,
                        "confidence": es.confidence,
                        "is_favorable": es.is_favorable,
                        "weight": es.weight,
                    }
                    for es in cs.endpoint_scores
                ],
            }
            for cat, cs in score.category_scores.items()
        },
        "predictions": [
            {
                "endpoint": p.endpoint,
                "category": p.category,
                "value": p.value,
                "probability": p.probability,
                "prediction": p.prediction,
                "confidence": p.confidence,
                "method": p.method,
                "details": p.details,
            }
            for p in result.predictions
        ],
        "limitations": score.limitations,
    }