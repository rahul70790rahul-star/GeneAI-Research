"""Streamlit UI for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import uuid

from geneai.autonomous_agent.core import (
    AutonomousBioAgent,
    AgentConfig,
    AgentStatus,
    ResearchResult,
    create_autonomous_agent,
)
from geneai.autonomous_agent.planner import TaskPlanner, TaskType
from geneai.autonomous_agent.monitor import WorkflowMonitor
from geneai.autonomous_agent.history import ExecutionHistory
from geneai.autonomous_agent.memory import get_short_term_memory, get_long_term_memory
from geneai.autonomous_agent.tools import get_tool_registry
from geneai.autonomous_agent.database import (
    get_agent_session,
    get_task_executions,
    get_pending_approvals,
    get_session_history,
)


def render_autonomous_agent_ui() -> None:
    """Render the Autonomous Bioinformatics Agent UI."""
    st.set_page_config(page_title="Autonomous Bioinformatics Agent", layout="wide")

    # Initialize session state
    if "agent" not in st.session_state:
        st.session_state.agent = create_autonomous_agent()
    if "current_session" not in st.session_state:
        st.session_state.current_session = None
    if "result" not in st.session_state:
        st.session_state.result = None

    agent = st.session_state.agent

    st.title("🤖 Autonomous Bioinformatics Agent")
    st.markdown("""
    An AI-powered agent that understands your research questions, selects appropriate bioinformatics tools,
    executes analyses, and generates comprehensive summaries.
    """)

    # Sidebar
    with st.sidebar:
        st.header("Configuration")
        max_retries = st.slider("Max Retries", 1, 5, 3)
        max_concurrent = st.slider("Max Concurrent Tasks", 1, 5, 3)
        approval_timeout = st.slider("Approval Timeout (hours)", 1, 48, 24)
        enable_memory = st.checkbox("Enable Conversation Memory", True)

        if st.button("Update Configuration"):
            st.session_state.agent = create_autonomous_agent(AgentConfig(
                max_retries=max_retries,
                max_concurrent_tasks=max_concurrent,
                approval_timeout_hours=approval_timeout,
                enable_memory=enable_memory,
            ))
            st.success("Configuration updated!")

        st.divider()
        st.header("Available Tools")
        registry = get_tool_registry()
        for category in registry.get_categories():
            with st.expander(f"{category.title()} Tools"):
                for tool in registry.list_tools(category):
                    st.write(f"- **{tool.name}**: {tool.description}")

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔬 Ask Question",
        "📋 Session History",
        "📊 Monitoring",
        "🧠 Memory",
        "⚙️ Tools Explorer"
    ])

    with tab1:
        render_ask_question_tab(agent)

    with tab2:
        render_session_history_tab()

    with tab3:
        render_monitoring_tab(agent)

    with tab4:
        render_memory_tab()

    with tab5:
        render_tools_explorer_tab()


def render_ask_question_tab(agent: AutonomousBioAgent) -> None:
    """Render the question input and results tab."""
    st.header("Ask a Research Question")

    # Example questions
    with st.expander("💡 Example Questions"):
        examples = [
            "I have a VCF file with mutations from a cancer patient. What drugs could target these mutations?",
            "Design a new inhibitor for EGFR kinase domain",
            "Find biomarkers for early detection of pancreatic cancer from RNA-seq data",
            "What are the known protein interactions for TP53?",
            "Predict ADMET properties for aspirin (CC(=O)OC1=CC=CC=C1C(=O)O)",
            "Analyze the pathway enrichment for genes: TP53, CDK1, CCNB1, RB1, E2F1",
            "Find literature on BRCA1 mutations in breast cancer",
            "Dock a ligand to the ATP binding site of BRAF kinase",
        ]
        for ex in examples:
            if st.button(ex, key=f"ex_{hash(ex)}", use_container_width=True):
                st.session_state.question_input = ex
                st.rerun()

    # Question input
    question = st.text_area(
        "Research Question",
        value=st.session_state.get("question_input", ""),
        height=100,
        placeholder="Enter your research question in natural language...",
        key="question_input_main",
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        process_btn = st.button("🚀 Process Question", type="primary", use_container_width=True)
    with col2:
        if st.session_state.current_session:
            cancel_btn = st.button("⏹️ Cancel Session", use_container_width=True)
            if cancel_btn:
                agent.cancel_session(st.session_state.current_session)
                st.session_state.current_session = None
                st.rerun()

    # Process question
    if process_btn and question:
        with st.spinner("Processing your question..."):
            result = agent.process_question(question, user_id="streamlit_user")
            st.session_state.result = result
            st.session_state.current_session = result.session_id

    # Display results
    if st.session_state.result:
        result: ResearchResult = st.session_state.result
        render_results(result, agent)


def render_results(result: ResearchResult, agent: AutonomousBioAgent) -> None:
    """Render research results."""
    st.divider()

    # Status badge
    status_colors = {
        "completed": "🟢",
        "failed": "🔴",
        "running": "🟡",
        "awaiting_approval": "🟠",
        "planning": "🔵",
        "cancelled": "⚫",
    }
    status_icon = status_colors.get(result.status.value, "⚪")
    st.subheader(f"{status_icon} Status: {result.status.value.title()}")

    if result.error_message:
        st.error(f"Error: {result.error_message}")

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Execution Time", f"{result.execution_time_seconds:.1f}s")
    with col2:
        st.metric("Tasks Executed", len(result.task_results) if result.task_results else 0)
    with col3:
        successful = sum(1 for r in result.task_results if r.get("status") == "completed")
        st.metric("Successful", successful)
    with col4:
        failed = sum(1 for r in result.task_results if r.get("status") == "failed")
        st.metric("Failed", failed)

    # Task Plan
    if result.task_plan:
        with st.expander("📋 Task Plan", expanded=True):
            for i, task in enumerate(result.task_plan.tasks, 1):
                task_result = next((r for r in result.task_results if r.get("task_id") == task.task_id), None)
                status = task_result.get("status", "pending") if task_result else "pending"
                status_emoji = {"completed": "✅", "failed": "❌", "running": "🔄", "pending": "⏳"}.get(status, "⏳")

                st.write(f"{i}. {status_emoji} **{task.name}** (`{task.tool_name}`)")
                if task_result and task_result.get("error"):
                    st.caption(f"Error: {task_result['error']}")

    # Task Results
    if result.task_results:
        with st.expander("📊 Task Results", expanded=True):
            for task_result in result.task_results:
                if task_result.get("result"):
                    st.write(f"**{task_result['task_name']}** (`{task_result['tool_name']}`)")
                    with st.expander("View Result"):
                        st.json(task_result["result"])

    # Summary
    if result.summary:
        st.divider()
        st.subheader("📝 Research Summary")
        st.markdown(result.summary)

        # Download button
        st.download_button(
            "📥 Download Summary",
            data=result.summary,
            file_name=f"research_summary_{result.session_id[:8]}.md",
            mime="text/markdown",
        )

    # Pending approvals
    if result.status.value == "awaiting_approval":
        st.divider()
        st.subheader("⏳ Pending Approvals")
        approvals = get_pending_approvals(result.session_id)
        for approval in approvals:
            with st.expander(f"Approval: {approval['description'][:80]}..."):
                st.write(f"**Type**: {approval['request_type']}")
                st.write(f"**Description**: {approval['description']}")
                st.json(approval.get("parameters", {}))

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Approve", key=f"approve_{approval['approval_id']}"):
                        agent.wait_for_approval(result.session_id, approval['approval_id'], "approved", "user")
                        st.rerun()
                with col2:
                    if st.button("❌ Reject", key=f"reject_{approval['approval_id']}"):
                        agent.wait_for_approval(result.session_id, approval['approval_id'], "rejected", "user")
                        st.rerun()


def render_session_history_tab() -> None:
    """Render session history tab."""
    st.header("Session History")

    # In production, would query database for all sessions
    # For now, show current session if exists
    if st.session_state.current_session:
        session = get_agent_session(st.session_state.current_session)
        if session:
            st.subheader(f"Session: {session['session_id'][:8]}...")
            st.write(f"**Question**: {session['question']}")
            st.write(f"**Status**: {session['status']}")
            st.write(f"**Created**: {session['created_at']}")

            executions = get_task_executions(st.session_state.current_session)
            if executions:
                df = pd.DataFrame(executions)
                st.dataframe(df[["task_name", "tool_name", "status", "execution_time_seconds", "retry_count"]])

                # Timeline chart
                fig = px.bar(
                    df,
                    x="task_name",
                    y="execution_time_seconds",
                    color="status",
                    title="Task Execution Times",
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No active session. Process a question to see session history.")


def render_monitoring_tab(agent: AutonomousBioAgent) -> None:
    """Render monitoring tab."""
    st.header("Workflow Monitoring")

    monitor = agent.monitor

    # Summary metrics
    summary = monitor.get_summary()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tasks", summary["total_tasks"])
    with col2:
        st.metric("Completed", summary["completed"])
    with col3:
        st.metric("Failed", summary["failed"])
    with col4:
        st.metric("Success Rate", f"{summary['success_rate']*100:.1f}%")

    # Running tasks
    running = monitor.get_running_tasks()
    if running:
        st.subheader("🔄 Running Tasks")
        for task in running:
            elapsed = time.time() - task.start_time if task.start_time else 0
            st.write(f"- **{task.task_name}** ({task.tool_name}) - {elapsed:.0f}s")

    # Anomalies
    anomalies = monitor.check_anomalies()
    if anomalies:
        st.subheader("⚠️ Anomalies Detected")
        for anomaly in anomalies:
            st.warning(f"{anomaly['type']}: {anomaly['message']}")

    # All metrics table
    if summary["total_tasks"] > 0:
        st.subheader("All Task Metrics")
        metrics_data = []
        for task_id, metrics in monitor.get_all_metrics().items():
            metrics_data.append({
                "Task ID": task_id[:8],
                "Name": metrics.task_name,
                "Tool": metrics.tool_name,
                "Status": metrics.status,
                "Duration (s)": f"{metrics.duration_seconds:.1f}",
                "Retries": metrics.retry_count,
            })
        st.dataframe(pd.DataFrame(metrics_data))


def render_memory_tab() -> None:
    """Render memory tab."""
    st.header("Agent Memory")

    short_term = get_short_term_memory()
    long_term = get_long_term_memory()

    if st.session_state.current_session:
        stats = short_term.get_stats(st.session_state.current_session)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Entries", stats["total_entries"])
        with col2:
            st.json(stats["by_type"])

        context = short_term.get_context(st.session_state.current_session)
        if context:
            with st.expander("Conversation Context"):
                st.markdown(context)

    # Long-term memory stats
    st.subheader("Long-term Memory")
    st.write(f"Learned Patterns: {len(long_term.patterns)}")
    st.write(f"Successful Workflows: {len(long_term.successful_workflows)}")

    if long_term.patterns:
        with st.expander("Learned Patterns"):
            for qtype, pattern in long_term.patterns.items():
                st.write(f"**{qtype}**: {pattern['count']} runs, {pattern['success_count']} successes")


def render_tools_explorer_tab() -> None:
    """Render tools explorer tab."""
    st.header("Tools Explorer")

    registry = get_tool_registry()

    # Search
    search = st.text_input("🔍 Search tools", placeholder="Search by name or description...")

    # Category filter
    categories = ["All"] + registry.get_categories()
    selected_category = st.selectbox("Category", categories)

    # Filter tools
    tools = registry.list_tools(None if selected_category == "All" else selected_category)
    if search:
        tools = [t for t in tools if search.lower() in t.name.lower() or search.lower() in t.description.lower()]

    # Display tools
    for tool in tools:
        with st.expander(f"{tool.name} ({tool.category})"):
            st.write(f"**Description**: {tool.description}")
            st.write(f"**Requires Approval**: {'Yes' if tool.requires_approval else 'No'}")

            # Parameters
            schema = tool.parameters_schema
            if schema.get("properties"):
                st.write("**Parameters**:")
                for param_name, param_info in schema["properties"].items():
                    required = param_name in schema.get("required", [])
                    st.write(f"- `{param_name}` ({param_info.get('type', 'any')}){' *' if required else ''}: {param_info.get('description', '')}")
                    if param_info.get("enum"):
                        st.write(f"  Options: {param_info['enum']}")

            # Test tool
            if st.button(f"Test {tool.name}", key=f"test_{tool.name}"):
                st.info("Tool testing would execute here with sample parameters")


# Import time for monitoring
import time


# Entry point for Streamlit
if __name__ == "__main__":
    render_autonomous_agent_ui()