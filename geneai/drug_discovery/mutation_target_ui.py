"""Streamlit UI for the mutation-to-target mapping workflow."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.drug_discovery.mutation_target_mapping import (
    MutationTargetRequest,
    map_variants_to_targets,
)
from geneai.drug_discovery.target_visualization import (
    variant_type_distribution,
    gene_disease_network_chart,
)

logger = logging.getLogger(__name__)


def render_mutation_target_page() -> None:
    """Render the Mutation-to-Target Analysis page."""
    st.subheader("Mutation Analysis")
    st.write(
        "Connect Phase 3 VCF variants to genes, disease associations, and "
        "potential drug targets. Variant consequences are reported as supplied "
        "in the VCF; no pathogenicity is inferred."
    )
    st.info(
        "Research use only. Not every disease-associated mutation is a druggable "
        "target. This workflow maps variants to genes and evidence contexts."
    )

    vcf_result = st.session_state.get("mutation_vcf_result") or {}
    variants = vcf_result.get("preview", []) if isinstance(vcf_result, dict) else []

    if not variants:
        st.warning("No VCF variants available. Upload and scan a VCF on the **AI Mutation Interpretation** page first.")
        st.stop()

    st.caption(f"{len(variants)} variant(s) from the current VCF preview are available for mapping.")

    disease_id = st.text_input(
        "Disease ID for association context (optional, e.g. EFO_0000001)",
        key="mut_target_disease_id",
    )
    disease_name = st.text_input(
        "Disease name (optional)", key="mut_target_disease_name",
    )
    max_genes = st.slider("Maximum genes to evaluate", 5, 100, 20, key="mut_target_max_genes")

    if st.button("Map variants to targets", type="primary", key="run_mut_target_mapping"):
        request = MutationTargetRequest(
            variants=variants,
            disease_id=disease_id.strip() or None,
            disease_name=disease_name.strip() or None,
            max_genes=max_genes,
        )
        with st.spinner("Mapping variants to genes and disease context…"):
            try:
                result = map_variants_to_targets(request)
                st.session_state["mutation_target_result"] = result
            except (ValueError, Exception) as exc:
                logger.exception("Mutation-to-target mapping failed")
                st.error(str(exc))

    result = st.session_state.get("mutation_target_result")
    if not isinstance(result, dict):
        return

    st.divider()
    st.subheader("Mapping Results")

    col1, col2, col3 = st.columns(3)
    col1.metric("Variants mapped", result.get("variant_count", 0))
    col2.metric("Genes identified", result.get("gene_count", 0))
    col3.metric("High-priority candidates", len(result.get("high_priority_candidates", [])))

    disease = result.get("disease", {})
    if disease.get("disease_id"):
        st.write(f"**Disease context:** {disease.get('disease_name', 'Unknown')} ({disease.get('disease_id')})")

    # Variant type chart
    st.plotly_chart(
        variant_type_distribution(result.get("variants_mapped", [])),
        use_container_width=True,
        key="mut_target_variant_types",
    )

    # Gene-disease network
    if result.get("target_candidates"):
        st.plotly_chart(
            gene_disease_network_chart(
                result["target_candidates"],
                disease_name=disease.get("disease_name", "Disease"),
            ),
            use_container_width=True,
            key="mut_target_gene_disease_network",
        )

    # Target candidates table
    candidates = result.get("target_candidates", [])
    if candidates:
        st.write("### Target Candidates")
        df = pd.DataFrame(candidates)
        display_cols = [
            c for c in (
                "gene_symbol", "gene_name", "ncbi_gene_id", "ensembl_gene_id",
                "uniprot_id", "disease_associated", "has_loss_of_function_variant",
                "has_gain_of_function_candidate", "variant_count",
            )
            if c in df.columns
        ]
        st.dataframe(df[display_cols], hide_index=True, alt="Mutation-to-target candidates")
        st.download_button(
            "Download candidates CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="geneai_mutation_target_candidates.csv",
            mime="text/csv",
            key="download_mut_target_csv",
        )

        # Variant details per gene
        with st.expander("Variant details by gene"):
            for candidate in candidates[:20]:
                symbol = candidate.get("gene_symbol", "Unknown")
                variants_list = candidate.get("variants", [])
                if variants_list:
                    st.write(f"**{symbol}** ({len(variants_list)} variant(s))")
                    vdf = pd.DataFrame(variants_list)
                    vcols = [
                        c for c in ("variant_id", "chrom", "pos", "ref", "alt", "variant_type", "consequence", "is_loss_of_function", "is_gain_of_function_candidate")
                        if c in vdf.columns
                    ]
                    st.dataframe(vdf[vcols], hide_index=True, alt=f"Variants for {symbol}")

    # Limitations
    with st.expander("Limitations"):
        for limitation in result.get("limitations", []):
            st.markdown(f"- {limitation}")
