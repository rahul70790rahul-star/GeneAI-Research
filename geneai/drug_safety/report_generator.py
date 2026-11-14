"""Report generation for drug safety and toxicity prediction."""
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
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)


def generate_ds_pdf_report(
    run_data: dict[str, Any],
    pubchem_tox: list[dict[str, Any]],
    chembl_tox: list[dict[str, Any]],
    admetlab_pred: dict[str, Any] | None,
    ml_predictions: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    run_id: str | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Generate comprehensive PDF report for drug safety analysis."""
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
    
    # Risk color mapping
    risk_colors = {
        "High": colors.HexColor("#c00000"),
        "Moderate": colors.HexColor("#bf8f00"),
        "Low-Moderate": colors.HexColor("#548235"),
        "Low": colors.HexColor("#548235"),
    }
    
    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 30 * mm))
    elements.append(Paragraph("Drug Safety & Toxicity Prediction Report", title_style))
    elements.append(Spacer(1, 5 * mm))
    
    if run_id:
        elements.append(Paragraph(f"Run ID: {run_id}", subtitle_style))
    
    identifier = run_data.get("identifier", "N/A")
    id_type = run_data.get("identifier_type", "N/A")
    elements.append(Paragraph(f"Compound: {identifier} ({id_type})", subtitle_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))
    elements.append(Spacer(1, 10 * mm))
    
    # Risk Assessment Summary
    risk_assessment = run_data.get("risk_assessment", {})
    risk_level = risk_assessment.get("risk_level", "Unknown")
    risk_score = risk_assessment.get("risk_score", 0.0)
    risk_color = risk_colors.get(risk_level, colors.HexColor("#4a4a4a"))
    
    summary_data = [
        ["Metric", "Value"],
        ["Overall Risk Level", risk_level],
        ["Risk Score", f"{risk_score:.3f}"],
        ["Risk Factors Identified", str(risk_assessment.get("num_factors", 0))],
        ["Data Sources", ", ".join(run_data.get("data_sources", ["None"]))],
        ["Molecular Properties Computed", "Yes" if run_data.get("molecular_properties") else "No"],
        ["Structural Alerts", str(len(run_data.get("structural_alerts", {})))],
        ["PubChem Assays Found", str(len(pubchem_tox))],
        ["ChEMBL Assays Found", str(len(chembl_tox))],
        ["ADMETlab Prediction", "Available" if admetlab_pred else "Not Available"],
        ["ML Endpoints Predicted", str(len(ml_predictions))],
        ["Drug Interactions Found", str(len(interactions))],
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
    # Highlight risk level row
    for i, row in enumerate(summary_data):
        if row[0] == "Overall Risk Level":
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (1, i), (1, i), risk_color),
                ("TEXTCOLOR", (1, i), (1, i), colors.white),
                ("FONTNAME", (1, i), (1, i), "Helvetica-Bold"),
            ]))
    
    elements.append(summary_table)
    elements.append(PageBreak())
    
    # ===== MOLECULAR PROPERTIES =====
    elements.append(Paragraph("1. Molecular Properties", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    mol_props = run_data.get("molecular_properties", {})
    if mol_props:
        # Key properties table
        key_props = [
            ("Molecular Weight", f"{mol_props.get('molecular_weight', 0):.2f} Da"),
            ("LogP (MolLogP)", f"{mol_props.get('logp', 0):.2f}"),
            ("TPSA", f"{mol_props.get('tpsa', 0):.2f} Å²"),
            ("H-Bond Donors", str(mol_props.get('hbd', 0))),
            ("H-Bond Acceptors", str(mol_props.get('hba', 0))),
            ("Rotatable Bonds", str(mol_props.get('rotatable_bonds', 0))),
            ("Aromatic Rings", str(mol_props.get('aromatic_rings', 0))),
            ("Heavy Atoms", str(mol_props.get('heavy_atoms', 0))),
            ("Formal Charge", str(mol_props.get('formal_charge', 0))),
            ("Lipinski Violations", str(mol_props.get('lipinski_violations', 0))),
        ]
        
        prop_data = [["Property", "Value"]]
        for k, v in key_props:
            prop_data.append([k, v])
        
        prop_table = Table(prop_data, colWidths=[60 * mm, 40 * mm])
        prop_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(prop_table)
        elements.append(Spacer(1, 6 * mm))
    
    # ===== STRUCTURAL ALERTS =====
    elements.append(Paragraph("2. Structural Alerts", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    alerts = run_data.get("structural_alerts", {})
    if alerts:
        alert_data = [["Alert Type", "Status"]]
        alert_names = {
            "pains_alerts": "PAINS (Pan-Assay Interference)",
            "brenk_alerts": "Brenk Structural Alerts",
            "nih_alerts": "NIH Structural Alerts",
            "alert_aldehyde": "Aldehyde Group",
            "alert_epoxide": "Epoxide Group",
            "alert_michael_acceptor": "Michael Acceptor",
            "alert_alkylating": "Alkylating Agent",
            "alert_nitro": "Nitro Group",
        }
        for key, value in alerts.items():
            if value > 0:
                alert_data.append([alert_names.get(key, key), f"⚠️ DETECTED ({int(value)})"])
            else:
                alert_data.append([alert_names.get(key, key), "Not Detected"])
        
        alert_table = Table(alert_data, colWidths=[80 * mm, 40 * mm])
        alert_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c00000")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fce4ec"), colors.white]),
        ]))
        elements.append(alert_table)
    else:
        elements.append(Paragraph("No structural alerts data available.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== RISK FACTORS =====
    elements.append(Paragraph("3. Risk Factor Analysis", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    risk_factors = risk_assessment.get("risk_factors", [])
    if risk_factors:
        rf_data = [["#", "Risk Factor"]]
        for i, factor in enumerate(risk_factors, 1):
            rf_data.append([str(i), factor])
        
        rf_table = Table(rf_data, colWidths=[15 * mm, 125 * mm])
        rf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c00000")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fce4ec"), colors.white]),
        ]))
        elements.append(rf_table)
    else:
        elements.append(Paragraph("No specific risk factors identified.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== PUB CHEM TOXICITY =====
    elements.append(Paragraph("4. PubChem BioAssay Toxicity Data", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if pubchem_tox:
        # Filter active assays
        active_assays = [a for a in pubchem_tox if a.get("activity_outcome") == "Active"]
        
        if active_assays:
            elements.append(Paragraph(f"Active Toxicity Assays: {len(active_assays)}", subheading_style))
            pc_data = [["Assay ID", "Assay Name", "Target", "Organism", "Score", "Conc. Value", "Conc. Unit"]]
            for a in active_assays[:30]:
                pc_data.append([
                    a.get("assay_id", "")[:15],
                    a.get("assay_name", "")[:40],
                    a.get("target_name", "")[:25],
                    a.get("organism", "")[:15],
                    f"{a.get('activity_score', 0):.1f}",
                    f"{a.get('concentration_value', 0):.2f}",
                    a.get("concentration_unit", ""),
                ])
            
            pc_table = Table(pc_data, colWidths=[15*mm, 35*mm, 25*mm, 15*mm, 12*mm, 15*mm, 15*mm])
            pc_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c00000")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fce4ec"), colors.white]),
            ]))
            elements.append(pc_table)
        
        # Inactive assays summary
        inactive_count = len(pubchem_tox) - len(active_assays)
        if inactive_count > 0:
            elements.append(Paragraph(f"Inactive/Inconclusive Assays: {inactive_count}", subheading_style))
    else:
        elements.append(Paragraph("No PubChem toxicity data found for this compound.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== CHEMBL TOXICITY =====
    elements.append(Paragraph("5. ChEMBL Toxicity Data", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if chembl_tox:
        # Focus on potency-related endpoints
        potency_assays = [a for a in chembl_tox if a.get("standard_type") in ("IC50", "EC50", "LD50", "LC50", "GI50")]
        
        if potency_assays:
            elements.append(Paragraph(f"Potency Assays Found: {len(potency_assays)}", subheading_style))
            cb_data = [["Assay", "Target", "Type", "Value", "Unit", "Relation", "Organism"]]
            for a in potency_assays[:30]:
                cb_data.append([
                    a.get("assay_chembl_id", "")[:15],
                    a.get("target_name", "")[:30],
                    a.get("standard_type", ""),
                    f"{a.get('standard_value', 0):.2f}",
                    a.get("standard_unit", ""),
                    a.get("standard_relation", ""),
                    a.get("organism", "")[:15],
                ])
            
            cb_table = Table(cb_data, colWidths=[15*mm, 30*mm, 12*mm, 15*mm, 12*mm, 12*mm, 15*mm])
            cb_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
            ]))
            elements.append(cb_table)
        else:
            elements.append(Paragraph("No potency assays (IC50/EC50/LD50) found.", normal_style))
    else:
        elements.append(Paragraph("No ChEMBL toxicity data found.", normal_style))
    
    elements.append(PageBreak())
    
    # ===== ADMETLAB PREDICTIONS =====
    if admetlab_pred:
        elements.append(Paragraph("6. ADMETlab Predictions", heading_style))
        elements.append(Spacer(1, 2 * mm))
        
        categories = [
            ("Absorption", admetlab_pred.get("absorption", {})),
            ("Distribution", admetlab_pred.get("distribution", {})),
            ("Metabolism", admetlab_pred.get("metabolism", {})),
            ("Excretion", admetlab_pred.get("excretion", {})),
            ("Toxicity", admetlab_pred.get("toxicity", {})),
        ]
        
        for cat_name, cat_data in categories:
            if not cat_data:
                continue
            elements.append(Paragraph(f"6.{categories.index((cat_name, cat_data))+1} {cat_name}", subheading_style))
            ad_data = [["Endpoint", "Value"]]
            for k, v in cat_data.items():
                if isinstance(v, (int, float)):
                    ad_data.append([k, f"{v:.3f}"])
                else:
                    ad_data.append([k, str(v)])
            
            ad_table = Table(ad_data, colWidths=[60 * mm, 40 * mm])
            ad_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
            ]))
            elements.append(ad_table)
            elements.append(Spacer(1, 4 * mm))
        
        elements.append(PageBreak())
    
    # ===== ML PREDICTIONS =====
    elements.append(Paragraph("7. ML Toxicity Predictions", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    if ml_predictions:
        # Group by confidence
        high_conf = [p for p in ml_predictions if p.get("confidence") == "high"]
        med_conf = [p for p in ml_predictions if p.get("confidence") == "medium"]
        low_conf = [p for p in ml_predictions if p.get("confidence") == "low"]
        
        # Toxic predictions
        toxic_preds = [p for p in ml_predictions if p.get("prediction") == "Toxic"]
        
        if toxic_preds:
            elements.append(Paragraph("⚠️ Predicted Toxic Endpoints", subheading_style))
            ml_data = [["Endpoint", "Probability", "Confidence", "Model", "CV AUC"]]
            for p in toxic_preds:
                details = p.get("details", {})
                ml_data.append([
                    p.get("endpoint", ""),
                    f"{p.get('probability', 0):.3f}",
                    p.get("confidence", "").capitalize(),
                    p.get("model_used", ""),
                    f"{details.get('cv_auc', 0):.3f}",
                ])
            
            ml_table = Table(ml_data, colWidths=[40*mm, 20*mm, 20*mm, 25*mm, 15*mm])
            ml_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c00000")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fce4ec"), colors.white]),
            ]))
            elements.append(ml_table)
            elements.append(Spacer(1, 6 * mm))
        
        # All predictions summary
        elements.append(Paragraph("All Endpoint Predictions", subheading_style))
        all_data = [["Endpoint", "Prediction", "Probability", "Confidence", "Model"]]
        for p in sorted(ml_predictions, key=lambda x: x.get("endpoint", "")):
            all_data.append([
                p.get("endpoint", ""),
                p.get("prediction", ""),
                f"{p.get('probability', 0):.3f}",
                p.get("confidence", "").capitalize(),
                p.get("model_used", ""),
            ])
        
        all_table = Table(all_data, colWidths=[35*mm, 20*mm, 20*mm, 20*mm, 30*mm])
        all_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(all_table)
    else:
        elements.append(Paragraph("No ML predictions available (models not trained).", normal_style))
    
    elements.append(PageBreak())
    
    # ===== DRUG INTERACTIONS =====
    if interactions:
        elements.append(Paragraph("8. Drug-Drug Interactions", heading_style))
        elements.append(Spacer(1, 2 * mm))
        
        di_data = [["Drug A", "Drug B", "Type", "Severity", "Description", "Source"]]
        for i in interactions:
            di_data.append([
                i.get("drug_a", ""),
                i.get("drug_b", ""),
                i.get("interaction_type", ""),
                i.get("severity", ""),
                i.get("description", "")[:50],
                i.get("source", ""),
            ])
        
        di_table = Table(di_data, colWidths=[20*mm, 20*mm, 15*mm, 15*mm, 40*mm, 20*mm])
        di_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e75b6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b4c6e7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7fb")]),
        ]))
        elements.append(di_table)
        elements.append(PageBreak())
    
    # ===== LIMITATIONS =====
    elements.append(Paragraph("9. Limitations & Disclaimers", heading_style))
    elements.append(Spacer(1, 2 * mm))
    
    limitations = [
        "This report presents computational predictions only, not experimentally validated results.",
        "Molecular property calculations use RDKit and may differ from experimental measurements.",
        "Structural alerts (PAINS, Brenk, NIH) indicate potential assay interference or reactivity, not confirmed toxicity.",
        "PubChem and ChEMBL assay data represent heterogeneous experimental conditions and endpoints.",
        "ADMETlab predictions (when available) are based on QSAR models with limited chemical space coverage.",
        "ML toxicity models require training on high-quality experimental data; placeholder models have not been trained.",
        "Drug-drug interactions require comprehensive databases (DrugBank, TWOSIDES) not fully integrated here.",
        "Risk scoring is heuristic and combines multiple evidence streams with arbitrary weights.",
        "Results should not be used for clinical decision-making without experimental validation.",
        "Data sources and model versions may change over time; results reflect state at generation time.",
    ]
    
    for lim in limitations:
        elements.append(Paragraph(f"• {lim}", small_style))
        elements.append(Spacer(1, 1 * mm))
    
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        "This report is generated by GeneAI Research Platform for research purposes only. "
        "It does not provide clinical safety assessments or regulatory guidance.",
        small_style,
    ))
    
    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    if output_path:
        Path(output_path).write_bytes(pdf_bytes)
        logger.info("Drug Safety PDF report saved to %s", output_path)
    
    return pdf_bytes


def generate_ds_csv_report(
    run_data: dict[str, Any],
    pubchem_tox: list[dict[str, Any]],
    chembl_tox: list[dict[str, Any]],
    admetlab_pred: dict[str, Any] | None,
    ml_predictions: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    run_id: str | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate CSV report for drug safety analysis."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Drug Safety & Toxicity Prediction Report"])
    writer.writerow(["Run ID", run_id or ""])
    writer.writerow(["Identifier", run_data.get("identifier", "")])
    writer.writerow(["Identifier Type", run_data.get("identifier_type", "")])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow([])
    
    # Risk Assessment
    risk = run_data.get("risk_assessment", {})
    writer.writerow(["Risk Assessment"])
    writer.writerow(["Risk Level", risk.get("risk_level", "")])
    writer.writerow(["Risk Score", f"{risk.get('risk_score', 0):.3f}"])
    writer.writerow(["Risk Factors", str(risk.get("num_factors", 0))])
    for i, factor in enumerate(risk.get("risk_factors", []), 1):
        writer.writerow([f"Risk Factor {i}", factor])
    writer.writerow([])
    
    # Molecular Properties
    writer.writerow(["Molecular Properties"])
    writer.writerow(["Property", "Value"])
    for k, v in run_data.get("molecular_properties", {}).items():
        writer.writerow([k, v])
    writer.writerow([])
    
    # Structural Alerts
    writer.writerow(["Structural Alerts"])
    writer.writerow(["Alert", "Count"])
    for k, v in run_data.get("structural_alerts", {}).items():
        writer.writerow([k, v])
    writer.writerow([])
    
    # PubChem
    writer.writerow(["PubChem Toxicity Assays"])
    writer.writerow(["Assay ID", "Assay Name", "Target", "Organism", "Outcome", "Score", "Conc Value", "Conc Unit"])
    for a in pubchem_tox:
        writer.writerow([
            a.get("assay_id", ""), a.get("assay_name", ""), a.get("target_name", ""),
            a.get("organism", ""), a.get("activity_outcome", ""), a.get("activity_score", ""),
            a.get("concentration_value", ""), a.get("concentration_unit", "")
        ])
    writer.writerow([])
    
    # ChEMBL
    writer.writerow(["ChEMBL Toxicity Assays"])
    writer.writerow(["Assay ID", "Description", "Target", "Type", "Value", "Unit", "Relation", "Organism"])
    for a in chembl_tox:
        writer.writerow([
            a.get("assay_chembl_id", ""), a.get("assay_description", ""), a.get("target_name", ""),
            a.get("standard_type", ""), a.get("standard_value", ""), a.get("standard_unit", ""),
            a.get("standard_relation", ""), a.get("organism", "")
        ])
    writer.writerow([])
    
    # ADMETlab
    if admetlab_pred:
        writer.writerow(["ADMETlab Predictions"])
        for cat, cat_data in [("Absorption", admetlab_pred.get("absorption", {})), 
                               ("Distribution", admetlab_pred.get("distribution", {})),
                               ("Metabolism", admetlab_pred.get("metabolism", {})),
                               ("Excretion", admetlab_pred.get("excretion", {})),
                               ("Toxicity", admetlab_pred.get("toxicity", {}))]:
            writer.writerow([f"{cat} Endpoints"])
            writer.writerow(["Endpoint", "Value"])
            for k, v in cat_data.items():
                writer.writerow([k, v])
            writer.writerow([])
    
    # ML Predictions
    writer.writerow(["ML Toxicity Predictions"])
    writer.writerow(["Endpoint", "Prediction", "Probability", "Confidence", "Model", "CV AUC", "CV AUC Std"])
    for p in ml_predictions:
        details = p.get("details", {})
        writer.writerow([
            p.get("endpoint", ""), p.get("prediction", ""), f"{p.get('probability', 0):.6f}",
            p.get("confidence", ""), p.get("model_used", ""),
            f"{details.get('cv_auc', 0):.6f}", f"{details.get('cv_auc_std', 0):.6f}"
        ])
    writer.writerow([])
    
    # Interactions
    writer.writerow(["Drug Interactions"])
    writer.writerow(["Drug A", "Drug B", "Type", "Severity", "Description", "Evidence", "Source"])
    for i in interactions:
        writer.writerow([
            i.get("drug_a", ""), i.get("drug_b", ""), i.get("interaction_type", ""),
            i.get("severity", ""), i.get("description", ""), i.get("evidence_level", ""),
            i.get("source", "")
        ])
    
    csv_string = output.getvalue()
    output.close()
    
    if output_path:
        Path(output_path).write_text(csv_string, encoding="utf-8")
        logger.info("Drug Safety CSV report saved to %s", output_path)
    
    return csv_string


def generate_ds_json_report(
    run_data: dict[str, Any],
    pubchem_tox: list[dict[str, Any]],
    chembl_tox: list[dict[str, Any]],
    admetlab_pred: dict[str, Any] | None,
    ml_predictions: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Generate JSON report for drug safety analysis."""
    return {
        "metadata": {
            "run_id": run_id,
            "identifier": run_data.get("identifier"),
            "identifier_type": run_data.get("identifier_type"),
            "generated_at": datetime.now().isoformat(),
            "data_sources": run_data.get("data_sources", []),
        },
        "risk_assessment": run_data.get("risk_assessment", {}),
        "molecular_properties": run_data.get("molecular_properties", {}),
        "structural_alerts": run_data.get("structural_alerts", {}),
        "pubchem_toxicity": pubchem_tox,
        "chembl_toxicity": chembl_tox,
        "admetlab_predictions": admetlab_pred,
        "ml_predictions": ml_predictions,
        "drug_interactions": interactions,
    }