"""Streamlit UI for druggability analysis."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from geneai.drug_discovery.druggability_engine import (
    DruggabilityRequest,
    assess_druggability,
    DEFAULT_DRUGGABILITY_WEIGHTS,
)
from geneai.drug_discovery.target_visualization import druggability_gauge

logger = logging.getLogger(__name__)


def render_druggability_analysis_page() -> None:
    """Render the Druggability Analysis page."""
    st.subheader("Druggability Analysis")
    st.write(
        "Evaluate a target's potential druggability using disease association, "
        "genetic evidence, protein function, pathway relevance, PPI network "
        "context, structural information, ligand evidence, and target "
        "accessibility. The output is an explainable research-priority index, "
        "NOT a probability of clinical success."
    )
    st.info(
        "Research use only. This score does not establish druggability, safety, "
        "or clinical effect. Experimental validation is required."
    )

    target_result = st.session_state.get("target_identification_result")
    if not isinstance(target_result, dict):
        st.warning(
            "Run **Drug Discovery · Target Identification** first to retrieve "
            "target candidates. Then return here to assess druggability."
        )
        return

    targets = target_result.get("targets", [])
    if not targets:
        st.warning("No targets available from the current target identification result.")
        return

    disease = target_result.get("disease", {})
    st.caption(
        f"Disease: {disease.get('name', 'Unknown')} "
        f"({disease.get('disease_id', 'n/a')})"
    )

    with st.expander("Configure druggability weights", expanded=True):
        st.caption(
            "Weights apply only to evidence domains returned for a target. "
            "Missing domains are excluded and remaining weights are renormalized."
        )
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            w_disease = st.slider("Disease association", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["disease_association"]), 0.25, key="drug_w_disease")
            w_genetic = st.slider("Genetic evidence", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["genetic_evidence"]), 0.25, key="drug_w_genetic")
        with w2:
            w_protein = st.slider("Protein function", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["protein_function"]), 0.25, key="drug_w_protein")
            w_pathway = st.slider("Pathway relevance", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["pathway_relevance"]), 0.25, key="drug_w_pathway")
        with w3:
            w_ppi = st.slider("PPI network", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["ppi_network"]), 0.25, key="drug_w_ppi")
            w_structural = st.slider("Structural info", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["structural_info"]), 0.25, key="drug_w_structural")
        with w4:
            w_ligand = st.slider("Ligand evidence", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["ligand_evidence"]), 0.25, key="drug_w_ligand")
            w_access = st.slider("Target accessibility", 0.0, 10.0, float(DEFAULT_DRUGGABILITY_WEIGHTS["target_accessibility"]), 0.25, key="drug_w_access")

    weights = {
        "disease_association": w_disease,
        "genetic_evidence": w_genetic,
        "protein_function": w_protein,
        "pathway_relevance": w_pathway,
        "ppi_network": w_ppi,
        "structural_info": w_structural,
        "ligand_evidence": w_ligand,
        "target_accessibility": w_access,
    }

    st.write("### Select Target for Druggability Assessment")
    target_options = [
        f"{t.get('gene_symbol', 'Unknown')} — {t.get('gene_name', '')} (rank {t.get('target_research_rank', '?')})"
        for t in targets
    ]
    selected_idx = st.selectbox("Target", range(len(target_options)), format_func=lambda i: target_options[i], key="druggability_target_select")
    selected_target = targets[selected_idx]

    if st.button("Assess druggability", type="primary", key="run_druggability"):
        request = DruggabilityRequest(target=selected_target, weights=weights)
        with st.spinner("Computing druggability assessment…"):
            try:
                assessment = assess_druggability(request)
                st.session_state["druggability_assessment"] = assessment
            except (ValueError, Exception) as exc:
                logger.exception("Druggability assessment failed")
                st.error(str(exc))

    assessment = st.session_state.get("druggability_assessment")
    if not isinstance(assessment, dict):
        return

    st.divider()
    st.subheader(f"Druggability Assessment: {assessment.get('gene_symbol', 'Unknown')}")

    col1, col2, col3 = st.columns(3)
    index_val = assessment.get("druggability_index")
    col1.metric("Druggability Index", f"{index_val}" if index_val is not None else "Not scored")
    col2.metric("Tier", assessment.get("druggability_tier", "Not scored"))
    col3.metric("Evidence domains", len(assessment.get("druggability_components", {})))

    st.plotly_chart(
        druggability_gauge(index_val),
        use_container_width=True,
        key="druggability_gauge",
    )

    st.write("### Evidence Component Breakdown")
    components = assessment.get("druggability_components", {})
    if components:
        comp_data = []
        for name, comp in components.items():
            comp_data.append({
                "domain": name.replace("_", " ").title(),
                "score": comp.get("score"),
                "weight": comp.get("weight"),
                "weighted_contribution": round(comp.get("score", 0) * comp.get("weight", 0), 3),
            })
        st.dataframe(pd.DataFrame(comp_data), hide_index=True, alt="Druggability components")

    missing = assessment.get("druggability_missing_domains", [])
    if missing:
        st.write("### Missing Evidence Domains")
        for domain in missing:
            st.write(f"- {domain.replace('_', ' ').title()}: no evidence available (excluded from score)")

    st.write("### Assessment Rationale")
    for reason in assessment.get("druggability_rationale", []):
        st.markdown(f"- {reason}")

    st.write("### Structural Evidence")
    struct = assessment.get("structural_evidence", {})
    st.write(f"- PDB structures: {', '.join(struct.get('pdb_ids', [])) or 'None'}")
    st.write(f"- AlphaFold models: {len(struct.get('alpha_fold_models', []))} (computational predictions)")
    st.write(f"- Experimental structure available: {struct.get('has_experimental_structure', False)}")

    st.write("### Ligand / Enzyme Evidence")
    lig = assessment.get("ligand_evidence", {})
    st.write(f"- Interaction count: {lig.get('interaction_count', 0)}")
    st.write(f"- EC numbers: {', '.join(lig.get('ec_numbers', [])) or 'None'}")

    st.write("### Target Accessibility")
    acc = assessment.get("target_accessibility", {})
    if isinstance(acc, dict):
        st.write(f"- Subcellular location: {acc.get('subcellular_location') or 'Not reported'}")
        st.write(f"- Protein family: {', '.join(acc.get('protein_family', [])) or 'Not reported'}")

    st.info(assessment.get("score_interpretation", ""))

    with st.expander("Limitations"):
        for limitation in assessment.get("limitations", []):
            st.markdown(f"- {limitation}")