"""Streamlit UI for Biotech Assistant - Phase 5.1."""
from __future__ import annotations

import json
import logging
import streamlit as st
from datetime import datetime
from typing import Any

from geneai.biotech_assistant.core import BiotechAssistant, create_biotech_assistant
from geneai.biotech_assistant.memory import get_current_memory, new_conversation, get_memory_store
from geneai.biotech_assistant.citations import CitationManager, EvidenceGrade

logger = logging.getLogger(__name__)


def render_biotech_assistant():
    """Render the Biotech Assistant chat interface."""
    st.title("🧬 GeneAI Biotechnology Research Assistant")
    st.caption("AI-powered research assistant for genomics, drug discovery, and biomedical research")
    
    # Initialize assistant in session state
    if "biotech_assistant" not in st.session_state:
        st.session_state.biotech_assistant = create_biotech_assistant()
        st.session_state.citation_manager = CitationManager()
        st.session_state.memory = get_current_memory()
    
    assistant: BiotechAssistant = st.session_state.biotech_assistant
    memory = st.session_state.memory
    citation_manager: CitationManager = st.session_state.citation_manager
    
    # Sidebar
    with st.sidebar:
        st.header("Session")
        st.write(f"**Session ID:** {memory.session_id}")
        st.write(f"**Turns:** {len(memory.turns)}")
        
        if st.button("🔄 New Conversation", use_container_width=True):
            new_conversation()
            assistant.clear_conversation()
            citation_manager.clear()
            st.rerun()
        
        st.divider()
        
        # Export options
        st.subheader("Export")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 JSON", use_container_width=True):
                export_data = memory.export("json")
                st.download_button(
                    "Download JSON",
                    export_data,
                    f"conversation_{memory.session_id}.json",
                    "application/json",
                    use_container_width=True,
                )
        with col2:
            if st.button("📝 Markdown", use_container_width=True):
                export_data = memory.export("markdown")
                st.download_button(
                    "Download MD",
                    export_data,
                    f"conversation_{memory.session_id}.md",
                    "text/markdown",
                    use_container_width=True,
                )
        
        st.divider()
        
        # Saved sessions
        st.subheader("Saved Sessions")
        store = get_memory_store()
        sessions = store.list_sessions()
        for sess in sessions[:5]:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"{sess['session_id'][:8]} - {sess['turns']} turns")
            with col2:
                if st.button("Load", key=f"load_{sess['session_id']}", use_container_width=True):
                    loaded = store.load(sess['session_id'])
                    assistant.memory = loaded
                    st.rerun()
        
        st.divider()
        
        # Settings
        st.subheader("Settings")
        max_turns = st.slider("Max History Turns", 5, 50, memory.max_turns)
        memory.max_turns = max_turns
        
        show_citations = st.checkbox("Show Citations", value=True)
        show_confidence = st.checkbox("Show Confidence", value=True)
        show_followups = st.checkbox("Show Follow-ups", value=True)
    
    # Main chat area
    st.subheader("Chat")
    
    # Display conversation history
    for turn in memory.turns:
        with st.chat_message("user"):
            st.write(turn.user_question)
        
        with st.chat_message("assistant"):
            answer = turn.assistant_answer
            
            # Answer text
            st.write(answer.get("answer_text", "No answer generated."))
            
            # Metadata row
            meta_cols = st.columns(4)
            with meta_cols[0]:
                st.caption(f"Type: {answer.get('question_type', 'unknown')}")
            with meta_cols[1]:
                if show_confidence:
                    conf = answer.get('confidence', 0)
                    color = "🟢" if conf > 0.7 else "🟡" if conf > 0.4 else "🔴"
                    st.caption(f"{color} Confidence: {conf:.0%}")
            with meta_cols[2]:
                st.caption(f"Tools: {len(answer.get('tool_calls', []))}")
            with meta_cols[3]:
                st.caption(f"Citations: {len(answer.get('citations', []))}")
            
            # Citations
            if show_citations and answer.get("citations"):
                with st.expander("📚 Citations", expanded=False):
                    for cit in answer["citations"]:
                        badge = _get_evidence_badge(cit.get('evidence_grade', 'literature_derived'))
                        st.markdown(f"{badge} **{cit.get('source_type', 'unknown').title()}:** {cit.get('title', cit.get('identifier', 'N/A'))}")
                        if cit.get('url'):
                            st.markdown(f"  [{cit['url']}]({cit['url']})")
                        if cit.get('snippet'):
                            st.caption(cit['snippet'][:200])
            
            # Tool calls
            if answer.get("tool_calls"):
                with st.expander("🔧 Tools Used", expanded=False):
                    for call in answer["tool_calls"]:
                        status = "✅" if not call.get("error") else "❌"
                        st.write(f"{status} **{call['tool_name']}**")
                        if call.get("parameters"):
                            st.json(call["parameters"], expanded=False)
                        if call.get("error"):
                            st.error(call["error"])
            
            # Follow-up questions
            if show_followups and answer.get("follow_up_questions"):
                st.caption("**Suggested follow-ups:**")
                for fq in answer["follow_up_questions"]:
                    if st.button(f"💡 {fq}", key=f"followup_{turn.turn_id}_{fq[:20]}", use_container_width=True):
                        # Trigger new question
                        st.session_state.pending_question = fq
                        st.rerun()
            
            # Limitations
            if answer.get("limitations"):
                with st.expander("⚠️ Limitations", expanded=False):
                    for lim in answer["limitations"]:
                        st.warning(lim)
    
    # Chat input
    prompt = st.chat_input("Ask a biological research question...")
    
    # Handle follow-up button clicks
    if "pending_question" in st.session_state:
        prompt = st.session_state.pending_question
        del st.session_state.pending_question
    
    if prompt:
        # Add user message
        with st.chat_message("user"):
            st.write(prompt)
        
        # Get answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = assistant.ask(prompt)
            
            # Display answer
            st.write(answer.answer_text)
            
            # Metadata
            meta_cols = st.columns(4)
            with meta_cols[0]:
                st.caption(f"Type: {answer.question_type.value}")
            with meta_cols[1]:
                if show_confidence:
                    color = "🟢" if answer.confidence > 0.7 else "🟡" if answer.confidence > 0.4 else "🔴"
                    st.caption(f"{color} Confidence: {answer.confidence:.0%}")
            with meta_cols[2]:
                st.caption(f"Tools: {len(answer.tool_calls)}")
            with meta_cols[3]:
                st.caption(f"Citations: {len(answer.citations)}")
            
            # Citations
            if show_citations and answer.citations:
                with st.expander("📚 Citations", expanded=False):
                    for cit in answer.citations:
                        badge = _get_evidence_badge(cit.evidence_grade.value)
                        st.markdown(f"{badge} **{cit.source_type.value.title()}:** {cit.title or cit.identifier}")
                        if cit.url:
                            st.markdown(f"  [{cit.url}]({cit.url})")
                        if cit.snippet:
                            st.caption(cit.snippet[:200])
            
            # Tool calls
            if answer.tool_calls:
                with st.expander("🔧 Tools Used", expanded=False):
                    for call in answer.tool_calls:
                        status = "✅" if not call.error else "❌"
                        st.write(f"{status} **{call.tool_name}**")
                        if call.parameters:
                            st.json(call.parameters, expanded=False)
                        if call.error:
                            st.error(call.error)
            
            # Follow-ups
            if show_followups and answer.follow_up_questions:
                st.caption("**Suggested follow-ups:**")
                for fq in answer.follow_up_questions:
                    if st.button(f"💡 {fq}", key=f"followup_new_{fq[:20]}", use_container_width=True):
                        st.session_state.pending_question = fq
                        st.rerun()
            
            # Limitations
            if answer.limitations:
                with st.expander("⚠️ Limitations", expanded=False):
                    for lim in answer.limitations:
                        st.warning(lim)
        
        st.rerun()


def _get_evidence_badge(grade: str) -> str:
    """Get emoji badge for evidence grade."""
    badges = {
        "experimental": "🟢",
        "database_curated": "🔵",
        "computational_prediction": "🟡",
        "literature_derived": "📖",
        "inference": "🟠",
        "speculative": "🔴",
        "level_1a": "🟢",
        "level_1b": "🟢",
        "level_2a": "🔵",
        "level_2b": "🔵",
        "level_3a": "🟡",
        "level_3b": "🟡",
        "level_4": "🟠",
        "level_5": "🔴",
    }
    return badges.get(grade, "⚪")


def render_assistant_dashboard():
    """Render a dashboard view of assistant capabilities."""
    st.title("🧬 GeneAI Assistant Dashboard")
    st.caption("Overview of available research capabilities")
    
    # Capability cards
    capabilities = [
        ("🧬 Gene Analysis", "Identify disease genes, expression patterns, pathways", "gene_analysis"),
        ("🔬 Protein Analysis", "Structure prediction, domain analysis, interactions", "protein_analysis"),
        ("🧪 Mutation Interpretation", "VCF analysis, variant classification, clinical significance", "mutation_explanation"),
        ("🏥 Disease Research", "Genetic basis, therapeutic targets, clinical trials", "disease_research"),
        ("💊 Drug Discovery", "Target identification, screening, ADMET, safety", "drug_research"),
        ("🛤️ Pathway Analysis", "Signaling, metabolic networks, crosstalk", "pathway_explanation"),
        ("📚 Literature Search", "PubMed, preprints, crossref, semantic search", "literature_summary"),
        ("📊 Report Generation", "Integrated workflows, evidence synthesis", "report_assistance"),
    ]
    
    cols = st.columns(4)
    for i, (title, desc, key) in enumerate(capabilities):
        with cols[i % 4]:
            st.markdown(f"### {title}")
            st.write(desc)
            if st.button(f"Try {title}", key=f"cap_{key}", use_container_width=True):
                st.session_state.pending_question = f"Help me with {title.lower()}"
                st.rerun()
    
    st.divider()
    
    # Example questions
    st.subheader("Example Questions")
    examples = [
        "What genes are associated with breast cancer?",
        "Analyze the TP53 R175H mutation",
        "Find drugs targeting EGFR",
        "Predict ADMET properties for aspirin",
        "What pathways are involved in Alzheimer's disease?",
        "Search recent papers on CRISPR gene therapy",
        "Find repurposing candidates for COVID-19",
        "Build a safety profile for ibuprofen",
    ]
    
    cols = st.columns(2)
    for i, ex in enumerate(examples):
        with cols[i % 2]:
            if st.button(f"💬 {ex}", key=f"ex_{i}", use_container_width=True):
                st.session_state.pending_question = ex
                st.rerun()


def render():
    """Main render function - chooses view based on state."""
    view = st.session_state.get("assistant_view", "chat")
    
    if view == "dashboard":
        render_assistant_dashboard()
    else:
        render_biotech_assistant()
    
    # View switcher in sidebar
    with st.sidebar:
        st.divider()
        if st.button("🏠 Dashboard", use_container_width=True):
            st.session_state.assistant_view = "dashboard"
            st.rerun()
        if st.button("💬 Chat", use_container_width=True):
            st.session_state.assistant_view = "chat"
            st.rerun()


if __name__ == "__main__":
    render()