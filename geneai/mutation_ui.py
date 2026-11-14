"""Streamlit presentation for the Phase 3 VCF evidence milestone."""
from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from geneai.mutation import summarize_vcf_interpretation_stream

logger = logging.getLogger(__name__)


def render_mutation_interpretation_page() -> None:
    """Render a bounded VCF scan and clearly separate source evidence from inference."""
    st.subheader("AI Mutation Interpretation")
    st.write(
        "Phase 3 research workspace: inspect VCF variants, sample calls, quality fields, "
        "and any annotations already present in the input. No pathogenicity prediction is generated."
    )
    st.info(
        "Research use only. This page does not provide a clinical diagnosis or treatment guidance. "
        "Gene, protein, and clinical labels below are shown only when they are present in the uploaded VCF."
    )

    uploaded = st.file_uploader(
        "VCF or compressed VCF",
        type=["vcf", "gz"],
        max_upload_size=500,
        key="mutation_vcf_file",
        help="Upload a .vcf or .vcf.gz file. Large inputs are scanned incrementally; only a bounded preview is retained.",
    )
    expected_build = st.selectbox(
        "Expected reference build (optional)",
        ["Do not check", "GRCh37", "GRCh38"],
        key="mutation_expected_build",
    )
    if uploaded and st.button("Scan and summarize", type="primary", key="scan_mutation_vcf"):
        st.session_state.pop("mutation_vcf_result", None)
        with st.spinner("Scanning VCF rows and sample evidence…"):
            try:
                summary, metadata, preview = summarize_vcf_interpretation_stream(
                    uploaded,
                    uploaded.name,
                    expected_build=None if expected_build == "Do not check" else expected_build,
                )
                st.session_state["mutation_vcf_result"] = {
                    "summary": summary,
                    "metadata": metadata,
                    "preview": preview,
                    "filename": uploaded.name,
                    "upload_bytes": uploaded.size,
                }
            except (ValueError, OSError, EOFError) as exc:
                logger.info("VCF interpretation scan rejected: %s", exc)
                st.error(str(exc))

    result = st.session_state.get("mutation_vcf_result")
    if not result:
        st.caption("Upload a VCF and choose Scan and summarize to begin.")
        return

    summary = result["summary"]
    metadata = result["metadata"]
    preview = result["preview"]
    st.caption(
        f"File: {result['filename']} · {result['upload_bytes'] / (1024 * 1024):,.1f} MB · "
        f"{summary['source_records']:,} source rows scanned"
    )

    if metadata["reference_build_status"] == "mismatch":
        st.error(
            f"Reference-build mismatch: file declares {metadata['reference_build']}, "
            f"but {metadata['expected_reference_build']} was selected."
        )
    elif metadata["reference_build_status"] == "not_declared" and metadata["expected_reference_build"]:
        st.warning("The file does not declare a reference build, so the selected build could not be checked.")
    elif metadata.get("reference_build"):
        st.caption(f"Declared reference build: {metadata['reference_build']}")
    else:
        st.warning("No reference build was found in the VCF header.")

    by_type = summary["by_type"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Variant alleles", f"{summary['variant_records']:,}")
    c2.metric("Samples", f"{summary['sample_count']:,}")
    c3.metric("Duplicate alleles", f"{summary['duplicate_alleles']:,}")
    c4.metric("Mean QUAL", summary["mean_qual"] if summary["mean_qual"] is not None else "Not provided")

    st.caption(
        "Variant types are based on VCF representation. QUAL and FILTER are source fields, "
        "not a clinical quality determination."
    )
    left, right = st.columns(2)
    with left:
        type_frame = pd.DataFrame(
            [{"Variant type": kind, "Alleles": count} for kind, count in sorted(by_type.items())]
        )
        st.plotly_chart(
            px.bar(type_frame, x="Variant type", y="Alleles", title="Variant representation"),
            width="stretch",
        )
    with right:
        chromosome_frame = pd.DataFrame(
            [{"Chromosome": chrom, "Alleles": count} for chrom, count in sorted(summary["by_chromosome"].items())]
        )
        st.plotly_chart(
            px.bar(chromosome_frame, x="Chromosome", y="Alleles", title="Variant alleles by chromosome"),
            width="stretch",
        )

    with st.expander("Header and source-field coverage"):
        st.json(
            {
                "reference_build": metadata.get("reference_build"),
                "expected_reference_build": metadata.get("expected_reference_build"),
                "reference_build_status": metadata.get("reference_build_status"),
                "sample_names": metadata.get("sample_names", []),
                "variants_with_source_fields": summary["embedded_annotation_counts"],
                "filter_values": summary["by_filter"],
                "genotype_calls": summary["genotype_counts"],
            }
        )
        st.caption(summary["normalization_note"])

    if summary["sample_metrics"]:
        st.subheader("Sample-level call metrics")
        st.dataframe(
            pd.DataFrame(
                [{"Sample": sample, **metrics} for sample, metrics in summary["sample_metrics"].items()]
            ),
            hide_index=True,
            alt="Per-sample VCF genotype, depth, and quality summary",
        )

    st.subheader("Variant preview")
    st.caption(
        f"Preview contains at most {summary['preview_limit']:,} alleles. Filters and CSV export apply to this preview; "
        "full-file summary counts cover all scanned rows."
    )
    all_types = sorted({row["variant_type"] for row in preview})
    all_chromosomes = sorted({row["chrom"] for row in preview})
    f1, f2 = st.columns(2)
    selected_types = f1.multiselect("Variant type", all_types, default=all_types, key="mutation_preview_types")
    selected_chromosomes = f2.multiselect(
        "Chromosome", all_chromosomes, default=all_chromosomes, key="mutation_preview_chromosomes"
    )
    minimum_qual = st.number_input(
        "Minimum QUAL (rows without QUAL are kept)", min_value=0.0, value=0.0, step=1.0,
        key="mutation_preview_min_qual",
    )
    filtered = [
        row for row in preview
        if row["variant_type"] in selected_types
        and row["chrom"] in selected_chromosomes
        and (row["qual"] is None or row["qual"] >= minimum_qual)
    ]
    visible_columns = [
        "chrom", "pos", "id", "ref", "alt", "variant_type", "sv_type", "qual", "filter",
        "source_af_info", "cohort_af_from_genotypes", "called_samples", "duplicate",
    ]
    preview_frame = pd.DataFrame(filtered, columns=visible_columns)
    st.dataframe(preview_frame, hide_index=True, alt="Filtered bounded VCF allele preview")
    if filtered:
        selected_row = st.selectbox(
            "Inspect preview row",
            range(len(filtered)),
            format_func=lambda index: (
                f"{filtered[index]['chrom']}:{filtered[index]['pos']} "
                f"{filtered[index]['ref']}>{filtered[index]['alt']}"
            ),
            key="mutation_preview_row",
        )
        variant = filtered[selected_row]
        with st.expander("Selected variant details", expanded=False):
            st.json({key: value for key, value in variant.items() if key != "sample_calls"})
            if variant["sample_calls"]:
                st.dataframe(
                    pd.DataFrame(variant["sample_calls"]),
                    hide_index=True,
                    alt="Per-sample genotype, depth, and genotype-quality fields for the selected allele",
                )
            else:
                st.caption("No sample genotype columns were present in this VCF.")

    st.download_button(
        "Download filtered preview CSV",
        preview_frame.to_csv(index=False),
        file_name="mutation_variant_preview.csv",
        mime="text/csv",
        disabled=preview_frame.empty,
    )
    st.warning(summary["classification_note"])
