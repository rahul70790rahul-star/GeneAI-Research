"""Streamlit UI for the Universal Dataset Registry.

Provides a dashboard for viewing, registering, and validating biological
datasets. Integrated into the main GeneAI Research application.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.dataset_registry import (
    DatasetRegistry,
    DataType,
    LicenseType,
    ProcessingStatus,
)
from geneai.dataset_registry.validation import validate_dataframe_quality

logger = logging.getLogger(__name__)


def _get_registry() -> DatasetRegistry:
    """Get or create a DatasetRegistry instance from session state."""
    if "dataset_registry" not in st.session_state:
        st.session_state["dataset_registry"] = DatasetRegistry()
    return st.session_state["dataset_registry"]


def render_dataset_registry() -> None:
    """Render the Universal Dataset Registry dashboard."""
    st.title("\U0001f4ca Universal Dataset Registry")
    st.markdown(
        "Discover, index, validate, and track biological datasets used by "
        "GeneAI Research. All dataset metadata is captured from verifiable "
        "sources; no records are fabricated."
    )

    registry = _get_registry()

    # Tabs for different views
    tab_browse, tab_register, tab_stats = st.tabs(
        ["\U0001f4cb Browse Datasets", "\u2709 Register Dataset", "\u2605 Statistics"]
    )

    with tab_browse:
        _render_browse_tab(registry)

    with tab_register:
        _render_register_tab(registry)

    with tab_stats:
        _render_stats_tab(registry)


def _render_browse_tab(registry: DatasetRegistry) -> None:
    """Render the browse datasets tab."""
    st.subheader("Registered Datasets")

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        source_filter = st.text_input(
            "Filter by source", placeholder="e.g., NCBI, Ensembl, UniProt"
        )
    with col2:
        status_options = [s.value for s in ProcessingStatus]
        status_filter = st.selectbox(
            "Filter by status", ["All"] + status_options, index=0
        )

    # Fetch entries
    source = source_filter.strip() or None
    status = None
    if status_filter != "All":
        status = ProcessingStatus(status_filter)

    entries = registry.list(source=source, status=status)

    if not entries:
        st.info("No datasets registered yet. Use the Register Dataset tab to add one.")
        return

    # Convert to DataFrame for display
    rows = []
    for entry in entries:
        m = entry.metadata
        rows.append({
            "Dataset ID": entry.dataset_id[:8] + "...",
            "Name": m.name,
            "Source": m.source,
            "Version": m.version,
            "Organism": m.organism,
            "Data Type": m.data_type.value,
            "Assembly": m.genome_assembly or "-",
            "License": m.license.value,
            "Quality Score": f"{entry.quality_score:.2f}",
            "Status": entry.processing_status.value,
            "Records": m.record_count or "-",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Detail view for selected dataset
    st.divider()
    st.subheader("Dataset Details")
    selected_id = st.selectbox(
        "Select a dataset to view details",
        options=[e.dataset_id for e in entries],
        format_func=lambda x: next(
            (e.metadata.name for e in entries if e.dataset_id == x), x
        ),
    )

    if selected_id:
        entry = registry.get(selected_id)
        if entry:
            m = entry.metadata
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Name:** {m.name}")
                st.write(f"**Source:** {m.source}")
                st.write(f"**Version:** {m.version}")
                st.write(f"**Organism:** {m.organism}")
                st.write(f"**Data Type:** {m.data_type.value}")
                st.write(f"**Genome Assembly:** {m.genome_assembly or 'Not specified'}")
            with col2:
                st.write(f"**License:** {m.license.value}")
                st.write(f"**Quality Score:** {entry.quality_score:.2f}")
                st.write(f"**Status:** {entry.processing_status.value}")
                st.write(f"**Download Date:** {m.download_date}")
                st.write(f"**Record Count:** {m.record_count or 'Not specified'}")
                st.write(f"**Last Validated:** {entry.last_validated or 'Not yet'}")

            if m.citation:
                st.write(f"**Citation:** {m.citation}")
            if m.provenance_url:
                st.write(f"**Provenance:** {m.provenance_url}")
            if entry.validation_issues:
                st.write("**Validation Issues:**")
                for issue in entry.validation_issues:
                    st.write(f"- {issue}")
            if entry.missing_value_summary:
                st.write("**Missing Values:**")
                for col, count in entry.missing_value_summary.items():
                    st.write(f"- {col}: {count}")


def _render_register_tab(registry: DatasetRegistry) -> None:
    """Render the register dataset tab."""
    st.subheader("Register a New Dataset")
    st.markdown(
        "Register a biological dataset with full provenance metadata. "
        "All fields are stored verbatim from your source; no values are "
        "fabricated or inferred."
    )

    with st.form("register_dataset_form"):
        name = st.text_input("Dataset Name *", placeholder="e.g., ClinVar")
        source = st.text_input("Source *", placeholder="e.g., NCBI")
        version = st.text_input("Version *", placeholder="e.g., current or 2024-01")
        organism = st.text_input("Organism", value="Homo sapiens")
        download_date = st.text_input(
            "Download Date (ISO-8601 UTC)",
            value="",
            placeholder="Leave blank for current time",
        )

        col1, col2 = st.columns(2)
        with col1:
            data_type_str = st.selectbox(
                "Data Type", [dt.value for dt in DataType], index=len(DataType) - 1
            )
            license_str = st.selectbox(
                "License", [lt.value for lt in LicenseType], index=len(LicenseType) - 1
            )
        with col2:
            genome_assembly = st.text_input(
                "Genome Assembly", placeholder="e.g., GRCh38"
            )
            record_count = st.number_input(
                "Record Count", min_value=0, value=0, step=1
            )

        citation = st.text_area("Citation", placeholder="Published citation for this dataset")
        provenance_url = st.text_area(
            "Provenance URL", placeholder="https://source.example.org/dataset"
        )
        license_url = st.text_area(
            "License URL", placeholder="https://source.example.org/license"
        )
        attributes_json = st.text_area(
            "Additional Attributes (JSON)",
            placeholder='{"key": "value"}',
            height=100,
        )

        submitted = st.form_submit_button("Register Dataset")

    if submitted:
        if not name or not source or not version:
            st.error("Name, Source, and Version are required fields.")
            return

        try:
            import json

            attributes = {}
            if attributes_json.strip():
                attributes = json.loads(attributes_json)

            dt = DataType(data_type_str)
            lic = LicenseType(license_str)

            entry = registry.register(
                name=name.strip(),
                source=source.strip(),
                version=version.strip(),
                download_date=download_date.strip() or None,
                organism=organism.strip() or "Homo sapiens",
                data_type=dt,
                genome_assembly=genome_assembly.strip() or None,
                license=lic,
                citation=citation.strip() or None,
                provenance_url=provenance_url.strip() or None,
                license_url=license_url.strip() or None,
                record_count=int(record_count) if record_count > 0 else None,
                attributes=attributes or None,
                processing_status=ProcessingStatus.PENDING,
            )
            st.success(
                f"Dataset registered successfully! ID: {entry.dataset_id}"
            )
            st.info(
                "The dataset is in PENDING status. Use validation tools "
                "to assess quality before using it in predictions."
            )
        except Exception as exc:
            logger.exception("Failed to register dataset")
            st.error(f"Failed to register dataset: {exc}")


def _render_stats_tab(registry: DatasetRegistry) -> None:
    """Render the statistics tab."""
    st.subheader("Registry Statistics")

    stats = registry.get_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Datasets", stats["total_datasets"])
    with col2:
        ready_count = stats["by_status"].get("ready", 0)
        st.metric("Ready for Use", ready_count)
    with col3:
        pending_count = stats["by_status"].get("pending", 0)
        st.metric("Pending Validation", pending_count)

    st.divider()

    st.subheader("Datasets by Source")
    if stats["by_source"]:
        source_df = pd.DataFrame(
            list(stats["by_source"].items()),
            columns=["Source", "Count"],
        )
        st.bar_chart(source_df.set_index("Source"))
    else:
        st.info("No datasets registered yet.")

    st.divider()

    st.subheader("Datasets by Status")
    if stats["by_status"]:
        status_df = pd.DataFrame(
            list(stats["by_status"].items()),
            columns=["Status", "Count"],
        )
        st.bar_chart(status_df.set_index("Status"))
    else:
        st.info("No datasets registered yet.")


def render_data_quality_validator() -> None:
    """Render a standalone data quality validation component.

    Allows users to upload a CSV/Excel/JSON file and validate its quality
    without registering it in the registry.
    """
    st.title("\u2699 Data Quality Validator")
    st.markdown(
        "Upload a dataset file to check its quality before registration. "
        "This validates missing values, duplicates, and structural issues "
        "without modifying the registry."
    )

    uploaded = st.file_uploader(
        "Upload dataset file",
        type=["csv", "xlsx", "xls", "json"],
        help="CSV, Excel, or JSON files only",
    )

    if uploaded is not None:
        try:
            import io

            name = uploaded.name
            if name.lower().endswith(".csv"):
                df = pd.read_csv(io.BytesIO(uploaded.read()))
            elif name.lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(uploaded.read()))
            elif name.lower().endswith(".json"):
                df = pd.read_json(io.BytesIO(uploaded.read()))
            else:
                st.error("Unsupported file type.")
                return

            st.success(f"Loaded {len(df)} rows, {len(df.columns)} columns")

            # Run validation
            report = validate_dataframe_quality(df)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Valid", "Yes" if report["is_valid"] else "No")
            with col2:
                st.metric("Duplicate Rows", report["duplicate_rows"])
            with col3:
                total_missing = sum(report["missing_values"].values())
                st.metric("Missing Values", total_missing)

            st.divider()

            if report["issues"]:
                st.subheader("Issues")
                for issue in report["issues"]:
                    st.warning(issue)

            if report["warnings"]:
                st.subheader("Warnings")
                for warning in report["warnings"]:
                    st.info(warning)

            if report["missing_values"]:
                st.subheader("Missing Values by Column")
                missing_df = pd.DataFrame(
                    list(report["missing_values"].items()),
                    columns=["Column", "Missing Count"],
                )
                st.dataframe(missing_df, use_container_width=True, hide_index=True)

            if report["biological_ids_found"]:
                st.subheader("Biological ID Columns Detected")
                st.write(", ".join(report["biological_ids_found"]))

        except Exception as exc:
            logger.exception("Failed to validate uploaded dataset")
            st.error(f"Validation failed: {exc}")


__all__ = [
    "render_dataset_registry",
    "render_data_quality_validator",
]