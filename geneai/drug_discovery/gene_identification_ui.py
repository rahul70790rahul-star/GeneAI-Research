"""Streamlit UI for standalone gene identification and gene-centric research."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.gene_identification import (
    get_gene_function,
    get_gene_identifiers,
    get_gene_information,
    get_expression_information,
    get_scientific_references,
    identify_disease_associated_genes,
    search_diseases_by_gene,
    search_genes_by_disease,
)

logger = logging.getLogger(__name__)


def render_gene_identification_page() -> None:
    """Render the Gene Identification page."""
    st.subheader("Gene Identification")
    st.write(
        "Look up gene identifiers, function, and disease associations from "
        "NCBI Gene, Ensembl, UniProt, and Open Targets. "
        "This is a gene-centric complement to the Disease Analysis workflow."
    )
    st.info(
        "Research use only. Database identifiers and annotations do not establish "
        "disease causality or druggability."
    )

    tab_lookup, tab_disease_genes, tab_gene_diseases, tab_references = st.tabs(
        ["Gene Lookup", "Genes by Disease", "Gene Context", "Scientific References"]
    )

    with tab_lookup:
        st.write("Search for a gene by symbol and retrieve cross-database identifiers.")
        symbol = st.text_input("Gene symbol (e.g. CFTR, TP53)", key="gene_lookup_symbol")
        if st.button("Look up gene", type="primary", key="gene_lookup_button"):
            if not symbol.strip():
                st.error("Enter a gene symbol.")
            else:
                with st.spinner("Retrieving gene information…"):
                    try:
                        info = get_gene_information(symbol.strip())
                        st.session_state["gene_lookup_result"] = info
                    except (ValueError, api_clients.DataSourceError) as exc:
                        st.error(str(exc))

        result = st.session_state.get("gene_lookup_result")
        if isinstance(result, dict):
            st.success(f"Gene: {result.get('gene_symbol', 'Unknown')}")
            col1, col2, col3 = st.columns(3)
            col1.metric("NCBI Gene ID", result.get("ncbi_gene_id") or "Not available")
            col2.metric("Ensembl Gene ID", result.get("ensembl_gene_id") or "Not available")
            col3.metric("UniProt ID", result.get("uniprot_id") or "Not available")
            st.write(f"**Chromosome:** {result.get('chromosome') or 'Not available'}")
            st.write(f"**Organism:** {result.get('organism') or 'Not available'}")
            st.write(f"**Gene name:** {result.get('gene_name') or 'Not available'}")
            with st.expander("Data sources and references"):
                for source in result.get("data_sources", []):
                    st.write(
                        f"- {source.get('source')}: {source.get('status')} "
                        f"(records: {source.get('record_count', 0)})"
                    )
                for url in result.get("source_references", []):
                    st.link_button("Open source record", url)

    with tab_disease_genes:
        st.write("Retrieve genes associated with a disease from Open Targets.")
        disease_id = st.text_input(
            "Disease ID (Open Targets identifier, e.g. EFO_0000001)",
            key="gene_disease_id",
        )
        limit = st.slider("Maximum genes", 1, 100, 20, key="gene_disease_limit")
        if st.button("Find genes", type="primary", key="gene_disease_button"):
            if not disease_id.strip():
                st.error("Enter a disease ID.")
            else:
                with st.spinner("Retrieving gene-disease associations…"):
                    try:
                        result = search_genes_by_disease(disease_id.strip(), limit=limit)
                        st.session_state["gene_disease_result"] = result
                    except (ValueError, api_clients.DataSourceError) as exc:
                        st.error(str(exc))

        result = st.session_state.get("gene_disease_result")
        if isinstance(result, dict):
            disease = result.get("disease", {})
            st.success(f"Disease: {disease.get('name', 'Unknown')} ({disease.get('disease_id', 'n/a')})")
            genes = result.get("genes", [])
            if genes:
                df = pd.DataFrame(genes)
                display_cols = [
                    c for c in ("gene_symbol", "gene_name", "association_score", "ncbi_gene_id", "ensembl_gene_id", "chromosome")
                    if c in df.columns
                ]
                st.dataframe(df[display_cols], hide_index=True, alt="Disease-associated genes")
                st.download_button(
                    "Download gene CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name=f"geneai_genes_by_disease_{disease.get('disease_id', 'disease')}.csv",
                    mime="text/csv",
                    key="download_genes_by_disease_csv",
                )
            else:
                st.info("No genes returned for this disease.")
            with st.expander("Data sources"):
                for source in result.get("data_sources", []):
                    st.write(
                        f"- {source.get('source')}: {source.get('status')} "
                        f"(records: {source.get('record_count', 0)})"
                    )

    with tab_gene_diseases:
        st.write("Resolve a gene to identifiers and annotation context.")
        st.caption(
            "Open Targets v4 GraphQL does not expose a public gene-to-disease "
            "search endpoint in this client. This tab returns identifier context only."
        )
        symbol2 = st.text_input("Gene symbol (e.g. CFTR, TP53)", key="gene_context_symbol")
        if st.button("Resolve gene", type="primary", key="gene_context_button"):
            if not symbol2.strip():
                st.error("Enter a gene symbol.")
            else:
                with st.spinner("Resolving gene context…"):
                    try:
                        result = search_diseases_by_gene(symbol2.strip())
                        st.session_state["gene_context_result"] = result
                    except (ValueError, api_clients.DataSourceError) as exc:
                        st.error(str(exc))

        result = st.session_state.get("gene_context_result")
        if isinstance(result, dict):
            st.write(f"**Gene symbol:** {result.get('gene_symbol', 'Unknown')}")
            st.write(f"**Gene name:** {result.get('gene_name') or 'Not available'}")
            st.write(f"**NCBI Gene ID:** {result.get('ncbi_gene_id') or 'Not available'}")
            st.write(f"**Ensembl Gene ID:** {result.get('ensembl_gene_id') or 'Not available'}")
            st.write(f"**Chromosome:** {result.get('chromosome') or 'Not available'}")
            with st.expander("Data sources"):
                for source in result.get("data_sources", []):
                    st.write(
                        f"- {source.get('source')}: {source.get('status')} "
                        f"(records: {source.get('record_count', 0)})"
                    )
            for limitation in result.get("limitations", []):
                st.caption(f"- {limitation}")

    with tab_references:
        st.write("Search PubMed for publications mentioning a gene and disease terms.")
        symbol3 = st.text_input("Gene symbol", key="gene_ref_symbol")
        ref_limit = st.slider("Maximum publications", 1, 50, 10, key="gene_ref_limit")
        if st.button("Search references", type="primary", key="gene_ref_button"):
            if not symbol3.strip():
                st.error("Enter a gene symbol.")
            else:
                with st.spinner("Searching PubMed…"):
                    try:
                        result = get_scientific_references(symbol3.strip(), limit=ref_limit)
                        st.session_state["gene_ref_result"] = result
                    except (ValueError, api_clients.DataSourceError, RuntimeError) as exc:
                        st.error(str(exc))

        result = st.session_state.get("gene_ref_result")
        if isinstance(result, dict):
            papers = result.get("publications", [])
            st.write(f"**Gene:** {result.get('gene_symbol', 'Unknown')} — {result.get('record_count', 0)} publication(s)")
            if papers:
                for paper in papers:
                    with st.container(border=True):
                        st.write(f"**{paper.get('title', 'Title not available')}**")
                        st.caption(
                            f"{paper.get('authors', '')} · {paper.get('year', '')} · {paper.get('journal', '')}"
                        )
                        st.link_button("Open PubMed record", paper.get("url", ""))
            else:
                st.info("No publications found.")
            for limitation in result.get("limitations", []):
                st.caption(f"- {limitation}")