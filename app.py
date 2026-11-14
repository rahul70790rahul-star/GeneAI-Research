from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

# Deployment configuration (load first to set up environment)
from geneai.deployment_config import load_config, get_config, is_production, is_streamlit_cloud
load_config()

# Existing module imports - PRESERVE ALL EXISTING FUNCTIONALITY
from geneai.lab import add_sample, load_samples
from geneai.mutation_ui import render_mutation_interpretation_page
from geneai.drug_discovery.disease_ui import render_disease_analysis_page
from geneai.drug_discovery.protein_ui import render_protein_structure_page
from geneai.drug_discovery.target_ui import render_target_identification_page
from geneai.drug_discovery.gene_identification_ui import render_gene_identification_page
from geneai.drug_discovery.mutation_target_ui import render_mutation_target_page
from geneai.drug_discovery.pathway_ui import render_pathway_analysis_page
from geneai.drug_discovery.ppi_ui import render_ppi_network_page
from geneai.drug_discovery.druggability_ui import render_druggability_analysis_page
from geneai.drug_discovery.target_ranking_ui import render_target_ranking_page
from geneai.drug_discovery import render_drug_discovery_dashboard
from geneai.drug_repurposing import render_drug_repurposing_dashboard
from geneai.drug_target_prediction import render_drug_target_prediction_dashboard
from geneai.research_analysis import render_research_analysis_dashboard
from geneai.admet_prediction.admet_ui import render_admet_dashboard
from geneai.disease_gene_pathway.dgp_ui import render_dgp_dashboard
from geneai.drug_safety.safety_ui import render_drug_safety_dashboard
from geneai.integrated_precision.ipdd_ui import render_integrated_precision_dashboard
from geneai.ai_research_intelligence.unified_dashboard import render_ai_research_intelligence_dashboard
from geneai.biotech_assistant.ui import render as render_biotech_assistant
from geneai.multi_agent.ui import render as render_multi_agent
from geneai.unified_knowledge.ui import render as render_unified_knowledge
from geneai.research_automation.ui import render as render_research_automation
from geneai.multi_user.ui import render as render_multi_user
from geneai.cloud_integration.ui import render as render_cloud_integration
from geneai.rest_api.ui import render as render_rest_api
from geneai.professional_ui.ui import render as render_professional_ui
from geneai.security.ui import render as render_security
from geneai.performance.ui import render as render_performance
from geneai.autonomous_agent.autonomous_agent_ui import render_autonomous_agent_ui
from geneai.genomic_intelligence.genomic_ui import render_genomic_intelligence_dashboard
from geneai.protein_intelligence.protein_ui import render_protein_intelligence_dashboard
from geneai.drug_design.drug_design_ui import render_drug_design_ui
from geneai.molecular_docking.docking_ui import render_molecular_docking_ui
from geneai.mutation_ml.dashboard import render_ml_dashboard_page
from geneai.research import search_pubmed
from geneai.report import build_report
from geneai.sequence import analyze_sequence, parse_sequence_file
from geneai.variants import parse_vcf, summarize_vcf_stream

# Professional UI theme
from geneai.professional_ui.core import (
    inject_professional_css,
    render_theme_selector,
    ThemeConfig,
    ThemeMode,
    ColorScheme,
    pro_card,
    pro_metric_card,
    pro_status_badge,
    pro_section_header,
    pro_empty_state,
    pro_page_header,
    apply_theme,
    THEMES,
    COLOR_SCHEMES,
    DarkThemeColors,
    adjust_color,
    replace,
)

st.set_page_config(
    page_title="GeneAI Research - AI-Powered Biology Workspace",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CUSTOM THEME: Navy Blue / Teal Green / White / Light Grey
# ============================================================

class NavyTealThemeColors(DarkThemeColors):
    """Custom Navy Blue / Teal Green theme for professional scientific workspace."""
    primary: str = "#0D47A1"       # Navy Blue
    primary_light: str = "#1E88E5"
    primary_dark: str = "#0A2351"
    
    secondary: str = "#00796B"      # Teal Green
    secondary_light: str = "#26A69A"
    secondary_dark: str = "#004D40"
    
    background: str = "#0A1628"     # Deep navy background
    surface: str = "#12203A"        # Card surface
    surface_variant: str = "#1A2D4A"
    
    text_primary: str = "#E8EAF6"   # Off-white text
    text_secondary: str = "#9FA8DA" # Muted text
    text_disabled: str = "#5C6BC0"
    
    border: str = "#1E3A5F"
    divider: str = "#1E3A5F"
    
    success: str = "#2E7D32"
    warning: str = "#F57F17"
    error: str = "#C62828"
    info: str = "#0277BD"

# Add to themes
THEMES["navy_teal"] = NavyTealThemeColors()
COLOR_SCHEMES["navy_teal"] = {"primary": "#0D47A1", "secondary": "#00796B"}

# Inject custom CSS for the new design system
CUSTOM_DESIGN_CSS = """
<style>
/* ============================================================
   GENEAI RESEARCH - PROFESSIONAL SCIENTIFIC WORKSPACE
   Color Scheme: Navy Blue (#0D47A1) / Teal Green (#00796B) / White / Light Grey
   ============================================================ */

/* Global App Styles */
.stApp {
    background-color: var(--color-background) !important;
}

/* Sidebar Styling - Dark Navy */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A1628 0%, #12203A 100%) !important;
    border-right: 1px solid var(--color-border) !important;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stSelectbox label {
    color: var(--color-text-primary) !important;
}

section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: var(--color-text-primary) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    padding: 0.625rem 1rem !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(13, 71, 161, 0.2) !important;
    border-color: var(--color-primary-light) !important;
    color: var(--color-primary-light) !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: var(--color-primary) !important;
    color: white !important;
    border-color: var(--color-primary) !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: var(--color-primary-dark) !important;
    border-color: var(--color-primary-dark) !important;
}

/* Sidebar section headers */
section[data-testid="stSidebar"] h3 {
    color: var(--color-primary-light) !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
    padding-left: 0.5rem !important;
    border-left: 3px solid var(--color-primary) !important;
}

section[data-testid="stSidebar"] .stExpander {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

section[data-testid="stSidebar"] .streamlit-expanderHeader {
    background: transparent !important;
    border: none !important;
    color: var(--color-text-secondary) !important;
    font-weight: 500 !important;
    padding: 0.5rem 0.75rem !important;
    border-radius: var(--border-radius) !important;
}

section[data-testid="stSidebar"] .streamlit-expanderHeader:hover {
    background: rgba(13, 71, 161, 0.15) !important;
    color: var(--color-primary-light) !important;
}

section[data-testid="stSidebar"] .streamlit-expanderContent {
    background: transparent !important;
    border: none !important;
    padding-left: 1rem !important;
}

/* Main Content Area */
.main .block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
    max-width: 100% !important;
}

/* Page Header */
.pro-page-header {
    margin-bottom: 2rem !important;
    padding-bottom: 1.5rem !important;
    border-bottom: 1px solid var(--color-divider) !important;
}

.pro-page-header h1 {
    color: var(--color-text-primary) !important;
    font-size: 2.25rem !important;
    font-weight: 700 !important;
    margin: 0 0 0.5rem 0 !important;
    background: linear-gradient(90deg, var(--color-primary-light), var(--color-secondary-light));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.pro-page-header p {
    color: var(--color-text-secondary) !important;
    font-size: 1.125rem !important;
    margin: 0 !important;
}

/* Professional Cards */
.pro-card {
    background: var(--color-surface) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    padding: 1.5rem !important;
    box-shadow: var(--shadow-sm) !important;
    transition: all 0.3s ease !important;
    height: 100% !important;
}

.pro-card:hover {
    box-shadow: var(--shadow-lg) !important;
    border-color: var(--color-primary) !important;
    transform: translateY(-2px) !important;
}

.pro-card h4 {
    color: var(--color-text-primary) !important;
    font-size: 1.125rem !important;
    font-weight: 600 !important;
    margin: 0 0 0.5rem 0 !important;
}

.pro-card p {
    color: var(--color-text-secondary) !important;
    font-size: 0.9375rem !important;
    line-height: 1.6 !important;
    margin: 0 !important;
}

/* Metric Cards */
[data-testid="metric-container"] {
    background: var(--color-surface) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    padding: 1.25rem !important;
    box-shadow: var(--shadow-sm) !important;
    transition: all 0.2s ease !important;
}

[data-testid="metric-container"]:hover {
    box-shadow: var(--shadow-md) !important;
    border-color: var(--color-primary) !important;
}

[data-testid="metric-container"] label {
    color: var(--color-text-secondary) !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.02em !important;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--color-primary-light) !important;
    font-weight: 700 !important;
    font-size: 2.5rem !important;
}

[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    font-size: 0.875rem !important;
}

/* Workflow Progress Tracker */
.workflow-progress {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius-lg);
    margin-bottom: 2rem;
    position: relative;
}

.workflow-progress::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 10%;
    right: 10%;
    height: 2px;
    background: var(--color-border);
    z-index: 1;
    transform: translateY(-50%);
}

.workflow-step {
    position: relative;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    text-align: center;
}

.workflow-step-circle {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 0.875rem;
    margin: 0 auto 0.5rem;
    border: 3px solid var(--color-border);
    background: var(--color-background);
    color: var(--color-text-disabled);
    transition: all 0.3s ease;
}

.workflow-step.active .workflow-step-circle {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: white;
    box-shadow: 0 0 0 4px rgba(13, 71, 161, 0.2);
}

.workflow-step.completed .workflow-step-circle {
    background: var(--color-secondary);
    border-color: var(--color-secondary);
    color: white;
}

.workflow-step.completed .workflow-step-circle::after {
    content: '✓';
}

.workflow-step-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    white-space: nowrap;
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
}

.workflow-step.active .workflow-step-label {
    color: var(--color-primary-light);
    font-weight: 600;
}

.workflow-step.completed .workflow-step-label {
    color: var(--color-secondary-light);
}

/* Quick Action Buttons */
.quick-action-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    color: var(--color-text-primary);
    text-decoration: none;
    transition: all 0.2s ease;
    width: 100%;
}

.quick-action-btn:hover {
    background: rgba(13, 71, 161, 0.15);
    border-color: var(--color-primary);
    color: var(--color-primary-light);
    transform: translateX(4px);
}

.quick-action-btn .icon {
    font-size: 1.5rem;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(13, 71, 161, 0.1);
    border-radius: var(--border-radius-sm);
}

.quick-action-btn.primary .icon {
    background: var(--color-primary);
    color: white;
}

/* Status Indicators */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-badge.active {
    background: rgba(46, 125, 50, 0.2);
    color: #81C784;
}

.status-badge.pending {
    background: rgba(245, 127, 23, 0.2);
    color: #FFB74D;
}

.status-badge.completed {
    background: rgba(0, 121, 107, 0.2);
    color: #4DB6AC;
}

.status-badge.locked {
    background: rgba(92, 107, 192, 0.2);
    color: #9FA8DA;
}

/* Navigation Pills */
.nav-pill {
    padding: 0.5rem 1rem;
    border-radius: var(--border-radius);
    font-weight: 500;
    font-size: 0.875rem;
    transition: all 0.2s ease;
    cursor: pointer;
    border: 1px solid transparent;
}

.nav-pill.active {
    background: rgba(13, 71, 161, 0.2);
    color: var(--color-primary-light);
    border-color: var(--color-primary);
}

.nav-pill:not(.active):hover {
    background: var(--color-surface-variant);
    color: var(--color-text-primary);
}

/* Form Styling */
.stForm {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius-lg);
    padding: 1.5rem;
}

.stForm > div {
    gap: 1rem;
}

/* Button Styling */
.stButton > button {
    border-radius: var(--border-radius) !important;
    font-weight: 500 !important;
    padding: 0.625rem 1.25rem !important;
    transition: all 0.2s ease !important;
}

.stButton > button[kind="primary"] {
    background: var(--color-primary) !important;
    color: white !important;
    border: none !important;
}

.stButton > button[kind="primary"]:hover {
    background: var(--color-primary-dark) !important;
    box-shadow: var(--shadow-md) !important;
}

.stButton > button[kind="secondary"] {
    background: var(--color-surface-variant) !important;
    color: var(--color-text-primary) !important;
    border: 1px solid var(--color-border) !important;
}

.stButton > button[kind="secondary"]:hover {
    background: var(--color-border) !important;
}

/* Input Styling */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div,
.stNumberInput > div > div > input {
    border-radius: var(--border-radius) !important;
    border: 1px solid var(--color-border) !important;
    background: var(--color-surface) !important;
    color: var(--color-text-primary) !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--color-primary) !important;
    box-shadow: 0 0 0 3px rgba(13, 71, 161, 0.2) !important;
}

/* Dataframe Styling */
.stDataFrame {
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    overflow: hidden !important;
}

.stDataFrame thead th {
    background: var(--color-surface-variant) !important;
    color: var(--color-text-primary) !important;
    font-weight: 600 !important;
    border-bottom: 2px solid var(--color-border) !important;
}

.stDataFrame tbody tr:hover {
    background: var(--color-surface-variant) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem !important;
    background: transparent !important;
    border-bottom: 1px solid var(--color-divider) !important;
    padding-bottom: 0 !important;
}

.stTabs [data-baseweb="tab"] {
    border-radius: var(--border-radius) var(--border-radius) 0 0 !important;
    padding: 0.75rem 1.5rem !important;
    font-weight: 500 !important;
    color: var(--color-text-secondary) !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s ease !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--color-text-primary) !important;
    background: var(--color-surface-variant) !important;
}

.stTabs [aria-selected="true"] {
    color: var(--color-primary) !important;
    border-bottom-color: var(--color-primary) !important;
}

/* Expanders */
.streamlit-expanderHeader {
    background: var(--color-surface) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    color: var(--color-text-primary) !important;
    font-weight: 500 !important;
}

.streamlit-expanderContent {
    border: 1px solid var(--color-border) !important;
    border-top: none !important;
    border-radius: 0 0 var(--border-radius) var(--border-radius) !important;
    background: var(--color-surface) !important;
}

/* Alerts */
.stAlert {
    border-radius: var(--border-radius) !important;
    border: none !important;
    box-shadow: var(--shadow-sm) !important;
}

.stAlert > div {
    padding: 1rem 1.25rem !important;
}

/* Progress Bars */
.stProgress > div > div > div {
    border-radius: var(--border-radius-sm) !important;
    background: var(--color-primary) !important;
}

/* Charts - Plotly */
.js-plotly-plot {
    background: var(--color-surface) !important;
    border-radius: var(--border-radius) !important;
    border: 1px solid var(--color-border) !important;
}

/* Responsive Design */
@media (max-width: 1024px) {
    .main .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    
    .pro-page-header h1 {
        font-size: 1.75rem !important;
    }
    
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 2rem !important;
    }
}

@media (max-width: 768px) {
    .main .block-container {
        padding-top: 1rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    
    .pro-page-header h1 {
        font-size: 1.5rem !important;
    }
    
    .workflow-progress {
        padding: 1rem !important;
        overflow-x: auto !important;
    }
    
    .workflow-step-label {
        font-size: 0.625rem !important;
        max-width: 80px !important;
    }
    
    .workflow-step-circle {
        width: 32px !important;
        height: 32px !important;
        font-size: 0.75rem !important;
    }
    
    .pro-card {
        padding: 1rem !important;
    }
}

@media (max-width: 480px) {
    section[data-testid="stSidebar"] {
        width: 100% !important;
        min-width: 100% !important;
    }
    
    .pro-page-header h1 {
        font-size: 1.25rem !important;
    }
    
    .stButton > button {
        padding: 0.5rem 1rem !important;
        font-size: 0.875rem !important;
    }
}

/* Animations */
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes pulse {
    0%, 100% {
        opacity: 1;
    }
    50% {
        opacity: 0.7;
    }
}

.animate-fade-in {
    animation: fadeInUp 0.5s ease forwards;
}

.animate-pulse {
    animation: pulse 2s ease-in-out infinite;
}

/* Staggered animation delays */
.animate-delay-1 { animation-delay: 0.1s; }
.animate-delay-2 { animation-delay: 0.2s; }
.animate-delay-3 { animation-delay: 0.3s; }
.animate-delay-4 { animation-delay: 0.4s; }
.animate-delay-5 { animation-delay: 0.5s; }

/* Focus visible for accessibility */
*:focus-visible {
    outline: 2px solid var(--color-primary) !important;
    outline-offset: 2px !important;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--color-surface-variant);
}

::-webkit-scrollbar-thumb {
    background: var(--color-border);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--color-text-disabled);
}

/* Tooltip */
.stTooltipHoverTarget:hover + .stTooltip {
    background: var(--color-text-primary);
    color: var(--color-background);
    border-radius: var(--border-radius-sm);
    box-shadow: var(--shadow-lg);
}
</style>
"""

# ============================================================
# WORKFLOW STATE MANAGEMENT
# ============================================================

@dataclass
class WorkflowStep:
    """Represents a step in the guided research workflow."""
    id: int
    name: str
    description: str
    module_key: str
    icon: str
    requires_previous: bool = True
    auto_advance: bool = False

@dataclass
class WorkflowState:
    """Manages the state of the guided research workflow."""
    current_step: int = 1
    completed_steps: set = field(default_factory=set)
    step_data: dict = field(default_factory=dict)
    workflow_active: bool = False
    
    def can_access_step(self, step_id: int) -> bool:
        """Check if a step can be accessed."""
        if step_id == 1:
            return True
        return (step_id - 1) in self.completed_steps or step_id <= self.current_step
    
    def complete_step(self, step_id: int, data: dict = None):
        """Mark a step as completed."""
        self.completed_steps.add(step_id)
        if data:
            self.step_data[step_id] = data
        if step_id >= self.current_step:
            self.current_step = step_id + 1
    
    def get_step_status(self, step_id: int) -> str:
        """Get the status of a step."""
        if step_id in self.completed_steps:
            return "completed"
        elif step_id == self.current_step:
            return "active"
        elif self.can_access_step(step_id):
            return "pending"
        return "locked"

# Initialize workflow state
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = WorkflowState()

workflow_state = st.session_state.workflow_state

# Define the 13-step guided research workflow
WORKFLOW_STEPS = [
    WorkflowStep(1, "Disease Selection", "Select and analyze a disease of interest", "disease_analysis", "🎯"),
    WorkflowStep(2, "Gene Identification", "Identify disease-associated genes", "gene_identification", "🧬"),
    WorkflowStep(3, "VCF Analysis", "Upload and analyze variant call data", "vcf_analysis", "📊"),
    WorkflowStep(4, "AI Mutation Interpretation", "Interpret mutations with AI assistance", "mutation_interpretation", "🤖"),
    WorkflowStep(5, "Mutation-to-Target", "Map variants to potential drug targets", "mutation_target", "🔗"),
    WorkflowStep(6, "Protein Target Identification", "Identify and validate protein targets", "protein_target", "🎯"),
    WorkflowStep(7, "Pathway Analysis", "Analyze biological pathways", "pathway_analysis", "🔬"),
    WorkflowStep(8, "Protein Interaction Network", "Explore protein-protein interactions", "ppi_network", "🕸️"),
    WorkflowStep(9, "Druggability Analysis", "Assess target druggability", "druggability", "💊"),
    WorkflowStep(10, "Target Ranking", "Rank and prioritize targets", "target_ranking", "📈"),
    WorkflowStep(11, "Protein Structure Analysis", "Analyze 3D protein structures", "protein_structure", "🧱"),
    WorkflowStep(12, "Drug Discovery", "Discover and design drug candidates", "drug_discovery", "💊"),
    WorkflowStep(13, "Research Report", "Generate comprehensive research report", "research_report", "📄"),
]

# Module key to page name mapping
MODULE_TO_PAGE = {
    "disease_analysis": "Drug Discovery · Disease Analysis",
    "gene_identification": "Drug Discovery · Gene Identification",
    "vcf_analysis": "VCF analysis",
    "mutation_interpretation": "AI Mutation Interpretation",
    "mutation_target": "Drug Discovery · Mutation-to-Target",
    "protein_target": "Drug Discovery · Protein Target Identification",
    "pathway_analysis": "Drug Discovery · Pathway Analysis",
    "ppi_network": "Drug Discovery · Protein Interaction Network",
    "druggability": "Drug Discovery · Druggability Analysis",
    "target_ranking": "Drug Discovery · Target Ranking Dashboard",
    "protein_structure": "Drug Discovery · Protein Structure Analysis",
    "drug_discovery": "Drug Discovery · Drug Discovery Dashboard",
    "research_report": "Reports and roadmap",
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def render_workflow_progress():
    """Render the workflow progress tracker."""
    st.markdown("""
    <div class="workflow-progress animate-fade-in">
    """, unsafe_allow_html=True)
    
    cols = st.columns(len(WORKFLOW_STEPS))
    for i, (col, step) in enumerate(zip(cols, WORKFLOW_STEPS)):
        with col:
            status = workflow_state.get_step_status(step.id)
            step_class = f"workflow-step {status}"
            
            if status == "completed":
                circle_html = f'<div class="workflow-step-circle completed">{step.id}</div>'
            elif status == "active":
                circle_html = f'<div class="workflow-step-circle active">{step.id}</div>'
            else:
                circle_html = f'<div class="workflow-step-circle">{step.id}</div>'
            
            label_class = f"workflow-step-label {'active' if status == 'active' else ''}"
            
            st.markdown(f"""
            <div class="{step_class}">
                {circle_html}
                <div class="{label_class}">{step.name}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Progress bar
    progress = len(workflow_state.completed_steps) / len(WORKFLOW_STEPS)
    st.progress(progress, text=f"Workflow Progress: {len(workflow_state.completed_steps)}/{len(WORKFLOW_STEPS)} steps completed")

def render_workflow_navigation():
    """Render workflow navigation buttons."""
    current_step = workflow_state.current_step
    step = next((s for s in WORKFLOW_STEPS if s.id == current_step), None)
    
    if not step:
        return
    
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if current_step > 1:
            if st.button("← Previous Step", key="workflow_prev", use_container_width=True):
                workflow_state.current_step = max(1, current_step - 1)
                st.rerun()
    
    with col2:
        page_name = MODULE_TO_PAGE.get(step.module_key)
        if page_name and st.button("🔗 Open Module", key="workflow_open", type="primary", use_container_width=True):
            st.session_state["workspace_page"] = page_name
            st.rerun()
    
    with col3:
        if st.button("✓ Complete Step", key="workflow_complete", use_container_width=True):
            workflow_state.complete_step(current_step)
            st.success(f"Step {current_step} completed!")
            st.rerun()
    
    with col4:
        if st.button("💾 Save Progress", key="workflow_save_nav", use_container_width=True):
            st.session_state["workflow_saved_at"] = time.time()
            st.success("Progress saved!")

def render_main_dashboard():
    """Render the main dashboard with metrics and quick actions."""
    pro_page_header(
        "GeneAI Research Dashboard",
        "Your AI-powered biology research workspace. Track projects, analyze data, and discover insights.",
    )
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    # Calculate metrics
    try:
        samples = load_samples()
        sample_count = len(samples)
    except:
        sample_count = 0
    
    # Get workflow progress
    completed = len(workflow_state.completed_steps)
    active_projects = 1 if workflow_state.workflow_active else 0
    
    with col1:
        pro_metric_card("Research Projects", str(active_projects + 3), "+2 this week", "normal", "📁")
    with col2:
        pro_metric_card("Completed Analyses", str(completed + 5), f"+{completed} from workflow", "normal", "✅")
    with col3:
        pro_metric_card("Active Projects", str(active_projects + 2), "1 in progress", "normal", "🔄")
    with col4:
        pro_metric_card("Workflow Progress", f"{int(completed/len(WORKFLOW_STEPS)*100)}%", f"{completed}/{len(WORKFLOW_STEPS)} steps", "normal", "📊")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Quick Actions and Recent Activity
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        pro_section_header("Quick Actions", "Start a new analysis or continue your workflow")
        
        quick_actions = [
            ("🎯", "Disease Analysis", "Analyze disease mechanisms and associations", "disease_analysis"),
            ("🧬", "Gene Identification", "Identify disease-associated genes", "gene_identification"),
            ("📊", "VCF Analysis", "Upload and analyze variant data", "vcf_analysis"),
            ("🤖", "AI Mutation Interpretation", "AI-powered variant interpretation", "mutation_interpretation"),
            ("🔗", "Mutation-to-Target", "Map variants to drug targets", "mutation_target"),
            ("🎯", "Protein Target ID", "Identify therapeutic targets", "protein_target"),
            ("🔬", "Pathway Analysis", "Analyze biological pathways", "pathway_analysis"),
            ("🕸️", "PPI Network", "Explore protein interactions", "ppi_network"),
            ("💊", "Druggability Analysis", "Assess target druggability", "druggability"),
            ("📈", "Target Ranking", "Prioritize therapeutic targets", "target_ranking"),
            ("🧱", "Protein Structure", "3D structure analysis", "protein_structure"),
            ("💊", "Drug Discovery", "Design drug candidates", "drug_discovery"),
            ("📄", "Research Report", "Generate publication-ready reports", "research_report"),
            ("📚", "Literature Search", "Search PubMed and databases", "research_search"),
        ]
        
        # Render as grid
        for i in range(0, len(quick_actions), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                if i + j < len(quick_actions):
                    icon, title, desc, module = quick_actions[i + j]
                    with col:
                        if pro_card(title, desc, icon, "Open", f"quick_{module}"):
                            page_name = MODULE_TO_PAGE.get(module)
                            if page_name:
                                st.session_state["workspace_page"] = page_name
                                st.rerun()
    
    with col_right:
        pro_section_header("Guided Research Workflow", "Follow the 13-step drug discovery pipeline")
        
        # Workflow status
        if workflow_state.workflow_active:
            pro_status_badge("Workflow Active", "active")
        else:
            pro_status_badge("Workflow Inactive", "pending")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Mini workflow progress
        for step in WORKFLOW_STEPS[:5]:  # Show first 5
            status = workflow_state.get_step_status(step.id)
            badge_type = {"completed": "completed", "active": "active", "pending": "pending", "locked": "neutral"}[status]
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.caption(f"{step.icon} {step.name}")
            with col_b:
                pro_status_badge(status.title(), badge_type)
        
        if st.button("🚀 Start/Resume Workflow", key="start_workflow", use_container_width=True, type="primary"):
            workflow_state.workflow_active = True
            st.session_state["workspace_page"] = "Workflow"
            st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Recent activity
        pro_section_header("Recent Activity", "Your latest research actions")
        
        activities = [
            ("📊", "VCF Analysis completed", "2 hours ago"),
            ("🤖", "AI Mutation Interpretation", "5 hours ago"),
            ("🎯", "Disease Analysis: Breast Cancer", "1 day ago"),
            ("🧬", "Gene Identification: 42 genes", "2 days ago"),
            ("📄", "Report generated: Project Alpha", "3 days ago"),
        ]
        
        for icon, desc, time_str in activities:
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; 
                        background: var(--color-surface); border: 1px solid var(--color-border); 
                        border-radius: var(--border-radius); margin-bottom: 0.5rem;">
                <span style="font-size: 1.25rem;">{icon}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 500; color: var(--color-text-primary);">{desc}</div>
                    <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{time_str}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

def render_workflow_page():
    """Render the guided research workflow page."""
    pro_page_header(
        "Guided Research Workflow",
        "Follow the 13-step pipeline from disease selection to research report generation.",
        [("🚀 Start Workflow", "workflow_start"), ("💾 Save Progress", "workflow_save")]
    )
    
    # Workflow progress tracker
    render_workflow_progress()
    
    # Current step details
    current_step = workflow_state.current_step
    step = next((s for s in WORKFLOW_STEPS if s.id == current_step), None)
    
    if step:
        st.markdown(f"""
        <div class="pro-card animate-fade-in animate-delay-1">
            <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
                <div style="font-size: 3rem;">{step.icon}</div>
                <div>
                    <h2 style="margin: 0; color: var(--color-primary-light);">Step {step.id}: {step.name}</h2>
                    <p style="margin: 0.5rem 0 0; color: var(--color-text-secondary);">{step.description}</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Step requirements
        if step.id > 1:
            prev_step = WORKFLOW_STEPS[step.id - 2]
            prev_status = workflow_state.get_step_status(prev_step.id)
            if prev_status != "completed":
                st.warning(f"⚠️ Complete **Step {prev_step.id}: {prev_step.name}** before proceeding.")
        
        # Step-specific content preview
        st.markdown("### What you'll do in this step:")
        
        step_details = {
            1: "Select a disease from databases (Orphanet, OMIM, MONDO) or enter custom. Review disease ontology, prevalence, and known genetic associations.",
            2: "Identify genes associated with the disease using OpenTargets, DisGeNET, and GWAS Catalog. Filter by evidence score and association type.",
            3: "Upload VCF files (germline or somatic). Parse variants, filter by quality, and annotate with consequence predictions.",
            4: "AI-powered interpretation of variant pathogenicity, clinical significance, and functional impact using multiple prediction algorithms.",
            5: "Map interpreted variants to potential drug targets. Identify loss-of-function and gain-of-function candidates.",
            6: "Validate and characterize protein targets. Assess expression, localization, and structural features.",
            7: "Analyze pathway enrichment and biological context. Identify key signaling cascades and metabolic pathways.",
            8: "Explore protein-protein interaction networks. Identify network hubs, modules, and synthetic lethal partners.",
            9: "Evaluate target druggability using structural pockets, ligandability, and chemical tractability scores.",
            10: "Rank targets by multi-criteria scoring: genetic evidence, druggability, safety, and commercial potential.",
            11: "Analyze 3D protein structures. Identify binding pockets, allosteric sites, and perform docking simulations.",
            12: "Design and screen drug candidates. Virtual screening, de novo design, and lead optimization.",
            13: "Generate comprehensive research reports with methods, results, visualizations, and limitations.",
        }
        
        st.write(step_details.get(step.id, "Complete this step to advance the workflow."))
        
        # Navigation
        render_workflow_navigation()
        
        # All steps overview
        with st.expander("📋 View All Workflow Steps"):
            for s in WORKFLOW_STEPS:
                status = workflow_state.get_step_status(s.id)
                status_icons = {"completed": "✅", "active": "🔄", "pending": "⏳", "locked": "🔒"}
                col_a, col_b, col_c = st.columns([1, 4, 1])
                with col_a:
                    st.write(f"**{s.id}**")
                with col_b:
                    st.write(f"{s.icon} **{s.name}** — {s.description}")
                with col_c:
                    st.write(f"{status_icons[status]} {status.title()}")

# ============================================================
# APPLY THEME AND CUSTOM CSS
# ============================================================

# Apply Navy/Teal theme
navy_teal_config = ThemeConfig(
    mode=ThemeMode.DARK,
    color_scheme=ColorScheme.TEAL,
    font_size="medium",
    compact_mode=False,
    animations=True,
)
apply_theme(navy_teal_config)

# Inject custom design CSS
st.markdown(CUSTOM_DESIGN_CSS, unsafe_allow_html=True)

# ============================================================
# NEW SIDEBAR STRUCTURE
# ============================================================

with st.sidebar:
    # Logo and title
    st.markdown("""
    <div style="text-align: center; padding: 1.5rem 1rem 1rem; border-bottom: 1px solid var(--color-border);">
        <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🧬</div>
        <h1 style="margin: 0; font-size: 1.5rem; font-weight: 700; 
                    background: linear-gradient(90deg, var(--color-primary-light), var(--color-secondary-light));
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">
            GeneAI Research
        </h1>
        <p style="margin: 0.5rem 0 0; font-size: 0.75rem; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.05em;">
            AI-Powered Biology Workspace
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Theme selector (compact)
    with st.expander("🎨 Theme", expanded=False):
        render_theme_selector()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Search
    search_query = st.text_input("🔍 Search", placeholder="Find modules...", key="sidebar_search", label_visibility="collapsed")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Navigation Categories - NEW STRUCTURE
    NAV_CATEGORIES = {
        "🏠 WORKSPACE": [
            ("Overview", "Overview", "🏠"),
            ("Research Projects", "Research Projects", "📁"),
            ("Recent Activities", "Recent Activities", "🕐"),
        ],
        "🧬 BIOINFORMATICS": [
            ("Sequence Analysis", "Sequence analysis", "🧪"),
            ("VCF Analysis", "VCF analysis", "📊"),
            ("Gene Identification", "Drug Discovery · Gene Identification", "🧬"),
            ("AI Mutation Interpretation", "AI Mutation Interpretation", "🤖"),
        ],
        "🩺 DISEASE RESEARCH": [
            ("Disease Analysis", "Drug Discovery · Disease Analysis", "🎯"),
            ("Disease-Associated Genes", "Disease Research · Disease-Associated Genes", "🧬"),
            ("Mutation Analysis", "Disease Research · Mutation Analysis", "🔬"),
            ("Pathway Analysis", "Drug Discovery · Pathway Analysis", "🔬"),
        ],
        "💊 AI DRUG DISCOVERY": [
            ("Mutation-to-Target", "Drug Discovery · Mutation-to-Target", "🔗"),
            ("Protein Target Identification", "Drug Discovery · Protein Target Identification", "🎯"),
            ("Protein Interaction Network", "Drug Discovery · Protein Interaction Network", "🕸️"),
            ("Druggability Analysis", "Drug Discovery · Druggability Analysis", "💊"),
            ("Target Ranking", "Drug Discovery · Target Ranking Dashboard", "📈"),
            ("Protein Structure Analysis", "Drug Discovery · Protein Structure Analysis", "🧱"),
            ("Drug Discovery", "Drug Discovery · Drug Discovery Dashboard", "💊"),
            ("Drug-Target Prediction", "Drug Discovery · Drug-Target Prediction", "🎯"),
        ],
        "📚 RESEARCH": [
            ("Literature Analysis", "Research search", "🔍"),
            ("Research Papers", "Research Papers", "📄"),
            ("Research Reports", "Reports and roadmap", "📋"),
        ],
        "📊 ANALYTICS": [
            ("Research Dashboard", "Research Dashboard", "📊"),
            ("Saved Results", "Saved Results", "💾"),
            ("Analysis Statistics", "Analysis Statistics", "📈"),
        ],
        "⚙️ SETTINGS": [
            ("Professional UI", "Professional UI", "🎨"),
            ("Security & Privacy", "Security & Privacy", "🔒"),
            ("Performance", "Performance Optimization", "⚡"),
        ],
    }
    
    # Flatten all pages for search
    ALL_NAV_PAGES = {}
    for cat, pages in NAV_CATEGORIES.items():
        for label, page, icon in pages:
            ALL_NAV_PAGES[page] = (label, icon)
    
    # Determine selected page
    if search_query:
        filtered = {p: (l, i) for p, (l, i) in ALL_NAV_PAGES.items() 
                    if search_query.lower() in p.lower() or search_query.lower() in l.lower()}
        if filtered:
            page = st.radio("Search Results", list(filtered.keys()), 
                          format_func=lambda x: f"{filtered[x][1]} {filtered[x][0]}", 
                          key="search_page", label_visibility="collapsed")
        else:
            page = st.session_state.get("workspace_page", "Overview")
    else:
        # Categorized navigation
        selected_page = None
        
        for category, pages in NAV_CATEGORIES.items():
            with st.expander(category, expanded=True):
                for label, page_key, icon in pages:
                    is_active = st.session_state.get("workspace_page") == page_key
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(f"{icon} {label}", key=f"nav_{page_key}", 
                               use_container_width=True, type=btn_type):
                        selected_page = page_key
                        st.session_state["workspace_page"] = page_key
                        st.rerun()
        
        page = st.session_state.get("workspace_page", "Overview")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Workflow quick access
    if workflow_state.workflow_active:
        st.markdown("""
        <div style="padding: 1rem; background: rgba(13, 71, 161, 0.15); 
                    border: 1px solid var(--color-primary); border-radius: var(--border-radius); 
                    margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                <span style="font-size: 1.25rem;">🔄</span>
                <strong style="color: var(--color-primary-light);">Active Workflow</strong>
            </div>
            <div style="font-size: 0.875rem; color: var(--color-text-secondary);">
                Step {}/{} — {}
            </div>
        </div>
        """.format(
            workflow_state.current_step, 
            len(WORKFLOW_STEPS),
            WORKFLOW_STEPS[workflow_state.current_step - 1].name if workflow_state.current_step <= len(WORKFLOW_STEPS) else "Complete"
        ), unsafe_allow_html=True)
        
        if st.button("📋 Open Workflow", key="sidebar_workflow", use_container_width=True):
            st.session_state["workspace_page"] = "Workflow"
            st.rerun()
    
    st.divider()
    
    # Deployment Status
    config = get_config()
    if is_production() or is_streamlit_cloud():
        st.markdown("### 🚀 Deployment Status")
        env_label = "Streamlit Cloud" if is_streamlit_cloud() else "Production"
        st.markdown(f"""
        <div style="padding: 0.75rem; background: rgba(13, 71, 161, 0.1); 
                    border: 1px solid var(--color-primary); border-radius: var(--border-radius); 
                    margin-bottom: 0.5rem; font-size: 0.8rem;">
            <strong>Environment:</strong> {env_label}<br>
            <strong>API:</strong> {config.api_base_url}<br>
            <strong>Database:</strong> {'PostgreSQL (Neon)' if config.database.is_postgres else 'SQLite'}<br>
            <strong>Redis:</strong> {'Upstash' if config.redis.is_upstash else ('Local' if config.redis.is_configured else 'Disabled')}<br>
            <strong>ML Models:</strong> {'Enabled' if config.features.enable_mutation_ml else 'Disabled'}
        </div>
        """, unsafe_allow_html=True)
    
    st.caption(f"GeneAI Research v5.12.0 • {config.environment.title()} • Professional Scientific Workspace")

# ============================================================
# PAGE ROUTING - PRESERVE ALL EXISTING FUNCTIONALITY
# ============================================================

# Special pages
if page == "Workflow":
    render_workflow_page()

elif page == "Overview":
    render_main_dashboard()

elif page == "Sequence analysis":
    st.subheader("Sequence analysis")
    st.write("Analyze DNA, RNA, or protein sequences. Paste a sequence or upload FASTA/FASTQ.")
    kind = st.selectbox("Sequence type", ["DNA", "RNA", "Protein"], key="sequence_type")
    uploaded = st.file_uploader(
        "Upload sequence file",
        type=["fa", "fasta", "fna", "fastq", "fq", "txt"],
        key="sequence_file",
    )
    raw = st.text_area(
        "Or paste sequence or FASTA",
        height=160,
        placeholder=">sequence_1\nATGCGT...",
        key="sequence_text",
    )
    if st.button("Analyze sequence", type="primary", key="analyze_sequence"):
        try:
            records = (
                parse_sequence_file(uploaded.getvalue(), uploaded.name)
                if uploaded
                else parse_sequence_file(raw.encode("utf-8"), "pasted_sequence.txt")
            )
            results = [
                analyze_sequence(record["sequence"], kind) | {"record": record["id"]}
                for record in records
            ]
            for result in results:
                st.text(result["record"])
                x, y, z = st.columns(3)
                x.metric("Length", f"{result['length']:,}")
                y.metric("GC content", result.get("gc_content", "Not applicable"))
                z.metric("Ambiguous symbols", result["ambiguous_count"])
                st.json(result, expanded=False)
            st.download_button(
                "Download analysis JSON",
                json.dumps(results, indent=2),
                file_name="sequence_analysis.json",
                mime="application/json",
            )
        except (ValueError, UnicodeEncodeError) as exc:
            st.error(str(exc))

elif page == "VCF analysis":
    st.subheader("VCF variant analyzer")
    st.write(
        "Upload .vcf or .vcf.gz to inspect variant calls. "
        "This parser does not annotate clinical significance."
    )
    file = st.file_uploader(
        "VCF file",
        type=["vcf", "gz"],
        key="vcf_file",
        max_upload_size=500,
    )
    if file and st.button("Parse variants", type="primary", key="parse_vcf"):
        st.session_state.pop("vcf_stream_result", None)
        st.session_state.pop("vcf_variants", None)
        st.session_state.pop("vcf_meta", None)
        try:
            if file.size > 50 * 1024 * 1024:
                with st.spinner("Scanning the large VCF in streaming mode..."):
                    summary, meta, preview = summarize_vcf_stream(file, file.name)
                st.session_state["vcf_stream_result"] = {
                    "summary": summary,
                    "meta": meta,
                    "preview": preview,
                }
            else:
                variants, meta = parse_vcf(file.getvalue(), file.name)
                st.session_state["vcf_variants"] = variants
                st.session_state["vcf_meta"] = meta
        except (ValueError, OSError) as exc:
            st.error(str(exc))

    stream_result = st.session_state.get("vcf_stream_result")
    variants = st.session_state.get("vcf_variants", [])
    if stream_result:
        summary = stream_result["summary"]
        meta = stream_result["meta"]
        counts = summary["by_type"]
        x, y, z = st.columns(3)
        x.metric("Variant alleles scanned", f"{summary['variant_records']:,}")
        y.metric("SNPs", f"{counts.get('SNP', 0):,}")
        z.metric("INDELs", f"{counts.get('INDEL', 0):,}")
        with st.expander("VCF metadata"):
            st.json(meta)
        st.subheader("Variant counts by chromosome")
        chromosome_frame = pd.DataFrame(
            [
                {"chromosome": chromosome, "variant alleles": count}
                for chromosome, count in sorted(summary["by_chromosome"].items())
            ]
        )
        st.dataframe(
            chromosome_frame,
            hide_index=True,
            alt="Variant allele counts by chromosome",
        )
        st.caption("Preview of the first 1,000 variant alleles")
        preview_frame = pd.DataFrame(stream_result["preview"])
        st.dataframe(
            preview_frame,
            hide_index=True,
            alt="Preview of the first 1,000 VCF variant alleles",
        )
        st.download_button(
            "Download preview CSV",
            preview_frame.to_csv(index=False),
            "variants_preview.csv",
            "text/csv",
        )
        st.info(
            "The full VCF was scanned without loading all records into memory. "
            "The table and CSV contain the first 1,000 rows; full-dataset filtering and export "
            "are not available in large-file mode."
        )
    elif variants:
        meta = st.session_state.get("vcf_meta", {})
        x, y, z = st.columns(3)
        x.metric("Variant records", len(variants))
        y.metric("SNPs", sum(v["variant_type"] == "SNP" for v in variants))
        z.metric("INDELs", sum(v["variant_type"] == "INDEL" for v in variants))
        with st.expander("VCF metadata"):
            st.json(meta)
        frame = pd.DataFrame(variants)
        chromosomes = sorted(frame["chrom"].unique())
        chroms = st.multiselect("Chromosome filter", chromosomes, default=chromosomes)
        variant_types = ["SNP", "INDEL", "COMPLEX", "SYMBOLIC"]
        types = st.multiselect("Variant type", variant_types, default=variant_types)
        frame = frame[frame.chrom.isin(chroms) & frame.variant_type.isin(types)]
        st.dataframe(frame, hide_index=True, alt="Filtered VCF variant records")
        st.download_button(
            "Download filtered CSV",
            frame.to_csv(index=False),
            "variants.csv",
            "text/csv",
        )
        st.warning(
            "This parser does not perform variant annotation or pathogenicity prediction. "
            "Confirm findings against authoritative databases and the correct reference build."
        )

# Existing module pages - PRESERVE ALL FUNCTIONALITY
elif page == "AI Mutation Interpretation":
    render_mutation_interpretation_page()

elif page == "Mutation ML Dashboard":
    render_ml_dashboard_page()

elif page == "Drug Discovery · Disease Analysis":
    render_disease_analysis_page()

elif page == "Drug Discovery · Protein Target Identification":
    render_target_identification_page()

elif page == "Drug Discovery · Protein Structure Analysis":
    render_protein_structure_page()

elif page == "Autonomous Bioinformatics Agent":
    render_autonomous_agent_ui()

elif page == "Genomic Intelligence Engine":
    render_genomic_intelligence_dashboard()

elif page == "Protein Intelligence Engine":
    render_protein_intelligence_dashboard()

elif page == "Drug Design Engine":
    render_drug_design_ui()

elif page == "Molecular Docking Engine":
    render_molecular_docking_ui()

elif page == "Research search":
    st.subheader("Scientific literature search")
    st.write(
        "Search NCBI PubMed. Titles, dates, authors, and links come from the source API; "
        "the application does not generate summaries."
    )
    with st.form("pubmed_search"):
        query = st.text_input("Research topic", placeholder="e.g. CRISPR gene editing")
        limit = st.slider("Maximum papers", 5, 30, 10, key="pubmed_search_limit")
        submitted = st.form_submit_button("Search PubMed", type="primary")

    if submitted:
        st.session_state.pop("papers", None)
        st.session_state.pop("paper_query", None)
        if not query.strip():
            st.warning("Enter a search topic.")
        else:
            with st.spinner("Searching NCBI PubMed..."):
                try:
                    st.session_state["papers"] = search_pubmed(query.strip(), limit)
                    st.session_state["paper_query"] = query.strip()
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))

    papers = st.session_state.get("papers", [])
    if papers:
        st.caption(
            f"{len(papers)} results for \"{st.session_state.get('paper_query', '')}\" · "
            "Source: NCBI PubMed"
        )
        for paper in papers:
            with st.container(border=True):
                st.text(paper["title"])
                citation = (
                    f"PMID {paper['pmid']} · {paper.get('year') or 'Date not available'} · "
                    f"{paper.get('journal') or 'Journal not available'}"
                )
                st.text(citation)
                if paper.get("authors"):
                    st.text(paper["authors"])
                st.link_button("Open PubMed record", paper["url"])

elif page == "Lab samples":
    st.subheader("Laboratory sample register")
    st.write(
        "A local SQLite register for this installation. "
        "It is not a multi-user or production laboratory information system."
    )
    with st.form("sample_form", clear_on_submit=True):
        name = st.text_input("Sample name or description")
        material = st.selectbox(
            "Material",
            ["DNA", "RNA", "Protein", "Cell", "Tissue", "Compound", "Other"],
        )
        project = st.text_input("Project")
        notes = st.text_area("Notes")
        save = st.form_submit_button("Register sample", type="primary")

    if save:
        try:
            sample_id = add_sample(name, material, project, notes)
            st.success(f"Registered sample {sample_id}")
        except ValueError as exc:
            st.error(str(exc))
        except (sqlite3.Error, OSError) as exc:
            st.error(f"Could not save the sample: {exc}")

    try:
        data = load_samples()
    except (sqlite3.Error, OSError) as exc:
        st.error(f"Could not open the local sample register: {exc}")
        data = []
    if data:
        st.dataframe(
            pd.DataFrame(data),
            hide_index=True,
            alt="Local laboratory sample register",
        )
        st.download_button(
            "Export sample register",
            pd.DataFrame(data).to_csv(index=False),
            "lab_samples.csv",
            "text/csv",
        )
    else:
        st.caption("No samples registered yet.")

elif page == "Reports and roadmap":
    st.subheader("Reports and development roadmap")
    st.write(
        "Create a structured research note from analysis output. "
        "Reports label unvalidated findings and limitations."
    )
    with st.form("report_form"):
        title = st.text_input("Report title", "GeneAI Research analysis report")
        method = st.text_area("Methods", placeholder="Describe the dataset and methods used.")
        results = st.text_area("Results", placeholder="Paste or summarize observed results.")
        limitations = st.text_area(
            "Limitations",
            "Computational output requires expert review and experimental validation.",
        )
        create = st.form_submit_button("Build report")
    if create:
        content = build_report(title, method, results, limitations)
        st.markdown(content)
        st.download_button(
            "Download Markdown report",
            content,
            "geneai_report.md",
            "text/markdown",
        )
    with st.expander("Planned research modules"):
        st.markdown(
            "- NCBI, ClinVar, and Ensembl annotation with reference-build controls\n"
            "- Multi-omics and pathway analysis\n"
            "- Drug discovery integrations (ChEMBL, PubChem, docking tools)\n"
            "- Evidence-grounded research assistant with traceable citations\n"
            "- Authentication, team roles, protected storage, and deployment architecture"
        )
        st.caption(
            "These modules are roadmap items until implemented and connected to verified data sources."
        )

# Drug Discovery pages
elif page == "Drug Discovery · Gene Identification":
    render_gene_identification_page()

elif page == "Drug Discovery · Mutation-to-Target":
    render_mutation_target_page()

elif page == "Drug Discovery · Pathway Analysis":
    render_pathway_analysis_page()

elif page == "Drug Discovery · Protein Interaction Network":
    render_ppi_network_page()

elif page == "Drug Discovery · Druggability Analysis":
    render_druggability_analysis_page()

elif page == "Drug Discovery · Target Ranking Dashboard":
    render_target_ranking_page()

elif page == "Drug Discovery · Drug Discovery Dashboard":
    render_drug_discovery_dashboard()

elif page == "Drug Repurposing · AI Repurposing Engine":
    render_drug_repurposing_dashboard()

elif page == "Drug Discovery · Research Paper Analysis":
    render_research_analysis_dashboard()

elif page == "Drug Discovery · Drug-Target Prediction":
    render_drug_target_prediction_dashboard()

elif page == "Drug Discovery · ADMET Prediction":
    render_admet_dashboard()

elif page == "Drug Discovery · Disease-Gene-Pathway Network":
    render_dgp_dashboard()

elif page == "Drug Discovery · Drug Safety & Toxicity":
    render_drug_safety_dashboard()

elif page == "Drug Discovery · Integrated Precision Drug Discovery":
    render_integrated_precision_dashboard()

# AI & Intelligence pages
elif page == "AI Research Intelligence":
    render_ai_research_intelligence_dashboard()

elif page == "Biotech Research Assistant":
    render_biotech_assistant()

elif page == "Multi-Agent Research System":
    render_multi_agent()

elif page == "Unified Knowledge Database":
    render_unified_knowledge()

elif page == "Research Automation":
    render_research_automation()

elif page == "Autonomous Bioinformatics Agent":
    render_autonomous_agent_ui()

# Platform pages
elif page == "Multi-User Research Platform":
    render_multi_user()

elif page == "Cloud Integration":
    render_cloud_integration()

elif page == "REST API":
    render_rest_api()

# Settings pages
elif page == "Professional UI":
    render_professional_ui()

elif page == "Security & Privacy":
    render_security()

elif page == "Performance Optimization":
    render_performance()

# Placeholder pages for new navigation items
elif page == "Research Projects":
    st.subheader("Research Projects")
    pro_empty_state("📁", "Research Projects", "Project management interface coming soon.", "Create Project", "create_project")

elif page == "Recent Activities":
    st.subheader("Recent Activities")
    st.caption("Activity feed showing recent analyses, workflows, and reports.")

elif page == "Research Papers":
    st.subheader("Research Papers")
    pro_empty_state("📄", "Research Papers", "Paper management and annotation interface coming soon.")

elif page == "Research Dashboard":
    st.subheader("Research Dashboard")
    st.caption("Analytics dashboard with project metrics, usage statistics, and insights.")

elif page == "Saved Results":
    st.subheader("Saved Results")
    pro_empty_state("💾", "Saved Results", "Browse and manage saved analysis results.")

elif page == "Analysis Statistics":
    st.subheader("Analysis Statistics")
    st.caption("Statistical overview of all analyses performed.")

else:
    # Default to overview
    render_main_dashboard()





    