"""Streamlit UI for Drug Safety & Toxicity Prediction (Phase 4.11)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import session_state as ss

from geneai.config import APP_NAME
from geneai.drug_safety.data_integration import (
    ADMETlabPrediction,
    ChEMBLToxicity,
    PubChemToxicity,
    SafetyProfile,
    build_safety_profile,
    calculate_toxicity_relevant_properties,
    fetch_admetlab_prediction,
    fetch_chembl_toxicity,
    fetch_pubchem_toxicity,
)
from geneai.drug_safety.database import (
    clear_ds_analysis_run,
    get_ds_admetlab_prediction,
    get_ds_analysis_run,
    get_ds_chembl_toxicity,
    get_ds_db_version,
    get_ds_ml_predictions,
    get_ds_models,
    get_ds_pubchem_toxicity,
    get_recent_ds_runs,
    search_ds_runs,
    store_ds_admetlab_prediction,
    store_ds_analysis_run,
    store_ds_chembl_toxicity,
    store_ds_drug_interactions,
    store_ds_ml_predictions,
    store_ds_model_metadata,
    store_ds_pubchem_toxicity,
)
from geneai.drug_safety.ml_models import (
    TOXICITY_ENDPOINTS,
    ToxicityModelManager,
    load_pretrained_models,
)
from geneai.drug_safety.report_generator import (
    generate_ds_csv_report,
    generate_ds_json_report,
    generate_ds_pdf_report,
)

def render_drug_safety_dashboard() -> None:
    """Render the Drug Safety & Toxicity Prediction dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - Drug Safety",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🛡️ AI Drug Safety & Toxicity Prediction Engine")
    st.caption("Computational prediction of hepatotoxicity, cardiotoxicity, nephrotoxicity, and other safety endpoints")
    
    # Initialize session state
    if "ds_results" not in ss:
        ss.ds_results = {}
    if "ds_current_run" not in ss:
        ss.ds_current_run = None
    if "ds_models" not in ss:
        ss.ds_models = None
    
    # Load ML models on first run
    if ss.ds_models is None:
        with st.spinner("Loading toxicity models..."):
            ss.ds_models = load_pretrained_models()
    
    # Sidebar
    with st.sidebar:
        st.header("🔬 Input Methods")
        input_method = st.radio(
            "Select Input Method",
            ["SMILES Input", "PubChem CID", "ChEMBL ID", "Batch Analysis"],
            key="ds_input_method",
        )
        
        st.divider()
        st.header("⚙️ Analysis Options")
        
        include_pubchem = st.checkbox("PubChem BioAssay", value=True, key="ds_pubchem")
        include_chembl = st.checkbox("ChEMBL Assays", value=True, key="ds_chembl")
        include_admetlab = st.checkbox("ADMETlab 2.0", value=False, key="ds_admetlab",
                                       help="Requires API access - may not be available")
        include_ml = st.checkbox("ML Predictions", value=True, key="ds_ml",
                                 help="Predictions from trained models (if available)")
        include_interactions = st.checkbox("Drug Interactions", value=False, key="ds_interactions",
                                           help="Requires DrugBank API key - not fully implemented")
        
        st.divider()
        st.header("💾 Database")
        save_to_db = st.checkbox("Save to Database", value=True, key="ds_save_db")
        
        st.divider()
        st.header("📊 Recent Analyses")
        recent = get_recent_ds_runs(10)
        for run in recent:
            risk = run.get("risk_assessment", {})
            risk_str = risk.get("risk_level", "N/A") if risk else "N/A"
            if st.button(f"{run['identifier'][:25]}... ({risk_str})", key=f"recent_{run['run_id']}"):
                _load_ds_run(run["run_id"])
    
    # Main content
    if input_method == "SMILES Input":
        render_smiles_input(include_pubchem, include_chembl, include_admetlab, include_ml, include_interactions, save_to_db)
    elif input_method == "PubChem CID":
        render_cid_input(include_pubchem, include_chembl, include_admetlab, include_ml, include_interactions, save_to_db)
    elif input_method == "ChEMBL ID":
        render_chembl_input(include_pubchem, include_chembl, include_admetlab, include_ml, include_interactions, save_to_db)
    elif input_method == "Batch Analysis":
        render_batch_input(include_pubchem, include_chembl, include_admetlab, include_ml, include_interactions, save_to_db)
    
    # Display results
    if ss.ds_current_run and ss.ds_current_run in ss.ds_results:
        display_ds_results(ss.ds_current_run, ss.ds_results[ss.ds_current_run])


def render_smiles_input(
    include_pubchem: bool, include_chembl: bool, include_admetlab: bool,
    include_ml: bool, include_interactions: bool, save_to_db: bool
) -> None:
    """Render SMILES input interface."""
    st.subheader("📝 SMILES Input")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        smiles = st.text_area(
            "Enter SMILES",
            placeholder="e.g., CC(=O)OC1=CC=CC=C1C(=O)O (Aspirin)",
            height=100,
            key="ds_smiles_input",
        )
    with col2:
        st.write("")
        st.write("")
        compound_name = st.text_input("Compound Name (optional)", key="ds_compound_name")
        analyze_btn = st.button("🔬 Analyze Safety", type="primary", use_container_width=True, key="ds_analyze_smiles")
    
    # Examples
    with st.expander("📋 Example Compounds"):
        examples = {
            "Aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
            "Paracetamol": "CC(=O)NC1=CC=C(C=C1)O",
            "Ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
            "Warfarin": "CC(=O)CC(C1=CC=CC=C1)C2=CC(=O)CC3=C2C=CC=C3",
            "Doxorubicin": "CC1C(C(C(CO1)O)N)O)C2=CC(=C(C=C2C(=O)C3=C4C=CC(=C5C(=C4C(=O)C(=C(C5=O)O)OC)O)OC)O",
        }
        cols = st.columns(len(examples))
        for i, (name, smi) in enumerate(examples.items()):
            if cols[i].button(name, key=f"ds_ex_{name}"):
                ss.ds_smiles_input = smi
                ss.ds_compound_name = name
                st.rerun()
    
    if analyze_btn and smiles.strip():
        run_safety_analysis(
            smiles=smiles.strip(),
            name=compound_name.strip() if compound_name else None,
            identifier_type="smiles",
            include_pubchem=include_pubchem,
            include_chembl=include_chembl,
            include_admetlab=include_admetlab,
            include_ml=include_ml,
            include_interactions=include_interactions,
            save_to_db=save_to_db,
        )


def render_cid_input(
    include_pubchem: bool, include_chembl: bool, include_admetlab: bool,
    include_ml: bool, include_interactions: bool, save_to_db: bool
) -> None:
    """Render PubChem CID input."""
    st.subheader("🆔 PubChem CID Lookup")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        cid = st.text_input("PubChem CID", placeholder="e.g., 2244 (Aspirin)", key="ds_cid_input")
    with col2:
        st.write("")
        lookup_btn = st.button("🔍 Lookup", type="primary", use_container_width=True, key="ds_lookup_cid")
    
    if lookup_btn and cid.strip():
        run_safety_analysis(
            smiles=None,
            cid=cid.strip(),
            identifier_type="cid",
            include_pubchem=include_pubchem,
            include_chembl=include_chembl,
            include_admetlab=include_admetlab,
            include_ml=include_ml,
            include_interactions=include_interactions,
            save_to_db=save_to_db,
        )


def render_chembl_input(
    include_pubchem: bool, include_chembl: bool, include_admetlab: bool,
    include_ml: bool, include_interactions: bool, save_to_db: bool
) -> None:
    """Render ChEMBL ID input."""
    st.subheader("🧬 ChEMBL ID Lookup")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        chembl_id = st.text_input("ChEMBL ID", placeholder="e.g., CHEMBL25 (Aspirin)", key="ds_chembl_input")
    with col2:
        st.write("")
        lookup_btn = st.button("🔍 Lookup", type="primary", use_container_width=True, key="ds_lookup_chembl")
    
    if lookup_btn and chembl_id.strip():
        run_safety_analysis(
            smiles=None,
            chembl_id=chembl_id.strip().upper(),
            identifier_type="chembl_id",
            include_pubchem=include_pubchem,
            include_chembl=include_chembl,
            include_admetlab=include_admetlab,
            include_ml=include_ml,
            include_interactions=include_interactions,
            save_to_db=save_to_db,
        )


def render_batch_input(
    include_pubchem: bool, include_chembl: bool, include_admetlab: bool,
    include_ml: bool, include_interactions: bool, save_to_db: bool
) -> None:
    """Render batch analysis."""
    st.subheader("📦 Batch Safety Analysis")
    st.write("Enter multiple SMILES (one per line) for batch toxicity screening.")
    
    batch_input = st.text_area(
        "SMILES List",
        placeholder="CC(=O)OC1=CC=CC=C1C(=O)O\nCC(=O)NC1=CC=C(C=C1)O\nCC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
        height=150,
        key="ds_batch_input",
    )
    
    if st.button("🔬 Run Batch Analysis", type="primary", key="ds_batch_analyze"):
        smiles_list = [s.strip() for s in batch_input.split("\n") if s.strip()]
        
        if len(smiles_list) < 2:
            st.warning("Please enter at least 2 SMILES for batch analysis")
            return
        
        if len(smiles_list) > 20:
            st.warning("Limiting to first 20 compounds for performance")
            smiles_list = smiles_list[:20]
        
        run_batch_analysis(
            smiles_list=smiles_list,
            include_pubchem=include_pubchem,
            include_chembl=include_chembl,
            include_admetlab=include_admetlab,
            include_ml=include_ml,
            include_interactions=include_interactions,
            save_to_db=save_to_db,
        )


def run_safety_analysis(
    smiles: str | None,
    cid: str | None,
    chembl_id: str | None,
    identifier_type: str,
    name: str | None,
    include_pubchem: bool,
    include_chembl: bool,
    include_admetlab: bool,
    include_ml: bool,
    include_interactions: bool,
    save_to_db: bool,
) -> None:
    """Run safety analysis."""
    run_id = str(uuid.uuid4())[:8]
    
    with st.spinner("Running safety analysis..."):
        try:
            # Build safety profile
            profile = build_safety_profile(
                smiles=smiles,
                cid=cid,
                chembl_id=chembl_id,
            )
            
            # ADMETlab
            admetlab_pred = None
            if include_admetlab and smiles:
                admetlab_obj = fetch_admetlab_prediction(smiles)
                if admetlab_obj:
                    admetlab_pred = {
                        "smiles": admetlab_obj.smiles,
                        "absorption": admetlab_obj.absorption,
                        "distribution": admetlab_obj.distribution,
                        "metabolism": admetlab_obj.metabolism,
                        "excretion": admetlab_obj.excretion,
                        "toxicity": admetlab_obj.toxicity,
                    }
            
            # ML Predictions
            ml_predictions = []
            if include_ml and smiles:
                mol_props = calculate_toxicity_relevant_properties(smiles)
                if mol_props:
                    X = pd.DataFrame([mol_props])
                    preds = ss.ds_models.predict(X, endpoints=TOXICITY_ENDPOINTS)
                    ml_predictions = [
                        {
                            "endpoint": p.endpoint,
                            "probability": p.probability,
                            "prediction": p.prediction,
                            "confidence": p.confidence,
                            "model_used": p.model_used,
                            "details": p.details,
                        }
                        for p in preds
                    ]
            
            # Drug interactions (placeholder)
            interactions = []
            if include_interactions and name:
                # Would need DrugBank API
                pass
            
            # Store results
            ss.ds_results[run_id] = {
                "profile": profile,
                "admetlab_pred": admetlab_pred,
                "ml_predictions": ml_predictions,
                "interactions": interactions,
                "name": name,
                "identifier_type": identifier_type,
            }
            ss.ds_current_run = run_id
            
            # Save to database
            if save_to_db:
                save_ds_to_db(run_id, profile, admetlab_pred, ml_predictions, interactions)
            
            st.success("Safety analysis complete!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            import traceback
            st.code(traceback.format_exc())


def run_batch_analysis(
    smiles_list: list[str],
    include_pubchem: bool,
    include_chembl: bool,
    include_admetlab: bool,
    include_ml: bool,
    include_interactions: bool,
    save_to_db: bool,
) -> None:
    """Run batch safety analysis."""
    batch_id = str(uuid.uuid4())[:8]
    
    progress = st.progress(0)
    status = st.empty()
    
    results = []
    
    for i, smiles in enumerate(smiles_list):
        progress.progress((i + 1) / len(smiles_list))
        status.text(f"Analyzing {i+1}/{len(smiles_list)}: {smiles[:30]}...")
        
        try:
            profile = build_safety_profile(smiles=smiles)
            
            # ML predictions
            ml_predictions = []
            if include_ml:
                mol_props = calculate_toxicity_relevant_properties(smiles)
                if mol_props:
                    X = pd.DataFrame([mol_props])
                    preds = ss.ds_models.predict(X, endpoints=TOXICITY_ENDPOINTS[:10])  # Limit for speed
                    ml_predictions = [
                        {
                            "endpoint": p.endpoint,
                            "probability": p.probability,
                            "prediction": p.prediction,
                            "confidence": p.confidence,
                        }
                        for p in preds
                    ]
            
            risk = profile.risk_assessment
            results.append({
                "SMILES": smiles[:50] + "..." if len(smiles) > 50 else smiles,
                "Risk Level": risk.get("risk_level", "N/A"),
                "Risk Score": f"{risk.get('risk_score', 0):.3f}",
                "Risk Factors": risk.get("num_factors", 0),
                "Structural Alerts": sum(1 for v in profile.structural_alerts.values() if v > 0),
                "PubChem Assays": len(profile.pubchem_toxicity),
                "ChEMBL Assays": len(profile.chembl_toxicity),
                "Toxic Predictions": sum(1 for p in ml_predictions if p["prediction"] == "Toxic"),
                "Profile": profile,
                "ML Predictions": ml_predictions,
            })
        except Exception as e:
            results.append({
                "SMILES": smiles[:50],
                "Error": str(e),
            })
    
    progress.empty()
    status.empty()
    
    # Store batch results
    ss.ds_results[batch_id] = {
        "batch_results": results,
        "is_batch": True,
    }
    ss.ds_current_run = batch_id
    
    st.success(f"Batch analysis complete for {len(results)} compounds!")
    st.rerun()


def save_ds_to_db(
    run_id: str,
    profile: SafetyProfile,
    admetlab_pred: dict | None,
    ml_predictions: list[dict],
    interactions: list[dict],
) -> None:
    """Save safety analysis to database."""
    try:
        store_ds_analysis_run(
            run_id,
            profile.identifier,
            "smiles" if profile.identifier.startswith("C") or "=" in profile.identifier else "cid" if profile.identifier.isdigit() else "chembl_id",
            profile.molecular_properties,
            profile.structural_alerts,
            profile.risk_assessment,
            profile.source.split("+") if profile.source != "none" else [],
        )
        
        if profile.pubchem_toxicity:
            store_ds_pubchem_toxicity(run_id, [
                {
                    "cid": t.cid,
                    "assay_id": t.assay_id,
                    "assay_name": t.assay_name,
                    "target_name": t.target_name,
                    "organism": t.organism,
                    "activity_outcome": t.activity_outcome,
                    "activity_score": t.activity_score,
                    "concentration_unit": t.concentration_unit,
                    "concentration_value": t.concentration_value,
                }
                for t in profile.pubchem_toxicity
            ])
        
        if profile.chembl_toxicity:
            store_ds_chembl_toxicity(run_id, [
                {
                    "chembl_id": t.chembl_id,
                    "assay_chembl_id": t.assay_chembl_id,
                    "assay_description": t.assay_description,
                    "target_chembl_id": t.target_chembl_id,
                    "target_name": t.target_name,
                    "organism": t.organism,
                    "standard_type": t.standard_type,
                    "standard_value": t.standard_value,
                    "standard_unit": t.standard_unit,
                    "standard_relation": t.standard_relation,
                    "data_validity_comment": t.data_validity_comment,
                    "document_chembl_id": t.document_chembl_id,
                }
                for t in profile.chembl_toxicity
            ])
        
        if admetlab_pred:
            store_ds_admetlab_prediction(run_id, admetlab_pred)
        
        if ml_predictions:
            store_ds_ml_predictions(run_id, ml_predictions)
        
        if interactions:
            store_ds_drug_interactions(run_id, interactions)
            
    except Exception as e:
        st.warning(f"Database save failed: {e}")


def _load_ds_run(run_id: str) -> None:
    """Load a previous run from database."""
    run = get_ds_analysis_run(run_id)
    if run:
        ss.ds_current_run = run_id
        st.info(f"Loaded run {run_id}. Re-run analysis to view full results.")


def display_ds_results(run_id: str, data: dict[str, Any]) -> None:
    """Display safety analysis results."""
    st.divider()
    
    # Check if batch
    if data.get("is_batch"):
        display_batch_results(run_id, data)
        return
    
    profile = data["profile"]
    admetlab_pred = data.get("admetlab_pred")
    ml_predictions = data.get("ml_predictions", [])
    interactions = data.get("interactions", [])
    name = data.get("name")
    id_type = data.get("identifier_type", "smiles")
    
    # Header
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Risk Level", profile.risk_assessment.get("risk_level", "N/A"))
    with col2:
        st.metric("Risk Score", f"{profile.risk_assessment.get('risk_score', 0):.3f}")
    with col3:
        st.metric("Risk Factors", profile.risk_assessment.get("num_factors", 0))
    with col4:
        toxic_count = sum(1 for p in ml_predictions if p.get("prediction") == "Toxic")
        st.metric("Toxic Predictions", toxic_count)
    
    st.caption(f"Compound: {name or 'Unknown'} | ID: {profile.identifier[:40]}... ({id_type})")
    
    # Tabs
    tabs = st.tabs([
        "⚠️ Risk Assessment",
        "🧪 Molecular Properties",
        "🚨 Structural Alerts",
        "📊 PubChem Assays",
        "🧬 ChEMBL Assays",
        "🤖 ML Predictions",
        "🔬 ADMETlab",
        "💊 Interactions",
        "📄 Reports",
    ])
    
    with tabs[0]:
        render_risk_tab(profile)
    
    with tabs[1]:
        render_molecular_props_tab(profile)
    
    with tabs[2]:
        render_alerts_tab(profile)
    
    with tabs[3]:
        render_pubchem_tab(profile)
    
    with tabs[4]:
        render_chembl_tab(profile)
    
    with tabs[5]:
        render_ml_predictions_tab(ml_predictions)
    
    with tabs[6]:
        render_admetlab_tab(admetlab_pred)
    
    with tabs[7]:
        render_interactions_tab(interactions)
    
    with tabs[8]:
        render_ds_reports_tab(run_id, profile, admetlab_pred, ml_predictions, interactions)


def display_batch_results(run_id: str, data: dict[str, Any]) -> None:
    """Display batch analysis results."""
    st.subheader("Batch Analysis Results")
    
    results = data["batch_results"]
    
    # Summary table
    summary_data = []
    for r in results:
        if "Error" in r:
            summary_data.append({
                "SMILES": r["SMILES"],
                "Status": "Error",
                "Error": r["Error"],
            })
        else:
            summary_data.append({
                "SMILES": r["SMILES"],
                "Risk Level": r["Risk Level"],
                "Risk Score": r["Risk Score"],
                "Risk Factors": r["Risk Factors"],
                "Structural Alerts": r["Structural Alerts"],
                "PubChem Assays": r["PubChem Assays"],
                "ChEMBL Assays": r["ChEMBL Assays"],
                "Toxic Predictions": r["Toxic Predictions"],
            })
    
    df = pd.DataFrame(summary_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Risk distribution chart
    if not df.empty and "Risk Level" in df.columns:
        risk_counts = df["Risk Level"].value_counts()
        fig = go.Figure(go.Bar(
            x=risk_counts.index.tolist(),
            y=risk_counts.values.tolist(),
            marker_color=['#c00000', '#bf8f00', '#548235', '#548235'][:len(risk_counts)],
        ))
        fig.update_layout(
            title="Risk Level Distribution",
            xaxis_title="Risk Level",
            yaxis_title="Count",
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Detailed view
    st.subheader("Compound Details")
    for r in results:
        if "Error" in r:
            with st.expander(f"❌ {r['SMILES']} - Error"):
                st.error(r["Error"])
        else:
            with st.expander(f"{r['Risk Level']} - {r['SMILES']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Risk Score:** {r['Risk Score']}")
                    st.write(f"**Risk Factors:** {r['Risk Factors']}")
                    st.write(f"**Structural Alerts:** {r['Structural Alerts']}")
                with col2:
                    st.write(f"**PubChem Assays:** {r['PubChem Assays']}")
                    st.write(f"**ChEMBL Assays:** {r['ChEMBL Assays']}")
                    st.write(f"**Toxic ML Predictions:** {r['Toxic Predictions']}")
                
                if "ML Predictions" in r:
                    st.write("**ML Predictions:**")
                    ml_df = pd.DataFrame(r["ML Predictions"])
                    st.dataframe(ml_df[["endpoint", "prediction", "probability", "confidence"]], hide_index=True)


def render_risk_tab(profile: SafetyProfile) -> None:
    """Render risk assessment tab."""
    st.subheader("Risk Assessment Summary")
    
    risk = profile.risk_assessment
    
    # Risk gauge
    risk_level = risk.get("risk_level", "Unknown")
    risk_score = risk.get("risk_score", 0.0)
    
    risk_colors = {
        "High": "#c00000",
        "Moderate": "#bf8f00",
        "Low-Moderate": "#548235",
        "Low": "#548235",
    }
    color = risk_colors.get(risk_level, "#4a4a4a")
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=risk_score * 100,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Risk Score: {risk_level}"},
        delta={'reference': 50},
        gauge={
            'axis': {'range': [None, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 20], 'color': "#548235"},
                {'range': [20, 40], 'color': "#548235"},
                {'range': [40, 70], 'color': "#bf8f00"},
                {'range': [70, 100], 'color': "#c00000"},
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': risk_score * 100
            }
        }
    ))
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)
    
    # Risk factors
    st.subheader("Identified Risk Factors")
    factors = risk.get("risk_factors", [])
    if factors:
        for i, factor in enumerate(factors, 1):
            st.write(f"{i}. {factor}")
    else:
        st.info("No specific risk factors identified.")


def render_molecular_props_tab(profile: SafetyProfile) -> None:
    """Render molecular properties tab."""
    st.subheader("Molecular Properties")
    
    props = profile.molecular_properties
    if not props:
        st.info("No molecular properties available.")
        return
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("MW", f"{props.get('molecular_weight', 0):.1f} Da")
        st.metric("LogP", f"{props.get('logp', 0):.2f}")
        st.metric("TPSA", f"{props.get('tpsa', 0):.1f} Å²")
    with col2:
        st.metric("HBD", props.get('hbd', 0))
        st.metric("HBA", props.get('hba', 0))
        st.metric("Rot. Bonds", props.get('rotatable_bonds', 0))
    with col3:
        st.metric("Aromatic Rings", props.get('aromatic_rings', 0))
        st.metric("Heavy Atoms", props.get('heavy_atoms', 0))
        st.metric("Charge", props.get('formal_charge', 0))
    
    st.divider()
    st.metric("Lipinski Violations", props.get('lipinski_violations', 0))
    
    # Full table
    with st.expander("All Properties"):
        prop_df = pd.DataFrame([{"Property": k, "Value": v} for k, v in props.items()])
        st.dataframe(prop_df, use_container_width=True, hide_index=True)


def render_alerts_tab(profile: SafetyProfile) -> None:
    """Render structural alerts tab."""
    st.subheader("Structural Alerts")
    
    alerts = profile.structural_alerts
    if not alerts:
        st.info("No structural alerts data.")
        return
    
    alert_descriptions = {
        "pains_alerts": "🔴 PAINS (Pan-Assay Interference Compounds)",
        "brenk_alerts": "🟠 Brenk Structural Alerts",
        "nih_alerts": "🟡 NIH Structural Alerts",
        "alert_aldehyde": "Aldehyde Group (reactive)",
        "alert_epoxide": "Epoxide Group (reactive)",
        "alert_michael_acceptor": "Michael Acceptor (reactive)",
        "alert_alkylating": "Alkylating Agent (reactive)",
        "alert_nitro": "Nitro Group (toxicophore)",
    }
    
    alert_data = []
    for key, value in alerts.items():
        if value > 0:
            alert_data.append({
                "Alert": alert_descriptions.get(key, key),
                "Status": "⚠️ DETECTED",
                "Count": int(value),
            })
        else:
            alert_data.append({
                "Alert": alert_descriptions.get(key, key),
                "Status": "✅ Not Detected",
                "Count": 0,
            })
    
    df = pd.DataFrame(alert_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Summary
    total_alerts = sum(1 for v in alerts.values() if v > 0)
    if total_alerts > 0:
        st.warning(f"⚠️ {total_alerts} structural alert(s) detected - review recommended")
    else:
        st.success("✅ No structural alerts detected")


def render_pubchem_tab(profile: SafetyProfile) -> None:
    """Render PubChem assays tab."""
    st.subheader("PubChem BioAssay Toxicity Data")
    
    assays = profile.pubchem_toxicity
    if not assays:
        st.info("No PubChem toxicity assays found.")
        return
    
    active = [a for a in assays if a.activity_outcome == "Active"]
    inactive = [a for a in assays if a.activity_outcome != "Active"]
    
    st.write(f"**Total Assays:** {len(assays)} | **Active:** {len(active)} | **Inactive/Inconclusive:** {len(inactive)}")
    
    if active:
        st.subheader("⚠️ Active Toxicity Assays")
        active_data = []
        for a in active[:50]:
            active_data.append({
                "AID": a.assay_id,
                "Assay Name": a.assay_name[:60],
                "Target": a.target_name[:30],
                "Organism": a.organism,
                "Score": f"{a.activity_score:.1f}",
                "Conc.": f"{a.concentration_value} {a.concentration_unit}",
            })
        st.dataframe(pd.DataFrame(active_data), use_container_width=True, hide_index=True)
    
    if inactive:
        with st.expander(f"Inactive/Inconclusive Assays ({len(inactive)})"):
            inactive_data = []
            for a in inactive[:50]:
                inactive_data.append({
                    "AID": a.assay_id,
                    "Assay Name": a.assay_name[:60],
                    "Target": a.target_name[:30],
                    "Outcome": a.activity_outcome,
                })
            st.dataframe(pd.DataFrame(inactive_data), use_container_width=True, hide_index=True)


def render_chembl_tab(profile: SafetyProfile) -> None:
    """Render ChEMBL assays tab."""
    st.subheader("ChEMBL Toxicity Assays")
    
    assays = profile.chembl_toxicity
    if not assays:
        st.info("No ChEMBL toxicity assays found.")
        return
    
    # Filter potency assays
    potency = [a for a in assays if a.standard_type in ("IC50", "EC50", "LD50", "LC50", "GI50")]
    other = [a for a in assays if a.standard_type not in ("IC50", "EC50", "LD50", "LC50", "GI50")]
    
    st.write(f"**Total Assays:** {len(assays)} | **Potency (IC50/EC50/LD50):** {len(potency)}")
    
    if potency:
        st.subheader("Potency Assays")
        pot_data = []
        for a in potency[:50]:
            pot_data.append({
                "Assay": a.assay_chembl_id,
                "Target": a.target_name[:40],
                "Type": a.standard_type,
                "Value": f"{a.standard_value:.2f}",
                "Unit": a.standard_unit,
                "Relation": a.standard_relation,
                "Organism": a.organism,
            })
        st.dataframe(pd.DataFrame(pot_data), use_container_width=True, hide_index=True)
    
    if other:
        with st.expander(f"Other Assays ({len(other)})"):
            other_data = []
            for a in other[:50]:
                other_data.append({
                    "Assay": a.assay_chembl_id,
                    "Description": a.assay_description[:60],
                    "Target": a.target_name[:30],
                    "Type": a.standard_type,
                })
            st.dataframe(pd.DataFrame(other_data), use_container_width=True, hide_index=True)


def render_ml_predictions_tab(predictions: list[dict]) -> None:
    """Render ML predictions tab."""
    st.subheader("ML Toxicity Predictions")
    
    if not predictions:
        st.info("No ML predictions available. Models need to be trained on experimental toxicity data.")
        st.caption("Available endpoints: " + ", ".join(TOXICITY_ENDPOINTS))
        return
    
    # Summary
    toxic = [p for p in predictions if p.get("prediction") == "Toxic"]
    non_toxic = [p for p in predictions if p.get("prediction") == "Non-toxic"]
    unknown = [p for p in predictions if p.get("prediction") not in ("Toxic", "Non-toxic")]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Toxic", len(toxic), delta_color="inverse")
    with col2:
        st.metric("Non-toxic", len(non_toxic))
    with col3:
        st.metric("Unknown/Error", len(unknown))
    
    # Confidence filter
    conf_filter = st.multiselect(
        "Filter by Confidence",
        ["high", "medium", "low"],
        default=["high", "medium", "low"],
        key="ds_ml_conf_filter",
    )
    
    filtered = [p for p in predictions if p.get("confidence", "low") in conf_filter]
    
    # Table
    pred_data = []
    for p in filtered:
        details = p.get("details", {})
        pred_data.append({
            "Endpoint": p.get("endpoint", ""),
            "Prediction": p.get("prediction", ""),
            "Probability": f"{p.get('probability', 0):.3f}",
            "Confidence": p.get("confidence", "").capitalize(),
            "Model": p.get("model_used", ""),
            "CV AUC": f"{details.get('cv_auc', 0):.3f}",
        })
    
    if pred_data:
        df = pd.DataFrame(pred_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Highlight toxic predictions
        toxic_df = df[df["Prediction"] == "Toxic"]
        if not toxic_df.empty:
            st.subheader("⚠️ Predicted Toxic Endpoints")
            st.dataframe(toxic_df, use_container_width=True, hide_index=True)
        
        # Probability chart
        fig = go.Figure(go.Bar(
            x=[p["Probability"] for p in pred_data],
            y=[p["Endpoint"] for p in pred_data],
            orientation='h',
            marker_color=['#c00000' if p["Prediction"] == "Toxic" else '#548235' for p in pred_data],
        ))
        fig.update_layout(
            title="Toxicity Probability by Endpoint",
            xaxis_title="Probability",
            xaxis=dict(range=[0, 1]),
            height=max(400, len(pred_data) * 25),
        )
        st.plotly_chart(fig, use_container_width=True)


def render_admetlab_tab(admetlab_pred: dict | None) -> None:
    """Render ADMETlab predictions tab."""
    st.subheader("ADMETlab 2.0 Predictions")
    
    if not admetlab_pred:
        st.info("ADMETlab predictions not available. API access may be limited or unavailable.")
        return
    
    categories = [
        ("Absorption", admetlab_pred.get("absorption", {})),
        ("Distribution", admetlab_pred.get("distribution", {})),
        ("Metabolism", admetlab_pred.get("metabolism", {})),
        ("Excretion", admetlab_pred.get("excretion", {})),
        ("Toxicity", admetlab_pred.get("toxicity", {})),
    ]
    
    for cat_name, cat_data in categories:
        if not cat_data:
            continue
        with st.expander(f"{cat_name} ({len(cat_data)} endpoints)"):
            cat_df = pd.DataFrame([
                {"Endpoint": k, "Value": f"{v:.3f}" if isinstance(v, (int, float)) else str(v)}
                for k, v in cat_data.items()
            ])
            st.dataframe(cat_df, use_container_width=True, hide_index=True)
            
            # Highlight high toxicity
            if cat_name == "Toxicity":
                high_tox = [(k, v) for k, v in cat_data.items() if isinstance(v, (int, float)) and v > 0.7]
                if high_tox:
                    st.warning(f"⚠️ High toxicity predictions: {', '.join([f'{k} ({v:.2f})' for k, v in high_tox])}")


def render_interactions_tab(interactions: list[dict]) -> None:
    """Render drug interactions tab."""
    st.subheader("Drug-Drug Interactions")
    
    if not interactions:
        st.info("Drug interaction data not available. Requires DrugBank API integration.")
        return
    
    df = pd.DataFrame(interactions)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_ds_reports_tab(
    run_id: str,
    profile: SafetyProfile,
    admetlab_pred: dict | None,
    ml_predictions: list[dict],
    interactions: list[dict],
) -> None:
    """Render reports tab."""
    st.subheader("Generate Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", use_container_width=True, key=f"ds_pdf_{run_id}"):
            with st.spinner("Generating PDF..."):
                pdf_bytes = generate_ds_pdf_report(
                    {
                        "identifier": profile.identifier,
                        "identifier_type": "smiles",
                        "molecular_properties": profile.molecular_properties,
                        "structural_alerts": profile.structural_alerts,
                        "risk_assessment": profile.risk_assessment,
                        "data_sources": profile.source.split("+") if profile.source != "none" else [],
                    },
                    [{"cid": t.cid, "assay_id": t.assay_id, "assay_name": t.assay_name,
                      "target_name": t.target_name, "organism": t.organism,
                      "activity_outcome": t.activity_outcome, "activity_score": t.activity_score,
                      "concentration_unit": t.concentration_unit, "concentration_value": t.concentration_value}
                     for t in profile.pubchem_toxicity],
                    [{"chembl_id": t.chembl_id, "assay_chembl_id": t.assay_chembl_id,
                      "assay_description": t.assay_description, "target_chembl_id": t.target_chembl_id,
                      "target_name": t.target_name, "organism": t.organism,
                      "standard_type": t.standard_type, "standard_value": t.standard_value,
                      "standard_unit": t.standard_unit, "standard_relation": t.standard_relation,
                      "data_validity_comment": t.data_validity_comment, "document_chembl_id": t.document_chembl_id}
                     for t in profile.chembl_toxicity],
                    admetlab_pred,
                    ml_predictions,
                    interactions,
                    run_id,
                )
            st.download_button(
                "⬇️ Download PDF",
                pdf_bytes,
                f"drug_safety_report_{run_id}.pdf",
                "application/pdf",
                use_container_width=True,
            )
    
    with col2:
        if st.button("📊 Generate CSV Report", use_container_width=True, key=f"ds_csv_{run_id}"):
            with st.spinner("Generating CSV..."):
                csv_str = generate_ds_csv_report(
                    {
                        "identifier": profile.identifier,
                        "identifier_type": "smiles",
                        "molecular_properties": profile.molecular_properties,
                        "structural_alerts": profile.structural_alerts,
                        "risk_assessment": profile.risk_assessment,
                        "data_sources": profile.source.split("+") if profile.source != "none" else [],
                    },
                    [{"cid": t.cid, "assay_id": t.assay_id, "assay_name": t.assay_name,
                      "target_name": t.target_name, "organism": t.organism,
                      "activity_outcome": t.activity_outcome, "activity_score": t.activity_score,
                      "concentration_unit": t.concentration_unit, "concentration_value": t.concentration_value}
                     for t in profile.pubchem_toxicity],
                    [{"chembl_id": t.chembl_id, "assay_chembl_id": t.assay_chembl_id,
                      "assay_description": t.assay_description, "target_chembl_id": t.target_chembl_id,
                      "target_name": t.target_name, "organism": t.organism,
                      "standard_type": t.standard_type, "standard_value": t.standard_value,
                      "standard_unit": t.standard_unit, "standard_relation": t.standard_relation,
                      "data_validity_comment": t.data_validity_comment, "document_chembl_id": t.document_chembl_id}
                     for t in profile.chembl_toxicity],
                    admetlab_pred,
                    ml_predictions,
                    interactions,
                    run_id,
                )
            st.download_button(
                "⬇️ Download CSV",
                csv_str,
                f"drug_safety_report_{run_id}.csv",
                "text/csv",
                use_container_width=True,
            )
    
    with col3:
        if st.button("📋 Generate JSON Report", use_container_width=True, key=f"ds_json_{run_id}"):
            with st.spinner("Generating JSON..."):
                json_data = generate_ds_json_report(
                    {
                        "identifier": profile.identifier,
                        "identifier_type": "smiles",
                        "molecular_properties": profile.molecular_properties,
                        "structural_alerts": profile.structural_alerts,
                        "risk_assessment": profile.risk_assessment,
                        "data_sources": profile.source.split("+") if profile.source != "none" else [],
                    },
                    [{"cid": t.cid, "assay_id": t.assay_id, "assay_name": t.assay_name,
                      "target_name": t.target_name, "organism": t.organism,
                      "activity_outcome": t.activity_outcome, "activity_score": t.activity_score,
                      "concentration_unit": t.concentration_unit, "concentration_value": t.concentration_value}
                     for t in profile.pubchem_toxicity],
                    [{"chembl_id": t.chembl_id, "assay_chembl_id": t.assay_chembl_id,
                      "assay_description": t.assay_description, "target_chembl_id": t.target_chembl_id,
                      "target_name": t.target_name, "organism": t.organism,
                      "standard_type": t.standard_type, "standard_value": t.standard_value,
                      "standard_unit": t.standard_unit, "standard_relation": t.standard_relation,
                      "data_validity_comment": t.data_validity_comment, "document_chembl_id": t.document_chembl_id}
                     for t in profile.chembl_toxicity],
                    admetlab_pred,
                    ml_predictions,
                    interactions,
                    run_id,
                )
            st.download_button(
                "⬇️ Download JSON",
                json.dumps(json_data, indent=2),
                f"drug_safety_report_{run_id}.json",
                "application/json",
                use_container_width=True,
            )


if __name__ == "__main__":
    render_drug_safety_dashboard()