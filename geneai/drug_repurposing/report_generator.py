"""Report generation module for drug repurposing analysis."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from geneai.drug_discovery import drug_report

logger = logging.getLogger(__name__)


def generate_repurposing_report_csv(
    analysis_result: dict[str, Any],
    include_score_breakdown: bool = True,
) -> str:
    """Generate CSV report for drug repurposing analysis."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["GeneAI Research - Drug Repurposing Analysis Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Disease", analysis_result.get("disease", {}).get("name", "N/A")])
    writer.writerow([])

    # Disease Information
    disease = analysis_result.get("disease", {})
    writer.writerow(["DISEASE INFORMATION"])
    writer.writerow(["Field", "Value"])
    writer.writerow(["Name", disease.get("name", "N/A")])
    writer.writerow(["Disease ID", disease.get("disease_id", "N/A")])
    writer.writerow(["Description", disease.get("description", "N/A")])
    writer.writerow(["Therapeutic Areas", "; ".join([ta.get("name", "") for ta in disease.get("therapeutic_areas", [])])])
    writer.writerow(["Known Drugs Count", disease.get("known_drugs_count", "N/A")])
    writer.writerow(["Associated Targets Count", disease.get("associated_targets_count", "N/A")])
    writer.writerow([])

    # Targets Analyzed
    writer.writerow(["TARGETS ANALYZED"])
    writer.writerow(["Target ID", "Gene Symbol", "Target Name", "Association Score", "Biotype", "Known Drugs"])
    targets = disease.get("targets", [])
    for t in targets:
        writer.writerow([
            t.get("target_id", "N/A"),
            t.get("approved_symbol", "N/A"),
            t.get("approved_name", "N/A"),
            t.get("association_score", "N/A"),
            t.get("biotype", "N/A"),
            t.get("known_drugs_count", "N/A"),
        ])
    writer.writerow([])

    # Top Candidates
    writer.writerow(["TOP REPURPOSING CANDIDATES"])
    candidates = analysis_result.get("top_candidates", [])
    if candidates:
        # Basic info
        writer.writerow([
            "Rank", "Drug Name", "Drug ID", "Target Gene", "Target ID",
            "Mechanism of Action", "Action Type", "Max Phase",
            "Indication", "Overall Score", "Evidence Classification",
            "Evidence Sources", "Supporting PMIDs"
        ])

        for c in candidates:
            writer.writerow([
                c.get("rank", "N/A"),
                c.get("drug_name", "N/A"),
                c.get("drug_id", "N/A"),
                c.get("target_symbol", "N/A"),
                c.get("target_id", "N/A"),
                c.get("mechanism_of_action", "N/A"),
                c.get("action_type", "N/A"),
                c.get("max_phase", "N/A"),
                c.get("indication", "N/A"),
                c.get("overall_score", "N/A"),
                c.get("evidence_classification", "N/A"),
                "; ".join(c.get("evidence_sources", [])),
                "; ".join(c.get("supporting_pmids", [])),
            ])

        writer.writerow([])

        # Score breakdown if requested
        if include_score_breakdown:
            writer.writerow(["DETAILED SCORE BREAKDOWN"])
            writer.writerow([
                "Drug Name", "Component", "Score", "Weight", "Weighted Score", "Description"
            ])

            for c in candidates:
                breakdown = c.get("score_breakdown", {})
                components = breakdown.get("components", [])
                for comp in components:
                    writer.writerow([
                        c.get("drug_name", "N/A"),
                        comp.get("name", "N/A"),
                        comp.get("score", "N/A"),
                        comp.get("weight", "N/A"),
                        comp.get("weighted_score", "N/A"),
                        comp.get("description", "N/A"),
                    ])

    else:
        writer.writerow(["No candidates found"])

    writer.writerow([])

    # Evidence Summary
    evidence_summary = analysis_result.get("evidence_summary", {})
    if evidence_summary:
        writer.writerow(["EVIDENCE SUMMARY"])
        writer.writerow(["Metric", "Value"])
        for key, value in evidence_summary.items():
            if isinstance(value, dict):
                writer.writerow([key, json.dumps(value)])
            else:
                writer.writerow([key, value])
        writer.writerow([])

    # Analysis Metadata
    metadata = analysis_result.get("analysis_metadata", {})
    writer.writerow(["ANALYSIS METADATA"])
    writer.writerow(["Parameter", "Value"])
    for key, value in metadata.items():
        if isinstance(value, list):
            writer.writerow([key, "; ".join(str(v) for v in value)])
        else:
            writer.writerow([key, value])
    writer.writerow([])

    # Limitations
    limitations = metadata.get("limitations", [])
    if limitations:
        writer.writerow(["LIMITATIONS"])
        for lim in limitations:
            writer.writerow([lim])

    return output.getvalue()


def generate_repurposing_report_json(analysis_result: dict[str, Any]) -> str:
    """Generate JSON report for drug repurposing analysis."""
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "tool": "GeneAI Research",
            "version": "4.6",
            "report_type": "drug_repurposing_analysis",
        },
        "analysis": analysis_result,
    }
    return json.dumps(report, indent=2, default=str)


def generate_candidate_comparison_csv(
    candidates: list[dict[str, Any]],
    indices: list[int],
) -> str:
    """Generate CSV comparing selected candidates."""
    output = io.StringIO()
    writer = csv.writer(output)

    selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
    if len(selected) < 2:
        writer.writerow(["Error: Need at least 2 candidates to compare"])
        return output.getvalue()

    writer.writerow(["GeneAI Research - Drug Candidate Comparison"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow([])

    # Compare attributes
    attributes = [
        "drug_name", "drug_id", "target_symbol", "target_id",
        "mechanism_of_action", "action_type", "max_phase",
        "indication", "overall_score", "evidence_classification",
        "evidence_sources", "supporting_pmids",
    ]

    writer.writerow(["Attribute"] + [c.get("drug_name", "Unknown") for c in selected])

    for attr in attributes:
        row = [attr.replace("_", " ").title()]
        for c in selected:
            val = c.get(attr, "N/A")
            if isinstance(val, list):
                val = "; ".join(str(v) for v in val)
            row.append(val)
        writer.writerow(row)

    writer.writerow([])
    writer.writerow(["SCORE BREAKDOWN COMPARISON"])

    # Compare score components
    for c in selected:
        breakdown = c.get("score_breakdown", {})
        components = breakdown.get("components", [])
        writer.writerow([f"--- {c.get('drug_name', 'Unknown')} ---"])
        writer.writerow(["Component", "Score", "Weight", "Weighted Score", "Description"])
        for comp in components:
            writer.writerow([
                comp.get("name", "N/A"),
                comp.get("score", "N/A"),
                comp.get("weight", "N/A"),
                comp.get("weighted_score", "N/A"),
                comp.get("description", "N/A"),
            ])
        writer.writerow([])

    return output.getvalue()


def generate_repurposing_pdf_content(analysis_result: dict[str, Any]) -> dict[str, Any]:
    """Generate structured content for PDF report (to be rendered by PDF library)."""
    disease = analysis_result.get("disease", {})
    candidates = analysis_result.get("top_candidates", [])
    evidence_summary = analysis_result.get("evidence_summary", {})
    metadata = analysis_result.get("analysis_metadata", {})

    sections = [
        {
            "title": "Drug Repurposing Analysis Report",
            "subtitle": f"GeneAI Research - {disease.get('name', 'Unknown Disease')}",
            "type": "title_page",
            "content": {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "disease": disease.get("name"),
                "disease_id": disease.get("disease_id"),
                "candidates_analyzed": len(candidates),
                "top_candidates": len([c for c in candidates if c.get("overall_score", 0) > 0.5]),
            },
        },
        {
            "title": "Disease Overview",
            "type": "section",
            "content": {
                "name": disease.get("name"),
                "disease_id": disease.get("disease_id"),
                "description": disease.get("description"),
                "therapeutic_areas": [ta.get("name", "") for ta in disease.get("therapeutic_areas", [])],
                "known_drugs_count": disease.get("known_drugs_count"),
                "associated_targets_count": disease.get("associated_targets_count"),
                "source": disease.get("source"),
                "source_url": disease.get("source_url"),
            },
        },
        {
            "title": "Associated Targets",
            "type": "table",
            "columns": ["Target ID", "Gene Symbol", "Target Name", "Association Score", "Biotype", "Known Drugs"],
            "rows": [
                [
                    t.get("target_id", "N/A"),
                    t.get("approved_symbol", "N/A"),
                    t.get("approved_name", "N/A"),
                    t.get("association_score", "N/A"),
                    t.get("biotype", "N/A"),
                    t.get("known_drugs_count", "N/A"),
                ]
                for t in disease.get("targets", [])[:20]
            ],
        },
        {
            "title": "Top Repurposing Candidates",
            "type": "table",
            "columns": ["Rank", "Drug", "Target", "Mechanism", "Phase", "Indication", "Score", "Evidence Class"],
            "rows": [
                [
                    c.get("rank", i + 1),
                    c.get("drug_name", "N/A"),
                    c.get("target_symbol", "N/A"),
                    c.get("mechanism_of_action", "N/A")[:50],
                    c.get("max_phase", "N/A"),
                    c.get("indication", "N/A"),
                    f"{c.get('overall_score', 0):.3f}",
                    c.get("evidence_classification", "N/A"),
                ]
                for i, c in enumerate(candidates[:20])
            ],
        },
    ]

    # Add score breakdown for top 5 candidates
    for c in candidates[:5]:
        breakdown = c.get("score_breakdown", {})
        components = breakdown.get("components", [])
        if components:
            sections.append({
                "title": f"Score Breakdown: {c.get('drug_name')}",
                "type": "table",
                "columns": ["Component", "Score", "Weight", "Weighted Score", "Description"],
                "rows": [
                    [
                        comp.get("name", "N/A").replace("_", " ").title(),
                        f"{comp.get('score', 0):.3f}",
                        f"{comp.get('weight', 0):.3f}",
                        f"{comp.get('weighted_score', 0):.3f}",
                        comp.get("description", "N/A")[:80],
                    ]
                    for comp in components
                ],
            })

    # Evidence summary
    sections.append({
        "title": "Evidence Summary",
        "type": "section",
        "content": {
            "evidence_classification_distribution": evidence_summary.get("evidence_classification_distribution", {}),
            "average_scores": evidence_summary.get("average_scores", {}),
            "top_targets": evidence_summary.get("top_targets", {}),
            "total_candidates": evidence_summary.get("total_candidates", 0),
        },
    })

    # Limitations
    sections.append({
        "title": "Limitations and Disclaimers",
        "type": "list",
        "items": metadata.get("limitations", [
            "Scores are computational predictions, not experimental validations",
            "Evidence from public databases may be incomplete",
            "Clinical relevance requires experimental validation",
            "Drug-target interactions may not translate to therapeutic efficacy",
        ]),
    })

    return {
        "title": "Drug Repurposing Analysis Report",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": sections,
    }


def export_analysis_to_database(analysis_result: dict[str, Any]) -> int:
    """Export repurposing analysis results to local database."""
    # This would integrate with drug_database.py
    # For now, return a placeholder
    logger = logging.getLogger(__name__)
    logger.info("Database export not yet implemented for repurposing analysis")
    return 0


def build_repurposing_summary_report(
    analysis_result: dict[str, Any],
) -> str:
    """Build a markdown summary report."""
    disease = analysis_result.get("disease", {})
    candidates = analysis_result.get("top_candidates", [])
    evidence_summary = analysis_result.get("evidence_summary", {})

    lines = [
        "# Drug Repurposing Analysis Report",
        f"**Disease:** {disease.get('name', 'Unknown')} ({disease.get('disease_id', 'N/A')})",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Candidates Found:** {len(candidates)}",
        "",
        "## Disease Overview",
        f"- **Description:** {disease.get('description', 'N/A')}",
        f"- **Therapeutic Areas:** {', '.join([ta.get('name', '') for ta in disease.get('therapeutic_areas', [])])}",
        f"- **Known Drugs:** {disease.get('known_drugs_count', 'N/A')}",
        f"- **Associated Targets:** {disease.get('associated_targets_count', 'N/A')}",
        "",
        "## Top Repurposing Candidates",
        "",
        "| Rank | Drug | Target | Mechanism | Phase | Indication | Score | Evidence |",
        "|------|------|--------|-----------|-------|------------|-------|----------|",
    ]

    for c in candidates[:15]:
        row = (f"| {c.get('rank', 'N/A')} | {c.get('drug_name', 'N/A')} | "
               f"{c.get('target_symbol', 'N/A')} | "
               f"{c.get('mechanism_of_action', 'N/A')[:40]} | "
               f"{c.get('max_phase', 'N/A')} | "
               f"{c.get('indication', 'N/A')} | "
               f"{c.get('overall_score', 0):.3f} | "
               f"{c.get('evidence_classification', 'N/A')} |")
        lines.append(row)

    more_lines = [
        "",
        "## Evidence Summary",
        f"- **Total Candidates:** {evidence_summary.get('total_candidates', 0)}",
        f"- **Evidence Distribution:** {evidence_summary.get('evidence_classification_distribution', {})}",
        f"- **Average Overall Score:** {evidence_summary.get('average_scores', {}).get('overall', 0):.3f}",
        "",
        "## Limitations",
        "- Scores are computational predictions, not experimental validations",
        "- Evidence from public databases may be incomplete",
        "- Clinical relevance requires experimental validation",
        "- Drug-target interactions may not translate to therapeutic efficacy",
        "",
        "---",
        "*Report generated by GeneAI Research Phase 4.6*",
    ]

    lines.extend(more_lines)

    return "\n".join(lines)