"""ADMET Streamlit Dashboard - Module 6: Interactive UI."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import streamlit as st
from streamlit import session_state as ss

from geneai.admet_prediction.admet_engine import ADMETPredictionEngine, create_admet_engine
from geneai.admet_prediction.admet_scoring import (
    OverallADMETScore,
    calculate_overall_admet_score,
    compare_compounds,
    generate_risk_report,
)
from geneai.admet_prediction.data_integration import (
    get_pubchem_compound_by_cid,
    get_pubchem_compound_by_smiles,
    get_chembl_molecule_by_chembl_id,
    merge_compound_data,
    search_pubchem_by_name,
    search_chembl_by_smiles,
)
from geneai.admet_prediction.database import (
    store_admet_prediction_run,
    store_admet_predictions,
    store_admet_score,
    get_recent_runs,
    search_admet_runs,
    initialize_admet_database,
)
from geneai.admet_prediction.molecular_properties import (
    calculate_molecular_properties,
    assess_drug_likeness,
)
from geneai.admet_prediction.report_generator import (
    generate_admet_csv_report,
    generate_admet_pdf_report,
    generate_admet_json_report,
)
from geneai.config import APP_NAME

logger = logging.getLogger(__name__)


def render_admet_dashboard() -> None:
    """Render the main ADMET prediction dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - ADMET Prediction",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🧪 ADMET Prediction Engine")
    st.caption("Advanced AI-based Absorption, Distribution, Metabolism, Excretion, and Toxicity prediction")
    
    # Initialize session state
    if "admet_results" not in ss:
        ss.admet_results = {}
    if "admet_scores" not in ss:
        ss.admet_scores = {}
    if "admet_compounds" not in ss:
        ss.admet_compounds = []
    
    # Sidebar
    with st.sidebar:
        st.header("🔬 Input Methods")
        input_method = st.radio(
            "Select Input Method",
            ["SMILES Input", "Compound Name Search", "PubChem CID", "ChEMBL ID", "Batch Comparison"],
            key="admet_input_method",
        )
        
        st.divider()
        st.header("⚙️ Settings")
        use_ml = st.checkbox("Use ML Models (when available)", value=True, key="admet_use_ml")
        save_to_db = st.checkbox("Save to Database", value=True, key="admet_save_db")
        
        st.divider()
        st.header("📊 Recent Predictions")
        recent = get_recent_runs(10)
        for run in recent:
            if st.button(f"{run['smiles'][:20]}... ({run['created_at']:.0f})", key=f"recent_{run['run_id']}"):
                _load_run(run["run_id"])
    
    # Main content based on input method
    if input_method == "SMILES Input":
        render_smiles_input(use_ml, save_to_db)
    elif input_method == "Compound Name Search":
        render_name_search(use_ml, save_to_db)
    elif input_method == "PubChem CID":
        render_cid_input(use_ml, save_to_db)
    elif input_method == "ChEMBL ID":
        render_chembl_input(use_ml, save_to_db)
    elif input_method == "Batch Comparison":
        render_batch_comparison()


def render_smiles_input(use_ml: bool, save_to_db: bool) -> None:
    """Render SMILES input interface."""
    st.subheader("📝 SMILES Input")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        smiles = st.text_area(
            "Enter SMILES",
            placeholder="e.g., CC(=O)OC1=CC=CC=C1C(=O)O (Aspirin)",
            height=100,
            key="admet_smiles_input",
        )
    with col2:
        st.write("")
        st.write("")
        compound_name = st.text_input("Compound Name (optional)", key="admet_compound_name")
        predict_btn = st.button("🔮 Predict ADMET", type="primary", use_container_width=True, key="admet_predict_smiles")
    
    # Example SMILES
    with st.expander("📋 Example SMILES"):
        examples = {
            "Aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
            "Caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
            "Ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
            "Paracetamol": "CC(=O)NC1=CC=C(C=C1)O",
            "Warfarin": "CC(=O)CC(C1=CC=CC=C1)C2=CC(=O)CC3=C2C=CC=C3",
        }
        cols = st.columns(len(examples))
        for i, (name, smi) in enumerate(examples.items()):
            if cols[i].button(name, key=f"ex_{name}"):
                ss.admet_smiles_input = smi
                ss.admet_compound_name = name
                st.rerun()
    
    if predict_btn and smiles.strip():
        with st.spinner("Running ADMET predictions..."):
            run_prediction(smiles.strip(), compound_name.strip() if compound_name else None, use_ml, save_to_db)


def render_name_search(use_ml: bool, save_to_db: bool) -> None:
    """Render compound name search."""
    st.subheader("🔍 Compound Name Search")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        name = st.text_input("Compound Name", placeholder="e.g., aspirin, ibuprofen", key="admet_name_search")
    with col2:
        st.write("")
        search_btn = st.button("🔍 Search", type="primary", use_container_width=True, key="admet_search_name")
    
    if search_btn and name.strip():
        with st.spinner(f"Searching PubChem for '{name}'..."):
            results = search_pubchem_by_name(name.strip(), limit=10)
        
        if results:
            st.success(f"Found {len(results)} compound(s)")
            for i, compound in enumerate(results):
                with st.expander(f"{compound.get('iupac_name', 'Unknown')} (CID: {compound.get('cid')})"):
                    cols = st.columns([2, 1, 1])
                    cols[0].write(f"**SMILES:** {compound.get('canonical_smiles', 'N/A')[:80]}...")
                    cols[0].write(f"**MW:** {compound.get('molecular_weight', 'N/A')} | **LogP:** {compound.get('logp', 'N/A')}")
                    if cols[1].button("Predict ADMET", key=f"pred_name_{i}"):
                        run_prediction(compound["canonical_smiles"], compound.get("iupac_name"), use_ml, save_to_db)
                    if cols[2].button("View Details", key=f"detail_name_{i}"):
                        st.json(compound)
        else:
            st.warning("No compounds found")


def render_cid_input(use_ml: bool, save_to_db: bool) -> None:
    """Render PubChem CID input."""
    st.subheader("🆔 PubChem CID Lookup")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        cid = st.text_input("PubChem CID", placeholder="e.g., 2244 (Aspirin)", key="admet_cid_input")
    with col2:
        st.write("")
        lookup_btn = st.button("🔍 Lookup", type="primary", use_container_width=True, key="admet_lookup_cid")
    
    if lookup_btn and cid.strip():
        with st.spinner(f"Fetching CID {cid}..."):
            compound = get_pubchem_compound_by_cid(cid.strip())
        
        if compound:
            st.success(f"Found: {compound.get('iupac_name', 'Unknown')}")
            cols = st.columns([2, 1, 1])
            cols[0].write(f"**SMILES:** {compound.get('canonical_smiles', 'N/A')[:80]}...")
            cols[0].write(f"**MW:** {compound.get('molecular_weight', 'N/A')} | **LogP:** {compound.get('logp', 'N/A')}")
            if cols[1].button("Predict ADMET", key="pred_cid"):
                run_prediction(compound["canonical_smiles"], compound.get("iupac_name"), use_ml, save_to_db)
            if cols[2].button("View Details", key="detail_cid"):
                st.json(compound)
        else:
            st.error("Compound not found")


def render_chembl_input(use_ml: bool, save_to_db: bool) -> None:
    """Render ChEMBL ID input."""
    st.subheader("🧬 ChEMBL ID Lookup")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        chembl_id = st.text_input("ChEMBL ID", placeholder="e.g., CHEMBL25 (Aspirin)", key="admet_chembl_input")
    with col2:
        st.write("")
        lookup_btn = st.button("🔍 Lookup", type="primary", use_container_width=True, key="admet_lookup_chembl")
    
    if lookup_btn and chembl_id.strip():
        with st.spinner(f"Fetching {chembl_id}..."):
            compound = get_chembl_molecule_by_chembl_id(chembl_id.strip())
        
        if compound:
            st.success(f"Found: {compound.get('pref_name', 'Unknown')}")
            cols = st.columns([2, 1, 1])
            cols[0].write(f"**SMILES:** {compound.get('canonical_smiles', 'N/A')[:80]}...")
            cols[0].write(f"**MW:** {compound.get('molecular_weight', 'N/A')} | **LogP:** {compound.get('logp', 'N/A')}")
            if cols[1].button("Predict ADMET", key="pred_chembl"):
                run_prediction(compound["canonical_smiles"], compound.get("pref_name"), use_ml, save_to_db)
            if cols[2].button("View Details", key="detail_chembl"):
                st.json(compound)
        else:
            st.error("Compound not found")


def render_batch_comparison() -> None:
    """Render batch compound comparison."""
    st.subheader("📊 Batch Comparison")
    
    st.write("Enter multiple SMILES (one per line) to compare ADMET profiles")
    
    batch_input = st.text_area(
        "SMILES List",
        placeholder="CC(=O)OC1=CC=CC=C1C(=O)O\nCN1C=NC2=C1C(=O)N(C(=O)N2C)C\nCC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
        height=150,
        key="admet_batch_input",
    )
    
    names_input = st.text_input(
        "Names (comma-separated, optional)",
        placeholder="Aspirin, Caffeine, Ibuprofen",
        key="admet_batch_names",
    )
    
    if st.button("🔮 Compare All", type="primary", key="admet_batch_predict"):
        smiles_list = [s.strip() for s in batch_input.split("\n") if s.strip()]
        names_list = [n.strip() for n in names_input.split(",")] if names_input else None
        
        if len(smiles_list) < 2:
            st.warning("Please enter at least 2 SMILES for comparison")
            return
        
        if names_list and len(names_list) != len(smiles_list):
            st.warning("Number of names must match number of SMILES")
            return
        
        results = []
        progress = st.progress(0)
        
        for i, smiles in enumerate(smiles_list):
            progress.progress((i + 1) / len(smiles_list))
            result = predict_admet(smiles)
            results.append(result)
        
        progress.empty()
        
        # Compare
        names = names_list or [f"Compound {i+1}" for i in range(len(smiles_list))]
        scores = [calculate_overall_admet_score(r) for r in results]
        comparison = compare_compounds(results, names)
        
        st.session_state["admet_batch_comparison"] = {
            "results": results,
            "scores": scores,
            "comparison": comparison,
            "names": names,
        }
        st.success("Comparison complete!")
    
    # Display comparison if available
    if "admet_batch_comparison" in st.session_state:
        render_batch_results(st.session_state["admet_batch_comparison"])


def render_batch_results(data: dict[str, Any]) -> None:
    """Render batch comparison results."""
    comparison = data["comparison"]
    names = data["names"]
    scores = data["scores"]
    
    st.divider()
    st.subheader("📈 Comparison Results")
    
    # Ranking table
    ranking_data = []
    for r in comparison["ranking"]:
        ranking_data.append({
            "Rank": r["rank"],
            "Compound": r["name"],
            "Overall Score": f"{r['overall_score']:.3f}",
            "Risk": r["risk"],
        })
    
    st.dataframe(ranking_data, use_container_width=True, hide_index=True)
    
    # Category comparison chart
    st.write("**Category Scores**")
    cat_data = comparison["category_comparison"]
    if cat_data:
        import pandas as pd
        df = pd.DataFrame(cat_data, index=[cat.capitalize() for cat in cat_data.keys()]).T
        st.bar_chart(df)
    
    # Detailed comparison
    with st.expander("📋 Detailed Comparison"):
        for name in names:
            idx = names.index(name)
            score = scores[idx]
            st.write(f"### {name}")
            st.write(f"Overall: {score.overall_score:.3f} ({score.risk_classification})")
            for cat, cat_score in score.category_scores.items():
                st.write(f"  **{cat.capitalize()}**: {cat_score.score:.3f} [{cat_score.risk_level}]")


def run_prediction(smiles: str, name: str | None, use_ml: bool, save_to_db: bool) -> None:
    """Run ADMET prediction and display results."""
    try:
        # Run prediction
        result = predict_admet(smiles)
        
        # Calculate score
        score = calculate_overall_admet_score(result)
        
        # Store in session
        run_id = str(uuid.uuid4())[:8]
        ss.admet_results[run_id] = result
        ss.admet_scores[run_id] = score
        
        if name:
            ss.admet_compounds.append({"run_id": run_id, "name": name, "smiles": smiles})
        
        # Save to database
        if save_to_db:
            store_admet_prediction_run(
                run_id,
                smiles,
                result.molecular_properties.get("canonical_smiles"),
                result.molecular_properties.get("inchikey"),
                result.molecular_properties,
                result.molecular_properties.get("drug_likeness"),
            )
            store_admet_predictions(run_id, [
                {
                    "endpoint": p.endpoint,
                    "category": p.category,
                    "value": p.value,
                    "probability": p.probability,
                    "prediction": p.prediction,
                    "confidence": p.confidence,
                    "source": p.method,
                    "details": p.details,
                }
                for p in result.predictions
            ])
            store_admet_score(run_id, {
                "overall_score": score.overall_score,
                "risk_classification": score.risk_classification,
                "drug_likeness_score": score.drug_likeness_score,
                "category_scores": {cat: cs.score for cat, cs in score.category_scores.items()},
                "summary": score.summary,
            })
        
        # Display results
        display_results(run_id, result, score, name)
        
    except Exception as e:
        logger.exception("Prediction failed")
        st.error(f"Prediction failed: {e}")


def display_results(run_id: str, result, score: OverallADMETScore, name: str | None) -> None:
    """Display prediction results."""
    st.divider()
    
    # Header
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.subheader(f"Results: {name or 'Unknown Compound'}")
        st.code(result.smiles, language=None)
    with col2:
        # Overall score gauge
        risk_color = {
            "Favorable": "🟢",
            "Acceptable": "🟡",
            "Concerning": "🟠",
            "High Risk": "🔴",
        }.get(score.risk_classification, "⚪")
        st.metric("Overall Score", f"{score.overall_score:.3f}", delta=risk_color)
        st.metric("Risk Level", score.risk_classification)
    with col3:
        st.metric("Drug-Likeness", f"{score.drug_likeness_score:.3f}")
        st.metric("Endpoints", score.summary.get("total_endpoints", 0))
    
    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", "🧪 Molecular Props", "📈 ADMET Details", "⚠️ Risk Report", "📄 Reports", "💾 Export"
    ])
    
    with tab1:
        render_overview_tab(score)
    
    with tab2:
        render_molecular_properties_tab(result)
    
    with tab3:
        render_admet_details_tab(result, score)
    
    with tab4:
        render_risk_report_tab(score)
    
    with tab5:
        render_reports_tab(run_id, result, score, name)
    
    with tab6:
        render_export_tab(run_id, result, score, name)


def render_overview_tab(score: OverallADMETScore) -> None:
    """Render overview tab with category scores."""
    st.subheader("Category Scores")
    
    # Radar chart data
    cats = list(score.category_scores.keys())
    scores = [score.category_scores[cat].score for cat in cats]
    risk_levels = [score.category_scores[cat].risk_level for cat in cats]
    
    # Bar chart
    import pandas as pd
    df = pd.DataFrame({
        "Category": [c.capitalize() for c in cats],
        "Score": scores,
        "Risk": risk_levels,
    })
    st.bar_chart(df.set_index("Category")["Score"])
    
    # Detailed table
    st.write("**Detailed Breakdown**")
    for cat, cat_score in score.category_scores.items():
        with st.expander(f"{cat.capitalize()} - Score: {cat_score.score:.3f} [{cat_score.risk_level}]"):
            ep_data = []
            for es in cat_score.endpoint_scores:
                ep_data.append({
                    "Endpoint": es.endpoint.replace("_", " ").title(),
                    "Score": f"{es.normalized_score:.3f}",
                    "Raw Prob": f"{es.raw_score:.3f}",
                    "Confidence": es.confidence.capitalize(),
                    "Favorable": "✅" if es.is_favorable else "❌",
                })
            st.dataframe(ep_data, use_container_width=True, hide_index=True)


def render_molecular_properties_tab(result) -> None:
    """Render molecular properties tab."""
    st.subheader("Molecular Properties")
    props = result.molecular_properties
    
    # Properties grid
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Molecular Weight", f"{props.get('molecular_weight', 0):.2f} Da")
        st.metric("LogP (XLogP3)", f"{props.get('logp', 0):.2f}")
        st.metric("TPSA", f"{props.get('tpsa', 0):.2f} Å²")
    
    with col2:
        st.metric("H-Bond Donors", props.get("hbd", 0))
        st.metric("H-Bond Acceptors", props.get("hba", 0))
        st.metric("Rotatable Bonds", props.get("rotatable_bonds", 0))
    
    with col3:
        st.metric("Molecular Formula", props.get("molecular_formula", "N/A"))
        st.metric("Exact Mass", f"{props.get('exact_mass', 0):.2f}")
        st.metric("Charge", props.get("charge", 0))
    
    # Drug-likeness
    st.divider()
    st.subheader("Drug-Likeness Assessment")
    dl = props.get("drug_likeness", {})
    
    if dl:
        for rule_name, rule_data in dl.items():
            if isinstance(rule_data, dict) and "passes" in rule_data:
                passed = rule_data["passes"]
                details = rule_data.get("details", {})
                
                with st.expander(f"{rule_name.capitalize()}: {'✅ PASS' if passed else '❌ FAIL'}"):
                    for key, val in details.items():
                        status = "✅" if val else "❌"
                        st.write(f"  {status} {key.replace('_', ' ').title()}")


def render_admet_details_tab(result, score: OverallADMETScore) -> None:
    """Render detailed ADMET predictions tab."""
    st.subheader("All ADMET Endpoints")
    
    # Group by category
    categories = ["absorption", "distribution", "metabolism", "excretion", "toxicity"]
    cat_names = {
        "absorption": "🧫 Absorption",
        "distribution": "🎯 Distribution",
        "metabolism": "⚙️ Metabolism",
        "excretion": "🚽 Excretion",
        "toxicity": "☠️ Toxicity",
    }
    
    for cat in categories:
        cat_score = score.category_scores.get(cat)
        if not cat_score or not cat_score.endpoint_scores:
            continue
        
        with st.expander(f"{cat_names[cat]} ({cat_score.favorable_count}/{cat_score.total_count} favorable)"):
            for es in cat_score.endpoint_scores:
                pred = next((p for p in result.predictions if p.endpoint == es.endpoint), None)
                
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                col1.write(f"**{es.endpoint.replace('_', ' ').title()}**")
                
                if pred:
                    color = "green" if es.is_favorable else "red"
                    col2.markdown(f":{color}[{pred.prediction}]")
                    col3.write(f"Prob: {es.raw_score:.3f}")
                    col4.write(f"Conf: {es.confidence.capitalize()}")
                
                if pred and pred.details:
                    with st.popover("Details"):
                        st.json(pred.details)


def render_risk_report_tab(score: OverallADMETScore) -> None:
    """Render risk assessment report."""
    st.subheader("Risk Assessment Report")
    
    report_text = generate_risk_report(score)
    st.code(report_text, language=None)
    
    # Quick summary
    st.divider()
    st.write("**Quick Summary**")
    
    high_risk_cats = [cat for cat, cs in score.category_scores.items() if cs.risk_level == "High"]
    if high_risk_cats:
        st.error(f"⚠️ High Risk Categories: {', '.join(high_risk_cats)}")
    
    mod_risk_cats = [cat for cat, cs in score.category_scores.items() if cs.risk_level == "Moderate"]
    if mod_risk_cats:
        st.warning(f"⚠️ Moderate Risk Categories: {', '.join(mod_risk_cats)}")
    
    low_risk_cats = [cat for cat, cs in score.category_scores.items() if cs.risk_level == "Low"]
    if low_risk_cats:
        st.success(f"✅ Low Risk Categories: {', '.join(low_risk_cats)}")


def render_reports_tab(run_id: str, result, score: OverallADMETScore, name: str | None) -> None:
    """Render report generation tab."""
    st.subheader("Generate Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", use_container_width=True, key=f"pdf_{run_id}"):
            with st.spinner("Generating PDF..."):
                pdf_bytes = generate_admet_pdf_report(result, score, name)
            st.download_button(
                "⬇️ Download PDF",
                pdf_bytes,
                file_name=f"admet_report_{name or 'compound'}_{run_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    
    with col2:
        if st.button("📊 Generate CSV Report", use_container_width=True, key=f"csv_{run_id}"):
            with st.spinner("Generating CSV..."):
                csv_str = generate_admet_csv_report(result, score, name)
            st.download_button(
                "⬇️ Download CSV",
                csv_str,
                file_name=f"admet_report_{name or 'compound'}_{run_id}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    
    with col3:
        if st.button("📋 Generate JSON Report", use_container_width=True, key=f"json_{run_id}"):
            with st.spinner("Generating JSON..."):
                json_data = generate_admet_json_report(result, score, name)
            import json
            st.download_button(
                "⬇️ Download JSON",
                json.dumps(json_data, indent=2),
                file_name=f"admet_report_{name or 'compound'}_{run_id}.json",
                mime="application/json",
                use_container_width=True,
            )


def render_export_tab(run_id: str, result, score: OverallADMETScore, name: str | None) -> None:
    """Render data export tab."""
    st.subheader("Data Export")
    
    st.write("**Prediction Data (JSON)**")
    export_data = {
        "run_id": run_id,
        "compound_name": name,
        "smiles": result.smiles,
        "molecular_properties": result.molecular_properties,
        "predictions": [
            {
                "endpoint": p.endpoint,
                "category": p.category,
                "value": p.value,
                "probability": p.probability,
                "prediction": p.prediction,
                "confidence": p.confidence,
                "method": p.method,
            }
            for p in result.predictions
        ],
        "overall_score": score.overall_score,
        "risk_classification": score.risk_classification,
    }
    
    import json
    st.json(export_data, expanded=False)
    
    st.download_button(
        "⬇️ Download Full JSON",
        json.dumps(export_data, indent=2),
        file_name=f"admet_data_{name or 'compound'}_{run_id}.json",
        mime="application/json",
        use_container_width=True,
    )


def _load_run(run_id: str) -> None:
    """Load a previous run from database."""
    # This would fetch from database and populate session state
    st.info(f"Loading run {run_id}... (not fully implemented)")


# Initialize database on import
initialize_admet_database()


if __name__ == "__main__":
    render_admet_dashboard()