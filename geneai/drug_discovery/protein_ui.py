"""Streamlit dashboard for protein sequence and structure research."""
from __future__ import annotations

import json
import logging
import sqlite3
import re
from dataclasses import replace
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from geneai.agents.protein_structure_agent import (
    ProteinAnalysisRequest,
    analyze_protein_record,
    lookup_protein_records,
)
from geneai.database.protein_schema import store_protein_analysis
from geneai.drug_discovery import api_clients
from geneai.drug_discovery.protein_reports import (
    protein_report_csv,
    protein_report_json,
    protein_report_pdf,
    protein_report_filename,
)
from geneai.drug_discovery.protein_structure import (
    build_structure_viewer_html,
    compare_structure_chains,
    compare_protein_substitution,
    parse_structure_file,
)
from geneai.sequence import parse_sequence_file

logger = logging.getLogger(__name__)
INPUT_KINDS = ["UniProt ID", "NCBI Protein ID", "PDB ID", "Protein name", "Gene symbol", "Protein FASTA"]


def _phase4_context() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    disease = st.session_state.get("disease_analysis_result")
    disease = disease if isinstance(disease, dict) else {}
    proteins = disease.get("proteins", []) if isinstance(disease.get("proteins"), list) else []
    vcf_result = st.session_state.get("mutation_vcf_result")
    preview = vcf_result.get("preview", []) if isinstance(vcf_result, dict) and isinstance(vcf_result.get("preview"), list) else []
    return disease, proteins, preview


def _parse_residue_range(value: str) -> tuple[int, int] | None:
    """Parse an optional inclusive PDB residue-number range from the UI."""
    if not value.strip():
        return None
    match = re.fullmatch(r"\s*(-?\d+)\s*[-:]\s*(-?\d+)\s*", value)
    if not match:
        raise ValueError("Enter a residue range such as 20-150, or leave it blank for the full chain.")
    start, end = (int(item) for item in match.groups())
    if end < start:
        raise ValueError("Residue range end must be greater than or equal to its start.")
    return start, end


def render_protein_structure_page() -> None:
    """Render the Protein Structure Analysis page inside the current app."""
    st.subheader("Protein Structure Analysis")
    st.write(
        "Inspect protein sequence properties, source annotations, available structures, and deposited ligand-contact regions. "
        "Experimental structures and computational predictions are labeled separately."
    )
    st.info(
        "Research use only. A structure, predicted model, or ligand-contact region does not establish protein function, "
        "drug binding, target validity, or clinical effect."
    )

    disease_context, phase4_proteins, vcf_preview = _phase4_context()
    prefill_kind = st.session_state.get("protein_prefill_kind", "UniProt ID")
    prefill_query = st.session_state.get("protein_prefill_query", "")
    if phase4_proteins:
        labels = {
            str(index): f"{protein.get('gene_symbol') or 'Gene unavailable'} · {protein.get('protein_name')} · {protein.get('uniprot_id')}"
            for index, protein in enumerate(phase4_proteins)
        }
        chosen_phase4 = st.selectbox(
            "Use a protein from the current Phase 4.2 Disease Analysis result",
            list(labels),
            format_func=lambda key: labels.get(key, key),
            key="phase4_protein_choice",
        )
        if st.button("Load selected disease protein", key="load_phase4_protein"):
            protein = phase4_proteins[int(chosen_phase4)]
            accession = protein.get("uniprot_id")
            input_kind = "UniProt ID" if accession else "Gene symbol"
            st.session_state["protein_prefill_kind"] = input_kind
            st.session_state["protein_prefill_query"] = str(accession or protein.get("gene_symbol") or "")
            st.session_state["protein_input_kind"] = input_kind
            st.rerun()

    kind = st.selectbox(
        "Protein input type",
        INPUT_KINDS,
        index=INPUT_KINDS.index(prefill_kind) if prefill_kind in INPUT_KINDS else 0,
        key="protein_input_kind",
    )
    with st.form("protein_lookup_form"):
        query = st.text_input(
            "Protein ID, name, or gene symbol",
            value=prefill_query,
            placeholder="P13569, CFTR, or a protein name",
            key="protein_input_query",
            disabled=kind == "Protein FASTA",
        )
        fasta_file = st.file_uploader(
            "Protein FASTA file (.fa, .fasta, .faa, .fna, .txt)",
            type=["fa", "fasta", "faa", "fna", "txt"],
            key="protein_fasta_file",
        )
        sequence_text = st.text_area(
            "Or paste one protein sequence",
            height=100,
            placeholder="MKWVTFISLLFLFSSAYS...",
            key="protein_sequence_text",
            disabled=kind != "Protein FASTA",
        )
        structure_file = st.file_uploader(
            "Optional PDB or mmCIF file",
            type=["pdb", "cif", "mmcif"],
            key="protein_structure_file",
        )
        st.caption("If you upload coordinates, that file is analyzed in place of any selected database model.")
        submitted = st.form_submit_button("Find protein and available structures", type="primary")

    if submitted:
        st.session_state.pop("protein_lookup", None)
        st.session_state.pop("protein_analysis_result", None)
        st.session_state.pop("protein_viewer_html", None)
        st.session_state.pop("protein_structure_comparison", None)
        request = ProteinAnalysisRequest(
            input_kind=kind,
            query=query.strip(),
            sequence_text=sequence_text,
            fasta_data=fasta_file.getvalue() if fasta_file else None,
            fasta_filename=fasta_file.name if fasta_file else "protein.fasta",
            structure_data=structure_file.getvalue() if structure_file else None,
            structure_filename=structure_file.name if structure_file else "structure.pdb",
            disease_context=disease_context,
            vcf_preview=vcf_preview,
        )
        try:
            with st.spinner("Retrieving protein and structure records from public databases…"):
                lookup = lookup_protein_records(request)
            st.session_state["protein_lookup"] = lookup
            st.session_state["protein_lookup_request"] = request
            st.session_state.pop("protein_prefill_kind", None)
            st.session_state.pop("protein_prefill_query", None)
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("Protein lookup was not completed: %s", exc)
            st.error(str(exc))

    lookup = st.session_state.get("protein_lookup")
    request = st.session_state.get("protein_lookup_request")
    if isinstance(lookup, dict) and isinstance(request, ProteinAnalysisRequest):
        _render_lookup(lookup, request)
    result = st.session_state.get("protein_analysis_result")
    if isinstance(result, dict):
        _render_analysis(result)


def _render_lookup(lookup: dict[str, Any], request: ProteinAnalysisRequest) -> None:
    records = lookup.get("protein_records", [])
    candidates = lookup.get("structure_candidates", [])
    st.divider()
    st.subheader("Protein records")
    if not records:
        st.warning("The selected database returned no protein record. Check the identifier or try FASTA input.")
        return
    if len(records) > 1:
        record_map = {str(item.get("record_key")): item for item in records}
        record_key = st.selectbox(
            "Select the matching protein",
            list(record_map),
            format_func=lambda key: (
                f"{record_map[key].get('protein_name')} · "
                f"{record_map[key].get('gene_symbol') or 'gene unavailable'} · "
                f"{record_map[key].get('primary_accession')}"
            ),
            key="selected_protein_record",
        )
    else:
        record_map = {str(records[0].get("record_key")): records[0]}
        record_key = next(iter(record_map))
    record = record_map[record_key]
    st.markdown(f"**{record.get('protein_name')}** · {record.get('gene_symbol') or 'gene not provided'} · {record.get('primary_accession')}")
    if record.get("source_url"):
        st.link_button("Open protein source record", record["source_url"])
    if record.get("function"):
        st.write(record["function"])

    candidate_list = [item for item in candidates if not item.get("record_key") or item.get("record_key") == record_key]
    candidate_labels = {"": "Sequence only / no structure"}
    for item in candidate_list:
        label = (
            f"{item.get('structure_id') or item.get('pdb_id')} · {item.get('structure_type')} · "
            f"{item.get('experimental_method') or 'method not reported'} · "
            f"resolution {item.get('resolution_angstrom') if item.get('resolution_angstrom') is not None else 'not reported'} Å"
        )
        candidate_labels[str(item.get("candidate_key"))] = label
    selected_structure_key = st.selectbox(
        "Structure model",
        list(candidate_labels),
        format_func=lambda key: candidate_labels.get(key, key),
        key="protein_structure_candidate",
    )
    if selected_structure_key:
        selected_candidate = next(item for item in candidate_list if item.get("candidate_key") == selected_structure_key)
        st.caption(
            f"Source: {selected_candidate.get('structure_source')} · {selected_candidate.get('structure_type')}"
        )
        if selected_candidate.get("source_url"):
            st.link_button("Open selected structure source", selected_candidate["source_url"])

    chain_id = st.text_input(
        "Chain ID (optional; first protein chain is used if blank)",
        key="protein_chain_input",
    )
    highlight_value = st.number_input(
        "Residue number to highlight (0 = none)",
        min_value=0,
        value=0,
        step=1,
        key="protein_highlight_residue",
    )
    if st.button("Analyze selected protein", type="primary", key="run_protein_analysis"):
        st.session_state.pop("protein_viewer_html", None)
        st.session_state.pop("protein_structure_comparison", None)
        selected_request = replace(
            request,
            selected_record_key=record_key,
            selected_structure_key=selected_structure_key,
            selected_chain=chain_id.strip(),
            highlight_residue=int(highlight_value) or None,
        )
        try:
            with st.spinner("Calculating protein properties and parsing coordinates…"):
                result = analyze_protein_record(
                    lookup,
                    selected_request,
                    structure_candidate_key=selected_structure_key,
                    persist=True,
                )
            st.session_state["protein_analysis_result"] = result
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("Protein analysis could not be completed: %s", exc)
            st.error(str(exc))

    _render_source_status(lookup.get("data_sources", []))
    if lookup.get("limitations"):
        with st.expander("Lookup limitations"):
            for item in lookup["limitations"]:
                st.markdown(f"- {item}")


def _render_source_status(sources: list[dict[str, Any]]) -> None:
    if sources:
        frame = pd.DataFrame(
            [{
                "Source": item.get("source"),
                "Status": item.get("status"),
                "Version": item.get("version", "not reported"),
                "Records": item.get("record_count", 0),
                "Details": item.get("error", ""),
            } for item in sources]
        )
        st.dataframe(frame, hide_index=True, alt="Protein source records, versions, and retrieval status")


def _render_analysis(result: dict[str, Any]) -> None:
    protein = result.get("protein") or {}
    metrics = result.get("sequence_analysis") or {}
    structure = result.get("structure") or {}
    st.divider()
    st.subheader(f"Analysis: {protein.get('protein_name') or 'Selected protein'}")
    st.caption(
        f"Analysis {result.get('analysis_id')} · {protein.get('source')} · "
        f"Storage: {result.get('storage', {}).get('status', 'not reported')} · retrieved {result.get('retrieved_at')}"
    )
    if result.get("storage", {}).get("status") == "unavailable":
        st.warning("Results are available in this session but could not be saved to the local database.")
    overview, function_tab, structure_tab, pockets_tab, compare_tab, reports_tab = st.tabs(
        ["Overview", "Function & sequence", "Structure viewer", "Contact regions", "Compare structures", "Exports"]
    )
    with overview:
        one, two, three, four = st.columns(4)
        one.metric("Sequence length", f"{metrics.get('length_residues', '—')}")
        two.metric("Molecular weight", f"{metrics.get('molecular_weight_da'):,.1f} Da" if metrics.get("molecular_weight_da") is not None else "Not calculated")
        three.metric("Theoretical pI", f"{metrics.get('theoretical_pi'):.2f}" if metrics.get("theoretical_pi") is not None else "Not calculated")
        four.metric("Structure chains", structure.get("chain_count", "—"))
        if structure:
            st.write(
                f"**Structure:** {structure.get('structure_id')} · {structure.get('structure_source')} · "
                f"{structure.get('structure_type')}"
            )
            st.caption(
                f"Method: {structure.get('experimental_method') or 'not reported'} · "
                f"Resolution: {structure.get('resolution_angstrom') if structure.get('resolution_angstrom') is not None else 'not reported'} Å"
            )
        else:
            st.info("No coordinates were loaded. Sequence and source annotations remain available.")
        if result.get("disease_associations_from_phase_4_2"):
            st.subheader("Disease associations from Phase 4.2")
            st.dataframe(pd.DataFrame(result["disease_associations_from_phase_4_2"]), hide_index=True, alt="Matching Phase 4.2 disease association evidence")
        if result.get("variant_records_from_phase_3_vcf_preview"):
            st.subheader("Matching variants from Phase 3 VCF preview")
            st.dataframe(pd.DataFrame(result["variant_records_from_phase_3_vcf_preview"]), hide_index=True, alt="VCF preview annotations matching this gene symbol")
            st.caption("These are annotations present in the input VCF. This page does not infer mutation impact.")
        st.subheader("Retrieved sources")
        _render_source_status(result.get("data_sources", []))
        st.caption(result.get("target_interpretation", "Research output; target validity is not established."))
        st.caption(result.get("research_only_disclaimer", "Research use only."))
        if result.get("limitations"):
            with st.expander("Analysis limitations"):
                for item in result["limitations"]:
                    st.markdown(f"- {item}")

    with function_tab:
        st.markdown(f"**Protein function:** {protein.get('function') or 'Not provided by the selected source.'}")
        st.markdown(f"**Cellular location:** {protein.get('subcellular_location') or 'Not provided by the selected source.'}")
        st.markdown(f"**Family annotations:** {'; '.join(protein.get('family_annotations', [])) or 'Not provided by the selected source.'}")
        st.markdown(f"**Enzyme classification:** {', '.join(protein.get('ec_numbers', [])) or 'Not provided by the selected source.'}")
        if protein.get("source_url"):
            st.link_button("Open UniProt or source record", protein["source_url"])
        composition = metrics.get("composition", {})
        composition_rows = [
            {"Amino acid": amino_acid, "Count": item.get("count", 0), "Fraction": item.get("fraction", 0)}
            for amino_acid, item in composition.items() if item.get("count", 0)
        ]
        if composition_rows:
            frame = pd.DataFrame(composition_rows)
            st.plotly_chart(px.bar(frame, x="Amino acid", y="Count", title="Amino-acid composition"), key="protein_composition_chart")
            st.dataframe(frame, hide_index=True, alt="Protein amino-acid counts and fractions")
        if metrics.get("hydropathy_distribution"):
            hydro = metrics["hydropathy_distribution"]
            st.plotly_chart(
                px.bar(
                    pd.DataFrame([
                        {"Residue group": "Hydrophobic (KD > 0)", "Fraction": hydro.get("hydrophobic_fraction", 0)},
                        {"Residue group": "Hydrophilic (KD < 0)", "Fraction": hydro.get("hydrophilic_fraction", 0)},
                        {"Residue group": "Neutral (KD = 0)", "Fraction": hydro.get("neutral_fraction", 0)},
                        {"Residue group": "Ambiguous/noncanonical", "Fraction": hydro.get("ambiguous_or_noncanonical_count", 0) / max(metrics.get("length_residues", 1), 1)},
                    ]),
                    x="Residue group", y="Fraction", title="Residue hydropathy distribution",
                ),
                key="protein_hydropathy_chart",
            )
        if protein.get("features"):
            st.subheader("Domains and functional regions")
            st.dataframe(pd.DataFrame(protein["features"]), hide_index=True, alt="UniProt protein domains and functional-region annotations")
        if protein.get("interactions"):
            st.subheader("Protein interaction annotations")
            st.dataframe(pd.DataFrame(protein["interactions"]), hide_index=True, alt="Interaction notes present in the UniProt record")
        if result.get("go_annotations"):
            st.subheader("Gene Ontology evidence annotations")
            st.caption("These are annotated terms with evidence codes, not a GO enrichment analysis.")
            st.dataframe(pd.DataFrame(result["go_annotations"]), hide_index=True, alt="QuickGO Gene Ontology annotations")
        if protein.get("sequence"):
            with st.expander("View retrieved amino-acid sequence"):
                st.code(protein["sequence"], language=None)
            with st.expander("Compare a single protein substitution"):
                st.caption("Enter an amino-acid change already mapped to this exact protein sequence; nucleotide variants are not translated here.")
                notation = st.text_input("Protein substitution", placeholder="p.Gly12Asp or p.G12D", key="protein_substitution_notation")
                if st.button("Compare with reference sequence", key="compare_protein_substitution"):
                    try:
                        comparison_result = compare_protein_substitution(protein["sequence"], notation)
                        result["protein_mutation_comparison"] = comparison_result
                        result.setdefault("drug_discovery_handoff", {})["protein_mutation_comparison"] = comparison_result
                        try:
                            store_protein_analysis(result)
                            result["storage"] = {"status": "saved", "analysis_id": result.get("analysis_id")}
                        except (sqlite3.Error, OSError, ValueError) as exc:
                            result["storage"] = {"status": "unavailable", "error": str(exc)}
                            result.setdefault("limitations", []).append("The protein substitution comparison could not be added to the local SQLite analysis snapshot.")
                        st.session_state["protein_analysis_result"] = result
                        st.success("The reference residue matches. This is a sequence-level comparison only.")
                    except ValueError as exc:
                        st.error(str(exc))
                if result.get("protein_mutation_comparison"):
                    st.json(result["protein_mutation_comparison"], expanded=False)

    with structure_tab:
        structure_bytes = result.get("_structure_bytes")
        structure_text = result.get("_structure_text")
        if not structure_bytes or not structure_text:
            st.info("Load an uploaded or database structure to display the 3D model.")
        else:
            chain_options = [item.get("chain_id", "") for item in structure.get("chains", [])]
            selected_chain = st.selectbox(
                "Displayed chain",
                chain_options,
                index=chain_options.index(result.get("selected_chain_id")) if result.get("selected_chain_id") in chain_options else 0,
                key="protein_viewer_chain",
            ) if chain_options else None
            representation = st.radio("Representation", ["Cartoon", "Surface"], horizontal=True, key="protein_view_representation")
            residue_max = max((item.get("amino_acid_residues", 1) for item in structure.get("chains", [])), default=1)
            highlight = st.number_input("Highlight residue number", min_value=0, max_value=max(int(residue_max), 1), value=int(result.get("_highlight_residue") or 0), key="viewer_residue")
            if st.button("Update structure view", key="update_protein_view"):
                try:
                    html = build_structure_viewer_html(
                        structure_text,
                        structure.get("format", "mmCIF"),
                        chain_id=selected_chain,
                        highlight_residue=int(highlight) or None,
                        representation=representation,
                    )
                    if html is None:
                        st.warning("Optional py3Dmol is unavailable. Install it to enable the 3D viewer; structure analysis still works.")
                    else:
                        st.session_state["protein_viewer_html"] = html
                except (ValueError, RuntimeError) as exc:
                    st.error(f"Could not render this model: {exc}")
            html = st.session_state.get("protein_viewer_html")
            if html:
                st.components.v1.html(html, height=580, scrolling=False)
            else:
                try:
                    html = build_structure_viewer_html(structure_text, structure.get("format", "mmCIF"), chain_id=selected_chain)
                    if html:
                        st.components.v1.html(html, height=580, scrolling=False)
                    else:
                        st.warning("Optional py3Dmol is unavailable. Coordinate analysis and downloads remain available.")
                except (ValueError, RuntimeError) as exc:
                    st.error(f"Could not render this model: {exc}")
            st.caption("Rotate and zoom using the mouse. Structure source and experimental/predicted status are shown above.")
            st.dataframe(pd.DataFrame(structure.get("chains", [])), hide_index=True, alt="Protein chains, residues, atoms, and coordinate bounds")
            st.caption(f"Secondary structure: {structure.get('secondary_structure', {}).get('status', 'not calculated')} — {structure.get('secondary_structure', {}).get('reason', '')}")
            if structure.get("disulfide_bonds"):
                st.dataframe(pd.DataFrame(structure["disulfide_bonds"]), hide_index=True, alt="Coordinate-distance candidate disulfide bonds")
            if structure.get("header_missing_residues"):
                st.dataframe(pd.DataFrame(structure["header_missing_residues"]), hide_index=True, alt="Missing residues reported in the PDB structure header")

    with pockets_tab:
        st.caption("Pocket candidates here are neighborhoods around deposited non-water hetero residues. No de novo pocket finder or druggability score is applied.")
        pockets = result.get("pockets", [])
        if pockets:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Candidate region": pocket.get("pocket_id"),
                        "Ligand/cofactor": pocket.get("ligand_or_cofactor"),
                        "Nearby residues": pocket.get("nearby_residue_count"),
                        "Center (Å)": pocket.get("center_angstrom"),
                        "Dimensions (Å)": pocket.get("dimensions_angstrom"),
                        "Method": pocket.get("method"),
                    }
                    for pocket in pockets
                ]),
                hide_index=True,
                alt="Deposited ligand-contact candidate regions; not predicted drug-binding pockets",
            )
            for pocket in pockets:
                with st.expander(f"{pocket.get('pocket_id')} nearby residues"):
                    st.dataframe(pd.DataFrame(pocket.get("nearby_residues", [])), hide_index=True, alt="Residues near the deposited hetero group")
        else:
            st.info("No deposited ligand/cofactor contact neighborhoods were found in the loaded coordinates.")
        st.download_button(
            "Download candidate contact regions CSV",
            pd.json_normalize(pockets, sep=".").to_csv(index=False),
            file_name="protein_contact_regions.csv",
            mime="text/csv",
            disabled=not pockets,
        )

    with compare_tab:
        st.write("Choose chains and, optionally, inclusive residue-number ranges. The software sequence-maps C-alpha atoms before calculating RMSD.")
        second_file = None
        primary_chains = [item.get("chain_id", "") for item in structure.get("chains", [])]
        with st.form("protein_comparison_form"):
            second_file = st.file_uploader("Comparison structure file", type=["pdb", "cif", "mmcif"], key="protein_comparison_file")
            primary_chain = st.selectbox("Primary structure chain", primary_chains, key="protein_compare_chain_a") if primary_chains else ""
            secondary_chain = st.text_input("Comparison structure chain ID (blank uses first protein chain)", key="protein_compare_chain_b")
            primary_range_text = st.text_input("Primary residue-number range (blank uses full chain)", placeholder="e.g. 20-150", key="protein_compare_range_a")
            secondary_range_text = st.text_input("Comparison residue-number range (blank uses full chain)", placeholder="e.g. 18-148", key="protein_compare_range_b")
            compare_clicked = st.form_submit_button("Compare selected chains", type="primary")
        if compare_clicked and result.get("_structure_bytes") and second_file:
            try:
                primary, _ = parse_structure_file(result["_structure_bytes"], result.get("_structure_filename", "primary.cif"))
                secondary, _ = parse_structure_file(second_file.getvalue(), second_file.name)
                secondary_chains = [str(chain.id or " ") for chain in secondary[0].get_chains()]
                chain_b = secondary_chain.strip() or (secondary_chains[0] if secondary_chains else "")
                comparison = compare_structure_chains(
                    primary,
                    secondary,
                    primary_chain,
                    chain_b,
                    _parse_residue_range(primary_range_text),
                    _parse_residue_range(secondary_range_text),
                )
                st.session_state["protein_structure_comparison"] = comparison
            except (ValueError, KeyError, IndexError) as exc:
                st.error(str(exc))
        elif compare_clicked:
            st.warning("Load a primary structure and upload the comparison structure first.")
        comparison = st.session_state.get("protein_structure_comparison")
        if isinstance(comparison, dict):
            if comparison.get("status") == "unavailable":
                st.warning(comparison.get("reason"))
            else:
                st.json(comparison)
                if comparison.get("warning"):
                    st.warning(comparison["warning"])

    with reports_tab:
        st.caption("The downloadable report includes sources, evidence metadata, and research limitations.")
        safe_name = str(protein.get("protein_name") or protein.get("primary_accession") or "protein_analysis")
        st.download_button("Download PDF report", protein_report_pdf(result), protein_report_filename(safe_name, "pdf"), "application/pdf", key="download_protein_pdf")
        st.download_button("Download CSV summary", protein_report_csv(result), protein_report_filename(safe_name, "csv"), "text/csv", key="download_protein_csv")
        st.download_button("Download structured JSON", protein_report_json(result), protein_report_filename(safe_name, "json"), "application/json", key="download_protein_json")
        if result.get("_structure_bytes"):
            filename = str(result.get("_structure_filename") or "protein_structure.cif")
            mime = "chemical/x-pdb" if filename.lower().endswith(".pdb") else "chemical/x-mmcif"
            st.download_button("Download loaded PDB/mmCIF file", result["_structure_bytes"], filename, mime, key="download_protein_coordinates")

