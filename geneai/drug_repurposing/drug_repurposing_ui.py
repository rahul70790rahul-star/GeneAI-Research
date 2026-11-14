"""Drug Repurposing Dashboard UI for GeneAI Research - Phase 4.6."""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
import streamlit as st

from geneai.drug_discovery import clinical_trials_client
from geneai.drug_discovery import drug_search
from geneai.drug_discovery import opentargets_client
from geneai.drug_repurposing import candidate_ranking
from geneai.drug_repurposing import drug_matching
from geneai.drug_repurposing import evidence_scoring
from geneai.drug_repurposing import literature_analysis
from geneai.drug_repurposing import network_analysis
from geneai.drug_repurposing import report_generator
from geneai.drug_repurposing import repurposing_engine
from geneai.drug_repurposing import target_matching

logger = logging.getLogger(__name__)


def render_drug_repurposing_dashboard() -> None:
    """Main entry point for the Drug Repurposing dashboard."""
    st.title("🔬 AI Drug Repurposing Engine")
    st.caption("Identify existing drugs for new therapeutic applications using multi-database evidence integration")

    # Initialize session state
    if "repurposing_results" not in st.session_state:
        st.session_state.repurposing_results = None
    if "selected_candidates" not in st.session_state:
        st.session_state.selected_candidates = []
    if "comparison_indices" not in st.session_state:
        st.session_state.comparison_indices = []

    # Main tabs
    tabs = st.tabs([
        "🎯 Disease Analysis",
        "🧬 Gene Set Analysis",
        "🔬 Mutation Analysis",
        "💊 Drug Candidates",
        "📊 Evidence Scoring",
        "🕸️ Network Visualization",
        "📈 Rankings & Comparison",
        "📄 Reports",
        "🔍 Literature Evidence",
    ])

    with tabs[0]:
        _render_disease_analysis_tab()

    with tabs[1]:
        _render_gene_set_tab()

    with tabs[2]:
        _render_mutation_tab()

    with tabs[3]:
        _render_candidates_tab()

    with tabs[4]:
        _render_evidence_scoring_tab()

    with tabs[5]:
        _render_network_tab()

    with tabs[6]:
        _render_ranking_tab()

    with tabs[7]:
        _render_reports_tab()

    with tabs[8]:
        _render_literature_tab()


def _render_disease_analysis_tab() -> None:
    """Disease-centric repurposing analysis."""
    st.subheader("Disease-Based Repurposing Analysis")
    st.write("Enter a disease name to identify repurposing candidates through genetic and chemical evidence.")

    col1, col2 = st.columns([3, 1])
    with col1:
        disease_input = st.text_input(
            "Disease name",
            placeholder="e.g., Alzheimer's disease, Triple-negative breast cancer, ALS",
            help="Search Open Targets and CTD for disease associations",
            key="repurp_disease_input",
        )
    with col2:
        st.write("")
        st.write("")
        run_analysis = st.button("🚀 Run Analysis", type="primary", use_container_width=True, key="repurp_run_analysis")

    # Advanced options
    with st.expander("Advanced Options"):
        col1, col2, col3 = st.columns(3)
        with col1:
            include_genetic = st.checkbox("Genetic Evidence (Open Targets)", value=True, key="repurp_include_genetic")
        with col2:
            include_chemical = st.checkbox("Chemical Evidence (CTD)", value=True, key="repurp_include_chemical")
        with col3:
            include_literature = st.checkbox("Literature Evidence (PubMed)", value=True, key="repurp_include_literature")

        col1, col2 = st.columns(2)
        with col1:
            min_score = st.slider("Minimum Overall Score", 0.0, 1.0, 0.1, 0.05, key="repurp_min_score")
        with col2:
            max_candidates = st.slider("Max Candidates", 10, 100, 30, key="repurp_max_candidates")

    if run_analysis and disease_input:
        _run_disease_analysis(disease_input, include_genetic, include_chemical, include_literature, min_score, max_candidates)

    # Display results
    if st.session_state.repurposing_results:
        _display_disease_results(st.session_state.repurposing_results)


def _run_disease_analysis(
    disease_name: str,
    include_genetic: bool,
    include_chemical: bool,
    include_literature: bool,
    min_score: float,
    max_candidates: int,
) -> None:
    """Run the disease repurposing analysis."""
    with st.spinner(f"Analyzing repurposing opportunities for {disease_name}..."):
        try:
            engine = repurposing_engine.create_repurposing_engine({
                "max_candidates": max_candidates,
                "min_overall_score": min_score,
            })

            result = engine.analyze_disease(
                disease_name=disease_name,
                include_genetic_evidence=include_genetic,
                include_literature=include_literature,
            )

            if "error" in result:
                st.error(result["error"])
                return

            # Filter by min_score
            candidates = result.get("top_candidates", [])
            filtered = [c for c in candidates if c.get("overall_score", 0) >= min_score]
            result["top_candidates"] = filtered[:max_candidates]

            st.session_state.repurposing_results = result
            st.success(f"Analysis complete! Found {len(filtered)} candidates above score threshold.")

        except Exception as e:
            logger.error("Disease analysis failed: %s", e)
            st.error(f"Analysis failed: {e}")


def _display_disease_results(result: dict[str, Any]) -> None:
    """Display disease analysis results."""
    disease = result.get("disease", {})
    candidates = result.get("top_candidates", [])

    # Disease info header
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Disease", disease.get("name", "N/A"))
    with col2:
        st.metric("Targets Analyzed", result.get("targets_analyzed", 0))
    with col3:
        st.metric("Candidates Found", result.get("candidates_found", 0))
    with col4:
        st.metric("Filtered Candidates", len(candidates))

    # Tabs for different views
    sub_tabs = st.tabs(["📋 Candidates Table", "📊 Score Breakdown", "🎯 Targets", "📈 Visualizations"])

    with sub_tabs[0]:
        _display_candidates_table(candidates)

    with sub_tabs[1]:
        _display_score_breakdown(candidates)

    with sub_tabs[2]:
        _display_targets_table(disease.get("targets", []))

    with sub_tabs[3]:
        _display_disease_visualizations(result)


def _display_candidates_table(candidates: list[dict[str, Any]]) -> None:
    """Display candidates in a sortable table."""
    if not candidates:
        st.info("No candidates meet the score threshold")
        return

    rows = []
    for c in candidates:
        rows.append({
            "Rank": c.get("rank", "N/A"),
            "Drug": c.get("drug_name", "N/A"),
            "Target": c.get("target_symbol", "N/A"),
            "Mechanism": c.get("mechanism_of_action", "N/A")[:50],
            "Phase": c.get("max_phase", "N/A"),
            "Indication": c.get("indication", "N/A"),
            "Score": f"{c.get('overall_score', 0):.3f}",
            "Evidence": c.get("evidence_classification", "N/A"),
            "Sources": ", ".join(c.get("evidence_sources", [])),
            "PMIDs": len(c.get("supporting_pmids", [])),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Selection for comparison
    if len(candidates) >= 2:
        selected = st.multiselect(
            "Select candidates for comparison (max 5)",
            options=range(len(candidates)),
            format_func=lambda i: f"{candidates[i].get('rank', i+1)}. {candidates[i].get('drug_name', 'Unknown')}",
            max_selections=5,
            key="repurp_cand_table_multiselect",
        )
        if st.button("Compare Selected", key="repurp_cand_table_compare"):
            st.session_state.comparison_indices = selected
            st.success(f"Added {len(selected)} candidates to comparison")


def _display_score_breakdown(candidates: list[dict[str, Any]]) -> None:
    """Display detailed score breakdown for candidates."""
    if not candidates:
        return

    # Candidate selector
    idx = st.selectbox(
        "Select candidate for detailed breakdown",
        range(len(candidates)),
        format_func=lambda i: f"{candidates[i].get('rank', i+1)}. {candidates[i].get('drug_name', 'Unknown')} (Score: {candidates[i].get('overall_score', 0):.3f})",
        key="repurp_score_breakdown_idx",
    )

    candidate = candidates[idx]
    breakdown = candidate.get("score_breakdown", {})
    components = breakdown.get("components", [])

    if not components:
        st.info("No detailed score breakdown available")
        return

    # Display component scores
    st.write(f"### {candidate.get('drug_name', 'Unknown')} - Score Breakdown")
    st.metric("Overall Score", f"{candidate.get('overall_score', 0):.3f}")
    st.metric("Evidence Classification", candidate.get("evidence_classification", "N/A"))

    # Component table
    comp_rows = []
    for comp in components:
        comp_rows.append({
            "Component": comp.get("name", "").replace("_", " ").title(),
            "Score": f"{comp.get('score', 0):.3f}",
            "Weight": f"{comp.get('weight', 0):.3f}",
            "Weighted Score": f"{comp.get('weighted_score', 0):.3f}",
            "Description": comp.get("description", "N/A"),
            "Source": comp.get("source", "N/A"),
        })

    df = pd.DataFrame(comp_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Limitations
    st.write("**Limitations:**")
    for comp in components:
        for lim in comp.get("limitations", []):
            st.caption(f"• {comp.get('name', '')}: {lim}")

    # Summary
    summary = breakdown.get("summary", {})
    if summary:
        st.write("**Summary:**")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"Strongest: {summary.get('strongest_evidence', {}).get('component', 'N/A')} ({summary.get('strongest_evidence', {}).get('score', 'N/A')})")
        with col2:
            st.write(f"Weakest: {summary.get('weakest_evidence', {}).get('component', 'N/A')} ({summary.get('weakest_evidence', {}).get('score', 'N/A')})")


def _display_targets_table(targets: list[dict[str, Any]]) -> None:
    """Display disease-associated targets."""
    if not targets:
        st.info("No targets found")
        return

    rows = []
    for t in targets:
        rows.append({
            "Target ID": t.get("target_id", "N/A"),
            "Gene Symbol": t.get("approved_symbol", "N/A"),
            "Target Name": t.get("approved_name", "N/A"),
            "Association Score": f"{t.get('association_score', 0):.3f}" if t.get("association_score") else "N/A",
            "Biotype": t.get("biotype", "N/A"),
            "Known Drugs": t.get("known_drugs_count", "N/A"),
            "Tractability (SM)": t.get("tractability_small_molecule", "N/A"),
            "Tractability (Ab)": t.get("tractability_antibody", "N/A"),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _display_disease_visualizations(result: dict[str, Any]) -> None:
    """Display visualizations for disease analysis."""
    candidates = result.get("top_candidates", [])
    disease = result.get("disease", {})

    if not candidates:
        return

    viz_type = st.selectbox(
        "Visualization",
        ["Candidate Rankings", "Evidence Comparison", "Phase Distribution", "Evidence Classes"],
        key="repurp_disease_viz_type",
    )

    if viz_type == "Candidate Rankings":
        fig = network_analysis.create_candidate_ranking_chart(candidates, top_n=15)
        st.plotly_chart(fig, use_container_width=True, key="repurp_candidate_rankings_chart")

    elif viz_type == "Evidence Comparison":
        fig = network_analysis.create_evidence_comparison_chart(candidates, top_n=10)
        st.plotly_chart(fig, use_container_width=True, key="repurp_evidence_comparison_chart")

    elif viz_type == "Phase Distribution":
        fig = network_analysis.create_phase_distribution_chart(candidates)
        st.plotly_chart(fig, use_container_width=True, key="repurp_phase_distribution_chart")

    elif viz_type == "Evidence Classes":
        fig = network_analysis.create_evidence_class_distribution(candidates)
        st.plotly_chart(fig, use_container_width=True, key="repurp_evidence_classes_chart")


def _render_gene_set_tab() -> None:
    """Gene set analysis for repurposing."""
    st.subheader("Gene Set Repurposing Analysis")
    st.write("Enter a list of genes (e.g., from pathway analysis or VCF) to find shared drug targets.")

    genes_input = st.text_area(
        "Gene symbols (one per line or comma-separated)",
        placeholder="EGFR\nTP53\nBRAF\nKRAS\nPTEN",
        height=150,
        key="repurp_genes_input",
    )

    disease_context = st.text_input(
        "Disease context (optional)",
        placeholder="e.g., Non-small cell lung cancer",
        help="Provides disease-specific prioritization",
        key="repurp_disease_context",
    )

    if st.button("Analyze Gene Set", type="primary", key="repurp_analyze_gene_set") and genes_input:
        genes = [g.strip().upper() for g in genes_input.replace(",", "\n").split("\n") if g.strip()]
        if genes:
            _run_gene_set_analysis(genes, disease_context)

    if st.session_state.get("gene_set_results"):
        _display_gene_set_results(st.session_state.gene_set_results)


def _run_gene_set_analysis(genes: list[str], disease_context: str | None) -> None:
    """Run gene set analysis."""
    with st.spinner(f"Analyzing {len(genes)} genes for repurposing..."):
        try:
            result = drug_matching.match_genes_to_drugs(genes, disease_context=disease_context)
            st.session_state.gene_set_results = result
            st.success(f"Analysis complete! Found {len(result.get('all_drugs', []))} drug associations.")
        except Exception as e:
            logger.error("Gene set analysis failed: %s", e)
            st.error(f"Analysis failed: {e}")


def _display_gene_set_results(result: dict[str, Any]) -> None:
    """Display gene set analysis results."""
    drugs = result.get("all_drugs", [])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Input Genes", len(result.get("input_genes", [])))
    with col2:
        st.metric("Unique Drugs", len(drugs))
    with col3:
        st.metric("Shared Drugs", len(result.get("shared_drugs", [])))

    if drugs:
        st.write("### Drug Associations")
        rows = []
        for d in drugs[:30]:
            rows.append({
                "Drug": d.get("drug_name", "N/A"),
                "Drug ID": d.get("drug_id", "N/A"),
                "Target Genes": ", ".join(d.get("target_genes", [])),
                "Gene Count": d.get("gene_count", 0),
                "Max Phase": d.get("max_phase", 0),
                "Mechanisms": ", ".join(d.get("mechanisms", []))[:50],
                "Indications": ", ".join(d.get("indications", []))[:50],
                "Score": f"{d.get('repurposing_score', 0):.3f}",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Shared drugs
    shared = result.get("shared_drugs", [])
    if shared:
        st.write("### Drugs Targeting Multiple Input Genes")
        rows = []
        for d in shared:
            rows.append({
                "Drug": d.get("drug_name", "N/A"),
                "Genes": ", ".join(d.get("genes", [])),
                "Max Phase": d.get("max_phase", 0),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_mutation_tab() -> None:
    """Mutation-specific repurposing analysis."""
    st.subheader("Mutation-Based Repurposing")
    st.write("Analyze a specific gene variant for drug repurposing opportunities.")

    col1, col2 = st.columns(2)
    with col1:
        gene = st.text_input("Gene symbol", placeholder="EGFR", key="repurp_mutation_gene")
    with col2:
        protein_change = st.text_input("Protein change (optional)", placeholder="p.L858R", key="repurp_mutation_protein_change")

    hgvs = st.text_input("HGVS notation (optional)", placeholder="NM_005228.5:c.2573T>G", key="repurp_mutation_hgvs")

    if st.button("Analyze Mutation", type="primary", key="repurp_analyze_mutation") and gene:
        variant_info = {}
        if protein_change:
            variant_info["protein_change"] = protein_change
        if hgvs:
            variant_info["hgvs"] = hgvs

        _run_mutation_analysis(gene, variant_info)

    if st.session_state.get("mutation_results"):
        _display_mutation_results(st.session_state.mutation_results)


def _run_mutation_analysis(gene: str, variant_info: dict[str, Any]) -> None:
    """Run mutation analysis."""
    with st.spinner(f"Analyzing {gene} variant for repurposing..."):
        try:
            engine = repurposing_engine.create_repurposing_engine()
            result = engine.analyze_mutation(gene, variant_info)
            st.session_state.mutation_results = result
            st.success("Analysis complete!")
        except Exception as e:
            logger.error("Mutation analysis failed: %s", e)
            st.error(f"Analysis failed: {e}")


def _display_mutation_results(result: dict[str, Any]) -> None:
    """Display mutation analysis results."""
    st.write(f"### Results for {result.get('gene_symbol', 'Unknown')}")

    if result.get("variant_specific"):
        st.write("**Variant-Specific Annotations:**")
        for key, val in result["variant_specific"].items():
            st.write(f"- **{key}:** {val}")

    candidates = result.get("candidates", [])
    if candidates:
        rows = []
        for c in candidates[:20]:
            rows.append({
                "Drug": c.get("drug_name", "N/A"),
                "Target": c.get("target_symbol", "N/A"),
                "Mechanism": c.get("mechanism_of_action", "N/A")[:50],
                "Phase": c.get("max_phase", 0),
                "Indication": c.get("indication", "N/A"),
                "Score": f"{c.get('overall_score', 0):.3f}",
                "Evidence": c.get("evidence_classification", "N/A"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if result.get("disclaimer"):
        st.warning(result["disclaimer"])


def _render_candidates_tab() -> None:
    """Drug candidate browser."""
    st.subheader("Drug Candidate Browser")
    st.write("Browse and filter repurposing candidates from previous analyses.")

    if st.session_state.repurposing_results:
        candidates = st.session_state.repurposing_results.get("top_candidates", [])

        if candidates:
            # Filters
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                min_score = st.slider("Min Score", 0.0, 1.0, 0.0, 0.05, key="repurp_cand_min_score")
            with col2:
                min_phase = st.selectbox("Min Phase", [0, 1, 2, 3, 4], index=0, key="repurp_cand_min_phase")
            with col3:
                evidence_filter = st.multiselect(
                    "Evidence Class",
                    ["clinical_evidence_same_indication", "clinical_evidence_approved_drug",
                     "strong_experimental_evidence", "moderate_experimental_evidence",
                     "strong_genetic_evidence", "computational_prediction"],
                    default=[],
                    key="repurp_cand_evidence_filter",
                )
            with col4:
                require_mech = st.checkbox("Require Mechanism", key="repurp_cand_require_mech")

            # Apply filters
            filtered = candidate_ranking.filter_candidates(
                candidates,
                min_score=min_score,
                min_phase=min_phase,
                evidence_classes=evidence_filter if evidence_filter else None,
                require_mechanism=require_mech,
            )

            st.write(f"Showing {len(filtered)} of {len(candidates)} candidates")
            _display_candidates_table(filtered)
        else:
            st.info("No candidates available. Run a disease analysis first.")
    else:
        st.info("Run a disease analysis or gene set analysis to populate candidates")


def _render_evidence_scoring_tab() -> None:
    """Evidence scoring configuration and analysis."""
    st.subheader("Evidence Scoring Framework")
    st.write("Configure and inspect the explainable AI scoring for repurposing candidates.")

    # Scoring weights configuration
    st.write("### Scoring Weights Configuration")

    default_weights = evidence_scoring.EvidenceScorer.DEFAULT_WEIGHTS
    weights = {}

    cols = st.columns(len(default_weights))
    for i, (component, default_weight) in enumerate(default_weights.items()):
        with cols[i]:
            weights[component] = st.slider(
                component.replace("_", " ").title(),
                0.0, 1.0, default_weight, 0.05,
                help=f"Weight for {component} in overall score",
                key=f"repurp_weight_{component}",
            )

    # Normalize weights
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
        st.write("**Normalized Weights:**")
        for k, v in weights.items():
            st.write(f"- {k}: {v:.3f}")

    # Test scoring on candidates
    if st.session_state.repurposing_results:
        candidates = st.session_state.repurposing_results.get("top_candidates", [])
        if candidates:
            st.write("### Rescore Top Candidates with New Weights")
            if st.button("Rescore Candidates", key="repurp_rescore_candidates"):
                disease_info = st.session_state.repurposing_results.get("disease", {})
                scored = evidence_scoring.score_candidates_batch(candidates, disease_info, weights)
                for c in scored:
                    c["ranking_strategy"] = "custom_weights"
                scored.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
                for i, c in enumerate(scored):
                    c["rank"] = i + 1
                st.session_state.rescored_candidates = scored
                st.success("Rescoring complete!")

            if "rescored_candidates" in st.session_state:
                _display_candidates_table(st.session_state.rescored_candidates)
    else:
        st.info("Run a disease analysis to test scoring configuration")


def _render_network_tab() -> None:
    """Network visualization tab."""
    st.subheader("Network Visualizations")
    st.write("Interactive network graphs for disease-gene-drug relationships.")

    if not st.session_state.repurposing_results:
        st.info("Run a disease analysis first to generate networks")
        return

    result = st.session_state.repurposing_results
    disease = result.get("disease", {})
    candidates = result.get("top_candidates", [])
    targets = disease.get("targets", [])

    viz_type = st.selectbox(
        "Network Type",
        [
            "Disease-Gene-Drug Network",
            "Drug-Target Network",
            "Target-Disease Network",
            "Export Network Data",
        ],
        key="repurp_network_viz_type",
    )

    if viz_type == "Disease-Gene-Drug Network":
        gene_symbols = [t.get("approved_symbol") for t in targets[:15] if t.get("approved_symbol")]
        fig = network_analysis.create_disease_gene_drug_network(
            disease.get("name", "Unknown"),
            gene_symbols,
            candidates,
        )
        st.plotly_chart(fig, use_container_width=True, key="repurp_disease_gene_drug_network")

    elif viz_type == "Drug-Target Network":
        fig = network_analysis.create_drug_target_network(candidates)
        st.plotly_chart(fig, use_container_width=True, key="repurp_drug_target_network")

    elif viz_type == "Target-Disease Network":
        target_symbol = st.selectbox(
            "Select Target",
            [t.get("approved_symbol") for t in targets if t.get("approved_symbol")],
            key="repurp_target_symbol",
        )
        if target_symbol:
            target_diseases = [t for t in targets if t.get("approved_symbol") == target_symbol]
            fig = network_analysis.create_target_disease_network(target_symbol, target_diseases)
            st.plotly_chart(fig, use_container_width=True, key="repurp_target_disease_network")

    elif viz_type == "Export Network Data":
        network_data = network_analysis.export_network_data(candidates, disease.get("name"))
        st.download_button(
            "Download Network JSON",
            json.dumps(network_data, indent=2),
            f"{disease.get('name', 'network')}_network.json",
            "application/json",
            key="repurp_download_network_json",
        )
        st.write(f"Nodes: {len(network_data['nodes'])}, Edges: {len(network_data['edges'])}")


def _render_ranking_tab() -> None:
    """Candidate ranking and comparison."""
    st.subheader("Candidate Ranking & Comparison")
    st.write("Rank candidates using different strategies and compare side-by-side.")

    if not st.session_state.repurposing_results:
        st.info("Run a disease analysis first")
        return

    candidates = st.session_state.repurposing_results.get("top_candidates", [])
    if not candidates:
        st.info("No candidates available")
        return

    # Ranking strategy
    strategy = st.selectbox(
        "Ranking Strategy",
        ["evidence_based", "phase_based", "target_based", "literature_based", "hybrid"],
        format_func=lambda s: s.replace("_", " ").title(),
        key="repurp_ranking_strategy",
    )

    if st.button("Rank Candidates", key="repurp_rank_candidates"):
        disease_info = st.session_state.repurposing_results.get("disease", {})
        ranked = candidate_ranking.rank_candidates(candidates, disease_info, strategy)
        st.session_state.ranked_candidates = ranked
        st.success(f"Ranked {len(ranked)} candidates using {strategy.replace('_', ' ')}")

    if "ranked_candidates" in st.session_state:
        _display_candidates_table(st.session_state.ranked_candidates)

    # Comparison section
    st.divider()
    st.write("### Candidate Comparison")

    if st.session_state.comparison_indices:
        indices = st.session_state.comparison_indices
        comparison = candidate_ranking.compare_candidates(
            st.session_state.ranked_candidates if "ranked_candidates" in st.session_state else candidates,
            indices,
        )

        if comparison:
            st.write("**Common Attributes:**")
            for attr, val in comparison.get("common_attributes", {}).items():
                st.write(f"- **{attr}:** {val}")

            st.write("**Differing Attributes:**")
            for attr, vals in comparison.get("differing_attributes", {}).items():
                st.write(f"- **{attr}:** {', '.join(str(v) for v in vals)}")

            # Export comparison
            csv_data = report_generator.generate_candidate_comparison_csv(
                st.session_state.ranked_candidates if "ranked_candidates" in st.session_state else candidates,
                indices,
            )
            st.download_button(
                "Download Comparison CSV",
                csv_data,
                "candidate_comparison.csv",
                "text/csv",
                key="repurp_download_comparison_csv",
            )
    else:
        st.info("Select candidates from the Candidates tab to compare")


def _render_reports_tab() -> None:
    """Report generation and export."""
    st.subheader("Reports & Export")
    st.write("Generate downloadable reports for repurposing analysis.")

    if not st.session_state.repurposing_results:
        st.info("Run a disease analysis first")
        return

    result = st.session_state.repurposing_results

    report_type = st.selectbox(
        "Report Format",
        ["Full CSV Report", "JSON Report", "Markdown Summary", "Candidate Comparison CSV"],
        key="repurp_report_type",
    )

    if report_type == "Full CSV Report":
        csv_data = report_generator.generate_repurposing_report_csv(result)
        st.download_button(
            "📥 Download Full CSV Report",
            csv_data,
            f"{result.get('disease', {}).get('name', 'repurposing')}_report.csv",
            "text/csv",
            key="repurp_download_csv_report",
        )

    elif report_type == "JSON Report":
        json_data = report_generator.generate_repurposing_report_json(result)
        st.download_button(
            "📥 Download JSON Report",
            json_data,
            f"{result.get('disease', {}).get('name', 'repurposing')}_report.json",
            "application/json",
            key="repurp_download_json_report",
        )

    elif report_type == "Markdown Summary":
        md_content = report_generator.build_repurposing_summary_report(result)
        st.download_button(
            "📥 Download Markdown Report",
            md_content,
            f"{result.get('disease', {}).get('name', 'repurposing')}_report.md",
            "text/markdown",
            key="repurp_download_md_report",
        )
        st.markdown(md_content)

    elif report_type == "Candidate Comparison CSV":
        if st.session_state.comparison_indices:
            candidates = st.session_state.ranked_candidates if "ranked_candidates" in st.session_state else result.get("top_candidates", [])
            csv_data = report_generator.generate_candidate_comparison_csv(candidates, st.session_state.comparison_indices)
            st.download_button(
                "📥 Download Comparison CSV",
                csv_data,
                "candidate_comparison.csv",
                "text/csv",
                key="repurp_download_comparison_csv_report",
            )
        else:
            st.info("Select candidates for comparison first")


def _render_literature_tab() -> None:
    """Literature evidence tab."""
    st.subheader("Literature Evidence")
    st.write("Retrieve and analyze PubMed publications supporting repurposing candidates.")

    if not st.session_state.repurposing_results:
        st.info("Run a disease analysis first")
        return

    candidates = st.session_state.repurposing_results.get("top_candidates", [])
    if not candidates:
        st.info("No candidates available")
        return

    # Candidate selector
    idx = st.selectbox(
        "Select candidate for literature analysis",
        range(len(candidates)),
        format_func=lambda i: f"{candidates[i].get('rank', i+1)}. {candidates[i].get('drug_name', 'Unknown')}",
        key="repurp_lit_candidate_idx",
    )

    candidate = candidates[idx]
    drug_name = candidate.get("drug_name")
    target_symbol = candidate.get("target_symbol")
    disease_name = st.session_state.repurposing_results.get("disease", {}).get("name")

    if st.button("Fetch Literature Evidence", type="primary", key="repurp_fetch_literature") and drug_name:
        _fetch_literature_evidence(drug_name, disease_name, target_symbol)

    if "literature_results" in st.session_state:
        _display_literature_results(st.session_state.literature_results, drug_name)


def _fetch_literature_evidence(drug_name: str, disease_name: str | None, target_symbol: str | None) -> None:
    """Fetch literature evidence for a candidate."""
    with st.spinner(f"Searching PubMed for {drug_name}..."):
        try:
            summary = literature_analysis.build_literature_evidence_summary(
                drug_name=drug_name,
                disease_name=disease_name,
                target_symbol=target_symbol,
                limit=30,
            )
            st.session_state.literature_results = summary
            st.success(f"Found {summary.get('total_publications', 0)} publications, {summary.get('relevant_findings', 0)} relevant")
        except Exception as e:
            logger.error("Literature search failed: %s", e)
            st.error(f"Literature search failed: {e}")


def _display_literature_results(summary: dict[str, Any], drug_name: str) -> None:
    """Display literature analysis results."""
    st.write(f"### Literature Evidence for {drug_name}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Publications", summary.get("total_publications", 0))
    with col2:
        st.metric("Relevant Findings", summary.get("relevant_findings", 0))
    with col3:
        st.metric("Evidence Levels", len(summary.get("evidence_levels", {})))

    # Finding types
    if summary.get("finding_types"):
        st.write("**Finding Types:**")
        type_df = pd.DataFrame(list(summary["finding_types"].items()), columns=["Type", "Count"])
        st.bar_chart(type_df.set_index("Type"))

    # Evidence levels
    if summary.get("evidence_levels"):
        st.write("**Evidence Levels:**")
        level_df = pd.DataFrame(list(summary["evidence_levels"].items()), columns=["Level", "Count"])
        st.bar_chart(level_df.set_index("Level"))

    # Top findings
    if summary.get("top_findings"):
        st.write("**Top Relevant Findings:**")
        for finding in summary["top_findings"][:10]:
            with st.expander(f"{finding.get('finding_type', 'unknown').title()} - PMID: {finding.get('pmid')}"):
                st.write(f"**Title:** {finding.get('title', 'N/A')}")
                st.write(f"**Journal:** {finding.get('journal', 'N/A')} ({finding.get('pub_date', 'N/A')})")
                st.write(f"**Relevance:** {finding.get('relevance', 'N/A')}")
                st.write(f"**Evidence Level:** {finding.get('evidence_level', 'N/A')}")
                if finding.get("key_sentences"):
                    st.write("**Key Sentences:**")
                    for sent in finding["key_sentences"]:
                        st.caption(sent)
                st.link_button("Open in PubMed", finding.get("url", ""))

    # Limitations
    st.warning("Limitations: " + "; ".join(summary.get("limitations", [])))