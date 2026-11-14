"""Citation management for Biotech Assistant - Phase 5.1."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CitationStyle(Enum):
    """Citation formatting styles."""
    APA = "apa"
    MLA = "mla"
    VANCOUVER = "vancouver"
    IEEE = "ieee"


class SourceType(Enum):
    """Source types for citations."""
    PUBMED = "pubmed"
    DATABASE = "database"
    COMPUTATION = "computation"
    CLINICAL_TRIAL = "clinical_trial"
    PREPRINT = "preprint"
    PATENT = "patent"
    TEXTBOOK = "textbook"
    GUIDELINE = "guideline"
    WEBSITE = "website"
    UNKNOWN = "unknown"


class EvidenceGrade(Enum):
    """Evidence grading system."""
    LEVEL_1A = "level_1a"      # Systematic review/meta-analysis of RCTs
    LEVEL_1B = "level_1b"      # Individual RCT
    LEVEL_2A = "level_2a"      # Systematic review of cohort studies
    LEVEL_2B = "level_2b"      # Individual cohort study
    LEVEL_3A = "level_3a"      # Systematic review of case-control
    LEVEL_3B = "level_3b"      # Individual case-control
    LEVEL_4 = "level_4"        # Case series, poor quality studies
    LEVEL_5 = "level_5"        # Expert opinion, mechanism-based reasoning
    
    # Computational grades
    EXPERIMENTAL = "experimental"           # Direct experimental evidence
    DATABASE_CURATED = "database_curated"   # Expert-curated database
    COMPUTATIONAL_PREDICTION = "computational_prediction"  # ML/model
    LITERATURE_DERIVED = "literature_derived"  # From publications
    INFERENCE = "inference"                 # Logical inference
    SPECULATIVE = "speculative"             # Hypothesis


@dataclass
class Citation:
    """Scientific citation with rich metadata."""
    source_type: Any = SourceType.UNKNOWN
    identifier: str = ""
    source: str = ""
    title: str = ""
    authors: Any = ""
    year: int | None = None
    journal: str = ""
    volume: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    pmid: str = ""
    pmcid: str = ""
    evidence_grade: Any = EvidenceGrade.LITERATURE_DERIVED
    relevance: float = 1.0
    snippet: str = ""
    tool_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.source and self.source_type:
            self.source = self.source_type.value if hasattr(self.source_type, "value") else str(self.source_type)
        elif not self.source_type or self.source_type == SourceType.UNKNOWN:
            if self.source:
                s_lower = self.source.lower()
                if "pubmed" in s_lower:
                    self.source_type = SourceType.PUBMED
                elif "database" in s_lower:
                    self.source_type = SourceType.DATABASE
                elif "trial" in s_lower:
                    self.source_type = SourceType.CLINICAL_TRIAL
                else:
                    self.source_type = self._detect_source_type()
            else:
                self.source_type = self._detect_source_type()
        
        # Auto-detect evidence grade
        if self.evidence_grade == EvidenceGrade.LITERATURE_DERIVED:
            self.evidence_grade = self._detect_evidence_grade()
    
    def _detect_source_type(self) -> SourceType:
        """Detect source type from identifier/URL."""
        id_lower = self.identifier.lower()
        url_lower = self.url.lower()
        
        if "pmid:" in id_lower or "pubmed" in url_lower:
            return SourceType.PUBMED
        elif any(db in id_lower for db in ["uniprot", "pdb", "opentargets", "chembl", "drugbank", "string", "kegg", "reactome"]):
            return SourceType.DATABASE
        elif "clinicaltrials" in url_lower or "nct" in id_lower:
            return SourceType.CLINICAL_TRIAL
        elif "arxiv" in url_lower or "biorxiv" in url_lower or "medrxiv" in url_lower:
            return SourceType.PREPRINT
        elif "patent" in url_lower or "google.com/patents" in url_lower:
            return SourceType.PATENT
        elif self.tool_name and "predict" in self.tool_name.lower():
            return SourceType.COMPUTATION
        return SourceType.WEBSITE
    
    def _detect_evidence_grade(self) -> EvidenceGrade:
        """Detect evidence grade from source."""
        if self.source_type == SourceType.DATABASE:
            return EvidenceGrade.DATABASE_CURATED
        elif self.source_type == SourceType.COMPUTATION:
            return EvidenceGrade.COMPUTATIONAL_PREDICTION
        elif self.source_type == SourceType.CLINICAL_TRIAL:
            return EvidenceGrade.EXPERIMENTAL
        elif self.source_type == SourceType.PUBMED:
            # Would need to check study type - default to literature derived
            return EvidenceGrade.LITERATURE_DERIVED
        return EvidenceGrade.INFERENCE
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_type": self.source_type.value,
            "identifier": self.identifier,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "url": self.url,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "evidence_grade": self.evidence_grade.value,
            "relevance": self.relevance,
            "snippet": self.snippet,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Citation":
        """Deserialize from dictionary."""
        return cls(
            source_type=SourceType(data.get("source_type", "unknown")),
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            authors=data.get("authors", ""),
            year=data.get("year"),
            journal=data.get("journal", ""),
            doi=data.get("doi", ""),
            url=data.get("url", ""),
            pmid=data.get("pmid", ""),
            pmcid=data.get("pmcid", ""),
            evidence_grade=EvidenceGrade(data.get("evidence_grade", "literature_derived")),
            relevance=data.get("relevance", 1.0),
            snippet=data.get("snippet", ""),
            tool_name=data.get("tool_name", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )
    
    def _authors_str(self) -> str:
        if isinstance(self.authors, list):
            return ", ".join(str(a) for a in self.authors)
        return str(self.authors or "")

    def format_apa(self) -> str:
        """Format as APA citation."""
        parts = []
        auth = self._authors_str()
        if auth:
            parts.append(auth)
        if self.year:
            parts.append(f"({self.year})")
        if self.title:
            parts.append(self.title)
        if self.journal:
            parts.append(f"*{self.journal}*")
        if self.volume:
            vol_str = f"*{self.volume}*"
            if self.pages:
                vol_str += f", {self.pages}"
            parts.append(vol_str)
        elif self.pages:
            parts.append(self.pages)
        if self.doi:
            parts.append(f"https://doi.org/{self.doi}")
        elif self.url:
            parts.append(self.url)
        
        return ". ".join(parts) + ("." if parts else "")
    
    def format_vancouver(self) -> str:
        """Format as Vancouver citation."""
        parts = []
        if isinstance(self.authors, list) and len(self.authors) > 3:
            parts.append(f"{self.authors[0]}, et al.")
        elif self.authors:
            parts.append(self._authors_str())
        if self.title:
            parts.append(self.title)
        if self.journal:
            parts.append(self.journal)
        if self.year:
            parts.append(str(self.year))
        if self.doi:
            parts.append(f"doi:{self.doi}")
        
        return ". ".join(parts) + ("." if parts else "")
    
    def format_markdown(self) -> str:
        """Format as markdown link."""
        label = self.title or self.identifier
        url = self.url or (f"https://doi.org/{self.doi}" if self.doi else "#")
        return f"[{label}]({url})"
    
    def get_evidence_badge(self) -> str:
        """Get evidence grade badge text."""
        grade_labels = {
            EvidenceGrade.EXPERIMENTAL: "🟢 Experimental",
            EvidenceGrade.DATABASE_CURATED: "🔵 Curated Database",
            EvidenceGrade.COMPUTATIONAL_PREDICTION: "🟡 Computational",
            EvidenceGrade.LITERATURE_DERIVED: "📖 Literature",
            EvidenceGrade.INFERENCE: "🟠 Inference",
            EvidenceGrade.SPECULATIVE: "🔴 Speculative",
        }
        return grade_labels.get(self.evidence_grade, "⚪ Unknown")


class CitationManager:
    """Manages citations for answers."""
    
    def __init__(self):
        self.citations: list[Citation] = []
        self._seen_identifiers: set[str] = set()
    
    def add(self, citation: Citation) -> None:
        """Add a citation, deduplicating by identifier."""
        key = f"{citation.source_type.value}:{citation.identifier}"
        if key not in self._seen_identifiers:
            self.citations.append(citation)
            self._seen_identifiers.add(key)
    
    def add_from_tool_result(self, tool_name: str, result: Any, source_type: SourceType = SourceType.COMPUTATION) -> list[Citation]:
        """Create citations from tool results."""
        citations = []
        
        if tool_name == "search_pubmed" and isinstance(result, list):
            for paper in result[:5]:
                cit = Citation(
                    source_type=SourceType.PUBMED,
                    identifier=f"PMID:{paper.get('pmid', 'unknown')}",
                    title=paper.get("title", ""),
                    authors=paper.get("authors", ""),
                    year=paper.get("year"),
                    journal=paper.get("journal", ""),
                    doi=paper.get("doi", ""),
                    url=paper.get("url", ""),
                    pmid=str(paper.get("pmid", "")),
                    tool_name=tool_name,
                    snippet=paper.get("abstract", "")[:200],
                    evidence_grade=EvidenceGrade.LITERATURE_DERIVED,
                )
                self.add(cit)
                citations.append(cit)
        
        elif tool_name in ["run_disease_gene_pathway_analysis", "identify_disease_genes"]:
            cit = Citation(
                source_type=SourceType.DATABASE,
                identifier="OpenTargets",
                title="Open Targets Platform - Disease-Gene Associations",
                url="https://platform.opentargets.org/",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.DATABASE_CURATED,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["search_uniprot_protein"]:
            cit = Citation(
                source_type=SourceType.DATABASE,
                identifier="UniProt",
                title="UniProt Knowledgebase",
                url="https://www.uniprot.org/",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.DATABASE_CURATED,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["fetch_rcsb_entry_metadata"]:
            cit = Citation(
                source_type=SourceType.DATABASE,
                identifier="RCSB PDB",
                title="RCSB Protein Data Bank",
                url="https://www.rcsb.org/",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.DATABASE_CURATED,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["predict_admet", "calculate_overall_admet_score", "build_safety_profile", "predict_drug_safety"]:
            cit = Citation(
                source_type=SourceType.COMPUTATION,
                identifier=tool_name,
                title=f"{tool_name.replace('_', ' ').title()} Prediction",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.COMPUTATIONAL_PREDICTION,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["find_kg_nodes", "get_kg_neighbors", "find_kg_path"]:
            cit = Citation(
                source_type=SourceType.DATABASE,
                identifier="GeneAI Knowledge Graph",
                title="Integrated Biological Knowledge Graph",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.DATABASE_CURATED,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["run_mutation_to_drug_workflow"]:
            cit = Citation(
                source_type=SourceType.COMPUTATION,
                identifier="mutation_to_drug_workflow",
                title="Mutation-to-Drug Discovery Workflow",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.COMPUTATIONAL_PREDICTION,
            )
            self.add(cit)
            citations.append(cit)
        
        elif tool_name in ["run_integrated_precision_drug_discovery"]:
            cit = Citation(
                source_type=SourceType.COMPUTATION,
                identifier="integrated_precision_drug_discovery",
                title="Integrated Precision Drug Discovery Pipeline",
                tool_name=tool_name,
                evidence_grade=EvidenceGrade.COMPUTATIONAL_PREDICTION,
            )
            self.add(cit)
            citations.append(cit)
        
        return citations
    
    def get_all(self) -> list[Citation]:
        return self.citations.copy()
    
    def get_by_grade(self, grade: EvidenceGrade) -> list[Citation]:
        return [c for c in self.citations if c.evidence_grade == grade]
    
    def get_by_source(self, source: SourceType) -> list[Citation]:
        return [c for c in self.citations if c.source_type == source]
    
    def clear(self) -> None:
        self.citations.clear()
        self._seen_identifiers.clear()
    
    def format_bibliography(self, style: str = "apa") -> str:
        """Format all citations as bibliography."""
        if not self.citations:
            return "No citations."
        
        # Sort by evidence grade (experimental first) then relevance
        grade_order = {
            EvidenceGrade.EXPERIMENTAL: 0,
            EvidenceGrade.DATABASE_CURATED: 1,
            EvidenceGrade.CLINICAL_TRIAL: 2,
            EvidenceGrade.LITERATURE_DERIVED: 3,
            EvidenceGrade.COMPUTATIONAL_PREDICTION: 4,
            EvidenceGrade.INFERENCE: 5,
            EvidenceGrade.SPECULATIVE: 6,
        }
        
        sorted_citations = sorted(
            self.citations,
            key=lambda c: (grade_order.get(c.evidence_grade, 99), -c.relevance)
        )
        
        lines = []
        for i, cit in enumerate(sorted_citations, 1):
            if style == "apa":
                lines.append(f"{i}. {cit.format_apa()} [{cit.get_evidence_badge()}]")
            elif style == "vancouver":
                lines.append(f"{i}. {cit.format_vancouver()} [{cit.get_evidence_badge()}]")
            elif style == "markdown":
                lines.append(f"{i}. {cit.format_markdown()} [{cit.get_evidence_badge()}]")
            else:
                lines.append(f"{i}. {cit.format_apa()} [{cit.get_evidence_badge()}]")
        
        return "\n".join(lines)
    
    def to_dict_list(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.citations]


def create_citation_from_pubmed(paper: dict[str, Any]) -> Citation:
    """Create citation from PubMed paper dict."""
    return Citation(
        source_type=SourceType.PUBMED,
        identifier=f"PMID:{paper.get('pmid', 'unknown')}",
        title=paper.get("title", ""),
        authors=paper.get("authors", ""),
        year=paper.get("year"),
        journal=paper.get("journal", ""),
        doi=paper.get("doi", ""),
        url=paper.get("url", ""),
        pmid=str(paper.get("pmid", "")),
        evidence_grade=EvidenceGrade.LITERATURE_DERIVED,
    )


def create_citation_from_database(name: str, identifier: str, url: str, title: str = "") -> Citation:
    """Create citation from database."""
    return Citation(
        source_type=SourceType.DATABASE,
        identifier=identifier,
        title=title or name,
        url=url,
        evidence_grade=EvidenceGrade.DATABASE_CURATED,
    )


def create_citation_from_computation(tool_name: str, description: str = "") -> Citation:
    """Create citation from computational tool."""
    return Citation(
        source_type=SourceType.COMPUTATION,
        identifier=tool_name,
        title=description or f"{tool_name.replace('_', ' ').title()} Result",
        tool_name=tool_name,
        evidence_grade=EvidenceGrade.COMPUTATIONAL_PREDICTION,
    )


def format_citation(citation: Citation, style: CitationStyle = CitationStyle.APA) -> str:
    """Format a single citation in the given style."""
    if style == CitationStyle.APA:
        return citation.format_apa()
    elif style == CitationStyle.VANCOUVER:
        return citation.format_vancouver()
    elif style == CitationStyle.MLA:
        return citation.format_markdown()
    elif style == CitationStyle.IEEE:
        return citation.format_markdown()
    else:
        return citation.format_apa()


def format_bibliography(citations: list[Citation], style: CitationStyle = CitationStyle.APA) -> str:
    """Format a list of citations as a bibliography."""
    if not citations:
        return "No citations."
    lines = []
    for i, cit in enumerate(citations, 1):
        lines.append(f"{i}. {format_citation(cit, style)}")
    return "\n".join(lines)