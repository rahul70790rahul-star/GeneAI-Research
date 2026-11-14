"""AI Research Assistant for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from geneai.research import search_pubmed
from geneai.research_analysis import analyze_paper
from geneai.ai_research_intelligence.knowledge_graph import find_nodes, get_neighbors, shortest_path, get_subgraph

logger = logging.getLogger(__name__)


@dataclass
class ResearchQuestion:
    """Structured research question."""
    question_id: str
    question: str
    question_type: str  # mechanistic, therapeutic, diagnostic, prognostic, biomarker, safety
    entities: list[str] = field(default_factory=list)  # genes, drugs, diseases
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Evidence:
    """Evidence item with citation."""
    evidence_id: str
    source: str  # pubmed, knowledge_graph, database, clinical_trial
    citation: str
    content: str
    relevance_score: float
    entity_links: list[str] = field(default_factory=list)


@dataclass
class ResearchAnswer:
    """Structured answer to a research question."""
    answer_id: str
    question_id: str
    answer: str
    confidence: float
    evidence: list[Evidence]
    reasoning: str
    limitations: list[str]
    follow_up_questions: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ResearchSession:
    """Multi-turn research session."""
    session_id: str
    questions: list[ResearchQuestion] = field(default_factory=list)
    answers: list[ResearchAnswer] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AIResearchAssistant:
    """LLM-powered research assistant with traceable citations."""
    
    def __init__(self):
        self.sessions: dict[str, ResearchSession] = {}
        self.knowledge_cache: dict[str, Any] = {}
    
    def ask(self, question: str, session_id: str | None = None, context: dict[str, Any] | None = None) -> ResearchAnswer:
        """Ask a research question."""
        # Parse question
        parsed = self._parse_question(question, context)
        
        # Get or create session
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        else:
            session_id = session_id or str(uuid.uuid4())[:8]
            session = ResearchSession(session_id=session_id)
            self.sessions[session_id] = session
        
        session.questions.append(parsed)
        session.context.update(context or {})
        
        # Retrieve evidence
        evidence = self._retrieve_evidence(parsed)
        
        # Generate answer
        answer = self._generate_answer(parsed, evidence, session)
        
        session.answers.append(answer)
        session.updated_at = datetime.now().isoformat()
        
        return answer
    
    def _parse_question(self, question: str, context: dict[str, Any] | None) -> ResearchQuestion:
        """Parse question into structured format."""
        question_lower = question.lower()
        
        # Determine question type
        if any(kw in question_lower for kw in ["mechanism", "how does", "pathway", "molecular"]):
            q_type = "mechanistic"
        elif any(kw in question_lower for kw in ["treat", "therapy", "drug", "compound", "repurpose"]):
            q_type = "therapeutic"
        elif any(kw in question_lower for kw in ["diagnos", "biomarker", "detect", "screen"]):
            q_type = "diagnostic"
        elif any(kw in question_lower for kw in ["prognos", "outcome", "survival", "progression"]):
            q_type = "prognostic"
        elif any(kw in question_lower for kw in ["biomarker", "signature", "marker"]):
            q_type = "biomarker"
        elif any(kw in question_lower for kw in ["safe", "toxicity", "adverse", "side effect"]):
            q_type = "safety"
        else:
            q_type = "general"
        
        # Extract entities (simplified - in production would use NER)
        entities = []
        context = context or {}
        if "gene_symbols" in context:
            entities.extend(context["gene_symbols"])
        if "disease_names" in context:
            entities.extend(context["disease_names"])
        if "drug_names" in context:
            entities.extend(context["drug_names"])
        
        return ResearchQuestion(
            question_id=str(uuid.uuid4())[:8],
            question=question,
            question_type=q_type,
            entities=entities,
            context=context or {},
        )
    
    def _retrieve_evidence(self, question: ResearchQuestion) -> list[Evidence]:
        """Retrieve relevant evidence from multiple sources."""
        evidence = []
        
        # 1. PubMed literature search
        if question.entities:
            for entity in question.entities[:3]:  # Limit searches
                try:
                    papers = search_pubmed(f"{entity} {question.question}", limit=5)
                    for paper in papers:
                        evidence.append(Evidence(
                            evidence_id=str(uuid.uuid4())[:8],
                            source="pubmed",
                            citation=f"PMID:{paper['pmid']}",
                            content=f"{paper['title']}. {paper.get('abstract', '')[:500]}",
                            relevance_score=0.8,
                            entity_links=[entity],
                        ))
                except Exception as e:
                    logger.warning(f"PubMed search failed for {entity}: {e}")
        
        # 2. Knowledge graph
        for entity in question.entities:
            nodes = find_nodes(name=entity, limit=5)
            for node in nodes:
                neighbors = get_neighbors(node.node_id, limit=10)
                for edge, target in neighbors:
                    evidence.append(Evidence(
                        evidence_id=str(uuid.uuid4())[:8],
                        source="knowledge_graph",
                        citation=f"KG:{edge.source}:{edge.edge_type}",
                        content=f"{node.name} --{edge.edge_type}--> {target.name} (confidence: {edge.confidence:.2f})",
                        relevance_score=edge.confidence,
                        entity_links=[entity, target.identifier],
                    ))
        
        # 3. Database queries (would connect to actual databases)
        # Placeholder for ChEMBL, OpenTargets, ClinVar, etc.
        
        # Sort by relevance
        evidence.sort(key=lambda e: e.relevance_score, reverse=True)
        
        return evidence[:20]  # Limit
    
    def _generate_answer(self, question: ResearchQuestion, evidence: list[Evidence], session: ResearchSession) -> ResearchAnswer:
        """Generate structured answer from evidence."""
        # In production, this would use an LLM with RAG
        # Here we generate a structured synthesis
        
        if not evidence:
            return ResearchAnswer(
                answer_id=str(uuid.uuid4())[:8],
                question_id=question.question_id,
                answer="I could not find sufficient evidence to answer this question. Please try rephrasing or providing more context.",
                confidence=0.1,
                evidence=[],
                reasoning="No evidence retrieved from available sources.",
                limitations=["No relevant literature or knowledge graph connections found"],
                follow_up_questions=[
                    "Could you specify the gene/drug/disease of interest?",
                    "Would you like me to search for a broader topic?",
                ],
            )
        
        # Synthesize answer based on question type
        if question.question_type == "therapeutic":
            answer_text = self._synthesize_therapeutic_answer(question, evidence)
        elif question.question_type == "mechanistic":
            answer_text = self._synthesize_mechanistic_answer(question, evidence)
        elif question.question_type == "biomarker":
            answer_text = self._synthesize_biomarker_answer(question, evidence)
        elif question.question_type == "safety":
            answer_text = self._synthesize_safety_answer(question, evidence)
        else:
            answer_text = self._synthesize_general_answer(question, evidence)
        
        # Calculate confidence based on evidence quality
        avg_relevance = sum(e.relevance_score for e in evidence) / len(evidence)
        source_diversity = len(set(e.source for e in evidence))
        confidence = min(avg_relevance * 0.7 + source_diversity * 0.1, 0.95)
        
        # Extract reasoning
        reasoning = self._extract_reasoning(evidence)
        
        # Identify limitations
        limitations = self._identify_limitations(evidence, question)
        
        # Generate follow-up questions
        follow_ups = self._generate_follow_ups(question, evidence)
        
        return ResearchAnswer(
            answer_id=str(uuid.uuid4())[:8],
            question_id=question.question_id,
            answer=answer_text,
            confidence=confidence,
            evidence=evidence,
            reasoning=reasoning,
            limitations=limitations,
            follow_up_questions=follow_ups,
        )
    
    def _synthesize_therapeutic_answer(self, question: ResearchQuestion, evidence: list[Evidence]) -> str:
        parts = []
        parts.append(f"**Therapeutic Analysis for: {', '.join(question.entities) or 'the query'}**\n")
        
        # Group evidence by type
        kg_evidence = [e for e in evidence if e.source == "knowledge_graph"]
        pubmed_evidence = [e for e in evidence if e.source == "pubmed"]
        
        if kg_evidence:
            parts.append("**Knowledge Graph Findings:**")
            for e in kg_evidence[:5]:
                parts.append(f"• {e.content}")
            parts.append("")
        
        if pubmed_evidence:
            parts.append("**Literature Evidence:**")
            for e in pubmed_evidence[:5]:
                parts.append(f"• {e.citation}: {e.content[:200]}...")
            parts.append("")
        
        parts.append("*Note: This is an automated synthesis. Experimental validation required.*")
        
        return "\n".join(parts)
    
    def _synthesize_mechanistic_answer(self, question: ResearchQuestion, evidence: list[Evidence]) -> str:
        parts = []
        parts.append(f"**Mechanistic Analysis for: {', '.join(question.entities) or 'the query'}**\n")
        
        kg_evidence = [e for e in evidence if e.source == "knowledge_graph"]
        if kg_evidence:
            parts.append("**Pathway & Interaction Network:**")
            for e in kg_evidence[:8]:
                parts.append(f"• {e.content}")
            parts.append("")
        
        pubmed_evidence = [e for e in evidence if e.source == "pubmed"]
        if pubmed_evidence:
            parts.append("**Supporting Literature:**")
            for e in pubmed_evidence[:5]:
                parts.append(f"• {e.citation}: {e.content[:200]}...")
            parts.append("")
        
        parts.append("*Note: Computational pathway analysis. Wet-lab validation required.*")
        
        return "\n".join(parts)
    
    def _synthesize_biomarker_answer(self, question: ResearchQuestion, evidence: list[Evidence]) -> str:
        parts = []
        parts.append(f"**Biomarker Analysis for: {', '.join(question.entities) or 'the query'}**\n")
        
        pubmed_evidence = [e for e in evidence if e.source == "pubmed"]
        if pubmed_evidence:
            parts.append("**Biomarker Literature:**")
            for e in pubmed_evidence[:5]:
                parts.append(f"• {e.citation}: {e.content[:200]}...")
            parts.append("")
        
        parts.append("*Note: Biomarker candidates require clinical validation.*")
        
        return "\n".join(parts)
    
    def _synthesize_safety_answer(self, question: ResearchQuestion, evidence: list[Evidence]) -> str:
        parts = []
        parts.append(f"**Safety/Toxicity Analysis for: {', '.join(question.entities) or 'the query'}**\n")
        
        pubmed_evidence = [e for e in evidence if e.source == "pubmed"]
        if pubmed_evidence:
            parts.append("**Safety Literature:**")
            for e in pubmed_evidence[:5]:
                parts.append(f"• {e.citation}: {e.content[:200]}...")
            parts.append("")
        
        parts.append("*Note: Safety predictions are computational. Clinical data required.*")
        
        return "\n".join(parts)
    
    def _synthesize_general_answer(self, question: ResearchQuestion, evidence: list[Evidence]) -> str:
        parts = []
        parts.append(f"**Research Summary for: {question.question}**\n")
        
        for e in evidence[:10]:
            parts.append(f"• [{e.source.upper()}] {e.content[:300]}")
        
        parts.append("\n*Note: Automated synthesis from multiple sources.*")
        
        return "\n".join(parts)
    
    def _extract_reasoning(self, evidence: list[Evidence]) -> str:
        sources = set(e.source for e in evidence)
        return f"Answer synthesized from {len(evidence)} evidence items across {len(sources)} sources: {', '.join(sources)}."
    
    def _identify_limitations(self, evidence: list[Evidence], question: ResearchQuestion) -> list[str]:
        limitations = [
            "Automated analysis requires expert review",
            "Literature search limited to PubMed abstracts",
            "Knowledge graph coverage may be incomplete",
            "No experimental validation performed",
        ]
        
        if len(evidence) < 5:
            limitations.append("Limited evidence base - low confidence")
        
        if len(set(e.source for e in evidence)) == 1:
            limitations.append("Single evidence source - potential bias")
        
        return limitations
    
    def _generate_follow_ups(self, question: ResearchQuestion, evidence: list[Evidence]) -> list[str]:
        follow_ups = []
        
        if question.question_type == "therapeutic":
            follow_ups.extend([
                f"What are the ADMET properties of the top candidates for {', '.join(question.entities)}?",
                f"Are there ongoing clinical trials targeting {', '.join(question.entities)}?",
            ])
        elif question.question_type == "mechanistic":
            follow_ups.extend([
                f"What are the downstream effectors of {', '.join(question.entities)}?",
                f"Which pathways crosstalk with {', '.join(question.entities)}?",
            ])
        elif question.question_type == "biomarker":
            follow_ups.extend([
                f"What is the sensitivity/specificity of proposed biomarkers for {', '.join(question.entities)}?",
                f"Have these biomarkers been validated in independent cohorts?",
            ])
        
        follow_ups.append("Can you provide a detailed report with all citations?")
        
        return follow_ups[:5]
    
    def get_session(self, session_id: str) -> ResearchSession | None:
        return self.sessions.get(session_id)
    
    def export_session(self, session_id: str, format: str = "json") -> str:
        session = self.get_session(session_id)
        if not session:
            return ""
        
        if format == "json":
            return json.dumps(asdict(session), indent=2)
        elif format == "markdown":
            md = [f"# Research Session: {session.session_id}"]
            for q, a in zip(session.questions, session.answers):
                md.append(f"\n## Q: {q.question}")
                md.append(f"**Type:** {q.question_type}")
                md.append(f"\n## A: {a.answer}")
                md.append(f"\n**Confidence:** {a.confidence:.0%}")
                md.append(f"\n**Evidence ({len(a.evidence)} items):**")
                for e in a.evidence[:5]:
                    md.append(f"- [{e.source}] {e.citation}: {e.content[:100]}...")
                md.append(f"\n**Limitations:**")
                for lim in a.limitations:
                    md.append(f"- {lim}")
            return "\n".join(md)
        return ""


def create_research_assistant() -> AIResearchAssistant:
    """Factory function to create an AI Research Assistant."""
    return AIResearchAssistant()