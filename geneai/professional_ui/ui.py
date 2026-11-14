"""Streamlit UI for Professional UI - Phase 5.8."""
from __future__ import annotations

import streamlit as st
from datetime import datetime
from typing import Any

from geneai.professional_ui.core import (
    ThemeMode, ColorScheme, apply_theme, render_theme_selector,
    inject_professional_css, pro_card, pro_metric_card, pro_status_badge,
    pro_section_header, pro_empty_state, pro_data_table, pro_page_header,
    announce_to_screen_reader
)

# Auto-inject professional CSS when module is imported
inject_professional_css()


def render_professional_ui_demo():
    """Render the professional UI demo page."""
    # Apply theme from session state (theme selector is in global sidebar)
    theme_mode = st.session_state.get("theme_mode", "light")
    color_scheme = st.session_state.get("color_scheme", "default")
    apply_theme(ThemeMode(theme_mode), ColorScheme(color_scheme))
    
    # Page header
    pro_page_header(
        "Professional UI Components",
        "Demonstration of GeneAI's professional UI component library",
        actions=[
            ("📋 Copy CSS", "copy_css"),
            ("🔄 Reset Theme", "reset_theme"),
        ]
    )
    
    # Theme showcase
    with st.expander("🎨 Theme Configuration", expanded=True):
        st.write("Current theme settings are applied globally. Use the sidebar to change theme mode and color scheme.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Theme Modes:**")
            for mode in ThemeMode:
                pro_status_badge(mode.value.title(), "info")
        
        with col2:
            st.markdown("**Color Schemes:**")
            for scheme in ColorScheme:
                pro_status_badge(scheme.value.title(), "neutral")
    
    st.divider()
    
    # Component demonstrations
    pro_section_header("📦 Cards", "Professional card components with hover effects")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        pro_card(
            "Gene Analysis",
            "Comprehensive gene analysis with disease associations, pathways, and variants",
            icon="🧬",
            action_label="Open",
            action_key="card_gene"
        )
    
    with col2:
        pro_card(
            "Drug Discovery",
            "Search drugs, predict targets, ADMET properties, and repurposing candidates",
            icon="💊",
            action_label="Open",
            action_key="card_drug"
        )
    
    with col3:
        pro_card(
            "Protein Analysis",
            "Structure prediction, interaction networks, and functional annotation",
            icon="🔬",
            action_label="Open",
            action_key="card_protein"
        )
    
    st.divider()
    
    # Metric cards
    pro_section_header("📊 Metric Cards", "Key performance indicators with trend indicators")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        pro_metric_card("Genes Analyzed", "12,345", "+12%", "normal", "🧬")
    
    with col2:
        pro_metric_card("Drug Candidates", "842", "+5%", "normal", "💊")
    
    with col3:
        pro_metric_card("Pathways Mapped", "1,234", "-2%", "inverse", "🛤️")
    
    with col4:
        pro_metric_card("Publications", "56,789", "+8%", "normal", "📚")
    
    st.divider()
    
    # Status badges
    pro_section_header("🏷️ Status Badges", "Semantic status indicators")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        pro_status_badge("Completed", "success")
    with col2:
        pro_status_badge("In Progress", "info")
    with col3:
        pro_status_badge("Warning", "warning")
    with col4:
        pro_status_badge("Failed", "error")
    with col5:
        pro_status_badge("Pending", "neutral")
    
    st.divider()
    
    # Data table
    pro_section_header("📋 Data Table", "Professional data table with selection")
    
    sample_data = [
        {"Gene": "TP53", "Disease": "Breast Cancer", "Score": 0.95, "Status": "Validated"},
        {"Gene": "BRCA1", "Disease": "Ovarian Cancer", "Score": 0.92, "Status": "Validated"},
        {"Gene": "EGFR", "Disease": "Lung Cancer", "Score": 0.88, "Status": "Clinical Trial"},
        {"Gene": "KRAS", "Disease": "Colorectal Cancer", "Score": 0.85, "Status": "Preclinical"},
        {"Gene": "PIK3CA", "Disease": "Breast Cancer", "Score": 0.82, "Status": "Research"},
    ]
    
    selected = pro_data_table(sample_data, selection=True, key="demo_table")
    
    if selected:
        st.success(f"Selected {len(selected)} rows: {selected}")
    
    st.divider()
    
    # Empty states
    pro_section_header("📭 Empty States", "User-friendly empty state patterns")
    
    col1, col2 = st.columns(2)
    
    with col1:
        pro_empty_state(
            "🔍", "No Results Found",
            "Try adjusting your search criteria or filters",
            "Clear Filters", "clear_filters"
        )
    
    with col2:
        pro_empty_state(
            "📁", "No Projects Yet",
            "Create your first research project to get started",
            "Create Project", "create_project_demo"
        )
    
    st.divider()
    
    # Form elements showcase
    pro_section_header("📝 Form Elements", "Professional form components")
    
    with st.form("demo_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.text_input("Gene Symbol", placeholder="e.g., TP53")
            st.selectbox("Analysis Type", ["Expression", "Mutation", "Pathway", "Interaction"])
            st.date_input("Start Date")
        
        with col2:
            st.text_area("Notes", placeholder="Additional information...")
            st.multiselect("Databases", ["OpenTargets", "ClinVar", "gnomAD", "UniProt", "PDB"])
            st.number_input("Confidence Threshold", 0.0, 1.0, 0.8)
        
        st.checkbox("Include literature references")
        st.slider("Max Results", 10, 500, 50)
        
        submitted = st.form_submit_button("Run Analysis", type="primary", use_container_width=True)
        
        if submitted:
            announce_to_screen_reader("Analysis started successfully")
            st.success("Analysis submitted!")
    
    st.divider()
    
    # Progress and feedback
    pro_section_header("⏳ Progress & Feedback", "Loading states and user feedback")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Progress Bar**")
        progress = st.progress(0)
        for i in range(101):
            progress.progress(i)
    
    with col2:
        st.write("**Spinner**")
        with st.spinner("Processing..."):
            import time
            time.sleep(1)
        st.success("Complete!")
    
    st.write("**Alert Types**")
    st.info("This is an informational message")
    st.success("Operation completed successfully!")
    st.warning("This is a warning message")
    st.error("An error occurred")
    
    st.divider()
    
    # Accessibility demo
    pro_section_header("♿ Accessibility", "Screen reader announcements and focus management")
    
    if st.button("Announce to Screen Reader"):
        announce_to_screen_reader("New gene analysis results are available")
        st.success("Announcement sent to screen readers")
    
    st.caption("Try navigating with Tab key - focus indicators are visible")


def render():
    """Main render function."""
    render_professional_ui_demo()


if __name__ == "__main__":
    render()