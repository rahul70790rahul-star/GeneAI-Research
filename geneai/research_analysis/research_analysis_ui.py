"""Research Paper Analysis Dashboard for GeneAI Research - Phase 4.8."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from geneai.research_analysis import (
    search_all_sources,
    analyze_paper,
    identify_gaps_from_papers,
    generate_gap_report,
    compare_papers,
    create_research_assistant,
    generate_drug_discovery_report,
    generate_analysis_report_csv,
    generate_analysis_report_json,
    generate_gap_report_csv,
    generate_comparison_report_csv,
    generate_pdf_report,
    generate_executive_summary,
    PaperComparison,
    GapAnalysisResult,
)

logger = logging.getLogger(__name__)


def render_research_analysis_dashboard() -> None:
    """Main entry point for the Research Paper Analysis dashboard."""
    st.title("📚 Advanced Research Paper Analysis Engine")
    st.caption("AI-powered literature search, analysis, and drug discovery intelligence")

    # Initialize session state
    _init_session_state()

    # Main tabs
    tabs = st.tabs([
        "🔍 Paper Search",
        "📄 Paper Analyzer",
        "🧬 Entity Extraction",
        "💊 Drug Discovery Intelligence",
        "🔬 Research Gap Detection",
        "⚖️ Multi-Paper Comparison",
        "🤖 AI Research Assistant",
        "📊 Report Generator",
    ])

    with tabs[0]:
        _render_paper_search_tab()

    with tabs[1]:
        _render_paper_analyzer_tab()

    with tabs[2]:
        _render_entity_extraction_tab()

    with tabs[3]:
        _render_drug_intelligence_tab()

    with tabs[4]:
        _render_gap_detection_tab()

    with tabs[5]:
        _render_comparison_tab()

    with tabs[6]:
        _render_research_assistant_tab()

    with tabs[7]:
        _render_report_generator_tab()


def _init_session_state() -> None:
    """Initialize session state variables."""
    defaults = {
        "ra_search_results": None,
        "ra_selected_papers": [],
        "ra_analyzed_papers": [],
        "ra_gap_analysis": None,
        "ra_comparison": None,
        "ra_assistant": None,
        "ra_drug_intelligence": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_paper_search_tab() -> None:
    """Paper search interface."""
    st.subheader("Multi-Source Literature Search")

    col1, col2 = st.columns([3, 1])

    with col1:
        query = st.text_input(
            "Search query",
            placeholder="e.g., BRCA1 breast cancer therapy, EGFR inhibitor resistance, Alzheimer amyloid beta",
            key="ra_search_query",
        )

        search_type = st.selectbox(
            "Search focus",
            ["General", "Gene/Protein", "Disease", "Drug/Compound", "Pathway", "Mutation/Variant"],
            key="ra_search_type",
        )

    with col2:
        sources = st.multiselect(
            "Data sources",
            ["PubMed", "Europe PMC", "Crossref", "OpenAlex"],
            default=["PubMed", "Europe PMC", "OpenAlex"],
            key="ra_search_sources",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            limit = st.slider("Results per source", 5, 50, 20, key="ra_search_limit")
        with col_b:
            year_from = st.number_input("Year from", 1990, 2026, 2020, key="ra_search_year_from")
            year_to = st.number_input("Year to", 1990, 2026, 2026, key="ra_search_year_to")

    if st.button("🔍 Search", type="primary", use_container_width=True, key="ra_search_btn"):
        if query:
            _perform_search(query, sources, limit, year_from, year_to)
        else:
            st.warning("Please enter a search query")

    # Display results
    if st.session_state.ra_search_results:
        _display_search_results(st.session_state.ra_search_results)


def _perform_search(
    query: str,
    sources: list[str],
    limit: int,
    year_from: int,
    year_to: int,
) -> None:
    """Perform multi-source literature search."""
    source_map = {
        "PubMed": "pubmed",
        "Europe PMC": "europe_pmc",
        "Crossref": "crossref",
        "OpenAlex": "openalex",
    }
    src = [source_map[s] for s in sources]

    with st.spinner(f"Searching {len(src)} sources..."):
        try:
            results = search_all_sources(query, limit, src, year_from, year_to)
            st.session_state.ra_search_results = results
            total = sum(len(v) for v in results.values())
            st.success(f"Found {total} papers across {len(src)} sources")
        except Exception as e:
            logger.error("Search failed: %s", e)
            st.error(f"Search failed: {e}")


def _display_search_results(results: dict[str, list[dict[str, Any]]]) -> None:
    """Display search results from all sources."""
    for source, papers in results.items():
        if not papers:
            continue

        with st.expander(f"📚 {source} ({len(papers)} papers)", expanded=True):
            for paper in papers:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])

                    with col1:
                        st.markdown(f"**{paper.get('title', 'Untitled')}**")

                        meta_parts = []
                        if paper.get("pmid"):
                            meta_parts.append(f"PMID: {paper['pmid']}")
                        if paper.get("doi"):
                            meta_parts.append(f"DOI: {paper['doi']}")
                        if paper.get("pmcid"):
                            meta_parts.append(f"PMCID: {paper['pmcid']}")
                        if paper.get("year"):
                            meta_parts.append(f"Year: {paper['year']}")
                        if paper.get("journal"):
                            meta_parts.append(f"Journal: {paper['journal']}")
                        if paper.get("authors"):
                            meta_parts.append(f"Authors: {paper['authors'][:100]}...")

                        st.caption(" · ".join(meta_parts))

                        if paper.get("abstract"):
                            with st.expander("Abstract"):
                                st.write(paper["abstract"][:500] + "..." if len(paper["abstract"]) > 500 else paper["abstract"])

                    with col2:
                        # Checkbox for selection
                        paper_id = paper.get("pmid") or paper.get("doi") or paper.get("title", "")[:50]
                        is_selected = any(p.get("pmid") == paper.get("pmid") or p.get("doi") == paper.get("doi") for p in st.session_state.ra_selected_papers)

                        if st.checkbox("Select", value=is_selected, key=f"ra_select_{paper_id}"):
                            if not is_selected:
                                st.session_state.ra_selected_papers.append(paper)
                        else:
                            st.session_state.ra_selected_papers = [
                                p for p in st.session_state.ra_selected_papers
                                if not (p.get("pmid") == paper.get("pmid") or p.get("doi") == paper.get("doi"))
                            ]

                        if paper.get("url"):
                            st.link_button("Open", paper["url"], use_container_width=True)

    # Selected papers summary
    if st.session_state.ra_selected_papers:
        st.divider()
        st.subheader(f"Selected Papers ({len(st.session_state.ra_selected_papers)})")

        cols = st.columns(3)
        with cols[0]:
            if st.button("📄 Analyze Selected", type="primary", use_container_width=True, key="ra_analyze_btn"):
                _analyze_selected_papers()

        with cols[1]:
            if st.button("⚖️ Compare Selected", use_container_width=True, key="ra_compare_btn"):
                if len(st.session_state.ra_selected_papers) >= 2:
                    _compare_selected_papers()
                else:
                    st.warning("Select at least 2 papers for comparison")

        with cols[2]:
            if st.button("🗑️ Clear Selection", use_container_width=True, key="ra_clear_btn"):
                st.session_state.ra_selected_papers = []
                st.rerun()

        # Show selected papers
        for i, paper in enumerate(st.session_state.ra_selected_papers):
            st.caption(f"{i+1}. {paper.get('title', 'Untitled')[:80]}... (PMID: {paper.get('pmid', 'N/A')})")


def _analyze_selected_papers() -> None:
    """Analyze all selected papers."""
    with st.spinner(f"Analyzing {len(st.session_state.ra_selected_papers)} papers..."):
        try:
            analyzed = []
            progress = st.progress(0)
            for i, paper in enumerate(st.session_state.ra_selected_papers):
                result = analyze_paper(paper)
                analyzed.append(result)
                progress.progress((i + 1) / len(st.session_state.ra_selected_papers))

            st.session_state.ra_analyzed_papers = analyzed
            st.success(f"Analysis complete for {len(analyzed)} papers!")

            # Auto-run gap analysis
            gap_analysis = identify_gaps_from_papers(analyzed)
            st.session_state.ra_gap_analysis = gap_analysis

            # Create research assistant
            st.session_state.ra_assistant = create_research_assistant(analyzed)

        except Exception as e:
            logger.error("Analysis failed: %s", e)
            st.error(f"Analysis failed: {e}")


def _compare_selected_papers() -> None:
    """Compare selected papers."""
    if len(st.session_state.ra_selected_papers) < 2:
        st.warning("Need at least 2 papers for comparison")
        return

    # Ensure papers are analyzed first
    if not st.session_state.ra_analyzed_papers or len(st.session_state.ra_analyzed_papers) != len(st.session_state.ra_selected_papers):
        _analyze_selected_papers()

    if st.session_state.ra_analyzed_papers:
        with st.spinner("Comparing papers..."):
            try:
                comparison = compare_papers(st.session_state.ra_analyzed_papers)
                st.session_state.ra_comparison = comparison
                st.success("Comparison complete!")
            except Exception as e:
                logger.error("Comparison failed: %s", e)
                st.error(f"Comparison failed: {e}")


def _render_paper_analyzer_tab() -> None:
    """Paper analyzer interface."""
    st.subheader("Paper Analysis Results")

    if not st.session_state.ra_analyzed_papers:
        st.info("Select and analyze papers from the Paper Search tab to see results here.")
        return

    # Paper selector
    paper_options = []
    for i, paper in enumerate(st.session_state.ra_analyzed_papers):
        meta = paper.get("metadata", {})
        label = f"{i+1}. {meta.get('title', 'Untitled')[:60]}... (PMID: {meta.get('pmid', 'N/A')})"
        paper_options.append(label)

    selected_idx = st.selectbox("Select paper to view", range(len(paper_options)), format_func=lambda x: paper_options[x], key="ra_paper_selector")

    if selected_idx is not None:
        paper = st.session_state.ra_analyzed_papers[selected_idx]
        _display_paper_analysis(paper)


def _display_paper_analysis(paper: dict[str, Any]) -> None:
    """Display detailed paper analysis."""
    metadata = paper.get("metadata", {})
    entities = paper.get("entities", {})
    summary = paper.get("summary", {})
    dt_rels = paper.get("drug_target_relationships", [])

    # Metadata
    with st.expander("📋 Paper Metadata", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Title:** {metadata.get('title', 'N/A')}")
            st.write(f"**PMID:** {metadata.get('pmid', 'N/A')}")
            st.write(f"**DOI:** {metadata.get('doi', 'N/A')}")
            st.write(f"**PMCID:** {metadata.get('pmcid', 'N/A')}")
        with col2:
            st.write(f"**Authors:** {metadata.get('authors', 'N/A')}")
            st.write(f"**Journal:** {metadata.get('journal', 'N/A')}")
            st.write(f"**Year:** {metadata.get('year', 'N/A')}")
            st.write(f"**Source:** {metadata.get('source', 'N/A')}")

        if metadata.get("abstract"):
            st.write("**Abstract:**")
            st.write(metadata["abstract"])

    # Structured Summary
    with st.expander("📝 Structured Summary", expanded=True):
        summary_sections = [
            ("Objectives", summary.get("objectives", [])),
            ("Methodology", summary.get("methodology", [])),
            ("Key Findings", summary.get("key_findings", [])),
            ("Results", summary.get("results", [])),
            ("Conclusions", summary.get("conclusions", [])),
            ("Limitations", summary.get("limitations", [])),
            ("Future Work", summary.get("future_work", [])),
        ]

        for section_name, items in summary_sections:
            if items:
                st.markdown(f"**{section_name}:**")
                for item in items:
                    st.markdown(f"- {item}")

    # Extracted Entities
    with st.expander("🧬 Extracted Entities", expanded=True):
        entity_types = [
            ("Genes", "genes", "symbol"),
            ("Proteins", "proteins", "name"),
            ("Diseases", "diseases", "name"),
            ("Drugs/Compounds", "drugs", "name"),
            ("Pathways", "pathways", "name"),
            ("Mutations", "mutations", "variant"),
            ("Biomarkers", "biomarkers", "name"),
        ]

        for label, key, name_key in entity_types:
            items = entities.get(key, [])
            if items:
                with st.expander(f"{label} ({len(items)})"):
                    df = pd.DataFrame([{name_key: e.get(name_key, ""), "Context": e.get("source_text", "")[:100]} for e in items])
                    st.dataframe(df, use_container_width=True, hide_index=True)

    # Drug-Target Relationships
    if dt_rels:
        with st.expander("💊 Drug-Target Relationships", expanded=True):
            df = pd.DataFrame([{
                "Drug": r.get("drug_name", ""),
                "Target": r.get("target_name", ""),
                "Relationship": r.get("relationship_type", ""),
                "Evidence Type": r.get("evidence_type", ""),
                "Confidence": r.get("confidence", ""),
                "Context": r.get("source_text", "")[:150],
            } for r in dt_rels])
            st.dataframe(df, use_container_width=True, hide_index=True)


def _render_entity_extraction_tab() -> None:
    """Entity extraction overview across all analyzed papers."""
    st.subheader("Cross-Paper Entity Extraction")

    if not st.session_state.ra_analyzed_papers:
        st.info("Analyze papers first to see entity extraction results.")
        return

    # Aggregate entities
    entity_counts = {}
    entity_papers = {}

    for paper in st.session_state.ra_analyzed_papers:
        entities = paper.get("entities", {})
        meta = paper.get("metadata", {})
        pmid = meta.get("pmid", "N/A")

        for entity_type in ["genes", "proteins", "diseases", "drugs", "pathways", "mutations", "biomarkers"]:
            for entity in entities.get(entity_type, []):
                name = entity.get("symbol") or entity.get("name") or entity.get("variant", "")
                if not name:
                    continue
                key = f"{entity_type}:{name}"
                entity_counts[key] = entity_counts.get(key, 0) + 1
                if key not in entity_papers:
                    entity_papers[key] = []
                entity_papers[key].append(pmid)

    # Display by type
    entity_types = ["genes", "proteins", "diseases", "drugs", "pathways", "mutations", "biomarkers"]

    for etype in entity_types:
        st.markdown(f"### {etype.capitalize()}")
        type_entities = {k: v for k, v in entity_counts.items() if k.startswith(f"{etype}:")}

        if type_entities:
            df = pd.DataFrame([
                {
                    "Entity": k.split(":", 1)[1],
                    "Papers": v,
                    "PMIDs": ", ".join(map(str, entity_papers.get(k, []))),
                }
                for k, v in sorted(type_entities.items(), key=lambda x: -x[1])
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No entities of this type found.")


def _render_drug_intelligence_tab() -> None:
    """Drug discovery intelligence from paper analysis."""
    st.subheader("Drug Discovery Intelligence")

    if not st.session_state.ra_analyzed_papers:
        st.info("Analyze papers first to generate drug discovery intelligence.")
        return

    if st.button("🔬 Generate Drug Intelligence Report", type="primary", key="ra_drug_intel_btn"):
        with st.spinner("Generating drug discovery intelligence..."):
            try:
                report = generate_drug_discovery_report(st.session_state.ra_analyzed_papers)
                st.session_state.ra_drug_intelligence = report
                st.success("Drug intelligence report generated!")
            except Exception as e:
                logger.error("Drug intelligence failed: %s", e)
                st.error(f"Drug intelligence generation failed: {e}")

    if st.session_state.ra_drug_intelligence:
        report = st.session_state.ra_drug_intelligence
        summary = report.get("summary", {})

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Drug-Target Relationships", summary.get("total_relationships", 0))
        with col2:
            st.metric("Validated Interactions", summary.get("validated_interactions", 0))
        with col3:
            st.metric("Predicted Interactions", summary.get("predicted_interactions", 0))
        with col4:
            st.metric("Repurposing Candidates", summary.get("repurposing_candidates", 0))

        # Drug-Target Intelligence
        with st.expander("💊 Drug-Target Intelligence", expanded=True):
            dt_intel = report.get("drug_target_intelligence", [])
            if dt_intel:
                df = pd.DataFrame([{
                    "Drug": r.get("drug_name", ""),
                    "Target": r.get("target_name", ""),
                    "Relationship": r.get("relationship_type", ""),
                    "Evidence": r.get("evidence_type", ""),
                    "Validation": r.get("validation_status", ""),
                    "Prediction Score": r.get("prediction_score", ""),
                    "Confidence": r.get("confidence", ""),
                    "ChEMBL ID": r.get("chembl_data", {}).get("chembl_id", "") if r.get("chembl_data") else "",
                    "PubChem CID": r.get("pubchem_data", {}).get("cid", "") if r.get("pubchem_data") else "",
                } for r in dt_intel])
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Disease-Target Intelligence
        with st.expander("🎯 Disease-Target Associations", expanded=True):
            disease_intel = report.get("disease_target_intelligence", [])
            if disease_intel:
                df = pd.DataFrame([{
                    "Disease": r.get("disease_name", ""),
                    "Target": r.get("target_name", ""),
                    "Association": r.get("association_type", ""),
                    "Evidence Strength": r.get("evidence_strength", ""),
                    "OpenTargets Score": r.get("opentargets_score", ""),
                    "Known Drugs": len(r.get("known_drugs", [])),
                    "Repurposing Ops": len(r.get("repurposing_opportunities", [])),
                } for r in disease_intel])
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Therapeutic Compounds
        with st.expander("🧪 Therapeutic Compounds", expanded=True):
            compounds = report.get("therapeutic_compounds", [])
            if compounds:
                df = pd.DataFrame([{
                    "Compound": r.get("compound_name", ""),
                    "Target Diseases": ", ".join(r.get("target_diseases", [])[:3]),
                    "Target Proteins": ", ".join(r.get("target_proteins", [])[:3]),
                    "Mechanism": r.get("mechanism_of_action", ""),
                    "Evidence Count": len(r.get("experimental_evidence", [])),
                    "Clinical Trials": len(r.get("clinical_trials", [])),
                    "Repurposing Potential": r.get("repurposing_potential", ""),
                    "ChEMBL Phase": r.get("chembl_data", {}).get("max_phase", "") if r.get("chembl_data") else "",
                } for r in compounds])
                st.dataframe(df, use_container_width=True, hide_index=True)


def _render_gap_detection_tab() -> None:
    """Research gap detection."""
    st.subheader("Research Gap Detection")

    if not st.session_state.ra_analyzed_papers:
        st.info("Analyze papers first to detect research gaps.")
        return

    if st.session_state.ra_gap_analysis:
        gap_analysis = st.session_state.ra_gap_analysis
    else:
        if st.button("🔬 Detect Research Gaps", type="primary", key="ra_gap_btn"):
            with st.spinner("Analyzing research gaps..."):
                try:
                    gap_analysis = identify_gaps_from_papers(st.session_state.ra_analyzed_papers)
                    st.session_state.ra_gap_analysis = gap_analysis
                    st.success("Gap analysis complete!")
                except Exception as e:
                    logger.error("Gap analysis failed: %s", e)
                    st.error(f"Gap analysis failed: {e}")
        return

    if gap_analysis:
        # Summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Gaps", len(gap_analysis.gaps))
        with col2:
            st.metric("Conflicting Findings", len(gap_analysis.conflicting_findings))
        with col3:
            st.metric("Papers Analyzed", gap_analysis.analysis_metadata.get("total_papers_analyzed", 0))

        # Gap type distribution
        gap_types = {}
        for gap in gap_analysis.gaps:
            gap_types[gap.gap_type] = gap_types.get(gap.gap_type, 0) + 1

        if gap_types:
            st.bar_chart(pd.DataFrame(list(gap_types.items()), columns=["Gap Type", "Count"]).set_index("Gap Type"))

        # Gaps table
        with st.expander("📋 Identified Gaps", expanded=True):
            df = pd.DataFrame([{
                "Type": g.gap_type.replace("_", " ").title(),
                "Description": g.description,
                "Entities": ", ".join(g.entities_involved),
                "Confidence": g.confidence,
                "Evidence": g.evidence_summary,
                "Suggested Experiments": "; ".join(g.suggested_experiments[:2]),
            } for g in gap_analysis.gaps])
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Conflicting findings
        if gap_analysis.conflicting_findings:
            with st.expander("⚔️ Conflicting Findings", expanded=True):
                for conflict in gap_analysis.conflicting_findings:
                    st.warning(f"**{conflict['topic']}**: {conflict['description']}")

        # Entity coverage
        with st.expander("📊 Entity Coverage", expanded=True):
            for entity_type, counts in gap_analysis.entity_coverage.items():
                if counts:
                    st.markdown(f"**{entity_type.capitalize()}**")
                    df = pd.DataFrame(list(counts.items()), columns=["Entity", "Paper Count"])
                    st.dataframe(df, use_container_width=True, hide_index=True)

        # Gap report
        st.markdown("### Gap Analysis Report")
        report_text = generate_gap_report(gap_analysis, format="markdown")
        st.markdown(report_text)


def _render_comparison_tab() -> None:
    """Multi-paper comparison."""
    st.subheader("Multi-Paper Comparison")

    if not st.session_state.ra_comparison:
        if len(st.session_state.ra_selected_papers) >= 2:
            if st.button("⚖️ Run Comparison", type="primary", key="ra_run_comparison"):
                _compare_selected_papers()
        else:
            st.info("Select at least 2 papers from Paper Search tab to compare.")
        return

    comparison = st.session_state.ra_comparison

    # Evidence summary
    st.markdown(comparison.evidence_summary)

    # Comparison table
    if comparison.comparison_table is not None:
        st.markdown("### Detailed Comparison")
        st.dataframe(comparison.comparison_table, use_container_width=True, hide_index=True)

    # Similarities
    with st.expander("✅ Similarities", expanded=True):
        for key, items in comparison.similarities.items():
            if items:
                st.markdown(f"**{key.replace('_', ' ').title()}**")
                for item in items:
                    if isinstance(item, dict):
                        st.markdown(f"- {item.get('entity', item.get('keyword', ''))}: {item.get('paper_count', 0)} papers")
                    else:
                        st.markdown(f"- {item}")

    # Differences
    with st.expander("🔄 Differences", expanded=True):
        for key, paper_items in comparison.differences.items():
            if paper_items:
                st.markdown(f"**{key.replace('_', ' ').title()}**")
                for paper, items in paper_items.items():
                    if items:
                        st.markdown(f"- {paper}: {', '.join(items[:5])}")


def _render_research_assistant_tab() -> None:
    """AI Research Assistant."""
    st.subheader("🤖 AI Research Assistant")

    if not st.session_state.ra_analyzed_papers:
        st.info("Analyze papers first to use the research assistant.")
        return

    if st.session_state.ra_assistant is None:
        st.session_state.ra_assistant = create_research_assistant(st.session_state.ra_analyzed_papers)

    assistant = st.session_state.ra_assistant

    # Example questions
    st.markdown("**Example questions:**")
    example_questions = [
        "What are the main findings?",
        "Which genes are involved?",
        "What proteins are associated?",
        "Which drugs were investigated?",
        "What are the limitations?",
        "What research gaps remain?",
        "What future experiments are suggested?",
        "What methodology was used?",
    ]

    cols = st.columns(4)
    for i, q in enumerate(example_questions):
        with cols[i % 4]:
            if st.button(q, key=f"ra_example_{i}", use_container_width=True):
                response = assistant.ask(q)
                _display_assistant_response(response)

    # Custom question
    question = st.text_input("Ask a question about the papers:", key="ra_question_input")

    if st.button("Ask", type="primary", key="ra_ask_btn") and question:
        response = assistant.ask(question)
        _display_assistant_response(response)


def _display_assistant_response(response: Any) -> None:
    """Display assistant response."""
    st.markdown("### Answer")
    st.markdown(response.answer)

    if response.citations:
        with st.expander("📚 Citations"):
            for cite in response.citations:
                pmid = cite.get("pmid")
                doi = cite.get("doi")
                title = cite.get("title", "")
                st.markdown(f"- PMID: {pmid or 'N/A'} | DOI: {doi or 'N/A'} | {title}")

    if response.excerpts:
        with st.expander("📝 Supporting Excerpts"):
            for excerpt in response.excerpts:
                st.caption(excerpt[:200])

    st.caption(f"Confidence: {response.confidence} | Evidence Available: {response.evidence_available}")


def _render_report_generator_tab() -> None:
    """Report generation."""
    st.subheader("📊 Scientific Report Generator")

    if not st.session_state.ra_analyzed_papers:
        st.info("Analyze papers first to generate reports.")
        return

    col1, col2 = st.columns(2)

    with col1:
        report_type = st.selectbox(
            "Report type",
            ["Full Analysis Report", "Executive Summary", "Gap Analysis Report", "Comparison Report", "Drug Intelligence Report"],
            key="ra_report_type",
        )

        format = st.selectbox(
            "Format",
            ["PDF", "CSV", "JSON", "Markdown"],
            key="ra_report_format",
        )

    with col2:
        include_full_text = st.checkbox("Include full text (JSON only)", value=False, key="ra_include_full")

    if st.button("📄 Generate Report", type="primary", use_container_width=True, key="ra_gen_report"):
        _generate_report(report_type, format.lower(), include_full_text)


def _generate_report(report_type: str, format: str, include_full_text: bool) -> None:
    """Generate and offer download for report."""
    try:
        with st.spinner("Generating report..."):
            temp_dir = Path(tempfile.gettempdir()) / "geneai_reports"
            temp_dir.mkdir(exist_ok=True)

            timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")

            if report_type == "Full Analysis Report":
                if format == "pdf":
                    path = temp_dir / f"full_analysis_{timestamp}.pdf"
                    generate_pdf_report(
                        st.session_state.ra_analyzed_papers,
                        st.session_state.ra_gap_analysis,
                        st.session_state.ra_comparison,
                        path,
                    )
                elif format == "csv":
                    path = temp_dir / f"full_analysis_{timestamp}.csv"
                    generate_analysis_report_csv(st.session_state.ra_analyzed_papers, path)
                elif format == "json":
                    path = temp_dir / f"full_analysis_{timestamp}.json"
                    generate_analysis_report_json(st.session_state.ra_analyzed_papers, path, include_full_text)
                elif format == "markdown":
                    path = temp_dir / f"full_analysis_{timestamp}.md"
                    summary = generate_executive_summary(st.session_state.ra_analyzed_papers, st.session_state.ra_gap_analysis)
                    with open(path, "w") as f:
                        f.write(summary)

            elif report_type == "Executive Summary":
                path = temp_dir / f"executive_summary_{timestamp}.{format}"
                summary = generate_executive_summary(st.session_state.ra_analyzed_papers, st.session_state.ra_gap_analysis)
                if format == "markdown":
                    with open(path, "w") as f:
                        f.write(summary)
                elif format == "json":
                    import json
                    with open(path, "w") as f:
                        json.dump({"summary": summary}, f, indent=2)
                elif format == "csv":
                    import csv
                    with open(path, "w") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Section", "Content"])
                        for line in summary.split("\n"):
                            writer.writerow([line.split(":")[0] if ":" in line else "Content", line])

            elif report_type == "Gap Analysis Report":
                if format == "pdf" and st.session_state.ra_gap_analysis:
                    path = temp_dir / f"gap_analysis_{timestamp}.pdf"
                    generate_pdf_report(
                        st.session_state.ra_analyzed_papers,
                        st.session_state.ra_gap_analysis,
                        None,
                        path,
                    )
                elif format == "csv" and st.session_state.ra_gap_analysis:
                    path = temp_dir / f"gap_analysis_{timestamp}.csv"
                    generate_gap_report_csv(st.session_state.ra_gap_analysis, path)
                elif format == "markdown" and st.session_state.ra_gap_analysis:
                    path = temp_dir / f"gap_analysis_{timestamp}.md"
                    report_text = generate_gap_report(st.session_state.ra_gap_analysis, format="markdown")
                    with open(path, "w") as f:
                        f.write(report_text)

            elif report_type == "Comparison Report" and st.session_state.ra_comparison:
                if format == "csv":
                    path = temp_dir / f"comparison_{timestamp}.csv"
                    generate_comparison_report_csv(st.session_state.ra_comparison, path)
                elif format == "json":
                    path = temp_dir / f"comparison_{timestamp}.json"
                    export_comparison_json(st.session_state.ra_comparison, path)

            elif report_type == "Drug Intelligence Report" and st.session_state.ra_drug_intelligence:
                path = temp_dir / f"drug_intelligence_{timestamp}.json"
                import json
                with open(path, "w") as f:
                    json.dump(st.session_state.ra_drug_intelligence, f, indent=2, default=str)

            else:
                st.warning("Please run the required analysis first (gap detection, comparison, or drug intelligence)")
                return

            # Offer download
            with open(path, "rb") as f:
                st.download_button(
                    f"⬇️ Download {report_type} ({format.upper()})",
                    f.read(),
                    file_name=path.name,
                    mime="application/pdf" if format == "pdf" else (
                        "text/csv" if format == "csv" else (
                            "application/json" if format == "json" else "text/markdown"
                        )
                    ),
                    use_container_width=True,
                )
            st.success(f"Report generated: {path.name}")

    except Exception as e:
        logger.error("Report generation failed: %s", e)
        st.error(f"Report generation failed: {e}")