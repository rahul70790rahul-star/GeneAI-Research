"""AI Biotechnology Research Assistant - Phase 5.1 Core Module."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import requests

from geneai.config import APP_NAME

logger = logging.getLogger(__name__)


class QuestionType(Enum):
    """Classification of biological questions."""
    FACTUAL = "factual"
    ANALYTICAL = "analytical"
    HYPOTHETICAL = "hypothetical"
    COMPARATIVE = "comparative"
    METHODOLOGICAL = "methodological"
    GENE_ANALYSIS = "gene_analysis"
    PROTEIN_ANALYSIS = "protein_analysis"
    MUTATION_EXPLANATION = "mutation_explanation"
    DISEASE_RESEARCH = "disease_research"
    DRUG_RESEARCH = "drug_research"
    PATHWAY_EXPLANATION = "pathway_explanation"
    LITERATURE_SUMMARY = "literature_summary"
    REPORT_ASSISTANCE = "report_assistance"
    GENERAL = "general"


class EvidenceGrade(Enum):
    """Evidence grading for answers."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    EXPERIMENTAL = "experimental"       # Direct experimental evidence
    CLINICAL_TRIAL = "clinical_trial"   # Clinical trial data
    DATABASE_CURATED = "database_curated"  # Expert-curated databases
    COMPUTATIONAL_PREDICTION = "computational_prediction"  # ML/model predictions
    LITERATURE_DERIVED = "literature_derived"  # From publications
    INFERENCE = "inference"             # Logical inference from multiple sources
    SPECULATIVE = "speculative"         # Hypothesis/speculation


@dataclass
class ToolCall:
    """Represents a tool invocation."""
    tool_name: str
    parameters: dict[str, Any]
    result: Any = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Citation:
    """Scientific citation with metadata."""
    identifier: str = ""
    source: str = ""
    source_type: str = ""
    title: str = ""
    authors: Any = field(default_factory=list)
    year: int | None = None
    url: str = ""
    journal: str = ""
    volume: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    evidence_grade: Any = None
    relevance: float = 1.0
    snippet: str = ""
    tool_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.source and self.source_type:
            self.source = str(self.source_type)
        elif not self.source_type and self.source:
            self.source_type = self.source
        if self.evidence_grade is None:
            self.evidence_grade = EvidenceGrade.LITERATURE_DERIVED

    def _authors_str(self) -> str:
        if isinstance(self.authors, list):
            return ", ".join(str(a) for a in self.authors)
        return str(self.authors or "")

    def format_apa(self) -> str:
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
        label = self.title or self.identifier
        url = self.url or (f"https://doi.org/{self.doi}" if self.doi else "#")
        return f"[{label}]({url})"

    def get_evidence_badge(self) -> str:
        return "📖 Citation"


@dataclass
class Answer:
    """Structured answer with evidence."""
    question: str = ""
    question_type: QuestionType = QuestionType.GENERAL
    answer_text: str = ""
    confidence: float = 1.0
    citations: list[Citation] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    text: str = ""

    def __post_init__(self):
        if not self.answer_text and self.text:
            self.answer_text = self.text
        elif not self.text and self.answer_text:
            self.text = self.answer_text


@dataclass
class ConversationTurn:
    """Single turn in conversation."""
    user_question: str = ""
    assistant_answer: Any = None
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str = ""
    answer: Any = None
    tool_calls: list[Any] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.user_question and self.question:
            self.user_question = self.question
        elif not self.question and self.user_question:
            self.question = self.user_question

        if self.assistant_answer is None and self.answer is not None:
            self.assistant_answer = self.answer
        elif self.answer is None and self.assistant_answer is not None:
            self.answer = self.assistant_answer


class ConversationMemory:
    """Manages conversation history and context."""
    
    def __init__(self, max_turns: int = 20):
        self.turns: list[ConversationTurn] = []
        self.max_turns = max_turns
        self.context: dict[str, Any] = {}  # Persistent context (genes, diseases, etc.)
    
    def add_turn(self, turn_or_q: ConversationTurn | str, answer: Any = None, tool_calls: Any = None) -> None:
        if isinstance(turn_or_q, ConversationTurn):
            self.turns.append(turn_or_q)
        else:
            t = ConversationTurn(
                user_question=str(turn_or_q),
                assistant_answer=answer,
                tool_calls=tool_calls or [],
            )
            self.turns.append(t)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
    
    def get_recent_context(self, n: int = 5) -> list[ConversationTurn]:
        return self.turns[-n:] if self.turns else []
    
    def get_context_summary(self) -> str:
        """Generate a summary of conversation context for LLM."""
        if not self.turns:
            return "No previous conversation."
        
        summary_parts = ["Conversation context:"]
        for turn in self.turns[-5:]:
            q = getattr(turn, "user_question", "") or getattr(turn, "question", "")
            ans = getattr(turn, "assistant_answer", None) or getattr(turn, "answer", None)
            ans_text = getattr(ans, "answer_text", "") or getattr(ans, "text", "") or str(ans or "")
            summary_parts.append(f"Q: {q[:100]}")
            summary_parts.append(f"A: {ans_text[:150]}...")
        
        if self.context:
            summary_parts.append(f"Persistent context: {json.dumps(self.context, default=str)}")
        
        return "\n".join(summary_parts)
    
    def update_context(self, key: str, value: Any) -> None:
        self.context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)
    
    def clear(self) -> None:
        self.turns.clear()
        self.context.clear()


class BiotechAssistant:
    """Main AI Biotechnology Research Assistant."""
    
    def __init__(self):
        self.memory = ConversationMemory()
        self.tools: dict[str, Callable] = {}
        self._register_tools()
        self.session_id = str(uuid.uuid4())[:8]
    
    def _register_tools(self) -> None:
        """Register all available tools from existing GeneAI modules."""
        # Sequence Analysis
        from geneai.sequence import analyze_sequence, parse_sequence_file
        self.tools["analyze_sequence"] = analyze_sequence
        self.tools["parse_sequence_file"] = parse_sequence_file
        
        # VCF Analysis
        from geneai.variants import parse_vcf, summarize_vcf_stream
        self.tools["parse_vcf"] = parse_vcf
        self.tools["summarize_vcf_stream"] = summarize_vcf_stream
        
        # Mutation Interpretation
        from geneai.mutation import summarize_vcf_interpretation_stream
        self.tools["summarize_vcf_interpretation_stream"] = summarize_vcf_interpretation_stream
        
        # Gene Analysis
        from geneai.drug_discovery.gene_identification import identify_disease_genes
        from geneai.drug_discovery.mutation_target_mapping import map_mutations_to_targets
        self.tools["identify_disease_genes"] = identify_disease_genes
        self.tools["map_mutations_to_targets"] = map_mutations_to_targets
        
        # Protein Analysis
        from geneai.drug_discovery.protein_structure import analyze_protein_sequence
        from geneai.drug_discovery.protein_api import search_uniprot_protein, fetch_rcsb_entry_metadata
        self.tools["analyze_protein_sequence"] = analyze_protein_sequence
        self.tools["search_uniprot_protein"] = search_uniprot_protein
        self.tools["fetch_rcsb_entry_metadata"] = fetch_rcsb_entry_metadata
        
        # Disease Analysis
        from geneai.disease_gene_pathway import run_disease_gene_pathway_analysis, run_vcf_analysis
        self.tools["run_disease_gene_pathway_analysis"] = run_disease_gene_pathway_analysis
        self.tools["run_vcf_analysis"] = run_vcf_analysis
        
        # Drug Discovery
        from geneai.drug_discovery.drug_search import (
            search_drugs_by_name, search_drugs_by_target, search_drugs_by_disease,
            get_drug_details, search_drugs_comprehensive
        )
        self.tools["search_drugs_by_name"] = search_drugs_by_name
        self.tools["search_drugs_by_target"] = search_drugs_by_target
        self.tools["search_drugs_by_disease"] = search_drugs_by_disease
        self.tools["get_drug_details"] = get_drug_details
        self.tools["search_drugs_comprehensive"] = search_drugs_comprehensive
        
        # Drug-Target Prediction
        from geneai.drug_target_prediction import predict_drug_target_interactions
        from geneai.drug_target_prediction.molecular_descriptors import calculate_molecular_descriptors
        self.tools["predict_drug_target_interactions"] = predict_drug_target_interactions
        self.tools["calculate_molecular_descriptors"] = calculate_molecular_descriptors
        
        # Drug Repurposing
        from geneai.drug_repurposing import find_repurposing_candidates
        from geneai.drug_repurposing.repurposing_engine import create_repurposing_engine
        self.tools["find_repurposing_candidates"] = find_repurposing_candidates
        self.tools["create_repurposing_engine"] = create_repurposing_engine
        
        # ADMET Prediction
        from geneai.admet_prediction import predict_admet, calculate_overall_admet_score
        from geneai.admet_prediction.molecular_properties import calculate_molecular_properties, assess_drug_likeness
        self.tools["predict_admet"] = predict_admet
        self.tools["calculate_overall_admet_score"] = calculate_overall_admet_score
        self.tools["calculate_molecular_properties"] = calculate_molecular_properties
        self.tools["assess_drug_likeness"] = assess_drug_likeness
        
        # Biomarker Discovery
        from geneai.biomarker_discovery import run_biomarker_discovery
        self.tools["run_biomarker_discovery"] = run_biomarker_discovery
        
        # Drug Safety
        from geneai.drug_safety import build_safety_profile, predict_drug_safety
        self.tools["build_safety_profile"] = build_safety_profile
        self.tools["predict_drug_safety"] = predict_drug_safety
        
        # Literature Search
        from geneai.research import search_pubmed
        from geneai.research_analysis import analyze_research_papers, search_all_sources
        self.tools["search_pubmed"] = search_pubmed
        self.tools["analyze_research_papers"] = analyze_research_papers
        self.tools["search_all_sources"] = search_all_sources
        
        # Knowledge Graph
        from geneai.ai_research_intelligence.knowledge_graph import find_nodes, get_neighbors, shortest_path
        self.tools["find_kg_nodes"] = find_nodes
        self.tools["get_kg_neighbors"] = get_neighbors
        self.tools["find_kg_path"] = shortest_path
        
        # Mutation-to-Drug Workflow
        from geneai.ai_research_intelligence.mutation_to_drug_workflow import run_mutation_to_drug_workflow
        self.tools["run_mutation_to_drug_workflow"] = run_mutation_to_drug_workflow
        
        # Integrated Precision
        from geneai.integrated_precision import run_integrated_precision_drug_discovery
        self.tools["run_integrated_precision_drug_discovery"] = run_integrated_precision_drug_discovery
        
        logger.info(f"Registered {len(self.tools)} tools")
    
    def classify_question(self, question: str) -> QuestionType:
        """Classify the type of biological question."""
        question_lower = question.lower()
        
        # Check for specific patterns
        if any(kw in question_lower for kw in ["mutation", "variant", "vcf", "snp", "indel", "genomic change"]):
            return QuestionType.MUTATION_EXPLANATION
        elif any(kw in question_lower for kw in ["gene", "genes", "genomic", "expression", "transcript"]):
            return QuestionType.GENE_ANALYSIS
        elif any(kw in question_lower for kw in ["protein", "structure", "folding", "domain", "pdb", "uniprot"]):
            return QuestionType.PROTEIN_ANALYSIS
        elif any(kw in question_lower for kw in ["disease", "disorder", "condition", "phenotype", "patient"]):
            return QuestionType.DISEASE_RESEARCH
        elif any(kw in question_lower for kw in ["drug", "compound", "medication", "therapeutic", "molecule", "smiles"]):
            return QuestionType.DRUG_RESEARCH
        elif any(kw in question_lower for kw in ["pathway", "signaling", "metabolic", "network", "interaction"]):
            return QuestionType.PATHWAY_EXPLANATION
        elif any(kw in question_lower for kw in ["paper", "publication", "literature", "pubmed", "review", "summarize"]):
            return QuestionType.LITERATURE_SUMMARY
        elif any(kw in question_lower for kw in ["report", "document", "write", "generate report"]):
            return QuestionType.REPORT_ASSISTANCE
        else:
            return QuestionType.GENERAL
    
    def _extract_entities(self, question: str) -> dict[str, list[str]]:
        """Extract biological entities from question (simple keyword-based)."""
        entities = {
            "genes": [],
            "proteins": [],
            "diseases": [],
            "drugs": [],
            "mutations": [],
        }
        
        # Common gene symbols (uppercase)
        words = question.split()
        for word in words:
            clean = word.strip(".,;:()[]{}").upper()
            if len(clean) >= 2 and clean.isalnum():
                # Could be gene symbol
                if clean in ["TP53", "EGFR", "BRCA1", "BRCA2", "KRAS", "PIK3CA", "PTEN", "MYC", "ALK", "ROS1",
                           "BRAF", "NRAS", "HRAS", "MET", "RET", "NTRK1", "NTRK2", "NTRK3", "CDK4", "CDK6",
                           "ERBB2", "HER2", "ESR1", "AR", "PD1", "PDL1", "CTLA4", "VEGF", "EGFR"]:
                    entities["genes"].append(clean)
        
        return entities
    
    def _select_tools(self, question_type: QuestionType, entities: dict) -> list[str]:
        """Select relevant tools based on question type and entities."""
        tool_map = {
            QuestionType.GENE_ANALYSIS: [
                "identify_disease_genes", "search_uniprot_protein", 
                "run_disease_gene_pathway_analysis", "find_kg_nodes"
            ],
            QuestionType.PROTEIN_ANALYSIS: [
                "analyze_protein_sequence", "search_uniprot_protein",
                "fetch_rcsb_entry_metadata", "find_kg_neighbors"
            ],
            QuestionType.MUTATION_EXPLANATION: [
                "parse_vcf", "summarize_vcf_interpretation_stream",
                "map_mutations_to_targets", "run_vcf_analysis"
            ],
            QuestionType.DISEASE_RESEARCH: [
                "run_disease_gene_pathway_analysis", "run_vcf_analysis",
                "search_drugs_by_disease", "find_repurposing_candidates"
            ],
            QuestionType.DRUG_RESEARCH: [
                "search_drugs_by_name", "search_drugs_by_target",
                "get_drug_details", "search_drugs_comprehensive",
                "predict_drug_target_interactions", "predict_admet",
                "build_safety_profile", "calculate_molecular_properties"
            ],
            QuestionType.PATHWAY_EXPLANATION: [
                "run_disease_gene_pathway_analysis", "find_kg_nodes",
                "get_kg_neighbors", "find_kg_path"
            ],
            QuestionType.LITERATURE_SUMMARY: [
                "search_pubmed", "search_all_sources", "analyze_research_papers"
            ],
            QuestionType.REPORT_ASSISTANCE: [
                "run_integrated_precision_drug_discovery",
                "run_mutation_to_drug_workflow"
            ],
            QuestionType.GENERAL: [
                "search_pubmed", "find_kg_nodes"
            ],
        }
        
        base_tools = tool_map.get(question_type, tool_map[QuestionType.GENERAL])
        
        # Add entity-specific tools
        if entities.get("genes"):
            base_tools.extend(["search_uniprot_protein", "find_kg_nodes"])
        if entities.get("drugs"):
            base_tools.extend(["search_drugs_by_name", "get_drug_details"])
        
        return list(dict.fromkeys(base_tools))  # Deduplicate preserving order
    
    def _execute_tool(self, tool_name: str, params: dict) -> ToolCall:
        """Execute a tool and return ToolCall with result or error."""
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolCall(tool_name=tool_name, parameters=params, error=f"Tool not found: {tool_name}")
        
        try:
            result = tool(**params)
            return ToolCall(tool_name=tool_name, parameters=params, result=result)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolCall(tool_name=tool_name, parameters=params, error=str(e))
    
    def _tool_calls_to_citations(self, tool_calls: list[ToolCall]) -> list[Citation]:
        """Convert tool calls to citations."""
        citations = []
        for call in tool_calls:
            if call.error:
                continue
            
            # Map tool to citation
            if call.tool_name == "search_pubmed" and call.result:
                for paper in call.result[:3]:
                    citations.append(Citation(
                        source_type="pubmed",
                        identifier=f"PMID:{paper.get('pmid', 'unknown')}",
                        title=paper.get("title", ""),
                        authors=paper.get("authors", ""),
                        year=paper.get("year"),
                        url=paper.get("url", ""),
                        evidence_grade=EvidenceGrade.LITERATURE_DERIVED,
                    ))
            elif call.tool_name in ["run_disease_gene_pathway_analysis", "identify_disease_genes"]:
                citations.append(Citation(
                    source_type="database",
                    identifier="OpenTargets",
                    title="Open Targets Platform - Disease-Gene Associations",
                    url="https://platform.opentargets.org/",
                    evidence_grade=EvidenceGrade.DATABASE_CURATED,
                ))
            elif call.tool_name in ["predict_admet", "build_safety_profile"]:
                citations.append(Citation(
                    source_type="computation",
                    identifier=call.tool_name,
                    title=f"{call.tool_name.replace('_', ' ').title()} Prediction",
                    evidence_grade=EvidenceGrade.COMPUTATIONAL_PREDICTION,
                ))
            elif call.tool_name in ["search_uniprot_protein", "fetch_rcsb_entry_metadata"]:
                citations.append(Citation(
                    source_type="database",
                    identifier="UniProt/RCSB PDB",
                    title="UniProt Knowledgebase / RCSB Protein Data Bank",
                    url="https://www.uniprot.org/",
                    evidence_grade=EvidenceGrade.DATABASE_CURATED,
                ))
        
        return citations
    
    def _generate_answer(
        self, 
        question: str, 
        question_type: QuestionType,
        tool_calls: list[ToolCall],
        citations: list[Citation],
        entities: dict
    ) -> Answer:
        """Generate structured answer from tool results."""
        
        # Build answer based on tool results
        successful_calls = [c for c in tool_calls if not c.error]
        failed_calls = [c for c in tool_calls if c.error]
        
        if not successful_calls:
            answer_text = "I couldn't retrieve relevant information for your question. "
            if failed_calls:
                answer_text += f"Tools attempted: {', '.join(c.tool_name for c in failed_calls)}. "
            answer_text += "Please try rephrasing or providing more specific details."
            confidence = 0.1
        else:
            # Synthesize answer from tool results
            answer_parts = []
            
            for call in successful_calls:
                if call.tool_name == "search_pubmed" and call.result:
                    answer_parts.append(f"Found {len(call.result)} relevant publications.")
                elif call.tool_name == "run_disease_gene_pathway_analysis" and call.result:
                    result = call.result
                    if hasattr(result, 'therapeutic_targets') and result.therapeutic_targets:
                        answer_parts.append(f"Identified {len(result.therapeutic_targets)} therapeutic targets.")
                elif call.tool_name == "predict_admet" and call.result:
                    answer_parts.append("Generated ADMET prediction with risk assessment.")
                elif call.tool_name == "search_drugs_by_target" and call.result:
                    answer_parts.append(f"Found {len(call.result)} drugs targeting the specified protein.")
                elif call.tool_name == "analyze_protein_sequence" and call.result:
                    answer_parts.append("Completed protein sequence analysis with biophysical properties.")
                else:
                    answer_parts.append(f"Completed {call.tool_name.replace('_', ' ')}.")
            
            answer_text = " ".join(answer_parts)
            
            # Add specific details from results
            if successful_calls:
                first_result = successful_calls[0].result
                if first_result and isinstance(first_result, dict):
                    # Add key findings
                    pass
            
            confidence = min(0.9, 0.5 + 0.1 * len(successful_calls))
        
        # Generate follow-up questions
        follow_ups = []
        if question_type == QuestionType.GENE_ANALYSIS:
            follow_ups.extend([
                "What drugs target this gene?",
                "What diseases are associated with this gene?",
                "Show me the protein structure for this gene."
            ])
        elif question_type == QuestionType.DRUG_RESEARCH:
            follow_ups.extend([
                "What are the ADMET properties of this drug?",
                "What are the known drug-target interactions?",
                "Are there repurposing opportunities for this drug?"
            ])
        elif question_type == QuestionType.MUTATION_EXPLANATION:
            follow_ups.extend([
                "What is the clinical significance of this mutation?",
                "What drugs might target this mutation?",
                "Show me the disease associations."
            ])
        elif question_type == QuestionType.DISEASE_RESEARCH:
            follow_ups.extend([
                "What are the therapeutic targets for this disease?",
                "What drugs are in clinical trials for this disease?",
                "Show me the pathway analysis."
            ])
        
        # Limitations
        limitations = [
            "This analysis is for research purposes only and not clinical advice.",
            "Computational predictions require experimental validation.",
            "Database information may not reflect the latest research."
        ]
        if failed_calls:
            limitations.append(f"Some tools failed: {', '.join(c.tool_name for c in failed_calls)}")
        
        return Answer(
            question=question,
            question_type=question_type,
            answer_text=answer_text,
            confidence=confidence,
            citations=citations,
            tool_calls=tool_calls,
            follow_up_questions=follow_ups[:3],
            limitations=limitations,
            session_id=self.session_id,
        )
    
    def ask(self, question: str) -> Answer:
        """Ask a question to the assistant."""
        if not question.strip():
            return Answer(
                question=question,
                question_type=QuestionType.GENERAL,
                answer_text="Please provide a question.",
                confidence=0.0,
                session_id=self.session_id,
            )
        
        # Classify question
        question_type = self.classify_question(question)
        entities = self._extract_entities(question)
        tools_to_use = self._select_tools(question_type, entities)
        
        # Execute tools
        tool_calls = []
        for tool_name in tools_to_use[:5]:  # Limit to 5 tools
            # Build parameters based on tool and entities
            params = self._build_tool_params(tool_name, question, entities)
            if params is not None:
                call = self._execute_tool(tool_name, params)
                tool_calls.append(call)
        
        # Generate citations
        citations = self._tool_calls_to_citations(tool_calls)
        
        # Generate answer
        answer = self._generate_answer(question, question_type, tool_calls, citations, entities)
        
        # Store in memory
        turn = ConversationTurn(user_question=question, assistant_answer=answer)
        self.memory.add_turn(turn)
        
        # Update context with entities
        for key, value in entities.items():
            if value:
                self.memory.update_context(key, value)
        
        return answer
    
    def _build_tool_params(self, tool_name: str, question: str, entities: dict) -> dict | None:
        """Build parameters for a tool based on question and entities."""
        # Simple parameter building - in production would use LLM
        params = {}
        
        if tool_name in ["search_drugs_by_name", "get_drug_details"]:
            if entities.get("drugs"):
                params["query"] = entities["drugs"][0]
            else:
                # Extract from question
                words = question.split()
                for i, w in enumerate(words):
                    if w.lower() in ["drug", "compound", "medication"] and i + 1 < len(words):
                        params["query"] = words[i + 1]
                        break
        
        elif tool_name in ["search_drugs_by_target", "search_uniprot_protein"]:
            if entities.get("genes"):
                params["target"] = entities["genes"][0]
                params["gene_symbols"] = entities["genes"]
            elif entities.get("proteins"):
                params["query"] = entities["proteins"][0]
        
        elif tool_name == "run_disease_gene_pathway_analysis":
            if entities.get("genes"):
                params["gene_symbols"] = entities["genes"]
            if entities.get("diseases"):
                params["disease_names"] = entities["diseases"]
        
        elif tool_name == "search_pubmed":
            params["query"] = question
            params["limit"] = 10
        
        elif tool_name == "predict_admet":
            # Need SMILES - would extract from context
            pass
        
        elif tool_name == "analyze_protein_sequence":
            if entities.get("proteins"):
                params["sequence"] = entities["proteins"][0]  # Would need actual sequence
        
        # Return params if not empty, else None to skip
        return params if params else None
    
    def get_conversation_history(self) -> list[ConversationTurn]:
        return self.memory.turns
    
    def clear_conversation(self) -> None:
        self.memory.clear()
        self.session_id = str(uuid.uuid4())[:8]
    
    def export_conversation(self, format: str = "json") -> str:
        """Export conversation history."""
        data = {
            "session_id": self.session_id,
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "question": t.user_question,
                    "answer": t.assistant_answer.answer_text,
                    "confidence": t.assistant_answer.confidence,
                    "question_type": t.assistant_answer.question_type.value,
                    "citations": [
                        {
                            "source": c.source_type,
                            "identifier": c.identifier,
                            "title": c.title,
                            "url": c.url,
                            "evidence_grade": c.evidence_grade.value,
                        } for c in t.assistant_answer.citations
                    ],
                    "timestamp": t.assistant_answer.timestamp,
                }
                for t in self.memory.turns
            ],
            "context": self.memory.context,
        }
        
        if format == "json":
            return json.dumps(data, indent=2)
        elif format == "markdown":
            md = [f"# Conversation Export - Session {self.session_id}\n"]
            for t in self.memory.turns:
                md.append(f"## Q: {t.user_question}")
                md.append(f"**Type:** {t.assistant_answer.question_type.value}")
                md.append(f"**Confidence:** {t.assistant_answer.confidence:.0%}")
                md.append(f"\n{t.assistant_answer.answer_text}\n")
                if t.assistant_answer.citations:
                    md.append("**Citations:**")
                    for c in t.assistant_answer.citations:
                        md.append(f"- [{c.source_type}] {c.identifier}: {c.title} ({c.url})")
                md.append("---\n")
            return "\n".join(md)
        return ""


# Factory function
def create_biotech_assistant() -> BiotechAssistant:
    """Create a new BiotechAssistant instance."""
    return BiotechAssistant()