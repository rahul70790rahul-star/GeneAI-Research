"""Research gap identification engine."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResearchGap:
    """Identified research gap."""
    gap_type: str  # underexplored_topic, missing_evidence, unanswered_question, conflicting_findings, understudied_entity, therapeutic_opportunity
    description: str
    entities_involved: list[str] = field(default_factory=list)
    supporting_papers: list[str] = field(default_factory=list)  # PMIDs or DOIs
    confidence: str = "medium"  # high, medium, low
    evidence_summary: str = ""
    suggested_experiments: list[str] = field(default_factory=list)


@dataclass
class GapAnalysisResult:
    """Result of gap analysis."""
    gaps: list[ResearchGap] = field(default_factory=list)
    topic_coverage: dict[str, int] = field(default_factory=dict)
    entity_coverage: dict[str, int] = field(default_factory=dict)
    conflicting_findings: list[dict[str, Any]] = field(default_factory=list)
    analysis_metadata: dict[str, Any] = field(default_factory=dict)


def identify_gaps_from_papers(analyzed_papers: list[dict[str, Any]]) -> GapAnalysisResult:
    """Identify research gaps from a collection of analyzed papers."""
    result = GapAnalysisResult()

    if not analyzed_papers:
        return result

    # Collect all entities and topics
    all_genes = Counter()
    all_proteins = Counter()
    all_diseases = Counter()
    all_drugs = Counter()
    all_pathways = Counter()
    all_mutations = Counter()
    all_biomarkers = Counter()
    all_conclusions = []
    all_limitations = []
    all_future_work = []

    paper_count = len(analyzed_papers)
    result.analysis_metadata["total_papers_analyzed"] = paper_count

    for paper in analyzed_papers:
        entities = paper.get("entities", {})
        summary = paper.get("summary", {})
        metadata = paper.get("metadata", {})

        pmid = metadata.get("pmid")
        doi = metadata.get("doi")
        paper_id = pmid or doi or "unknown"

        # Count entities
        for gene in entities.get("genes", []):
            all_genes[gene.get("symbol", "")] += 1
        for protein in entities.get("proteins", []):
            all_proteins[protein.get("name", "")] += 1
        for disease in entities.get("diseases", []):
            all_diseases[disease.get("name", "")] += 1
        for drug in entities.get("drugs", []):
            all_drugs[drug.get("name", "")] += 1
        for pathway in entities.get("pathways", []):
            all_pathways[pathway.get("name", "")] += 1
        for mutation in entities.get("mutations", []):
            all_mutations[mutation.get("variant", "")] += 1
        for biomarker in entities.get("biomarkers", []):
            all_biomarkers[biomarker.get("name", "")] += 1

        # Collect conclusions, limitations, future work
        all_conclusions.extend(summary.get("conclusions", []))
        all_limitations.extend(summary.get("limitations", []))
        all_future_work.extend(summary.get("future_work", []))

    # Store coverage
    result.entity_coverage = {
        "genes": dict(all_genes.most_common(20)),
        "proteins": dict(all_proteins.most_common(20)),
        "diseases": dict(all_diseases.most_common(20)),
        "drugs": dict(all_drugs.most_common(20)),
        "pathways": dict(all_pathways.most_common(20)),
        "mutations": dict(all_mutations.most_common(20)),
        "biomarkers": dict(all_biomarkers.most_common(20)),
    }

    # Identify understudied entities (mentioned in < 10% of papers)
    threshold = max(1, paper_count * 0.1)

    for entity_type, counts in [
        ("genes", all_genes),
        ("proteins", all_proteins),
        ("diseases", all_diseases),
        ("drugs", all_drugs),
        ("pathways", all_pathways),
    ]:
        for entity, count in counts.items():
            if count < threshold and count > 0:
                # This entity is mentioned but not well studied
                result.gaps.append(ResearchGap(
                    gap_type="understudied_entity",
                    description=f"{entity_type.capitalize()[:-1]} '{entity}' mentioned in only {count}/{paper_count} papers",
                    entities_involved=[entity],
                    supporting_papers=[paper_id for paper in analyzed_papers if entity in str(paper.get("entities", {}))],
                    confidence="medium",
                    evidence_summary=f"Low coverage in literature ({count}/{paper_count} papers)",
                    suggested_experiments=[f"Investigate role of {entity} in {entity_type} context"],
                ))

    # Identify underexplored topics from future work suggestions
    future_work_counter = Counter()
    for fw in all_future_work:
        # Extract key terms
        words = fw.lower().split()
        for i, word in enumerate(words):
            if len(word) > 4 and word not in {"further", "future", "studies", "research", "investigate", "explore", "validate", "confirm", "additional", "required", "necessary", "important"}:
                future_work_counter[word] += 1

    for topic, count in future_work_counter.most_common(10):
        if count >= 2:
            result.gaps.append(ResearchGap(
                gap_type="underexplored_topic",
                description=f"Topic '{topic}' suggested for future investigation in {count} papers",
                entities_involved=[topic],
                supporting_papers=[],
                confidence="medium",
                evidence_summary=f"Repeatedly mentioned in future work sections",
                suggested_experiments=[f"Design studies to explore {topic}"],
            ))

    # Identify missing evidence (limitations)
    limitation_counter = Counter()
    for lim in all_limitations:
        words = lim.lower().split()
        for word in words:
            if len(word) > 4:
                limitation_counter[word] += 1

    for lim_topic, count in limitation_counter.most_common(10):
        if count >= 2:
            result.gaps.append(ResearchGap(
                gap_type="missing_evidence",
                description=f"Limitation regarding '{lim_topic}' mentioned in {count} papers",
                entities_involved=[lim_topic],
                supporting_papers=[],
                confidence="medium",
                evidence_summary=f"Common limitation across multiple studies",
                suggested_experiments=[f"Address limitation: {lim_topic}"],
            ))

    # Identify conflicting findings
    # Simple approach: look for contradictory conclusions
    conclusion_keywords = Counter()
    for conc in all_conclusions:
        words = conc.lower().split()
        for word in words:
            if len(word) > 4:
                conclusion_keywords[word] += 1

    # Look for papers with opposite conclusions on same topic
    # This is simplified - in reality would need more sophisticated NLP
    for topic, count in conclusion_keywords.most_common(20):
        if count >= 3:
            # Check if there are contradictory statements
            positive = sum(1 for c in all_conclusions if topic in c.lower() and any(w in c.lower() for w in ["increase", "enhance", "promote", "activate", "upregulate", "positive", "beneficial"]))
            negative = sum(1 for c in all_conclusions if topic in c.lower() and any(w in c.lower() for w in ["decrease", "reduce", "inhibit", "suppress", "downregulate", "negative", "detrimental"]))
            if positive > 0 and negative > 0:
                result.conflicting_findings.append({
                    "topic": topic,
                    "positive_evidence": positive,
                    "negative_evidence": negative,
                    "description": f"Conflicting evidence on {topic}: {positive} papers report positive effects, {negative} report negative effects",
                })
                result.gaps.append(ResearchGap(
                    gap_type="conflicting_findings",
                    description=f"Conflicting evidence on {topic}",
                    entities_involved=[topic],
                    supporting_papers=[],
                    confidence="high",
                    evidence_summary=f"{positive} positive vs {negative} negative findings",
                    suggested_experiments=[f"Resolve conflicting evidence on {topic} with controlled experiments"],
                ))

    # Identify therapeutic opportunities (disease + target with limited drug coverage)
    for disease, d_count in all_diseases.most_common(10):
        for target, t_count in all_genes.most_common(20):
            # Check if this disease-target pair has drug mentions
            drug_mentions = sum(1 for paper in analyzed_papers
                              if disease.lower() in str(paper.get("entities", {}).get("diseases", [])).lower()
                              and target.lower() in str(paper.get("entities", {}).get("genes", [])).lower()
                              and len(paper.get("entities", {}).get("drugs", [])) > 0)
            if d_count >= 2 and t_count >= 2 and drug_mentions == 0:
                result.gaps.append(ResearchGap(
                    gap_type="therapeutic_opportunity",
                    description=f"Disease '{disease}' and target '{target}' co-mentioned but no drug candidates identified",
                    entities_involved=[disease, target],
                    supporting_papers=[],
                    confidence="medium",
                    evidence_summary=f"Disease ({d_count} papers) and target ({t_count} papers) studied but no therapeutic agents reported",
                    suggested_experiments=[f"Screen compounds for {target} in {disease} models"],
                ))

    return result


def generate_gap_report(gap_analysis: GapAnalysisResult, format: str = "markdown") -> str:
    """Generate a formatted research gap report."""
    if format == "markdown":
        lines = [
            "# Research Gap Analysis Report",
            "",
            f"**Papers Analyzed:** {gap_analysis.analysis_metadata.get('total_papers_analyzed', 0)}",
            "",
            "## Identified Research Gaps",
            "",
        ]

        for i, gap in enumerate(gap_analysis.gaps, 1):
            lines.extend([
                f"### Gap {i}: {gap.gap_type.replace('_', ' ').title()}",
                f"**Description:** {gap.description}",
                f"**Confidence:** {gap.confidence}",
                f"**Entities Involved:** {', '.join(gap.entities_involved) if gap.entities_involved else 'N/A'}",
                f"**Evidence Summary:** {gap.evidence_summary}",
                f"**Suggested Experiments:**",
            ])
            for exp in gap.suggested_experiments:
                lines.append(f"- {exp}")
            if gap.supporting_papers:
                lines.append(f"**Supporting Papers:** {', '.join(gap.supporting_papers[:5])}")
            lines.append("")

        lines.extend([
            "## Entity Coverage Summary",
            "",
        ])
        for entity_type, counts in gap_analysis.entity_coverage.items():
            lines.append(f"### {entity_type.capitalize()}")
            for entity, count in list(counts.items())[:10]:
                lines.append(f"- {entity}: {count} papers")
            lines.append("")

        if gap_analysis.conflicting_findings:
            lines.extend([
                "## Conflicting Findings",
                "",
            ])
            for conflict in gap_analysis.conflicting_findings:
                lines.extend([
                    f"### {conflict['topic']}",
                    f"- Positive evidence: {conflict['positive_evidence']} papers",
                    f"- Negative evidence: {conflict['negative_evidence']} papers",
                    f"- {conflict['description']}",
                    "",
                ])

        lines.extend([
            "---",
            "*Disclaimer: These are computational suggestions based on literature analysis. "
            "They do not represent validated scientific discoveries and require experimental validation.*",
        ])

        return "\n".join(lines)

    elif format == "json":
        import json
        return json.dumps({
            "gaps": [g.__dict__ for g in gap_analysis.gaps],
            "entity_coverage": gap_analysis.entity_coverage,
            "conflicting_findings": gap_analysis.conflicting_findings,
            "analysis_metadata": gap_analysis.analysis_metadata,
        }, indent=2)

    else:
        return str(gap_analysis)