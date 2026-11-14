"""Streamlit UI for AI Biomarker Discovery Engine (Phase 4.10)."""
from __future__ import annotations

import io
import json
import uuid
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import session_state as ss

from geneai.biomarker_discovery.data_integration import (
    fetch_ensembl_gene,
    fetch_geo_dataset,
    fetch_ncbi_gene,
    fetch_uniprot_biomarker_info,
    search_geo_datasets,
)
from geneai.biomarker_discovery.database import (
    clear_bd_analysis_run,
    get_bd_analysis_run,
    get_bd_candidates,
    get_bd_db_version,
    get_bd_differential_expression,
    get_bd_feature_ranking,
    get_bd_model_performance,
    get_bd_roc_curves,
    get_recent_bd_runs,
    search_bd_runs,
    store_bd_analysis_run,
    store_bd_candidates,
    store_bd_differential_expression,
    store_bd_feature_ranking,
    store_bd_model_performance,
    store_bd_roc_curves,
)
from geneai.biomarker_discovery.ml_engine import (
    BiomarkerDiscoveryEngine,
    run_biomarker_discovery,
)
from geneai.config import APP_NAME

def render_biomarker_discovery_dashboard() -> None:
    """Render the Biomarker Discovery dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - Biomarker Discovery",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🧬 AI Biomarker Discovery Engine")
    st.caption("Identify diagnostic, prognostic, and therapeutic biomarkers from gene expression data")
    
    # Initialize session state
    if "bd_results" not in ss:
        ss.bd_results = {}
    if "bd_current_run" not in ss:
        ss.bd_current_run = None
    if "bd_uploaded_data" not in ss:
        ss.bd_uploaded_data = None
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Data Input")
        input_method = st.radio(
            "Input Method",
            ["Upload Expression Matrix", "GEO Dataset", "Manual Entry"],
            key="bd_input_method",
        )
        
        st.divider()
        st.header("⚙️ Analysis Parameters")
        
        biomarker_type = st.selectbox(
            "Biomarker Type",
            ["diagnostic", "prognostic", "therapeutic"],
            key="bd_biomarker_type",
        )
        
        feature_selection = st.selectbox(
            "Feature Selection",
            ["mutual_info", "f_classif", "model_based"],
            key="bd_feature_selection",
        )
        
        n_features = st.number_input(
            "Max Features to Select",
            10, 500, 50, 10,
            key="bd_n_features",
        )
        
        cv_folds = st.number_input(
            "CV Folds",
            3, 10, 5, 1,
            key="bd_cv_folds",
        )
        
        test_size = st.slider(
            "Test Set Size",
            0.1, 0.4, 0.2, 0.05,
            key="bd_test_size",
        )
        
        save_to_db = st.checkbox("Save to Database", value=True, key="bd_save_db")
        
        st.divider()
        st.header("📈 Recent Analyses")
        recent = get_recent_bd_runs(10)
        for run in recent:
            if st.button(f"{run.get('dataset_name', 'Unnamed')} ({run['created_at']:.0f})", key=f"recent_{run['run_id']}"):
                _load_bd_run(run["run_id"])
    
    # Main content
    if input_method == "Upload Expression Matrix":
        render_upload_input(biomarker_type, feature_selection, n_features, cv_folds, test_size, save_to_db)
    elif input_method == "GEO Dataset":
        render_geo_input(biomarker_type, feature_selection, n_features, cv_folds, test_size, save_to_db)
    elif input_method == "Manual Entry":
        render_manual_input(biomarker_type, feature_selection, n_features, cv_folds, test_size, save_to_db)
    
    # Display results if available
    if ss.bd_current_run and ss.bd_current_run in ss.bd_results:
        display_bd_results(ss.bd_current_run, ss.bd_results[ss.bd_current_run])


def render_upload_input(
    biomarker_type: str,
    feature_selection: str,
    n_features: int,
    cv_folds: int,
    test_size: float,
    save_to_db: bool,
) -> None:
    """Render file upload interface."""
    st.subheader("📤 Upload Expression Matrix")
    st.write("Upload a CSV/TSV file with samples as rows and genes as columns. Include a target column for classification.")
    
    uploaded_file = st.file_uploader(
        "Expression Matrix",
        type=["csv", "tsv", "txt"],
        key="bd_upload_file",
    )
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".tsv") or uploaded_file.name.endswith(".txt"):
                df = pd.read_csv(uploaded_file, sep="\t")
            else:
                df = pd.read_csv(uploaded_file)
            
            st.success(f"Loaded {df.shape[0]} samples × {df.shape[1]} features")
            
            # Show preview
            with st.expander("Data Preview"):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Target column selection
            target_col = st.selectbox(
                "Target Column (class labels)",
                df.columns.tolist(),
                key="bd_target_col",
            )
            
            # Feature columns (exclude target)
            feature_cols = [c for c in df.columns if c != target_col]
            
            st.info(f"Features: {len(feature_cols)} | Target classes: {df[target_col].nunique()}")
            
            # Show class distribution
            class_dist = df[target_col].value_counts()
            st.write("**Class Distribution:**")
            st.bar_chart(class_dist)
            
            if st.button("🔬 Run Biomarker Discovery", type="primary", use_container_width=True, key="bd_run_upload"):
                X = df[feature_cols]
                y = df[target_col]
                run_bd_analysis(X, y, biomarker_type, feature_selection, n_features, cv_folds, test_size, save_to_db, uploaded_file.name)
                
        except Exception as e:
            st.error(f"Failed to load file: {e}")


def render_geo_input(
    biomarker_type: str,
    feature_selection: str,
    n_features: int,
    cv_folds: int,
    test_size: float,
    save_to_db: bool,
) -> None:
    """Render GEO dataset search interface."""
    st.subheader("🔍 GEO Dataset Search")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input(
            "Search GEO",
            placeholder="e.g., breast cancer, lung cancer GSE12345",
            key="bd_geo_query",
        )
    with col2:
        st.write("")
        search_btn = st.button("🔍 Search", type="primary", use_container_width=True, key="bd_geo_search")
    
    if search_btn and query.strip():
        with st.spinner("Searching GEO..."):
            datasets = search_geo_datasets(query.strip(), max_results=20)
        
        if datasets:
            st.session_state["bd_geo_results"] = datasets
            st.success(f"Found {len(datasets)} datasets")
        else:
            st.warning("No datasets found")
    
    # Display search results
    if "bd_geo_results" in st.session_state:
        datasets = st.session_state["bd_geo_results"]
        for i, ds in enumerate(datasets):
            with st.expander(f"{ds.title} ({ds.accession})"):
                cols = st.columns([2, 1, 1])
                cols[0].write(f"**Organism:** {ds.organism}")
                cols[0].write(f"**Type:** {ds.experiment_type}")
                cols[0].write(f"**Samples:** {ds.samples}")
                cols[0].write(f"**Platform:** {ds.platform}")
                if ds.pubmed_id:
                    cols[0].write(f"**PubMed:** {ds.pubmed_id}")
                
                if cols[1].button("View Details", key=f"geo_detail_{i}"):
                    st.json(ds.__dict__)
                
                if cols[2].button("Load for Analysis", key=f"geo_load_{i}"):
                    st.info("GEO expression data loading requires supplementary files. Please download from GEO and upload via 'Upload Expression Matrix'.")


def render_manual_input(
    biomarker_type: str,
    feature_selection: str,
    n_features: int,
    cv_folds: int,
    test_size: float,
    save_to_db: bool,
) -> None:
    """Render manual data entry interface."""
    st.subheader("✏️ Manual Data Entry")
    st.write("Enter a small expression matrix manually for quick testing.")
    
    # Example data
    if st.button("Load Example Data", key="bd_load_example"):
        example_data = """Gene1,Gene2,Gene3,Gene4,Gene5,Target
2.3,1.1,0.5,3.2,1.8,0
2.1,1.3,0.7,3.0,1.9,0
2.5,1.0,0.4,3.5,2.0,0
1.8,2.2,1.5,1.2,0.8,1
2.0,2.5,1.7,1.0,0.9,1
1.9,2.3,1.6,1.1,1.0,1"""
        ss.bd_manual_data = example_data
    
    manual_text = st.text_area(
        "CSV Data (include header row with Target column)",
        value=ss.get("bd_manual_data", ""),
        height=200,
        key="bd_manual_input",
    )
    
    if st.button("🔬 Analyze Manual Data", type="primary", key="bd_run_manual"):
        try:
            df = pd.read_csv(io.StringIO(manual_text))
            target_col = "Target" if "Target" in df.columns else df.columns[-1]
            feature_cols = [c for c in df.columns if c != target_col]
            X = df[feature_cols]
            y = df[target_col]
            run_bd_analysis(X, y, biomarker_type, feature_selection, n_features, cv_folds, test_size, save_to_db, "manual_entry")
        except Exception as e:
            st.error(f"Failed to parse data: {e}")


def run_bd_analysis(
    X: pd.DataFrame,
    y: pd.Series,
    biomarker_type: str,
    feature_selection: str,
    n_features: int,
    cv_folds: int,
    test_size: float,
    save_to_db: bool,
    dataset_name: str,
) -> None:
    """Run biomarker discovery analysis."""
    run_id = str(uuid.uuid4())[:8]
    
    with st.spinner("Running biomarker discovery..."):
        try:
            engine = BiomarkerDiscoveryEngine(
                test_size=test_size,
                cv_folds=cv_folds,
                random_state=42,
            )
            
            result = engine.run_discovery(
                X, y,
                feature_selection=feature_selection,
                n_features=n_features,
                biomarker_type=biomarker_type,
            )
            
            # Store in session
            ss.bd_results[run_id] = {
                "result": result,
                "X": X,
                "y": y,
                "dataset_name": dataset_name,
            }
            ss.bd_current_run = run_id
            
            # Save to database
            if save_to_db:
                save_bd_to_db(run_id, dataset_name, result, engine)
            
            st.success("Analysis complete!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            import traceback
            st.code(traceback.format_exc())


def save_bd_to_db(run_id: str, dataset_name: str, result, engine: BiomarkerDiscoveryEngine) -> None:
    """Save biomarker discovery results to database."""
    try:
        store_bd_analysis_run(
            run_id,
            dataset_name,
            result.dataset_info,
            result.best_model,
            result.best_model_auc,
            result.cross_validation,
            result.warnings,
        )
        
        # Convert candidates to dict
        candidates_data = []
        for c in result.candidates:
            candidates_data.append({
                "gene_symbol": c.gene_symbol,
                "feature_importance": c.feature_importance,
                "p_value": c.p_value,
                "fold_change": c.fold_change,
                "auc_score": c.auc_score,
                "cv_auc_mean": c.cv_auc_mean,
                "cv_auc_std": c.cv_auc_std,
                "expression_stats": c.expression_stats,
                "biomarker_type": c.biomarker_type,
                "confidence": c.confidence,
                "validation_status": c.validation_status,
            })
        store_bd_candidates(run_id, candidates_data)
        
        # Model performance
        store_bd_model_performance(run_id, {
            name: {
                "cv_auc_mean": r.get("cv_auc_mean", 0),
                "cv_auc_std": r.get("cv_auc_std", 0),
                "cv_scores": r.get("cv_scores", []),
                "test_auc": 0,
            }
            for name, r in result.cross_validation.items()
        })
        
        # ROC curves
        store_bd_roc_curves(run_id, result.roc_curves)
        
        # Feature ranking
        store_bd_feature_ranking(run_id, result.feature_ranking)
        
        # Differential expression (would need to re-run or store from engine)
        # For now, skip as it's computed internally
        
    except Exception as e:
        st.warning(f"Database save failed: {e}")


def _load_bd_run(run_id: str) -> None:
    """Load a previous run from database."""
    run = get_bd_analysis_run(run_id)
    if run:
        st.session_state["bd_current_run"] = run_id
        st.info(f"Loaded run {run_id}. Re-run analysis to view full results.")


def display_bd_results(run_id: str, data: dict[str, Any]) -> None:
    """Display biomarker discovery results."""
    result = data["result"]
    X = data["X"]
    y = data["y"]
    dataset_name = data.get("dataset_name", "Unknown")
    
    st.divider()
    
    # Header
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Samples", len(y))
    with col2:
        st.metric("Features", X.shape[1])
    with col3:
        st.metric("Best Model", result.best_model)
    with col4:
        st.metric("Best AUC", f"{result.best_model_auc:.3f}")
    
    st.caption(f"Dataset: {dataset_name} | Biomarker Type: {result.candidates[0].biomarker_type if result.candidates else 'N/A'}")
    
    # Tabs
    tabs = st.tabs([
        "🏆 Top Biomarkers",
        "📊 Model Performance",
        "📈 ROC Curves",
        "🎯 Feature Ranking",
        "📋 Differential Expression",
        "⚠️ Warnings & Limitations",
        "📄 Reports",
    ])
    
    with tabs[0]:
        render_biomarkers_tab(result)
    
    with tabs[1]:
        render_model_performance_tab(result)
    
    with tabs[2]:
        render_roc_curves_tab(result)
    
    with tabs[3]:
        render_feature_ranking_tab(result)
    
    with tabs[4]:
        render_differential_expression_tab(result)
    
    with tabs[5]:
        render_warnings_tab(result)
    
    with tabs[6]:
        render_reports_tab(run_id, result, dataset_name)


def render_biomarkers_tab(result: Any) -> None:
    """Render top biomarkers table."""
    st.subheader("Top Biomarker Candidates")
    
    if not result.candidates:
        st.info("No biomarker candidates found.")
        return
    
    # Confidence filter
    conf_filter = st.multiselect(
        "Filter by Confidence",
        ["high", "medium", "low"],
        default=["high", "medium", "low"],
        key="bd_conf_filter",
    )
    
    filtered = [c for c in result.candidates if c.confidence in conf_filter]
    
    if not filtered:
        st.info("No candidates match the confidence filter.")
        return
    
    # Display table
    biomarker_data = []
    for i, c in enumerate(filtered):
        biomarker_data.append({
            "Rank": i + 1,
            "Gene": c.gene_symbol,
            "Importance": f"{c.feature_importance:.4f}",
            "P-value": f"{c.p_value:.2e}",
            "Log2 FC": f"{c.fold_change:.3f}",
            "AUC": f"{c.auc_score:.3f}",
            "CV AUC": f"{c.cv_auc_mean:.3f}±{c.cv_auc_std:.3f}",
            "Confidence": c.confidence.capitalize(),
            "Status": c.validation_status.capitalize(),
            "Type": c.biomarker_type.capitalize(),
        })
    
    st.dataframe(biomarker_data, use_container_width=True, hide_index=True)
    
    # Download
    df = pd.DataFrame(biomarker_data)
    csv = df.to_csv(index=False)
    st.download_button(
        "⬇️ Download Biomarkers CSV",
        csv,
        "biomarker_candidates.csv",
        "text/csv",
    )
    
    # Visualization
    st.subheader("Biomarker Importance")
    top_20 = filtered[:20]
    fig = go.Figure(go.Bar(
        x=[c.feature_importance for c in reversed(top_20)],
        y=[c.gene_symbol for c in reversed(top_20)],
        orientation='h',
        marker_color=['#e74c3c' if c.confidence == 'high' else '#f39c12' if c.confidence == 'medium' else '#3498db' for c in reversed(top_20)],
    ))
    fig.update_layout(
        title="Top 20 Biomarkers by Feature Importance",
        xaxis_title="Mean Feature Importance",
        yaxis_title="Gene",
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_model_performance_tab(result: Any) -> None:
    """Render model performance comparison."""
    st.subheader("Cross-Validation Performance")
    
    cv_data = []
    for model_name, metrics in result.cross_validation.items():
        cv_data.append({
            "Model": model_name,
            "Mean AUC": f"{metrics['mean_auc']:.4f}",
            "Std AUC": f"{metrics['std_auc']:.4f}",
            "CV Scores": ", ".join(f"{s:.3f}" for s in metrics['scores']),
        })
    
    df = pd.DataFrame(cv_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Bar chart
    fig = go.Figure(go.Bar(
        x=[d["Model"] for d in cv_data],
        y=[float(d["Mean AUC"]) for d in cv_data],
        error_y=dict(type='data', array=[float(d["Std AUC"]) for d in cv_data], visible=True),
        marker_color='#2e75b6',
    ))
    fig.update_layout(
        title="Model Performance Comparison (CV AUC)",
        xaxis_title="Model",
        yaxis_title="AUC",
        yaxis=dict(range=[0.5, 1.0]),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_roc_curves_tab(result: Any) -> None:
    """Render ROC curves."""
    st.subheader("ROC Curves")
    
    if not result.roc_curves:
        st.info("No ROC curves available.")
        return
    
    fig = go.Figure()
    
    # Add diagonal reference line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode='lines',
        line=dict(dash='dash', color='gray'),
        showlegend=False,
    ))
    
    for model_name, curve in result.roc_curves.items():
        fig.add_trace(go.Scatter(
            x=curve["fpr"],
            y=curve["tpr"],
            mode='lines',
            name=f"{model_name} (AUC={curve['auc']:.3f})",
            line=dict(width=2),
        ))
    
    fig.update_layout(
        title="ROC Curves Comparison",
        xaxis_title="False Positive Rate",
        yaxis_title="True Positive Rate",
        xaxis=dict(range=[0, 1]),
        yaxis=dict(range=[0, 1]),
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # AUC table
    auc_data = [{"Model": k, "Test AUC": f"{v['auc']:.4f}"} for k, v in result.roc_curves.items()]
    st.dataframe(auc_data, use_container_width=True, hide_index=True)


def render_feature_ranking_tab(result: Any) -> None:
    """Render feature ranking."""
    st.subheader("Feature Importance Ranking")
    
    if not result.feature_ranking:
        st.info("No feature ranking available.")
        return
    
    ranking_data = []
    for i, item in enumerate(result.feature_ranking[:50]):
        ranking_data.append({
            "Rank": i + 1,
            "Gene": item["gene"],
            "Mean Importance": f"{item['mean_importance']:.4f}",
            "Std": f"{item['std_importance']:.4f}",
            "Median": f"{item['median_importance']:.4f}",
            "Max": f"{item['max_importance']:.4f}",
            "Models Agreeing": item["models_agreeing"],
        })
    
    st.dataframe(ranking_data, use_container_width=True, hide_index=True)
    
    # Download
    df = pd.DataFrame(ranking_data)
    csv = df.to_csv(index=False)
    st.download_button(
        "⬇️ Download Ranking CSV",
        csv,
        "feature_ranking.csv",
        "text/csv",
    )


def render_differential_expression_tab(result: Any) -> None:
    """Render differential expression analysis."""
    st.subheader("Differential Expression (Top Biomarkers)")
    
    if not result.candidates:
        st.info("Run analysis with expression data to see differential expression.")
        return
    
    # Show for top 10 candidates
    de_data = []
    for c in result.candidates[:15]:
        stats = c.expression_stats
        de_data.append({
            "Gene": c.gene_symbol,
            "Mean (Class 0)": f"{stats.get('mean_class_0', 0):.3f}",
            "Mean (Class 1)": f"{stats.get('mean_class_1', 0):.3f}",
            "Log2 FC": f"{c.fold_change:.3f}",
            "P-value": f"{c.p_value:.2e}",
            "Confidence": c.confidence.capitalize(),
        })
    
    st.dataframe(de_data, use_container_width=True, hide_index=True)
    
    # Volcano plot data (mock for display)
    st.caption("Volcano plot would show -log10(p-value) vs Log2 Fold Change for all genes")


def render_warnings_tab(result: Any) -> None:
    """Render warnings and limitations."""
    st.subheader("Warnings & Limitations")
    
    if result.warnings:
        for w in result.warnings:
            st.warning(w)
    else:
        st.info("No warnings generated.")
    
    st.divider()
    st.subheader("Standard Limitations")
    limitations = [
        "Computational biomarker predictions require experimental validation.",
        "Results depend on data quality, sample size, and class balance.",
        "Cross-validation AUC estimates may be optimistic for small datasets.",
        "Feature importance rankings can vary between models and random seeds.",
        "Biomarkers identified here are research candidates, not clinically validated.",
        "Missing value imputation and feature selection may introduce bias.",
        "Class imbalance can affect model performance and biomarker ranking.",
        "Results should be validated in independent cohorts before clinical consideration.",
    ]
    for lim in limitations:
        st.write(f"• {lim}")


def render_reports_tab(run_id: str, result: Any, dataset_name: str) -> None:
    """Render report generation."""
    st.subheader("Generate Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", use_container_width=True, key=f"bd_pdf_{run_id}"):
            pdf_bytes = generate_bd_pdf_report(result, run_id, dataset_name)
            st.download_button(
                "⬇️ Download PDF",
                pdf_bytes,
                f"biomarker_report_{run_id}.pdf",
                "application/pdf",
                use_container_width=True,
            )
    
    with col2:
        if st.button("📊 Generate CSV Report", use_container_width=True, key=f"bd_csv_{run_id}"):
            csv_str = generate_bd_csv_report(result, run_id, dataset_name)
            st.download_button(
                "⬇️ Download CSV",
                csv_str,
                f"biomarker_report_{run_id}.csv",
                "text/csv",
                use_container_width=True,
            )
    
    with col3:
        if st.button("📋 Generate JSON Report", use_container_width=True, key=f"bd_json_{run_id}"):
            json_data = generate_bd_json_report(result, run_id, dataset_name)
            st.download_button(
                "⬇️ Download JSON",
                json.dumps(json_data, indent=2),
                f"biomarker_report_{run_id}.json",
                "application/json",
                use_container_width=True,
            )
    
    st.divider()
    st.write("**JSON Preview**")
    st.json(generate_bd_json_report(result, run_id, dataset_name), expanded=False)


def generate_bd_pdf_report(result: Any, run_id: str, dataset_name: str) -> bytes:
    """Generate PDF report for biomarker discovery."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    )
    from datetime import datetime
    import io
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []
    
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=18, spaceAfter=6, alignment=TA_CENTER, textColor=colors.HexColor("#1f4e79"))
    heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#1f4e79"))
    normal_style = styles["Normal"]
    
    elements.append(Spacer(1, 30*mm))
    elements.append(Paragraph("AI Biomarker Discovery Report", title_style))
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(f"Run ID: {run_id}", styles["Normal"]))
    elements.append(Paragraph(f"Dataset: {dataset_name}", styles["Normal"]))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    elements.append(Spacer(1, 10*mm))
    
    # Summary
    summary_data = [
        ["Metric", "Value"],
        ["Best Model", result.best_model],
        ["Best Model AUC", f"{result.best_model_auc:.4f}"],
        ["Biomarker Type", result.candidates[0].biomarker_type if result.candidates else "N/A"],
        ["Total Candidates", str(len(result.candidates))],
        ["High Confidence", str(sum(1 for c in result.candidates if c.confidence == "high"))],
        ["Medium Confidence", str(sum(1 for c in result.candidates if c.confidence == "medium"))],
        ["Low Confidence", str(sum(1 for c in result.candidates if c.confidence == "low"))],
    ]
    t = Table(summary_data, colWidths=[60*mm, 60*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")])]))
    elements.append(t)
    elements.append(PageBreak())
    
    # Candidates
    elements.append(Paragraph("Top Biomarker Candidates", heading_style))
    cand_data = [["Rank", "Gene", "Importance", "P-value", "Log2FC", "AUC", "CV AUC", "Confidence", "Status"]]
    for i, c in enumerate(result.candidates[:30]):
        cand_data.append([str(i+1), c.gene_symbol, f"{c.feature_importance:.4f}", f"{c.p_value:.2e}", f"{c.fold_change:.3f}", f"{c.auc_score:.3f}", f"{c.cv_auc_mean:.3f}", c.confidence.capitalize(), c.validation_status.capitalize()])
    t = Table(cand_data, colWidths=[10*mm, 18*mm, 18*mm, 18*mm, 18*mm, 15*mm, 18*mm, 18*mm, 18*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]), ("FONTSIZE", (0,0), (-1,-1), 8)]))
    elements.append(t)
    
    # Limitations
    elements.append(PageBreak())
    elements.append(Paragraph("Limitations", heading_style))
    for lim in [
        "Computational biomarker predictions require experimental validation.",
        "Results depend on data quality, sample size, and class balance.",
        "Cross-validation AUC estimates may be optimistic for small datasets.",
        "Feature importance rankings can vary between models and random seeds.",
        "Biomarkers identified here are research candidates, not clinically validated.",
    ]:
        elements.append(Paragraph(f"• {lim}", normal_style))
    
    doc.build(elements)
    return buffer.getvalue()


def generate_bd_csv_report(result: Any, run_id: str, dataset_name: str) -> str:
    """Generate CSV report for biomarker discovery."""
    import io
    from datetime import datetime
    
    output = io.StringIO()
    writer = __import__('csv').writer(output)
    
    writer.writerow(["Biomarker Discovery Report"])
    writer.writerow(["Run ID", run_id])
    writer.writerow(["Dataset", dataset_name])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Best Model", result.best_model])
    writer.writerow(["Best Model AUC", f"{result.best_model_auc:.4f}"])
    writer.writerow([])
    
    writer.writerow(["Biomarker Candidates"])
    writer.writerow(["Rank", "Gene", "Importance", "P-value", "Log2FC", "AUC", "CV_AUC_Mean", "CV_AUC_Std", "Confidence", "Validation_Status", "Type"])
    for i, c in enumerate(result.candidates):
        writer.writerow([i+1, c.gene_symbol, f"{c.feature_importance:.6f}", f"{c.p_value:.6e}", f"{c.fold_change:.6f}", f"{c.auc_score:.6f}", f"{c.cv_auc_mean:.6f}", f"{c.cv_auc_std:.6f}", c.confidence, c.validation_status, c.biomarker_type])
    writer.writerow([])
    
    writer.writerow(["Model Performance"])
    writer.writerow(["Model", "Mean_AUC", "Std_AUC"])
    for name, metrics in result.cross_validation.items():
        writer.writerow([name, f"{metrics['mean_auc']:.6f}", f"{metrics['std_auc']:.6f}"])
    writer.writerow([])
    
    writer.writerow(["Feature Ranking"])
    writer.writerow(["Rank", "Gene", "Mean_Importance", "Std_Importance", "Median_Importance", "Max_Importance", "Models_Agreeing"])
    for i, item in enumerate(result.feature_ranking):
        writer.writerow([i+1, item["gene"], f"{item['mean_importance']:.6f}", f"{item['std_importance']:.6f}", f"{item['median_importance']:.6f}", f"{item['max_importance']:.6f}", item["models_agreeing"]])
    
    return output.getvalue()


def generate_bd_json_report(result: Any, run_id: str, dataset_name: str) -> dict[str, Any]:
    """Generate JSON report for biomarker discovery."""
    from datetime import datetime
    
    return {
        "metadata": {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "generated_at": datetime.now().isoformat(),
            "best_model": result.best_model,
            "best_model_auc": result.best_model_auc,
        },
        "candidates": [
            {
                "rank": i+1,
                "gene_symbol": c.gene_symbol,
                "feature_importance": c.feature_importance,
                "p_value": c.p_value,
                "fold_change": c.fold_change,
                "auc_score": c.auc_score,
                "cv_auc_mean": c.cv_auc_mean,
                "cv_auc_std": c.cv_auc_std,
                "expression_stats": c.expression_stats,
                "biomarker_type": c.biomarker_type,
                "confidence": c.confidence,
                "validation_status": c.validation_status,
            }
            for i, c in enumerate(result.candidates)
        ],
        "model_performance": result.cross_validation,
        "roc_curves": result.roc_curves,
        "feature_ranking": result.feature_ranking,
        "dataset_info": result.dataset_info,
        "warnings": result.warnings,
    }


if __name__ == "__main__":
    render_biomarker_discovery_dashboard()