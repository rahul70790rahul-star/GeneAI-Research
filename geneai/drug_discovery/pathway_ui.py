"""Streamlit UI for biological pathway analysis."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from geneai.drug_discovery import api_clients

logger = logging.getLogger(__name__)


def render_pathway_analysis_page() -> None:
    """Render the Pathway Analysis page."""
    st.subheader("Pathway Analysis")
    st.write(
        "Explore biological pathways associated with genes from the current "
        "Disease Analysis result. Pathways come from Reactome enrichment and "
        "Gene Ontology annotations."
    )
    st.info(
        "Research use only. Pathway enrichment does not establish disease "
        "mechanism or therapeutic relevance."
    )

    disease_result = st.session_state.get("disease_analysis_result")
    if not isinstance(disease_result, dict):
        st.warning("Run **Drug Discovery · Disease Analysis** first to retrieve pathway data.")
        return

    disease = disease_result.get("disease", {})
    st.caption(
        f"Disease: {disease.get('name', 'Unknown')} "
        f"({disease.get('disease_id', 'n/a')})"
    )

    pathways = (disease_result.get("pathways") or {}).get("pathways", [])
    go_annotations = disease_result.get("go_annotations", [])

    tab_reactome, tab_go = st.tabs(["Reactome Pathways", "Gene Ontology"])

    with tab_reactome:
        st.write("Reactome over-representation results for the disease gene set.")
        if pathways:
            df = pd.DataFrame(pathways)
            display_cols = [
                c for c in ("pathway_id", "name", "p_value", "fdr", "genes_found", "total")
                if c in df.columns
            ]
            if display_cols:
                st.dataframe(df[display_cols], hide_index=True, alt="Reactome pathways")
                st.download_button(
                    "Download pathway CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="geneai_reactome_pathways.csv",
                    mime="text/csv",
                    key="download_reactome_csv",
                )
            else:
                st.dataframe(df, hide_index=True, alt="Reactome pathways")
        else:
            st.info("No Reactome pathways available for this disease.")
        warning = (disease_result.get("pathways") or {}).get("warning")
        if warning:
            st.caption(warning)

    with tab_go:
        st.write("Gene Ontology annotations for genes in the current result.")
        if go_annotations:
            df = pd.DataFrame(go_annotations)
            display_cols = [
                c for c in ("gene_symbol", "go_id", "go_name", "aspect", "evidence_code", "reference")
                if c in df.columns
            ]
            if display_cols:
                st.dataframe(df[display_cols], hide_index=True, alt="GO annotations")
            else:
                st.dataframe(df, hide_index=True, alt="GO annotations")
            st.download_button(
                "Download GO annotations CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="geneai_go_annotations.csv",
                mime="text/csv",
                key="download_go_csv",
            )
        else:
            st.info("No Gene Ontology annotations available.")

    st.divider()
    st.subheader("Pathway Enrichment Status")
    source_status = disease_result.get("data_sources", [])
    for source in source_status:
        if source.get("source") in ("Reactome", "QuickGO / GOA"):
            st.write(
                f"- {source.get('source')}: {source.get('status')} "
                f"(records: {source.get('record_count', 0)})"
            )
            if source.get("error"):
                st.error(f"Error: {source['error']}")
