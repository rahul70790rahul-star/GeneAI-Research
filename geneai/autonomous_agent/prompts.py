"""Prompt templates for Autonomous Bioinformatics Agent."""
from __future__ import annotations

from typing import Any


# System prompt for the autonomous agent
SYSTEM_PROMPT = """You are an expert Autonomous Bioinformatics Agent. Your role is to help researchers answer complex biological questions by:

1. Understanding the research question
2. Decomposing it into executable tasks
3. Selecting appropriate bioinformatics tools
4. Executing analyses
5. Interpreting results
6. Generating comprehensive summaries

You have access to tools for:
- Sequence analysis (DNA, RNA, protein)
- Variant analysis (VCF, functional annotation)
- Literature search (PubMed, Europe PMC)
- ADMET prediction for drug candidates
- Molecular docking and binding site prediction
- Pathway and GO enrichment analysis
- Protein-protein interaction networks
- Gene expression analysis

Always think step-by-step and explain your reasoning. When you need to use a tool, clearly state which tool and why."""


# Planning prompt
PLANNING_PROMPT = """Given the research question below, create a detailed task plan.

Research Question: {question}

Available Tool Categories:
- sequence: Sequence analysis, alignment
- variant: Variant annotation, filtering
- literature: PubMed, gene/disease literature search
- admet: ADMET property prediction
- docking: Molecular docking, binding site prediction
- analysis: Pathway enrichment, GO, PPI, expression analysis

Create a task plan with:
1. Task name and description
2. Tool to use
3. Parameters needed
4. Dependencies between tasks
5. Whether approval is required (for docking, ADMET, experimental design)

Output as JSON with tasks array."""


# Tool selection prompt
TOOL_SELECTION_PROMPT = """Select the best tool for the following task:

Task: {task_description}
Available Tools: {available_tools}

Consider:
- Tool category match
- Required parameters availability
- Tool capabilities
- Whether approval is needed

Return the tool name and parameter mapping."""


# Result interpretation prompt
INTERPRETATION_PROMPT = """Interpret the following tool results in the context of the research question.

Research Question: {question}
Task: {task_name}
Tool: {tool_name}
Results: {results}

Provide:
1. Key findings
2. Biological significance
3. Limitations
4. Next steps or follow-up analyses needed"""


# Summary generation prompt
SUMMARY_PROMPT = """Generate a comprehensive research summary.

Research Question: {question}
Task Plan: {task_plan}
Task Results: {task_results}

Structure:
1. Executive Summary
2. Methodology
3. Key Findings
4. Biological Interpretation
5. Limitations
6. Recommendations
7. References (from literature searches)"""


# Error recovery prompt
ERROR_RECOVERY_PROMPT = """A tool execution failed. Suggest recovery strategy.

Tool: {tool_name}
Error: {error}
Attempt: {attempt}/{max_attempts}
Parameters: {parameters}

Suggest:
1. Parameter adjustments
2. Alternative tools
3. Whether to retry or skip"""


# Approval request prompt
APPROVAL_PROMPT = """The following action requires human approval:

Task: {task_name}
Tool: {tool_name}
Description: {description}
Parameters: {parameters}
Risk Level: {risk_level}

Please review and approve or reject."""


# Few-shot examples for planning
PLANNING_EXAMPLES = [
    {
        "question": "I have a VCF file with mutations from a cancer patient. What drugs could target these mutations?",
        "tasks": [
            {"name": "Parse VCF and annotate variants", "tool": "variant_analysis", "depends_on": []},
            {"name": "Identify affected genes", "tool": "gene_identification", "depends_on": ["Parse VCF"]},
            {"name": "Find disease associations", "tool": "disease_analysis", "depends_on": ["Identify genes"]},
            {"name": "Search literature for mutations", "tool": "literature_search", "depends_on": ["Identify genes"]},
            {"name": "Drug repurposing for targets", "tool": "drug_repurposing", "depends_on": ["Disease associations"]},
            {"name": "ADMET prediction for candidates", "tool": "admet_prediction", "depends_on": ["Drug repurposing"], "requires_approval": True},
            {"name": "Generate report", "tool": "report_generation", "depends_on": ["ADMET prediction"]},
        ]
    },
    {
        "question": "Design a new inhibitor for EGFR kinase domain",
        "tasks": [
            {"name": "Analyze EGFR structure", "tool": "protein_analysis", "depends_on": []},
            {"name": "Predict binding site", "tool": "binding_site_prediction", "depends_on": ["Analyze EGFR"]},
            {"name": "Generate molecule candidates", "tool": "molecule_generation", "depends_on": ["Binding site"], "requires_approval": True},
            {"name": "Filter by drug-likeness", "tool": "drug_likeness_filter", "depends_on": ["Generate molecules"]},
            {"name": "ADMET prediction", "tool": "admet_prediction", "depends_on": ["Filter molecules"], "requires_approval": True},
            {"name": "Molecular docking", "tool": "molecular_docking", "depends_on": ["ADMET prediction"], "requires_approval": True},
            {"name": "Lead optimization", "tool": "lead_optimization", "depends_on": ["Docking"], "requires_approval": True},
            {"name": "Generate report", "tool": "report_generation", "depends_on": ["Lead optimization"]},
        ]
    },
    {
        "question": "Find biomarkers for early detection of pancreatic cancer from RNA-seq data",
        "tasks": [
            {"name": "Load expression data", "tool": "load_expression_data", "depends_on": []},
            {"name": "Differential expression analysis", "tool": "differential_expression", "depends_on": ["Load data"]},
            {"name": "Pathway enrichment", "tool": "pathway_analysis", "depends_on": ["Differential expression"]},
            {"name": "Biomarker candidate ranking", "tool": "biomarker_ranking", "depends_on": ["Pathway enrichment"]},
            {"name": "Validate with literature", "tool": "literature_search", "depends_on": ["Biomarker ranking"]},
            {"name": "Generate report", "tool": "report_generation", "depends_on": ["Literature validation"]},
        ]
    },
]


def get_system_prompt() -> str:
    """Get the system prompt."""
    return SYSTEM_PROMPT


def get_planning_prompt(question: str) -> str:
    """Get the planning prompt with examples."""
    examples_str = "\n\n".join([
        f"Example {i+1}:\nQuestion: {ex['question']}\nTasks: {ex['tasks']}"
        for i, ex in enumerate(PLANNING_EXAMPLES)
    ])
    return PLANNING_PROMPT.format(question=question) + "\n\nExamples:\n" + examples_str


def get_tool_selection_prompt(task_description: str, available_tools: list[str]) -> str:
    """Get the tool selection prompt."""
    return TOOL_SELECTION_PROMPT.format(
        task_description=task_description,
        available_tools=", ".join(available_tools),
    )


def get_interpretation_prompt(
    question: str,
    task_name: str,
    tool_name: str,
    results: dict[str, Any],
) -> str:
    """Get the result interpretation prompt."""
    return INTERPRETATION_PROMPT.format(
        question=question,
        task_name=task_name,
        tool_name=tool_name,
        results=results,
    )


def get_summary_prompt(
    question: str,
    task_plan: dict[str, Any],
    task_results: list[dict[str, Any]],
) -> str:
    """Get the summary generation prompt."""
    return SUMMARY_PROMPT.format(
        question=question,
        task_plan=task_plan,
        task_results=task_results,
    )


def get_error_recovery_prompt(
    tool_name: str,
    error: str,
    attempt: int,
    max_attempts: int,
    parameters: dict[str, Any],
) -> str:
    """Get the error recovery prompt."""
    return ERROR_RECOVERY_PROMPT.format(
        tool_name=tool_name,
        error=error,
        attempt=attempt,
        max_attempts=max_attempts,
        parameters=parameters,
    )


def get_approval_prompt(
    task_name: str,
    tool_name: str,
    description: str,
    parameters: dict[str, Any],
    risk_level: str = "medium",
) -> str:
    """Get the approval request prompt."""
    return APPROVAL_PROMPT.format(
        task_name=task_name,
        tool_name=tool_name,
        description=description,
        parameters=parameters,
        risk_level=risk_level,
    )