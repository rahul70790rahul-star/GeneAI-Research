"""Agent orchestrator for coordinating multi-agent workflows - Phase 5.2."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from geneai.multi_agent.core import BaseAgent, MessageBus, AgentMessage, MessageType, get_message_bus
from geneai.multi_agent.agents import create_all_agents, register_all_agents

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Status of a workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    step_id: str
    agent_type: str
    action: str
    parameters: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)  # step_ids this depends on
    name: str = ""  # Derived from agent_type and action if not provided
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    
    def __post_init__(self):
        if not self.name:
            object.__setattr__(self, 'name', f"{self.agent_type}.{self.action}")
    
    # Aliases for backward compatibility
    @property
    def agent_id(self) -> str:
        return self.agent_type
    
    @property
    def task(self) -> dict[str, Any]:
        task = self.parameters.copy()
        task["type"] = self.action
        return task


@dataclass
class Workflow:
    """A multi-agent workflow definition."""
    workflow_id: str
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.workflow_id)
    
    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)
    
    def get_step(self, step_id: str) -> WorkflowStep | None:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def get_ready_steps(self) -> list[WorkflowStep]:
        """Get steps that are ready to execute (dependencies met)."""
        ready = []
        for step in self.steps:
            if step.status != WorkflowStatus.PENDING:
                continue
            # Check if all dependencies are completed
            deps_met = all(
                self.get_step(dep_id) and self.get_step(dep_id).status == WorkflowStatus.COMPLETED
                for dep_id in step.dependencies
            )
            if deps_met:
                ready.append(step)
        return ready
    
    def is_complete(self) -> bool:
        return all(s.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED) for s in self.steps)
    
    def has_failures(self) -> bool:
        return any(s.status == WorkflowStatus.FAILED for s in self.steps)


class AgentOrchestrator:
    """Orchestrates multi-agent workflows."""
    
    def __init__(self, message_bus: MessageBus | None = None):
        self.message_bus = message_bus or get_message_bus()
        self._workflows: dict[str, Workflow] = {}
        self._running_workflows: dict[str, Workflow] = {}
        self.agents = {}  # For test compatibility
        self._register_agents()
    
    def _register_agents(self) -> None:
        """Register all specialized agents."""
        agents = create_all_agents()
        for agent in agents:
            self.agents[agent.agent_id] = agent
        register_all_agents(self.message_bus)
    
    def create_workflow(self, name: str, description: str = "") -> Workflow:
        """Create a new workflow."""
        workflow_id = str(uuid.uuid4())[:8]
        workflow = Workflow(workflow_id=workflow_id, name=name, description=description)
        self._workflows[workflow_id] = workflow
        return workflow
    
    def add_workflow_step(self, workflow_id: str, name: str, agent_type: str, 
                          action: str, parameters: dict[str, Any], dependencies: list[str] | None = None) -> WorkflowStep:
        """Add a step to a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        step_id = str(uuid.uuid4())[:8]
        step = WorkflowStep(
            step_id=step_id,
            name=name,
            agent_type=agent_type,
            action=action,
            parameters=parameters,
            dependencies=dependencies or [],
        )
        workflow.add_step(step)
        return step
    
    async def execute_workflow(self, workflow_id: str | Workflow) -> Workflow:
        """Execute a workflow."""
        # Accept either workflow_id string or Workflow object
        if isinstance(workflow_id, Workflow):
            workflow = workflow_id
            workflow_id = workflow.workflow_id
            # Register the workflow if not already registered
            if workflow_id not in self._workflows:
                self._workflows[workflow_id] = workflow
        else:
            workflow = self._workflows.get(workflow_id)
        
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now().isoformat()
        self._running_workflows[workflow_id] = workflow
        
        logger.info(f"Starting workflow {workflow_id}: {workflow.name}")
        
        # Execute steps in dependency order
        while not workflow.is_complete():
            ready_steps = workflow.get_ready_steps()
            
            if not ready_steps:
                # Check for deadlock
                pending = [s for s in workflow.steps if s.status == WorkflowStatus.PENDING]
                if pending:
                    logger.error(f"Workflow {workflow_id} deadlocked: {len(pending)} steps waiting")
                    for step in pending:
                        step.status = WorkflowStatus.FAILED
                        step.error = "Dependency deadlock"
                break
            
            # Execute ready steps (could parallelize)
            for step in ready_steps:
                self._execute_step(workflow, step)
        
        # Determine final status
        if workflow.has_failures():
            workflow.status = WorkflowStatus.FAILED
        else:
            workflow.status = WorkflowStatus.COMPLETED
        
        workflow.completed_at = datetime.now().isoformat()
        del self._running_workflows[workflow_id]
        
        logger.info(f"Workflow {workflow_id} completed with status: {workflow.status.value}")
        return workflow
    
    def _execute_step(self, workflow: Workflow, step: WorkflowStep) -> None:
        """Execute a single workflow step."""
        step.status = WorkflowStatus.RUNNING
        step.started_at = datetime.now().isoformat()
        
        logger.info(f"Executing step {step.step_id}: {step.name} on agent {step.agent_type}")
        
        # Find agent by type
        agent = None
        agent_type_lower = step.agent_type.lower()
        for a in self.agents.values():
            # Match by agent_id (e.g., "GeneAnalysisAgent" -> "gene_analysis_agent")
            expected_id = agent_type_lower.replace("agent", "_agent")
            if a.agent_id == expected_id or a.agent_id == agent_type_lower:
                agent = a
                break
            # Match by name (e.g., "GeneAnalysisAgent" in "Gene Analysis Agent")
            if step.agent_type.replace("Agent", "").lower() in a.name.lower():
                agent = a
                break
            # Match by class name
            if a.__class__.__name__ == step.agent_type:
                agent = a
                break
        
        if not agent:
            # Try to get from message bus
            agent = self.message_bus.get_agent(step.agent_type)
        
        if not agent:
            step.status = WorkflowStatus.FAILED
            step.error = f"Agent not found: {step.agent_type}"
            step.completed_at = datetime.now().isoformat()
            return
        
        # Prepare task with workflow context
        task = step.parameters.copy()
        task["type"] = step.action
        task["workflow_context"] = workflow.context
        
        # Add results from dependency steps
        for dep_id in step.dependencies:
            dep_step = workflow.get_step(dep_id)
            if dep_step and dep_step.result:
                task[f"dep_{dep_id}"] = dep_step.result
        
        try:
            result = agent.execute_task(task)
            step.result = result
            step.status = WorkflowStatus.COMPLETED
            
            # Update workflow context with step result
            workflow.context[step.step_id] = result
            
        except Exception as e:
            logger.error(f"Step {step.step_id} failed: {e}")
            step.status = WorkflowStatus.FAILED
            step.error = str(e)
        finally:
            step.completed_at = datetime.now().isoformat()
    
    def get_workflow(self, workflow_id: str) -> Workflow | None:
        return self._workflows.get(workflow_id)
    
    def list_workflows(self) -> list[dict[str, Any]]:
        return [
            {
                "workflow_id": w.workflow_id,
                "name": w.name,
                "description": w.description,
                "status": w.status.value,
                "steps": len(w.steps),
                "created_at": w.created_at,
            }
            for w in self._workflows.values()
        ]
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        workflow = self._workflows.get(workflow_id)
        if workflow and workflow.status == WorkflowStatus.RUNNING:
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.now().isoformat()
            if workflow_id in self._running_workflows:
                del self._running_workflows[workflow_id]
            return True
        return False


# Predefined workflow templates
class WorkflowTemplates:
    """Predefined workflow templates for common research tasks."""
    
    @staticmethod
    def mutation_to_drug_workflow(gene: str, mutation: str) -> Workflow:
        """Create a mutation-to-drug workflow."""
        workflow_id = f"mutation_to_drug_{str(uuid.uuid4())[:8]}"
        workflow = Workflow(
            workflow_id=workflow_id,
            name=f"Mutation to Drug: {gene} {mutation}",
            description=f"Analyze mutation {mutation} in {gene} and identify drug candidates"
        )
        
        # Step 1: Gene analysis
        step1 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Gene Analysis",
            agent_type="GeneAnalysisAgent",
            action="analyze_gene",
            parameters={"gene_symbol": gene, "mutation": mutation},
            dependencies=[],
        )
        workflow.add_step(step1)
        
        # Step 2: Drug discovery
        step2 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Drug Discovery",
            agent_type="DrugDiscoveryAgent",
            action="search_drugs_by_target",
            parameters={"target": gene},
            dependencies=[step1.step_id],
        )
        workflow.add_step(step2)
        
        return workflow
    
    @staticmethod
    def drug_repurposing_workflow(disease: str) -> Workflow:
        """Create a drug repurposing workflow."""
        workflow_id = f"drug_repurposing_{str(uuid.uuid4())[:8]}"
        workflow = Workflow(
            workflow_id=workflow_id,
            name=f"Drug Repurposing: {disease}",
            description=f"Find repurposing candidates for {disease}"
        )
        
        # Step 1: Disease analysis
        step1 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Disease Analysis",
            agent_type="DiseaseAnalysisAgent",
            action="analyze_disease",
            parameters={"disease_name": disease},
            dependencies=[],
        )
        workflow.add_step(step1)
        
        # Step 2: Drug repurposing
        step2 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Drug Repurposing",
            agent_type="DrugRepurposingAgent",
            action="find_repurposing_candidates",
            parameters={"disease": disease},
            dependencies=[step1.step_id],
        )
        workflow.add_step(step2)
        
        return workflow
    
    @staticmethod
    def biomarker_discovery_workflow(disease: str) -> Workflow:
        """Create a biomarker discovery workflow."""
        workflow_id = f"biomarker_discovery_{str(uuid.uuid4())[:8]}"
        workflow = Workflow(
            workflow_id=workflow_id,
            name=f"Biomarker Discovery: {disease}",
            description=f"Discover biomarkers for {disease}"
        )
        
        # Step 1: Biomarker discovery
        step1 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Biomarker Discovery",
            agent_type="BiomarkerAgent",
            action="discover_biomarkers",
            parameters={"disease": disease},
            dependencies=[],
        )
        workflow.add_step(step1)
        
        # Step 2: Gene analysis
        step2 = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            name="Gene Analysis",
            agent_type="GeneAnalysisAgent",
            action="identify_disease_genes",
            parameters={"disease_name": disease},
            dependencies=[step1.step_id],
        )
        workflow.add_step(step2)
        
        return workflow


# Global orchestrator instance
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator