"""Streamlit UI for Research Automation - Phase 5.4."""
from __future__ import annotations

import json
import logging
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Any

from geneai.research_automation.core import (
    AutomationEngine, AutomationTask, TaskExecution, 
    AutomationStatus, TriggerType, AutomationTemplates,
    get_automation_engine, register_custom_executor, StepExecutor
)

logger = logging.getLogger(__name__)


def render_research_automation_dashboard():
    """Render the research automation dashboard."""
    st.title("⚙️ GeneAI Research Automation")
    st.caption("Automate repetitive research tasks with scheduled workflows and pipelines")
    
    # Initialize automation engine
    if "automation_engine" not in st.session_state:
        st.session_state.automation_engine = get_automation_engine()
    
    engine: AutomationEngine = st.session_state.automation_engine
    
    # Sidebar
    with st.sidebar:
        st.header("Automation Engine")
        
        # Quick stats
        tasks = engine.list_tasks()
        pending = sum(1 for t in tasks if t.status == AutomationStatus.PENDING)
        running = sum(1 for t in tasks if t.status == AutomationStatus.RUNNING)
        completed = sum(1 for t in tasks if t.status == AutomationStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == AutomationStatus.FAILED)
        
        st.metric("Total Tasks", len(tasks))
        col1, col2 = st.columns(2)
        col1.metric("Pending", pending)
        col2.metric("Running", running)
        col1.metric("Completed", completed)
        col2.metric("Failed", failed)
        
        st.divider()
        
        # Create from template
        st.subheader("Create from Template")
        templates = {
            "Daily Literature Monitor": "daily_literature_monitor",
            "Weekly Drug Discovery Scan": "weekly_drug_discovery_scan",
            "ADMET Screening Pipeline": "admet_screening_pipeline",
            "Biomarker Discovery Workflow": "biomarker_discovery_workflow",
        }
        
        selected_template = st.selectbox("Template", list(templates.keys()))
        
        if selected_template == "Daily Literature Monitor":
            disease = st.text_input("Disease", "cancer")
            webhook = st.text_input("Webhook URL (optional)", "")
            if st.button("Create Task", use_container_width=True):
                task = AutomationTemplates.daily_literature_monitor(disease, webhook)
                st.success(f"Created task: {task.task_id}")
                st.rerun()
        
        elif selected_template == "Weekly Drug Discovery Scan":
            disease = st.text_input("Disease", "breast cancer")
            if st.button("Create Task", use_container_width=True):
                task = AutomationTemplates.weekly_drug_discovery_scan(disease)
                st.success(f"Created task: {task.task_id}")
                st.rerun()
        
        elif selected_template == "ADMET Screening Pipeline":
            smiles_input = st.text_area("SMILES (one per line)", "CCO\nCC(=O)OC1=CC=CC=C1C(=O)O")
            if st.button("Create Task", use_container_width=True):
                smiles_list = [s.strip() for s in smiles_input.split("\n") if s.strip()]
                task = AutomationTemplates.admet_screening_pipeline(smiles_list)
                st.success(f"Created task: {task.task_id}")
                st.rerun()
        
        elif selected_template == "Biomarker Discovery Workflow":
            disease = st.text_input("Disease", "Alzheimer's disease")
            sample_type = st.selectbox("Sample Type", ["blood", "tissue", "CSF", "urine"])
            if st.button("Create Task", use_container_width=True):
                task = AutomationTemplates.biomarker_discovery_workflow(disease, sample_type)
                st.success(f"Created task: {task.task_id}")
                st.rerun()
        
        st.divider()
        
        # Run due tasks
        if st.button("▶️ Run Due Scheduled Tasks", use_container_width=True):
            with st.spinner("Running due tasks..."):
                executions = engine.run_due_tasks()
            if executions:
                st.success(f"Executed {len(executions)} tasks")
                for ex in executions:
                    st.write(f"- {ex.task_id}: {ex.status.value}")
            else:
                st.info("No tasks due")
            st.rerun()
        
        st.divider()
        
        # Export/Import
        st.subheader("Data Management")
        if st.button("📥 Export Tasks", use_container_width=True):
            export_data = json.dumps([t.to_dict() for t in tasks], indent=2)
            st.download_button(
                "Download JSON",
                export_data,
                f"automation_tasks_{datetime.now().strftime('%Y%m%d')}.json",
                "application/json",
                use_container_width=True,
            )
        
        uploaded = st.file_uploader("Import Tasks", type=["json"])
        if uploaded and st.button("Import", use_container_width=True):
            try:
                data = json.load(uploaded)
                for task_data in data:
                    task = AutomationTask.from_dict(task_data)
                    engine.tasks[task.task_id] = task
                engine._save_tasks()
                st.success(f"Imported {len(data)} tasks")
                st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")
    
    # Main tabs
    tab1, tab2, tab3 = st.tabs(["📋 Tasks", "▶️ Execute", "📊 History"])
    
    with tab1:
        render_tasks_tab(engine)
    
    with tab2:
        render_execute_tab(engine)
    
    with tab3:
        render_history_tab(engine)


def render_tasks_tab(engine: AutomationEngine):
    """Render tasks management tab."""
    st.subheader("Automation Tasks")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Status",
            ["All"] + [s.value for s in AutomationStatus]
        )
    with col2:
        tag_filter = st.text_input("Tag filter")
    with col3:
        search = st.text_input("Search")
    
    # Get filtered tasks
    tasks = engine.list_tasks()
    if status_filter != "All":
        tasks = [t for t in tasks if t.status.value == status_filter]
    if tag_filter:
        tasks = [t for t in tasks if tag_filter.lower() in " ".join(t.tags).lower()]
    if search:
        tasks = [t for t in tasks if search.lower() in t.name.lower() or search.lower() in t.description.lower()]
    
    # Display tasks
    if not tasks:
        st.info("No tasks found. Create one from a template or build custom.")
        return
    
    for task in tasks:
        status_icon = {
            AutomationStatus.PENDING: "⏳",
            AutomationStatus.RUNNING: "🔄",
            AutomationStatus.COMPLETED: "✅",
            AutomationStatus.FAILED: "❌",
            AutomationStatus.CANCELLED: "⏹️",
            AutomationStatus.SCHEDULED: "📅",
        }.get(task.status, "❓")
        
        with st.expander(f"{status_icon} {task.name} ({task.task_id})", expanded=False):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.write(f"**Description:** {task.description}")
                st.write(f"**Trigger:** {task.trigger_type.value}")
                if task.trigger_type == TriggerType.SCHEDULE:
                    st.write(f"**Schedule:** {task.schedule}")
                    st.write(f"**Next Run:** {task.next_run or 'Not calculated'}")
                st.write(f"**Steps:** {len(task.steps)}")
                if task.tags:
                    st.write(f"**Tags:** {', '.join(task.tags)}")
                
                # Steps preview
                if task.steps:
                    with st.expander("Steps", expanded=False):
                        for i, step in enumerate(task.steps):
                            st.write(f"{i+1}. **{step.get('type', 'unknown')}**")
                            st.json(step, expanded=False)
            
            with col2:
                st.write(f"**Status:** {task.status.value}")
                st.write(f"**Created:** {task.created_at[:19]}")
                st.write(f"**Runs:** {task.run_count}")
                st.write(f"**Success:** {task.success_count}")
                st.write(f"**Failed:** {task.failure_count}")
                if task.last_run:
                    st.write(f"**Last Run:** {task.last_run[:19]}")
                if task.last_error:
                    st.error(f"Last Error: {task.last_error}")
                
                # Actions
                if task.status != AutomationStatus.RUNNING:
                    if st.button("▶️ Run Now", key=f"run_{task.task_id}", use_container_width=True):
                        with st.spinner("Executing..."):
                            execution = engine.execute_task(task.task_id)
                        st.success(f"Execution: {execution.status.value}")
                        st.rerun()
                
                if st.button("🗑️ Delete", key=f"del_{task.task_id}", use_container_width=True):
                    engine.delete_task(task.task_id)
                    st.success("Task deleted")
                    st.rerun()
                
                # Edit
                with st.expander("Edit", expanded=False):
                    new_name = st.text_input("Name", task.name, key=f"name_{task.task_id}")
                    new_desc = st.text_area("Description", task.description, key=f"desc_{task.task_id}")
                    new_schedule = st.text_input("Schedule (cron)", task.schedule, key=f"sched_{task.task_id}")
                    
                    if st.button("Save", key=f"save_{task.task_id}"):
                        engine.update_task(task.task_id, name=new_name, description=new_desc, schedule=new_schedule)
                        st.success("Task updated")
                        st.rerun()


def render_execute_tab(engine: AutomationEngine):
    """Render manual execution tab."""
    st.subheader("Manual Execution")
    st.write("Run any task with custom context")
    
    tasks = engine.list_tasks()
    if not tasks:
        st.info("No tasks available. Create a task first.")
        return
    
    task_options = {f"{t.name} ({t.task_id})": t.task_id for t in tasks}
    selected = st.selectbox("Select Task", list(task_options.keys()))
    task_id = task_options[selected]
    task = engine.get_task(task_id)
    
    if task:
        st.write(f"**Task:** {task.name}")
        st.write(f"**Steps:** {len(task.steps)}")
        
        # Context input
        st.write("**Execution Context (JSON)**")
        context_str = st.text_area(
            "Context", 
            value=json.dumps(task.context, indent=2),
            height=200,
            key="exec_context"
        )
        
        try:
            context = json.loads(context_str)
        except json.JSONDecodeError:
            st.error("Invalid JSON")
            context = {}
        
        if st.button("▶️ Execute Task", type="primary", use_container_width=True):
            with st.spinner("Executing task..."):
                execution = engine.execute_task(task_id, context)
            
            st.success(f"Execution completed: {execution.status.value}")
            
            # Show results
            st.subheader("Execution Results")
            st.write(f"**Execution ID:** {execution.execution_id}")
            st.write(f"**Duration:** {(datetime.fromisoformat(execution.completed_at) - datetime.fromisoformat(execution.started_at)).total_seconds():.1f}s" if execution.completed_at else "Running...")
            
            if execution.error:
                st.error(f"Error: {execution.error}")
            
            # Step results
            for step_result in execution.steps_results:
                with st.expander(f"Step {step_result['step_index']+1}: {step_result['step_type']}", expanded=True):
                    st.json(step_result['result'], expanded=False)
            
            # Output context
            if execution.output:
                with st.expander("Final Context", expanded=False):
                    st.json(execution.output, expanded=False)


def render_history_tab(engine: AutomationEngine):
    """Render execution history tab."""
    st.subheader("Execution History")
    
    executions = engine.get_execution_history(limit=100)
    
    if not executions:
        st.info("No executions yet")
        return
    
    # Summary
    total = len(executions)
    successful = sum(1 for e in executions if e.status == AutomationStatus.COMPLETED)
    failed = sum(1 for e in executions if e.status == AutomationStatus.FAILED)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Executions", total)
    col2.metric("Successful", successful)
    col3.metric("Failed", failed)
    
    # History table
    history_data = []
    for ex in executions:
        task = engine.get_task(ex.task_id)
        history_data.append({
            "Execution ID": ex.execution_id,
            "Task": task.name if task else ex.task_id,
            "Status": ex.status.value,
            "Started": ex.started_at[:19],
            "Completed": ex.completed_at[:19] if ex.completed_at else "Running",
            "Steps": len(ex.steps_results),
            "Error": ex.error[:50] if ex.error else "",
        })
    
    df = pd.DataFrame(history_data)
    st.dataframe(df, hide_index=True)
    
    # Detail view
    selected_exec = st.selectbox(
        "View execution details",
        options=[e.execution_id for e in executions],
        format_func=lambda x: f"{x} - {next((e for e in executions if e.execution_id == x), None).status.value}"
    )
    
    if selected_exec:
        execution = next((e for e in executions if e.execution_id == selected_exec), None)
        if execution:
            task = engine.get_task(execution.task_id)
            st.write(f"**Task:** {task.name if task else execution.task_id}")
            st.write(f"**Status:** {execution.status.value}")
            st.write(f"**Started:** {execution.started_at}")
            st.write(f"**Completed:** {execution.completed_at or 'Running'}")
            
            if execution.error:
                st.error(f"Error: {execution.error}")
            
            st.write("**Step Results:**")
            for step_result in execution.steps_results:
                with st.expander(f"Step {step_result['step_index']+1}: {step_result['step_type']}", expanded=False):
                    st.json(step_result['result'], expanded=False)


def render_custom_step_builder():
    """Render custom step builder (for advanced users)."""
    st.subheader("Custom Step Builder")
    st.write("Create custom automation steps by implementing StepExecutor")
    
    with st.expander("StepExecutor Template", expanded=True):
        st.code("""
class CustomStep(StepExecutor):
    def get_step_type(self) -> str:
        return "custom_step_type"
    
    def execute(self, step: dict, context: dict) -> dict:
        # Your custom logic here
        param = step.get("param", context.get("default"))
        result = do_something(param)
        return {"result": result}

# Register
register_custom_executor(CustomStep())
""", language="python")


def render():
    """Main render function."""
    tab1, tab2 = st.tabs(["📋 Automation Dashboard", "🔧 Custom Steps"])
    
    with tab1:
        render_research_automation_dashboard()
    
    with tab2:
        render_custom_step_builder()


if __name__ == "__main__":
    render()