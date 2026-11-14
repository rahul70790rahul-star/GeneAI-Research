"""Prompts for Biotech Assistant - Phase 5.1."""
from __future__ import annotations

from string import Template
from typing import Any


class PromptTemplate(str):
    """String subclass that also supports Template.substitute."""
    def substitute(self, *args, **kwargs) -> str:
        return Template(str(self)).substitute(*args, **kwargs)

    def safe_substitute(self, *args, **kwargs) -> str:
        return Template(str(self)).safe_substitute(*args, **kwargs)


SYSTEM_PROMPT = """You are the GeneAI Biotechnology Research Assistant, an expert AI system specialized in genomics, 
proteomics, drug discovery, and biomedical research. You have access to a comprehensive suite of computational 
biology tools and databases.

Your capabilities include:
- Sequence analysis (DNA, RNA, protein)
- Variant interpretation (VCF, mutations)
- Gene-disease association analysis
- Protein structure and function analysis
- Drug discovery and repurposing
- ADMET prediction and drug safety assessment
- Biomarker discovery
- Literature search and analysis
- Knowledge graph traversal
- Integrated precision medicine workflows

Guidelines:
1. Always cite your sources using the provided citation system
2. Distinguish between experimental evidence, computational predictions, and database annotations
3. Acknowledge limitations of computational methods
4. Suggest experimental validation for predictions
5. Ask clarifying questions when needed
6. Provide actionable follow-up suggestions
7. Maintain scientific rigor and accuracy

When answering:
- Classify the question type first
- Select appropriate tools
- Execute tools and collect results
- Synthesize findings with proper citations
- State confidence level
- Note limitations
- Suggest follow-up questions"""


QUESTION_CLASSIFICATION_PROMPT = PromptTemplate("""Classify the following biological research question into one of these categories:
- GENE_ANALYSIS: Questions about genes, expression, genomics
- PROTEIN_ANALYSIS: Questions about proteins, structures, domains
- MUTATION_EXPLANATION: Questions about variants, mutations, VCF files
- DISEASE_RESEARCH: Questions about diseases, disorders, phenotypes
- DRUG_RESEARCH: Questions about drugs, compounds, therapeutics
- PATHWAY_EXPLANATION: Questions about pathways, signaling, networks
- LITERATURE_SUMMARY: Questions about papers, publications, reviews
- REPORT_ASSISTANCE: Questions about generating reports, documents
- GENERAL: Other biology questions

Question: $question

Return only the category name.""")

TOOL_SELECTION_PROMPT = PromptTemplate("""Given the question type and available tools, select the most relevant tools to answer this question.

Question: $question
Question Type: $question_type
Entities: $entities

Available Tools:
$tool_list

Return a JSON list of tool names (max 5) in order of relevance.""")

ANSWER_SYNTHESIS_PROMPT = PromptTemplate("""Synthesize a comprehensive answer from the tool results.

Question: $question
Question Type: $question_type
Tool Results: $tool_results
Citations: $citations
Conversation Context: $context

Generate:
1. A clear, concise answer addressing the question
2. Confidence level (0-1)
3. Key findings
4. Limitations
5. 3 follow-up questions

Format as JSON:
{
  "answer_text": "...",
  "confidence": 0.0-1.0,
  "key_findings": [...],
  "limitations": [...],
  "follow_up_questions": [...]
}""")

CITATION_FORMATTING_PROMPT = PromptTemplate("""Format the following citations in a standard scientific format.

Citations: $citations

Return formatted citations as a list of strings.""")

FOLLOW_UP_PROMPT = Template("""Based on the question and answer, suggest 3 relevant follow-up questions.

Question: $question
Answer: $answer
Question Type: $question_type

Return a JSON list of 3 follow-up questions.""")

CLARIFICATION_PROMPT = Template("""The question is ambiguous. Ask for clarification.

Question: $question
Possible interpretations: $interpretations

Return a polite clarification question.""")

ERROR_HANDLING_PROMPT = Template("""A tool failed during execution. Provide a helpful response.

Question: $question
Failed Tool: $tool_name
Error: $error

Return a response explaining the issue and suggesting alternatives.""")

REPORT_GENERATION_PROMPT = Template("""Generate a structured research report based on the conversation.

Session ID: $session_id
Turns: $turns
Topic: $topic

Generate a markdown report with:
1. Executive Summary
2. Methods (tools used)
3. Results (key findings with citations)
4. Discussion
5. Limitations
6. Recommendations
7. References""")

SUMMARIZATION_PROMPT = Template("""Summarize the following text for a scientific audience.

Text: $text
Max Length: $max_length words

Return a concise summary.""")


# Prompt templates for specific question types
GENE_ANALYSIS_PROMPT = """Focus on:
- Gene function and annotations
- Disease associations (OpenTargets, DisGeNET)
- Expression patterns
- Pathway membership
- Orthologs and paralogs
- Known mutations and variants"""

PROTEIN_ANALYSIS_PROMPT = """Focus on:
- Protein structure (PDB, AlphaFold)
- Domains and motifs
- Post-translational modifications
- Protein-protein interactions
- Subcellular localization
- Biophysical properties"""

MUTATION_EXPLANATION_PROMPT = """Focus on:
- Variant classification (ClinVar, ACMG)
- Functional impact predictions
- Population frequencies (gnomAD)
- Disease associations
- Drug targeting implications
- Pathogenicity evidence"""

DISEASE_RESEARCH_PROMPT = """Focus on:
- Genetic basis (GWAS, rare variants)
- Molecular pathways
- Therapeutic targets
- Clinical trials landscape
- Biomarkers
- Animal models"""

DRUG_RESEARCH_PROMPT = """Focus on:
- Mechanism of action
- Target profile
- ADMET properties
- Safety profile
- Clinical status
- Repurposing potential
- Structure-activity relationships"""

PATHWAY_EXPLANATION_PROMPT = """Focus on:
- Pathway components and topology
- Key regulatory nodes
- Disease perturbations
- Drug targets in pathway
- Crosstalk with other pathways
- Experimental evidence"""

LITERATURE_SUMMARY_PROMPT = """Focus on:
- Key findings and conclusions
- Study designs and sample sizes
- Statistical significance
- Reproducibility
- Consensus vs. controversy
- Recent advances"""


def get_question_type_prompt(question_type: Any) -> str:
    """Get specialized prompt for question type."""
    val = getattr(question_type, "value", str(question_type)).upper()
    prompts = {
        "GENE_ANALYSIS": GENE_ANALYSIS_PROMPT,
        "PROTEIN_ANALYSIS": PROTEIN_ANALYSIS_PROMPT,
        "MUTATION_EXPLANATION": MUTATION_EXPLANATION_PROMPT,
        "DISEASE_RESEARCH": DISEASE_RESEARCH_PROMPT,
        "DRUG_RESEARCH": DRUG_RESEARCH_PROMPT,
        "PATHWAY_EXPLANATION": PATHWAY_EXPLANATION_PROMPT,
        "LITERATURE_SUMMARY": LITERATURE_SUMMARY_PROMPT,
        "FACTUAL": "Focus on factual, verified biological data and citations.",
        "ANALYTICAL": "Focus on comparative and in-depth mechanism analysis with statistical backing.",
        "HYPOTHETICAL": "Focus on biological plausibility, testable hypotheses, and validation experiments.",
        "COMPARATIVE": "Compare sequences, targets, pathways, or efficacy profiles side by side.",
        "METHODOLOGICAL": "Focus on experimental protocols, computational pipelines, and best practices.",
    }
    return prompts.get(val, GENE_ANALYSIS_PROMPT)


# Backward-compatibility alias for the classification prompt
QUESTION_ANALYSIS_PROMPT = QUESTION_CLASSIFICATION_PROMPT


# Backward-compatibility alias for citation formatting prompt
CITATION_FORMAT_PROMPT = CITATION_FORMATTING_PROMPT


# Backward-compatibility alias
get_prompt_for_question_type = get_question_type_prompt


def format_tool_list(tools: list[dict[str, str]]) -> str:
    """Format tool list for prompt."""
    lines = []
    for tool in tools:
        lines.append(f"- {tool['name']}: {tool['description']}")
    return "\n".join(lines)