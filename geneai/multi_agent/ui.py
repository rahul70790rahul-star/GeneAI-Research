"""Streamlit UI for Multi-Agent System - Phase 5.2."""
from __future__ import annotations

import json
import logging
import streamlit as st
from typing import Any

from geneai.multi_agent.core import get_message_bus, AgentStatus, MessageType
from geneai.multi_agent.agents import create_all_agents, register_all_agents
from geneai.multi_agent.orchestrator import (
    AgentOrchestrator, WorkflowTemplates, WorkflowStatus, get_orchestrator
)

logger = logging.getLogger(__name__)


def render_multi_agent_dashboard():
    """Render the multi-agent system dashboard."""
    st.title("🤖 GeneAI Multi-Agent Research System")
    st.caption("Coordinated AI agents for complex biotechnology research workflows")
    
    # Initialize orchestrator and message bus
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = get_orchestrator()
        st.session_state.message_bus = get_message_bus()
        # Register agents if not already
        if not st.session_state.message_bus._agents:
            register_all_agents(st.session_state.message_bus)
            st.session_state.message_bus.start()
    
    orchestrator: AgentOrchestrator = st.session_state.orchestrator
    message_bus = st.session_state.message_bus
    
    # Sidebar
    with st.sidebar:
        st.header("System Status")
        
        # Agent status
        agents = message_bus.list_agents()
        st.subheader(f"Agents ({len(agents)})")
        for agent in agents:
            status_color = {
                "idle": "🟢",
                "busy": "🟡",
                "error": "🔴",
                "initializing": "🔵",
                "shutdown": "⚫",
            }.get(agent["status"], "⚪")
            with st.expander(f"{status_color} {agent['name']}", expanded=False):
                st.write(f"**ID:** {agent['agent_id']}")
                st.write(f"**Status:** {agent['status']}")
                st.write(f"**Capabilities:** {', '.join(agent['capabilities'])}")
        
        st.divider()
        
        # Workflow templates
        st.subheader("Workflow Templates")
        templates = {
            "Drug Discovery": "create_drug_discovery_workflow",
            "Mutation Analysis": "create_mutation_analysis_workflow",
            "Biomarker Discovery": "create_biomarker_discovery_workflow",
        }
        
        selected_template = st.selectbox("Select Template", list(templates.keys()))
        
        if selected_template == "Drug Discovery":
            disease = st.text_input("Disease", "breast cancer")
            genes = st.text_input("Gene symbols (comma-separated)", "TP53, BRCA1, BRCA2")
            if st.button("Create Workflow", use_container_width=True):
                gene_list = [g.strip() for g in genes.split(",") if g.strip()]
                workflow = WorkflowTemplates.create_drug_discovery_workflow(
                    orchestrator, disease, gene_list
                )
                st.session_state.current_workflow = workflow.workflow_id
                st.success(f"Created workflow: {workflow.workflow_id}")
                st.rerun()
        
        elif selected_template == "Mutation Analysis":
            mutations = st.text_input("Mutations (comma-separated)", "TP53 R175H, EGFR L858R")
            disease = st.text_input("Associated disease", "lung cancer")
            if st.button("Create Workflow", use_container_width=True):
                mut_list = [m.strip() for m in mutations.split(",") if m.strip()]
                workflow = WorkflowTemplates.create_mutation_analysis_workflow(
                    orchestrator, mut_list, disease
                )
                st.session_state.current_workflow = workflow.workflow_id
                st.success(f"Created workflow: {workflow.workflow_id}")
                st.rerun()
        
        elif selected_template == "Biomarker Discovery":
            disease = st.text_input("Disease", "Alzheimer's disease")
            sample_type = st.selectbox("Sample Type", ["blood", "tissue", "CSF", "urine"])
            if st.button("Create Workflow", use_container_width=True):
                workflow = WorkflowTemplates.create_biomarker_discovery_workflow(
                    orchestrator, disease, sample_type
                )
                st.session_state.current_workflow = workflow.workflow_id
                st.success(f"Created workflow: {workflow.workflow_id}")
                st.rerun()
        
        st.divider()
        
        # Saved workflows
        st.subheader("Workflows")
        workflows = orchestrator.list_workflows()
        for wf in workflows[-5:]:
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "cancelled": "⏹️",
            }.get(wf["status"], "❓")
            if st.button(f"{status_icon} {wf['name']}", key=f"wf_{wf['workflow_id']}", use_container_width=True):
                st.session_state.current_workflow = wf["workflow_id"]
                st.rerun()
    
    # Main content
    current_wf_id = st.session_state.get("current_workflow")
    
    if current_wf_id:
        workflow = orchestrator.get_workflow(current_wf_id)
        if workflow:
            render_workflow_detail(workflow, orchestrator)
        else:
            st.error("Workflow not found")
            if st.button("Clear"):
                del st.session_state.current_workflow
                st.rerun()
    else:
        render_workflow_overview(orchestrator)


def render_workflow_overview(orchestrator: AgentOrchestrator):
    """Render overview of all workflows."""
    st.subheader("Workflow Overview")
    
    workflows = orchestrator.list_workflows()
    
    if not workflows:
        st.info("No workflows created yet. Use the sidebar to create one from a template.")
        return
    
    # Summary metrics
    total = len(workflows)
    completed = sum(1 for w in workflows if w["status"] == "completed")
    running = sum(1 for w in workflows if w["status"] == "running")
    failed = sum(1 for w in workflows if w["status"] == "failed")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", total)
    col2.metric("Completed", completed)
    col3.metric("Running", running)
    col4.metric("Failed", failed)
    
    # Workflow list
    st.subheader("All Workflows")
    for wf in workflows:
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "⏹️",
        }.get(wf["status"], "❓")
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"{status_icon} **{wf['name']}**")
                st.caption(wf["description"])
            with col2:
                st.write(f"Status: {wf['status']}")
                st.caption(f"Steps: {wf['steps']}")
            with col3:
                st.caption(f"Created: {wf['created_at'][:19]}")
                if st.button("View", key=f"view_{wf['workflow_id']}"):
                    st.session_state.current_workflow = wf["workflow_id"]
                    st.rerun()


def render_workflow_detail(workflow, orchestrator: AgentOrchestrator):
    """Render detailed view of a workflow."""
    st.subheader(f"Workflow: {workflow.name}")
    st.caption(workflow.description)
    
    # Status bar
    status_colors = {
        WorkflowStatus.PENDING: "🟡",
        WorkflowStatus.RUNNING: "🔵",
        WorkflowStatus.COMPLETED: "🟢",
        WorkflowStatus.FAILED: "🔴",
        WorkflowStatus.CANCELLED: "⚫",
    }
    status_icon = status_colors.get(workflow.status, "❓")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.write(f"{status_icon} **Status:** {workflow.status.value}")
    col2.write(f"**Steps:** {len(workflow.steps)}")
    col3.write(f"**Created:** {workflow.created_at[:19]}")
    if workflow.started_at:
        col4.write(f"**Started:** {workflow.started_at[:19]}")
    
    # Action buttons
    if workflow.status == WorkflowStatus.PENDING:
        if st.button("▶️ Execute Workflow", type="primary", use_container_width=True):
            with st.spinner("Executing workflow..."):
                result = orchestrator.execute_workflow(workflow.workflow_id)
            st.success(f"Workflow {result.status.value}")
            st.rerun()
    elif workflow.status == WorkflowStatus.RUNNING:
        st.info("Workflow is running...")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    elif workflow.status == WorkflowStatus.FAILED:
        if st.button("🔁 Retry", use_container_width=True):
            # Reset failed steps
            for step in workflow.steps:
                if step.status == WorkflowStatus.FAILED:
                    step.status = WorkflowStatus.PENDING
                    step.error = None
            workflow.status = WorkflowStatus.PENDING
            st.rerun()
    
    st.divider()
    
    # Steps
    st.subheader("Workflow Steps")
    
    for step in workflow.steps:
        step_status_colors = {
            WorkflowStatus.PENDING: "⏳",
            WorkflowStatus.RUNNING: "🔄",
            WorkflowStatus.COMPLETED: "✅",
            WorkflowStatus.FAILED: "❌",
            WorkflowStatus.CANCELLED: "⏹️",
        }
        step_icon = step_status_colors.get(step.status, "❓")
        
        with st.expander(f"{step_icon} Step {step.step_id[:8]}: {step.name} ({step.agent_id})", 
                         expanded=step.status in (WorkflowStatus.RUNNING, WorkflowStatus.FAILED)):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.write(f"**Agent:** {step.agent_id}")
                st.write(f"**Task:** {step.name}")
                st.json(step.task, expanded=False)
                
                if step.dependencies:
                    st.write(f"**Dependencies:** {', '.join(step.dependencies)}")
            
            with col2:
                st.write(f"**Status:** {step.status.value}")
                if step.started_at:
                    st.write(f"**Started:** {step.started_at[:19]}")
                if step.completed_at:
                    st.write(f"**Completed:** {step.completed_at[:19]}")
                
                if step.error:
                    st.error(f"Error: {step.error}")
            
            # Show result
            if step.result:
                with st.expander("Result", expanded=False):
                    st.json(step.result, expanded=False)
    
    # Workflow context
    if workflow.context:
        st.divider()
        st.subheader("Workflow Context")
        st.json(workflow.context, expanded=False)


def render_agent_chat():
    """Render a chat interface for interacting with agents."""
    st.title("💬 Agent Chat")
    st.caption("Direct interaction with specialized agents")
    
    message_bus = get_message_bus()
    agents = message_bus.list_agents()
    
    # Agent selector
    agent_names = {a["agent_id"]: a["name"] for a in agents}
    selected_agent_id = st.selectbox(
        "Select Agent",
        options=list(agent_names.keys()),
        format_func=lambda x: agent_names[x]
    )
    
    agent = message_bus.get_agent(selected_agent_id)
    if not agent:
        st.error("Agent not found")
        return
    
    # Show agent capabilities
    with st.expander("Agent Capabilities", expanded=False):
        for cap in agent.get_capabilities():
            st.write(f"**{cap.name}**: {cap.description}")
            with st.expander("Input Schema"):
                st.json(cap.input_schema)
            with st.expander("Output Schema"):
                st.json(cap.output_schema)
    
    # Chat interface
    if "agent_chat_history" not in st.session_state:
        st.session_state.agent_chat_history = []
    
    # Display history
    for msg in st.session_state.agent_chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("result"):
                st.json(msg["result"], expanded=False)
    
    # Input
    prompt = st.chat_input("Enter task for agent...")
    
    if prompt:
        # Add user message
        st.session_state.agent_chat_history.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Execute task
        with st.chat_message("assistant"):
            with st.spinner("Agent working..."):
                try:
                    # Parse task from prompt (simplified)
                    task = {"type": "analyze_disease", "disease_name": prompt}  # default
                    # Try to infer task type from prompt
                    prompt_lower = prompt.lower()
                    if "gene" in prompt_lower:
                        task = {"type": "identify_disease_genes", "disease_name": prompt}
                    elif "drug" in prompt_lower or "compound" in prompt_lower:
                        task = {"type": "search_drugs_by_disease", "disease": prompt}
                    elif "protein" in prompt_lower:
                        task = {"type": "search_uniprot", "query": prompt}
                    elif "admet" in prompt_lower or "toxicity" in prompt_lower:
                        task = {"type": "predict_admet", "smiles": "CCO"}
                    elif "literature" in prompt_lower or "paper" in prompt_lower:
                        task = {"type": "search_pubmed", "query": prompt}
                    elif "biomarker" in prompt_lower:
                        task = {"type": "discover_biomarkers", "disease": prompt}
                    elif "repurpos" in prompt_lower:
                        task = {"type": "find_repurposing_candidates", "disease": prompt}
                    
                    result = agent.execute_task(task)
                    
                    st.success("Task completed!")
                    st.json(result, expanded=False)
                    
                    st.session_state.agent_chat_history.append({
                        "role": "assistant",
                        "content": f"Completed task: {task.get('type')}",
                        "result": result
                    })
                    
                except Exception as e:
                    st.error(f"Task failed: {e}")
                    st.session_state.agent_chat_history.append({
                        "role": "assistant",
                        "content": f"Error: {e}"
                    })


def render():
    """Main render function with tabs."""
    tab1, tab2 = st.tabs(["📊 Workflow Dashboard", "💬 Agent Chat"])
    
    with tab1:
        render_multi_agent_dashboard()
    
    with tab2:
        render_agent_chat()


if __name__ == "__main__":
    render()