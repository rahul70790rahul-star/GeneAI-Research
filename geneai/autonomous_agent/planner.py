"""Task planning module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from geneai.autonomous_agent.types import TaskType

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """A single task in a research plan."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    task_type: TaskType = TaskType.SEQUENCE_ANALYSIS
    tool_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # task_ids this depends on
    requires_approval: bool = False
    priority: int = 0  # Higher = more important
    estimated_duration_seconds: float = 60.0
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class TaskPlan:
    """A complete plan for answering a research question."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    question: str = ""
    tasks: list[Task] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: __import__('time').time())
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_ready_tasks(self, completed_task_ids: set[str]) -> list[Task]:
        """Get tasks whose dependencies are all satisfied."""
        ready = []
        for task in self.tasks:
            if task.task_id in completed_task_ids:
                continue
            if all(dep in completed_task_ids for dep in task.dependencies):
                ready.append(task)
        # Sort by priority (descending)
        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def topological_sort(self) -> list[Task]:
        """Return tasks in topological order."""
        # Kahn's algorithm
        in_degree = {task.task_id: len(task.dependencies) for task in self.tasks}
        task_map = {task.task_id: task for task in self.tasks}
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            tid = queue.pop(0)
            result.append(task_map[tid])
            for task in self.tasks:
                if tid in task.dependencies:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)

        if len(result) != len(self.tasks):
            logger.warning("Cycle detected in task dependencies, returning partial order")

        return result


class TaskPlanner:
    """
    Decompose research questions into executable task plans.

    Uses LLM-based planning with domain knowledge of bioinformatics workflows.
    """

    # Task templates for common research patterns
    TASK_TEMPLATES = {
        "mutation_to_drug": [
            ("Parse VCF/variant input", TaskType.VARIANT_ANALYSIS, "variant_analysis"),
            ("Identify affected genes", TaskType.GENE_IDENTIFICATION, "gene_identification"),
            ("Find disease associations", TaskType.DISEASE_ANALYSIS, "disease_analysis"),
            ("Search literature for mutations", TaskType.LITERATURE_SEARCH, "literature_search"),
            ("Predict ADMET for candidates", TaskType.ADMET_PREDICTION, "admet_prediction"),
            ("Drug repurposing search", TaskType.DRUG_REPURPOSING, "drug_repurposing"),
            ("Generate report", TaskType.REPORT_GENERATION, "report_generation"),
        ],
        "target_identification": [
            ("Analyze disease", TaskType.DISEASE_ANALYSIS, "disease_analysis"),
            ("Identify disease genes", TaskType.GENE_IDENTIFICATION, "gene_identification"),
            ("Analyze protein structures", TaskType.PROTEIN_ANALYSIS, "protein_analysis"),
            ("Assess druggability", TaskType.DRUG_OPTIMIZATION, "druggability_assessment"),
            ("Find known drugs", TaskType.DRUG_REPURPOSING, "drug_repurposing"),
            ("Molecular docking", TaskType.MOLECULAR_DOCKING, "molecular_docking"),
            ("Generate report", TaskType.REPORT_GENERATION, "report_generation"),
        ],
        "biomarker_discovery": [
            ("Load expression data", TaskType.SEQUENCE_ANALYSIS, "load_expression_data"),
            ("Differential expression", TaskType.SEQUENCE_ANALYSIS, "differential_expression"),
            ("Pathway enrichment", TaskType.PATHWAY_ANALYSIS, "pathway_analysis"),
            ("Biomarker candidate ranking", TaskType.BIOMARKER_DISCOVERY, "biomarker_ranking"),
            ("Validate with literature", TaskType.LITERATURE_SEARCH, "literature_search"),
            ("Generate report", TaskType.REPORT_GENERATION, "report_generation"),
        ],
        "drug_design": [
            ("Define target properties", TaskType.PROTEIN_ANALYSIS, "protein_analysis"),
            ("Generate molecule candidates", TaskType.DRUG_OPTIMIZATION, "molecule_generation"),
            ("Filter by drug-likeness", TaskType.DRUG_OPTIMIZATION, "drug_likeness_filter"),
            ("Predict ADMET", TaskType.ADMET_PREDICTION, "admet_prediction"),
            ("Molecular docking", TaskType.MOLECULAR_DOCKING, "molecular_docking"),
            ("Optimize leads", TaskType.DRUG_OPTIMIZATION, "lead_optimization"),
            ("Generate report", TaskType.REPORT_GENERATION, "report_generation"),
        ],
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def decompose(self, question: str) -> TaskPlan:
        """
        Decompose a research question into a task plan.

        Args:
            question: Natural language research question

        Returns:
            TaskPlan with ordered tasks
        """
        self.logger.info("Decomposing question: %s", question[:100])

        # Classify question type
        question_type = self._classify_question(question)

        # Get template
        template = self.TASK_TEMPLATES.get(question_type, self.TASK_TEMPLATES["mutation_to_drug"])

        # Create tasks from template
        tasks = []
        for i, (name, task_type, tool_name) in enumerate(template):
            task = Task(
                name=name,
                description=f"Execute {name} for research question",
                task_type=task_type,
                tool_name=tool_name,
                dependencies=[tasks[i-1].task_id] if i > 0 else [],
                requires_approval=self._requires_approval(tool_name),
                priority=10 - i,  # Earlier tasks higher priority
            )
            tasks.append(task)

        # Extract parameters from question
        self._extract_parameters(question, tasks)

        return TaskPlan(
            question=question,
            tasks=tasks,
            metadata={"question_type": question_type},
        )

    def _classify_question(self, question: str) -> str:
        """Classify the research question type."""
        question_lower = question.lower()

        if any(kw in question_lower for kw in ["mutation", "variant", "vcf", "snp", "genomic"]):
            if any(kw in question_lower for kw in ["drug", "treatment", "therapy", "compound"]):
                return "mutation_to_drug"
            return "variant_analysis"

        if any(kw in question_lower for kw in ["target", "protein", "binding", "druggability"]):
            return "target_identification"

        if any(kw in question_lower for kw in ["biomarker", "expression", "differential", "rna-seq", "omics"]):
            return "biomarker_discovery"

        if any(kw in question_lower for kw in ["design", "generate", "molecule", "compound", "optimize"]):
            return "drug_design"

        if any(kw in question_lower for kw in ["disease", "phenotype", "disorder", "condition"]):
            return "target_identification"

        # Default
        return "mutation_to_drug"

    def _requires_approval(self, tool_name: str | None) -> bool:
        """Check if a tool requires human approval."""
        approval_tools = {
            "molecular_docking",
            "drug_repurposing",
            "lead_optimization",
            "molecule_generation",
        }
        return tool_name in approval_tools

    def _extract_parameters(self, question: str, tasks: list[Task]) -> None:
        """Extract parameters from question for tasks."""
        # Simple keyword extraction - in production would use LLM
        import re

        # Extract gene symbols
        gene_pattern = r'\b([A-Z]{2,10}\d*)\b'
        genes = re.findall(gene_pattern, question)

        # Extract disease terms
        disease_keywords = ["cancer", "diabetes", "alzheimer", "parkinson", "covid", "rare disease"]
        diseases = [kw for kw in disease_keywords if kw in question.lower()]

        # Extract compound/SMILES
        smiles_pattern = r'[CNOC1=CC=CC=C1]'
        has_smiles = bool(re.search(smiles_pattern, question))

        # Apply to tasks
        for task in tasks:
            if task.tool_name in ("gene_identification", "disease_analysis") and genes:
                task.parameters["genes"] = genes
            if task.tool_name == "disease_analysis" and diseases:
                task.parameters["diseases"] = diseases
            if task.tool_name in ("admet_prediction", "molecular_docking") and has_smiles:
                # Would extract actual SMILES in production
                pass

    def create_custom_plan(
        self,
        question: str,
        task_specs: list[dict[str, Any]],
    ) -> TaskPlan:
        """Create a custom plan from specifications."""
        tasks = []
        for i, spec in enumerate(task_specs):
            task = Task(
                name=spec.get("name", f"Task {i+1}"),
                description=spec.get("description", ""),
                task_type=TaskType(spec.get("type", "sequence_analysis")),
                tool_name=spec.get("tool"),
                parameters=spec.get("parameters", {}),
                dependencies=spec.get("dependencies", []),
                requires_approval=spec.get("requires_approval", False),
                priority=spec.get("priority", 5),
                estimated_duration_seconds=spec.get("duration", 60),
                max_retries=spec.get("max_retries", 3),
            )
            tasks.append(task)

        return TaskPlan(question=question, tasks=tasks)