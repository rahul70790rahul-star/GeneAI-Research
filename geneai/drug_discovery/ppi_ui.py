"""Streamlit UI for protein-protein interaction network analysis."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.ppi_analysis import summarize_ppi_network
from geneai.drug_discovery.target_visualization import ppi_network_chart

logger = logging.getLogger(__name__)


def render_ppi_network_page() -> None:
    """Render the Protein-Protein Interaction Network page."""
    st.subheader("Protein Interaction Network")
    st.write(
        "Explore STRING protein association networks for genes from the current "
        "Disease Analysis result. Experimentally supported interactions are "
        "distinguished from predicted associations."
    )
    st.info(
        "Research use only. STRING edges represent database associations. "
        "Experimental-channel scores are shown separately and do not prove "
        "direct physical interaction or disease mechanism."
    )

    disease_result = st.session_state.get("disease_analysis_result")
    if not isinstance(disease_result, dict):
        st.warning("Run **Drug Discovery · Disease Analysis** first to retrieve gene context.")
        return

    target_result = st.session_state.get("target_identification_result")
    network = target_result.get("ppi_network") if isinstance(target_result, dict) else None

    disease = disease_result.get("disease", {})
    st.caption(
        f"Disease: {disease.get('name', 'Unknown')} "
        f"({disease.get('disease_id', 'n/a')})"
    )

    with st.expander("Configure STRING network", expanded=network is None):
        network_type = st.selectbox(
            "STRING network type",
            ["functional", "physical"],
            key="ppi_network_type",
        )
        required_score = st.slider(
            "Minimum STRING combined score",
            0, 1000, 400, 50,
            key="ppi_required_score",
        )
        if st.button("Retrieve STRING network", type="primary", key="run_ppi_network"):
            genes = disease_result.get("genes", [])
            symbols = [
                str(g.get("gene_symbol", "")).strip().upper()
                for g in genes
                if isinstance(g, dict) and g.get("gene_symbol")
            ][:20]
            if len(symbols) < 2:
                st.error("At least two gene symbols are required for a STRING network request.")
            else:
                with st.spinner("Retrieving STRING network…"):
                    try:
                        edges = api_clients.fetch_string_interactions(
                            symbols, network_type=network_type, required_score=required_score
                        )
                        network = summarize_ppi_network(edges, symbols)
                        if isinstance(target_result, dict):
                            target_result["ppi_network"] = network
                            st.session_state["target_identification_result"] = target_result
                        st.success(f"Retrieved {len(network.get('edges', []))} interaction(s) for {len(network.get('nodes', []))} protein(s).")
                    except (ValueError, api_clients.DataSourceError) as exc:
                        logger.info("STRING network unavailable: %s", exc)
                        st.error(f"STRING network unavailable: {exc}. Ranking continues without network data.")
                        network = None

    if network:
        st.divider()
        st.subheader("Network Summary")
        col1, col2, col3 = st.columns(3)
        col1.metric("Proteins", network.get("node_count", 0))
        col2.metric("Interactions", network.get("edge_count", 0))
        col3.metric("Hub candidates", len(network.get("hub_candidates", [])))

        st.plotly_chart(
            ppi_network_chart(network),
            use_container_width=True,
            key="ppi_network_chart",
        )

        st.write("### Network Nodes")
        nodes = network.get("nodes", [])
        if nodes:
            df = pd.DataFrame(nodes)
            display_cols = [
                c for c in (
                    "gene_symbol", "string_id", "is_input_gene", "interaction_count",
                    "degree_centrality", "weighted_degree", "max_combined_score",
                    "max_experimental_channel_score",
                )
                if c in df.columns
            ]
            st.dataframe(df[display_cols], hide_index=True, alt="PPI network nodes")
            st.download_button(
                "Download PPI nodes CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="geneai_ppi_network_nodes.csv",
                mime="text/csv",
                key="download_ppi_csv",
            )

        st.write("### Hub Proteins")
        hubs = network.get("hub_candidates", [])
        if hubs:
            st.write(", ".join(hubs))
            st.caption("Hubs are ranked by interaction count in the retrieved network only.")

        st.write("### Interaction Edges")
        edges = network.get("edges", [])
        if edges:
            edf = pd.DataFrame(edges)
            edisplay = [
                c for c in (
                    "protein_a", "protein_b", "network_type", "combined_score",
                    "experimental_channel_score",
                )
                if c in edf.columns
            ]
            st.dataframe(edf[edisplay], hide_index=True, alt="PPI interaction edges")

    st.divider()
    with st.expander("Interpretation"):
        st.write(network.get("interpretation", "") if network else "")
        st.write(network.get("centrality_method", "") if network else "")
