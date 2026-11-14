"""Multi-paper comparison engine for research analysis."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PaperComparison:
    """Comparison result for multiple papers."""
    papers: list[dict[str, Any]] = field(default_factory=list)
    comparison_table: pd.DataFrame | None = None
    similarities: dict[str, Any] = field(default_factory=dict)
    differences: dict[str, Any] = field(default_factory=dict)
    evidence_summary: str = ""


def compare_papers(analyzed_papers: list[dict[str, Any]]) -> PaperComparison:
    """Compare multiple analyzed papers across key dimensions."""
    if len(analyzed_papers) < 2:
        raise ValueError("At least 2 papers required for comparison")

    comparison = PaperComparison()
    comparison.papers = analyzed_papers

    # Extract key dimensions for comparison
    dimensions = {
        "objectives": [],
        "methodology": [],
        "experimental_models": [],
        "sample_sizes": [],
        "statistical_methods": [],
        "key_findings": [],
        "results": [],
        "conclusions": [],
        "limitations": [],
        "future_work": [],
        "genes": [],
        "proteins": [],
        "diseases": [],
        "drugs": [],
        "pathways": [],
        "mutations": [],
    }

    paper_labels = []
    for i, paper in enumerate(analyzed_papers):
        metadata = paper.get("metadata", {})
        label = metadata.get("title", f"Paper {i+1}")[:50]
        if metadata.get("pmid"):
            label = f"PMID:{metadata['pmid']} - {label}"
        elif metadata.get("doi"):
            label = f"DOI:{metadata['doi'][:20]} - {label}"
        paper_labels.append(label)

        summary = paper.get("summary", {})
        entities = paper.get("entities", {})

        for dim in dimensions:
            if dim in summary:
                dimensions[dim].append("; ".join(summary[dim][:3]))
            elif dim in entities:
                if dim in ["genes"]:
                    dimensions[dim].append("; ".join([g.get("symbol", "") for g in entities[dim][:5]]))
                elif dim in ["proteins"]:
                    dimensions[dim].append("; ".join([p.get("name", "") for p in entities[dim][:5]]))
                elif dim in ["diseases"]:
                    dimensions[dim].append("; ".join([d.get("name", "") for d in entities[dim][:5]]))
                elif dim in ["drugs"]:
                    dimensions[dim].append("; ".join([dr.get("name", "") for dr in entities[dim][:5]]))
                elif dim in ["pathways"]:
                    dimensions[dim].append("; ".join([p.get("name", "") for p in entities[dim][:5]]))
                elif dim in ["mutations"]:
                    dimensions[dim].append("; ".join([m.get("variant", "") for m in entities[dim][:5]]))
                else:
                    dimensions[dim].append("")
            else:
                dimensions[dim].append("")

    # Create comparison DataFrame
    comparison_data = {"Dimension": list(dimensions.keys())}
    for i, label in enumerate(paper_labels):
        comparison_data[label] = [dimensions[dim][i] if i < len(dimensions[dim]) else "" for dim in dimensions.keys()]

    comparison.comparison_table = pd.DataFrame(comparison_data)

    # Compute similarities and differences
    comparison.similarities = _compute_similarities(analyzed_papers, paper_labels)
    comparison.differences = _compute_differences(analyzed_papers, paper_labels)
    comparison.evidence_summary = _generate_evidence_summary(comparison)

    return comparison


def _compute_similarities(analyzed_papers: list[dict[str, Any]], paper_labels: list[str]) -> dict[str, Any]:
    """Compute similarities across papers."""
    similarities = {
        "common_genes": [],
        "common_proteins": [],
        "common_diseases": [],
        "common_drugs": [],
        "common_pathways": [],
        "common_conclusions": [],
        "shared_methodology": [],
    }

    # Collect all entities
    all_entities = {}
    for i, paper in enumerate(analyzed_papers):
        entities = paper.get("entities", {})
        for entity_type in ["genes", "proteins", "diseases", "drugs", "pathways"]:
            for entity in entities.get(entity_type, []):
                key = entity.get("symbol") or entity.get("name") or ""
                if key:
                    if key not in all_entities:
                        all_entities[key] = {"type": entity_type, "papers": []}
                    all_entities[key]["papers"].append(paper_labels[i])

    # Find common entities (mentioned in >50% of papers)
    threshold = len(analyzed_papers) * 0.5
    for entity, info in all_entities.items():
        if len(info["papers"]) >= threshold:
            similarities[f"common_{info['type']}"].append({
                "entity": entity,
                "mentioned_in": info["papers"],
                "paper_count": len(info["papers"]),
            })

    # Common conclusions
    all_conclusions = []
    for paper in analyzed_papers:
        for conc in paper.get("summary", {}).get("conclusions", []):
            all_conclusions.append(conc.lower())

    # Simple keyword overlap for conclusions
    conclusion_words = Counter()
    for conc in all_conclusions:
        for word in conc.split():
            if len(word) > 4:
                conclusion_words[word] += 1

    for word, count in conclusion_words.most_common(10):
        if count >= len(analyzed_papers) * 0.5:
            similarities["common_conclusions"].append({
                "keyword": word,
                "paper_count": count,
            })

    return similarities


def _compute_differences(analyzed_papers: list[dict[str, Any]], paper_labels: list[str]) -> dict[str, Any]:
    """Compute differences across papers."""
    differences = {
        "unique_genes": {},
        "unique_proteins": {},
        "unique_diseases": {},
        "unique_drugs": {},
        "different_conclusions": [],
        "different_methodologies": [],
        "different_models": [],
    }

    # Find entities unique to each paper
    for i, paper in enumerate(analyzed_papers):
        entities = paper.get("entities", {})
        label = paper_labels[i]

        for entity_type in ["genes", "proteins", "diseases", "drugs"]:
            unique_entities = []
            for entity in entities.get(entity_type, []):
                key = entity.get("symbol") or entity.get("name") or ""
                if key:
                    # Check if this entity appears in other papers
                    found_elsewhere = False
                    for j, other_paper in enumerate(analyzed_papers):
                        if i != j:
                            other_entities = other_paper.get("entities", {}).get(entity_type, [])
                            other_keys = [e.get("symbol") or e.get("name") or "" for e in other_entities]
                            if key in other_keys:
                                found_elsewhere = True
                                break
                    if not found_elsewhere:
                        unique_entities.append(key)

            if unique_entities:
                differences[f"unique_{entity_type}"][label] = unique_entities

    return differences


def _generate_evidence_summary(comparison: PaperComparison) -> str:
    """Generate a human-readable evidence summary."""
    lines = ["## Multi-Paper Comparison Summary", ""]

    sim = comparison.similarities
    diff = comparison.differences

    lines.append("### Common Elements Across Papers")
    for key, items in sim.items():
        if items:
            lines.append(f"**{key.replace('_', ' ').title()}:**")
            for item in items[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('entity', item.get('keyword', ''))}: mentioned in {item.get('paper_count', 0)} papers")
                else:
                    lines.append(f"- {item}")
            lines.append("")

    lines.append("### Unique Elements Per Paper")
    for key, paper_items in diff.items():
        if paper_items:
            lines.append(f"**{key.replace('_', ' ').title()}:**")
            for paper, items in paper_items.items():
                if items:
                    lines.append(f"- {paper}: {', '.join(items[:5])}")
            lines.append("")

    return "\n".join(lines)


def export_comparison_csv(comparison: PaperComparison, filepath: str) -> None:
    """Export comparison table to CSV."""
    if comparison.comparison_table is not None:
        comparison.comparison_table.to_csv(filepath, index=False)


def export_comparison_json(comparison: PaperComparison, filepath: str) -> None:
    """Export comparison to JSON."""
    import json
    data = {
        "papers": [p.get("metadata", {}) for p in comparison.papers],
        "similarities": comparison.similarities,
        "differences": comparison.differences,
        "evidence_summary": comparison.evidence_summary,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)