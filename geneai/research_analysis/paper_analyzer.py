"""AI-powered research paper analyzer and structured summary generator."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from geneai.research_analysis.literature_clients import (
    search_all_sources,
    get_europe_pmc_fulltext,
    get_openalex_work,
)
from geneai.drug_discovery.api_clients import fetch_pubmed_abstracts

logger = logging.getLogger(__name__)


@dataclass
class PaperMetadata:
    """Structured paper metadata."""
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    openalex_id: str | None = None
    title: str = ""
    abstract: str | None = None
    full_text: str | None = None
    authors: str | None = None
    journal: str | None = None
    year: str | None = None
    source: str = ""
    url: str = ""
    is_open_access: bool = False
    open_access_url: str | None = None
    citation_count: int = 0
    concepts: list[str] = field(default_factory=list)
    type: str = ""


@dataclass
class ExtractedEntities:
    """Extracted biological entities from paper."""
    genes: list[dict[str, Any]] = field(default_factory=list)
    proteins: list[dict[str, Any]] = field(default_factory=list)
    diseases: list[dict[str, Any]] = field(default_factory=list)
    drugs: list[dict[str, Any]] = field(default_factory=list)
    pathways: list[dict[str, Any]] = field(default_factory=list)
    mutations: list[dict[str, Any]] = field(default_factory=list)
    biomarkers: list[dict[str, Any]] = field(default_factory=list)
    chemicals: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StructuredSummary:
    """AI-generated structured summary of a paper."""
    objectives: list[str] = field(default_factory=list)
    methodology: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    conclusions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    future_work: list[str] = field(default_factory=list)
    experimental_models: list[str] = field(default_factory=list)
    sample_sizes: list[str] = field(default_factory=list)
    statistical_methods: list[str] = field(default_factory=list)


@dataclass
class DrugTargetRelationship:
    """Drug-target relationship extracted from paper."""
    drug_name: str
    target_name: str
    relationship_type: str  # inhibitor, activator, binder, modulator, etc.
    evidence_type: str  # experimental, computational, clinical, review
    affinity_value: str | None = None
    affinity_unit: str | None = None
    assay_type: str | None = None
    organism: str | None = None
    context: str = ""
    confidence: str = "medium"  # high, medium, low
    source_text: str = ""
    pmid: str | None = None
    doi: str | None = None


# Regex patterns for entity extraction
GENE_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9]{1,}[A-Z0-9])\b"
)
PROTEIN_PATTERN = re.compile(
    r"\b([A-Z]{2,}[0-9]{1,}[A-Z]?)\b"
)
MUTATION_PATTERN = re.compile(
    r"\b([A-Z][a-z]{2}\d+[A-Z][a-z]{2}|\w+\.\d+[A-Z]>[A-Z]|\w+:\w+:\w+\.\w+)\b"
)
DISEASE_PATTERNS = [
    re.compile(r"\b(cancer|carcinoma|tumor|tumour|neoplasm|malignancy|lymphoma|leukemia|melanoma|sarcoma)\b", re.I),
    re.compile(r"\b(diabetes|alzheimer|parkinson|huntington|als|multiple sclerosis|arthritis)\b", re.I),
    re.compile(r"\b(covid-19|sars-cov-2|coronavirus|influenza|hiv|hepatitis)\b", re.I),
]
DRUG_PATTERNS = [
    re.compile(r"\b(ibuprofen|aspirin|metformin|insulin|doxorubicin|paclitaxel|cisplatin|rituximab|trastuzumab|bevacizumab|pembrolizumab|nivolumab|ipilimumab)\b", re.I),
    re.compile(r"\b([A-Z]{2,}-\d+|[A-Z]{3,}\d+[A-Z]?)\b"),  # Drug codes
]
PATHWAY_PATTERNS = [
    re.compile(r"\b(PI3K|AKT|mTOR|MAPK|ERK|JAK|STAT|NF-κB|WNT|NOTCH|HEDGEHOG|TGF-β|VEGF|EGFR|HER2|PD-1|PD-L1|CTLA-4|BRCA|TP53|KRAS|EGFR|ALK|ROS1|MET|RET|NTRK)\b", re.I),
]


def extract_entities_from_text(text: str, pmid: str | None = None, doi: str | None = None) -> ExtractedEntities:
    """Extract biological entities from text using pattern matching."""
    entities = ExtractedEntities()
    text_lower = text.lower()

    # Extract genes (simplified - in production would use NER model)
    gene_matches = set()
    for match in GENE_PATTERN.finditer(text):
        gene = match.group(1)
        if len(gene) >= 2 and gene.isupper() and not gene.isdigit():
            # Filter out common false positives
            if gene not in {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "HAVE", "HAS", "HAD", "WERE", "BEEN", "THEIR", "THEY", "THEM", "WHICH", "WHEN", "WHERE", "WHILE", "ABOUT", "AFTER", "BEFORE", "DURING", "INTO", "OVER", "UNDER", "AGAIN", "FURTHER", "THEN", "ONCE", "HERE", "THERE", "WHEN", "WHY", "HOW", "ALL", "ANY", "BOTH", "EACH", "FEW", "MORE", "MOST", "OTHER", "SOME", "SUCH", "ONLY", "OWN", "SAME", "SO", "THAN", "TOO", "VERY", "CAN", "WILL", "JUST", "DON", "SHOULD", "NOW"}:
                gene_matches.add(gene)

    for gene in sorted(gene_matches):
        entities.genes.append({
            "symbol": gene,
            "source_text": f"Found in text",
            "pmid": pmid,
            "doi": doi,
            "confidence": "low",  # Would be higher with NER
        })

    # Extract proteins (similar approach)
    protein_matches = set()
    for match in PROTEIN_PATTERN.finditer(text):
        protein = match.group(1)
        if len(protein) >= 3 and any(c.isdigit() for c in protein):
            protein_matches.add(protein)

    for protein in sorted(protein_matches):
        entities.proteins.append({
            "name": protein,
            "source_text": f"Found in text",
            "pmid": pmid,
            "doi": doi,
            "confidence": "low",
        })

    # Extract diseases
    for pattern in DISEASE_PATTERNS:
        for match in pattern.finditer(text):
            disease = match.group(1)
            entities.diseases.append({
                "name": disease,
                "source_text": match.group(0),
                "pmid": pmid,
                "doi": doi,
                "confidence": "medium",
            })

    # Extract drugs
    for pattern in DRUG_PATTERNS:
        for match in pattern.finditer(text):
            drug = match.group(1)
            entities.drugs.append({
                "name": drug,
                "source_text": match.group(0),
                "pmid": pmid,
                "doi": doi,
                "confidence": "medium",
            })

    # Extract pathways
    for pattern in PATHWAY_PATTERNS:
        for match in pattern.finditer(text):
            pathway = match.group(1)
            entities.pathways.append({
                "name": pathway,
                "source_text": match.group(0),
                "pmid": pmid,
                "doi": doi,
                "confidence": "medium",
            })

    # Extract mutations
    for match in MUTATION_PATTERN.finditer(text):
        mutation = match.group(1)
        entities.mutations.append({
            "variant": mutation,
            "source_text": match.group(0),
            "pmid": pmid,
            "doi": doi,
            "confidence": "medium",
        })

    return entities


def generate_structured_summary(text: str) -> StructuredSummary:
    """Generate structured summary from paper text using rule-based extraction."""
    summary = StructuredSummary()

    # Simple section detection based on keywords
    sentences = re.split(r'(?<=[.!?])\s+', text)

    current_section = "general"
    section_keywords = {
        "objectives": ["objective", "aim", "goal", "hypothesis", "purpose", "investigate", "study"],
        "methodology": ["method", "methodology", "approach", "technique", "protocol", "procedure", "experiment", "assay", "analysis"],
        "results": ["result", "finding", "observed", "showed", "demonstrated", "revealed", "indicated", "significant", "p-value", "p value"],
        "conclusions": ["conclusion", "conclude", "suggest", "imply", "support", "hypothesis", "consistent"],
        "limitations": ["limitation", "limited", "caveat", "weakness", "shortcoming", "constraint"],
        "future_work": ["future", "further", "next", "additional", "investigate", "explore", "validate", "confirm"],
    }

    for sentence in sentences:
        sentence_lower = sentence.lower()
        matched_section = None
        for section, keywords in section_keywords.items():
            if any(kw in sentence_lower for kw in keywords):
                matched_section = section
                break

        if matched_section:
            current_section = matched_section
            if len(sentence.strip()) > 20:
                getattr(summary, current_section).append(sentence.strip())
        elif current_section != "general" and len(sentence.strip()) > 30:
            getattr(summary, current_section).append(sentence.strip())

    # Extract experimental models
    model_patterns = [
        r"(mouse|mice|rat|rats|zebrafish|xenopus|drosophila|c\. elegans|cell line|hela|hek293|mcf-?7|a549|patient|clinical|cohort)",
    ]
    for pattern in model_patterns:
        for match in re.finditer(pattern, text, re.I):
            summary.experimental_models.append(match.group(1))

    # Extract sample sizes
    sample_patterns = [
        r"(n\s*=\s*\d+|sample size of \d+|\d+ patients|\d+ subjects|\d+ participants)",
    ]
    for pattern in sample_patterns:
        for match in re.finditer(pattern, text, re.I):
            summary.sample_sizes.append(match.group(1))

    # Extract statistical methods
    stat_patterns = [
        r"(t-test|anova|chi-square|chi-squared|regression|logistic|cox|kaplan-meier|log-rank|fisher|mann-whitney|wilcoxon|pearson|spearman)",
    ]
    for pattern in stat_patterns:
        for match in re.finditer(pattern, text, re.I):
            summary.statistical_methods.append(match.group(1))

    # Deduplicate
    for attr in ["objectives", "methodology", "key_findings", "results", "conclusions", "limitations", "future_work", "experimental_models", "sample_sizes", "statistical_methods"]:
        val = getattr(summary, attr)
        if val:
            setattr(summary, attr, list(dict.fromkeys(val))[:10])  # Limit to 10 per section

    return summary


def extract_drug_target_relationships(text: str, pmid: str | None = None, doi: str | None = None) -> list[DrugTargetRelationship]:
    """Extract drug-target relationships from paper text."""
    relationships = []

    # Pattern for drug-target interactions
    interaction_patterns = [
        r"(\w+)\s+(inhibit|activate|bind|modulate|target|block|antagonize|agonize)\s+(\w+)",
        r"(\w+)\s+(inhibitor|activator|binder|modulator|antagonist|agonist)\s+(of|for)\s+(\w+)",
        r"(\w+)\s+targets\s+(\w+)",
        r"(\w+)\s+-\s*(\w+)\s+interaction",
    ]

    for pattern in interaction_patterns:
        for match in re.finditer(pattern, text, re.I):
            groups = match.groups()
            if len(groups) >= 3:
                if "inhibit" in pattern or "activate" in pattern or "bind" in pattern or "modulate" in pattern or "target" in pattern or "block" in pattern or "antagonize" in pattern or "agonize" in pattern:
                    drug, rel_type, target = groups[0], groups[1], groups[2]
                elif "inhibitor" in pattern or "activator" in pattern or "binder" in pattern or "modulator" in pattern or "antagonist" in pattern or "agonist" in pattern:
                    drug, rel_type, _, target = groups[0], groups[1], groups[2], groups[3]
                else:
                    continue

                relationships.append(DrugTargetRelationship(
                    drug_name=drug.strip(),
                    target_name=target.strip(),
                    relationship_type=rel_type.strip(),
                    evidence_type="experimental" if any(kw in text.lower() for kw in ["assay", "experiment", "measured", "determined", "ic50", "ec50", "kd", "ki"]) else "computational",
                    context=match.group(0),
                    source_text=text[max(0, match.start()-100):match.end()+100],
                    pmid=pmid,
                    doi=doi,
                    confidence="medium",
                ))

    return relationships


def fetch_paper_content(paper: dict[str, Any]) -> PaperMetadata:
    """Fetch full paper content including abstract and full text if available."""
    metadata = PaperMetadata(
        pmid=paper.get("pmid"),
        pmcid=paper.get("pmcid"),
        doi=paper.get("doi"),
        openalex_id=paper.get("openalex_id"),
        title=paper.get("title", ""),
        abstract=paper.get("abstract"),
        authors=paper.get("authors"),
        journal=paper.get("journal"),
        year=paper.get("year"),
        source=paper.get("source", ""),
        url=paper.get("url", ""),
        is_open_access=paper.get("is_open_access", False),
        open_access_url=paper.get("open_access_url"),
        citation_count=paper.get("citation_count", 0),
        concepts=paper.get("concepts", []),
        type=paper.get("type", ""),
    )

    # Try to get abstract from PubMed if we have PMID
    if metadata.pmid and not metadata.abstract:
        try:
            abstracts = fetch_pubmed_abstracts([metadata.pmid])
            metadata.abstract = abstracts.get(metadata.pmid)
        except Exception as e:
            logger.warning("Failed to fetch PubMed abstract: %s", e)

    # Try to get full text from Europe PMC if open access
    if metadata.pmcid and metadata.is_open_access and not metadata.full_text:
        try:
            metadata.full_text = get_europe_pmc_fulltext(metadata.pmcid)
        except Exception as e:
            logger.warning("Failed to fetch Europe PMC full text: %s", e)

    # Try to get more details from OpenAlex
    if metadata.openalex_id and not metadata.full_text:
        try:
            work = get_openalex_work(metadata.openalex_id)
            if work and work.get("open_access_url"):
                metadata.open_access_url = work["open_access_url"]
        except Exception as e:
            logger.warning("Failed to fetch OpenAlex details: %s", e)

    return metadata


def analyze_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Complete paper analysis pipeline."""
    # Fetch content
    metadata = fetch_paper_content(paper)

    # Combine text for analysis
    full_text = " ".join(filter(None, [
        metadata.title,
        metadata.abstract,
        metadata.full_text,
    ]))

    # Extract entities
    entities = extract_entities_from_text(full_text, metadata.pmid, metadata.doi)

    # Generate structured summary
    summary = generate_structured_summary(full_text)

    # Extract drug-target relationships
    dt_relationships = extract_drug_target_relationships(full_text, metadata.pmid, metadata.doi)

    return {
        "metadata": metadata.__dict__,
        "entities": entities.__dict__,
        "summary": summary.__dict__,
        "drug_target_relationships": [r.__dict__ for r in dt_relationships],
        "analysis_timestamp": __import__("datetime").datetime.now().isoformat(),
    }


def analyze_research_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Analyze a collection of papers, returning one structured result each.

    Errors on individual papers are logged and skipped so a single bad record
    cannot abort a batch analysis.
    """
    results: list[dict[str, Any]] = []
    for paper in papers:
        try:
            results.append(analyze_paper(paper))
        except Exception:  # pragma: no cover - defensive batch handling
            logger.warning("Failed to analyze paper %r", paper.get("title"), exc_info=True)
    return results
