"""Drug Discovery Dashboard for GeneAI Research - Streamlit UI."""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.drug_discovery import drug_comparison
from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import drug_report
from geneai.drug_discovery import drug_search
from geneai.drug_discovery import drug_target_analysis
from geneai.drug_discovery import drug_visualization
from geneai.drug_discovery import gene_drug_mapping

logger = logging.getLogger(__name__)


def render_drug_discovery_dashboard() -> None:
    """Main entry point for the Drug Discovery dashboard."""
    st.title("💊 Drug Discovery & Target Analysis")
    st.caption("Integrated drug database search, target analysis, and VCF-to-drug mapping")

    # Initialize session state
    if "drug_search_results" not in st.session_state:
        st.session_state.drug_search_results = None
    if "selected_drug" not in st.session_state:
        st.session_state.selected_drug = None
    if "comparison_drugs" not in st.session_state:
        st.session_state.comparison_drugs = []

    # Main tabs
    tabs = st.tabs([
        "🔍 Drug Search",
        "🎯 Drug-Target Explorer",
        "🧬 Gene-Drug Association",
        "🏥 Disease-Drug Association",
        "📋 Clinical Trial Explorer",
        "⚗️ Chemical Properties",
        "📊 Visualizations",
        "📄 Reports",
        "🔬 VCF to Drug Mapping",
    ])

    with tabs[0]:
        _render_drug_search_tab()

    with tabs[1]:
        _render_drug_target_tab()

    with tabs[2]:
        _render_gene_drug_tab()

    with tabs[3]:
        _render_disease_drug_tab()

    with tabs[4]:
        _render_clinical_trials_tab()

    with tabs[5]:
        _render_chemical_properties_tab()

    with tabs[6]:
        _render_visualizations_tab()

    with tabs[7]:
        _render_reports_tab()

    with tabs[8]:
        _render_vcf_to_drug_tab()


def _render_drug_search_tab() -> None:
    """Drug search interface."""
    st.subheader("Multi-Database Drug Search")

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input(
            "Search query",
            placeholder="Drug name, gene symbol, disease, or chemical identifier...",
            help="Search across PubChem, ChEMBL, Open Targets, and ClinicalTrials.gov",
        )
    with col2:
        search_type = st.selectbox(
            "Search type",
            ["Auto-detect", "Drug name", "Target/Gene", "Disease", "Chemical ID"],
            index=0,
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        sources = st.multiselect(
            "Data sources",
            ["PubChem", "ChEMBL", "Open Targets", "ClinicalTrials.gov"],
            default=["PubChem", "ChEMBL", "Open Targets", "ClinicalTrials.gov"],
        )
    with col2:
        limit = st.slider("Max results", 5, 100, 20, key="drug_search_limit")
    with col3:
        if st.button("🔍 Search", type="primary", use_container_width=True):
            if query:
                _perform_drug_search(query, search_type, sources, limit)
            else:
                st.warning("Please enter a search query")

    # Display results
    if st.session_state.drug_search_results:
        _display_search_results(st.session_state.drug_search_results)


def _perform_drug_search(query: str, search_type: str, sources: list[str], limit: int) -> None:
    """Execute drug search based on type."""
    with st.spinner("Searching databases..."):
        try:
            source_map = {
                "PubChem": "pubchem",
                "ChEMBL": "chembl",
                "Open Targets": "opentargets",
                "ClinicalTrials.gov": "clinicaltrials",
            }
            src = [source_map[s] for s in sources]

            if search_type == "Drug name" or (search_type == "Auto-detect" and not query.isdigit() and not query.startswith("NCT")):
                results = drug_search.search_drugs_by_name(query, src, limit)
            elif search_type == "Target/Gene" or (search_type == "Auto-detect" and query.isupper() and len(query) <= 10):
                results = drug_search.search_drugs_by_target(query, limit)
            elif search_type == "Disease":
                results = drug_search.search_drugs_by_disease(query, limit)
            else:
                results = drug_search.search_drugs_comprehensive(query, "name", src, limit)

            st.session_state.drug_search_results = results
            st.success(f"Found {len(results)} results")
        except Exception as e:
            logger.error("Search failed: %s", e)
            st.error(f"Search failed: {e}")


def _display_search_results(results: list[dict[str, Any]]) -> None:
    """Display search results in a table."""
    if not results:
        st.info("No results found")
        return

    # Convert to DataFrame for display
    rows = []
    for r in results:
        row = {
            "Name": r.get("name") or r.get("pref_name") or r.get("drug_name") or r.get("brief_title") or "Unknown",
            "Source": r.get("search_source", "Unknown"),
            "Type": r.get("result_type", "drug"),
        }
        # Add identifiers
        if "cid" in r:
            row["PubChem CID"] = r["cid"]
        if "chembl_id" in r:
            row["ChEMBL ID"] = r["chembl_id"]
        if "drug_id" in r:
            row["Open Targets ID"] = r["drug_id"]
        if "nct_id" in r:
            row["NCT ID"] = r["nct_id"]
        if "inchikey" in r:
            row["InChIKey"] = r["inchikey"][:14] + "..."
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Detail view for selected result
    if len(results) > 0:
        selected_idx = st.selectbox(
            "Select result for details",
            range(len(results)),
            format_func=lambda i: f"{i+1}. {rows[i]['Name']} ({rows[i]['Source']})",
        )
        if st.button("View Details"):
            st.session_state.selected_drug = results[selected_idx]
            st.rerun()


def _render_drug_target_tab() -> None:
    """Drug-target interaction analysis."""
    st.subheader("Drug-Target Interaction Analysis")

    col1, col2 = st.columns([3, 1])
    with col1:
        drug_query = st.text_input(
            "Drug identifier",
            placeholder="Drug name, PubChem CID, ChEMBL ID, or InChIKey",
        )
    with col2:
        id_type = st.selectbox("Identifier type", ["Auto-detect", "Name", "PubChem CID", "ChEMBL ID", "InChIKey"])

    if st.button("Analyze Targets", type="primary"):
        if drug_query:
            _perform_target_analysis(drug_query, id_type)
        else:
            st.warning("Enter a drug identifier")

    # Display results
    if "target_analysis_results" in st.session_state:
        _display_target_analysis(st.session_state.target_analysis_results)


def _perform_target_analysis(drug_query: str, id_type: str) -> None:
    """Perform drug-target analysis."""
    with st.spinner("Analyzing drug-target interactions..."):
        try:
            type_map = {
                "Auto-detect": "auto",
                "Name": "name",
                "PubChem CID": "cid",
                "ChEMBL ID": "chembl_id",
                "InChIKey": "inchikey",
            }
            result = drug_target_analysis.analyze_drug_targets(drug_query, type_map[id_type])
            st.session_state.target_analysis_results = result
            st.success("Analysis complete")
        except Exception as e:
            logger.error("Target analysis failed: %s", e)
            st.error(f"Analysis failed: {e}")


def _display_target_analysis(result: dict[str, Any]) -> None:
    """Display target analysis results."""
    targets = result.get("targets", [])

    if not targets:
        st.info("No targets found")
        return

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Targets", result.get("target_count", 0))
    with col2:
        st.metric("High Confidence", result.get("high_confidence_targets", 0))
    with col3:
        st.metric("Sources", len(result.get("sources_used", [])))

    # Evidence breakdown
    st.write("**Evidence Breakdown**")
    evidence_df = pd.DataFrame(
        list(result.get("evidence_breakdown", {}).items()),
        columns=["Evidence Level", "Count"]
    )
    st.bar_chart(evidence_df.set_index("Evidence Level"))

    # Targets table
    rows = []
    for t in targets:
        rows.append({
            "Target": t.get("target_name") or t.get("target_symbol") or t.get("target_id", "Unknown"),
            "Gene": t.get("gene_symbol", ""),
            "UniProt": t.get("uniprot_id", ""),
            "Evidence": t.get("evidence_level", ""),
            "Confidence": f"{t.get('confidence', 0):.2f}",
            "Mechanism": t.get("mechanism", "")[:50],
            "Action": t.get("action_type", ""),
            "Sources": ", ".join(t.get("sources", [])),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Network visualization
    st.write("**Interaction Network**")
    fig = drug_visualization.create_drug_target_network(
        {"merged": {"name": result.get("drug_identifier"), "targets": targets}},
        max_targets=20,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Pathways
    pathways = result.get("pathways", [])
    if pathways:
        st.write("**Associated Pathways**")
        st.write(", ".join(pathways[:20]))


def _render_gene_drug_tab() -> None:
    """Gene-drug association from VCF/mutation workflow."""
    st.subheader("Gene-Drug Association")
    st.caption("Map genes from variant analysis to known drug associations")

    # Input methods
    input_method = st.radio(
        "Input method",
        ["Single Gene", "Gene List", "From VCF Analysis"],
        horizontal=True,
    )

    if input_method == "Single Gene":
        gene = st.text_input("Gene symbol", placeholder="e.g., EGFR, TP53, BRAF")
        if st.button("Map to Drugs", type="primary") and gene:
            _map_single_gene(gene)

    elif input_method == "Gene List":
        genes_text = st.text_area("Gene symbols (one per line or comma-separated)")
        if st.button("Map Gene List", type="primary") and genes_text:
            genes = [g.strip().upper() for g in genes_text.replace(",", "\n").split("\n") if g.strip()]
            _map_gene_list(genes)

    elif input_method == "From VCF Analysis":
        st.info("This will use genes identified from your VCF analysis")
        if st.button("Use VCF Genes", type="primary"):
            _map_vcf_genes()

    # Display results
    if "gene_drug_results" in st.session_state:
        _display_gene_drug_results(st.session_state.gene_drug_results)


def _map_single_gene(gene: str) -> None:
    """Map single gene to drugs."""
    with st.spinner(f"Mapping {gene} to drug associations..."):
        try:
            result = gene_drug_mapping.map_gene_to_drugs(gene)
            st.session_state.gene_drug_results = {"type": "single", "data": result}
            st.success("Mapping complete")
        except Exception as e:
            logger.error("Gene mapping failed: %s", e)
            st.error(f"Mapping failed: {e}")


def _map_gene_list(genes: list[str]) -> None:
    """Map multiple genes to drugs."""
    with st.spinner(f"Mapping {len(genes)} genes to drug associations..."):
        try:
            result = gene_drug_mapping.map_gene_list_to_drugs(genes)
            st.session_state.gene_drug_results = {"type": "list", "data": result}
            st.success("Mapping complete")
        except Exception as e:
            logger.error("Gene list mapping failed: %s", e)
            st.error(f"Mapping failed: {e}")


def _map_vcf_genes() -> None:
    """Map genes from VCF analysis."""
    # Try to get genes from session state or previous analysis
    vcf_genes = st.session_state.get("vcf_genes", [])
    if not vcf_genes:
        st.warning("No VCF genes found. Please run VCF analysis first.")
        return

    with st.spinner(f"Building VCF-to-drug report for {len(vcf_genes)} genes..."):
        try:
            result = gene_drug_mapping.build_vcf_to_drug_report(vcf_genes)
            st.session_state.gene_drug_results = {"type": "vcf", "data": result}
            st.success("Report generated")
        except Exception as e:
            logger.error("VCF mapping failed: %s", e)
            st.error(f"Mapping failed: {e}")


def _display_gene_drug_results(results: dict[str, Any]) -> None:
    """Display gene-drug mapping results."""
    data = results.get("data", {})
    rtype = results.get("type", "single")

    if rtype == "single":
        _display_single_gene_result(data)
    elif rtype == "list":
        _display_gene_list_result(data)
    elif rtype == "vcf":
        _display_vcf_drug_result(data)


def _display_single_gene_result(data: dict[str, Any]) -> None:
    """Display single gene-drug mapping."""
    gene = data.get("gene_symbol", "Unknown")

    st.write(f"### Results for **{gene}**")

    # Evidence summary
    ev = data.get("evidence_summary", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Drugs", ev.get("total_drugs", 0))
    with col2:
        st.metric("Approved", ev.get("approved", 0))
    with col3:
        st.metric("Clinical", ev.get("clinical", 0))
    with col4:
        st.metric("Preclinical", ev.get("preclinical", 0))

    # Drugs table
    drugs = data.get("target_drugs", [])
    if drugs:
        rows = []
        for d in drugs:
            rows.append({
                "Drug": d.get("drug_name", ""),
                "ChEMBL ID": d.get("drug_id", ""),
                "Phase": d.get("phase", 0),
                "Mechanism": d.get("mechanism_of_action", "")[:50],
                "Target": d.get("target_name", ""),
                "Disease": d.get("disease_name", ""),
                "Score": d.get("score", 0),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Network
        fig = drug_visualization.create_gene_drug_network({"genes": {gene: data}})
        st.plotly_chart(fig, use_container_width=True)

    # Clinical trials
    trials = data.get("clinical_trials", [])
    if trials:
        st.write("**Clinical Trials**")
        trial_rows = []
        for t in trials[:10]:
            trial_rows.append({
                "NCT ID": t.get("nct_id"),
                "Title": t.get("brief_title", "")[:60],
                "Status": t.get("overall_status"),
                "Phase": ", ".join(t.get("phase", [])) if isinstance(t.get("phase"), list) else t.get("phase", ""),
            })
        st.dataframe(pd.DataFrame(trial_rows), use_container_width=True, hide_index=True)

    # Export
    csv_data = drug_report.generate_drug_report_csv({"merged": {"name": gene, "targets": drugs}})
    st.download_button(
        "📥 Download CSV Report",
        csv_data,
        f"{gene}_drug_report.csv",
        "text/csv",
    )


def _display_gene_list_result(data: dict[str, Any]) -> None:
    """Display gene list mapping results."""
    summary = data.get("summary", {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Input Genes", summary.get("total_genes", 0))
    with col2:
        st.metric("Genes with Drugs", summary.get("genes_with_drugs", 0))
    with col3:
        st.metric("Unique Drugs", summary.get("unique_drugs", 0))
    with col4:
        st.metric("Shared Drugs", summary.get("shared_drug_count", 0))

    # Shared drugs
    shared = data.get("shared_drugs", [])
    if shared:
        st.write("**Drugs Targeting Multiple Input Genes**")
        rows = []
        for d in shared:
            rows.append({
                "Drug": d.get("drug_name"),
                "Genes": ", ".join(d.get("genes", [])),
                "Max Phase": d.get("max_phase"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Shared targets
    shared_targets = data.get("shared_targets", [])
    if shared_targets:
        st.write("**Shared Targets**")
        rows = []
        for t in shared_targets:
            rows.append({
                "Target": t.get("target_name"),
                "Genes": ", ".join(t.get("genes", [])),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Network
    fig = drug_visualization.create_gene_drug_network({"genes": data.get("genes", {})})
    st.plotly_chart(fig, use_container_width=True)


def _display_vcf_drug_result(data: dict[str, Any]) -> None:
    """Display VCF-to-drug report."""
    summary = data.get("summary", {})

    st.write("### VCF-to-Drug Analysis Report")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Input Genes", summary.get("total_input_genes", 0))
    with col2:
        st.metric("Genes w/ Drugs", summary.get("genes_with_drug_associations", 0))
    with col3:
        st.metric("Unique Drugs", summary.get("total_unique_drugs", 0))
    with col4:
        st.metric("Clinical Trials", summary.get("total_clinical_trials", 0))

    # Consolidated drugs
    drugs = data.get("consolidated_drugs", [])
    if drugs:
        st.write("**Top Drug Candidates (Across All Genes)**")
        rows = []
        for d in drugs[:20]:
            rows.append({
                "Drug": d.get("drug_name"),
                "Genes": ", ".join(d.get("genes", [])),
                "Max Phase": d.get("max_phase"),
                "Mechanisms": ", ".join(set(d.get("mechanisms", [])))[:50],
                "Indications": ", ".join(set(d.get("indications", [])))[:50],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Clinical trials
    trials = data.get("clinical_trial_opportunities", [])
    if trials:
        st.write("**Clinical Trial Opportunities**")
        trial_rows = []
        for t in trials[:15]:
            trial_rows.append({
                "NCT ID": t.get("nct_id"),
                "Title": t.get("brief_title", "")[:60],
                "Status": t.get("overall_status"),
                "Phase": ", ".join(t.get("phase", [])) if isinstance(t.get("phase"), list) else t.get("phase", ""),
                "Conditions": ", ".join(t.get("conditions", []))[:50],
            })
        st.dataframe(pd.DataFrame(trial_rows), use_container_width=True, hide_index=True)

    # Trial status chart
    if trials:
        fig = drug_visualization.create_clinical_trial_status_chart(trials)
        st.plotly_chart(fig, use_container_width=True)

    # Export
    csv_data = drug_report.generate_gene_drug_report_csv(data)
    st.download_button(
        "📥 Download Full CSV Report",
        csv_data,
        "vcf_drug_report.csv",
        "text/csv",
    )

    json_data = drug_report.generate_vcf_drug_report_json(data)
    st.download_button(
        "📥 Download JSON Report",
        json_data,
        "vcf_drug_report.json",
        "application/json",
    )


def _render_disease_drug_tab() -> None:
    """Disease-drug association."""
    st.subheader("Disease-Drug Association")

    disease = st.text_input("Disease name", placeholder="e.g., breast cancer, Alzheimer's disease, melanoma")
    if st.button("Search", type="primary") and disease:
        _search_disease_drugs(disease)

    if "disease_drug_results" in st.session_state:
        _display_disease_drug_results(st.session_state.disease_drug_results)


def _search_disease_drugs(disease: str) -> None:
    """Search drugs for a disease."""
    with st.spinner("Searching disease-drug associations..."):
        try:
            from geneai.drug_discovery import opentargets_client
            from geneai.drug_discovery import clinical_trials_client

            # Open Targets
            diseases = opentargets_client.search_diseases(disease, limit=5)
            all_drugs = []
            all_trials = []

            for d in diseases:
                disease_id = d.get("disease_id")
                if disease_id:
                    targets = opentargets_client.get_disease_targets(disease_id, limit=20)
                    # Get drugs for each target
                    for t in targets:
                        target_id = t.get("target_id")
                        if target_id:
                            drugs = opentargets_client.get_target_drugs(target_id, limit=10)
                            for drug in drugs:
                                drug["disease_context"] = d.get("disease_name")
                                all_drugs.append(drug)

            # Clinical trials
            trials = clinical_trials_client.search_studies_by_condition(disease, limit=20)

            st.session_state.disease_drug_results = {
                "disease": disease,
                "opentargets_diseases": diseases,
                "drugs": all_drugs,
                "trials": trials,
            }
            st.success("Search complete")
        except Exception as e:
            logger.error("Disease search failed: %s", e)
            st.error(f"Search failed: {e}")


def _display_disease_drug_results(data: dict[str, Any]) -> None:
    """Display disease-drug results."""
    st.write(f"### Results for **{data.get('disease', 'Unknown')}**")

    # Drugs
    drugs = data.get("drugs", [])
    if drugs:
        # Deduplicate
        seen = set()
        unique_drugs = []
        for d in drugs:
            did = d.get("drug_id")
            if did and did not in seen:
                seen.add(did)
                unique_drugs.append(d)

        rows = []
        for d in unique_drugs[:30]:
            rows.append({
                "Drug": d.get("drug_name"),
                "Phase": d.get("phase"),
                "Mechanism": d.get("mechanism_of_action", "")[:50],
                "Target": d.get("target_name"),
                "Disease Context": d.get("disease_context"),
                "Score": d.get("score"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Network
        fig = drug_visualization.create_disease_drug_network({
            "diseases": [{"disease_id": "query", "disease_name": data.get("disease"), "drugs": unique_drugs[:20]}]
        })
        st.plotly_chart(fig, use_container_width=True)

    # Trials
    trials = data.get("trials", [])
    if trials:
        st.write("**Clinical Trials**")
        trial_rows = []
        for t in trials[:15]:
            trial_rows.append({
                "NCT ID": t.get("nct_id"),
                "Title": t.get("brief_title", "")[:60],
                "Status": t.get("overall_status"),
                "Phase": ", ".join(t.get("phase", [])) if isinstance(t.get("phase"), list) else t.get("phase", ""),
            })
        st.dataframe(pd.DataFrame(trial_rows), use_container_width=True, hide_index=True)


def _render_clinical_trials_tab() -> None:
    """Clinical trial explorer."""
    st.subheader("Clinical Trial Explorer")

    search_mode = st.radio("Search by", ["Condition/Disease", "Drug/Intervention", "Gene/Target", "NCT ID"], horizontal=True)

    query = st.text_input("Search query", placeholder="Enter search term...")
    col1, col2 = st.columns(2)
    with col1:
        limit = st.slider("Max results", 5, 100, 20, key="clinical_trials_limit")
    with col2:
        status_filter = st.multiselect(
            "Status filter",
            ["Recruiting", "Not yet recruiting", "Active, not recruiting", "Completed", "Terminated"],
            default=["Recruiting", "Not yet recruiting", "Active, not recruiting"],
        )

    if st.button("Search Trials", type="primary") and query:
        _search_clinical_trials(query, search_mode, limit, status_filter)

    if "trial_results" in st.session_state:
        _display_trial_results(st.session_state.trial_results)


def _search_clinical_trials(query: str, mode: str, limit: int, status_filter: list[str]) -> None:
    """Search clinical trials."""
    with st.spinner("Searching ClinicalTrials.gov..."):
        try:
            from geneai.drug_discovery import clinical_trials_client

            if mode == "Condition/Disease":
                results = clinical_trials_client.search_studies_by_condition(query, limit=limit)
            elif mode == "Drug/Intervention":
                results = clinical_trials_client.search_studies_by_intervention(query, limit=limit)
            elif mode == "Gene/Target":
                results = clinical_trials_client.get_studies_by_target_gene(query, limit=limit)
            else:  # NCT ID
                result = clinical_trials_client.get_study_by_nct_id(query)
                results = [result] if result else []

            # Filter by status
            if status_filter:
                results = [t for t in results if t.get("overall_status") in status_filter]

            st.session_state.trial_results = results
            st.success(f"Found {len(results)} trials")
        except Exception as e:
            logger.error("Trial search failed: %s", e)
            st.error(f"Search failed: {e}")


def _display_trial_results(trials: list[dict[str, Any]]) -> None:
    """Display clinical trial results."""
    if not trials:
        st.info("No trials found")
        return

    # Status chart
    fig = drug_visualization.create_clinical_trial_status_chart(trials)
    st.plotly_chart(fig, use_container_width=True)

    # Trials table
    rows = []
    for t in trials:
        rows.append({
            "NCT ID": t.get("nct_id"),
            "Title": t.get("brief_title", "")[:80],
            "Status": t.get("overall_status"),
            "Phase": ", ".join(t.get("phase", [])) if isinstance(t.get("phase"), list) else t.get("phase", ""),
            "Conditions": ", ".join(t.get("conditions", []))[:60],
            "Interventions": ", ".join([iv.get("name", "") for iv in t.get("interventions", [])])[:60],
            "Sponsor": t.get("sponsor", ""),
            "Locations": len(t.get("locations", [])),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Detail view
    selected = st.selectbox(
        "Select trial for details",
        range(len(trials)),
        format_func=lambda i: f"{trials[i].get('nct_id')}: {trials[i].get('brief_title', '')[:50]}",
    )

    trial = trials[selected]
    with st.expander("Trial Details", expanded=True):
        st.write(f"**NCT ID:** {trial.get('nct_id')}")
        st.write(f"**Title:** {trial.get('official_title') or trial.get('brief_title')}")
        st.write(f"**Status:** {trial.get('overall_status')}")
        st.write(f"**Phase:** {', '.join(trial.get('phase', [])) if isinstance(trial.get('phase'), list) else trial.get('phase')}")
        st.write(f"**Sponsor:** {trial.get('sponsor')}")
        st.write(f"**Conditions:** {', '.join(trial.get('conditions', []))}")
        st.write(f"**Interventions:**")
        for iv in trial.get("interventions", []):
            st.write(f"  - {iv.get('name')} ({iv.get('type')})")
        st.write(f"**Eligibility:** {trial.get('eligibility_criteria', '')[:500]}...")


def _render_chemical_properties_tab() -> None:
    """Chemical properties viewer."""
    st.subheader("Chemical Properties")

    if st.session_state.selected_drug:
        drug = st.session_state.selected_drug
        st.write(f"### {drug.get('name') or drug.get('pref_name') or 'Selected Drug'}")

        # Properties table
        props = {}
        if "molecular_formula" in drug:
            props["Molecular Formula"] = drug.get("molecular_formula")
        if "molecular_weight" in drug:
            props["Molecular Weight"] = f"{drug.get('molecular_weight')} g/mol"
        if "canonical_smiles" in drug:
            props["Canonical SMILES"] = drug.get("canonical_smiles")
        if "isomeric_smiles" in drug:
            props["Isomeric SMILES"] = drug.get("isomeric_smiles")
        if "inchi" in drug:
            props["InChI"] = drug.get("inchi")
        if "inchikey" in drug:
            props["InChIKey"] = drug.get("inchikey")
        if "iupac_name" in drug:
            props["IUPAC Name"] = drug.get("iupac_name")
        if "xlogp3" in drug:
            props["XLogP3"] = drug.get("xlogp3")
        if "tpsa" in drug:
            props["TPSA"] = f"{drug.get('tpsa')} Å²"
        if "hbond_donor_count" in drug:
            props["H-Bond Donors"] = drug.get("hbond_donor_count")
        if "hbond_acceptor_count" in drug:
            props["H-Bond Acceptors"] = drug.get("hbond_acceptor_count")
        if "rotatable_bond_count" in drug:
            props["Rotatable Bonds"] = drug.get("rotatable_bond_count")
        if "max_phase" in drug:
            props["Max Clinical Phase"] = drug.get("max_phase")

        if props:
            df = pd.DataFrame(list(props.items()), columns=["Property", "Value"])
            st.dataframe(df, use_container_width=True, hide_index=True)

        # 2D Structure (if SMILES available)
        smiles = drug.get("canonical_smiles") or drug.get("isomeric_smiles")
        if smiles:
            st.write("**2D Structure**")
            st.code(smiles, language="text")
            # Could add RDKit depiction here if available

    else:
        st.info("Select a drug from the Drug Search tab to view chemical properties")


def _render_visualizations_tab() -> None:
    """Visualizations dashboard."""
    st.subheader("Interactive Visualizations")

    viz_type = st.selectbox(
        "Visualization type",
        [
            "Drug-Target Network",
            "Gene-Drug Network",
            "Disease-Drug Network",
            "Clinical Trial Status",
            "Drug Property Radar",
            "Drug Property Scatter",
            "Target Druggability",
        ],
    )

    if viz_type == "Drug-Target Network":
        if st.session_state.get("target_analysis_results"):
            result = st.session_state.target_analysis_results
            fig = drug_visualization.create_drug_target_network(
                {"merged": {"name": result.get("drug_identifier"), "targets": result.get("targets", [])}},
                max_targets=20,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run a drug-target analysis first")

    elif viz_type == "Gene-Drug Network":
        if st.session_state.get("gene_drug_results"):
            data = st.session_state.gene_drug_results.get("data", {})
            if data.get("type") == "list":
                fig = drug_visualization.create_gene_drug_network({"genes": data.get("genes", {})})
            else:
                fig = drug_visualization.create_gene_drug_network({"genes": {data.get("gene_symbol"): data}})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run a gene-drug mapping first")

    elif viz_type == "Disease-Drug Network":
        if st.session_state.get("disease_drug_results"):
            data = st.session_state.disease_drug_results
            fig = drug_visualization.create_disease_drug_network({
                "diseases": [{"disease_id": "query", "disease_name": data.get("disease"), "drugs": data.get("drugs", [])[:20]}]
            })
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run a disease-drug search first")

    elif viz_type == "Clinical Trial Status":
        if st.session_state.get("trial_results"):
            fig = drug_visualization.create_clinical_trial_status_chart(st.session_state.trial_results)
            st.plotly_chart(fig, use_container_width=True)
        elif st.session_state.get("gene_drug_results", {}).get("data", {}).get("clinical_trial_opportunities"):
            fig = drug_visualization.create_clinical_trial_status_chart(
                st.session_state.gene_drug_results["data"]["clinical_trial_opportunities"]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Search for clinical trials first")

    elif viz_type == "Drug Property Radar":
        if st.session_state.get("comparison_drugs"):
            drugs_data = []
            for d in st.session_state.comparison_drugs:
                detail = drug_search.get_drug_details(d[0], d[1])
                if detail:
                    drugs_data.append(detail)
            if drugs_data:
                fig = drug_visualization.create_drug_property_radar(drugs_data)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add drugs to comparison first")

    elif viz_type == "Drug Property Scatter":
        if st.session_state.get("comparison_drugs"):
            drugs_data = []
            for d in st.session_state.comparison_drugs:
                detail = drug_search.get_drug_details(d[0], d[1])
                if detail:
                    drugs_data.append(detail)
            if drugs_data:
                col1, col2, col3 = st.columns(3)
                with col1:
                    x_prop = st.selectbox("X axis", ["molecular_weight", "xlogp3", "tpsa", "alogp", "psa"])
                with col2:
                    y_prop = st.selectbox("Y axis", ["xlogp3", "molecular_weight", "tpsa", "alogp", "psa"])
                with col3:
                    color_prop = st.selectbox("Color", ["tpsa", "molecular_weight", "xlogp3", "None"])
                fig = drug_visualization.create_drug_property_scatter(
                    drugs_data, x_prop, y_prop, None if color_prop == "None" else color_prop
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add drugs to comparison first")

    elif viz_type == "Target Druggability":
        if st.session_state.get("gene_drug_results"):
            data = st.session_state.gene_drug_results.get("data", {})
            targets = data.get("opentargets_target")
            if targets:
                fig = drug_visualization.create_target_druggability_chart([targets])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No target druggability data available")


def _render_reports_tab() -> None:
    """Report generation and export."""
    st.subheader("Reports & Export")

    report_type = st.selectbox(
        "Report type",
        [
            "Drug Detail Report",
            "Gene-Drug Mapping Report",
            "VCF-to-Drug Analysis Report",
            "Drug Comparison Report",
        ],
    )

    if report_type == "Drug Detail Report":
        if st.session_state.get("target_analysis_results"):
            result = st.session_state.target_analysis_results
            drug_detail = drug_search.get_drug_details(result.get("drug_identifier"), "auto")
            if drug_detail:
                csv_data = drug_report.generate_drug_report_csv(drug_detail)
                st.download_button(
                    "📥 Download CSV",
                    csv_data,
                    f"{result.get('drug_identifier')}_report.csv",
                    "text/csv",
                )
                json_data = json.dumps(drug_detail, indent=2, default=str)
                st.download_button(
                    "📥 Download JSON",
                    json_data,
                    f"{result.get('drug_identifier')}_report.json",
                    "application/json",
                )
        else:
            st.info("Run a drug-target analysis first")

    elif report_type == "Gene-Drug Mapping Report":
        if st.session_state.get("gene_drug_results"):
            data = st.session_state.gene_drug_results.get("data", {})
            csv_data = drug_report.generate_gene_drug_report_csv(data)
            st.download_button(
                "📥 Download CSV",
                csv_data,
                "gene_drug_report.csv",
                "text/csv",
            )
        else:
            st.info("Run a gene-drug mapping first")

    elif report_type == "VCF-to-Drug Analysis Report":
        if st.session_state.get("gene_drug_results", {}).get("type") == "vcf":
            data = st.session_state.gene_drug_results.get("data", {})
            csv_data = drug_report.generate_gene_drug_report_csv(data)
            st.download_button(
                "📥 Download CSV",
                csv_data,
                "vcf_drug_report.csv",
                "text/csv",
            )
            json_data = drug_report.generate_vcf_drug_report_json(data)
            st.download_button(
                "📥 Download JSON",
                json_data,
                "vcf_drug_report.json",
                "application/json",
            )
        else:
            st.info("Run a VCF-to-drug analysis first")

    elif report_type == "Drug Comparison Report":
        if st.session_state.get("comparison_drugs"):
            comparison = drug_comparison.compare_drugs_detailed(st.session_state.comparison_drugs)
            csv_data = drug_report.generate_comparison_report_csv(comparison)
            st.download_button(
                "📥 Download CSV",
                csv_data,
                "drug_comparison_report.csv",
                "text/csv",
            )
            # Text report
            text_report = drug_comparison.generate_comparison_report(st.session_state.comparison_drugs)
            st.download_button(
                "📥 Download Text Report",
                text_report,
                "drug_comparison_report.txt",
                "text/plain",
            )
        else:
            st.info("Add drugs to comparison first")


def _render_vcf_to_drug_tab() -> None:
    """VCF to drug mapping workflow."""
    st.subheader("VCF → Drug Discovery Workflow")
    st.caption("Connect variant analysis to drug discovery")

    st.write("""
    This workflow connects your VCF analysis results to drug databases:
    1. **VCF Upload** → Variant Detection
    2. **Mutation Annotation** → Gene Identification
    3. **Protein Target Identification** → Drug Database Search
    4. **Drug-Target Association** → Evidence-Based Report
    """)

    # Check for existing VCF analysis
    vcf_genes = st.session_state.get("vcf_genes", [])
    if vcf_genes:
        st.success(f"Found {len(vcf_genes)} genes from VCF analysis: {', '.join(vcf_genes[:10])}")

        if st.button("🚀 Run Full VCF-to-Drug Analysis", type="primary"):
            _run_vcf_to_drug_workflow(vcf_genes)
    else:
        st.warning("No VCF analysis found. Please run the VCF Analyzer first.")
        st.write("**Or manually enter genes:**")
        manual_genes = st.text_area("Gene symbols (one per line)", placeholder="EGFR\nTP53\nBRAF\nKRAS")
        if st.button("Analyze Manual Genes", type="primary") and manual_genes:
            genes = [g.strip().upper() for g in manual_genes.split("\n") if g.strip()]
            _run_vcf_to_drug_workflow(genes)

    # Display workflow results
    if "vcf_drug_workflow_results" in st.session_state:
        _display_vcf_workflow_results(st.session_state.vcf_drug_workflow_results)


def _run_vcf_to_drug_workflow(genes: list[str]) -> None:
    """Run the complete VCF-to-drug workflow."""
    progress = st.progress(0)
    status = st.empty()

    try:
        status.write("Step 1/4: Mapping genes to targets...")
        progress.progress(25)

        status.write("Step 2/4: Searching drug databases...")
        progress.progress(50)

        status.write("Step 3/4: Building drug-target associations...")
        progress.progress(75)

        status.write("Step 4/4: Generating report...")
        progress.progress(90)

        result = gene_drug_mapping.build_vcf_to_drug_report(genes)

        progress.progress(100)
        status.write("Complete!")

        st.session_state.vcf_drug_workflow_results = result
        st.success("Workflow complete! View results below.")
    except Exception as e:
        logger.error("VCF-to-drug workflow failed: %s", e)
        st.error(f"Workflow failed: {e}")


def _display_vcf_workflow_results(result: dict[str, Any]) -> None:
    """Display VCF-to-drug workflow results."""
    summary = result.get("summary", {})

    st.write("### Workflow Results")

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Input Genes", summary.get("total_input_genes", 0))
    with col2:
        st.metric("Genes w/ Drugs", summary.get("genes_with_drug_associations", 0))
    with col3:
        st.metric("Unique Drugs", summary.get("total_unique_drugs", 0))
    with col4:
        st.metric("Approved Drugs", summary.get("approved_drugs", 0))
    with col5:
        st.metric("Clinical Trials", summary.get("total_clinical_trials", 0))

    # Drug table
    drugs = result.get("consolidated_drugs", [])
    if drugs:
        st.write("**Drug Candidates**")
        rows = []
        for d in drugs:
            rows.append({
                "Drug": d.get("drug_name"),
                "Genes": ", ".join(d.get("genes", [])),
                "Max Phase": d.get("max_phase"),
                "Mechanisms": ", ".join(set(d.get("mechanisms", [])))[:60],
                "Indications": ", ".join(set(d.get("indications", [])))[:60],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Clinical trials
    trials = result.get("clinical_trial_opportunities", [])
    if trials:
        st.write("**Clinical Trial Opportunities**")
        trial_rows = []
        for t in trials[:15]:
            trial_rows.append({
                "NCT ID": t.get("nct_id"),
                "Title": t.get("brief_title", "")[:60],
                "Status": t.get("overall_status"),
                "Phase": ", ".join(t.get("phase", [])) if isinstance(t.get("phase"), list) else t.get("phase", ""),
            })
        st.dataframe(pd.DataFrame(trial_rows), use_container_width=True, hide_index=True)

    # Export buttons
    csv_data = drug_report.generate_gene_drug_report_csv(result)
    st.download_button(
        "📥 Download CSV Report",
        csv_data,
        "vcf_drug_workflow_report.csv",
        "text/csv",
    )

    json_data = drug_report.generate_vcf_drug_report_json(result)
    st.download_button(
        "📥 Download JSON Report",
        json_data,
        "vcf_drug_workflow_report.json",
        "application/json",
    )

    # Disclaimer
    st.warning(result.get("disclaimer", ""))


# Drug comparison sidebar
def render_drug_comparison_sidebar() -> None:
    """Render drug comparison controls in sidebar."""
    with st.sidebar:
        st.write("### Drug Comparison")
        st.caption("Add drugs to compare side-by-side")

        drug_input = st.text_input("Add drug (name/ID)", key="comp_drug_input")
        id_type = st.selectbox("ID type", ["Auto", "Name", "CID", "ChEMBL", "InChIKey"], key="comp_id_type")

        if st.button("Add to Comparison", key="comp_add"):
            if drug_input:
                type_map = {"Auto": "auto", "Name": "name", "CID": "cid", "ChEMBL": "chembl_id", "InChIKey": "inchikey"}
                drug_tuple = (drug_input, type_map[id_type])
                if drug_tuple not in st.session_state.comparison_drugs:
                    st.session_state.comparison_drugs.append(drug_tuple)
                    st.success(f"Added {drug_input}")
                else:
                    st.warning("Already in comparison")

        # Show current comparison drugs
        if st.session_state.comparison_drugs:
            st.write("**Current drugs:**")
            for i, (drug, dtype) in enumerate(st.session_state.comparison_drugs):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"{i+1}. {drug} ({dtype})")
                with col2:
                    if st.button("✕", key=f"comp_remove_{i}"):
                        st.session_state.comparison_drugs.pop(i)
                        st.rerun()

            if len(st.session_state.comparison_drugs) >= 2:
                if st.button("Compare", type="primary", key="comp_run"):
                    comparison = drug_comparison.compare_drugs_detailed(st.session_state.comparison_drugs)
                    st.session_state.comparison_results = comparison
                    st.success("Comparison ready in Visualizations tab")
            else:
                st.info("Add at least 2 drugs to compare")

            if st.button("Clear All", key="comp_clear"):
                st.session_state.comparison_drugs = []
                st.rerun()