"""Drug-Target Interaction Prediction Dashboard for GeneAI Research - Streamlit UI."""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.drug_target_prediction import binding_affinity
from geneai.drug_target_prediction import ml_models
from geneai.drug_target_prediction import prediction_engine
from geneai.drug_target_prediction import report_generator
from geneai.drug_target_prediction import visualization
from geneai.drug_target_prediction.molecular_descriptors import (
    calculate_molecular_descriptors,
    is_rdkit_available,
)

logger = logging.getLogger(__name__)


def render_drug_target_prediction_dashboard() -> None:
    """Main entry point for the Drug-Target Prediction dashboard."""
    st.title("🎯 Drug-Target Interaction Prediction")
    st.caption("AI-powered prediction of drug-target interactions and binding affinity estimation")
    
    # Check RDKit availability
    if not is_rdkit_available():
        st.warning("⚠️ RDKit is not installed. Molecular descriptor calculation and ML predictions will be limited. Install with: `pip install rdkit-pypi`")
    
    # Initialize session state
    _init_session_state()
    
    # Main tabs
    tabs = st.tabs([
        "🔮 Single Prediction",
        "📊 Batch Screening",
        "🎯 Target Profile",
        "🧪 Affinity Estimation",
        "🤖 Model Training",
        "📈 Visualizations",
        "📄 Reports",
        "⚙️ Settings",
    ])
    
    with tabs[0]:
        _render_single_prediction_tab()
    
    with tabs[1]:
        _render_batch_screening_tab()
    
    with tabs[2]:
        _render_target_profile_tab()
    
    with tabs[3]:
        _render_affinity_estimation_tab()
    
    with tabs[4]:
        _render_model_training_tab()
    
    with tabs[5]:
        _render_visualizations_tab()
    
    with tabs[6]:
        _render_reports_tab()
    
    with tabs[7]:
        _render_settings_tab()


def _init_session_state() -> None:
    """Initialize session state variables."""
    defaults = {
        "dtp_predictions": None,
        "dtp_batch_results": None,
        "dtp_target_profile": None,
        "dtp_affinity_results": None,
        "dtp_model": None,
        "dtp_training_results": None,
        "dtp_engine": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _get_engine() -> prediction_engine.DrugTargetPredictionEngine:
    """Get or create prediction engine."""
    if st.session_state.dtp_engine is None:
        st.session_state.dtp_engine = prediction_engine.DrugTargetPredictionEngine(
            model_type=st.session_state.get("dtp_model_type", "random_forest"),
            use_fingerprints=st.session_state.get("dtp_use_fingerprints", True),
            fp_type=st.session_state.get("dtp_fp_type", "morgan"),
        )
    return st.session_state.dtp_engine


def _render_single_prediction_tab() -> None:
    """Single drug-target prediction interface."""
    st.subheader("Single Drug-Target Prediction")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Drug**")
        drug_input = st.text_input(
            "Drug identifier",
            placeholder="e.g., aspirin, CHEMBL25, CID 2244, CC(=O)OC1=CC=CC=C1C(=O)O",
            key="dtp_single_drug",
        )
        drug_id_type = st.selectbox(
            "Identifier type",
            ["Auto-detect", "Name", "ChEMBL ID", "PubChem CID", "InChIKey", "SMILES"],
            key="dtp_single_drug_type",
        )
    
    with col2:
        st.markdown("**Target**")
        target_input = st.text_input(
            "Target identifier",
            placeholder="e.g., EGFR, CHEMBL203, P00533",
            key="dtp_single_target",
        )
        target_id_type = st.selectbox(
            "Identifier type",
            ["Gene Symbol", "ChEMBL Target ID", "UniProt ID"],
            key="dtp_single_target_type",
        )
    
    if st.button("🔮 Predict Interaction", type="primary", use_container_width=True, key="dtp_single_predict"):
        if drug_input and target_input:
            _perform_single_prediction(drug_input, target_input, drug_id_type, target_id_type)
        else:
            st.warning("Please enter both drug and target identifiers")
    
    # Display results
    if st.session_state.dtp_predictions:
        _display_single_prediction_results(st.session_state.dtp_predictions)


def _perform_single_prediction(
    drug_input: str,
    target_input: str,
    drug_type: str,
    target_type: str,
) -> None:
    """Perform single drug-target prediction."""
    engine = _get_engine()
    
    with st.spinner("Predicting interaction..."):
        try:
            # Map UI types to engine types
            drug_type_map = {
                "Auto-detect": "auto",
                "Name": "name",
                "ChEMBL ID": "chembl_id",
                "PubChem CID": "cid",
                "InChIKey": "inchikey",
                "SMILES": "smiles",
            }
            
            result = engine.predict_drug_target(
                drug_identifier=drug_input,
                target_identifier=target_input,
                identifier_type=drug_type_map.get(drug_type, "auto"),
            )
            
            st.session_state.dtp_predictions = result
            st.success("Prediction complete!")
            
        except Exception as e:
            logger.error("Single prediction failed: %s", e)
            st.error(f"Prediction failed: {e}")


def _display_single_prediction_results(result: dict[str, Any]) -> None:
    """Display single prediction results."""
    if not result.get("success"):
        st.error(f"Prediction failed: {result.get('error', 'Unknown error')}")
        return
    
    # Main result card
    prob = result.get("interaction_probability", 0)
    pred = result.get("predicted_interaction", 0)
    conf = result.get("confidence", "unknown")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Interaction Probability",
            f"{prob:.1%}",
            delta="Interacts" if pred == 1 else "No Interaction",
        )
    
    with col2:
        st.metric("Predicted Class", "Interacts" if pred == 1 else "No Interaction")
    
    with col3:
        confidence_colors = {"high": "🟢", "medium": "🟡", "low": "🟠", "unknown": "⚪"}
        st.metric("Confidence", f"{confidence_colors.get(conf, '⚪')} {conf.title()}")
    
    # Details
    with st.expander("📋 Prediction Details", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Drug:** {result.get('drug_identifier', 'N/A')}")
            st.write(f"**Target:** {result.get('target_identifier', 'N/A')}")
            st.write(f"**Drug SMILES:** {result.get('drug_smiles', 'N/A')[:100]}...")
        with col2:
            st.write(f"**Model:** {st.session_state.get('dtp_model_type', 'random_forest')}")
            st.write(f"**Fingerprints:** {st.session_state.get('dtp_use_fingerprints', True)}")
            st.write(f"**FP Type:** {st.session_state.get('dtp_fp_type', 'morgan')}")
    
    # Affinity estimation
    if st.button("🧪 Estimate Binding Affinity", key="dtp_single_affinity"):
        _estimate_single_affinity(result.get("drug_smiles", ""), result.get("target_identifier", ""))


def _estimate_single_affinity(drug_smiles: str, target_identifier: str) -> None:
    """Estimate binding affinity for single prediction."""
    with st.spinner("Estimating binding affinity..."):
        try:
            result = binding_affinity.generate_affinity_report(
                drug_identifier=drug_smiles,
                target_identifier=target_identifier,
            )
            st.session_state.dtp_affinity_results = [result]
            
            if "consensus" in result:
                cons = result["consensus"]
                st.success(f"Consensus pKd: {cons.get('geometric_mean_pkd', 0):.2f} "
                          f"({cons.get('geometric_mean_nm', 0):.2f} nM) - "
                          f"{cons.get('potency_class', 'Unknown')}")
            
        except Exception as e:
            logger.error("Affinity estimation failed: %s", e)
            st.error(f"Affinity estimation failed: {e}")


def _render_batch_screening_tab() -> None:
    """Batch screening interface."""
    st.subheader("Batch Drug Screening Against Target")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        target_input = st.text_input(
            "Target identifier",
            placeholder="e.g., EGFR, CHEMBL203",
            key="dtp_batch_target",
        )
        
        drug_input_method = st.radio(
            "Drug input method",
            ["Paste list", "Upload file", "From database"],
            horizontal=True,
            key="dtp_batch_method",
        )
        
        if drug_input_method == "Paste list":
            drug_list_text = st.text_area(
                "Drug identifiers (one per line)",
                placeholder="aspirin\nibuprofen\nCHEMBL25\nCC(=O)OC1=CC=CC=C1C(=O)O",
                height=200,
                key="dtp_batch_drugs_text",
            )
            drug_list = [d.strip() for d in drug_list_text.split("\n") if d.strip()]
        
        elif drug_input_method == "Upload file":
            uploaded_file = st.file_uploader(
                "Upload drug list (CSV/TSV with 'identifier' column)",
                type=["csv", "tsv", "txt"],
                key="dtp_batch_file",
            )
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith(".tsv"):
                        df = pd.read_csv(uploaded_file, sep="\t")
                    else:
                        df = pd.read_csv(uploaded_file)
                    drug_list = df.iloc[:, 0].astype(str).tolist()
                    st.info(f"Loaded {len(drug_list)} drugs from file")
                except Exception as e:
                    st.error(f"Failed to read file: {e}")
                    drug_list = []
            else:
                drug_list = []
        
        else:  # From database
            st.info("Database integration coming soon")
            drug_list = []
    
    with col2:
        st.markdown("**Options**")
        identifier_type = st.selectbox(
            "Drug identifier type",
            ["Auto-detect", "Name", "ChEMBL ID", "PubChem CID", "SMILES"],
            key="dtp_batch_id_type",
        )
        top_n = st.number_input("Top hits to highlight", 10, 500, 50, key="dtp_batch_top_n")
    
    if st.button("🚀 Run Batch Screening", type="primary", use_container_width=True, key="dtp_batch_run"):
        if target_input and drug_list:
            _perform_batch_screening(drug_list, target_input, identifier_type, top_n)
        else:
            st.warning("Please provide target and drug list")
    
    # Display results
    if st.session_state.dtp_batch_results:
        _display_batch_results(st.session_state.dtp_batch_results)


def _perform_batch_screening(
    drug_list: list[str],
    target_input: str,
    identifier_type: str,
    top_n: int,
) -> None:
    """Perform batch screening."""
    engine = _get_engine()
    
    type_map = {
        "Auto-detect": "auto",
        "Name": "name",
        "ChEMBL ID": "chembl_id",
        "PubChem CID": "cid",
        "SMILES": "smiles",
    }
    
    with st.spinner(f"Screening {len(drug_list)} drugs against {target_input}..."):
        try:
            results = engine.predict_drug_target_batch(
                drug_identifiers=drug_list,
                target_identifier=target_input,
                identifier_type=type_map.get(identifier_type, "auto"),
            )
            
            st.session_state.dtp_batch_results = {
                "predictions": results,
                "target": target_input,
                "top_n": top_n,
            }
            st.success(f"Screening complete! {len(results)} predictions generated.")
            
        except Exception as e:
            logger.error("Batch screening failed: %s", e)
            st.error(f"Batch screening failed: {e}")


def _display_batch_results(batch_data: dict[str, Any]) -> None:
    """Display batch screening results."""
    predictions = batch_data["predictions"]
    target = batch_data["target"]
    top_n = batch_data["top_n"]
    
    # Filter successful
    successful = [p for p in predictions if p.get("success")]
    
    if not successful:
        st.warning("No successful predictions")
        return
    
    # Sort by probability
    successful.sort(key=lambda x: x.get("interaction_probability", 0), reverse=True)
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Screened", len(predictions))
    with col2:
        st.metric("Successful", len(successful))
    with col3:
        interacting = sum(1 for p in successful if p.get("predicted_interaction") == 1)
        st.metric("Predicted Interacting", interacting)
    with col4:
        high_conf = sum(1 for p in successful if p.get("confidence") == "high")
        st.metric("High Confidence", high_conf)
    
    # Results table
    df = pd.DataFrame(successful)
    df["Rank"] = range(1, len(df) + 1)
    df["Top Hit"] = df["Rank"].apply(lambda x: "⭐" if x <= top_n else "")
    
    display_cols = ["Rank", "Top Hit", "drug_identifier", "drug_smiles", 
                    "interaction_probability", "predicted_interaction", "confidence"]
    display_df = df[display_cols].copy()
    display_df.columns = ["Rank", "Top Hit", "Drug ID", "SMILES", "Probability", "Prediction", "Confidence"]
    display_df["Probability"] = display_df["Probability"].apply(lambda x: f"{x:.2%}")
    display_df["Prediction"] = display_df["Prediction"].apply(lambda x: "Interacts" if x == 1 else "No Interaction")
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Visualization
    fig = visualization.create_prediction_confidence_chart(successful, 
        title=f"Batch Screening Results: {target}")
    st.plotly_chart(fig, use_container_width=True)


def _render_target_profile_tab() -> None:
    """Target profile prediction for a drug."""
    st.subheader("Drug Target Profile")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        drug_input = st.text_input(
            "Drug identifier",
            placeholder="e.g., aspirin, CHEMBL25, CID 2244",
            key="dtp_profile_drug",
        )
        
        target_input_method = st.radio(
            "Target list source",
            ["Predefined panels", "Custom list", "From database"],
            horizontal=True,
            key="dtp_profile_method",
        )
        
        if target_input_method == "Predefined panels":
            panel = st.selectbox(
                "Target panel",
                ["Kinases", "GPCRs", "Ion Channels", "Nuclear Receptors", "Proteases", "All Common Targets"],
                key="dtp_profile_panel",
            )
            target_list = _get_predefined_targets(panel)
            st.info(f"{len(target_list)} targets in {panel} panel")
        
        elif target_input_method == "Custom list":
            target_text = st.text_area(
                "Target identifiers (one per line)",
                placeholder="EGFR\nCHEMBL203\nP00533\nBRAF",
                height=150,
                key="dtp_profile_targets_text",
            )
            target_list = [t.strip() for t in target_text.split("\n") if t.strip()]
        
        else:
            st.info("Database integration coming soon")
            target_list = []
    
    with col2:
        st.markdown("**Options**")
        drug_id_type = st.selectbox(
            "Drug identifier type",
            ["Auto-detect", "Name", "ChEMBL ID", "PubChem CID", "SMILES"],
            key="dtp_profile_drug_type",
        )
    
    if st.button("🎯 Generate Target Profile", type="primary", use_container_width=True, key="dtp_profile_run"):
        if drug_input and target_list:
            _perform_target_profile(drug_input, target_list, drug_id_type)
        else:
            st.warning("Please provide drug and target list")
    
    # Display results
    if st.session_state.dtp_target_profile:
        _display_target_profile(st.session_state.dtp_target_profile)


def _get_predefined_targets(panel: str) -> list[str]:
    """Get predefined target panels."""
    panels = {
        "Kinases": [
            "EGFR", "BRAF", "ABL1", "SRC", "AKT1", "MTOR", "PIK3CA", "MAPK1", "MAPK3",
            "CDK2", "CDK4", "CDK6", "ALK", "MET", "RET", "ROS1", "NTRK1", "NTRK2", "NTRK3",
        ],
        "GPCRs": [
            "ADORA1", "ADORA2A", "DRD2", "DRD3", "HTR1A", "HTR2A", "HTR2C", "OPRM1",
            "OPRD1", "OPRK1", "CNR1", "CNR2", "ADRB1", "ADRB2", "CHRM1", "CHRM2",
        ],
        "Ion Channels": [
            "SCN5A", "SCN9A", "CACNA1C", "CACNA1S", "KCNH2", "KCNQ1", "GRIN1", "GRIN2A",
            "GABRA1", "GABRB2", "CHRNA1", "CHRNA4", "TRPV1", "TRPA1",
        ],
        "Nuclear Receptors": [
            "ESR1", "ESR2", "AR", "PGR", "NR3C1", "NR3C2", "PPARG", "PPARA", "PPARD",
            "RARA", "RARB", "RARG", "THRA", "THRB", "VDR",
        ],
        "Proteases": [
            "HIV1_PROTEASE", "RENIN", "ACE", "FURIN", "MMP2", "MMP9", "CASP3", "CASP9",
            "BACE1", "DPP4", "NEUROLYSIN",
        ],
        "All Common Targets": [
            "EGFR", "BRAF", "ABL1", "SRC", "AKT1", "MTOR", "PIK3CA", "MAPK1", "MAPK3",
            "ADORA1", "ADORA2A", "DRD2", "HTR1A", "HTR2A", "OPRM1", "CNR1", "CNR2",
            "ESR1", "AR", "PGR", "PPARG", "SCN5A", "KCNH2", "CACNA1C",
        ],
    }
    return panels.get(panel, [])


def _perform_target_profile(
    drug_input: str,
    target_list: list[str],
    drug_id_type: str,
) -> None:
    """Generate target profile for a drug."""
    engine = _get_engine()
    
    type_map = {
        "Auto-detect": "auto",
        "Name": "name",
        "ChEMBL ID": "chembl_id",
        "PubChem CID": "cid",
        "SMILES": "smiles",
    }
    
    with st.spinner(f"Predicting interactions for {len(target_list)} targets..."):
        try:
            results = engine.predict_target_profile(
                drug_identifier=drug_input,
                target_list=target_list,
                identifier_type=type_map.get(drug_id_type, "auto"),
            )
            
            st.session_state.dtp_target_profile = {
                "drug": drug_input,
                "predictions": results,
            }
            st.success(f"Target profile generated for {len(results)} targets!")
            
        except Exception as e:
            logger.error("Target profile failed: %s", e)
            st.error(f"Target profile failed: {e}")


def _display_target_profile(profile_data: dict[str, Any]) -> None:
    """Display target profile results."""
    predictions = profile_data["predictions"]
    drug = profile_data["drug"]
    
    successful = [p for p in predictions if p.get("success")]
    interacting = [p for p in successful if p.get("predicted_interaction") == 1]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Targets", len(predictions))
    with col2:
        st.metric("Predicted Interacting", len(interacting))
    with col3:
        high_conf_hits = sum(1 for p in interacting if p.get("confidence") == "high")
        st.metric("High Confidence Hits", high_conf_hits)
    
    # Heatmap
    fig = visualization.create_target_profile_heatmap(predictions,
        title=f"Target Profile: {drug}")
    st.plotly_chart(fig, use_container_width=True)
    
    # Top hits table
    st.subheader("Top Predicted Interactions")
    top_df = pd.DataFrame(interacting[:20])
    if not top_df.empty:
        display_cols = ["target_identifier", "interaction_probability", "confidence"]
        top_df = top_df[display_cols].copy()
        top_df.columns = ["Target", "Probability", "Confidence"]
        top_df["Probability"] = top_df["Probability"].apply(lambda x: f"{x:.2%}")
        st.dataframe(top_df, use_container_width=True, hide_index=True)
    
    # Network visualization
    if len(interacting) > 0:
        fig = visualization.create_interaction_network(predictions, threshold=0.3,
            title=f"Interaction Network: {drug}")
        st.plotly_chart(fig, use_container_width=True)


def _render_affinity_estimation_tab() -> None:
    """Binding affinity estimation interface."""
    st.subheader("Binding Affinity Estimation")
    
    col1, col2 = st.columns(2)
    
    with col1:
        drug_input = st.text_input(
            "Drug identifier",
            placeholder="e.g., aspirin, CHEMBL25, CC(=O)OC1=CC=CC=C1C(=O)O",
            key="dtp_aff_drug",
        )
        target_input = st.text_input(
            "Target identifier",
            placeholder="e.g., EGFR, PTGS1, CHEMBL203",
            key="dtp_aff_target",
        )
    
    with col2:
        methods = st.multiselect(
            "Estimation methods",
            ["Reference (literature)", "Rule-based (drug-likeness)", "ML-based"],
            default=["Reference (literature)", "Rule-based (drug-likeness)", "ML-based"],
            key="dtp_aff_methods",
        )
        method_map = {
            "Reference (literature)": "reference",
            "Rule-based (drug-likeness)": "rule_based",
            "ML-based": "ml",
        }
        selected_methods = [method_map[m] for m in methods]
    
    if st.button("🧪 Estimate Affinity", type="primary", use_container_width=True, key="dtp_aff_run"):
        if drug_input and target_input:
            _perform_affinity_estimation(drug_input, target_input, selected_methods)
        else:
            st.warning("Please provide both drug and target identifiers")
    
    # Display results
    if st.session_state.dtp_affinity_results:
        _display_affinity_results(st.session_state.dtp_affinity_results)


def _perform_affinity_estimation(
    drug_input: str,
    target_input: str,
    methods: list[str],
) -> None:
    """Perform affinity estimation."""
    engine = _get_engine()
    
    # Resolve drug to SMILES
    drug_smiles = engine._resolve_drug_to_smiles(drug_input, "auto")
    if not drug_smiles:
        st.error("Could not resolve drug to SMILES")
        return
    
    with st.spinner("Estimating binding affinity..."):
        try:
            results = []
            for method in methods:
                result = binding_affinity.estimate_binding_affinity(
                    drug_smiles=drug_smiles,
                    target_identifier=target_input,
                    method=method,
                )
                result["drug_identifier"] = drug_input
                result["target_identifier"] = target_input
                results.append(result)
            
            # Also get consensus report
            consensus = binding_affinity.generate_affinity_report(
                drug_identifier=drug_input,
                target_identifier=target_input,
                methods=methods,
            )
            
            st.session_state.dtp_affinity_results = {
                "individual": results,
                "consensus": consensus,
            }
            st.success("Affinity estimation complete!")
            
        except Exception as e:
            logger.error("Affinity estimation failed: %s", e)
            st.error(f"Affinity estimation failed: {e}")


def _display_affinity_results(aff_data: dict[str, Any]) -> None:
    """Display affinity estimation results."""
    individual = aff_data["individual"]
    consensus = aff_data.get("consensus", {})
    
    # Consensus
    if consensus.get("consensus"):
        cons = consensus["consensus"]
        st.subheader("Consensus Estimate")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Geometric Mean pKd", f"{cons.get('geometric_mean_pkd', 0):.2f}")
        with col2:
            st.metric("Geometric Mean Affinity", f"{cons.get('geometric_mean_nm', 0):.2f} nM")
        with col3:
            st.metric("Potency Class", cons.get("potency_class", "Unknown"))
        with col4:
            st.metric("Methods Used", cons.get("methods_used", 0))
        
        if cons.get("range_nm"):
            st.caption(f"Range: {cons['range_nm'][0]:.2f} - {cons['range_nm'][1]:.2f} nM")
    
    # Individual methods
    st.subheader("Individual Method Estimates")
    df = pd.DataFrame(individual)
    if not df.empty:
        display_df = df[["method", "estimated_affinity_nm", "estimated_pkd", "confidence", "details"]].copy()
        display_df.columns = ["Method", "Affinity (nM)", "pKd", "Confidence", "Details"]
        display_df["Affinity (nM)"] = display_df["Affinity (nM)"].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
        )
        display_df["pKd"] = display_df["pKd"].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Visualization
    fig = visualization.create_affinity_scatter(individual)
    st.plotly_chart(fig, use_container_width=True)
    
    # Ligand efficiency
    if consensus.get("ligand_efficiency"):
        st.subheader("Ligand Efficiency Metrics")
        le = consensus["ligand_efficiency"]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("LE", f"{le.get('le', 0):.3f}")
        with col2:
            st.metric("LLE", f"{le.get('lle', 0):.3f}")
        with col3:
            st.metric("BE", f"{le.get('be', 0):.3f}")
        with col4:
            st.metric("SEI", f"{le.get('sei', 0):.3f}")


def _render_model_training_tab() -> None:
    """Model training interface."""
    st.subheader("Model Training")
    
    training_mode = st.radio(
        "Training data source",
        ["Sample data (demo)", "ChEMBL bioactivities", "Local database", "Upload CSV"],
        horizontal=True,
        key="dtp_train_mode",
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        model_type = st.selectbox(
            "Model type",
            ["Random Forest", "Gradient Boosting", "Logistic Regression"],
            key="dtp_train_model_type",
        )
        model_type_map = {
            "Random Forest": "random_forest",
            "Gradient Boosting": "gradient_boosting",
            "Logistic Regression": "logistic_regression",
        }
        
        use_fp = st.checkbox("Use molecular fingerprints", value=True, key="dtp_train_use_fp")
        fp_type = st.selectbox("Fingerprint type", ["Morgan (ECFP4)", "MACCS Keys", "RDKit"],
                              key="dtp_train_fp_type")
        fp_type_map = {
            "Morgan (ECFP4)": "morgan",
            "MACCS Keys": "maccs",
            "RDKit": "rdkit",
        }
    
    with col2:
        if training_mode == "ChEMBL bioactivities":
            target_chembl = st.text_input(
                "ChEMBL Target ID",
                placeholder="e.g., CHEMBL203 (EGFR)",
                key="dtp_train_chembl_target",
            )
            activity_threshold = st.number_input(
                "Activity threshold (nM)",
                1, 100000, 1000,
                key="dtp_train_threshold",
            )
            limit = st.number_input("Max activities", 100, 10000, 500, key="dtp_train_limit")
        
        elif training_mode == "Upload CSV":
            uploaded_file = st.file_uploader(
                "Upload training data (CSV with 'smiles' and 'label' columns)",
                type=["csv"],
                key="dtp_train_file",
            )
        
        elif training_mode == "Local database":
            st.info("Uses drug-target interactions from local database with binding affinity data")
    
    if st.button("🤖 Train Model", type="primary", use_container_width=True, key="dtp_train_run"):
        _perform_training(training_mode, model_type_map[model_type], use_fp, fp_type_map[fp_type])
    
    # Display training results
    if st.session_state.dtp_training_results:
        _display_training_results(st.session_state.dtp_training_results)


def _perform_training(
    mode: str,
    model_type: str,
    use_fp: bool,
    fp_type: str,
) -> None:
    """Train the model."""
    engine = prediction_engine.DrugTargetPredictionEngine(
        model_type=model_type,
        use_fingerprints=use_fp,
        fp_type=fp_type,
    )
    
    with st.spinner("Training model..."):
        try:
            if mode == "Sample data (demo)":
                results = engine.predictor.train(*ml_models.create_sample_training_data(), validate=True)
            
            elif mode == "ChEMBL bioactivities":
                target_chembl = st.session_state.get("dtp_train_chembl_target", "")
                if not target_chembl:
                    st.error("Please provide ChEMBL target ID")
                    return
                threshold = st.session_state.get("dtp_train_threshold", 1000)
                limit = st.session_state.get("dtp_train_limit", 500)
                results = engine.train_from_chembl(target_chembl, threshold, limit)
            
            elif mode == "Local database":
                results = engine.train_from_local_database()
            
            elif mode == "Upload CSV":
                uploaded = st.session_state.get("dtp_train_file")
                if not uploaded:
                    st.error("Please upload a CSV file")
                    return
                df = pd.read_csv(uploaded)
                if "smiles" not in df.columns or "label" not in df.columns:
                    st.error("CSV must contain 'smiles' and 'label' columns")
                    return
                results = engine.predictor.train(df["smiles"].tolist(), df["label"].tolist(), validate=True)
            
            # Update session state
            st.session_state.dtp_engine = engine
            st.session_state.dtp_training_results = results
            st.session_state.dtp_model_type = model_type
            st.session_state.dtp_use_fingerprints = use_fp
            st.session_state.dtp_fp_type = fp_type
            
            st.success("Model trained successfully!")
            
        except Exception as e:
            logger.error("Training failed: %s", e)
            st.error(f"Training failed: {e}")


def _display_training_results(results: dict[str, Any]) -> None:
    """Display training results."""
    st.subheader("Training Results")
    
    # Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Accuracy", f"{results.get('train_accuracy', 0):.3f}")
    with col2:
        st.metric("Precision", f"{results.get('train_precision', 0):.3f}")
    with col3:
        st.metric("Recall", f"{results.get('train_recall', 0):.3f}")
    with col4:
        st.metric("F1", f"{results.get('train_f1', 0):.3f}")
    with col5:
        st.metric("ROC-AUC", f"{results.get('train_roc_auc', 0):.3f}")
    
    if "cv_roc_auc_mean" in results:
        st.metric("CV ROC-AUC", f"{results['cv_roc_auc_mean']:.3f} ± {results.get('cv_roc_auc_std', 0):.3f}")
    
    # Feature importance
    if "feature_importance" in results:
        fig = visualization.create_feature_importance_chart(results["feature_importance"])
        st.plotly_chart(fig, use_container_width=True)
    
    # Training history chart
    fig = visualization.create_training_history_chart(results)
    st.plotly_chart(fig, use_container_width=True)


def _render_visualizations_tab() -> None:
    """Visualizations tab."""
    st.subheader("Visualizations")
    
    viz_type = st.selectbox(
        "Visualization type",
        ["Prediction Confidence", "Target Profile Heatmap", "Feature Importance", 
         "Drug Property Radar", "Interaction Network", "Model Comparison"],
        key="dtp_viz_type",
    )
    
    if viz_type == "Prediction Confidence" and st.session_state.dtp_predictions:
        fig = visualization.create_prediction_confidence_chart([st.session_state.dtp_predictions])
        st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Target Profile Heatmap" and st.session_state.dtp_target_profile:
        fig = visualization.create_target_profile_heatmap(st.session_state.dtp_target_profile["predictions"])
        st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Feature Importance" and st.session_state.dtp_training_results:
        fig = visualization.create_feature_importance_chart(
            st.session_state.dtp_training_results.get("feature_importance", [])
        )
        st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Drug Property Radar":
        drug_smiles = st.text_input("Drug SMILES", key="dtp_radar_smiles")
        if drug_smiles:
            fig = visualization.create_drug_property_radar(drug_smiles)
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Interaction Network":
        if st.session_state.dtp_target_profile:
            fig = visualization.create_interaction_network(
                st.session_state.dtp_target_profile["predictions"]
            )
            st.plotly_chart(fig, use_container_width=True)
        elif st.session_state.dtp_batch_results:
            fig = visualization.create_interaction_network(
                st.session_state.dtp_batch_results["predictions"]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run a target profile or batch screening first")
    
    elif viz_type == "Model Comparison":
        st.info("Train multiple models to compare")


def _render_reports_tab() -> None:
    """Reports tab."""
    st.subheader("Report Generation")
    
    report_type = st.selectbox(
    "Report type",
    ["Single Prediction", "Batch Screening", "Target Profile", "Affinity Estimation", "Model Performance"],
    key="dtp_report_type",
)
    
    output_format = st.selectbox(
        "Output format",
        ["CSV", "JSON", "TSV"],
        key="dtp_report_format",
    )
    
    if st.button("📄 Generate Report", type="primary", key="dtp_report_gen"):
        _generate_report(report_type, output_format.lower())
    
    # Download buttons
    if st.session_state.get("dtp_last_report_path"):
        with open(st.session_state.dtp_last_report_path, "rb") as f:
            st.download_button(
                "⬇️ Download Report",
                f.read(),
                file_name=Path(st.session_state.dtp_last_report_path).name,
                mime="text/csv" if output_format == "CSV" else "application/json",
            )


def _generate_report(report_type: str, format: str) -> None:
    """Generate report based on type."""
    from pathlib import Path
    import tempfile
    
    output_dir = Path(tempfile.gettempdir()) / "geneai_reports"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        if report_type == "Single Prediction" and st.session_state.dtp_predictions:
            path = output_dir / f"single_prediction_{timestamp}.{format}"
            report_generator.generate_prediction_report_csv(
                [st.session_state.dtp_predictions], path
            )
        
        elif report_type == "Batch Screening" and st.session_state.dtp_batch_results:
            path = output_dir / f"batch_screening_{timestamp}.{format}"
            report_generator.generate_batch_screening_report(
                [],  # drug_list not stored
                st.session_state.dtp_batch_results["target"],
                st.session_state.dtp_batch_results["predictions"],
                path,
            )
        
        elif report_type == "Target Profile" and st.session_state.dtp_target_profile:
            path = output_dir / f"target_profile_{timestamp}.{format}"
            report_generator.generate_target_profile_report(
                st.session_state.dtp_target_profile["drug"],
                st.session_state.dtp_target_profile["predictions"],
                path,
                format=format,
            )
        
        elif report_type == "Affinity Estimation" and st.session_state.dtp_affinity_results:
            path = output_dir / f"affinity_estimation_{timestamp}.{format}"
            report_generator.generate_affinity_report_csv(
                st.session_state.dtp_affinity_results.get("individual", []),
                path,
            )
        
        elif report_type == "Model Performance" and st.session_state.dtp_training_results:
            path = output_dir / f"model_performance_{timestamp}.{format}"
            report_generator.generate_model_performance_report(
                st.session_state.dtp_training_results,
                st.session_state.dtp_training_results.get("feature_importance"),
                path,
            )
        
        else:
            st.warning("No data available for selected report type")
            return
        
        st.session_state.dtp_last_report_path = str(path)
        st.success(f"Report generated: {path.name}")
        
    except Exception as e:
        logger.error("Report generation failed: %s", e)
        st.error(f"Report generation failed: {e}")


def _render_settings_tab() -> None:
    """Settings tab."""
    st.subheader("Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Model Settings**")
        model_type = st.selectbox(
            "Default model type",
            ["Random Forest", "Gradient Boosting", "Logistic Regression"],
            index=["random_forest", "gradient_boosting", "logistic_regression"].index(
                st.session_state.get("dtp_model_type", "random_forest")
            ),
            key="dtp_settings_model",
        )
        model_type_map = {
            "Random Forest": "random_forest",
            "Gradient Boosting": "gradient_boosting",
            "Logistic Regression": "logistic_regression",
        }
        st.session_state.dtp_model_type = model_type_map[model_type]
        
        use_fp = st.checkbox(
            "Use molecular fingerprints",
            value=st.session_state.get("dtp_use_fingerprints", True),
            key="dtp_settings_fp",
        )
        st.session_state.dtp_use_fingerprints = use_fp
        
        fp_type = st.selectbox(
            "Fingerprint type",
            ["Morgan (ECFP4)", "MACCS Keys", "RDKit"],
            index=["morgan", "maccs", "rdkit"].index(
                st.session_state.get("dtp_fp_type", "morgan")
            ),
            key="dtp_settings_fp_type",
        )
        fp_type_map = {
            "Morgan (ECFP4)": "morgan",
            "MACCS Keys": "maccs",
            "RDKit": "rdkit",
        }
        st.session_state.dtp_fp_type = fp_type_map[fp_type]
    
    with col2:
        st.markdown("**System Info**")
        st.write(f"RDKit Available: {'✅' if is_rdkit_available() else '❌'}")
        st.write(f"scikit-learn Available: {'✅' if ml_models.SKLEARN_AVAILABLE else '❌'}")
        
        if st.session_state.dtp_engine:
            info = st.session_state.dtp_engine.get_model_info()
            st.json(info)
        
        if st.button("🔄 Reset Engine", key="dtp_reset_engine"):
            st.session_state.dtp_engine = None
            st.success("Engine reset. Will be recreated with new settings.")
    
    st.markdown("---")
    st.markdown("**About**")
    st.markdown("""
    **Drug-Target Interaction Prediction Engine (Phase 4.7)**
    
    This module provides AI-powered prediction of drug-target interactions using:
    - Molecular descriptors (RDKit)
    - Molecular fingerprints (Morgan/ECFP4, MACCS, RDKit)
    - Machine learning models (Random Forest, Gradient Boosting, Logistic Regression)
    - Binding affinity estimation (literature, rule-based, ML)
    - Integration with ChEMBL, PubChem, and local databases
    
    **Data Sources:**
    - ChEMBL bioactivity data
    - PubChem compound information
    - Local drug-target interaction database
    - Literature-curated binding affinities
    """)


# Need to import datetime for reports
from datetime import datetime
from pathlib import Path