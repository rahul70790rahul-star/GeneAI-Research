"""Streamlit UI for the target ranking dashboard."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from geneai.drug_discovery.target_visualization import (
    target_ranking_chart,
    evidence_distribution_chart,
    gene_disease_network_chart,
)

logger = logging.getLogger(__name__)


def render_target_ranking_page() -> None:
    """Render the Target Ranking Dashboard page."""
    st.subheader("Target Ranking Dashboard")
    st.write(
        "Explore prioritized therapeutic targets from the current target "
        "identification result. Filter, compare, and export targets with "
        "their evidence profiles."
    )
    st.info(
        "Research use only. Priority scores are research shortlist indices, "
        "NOT probabilities of clinical success or validated druggability."
    )

    target_result = st.session_state.get("target_identification_result")
    if not isinstance(target_result, dict):
        st.warning(
            "Run **Drug Discovery · Target Identification** first to retrieve "
            "and rank targets."
        )
        return

    targets = target_result.get("targets", [])
    if not targets:
        st.warning("No targets available from the current target identification result.")
        return

    disease = target_result.get("disease", {})
    st.caption(
        f"Disease: {disease.get('name', 'Unknown')} "
        f"({disease.get('disease_id', 'n/a')}) · "
        f"Analysis ID: {target_result.get('analysis_id', 'n/a')}"
    )

    # Filters
    with st.expander("Filter targets", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            min_score = st.slider("Minimum priority index", 0.0, 100.0, 0.0, 1.0, key="rank_min_score")
            tier_filter = st.multiselect(
                "Priority tier",
                ["High research-priority shortlist", "Medium research-priority shortlist", "Low research-priority shortlist", "Not scored"],
                key="rank_tier_filter",
            )
        with f2:
            disease_assoc = st.checkbox("Disease-associated only", value=False, key="rank_disease_assoc")
            has_protein = st.checkbox("Has UniProt annotation", value=False, key="rank_has_protein")
        with f3:
            has_ppi = st.checkbox("Has PPI network evidence", value=False, key="rank_has_ppi")
            has_variant = st.checkbox("Has VCF variants", value=False, key="rank_has_variant")

    df = pd.DataFrame(targets)

    # Apply filters
    if min_score > 0:
        df = df[df["target_research_priority_index"].fillna(0) >= min_score]
    if tier_filter:
        df = df[df["target_research_priority_tier"].isin(tier_filter)]
    if disease_assoc:
        df = df[df.get("disease_association_evidence_score", pd.Series([None]*len(df))).notna()]
    if has_protein:
        df = df[df["uniprot_id"].notna() & (df["uniprot_id"] != "")]
    if has_ppi:
        df = df[df["ppi_interaction_count"].fillna(0) > 0]
    if has_variant:
        df = df[df["vcf_preview_variant_count"].fillna(0) > 0]

    st.write(f"### {len(df)} target(s) after filtering")

    # Charts
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.plotly_chart(
            target_ranking_chart(df.to_dict("records")),
            use_container_width=True,
            key="rank_chart",
        )
    with col_chart2:
        st.plotly_chart(
            evidence_distribution_chart(df.to_dict("records")),
            use_container_width=True,
            key="rank_evidence_chart",
        )

    # Gene-disease network
    st.plotly_chart(
        gene_disease_network_chart(
            df.to_dict("records"),
            disease_name=disease.get("name", "Disease"),
        ),
        use_container_width=True,
        key="rank_network_chart",
    )

    # Target table
    st.write("### Target Details")
    display_cols = [
        c for c in (
            "target_research_rank", "gene_symbol", "gene_name", "ncbi_gene_id",
            "ensembl_gene_id", "uniprot_id", "target_research_priority_index",
            "target_research_priority_tier", "disease_association_evidence_score",
            "genetic_evidence_score", "literature_evidence_score", "ppi_network_score",
            "ppi_interaction_count", "ppi_degree_centrality", "vcf_preview_variant_count",
            "protein_function", "protein_subcellular_location", "go_annotation_count",
        )
        if c in df.columns
    ]
    if display_cols:
        st.dataframe(df[display_cols], hide_index=True, alt="Target ranking details")
        st.download_button(
            "Download targets CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="geneai_target_ranking.csv",
            mime="text/csv",
            key="download_target_ranking_csv",
        )
    else:
        st.dataframe(df, hide_index=True, alt="Target ranking details")

    # Missing evidence per target
    with st.expander("Missing evidence by target"):
        for _, row in df.iterrows():
            missing = row.get("target_missing_evidence_domains", [])
            if missing:
                symbol = row.get("gene_symbol", "Unknown")
                st.write(f"- **{symbol}**: {', '.join(str(m).replace('_', ' ').title() for m in missing)}")

    # Limitations
    with st.expander("Limitations"):
        for limitation in target_result.get("limitations", []):
            st.markdown(f"- {limitation}")
