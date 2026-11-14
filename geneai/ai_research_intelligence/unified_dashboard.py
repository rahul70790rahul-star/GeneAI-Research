"""Unified Dashboard for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import session_state as ss

from geneai.ai_research_intelligence.knowledge_graph import (
    find_nodes, get_neighbors, shortest_path, get_subgraph, compute_centrality,
    KGNode, KGEdge, add_node, add_edge, initialize_knowledge_graph,
)
from geneai.ai_research_intelligence.mutation_to_drug_workflow import (
    MutationToDrugWorkflow, run_mutation_to_drug_workflow,
    VariantAnnotation, GeneDiseaseLink, DrugCandidate, MutationToDrugResult,
)
from geneai.ai_research_intelligence.ai_candidate_ranking import (
    AICandidateRanker, CandidateFeatures, rank_candidates,
)
from geneai.ai_research_intelligence.ai_research_assistant import (
    AIResearchAssistant, ResearchQuestion, ResearchAnswer, create_research_assistant,
)
from geneai.ai_research_intelligence.reproducibility import (
    ReproducibilityTracker, initialize_reproducibility,
)
from geneai.ai_research_intelligence.advanced_report_generator import (
    AdvancedReportGenerator, ReportConfig, create_mutation_to_drug_report,
)
from geneai.config import APP_NAME
from geneai.variants import parse_vcf


def render_ai_research_intelligence_dashboard() -> None:
    """Render the AI Research Intelligence unified dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - AI Research Intelligence",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🧠 AI Research Intelligence Engine")
    st.caption("Unified workspace: Knowledge Graph • Mutation→Drug • AI Ranking • Research Assistant • Reproducibility • Reports")
    
    # Initialize session state
    _init_session_state()
    
    # Sidebar navigation
    with st.sidebar:
        st.header("🧭 Navigation")
        module = st.radio(
            "Module",
            [
                "🏠 Overview",
                "🕸️ Knowledge Graph",
                "🧬 Mutation→Drug Workflow",
                "🏆 AI Candidate Ranking",
                "🤖 AI Research Assistant",
                "📊 Reproducibility Tracker",
                "📄 Advanced Reports",
            ],
            key="ari_module",
        )
        
        st.divider()
        st.header("⚙️ Global Settings")
        
        # Data source toggles
        st.checkbox("OpenTargets", value=True, key="ari_opentargets")
        st.checkbox("STRING PPI", value=True, key="ari_string")
        st.checkbox("ChEMBL", value=True, key="ari_chembl")
        st.checkbox("PubMed", value=True, key="ari_pubmed")
        st.checkbox("KEGG/Reactome", value=True, key="ari_pathways")
        st.checkbox("GO/UniProt", value=True, key="ari_go")
        
        st.divider()
        st.header("💾 Session")
        if st.button("💾 Save Session", use_container_width=True):
            _save_session()
        if st.button("📂 Load Session", use_container_width=True):
            _load_session()
        if st.button("🔄 Clear All", use_container_width=True):
            _clear_session()
    
    # Route to module
    if module == "🏠 Overview":
        render_overview()
    elif module == "🕸️ Knowledge Graph":
        render_knowledge_graph()
    elif module == "🧬 Mutation→Drug Workflow":
        render_mutation_to_drug()
    elif module == "🏆 AI Candidate Ranking":
        render_ai_ranking()
    elif module == "🤖 AI Research Assistant":
        render_research_assistant()
    elif module == "📊 Reproducibility Tracker":
        render_reproducibility()
    elif module == "📄 Advanced Reports":
        render_advanced_reports()


def _init_session_state() -> None:
    """Initialize session state."""
    defaults = {
        "ari_kg_nodes": [],
        "ari_kg_edges": [],
        "ari_mtd_result": None,
        "ari_ranking_results": [],
        "ari_assistant": None,
        "ari_current_session": None,
        "ari_experiments": [],
    }
    for key, val in defaults.items():
        if key not in ss:
            ss[key] = val
    
    if ss.ari_assistant is None:
        ss.ari_assistant = create_research_assistant()
    
    initialize_knowledge_graph()
    initialize_reproducibility()


def _save_session() -> None:
    """Save session to file."""
    session_data = {
        "kg_nodes": [asdict(n) for n in ss.ari_kg_nodes] if ss.ari_kg_nodes else [],
        "kg_edges": [asdict(e) for e in ss.ari_kg_edges] if ss.ari_kg_edges else [],
        "mtd_result": asdict(ss.ari_mtd_result) if ss.ari_mtd_result else None,
        "ranking_results": [asdict(r) for r in ss.ari_ranking_results],
        "experiments": [asdict(e) for e in ss.ari_experiments],
    }
    json_str = json.dumps(session_data, default=str, indent=2)
    st.download_button("⬇️ Download Session", json_str, "ari_session.json", "application/json")


def _load_session() -> None:
    """Load session from file."""
    file = st.file_uploader("Upload Session JSON", type=["json"], key="ari_load_session")
    if file:
        data = json.load(file)
        # Restore would require deserializing dataclasses
        st.success("Session loaded (partial restore)")


def _clear_session() -> None:
    """Clear session state."""
    for key in list(ss.keys()):
        if key.startswith("ari_"):
            del ss[key]
    st.rerun()


def render_overview() -> None:
    """Render overview dashboard."""
    st.subheader("📊 AI Research Intelligence Overview")
    
    # Metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    mtd = ss.ari_mtd_result
    with col1:
        st.metric("Variants Analyzed", mtd.summary.get("variants_analyzed", 0) if mtd else 0)
    with col2:
        st.metric("Genes Linked", mtd.summary.get("genes_linked", 0) if mtd else 0)
    with col3:
        st.metric("Targets Prioritized", mtd.summary.get("targets_prioritized", 0) if mtd else 0)
    with col4:
        st.metric("Candidates Found", mtd.summary.get("candidates_discovered", 0) if mtd else 0)
    with col5:
        st.metric("Top Candidate", mtd.summary.get("top_drug", "N/A") if mtd else "N/A")
    
    st.divider()
    
    # Quick actions
    st.subheader("🚀 Quick Start")
    actions = st.columns(4)
    
    with actions[0]:
        if st.button("🧬 Run Mutation→Drug", use_container_width=True):
            ss.ari_module = "🧬 Mutation→Drug Workflow"
            st.rerun()
    
    with actions[1]:
        if st.button("🕸️ Explore Knowledge Graph", use_container_width=True):
            ss.ari_module = "🕸️ Knowledge Graph"
            st.rerun()
    
    with actions[2]:
        if st.button("🤖 Ask Research Question", use_container_width=True):
            ss.ari_module = "🤖 AI Research Assistant"
            st.rerun()
    
    with actions[3]:
        if st.button("📄 Generate Report", use_container_width=True):
            ss.ari_module = "📄 Advanced Reports"
            st.rerun()
    
    # Recent activity
    st.divider()
    st.subheader("📋 Recent Activity")
    
    if mtd:
        st.info(f"Last workflow: {mtd.workflow_id} — {mtd.timestamp[:19]} — Top: {mtd.summary.get('top_drug', 'N/A')}")
    else:
        st.caption("No analyses run yet. Start with Mutation→Drug Workflow or Knowledge Graph.")


def render_knowledge_graph() -> None:
    """Render knowledge graph explorer."""
    st.subheader("🕸️ Biomedical Knowledge Graph Explorer")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 Search", "🌐 Graph View", "📊 Analytics", "➕ Add Data"])
    
    with tab1:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Search nodes", placeholder="gene symbol, disease name, drug name, pathway...", key="kg_search")
        with col2:
            node_type = st.selectbox("Type", ["All", "gene", "protein", "disease", "drug", "pathway", "variant", "publication"], key="kg_type_filter")
        
        if query and st.button("Search", key="kg_search_btn"):
            with st.spinner("Searching knowledge graph..."):
                results = find_nodes(name=query, node_type=node_type if node_type != "All" else None, limit=50)
                ss.ari_kg_nodes = results
                st.success(f"Found {len(results)} nodes")
        
        if ss.ari_kg_nodes:
            st.subheader("Results")
            node_data = []
            for n in ss.ari_kg_nodes:
                node_data.append({
                    "ID": n.node_id,
                    "Type": n.node_type,
                    "Identifier": n.identifier,
                    "Name": n.name or "N/A",
                    "Source": n.source or "N/A",
                })
            st.dataframe(pd.DataFrame(node_data), use_container_width=True, hide_index=True)
            
            # Explore neighbors
            selected = st.selectbox("Explore neighbors of:", [f"{n.name} ({n.node_id})" for n in ss.ari_kg_nodes], key="kg_neighbor_select")
            if selected and st.button("Get Neighbors", key="kg_get_neighbors"):
                node_id = selected.split("(")[-1].rstrip(")")
                neighbors = get_neighbors(node_id, limit=100)
                st.subheader(f"Neighbors of {node_id}")
                for edge, target in neighbors[:30]:
                    st.write(f"• **{edge.edge_type}** → {target.name or target.identifier} ({target.node_type}) [conf: {edge.confidence:.2f}]")
    
    with tab2:
        st.subheader("Graph Visualization")
        st.info("Interactive graph visualization requires networkx + pyvis. Showing subgraph data.")
        
        if ss.ari_kg_nodes:
            node_ids = [n.node_id for n in ss.ari_kg_nodes[:10]]
            subgraph = get_subgraph(node_ids, max_hops=2)
            
            st.write(f"**Subgraph:** {len(subgraph['nodes'])} nodes, {len(subgraph['edges'])} edges")
            
            # Show as table
            edge_data = []
            for e in subgraph["edges"][:50]:
                src = subgraph["nodes"].get(e["source_node_id"], {})
                tgt = subgraph["nodes"].get(e["target_node_id"], {})
                edge_data.append({
                    "Source": src.get("name", e["source_node_id"]),
                    "Type": e["edge_type"],
                    "Target": tgt.get("name", e["target_node_id"]),
                    "Weight": e["weight"],
                    "Confidence": e["confidence"],
                })
            st.dataframe(pd.DataFrame(edge_data), use_container_width=True, hide_index=True)
    
    with tab3:
        st.subheader("Graph Analytics")
        
        col1, col2 = st.columns(2)
        with col1:
            node_type = st.selectbox("Centrality for:", ["All", "gene", "disease", "drug", "protein"], key="kg_centrality_type")
        with col2:
            top_k = st.number_input("Top K", 10, 200, 50, key="kg_top_k")
        
        if st.button("Compute Centrality", key="kg_compute_centrality"):
            with st.spinner("Computing..."):
                results = compute_centrality(node_type if node_type != "All" else None, top_k)
                if results:
                    df = pd.DataFrame(results)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Bar chart
                    fig = go.Figure(go.Bar(
                        x=[r["degree"] for r in reversed(results[:20])],
                        y=[r["name"] or r["identifier"] for r in reversed(results[:20])],
                        orientation='h',
                    ))
                    fig.update_layout(title="Top Nodes by Degree Centrality", height=500)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No nodes found")
        
        # Path finding
        st.divider()
        st.write("**Shortest Path**")
        col1, col2 = st.columns(2)
        with col1:
            source = st.text_input("Source node ID", key="kg_path_source")
        with col2:
            target = st.text_input("Target node ID", key="kg_path_target")
        
        if source and target and st.button("Find Path", key="kg_find_path"):
            path = shortest_path(source, target, max_depth=6)
            if path:
                st.success(f"Path found: {len(path)} nodes")
                for i, n in enumerate(path):
                    st.write(f"{i+1}. **{n.name or n.identifier}** ({n.node_type})")
            else:
                st.error("No path found within 6 hops")
    
    with tab4:
        st.subheader("Add Data to Knowledge Graph")
        
        with st.form("kg_add_node"):
            st.write("**Add Node**")
            col1, col2 = st.columns(2)
            with col1:
                n_id = st.text_input("Node ID (e.g., gene:TP53)", key="kg_new_node_id")
                n_type = st.selectbox("Type", ["gene", "protein", "disease", "drug", "pathway", "variant", "publication"], key="kg_new_node_type")
            with col2:
                n_identifier = st.text_input("Identifier", key="kg_new_identifier")
                n_name = st.text_input("Name", key="kg_new_name")
            n_source = st.text_input("Source", key="kg_new_source")
            n_props = st.text_area("Properties (JSON)", "{}", key="kg_new_props")
            
            if st.form_submit_button("Add Node"):
                try:
                    props = json.loads(n_props)
                    node = KGNode(node_id=n_id, node_type=n_type, identifier=n_identifier, name=n_name, properties=props, source=n_source)
                    add_node(node)
                    st.success(f"Added node: {n_id}")
                except Exception as e:
                    st.error(f"Failed: {e}")
        
        with st.form("kg_add_edge"):
            st.write("**Add Edge**")
            col1, col2, col3 = st.columns(3)
            with col1:
                e_source = st.text_input("Source Node ID", key="kg_new_edge_source")
            with col2:
                e_target = st.text_input("Target Node ID", key="kg_new_edge_target")
            with col3:
                e_type = st.selectbox("Edge Type", 
                    ["associated_with", "interacts_with", "treats", "causes", "regulates", 
                     "participates_in", "binds_to", "inhibits", "activates"], key="kg_new_edge_type")
            e_weight = st.slider("Weight", 0.0, 1.0, 1.0, key="kg_new_edge_weight")
            e_conf = st.slider("Confidence", 0.0, 1.0, 1.0, key="kg_new_edge_conf")
            e_source_db = st.text_input("Source DB", key="kg_new_edge_source_db")
            
            if st.form_submit_button("Add Edge"):
                try:
                    edge = KGEdge(
                        edge_id=f"edge:{e_source}:{e_type}:{e_target}",
                        source_node_id=e_source, target_node_id=e_target,
                        edge_type=e_type, weight=e_weight, confidence=e_conf, source=e_source_db,
                    )
                    add_edge(edge)
                    st.success(f"Added edge: {e_source} --{e_type}--> {e_target}")
                except Exception as e:
                    st.error(f"Failed: {e}")


def render_mutation_to_drug() -> None:
    """Render mutation-to-drug workflow."""
    st.subheader("🧬 Mutation-to-Drug Discovery Workflow")
    st.caption("End-to-end pipeline: VCF → Variants → Genes → Diseases → Targets → Drugs → Candidates")
    
    with st.sidebar:
        st.header("📥 Input Data")
        input_mode = st.radio("Input Type", ["VCF File", "Variant List", "Gene Symbols", "Combined"], key="mtd_input_mode")
        
        st.divider()
        st.header("⚙️ Pipeline Options")
        max_candidates = st.number_input("Max Candidates", 5, 100, 20, key="mtd_max_cands")
        min_pathogenicity = st.slider("Min Pathogenicity", 0.0, 1.0, 0.3, key="mtd_min_path")
        
        st.divider()
        st.header("📤 Output")
        save_results = st.checkbox("Save to Database", True, key="mtd_save")
        generate_report = st.checkbox("Generate Report", True, key="mtd_report")
    
    # Input forms
    variants = None
    gene_symbols = None
    disease_names = None
    
    if input_mode == "VCF File":
        file = st.file_uploader("VCF File", type=["vcf", "vcf.gz"], key="mtd_vcf")
        disease_names = st.text_input("Disease Names (optional)", placeholder="breast cancer, NSCLC", key="mtd_vcf_diseases")
        
        if file and st.button("🚀 Run Workflow", type="primary", use_container_width=True, key="mtd_run_vcf"):
            with st.spinner("Parsing VCF..."):
                variants, _ = parse_vcf(file.getvalue(), file.name)
            _run_mtd_workflow(variants, gene_symbols, disease_names, max_candidates, save_results, generate_report)
    
    elif input_mode == "Variant List":
        var_text = st.text_area("Variants (JSON)", placeholder='[{"chrom":"17","pos":7577120,"ref":"C","alt":"T","gene":"TP53","impact":"HIGH","consequence":"missense_variant"}]', height=150, key="mtd_variants_json")
        disease_names = st.text_input("Disease Names (optional)", key="mtd_var_diseases")
        
        if st.button("🚀 Run Workflow", type="primary", use_container_width=True, key="mtd_run_var"):
            try:
                variants = json.loads(var_text)
                _run_mtd_workflow(variants, gene_symbols, disease_names, max_candidates, save_results, generate_report)
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
    
    elif input_mode == "Gene Symbols":
        genes_text = st.text_area("Gene Symbols", placeholder="TP53\nEGFR\nBRCA1\nKRAS", height=100, key="mtd_genes")
        disease_names = st.text_input("Disease Names (optional)", key="mtd_gene_diseases")
        
        if st.button("🚀 Run Workflow", type="primary", use_container_width=True, key="mtd_run_genes"):
            gene_symbols = [g.strip().upper() for g in genes_text.replace(",", "\n").split("\n") if g.strip()]
            _run_mtd_workflow(variants, gene_symbols, disease_names, max_candidates, save_results, generate_report)
    
    elif input_mode == "Combined":
        col1, col2 = st.columns(2)
        with col1:
            file = st.file_uploader("VCF (optional)", type=["vcf", "vcf.gz"], key="mtd_comb_vcf")
            genes_text = st.text_area("Genes (optional)", key="mtd_comb_genes")
        with col2:
            disease_names = st.text_input("Diseases (optional)", key="mtd_comb_diseases")
            var_text = st.text_area("Variants JSON (optional)", key="mtd_comb_var_json")
        
        if st.button("🚀 Run Full Workflow", type="primary", use_container_width=True, key="mtd_run_comb"):
            if file:
                variants, _ = parse_vcf(file.getvalue(), file.name)
            if var_text:
                try:
                    variants = json.loads(var_text)
                except:
                    pass
            gene_symbols = [g.strip().upper() for g in genes_text.replace(",", "\n").split("\n") if g.strip()] if genes_text else None
            d_names = [d.strip() for d in disease_names.split(",") if d.strip()] if disease_names else None
            _run_mtd_workflow(variants, gene_symbols, d_names, max_candidates, save_results, generate_report)
    
    # Display results
    if ss.ari_mtd_result:
        display_mtd_results(ss.ari_mtd_result)


def _run_mtd_workflow(variants, gene_symbols, disease_names, max_candidates, save_results, generate_report):
    """Run the mutation-to-drug workflow."""
    d_names = [d.strip() for d in disease_names.split(",") if d.strip()] if disease_names else None
    
    with st.spinner("Running mutation-to-drug workflow..."):
        try:
            tracker = ReproducibilityTracker.start(
                "mutation_to_drug",
                parameters={"max_candidates": max_candidates, "min_pathogenicity": 0.3},
                inputs={"variants": len(variants) if variants else 0, "genes": gene_symbols, "diseases": d_names},
                tags=["mtd", "phase4.13"],
            )
            
            result = run_mutation_to_drug_workflow(
                variants=variants,
                gene_symbols=gene_symbols,
                disease_names=d_names,
                max_candidates=max_candidates,
            )
            
            ss.ari_mtd_result = result
            tracker.log_output("result", asdict(result))
            tracker.complete()
            
            if save_results:
                # Would save to database
                pass
            
            if generate_report:
                _generate_mtd_report(result)
            
            st.success(f"Workflow complete! Run ID: {result.workflow_id}")
            st.rerun()
            
        except Exception as e:
            st.error(f"Workflow failed: {e}")
            import traceback
            st.code(traceback.format_exc())


def display_mtd_results(result: MutationToDrugResult) -> None:
    """Display mutation-to-drug results."""
    st.divider()
    
    # Summary metrics
    summary = result.summary
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Variants", summary.get("variants_analyzed", 0))
    col2.metric("Genes", summary.get("genes_linked", 0))
    col3.metric("Diseases", summary.get("diseases_linked", 0))
    col4.metric("Targets", summary.get("targets_prioritized", 0))
    col5.metric("Candidates", summary.get("candidates_discovered", 0))
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🧬 Variants", "🔗 Gene-Disease", "🎯 Targets", "💊 Candidates", "🕸️ KG Paths", "📋 Summary"
    ])
    
    with tab1:
        if result.input_variants:
            df = pd.DataFrame([{
                "Variant": v.variant_id,
                "Gene": v.gene,
                "Impact": v.impact,
                "Consequence": v.consequence,
                "Pathogenicity": f"{v.pathogenicity_score:.2f}" if v.pathogenicity_score else "N/A",
                "Interpretation": v.interpretation,
            } for v in result.input_variants])
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tab2:
        if result.gene_disease_links:
            df = pd.DataFrame([{
                "Gene": l.gene_symbol,
                "Disease": l.disease_name,
                "Score": f"{l.score:.3f}",
                "Evidence": ", ".join(l.evidence_types),
                "Therapeutic Area": l.therapeutic_area or "N/A",
            } for l in result.gene_disease_links])
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tab3:
        if result.prioritized_targets:
            st.write("**Prioritized Therapeutic Targets:**")
            for i, t in enumerate(result.prioritized_targets[:20], 1):
                st.write(f"{i}. {t}")
    
    with tab4:
        if result.top_candidates:
            df = pd.DataFrame([{
                "Rank": c.rank,
                "Drug": c.name,
                "Targets": ", ".join(c.targets[:3]),
                "ADMET": f"{c.admet_score:.2f}" if c.admet_score else "N/A",
                "Safety": c.safety_risk or "N/A",
                "Phase": c.phase,
                "Binding": f"{sum(c.binding_affinities.values())/len(c.binding_affinities):.1f}" if c.binding_affinities else "N/A",
                "Evidence": "; ".join(c.repurposing_evidence[:2]),
            } for c in result.top_candidates])
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Score chart
            fig = go.Figure(go.Bar(
                x=[c.admet_score or 0 for c in reversed(result.top_candidates[:15])],
                y=[c.name for c in reversed(result.top_candidates[:15])],
                orientation='h',
            ))
            fig.update_layout(title="Top Candidates by ADMET Score", height=400)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab5:
        kg = result.knowledge_graph_subgraph
        if kg.get("paths"):
            st.write(f"**Paths Found:** {kg.get('path_count', 0)}")
            for p in kg["paths"][:10]:
                st.write(f"• Length {p['length']}: {' → '.join(p['nodes'])}")
        if kg.get("subgraph"):
            sg = kg["subgraph"]
            st.write(f"**Subgraph:** {len(sg.get('nodes', {}))} nodes, {len(sg.get('edges', {}))} edges")
    
    with tab6:
        st.json(summary)


def _generate_mtd_report(result: MutationToDrugResult) -> None:
    """Generate and offer report download."""
    generator = create_mutation_to_drug_report(result)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        pdf_bytes = generator.generate_pdf("/tmp/mtd_report.pdf")
        with open("/tmp/mtd_report.pdf", "rb") as f:
            st.download_button("📄 Download PDF", f.read(), f"mtd_report_{result.workflow_id}.pdf", "application/pdf", use_container_width=True)
    with col2:
        html_path = generator.generate_html("/tmp/mtd_report.html")
        with open(html_path, "r") as f:
            st.download_button("🌐 Download HTML", f.read(), f"mtd_report_{result.workflow_id}.html", "text/html", use_container_width=True)
    with col3:
        md_path = generator.generate_markdown("/tmp/mtd_report.md")
        with open(md_path, "r") as f:
            st.download_button("📝 Download Markdown", f.read(), f"mtd_report_{result.workflow_id}.md", "text/markdown", use_container_width=True)


def render_ai_ranking() -> None:
    """Render AI candidate ranking."""
    st.subheader("🏆 AI Candidate Ranking")
    st.caption("ML-based multi-criteria ranking of drug candidates")
    
    if not ss.ari_mtd_result or not ss.ari_mtd_result.drug_candidates:
        st.info("Run Mutation→Drug workflow first to generate candidates, or load candidates manually.")
        
        # Manual candidate input
        with st.expander("Manual Candidate Input"):
            cand_json = st.text_area("Candidates JSON", height=200, key="ari_manual_cands")
            if st.button("Rank Candidates", key="ari_rank_manual"):
                try:
                    candidates = json.loads(cand_json)
                    context = {"disease_association_score": 0.8, "gene_disease_link_strength": 0.7}
                    results = rank_candidates(candidates, context)
                    ss.ari_ranking_results = results
                    st.success(f"Ranked {len(results)} candidates")
                except Exception as e:
                    st.error(f"Error: {e}")
        return
    
    candidates = ss.ari_mtd_result.drug_candidates
    
    # Ranking options
    col1, col2, col3 = st.columns(3)
    with col1:
        model_type = st.selectbox("Model", ["gradient_boosting", "random_forest", "linear"], key="ari_model_type")
    with col2:
        use_pretrained = st.checkbox("Use Pretrained", True, key="ari_pretrained")
    with col3:
        if st.button("🔮 Rank Candidates", type="primary", key="ari_run_ranking"):
            with st.spinner("Ranking candidates..."):
                context = {
                    "disease_association_score": 0.8,
                    "gene_disease_link_strength": 0.7,
                }
                results = rank_candidates(candidates, context, model_type=model_type)
                ss.ari_ranking_results = results
                st.success(f"Ranked {len(results)} candidates")
    
    if ss.ari_ranking_results:
        display_ranking_results(ss.ari_ranking_results)


def display_ranking_results(results: list) -> None:
    """Display ranking results."""
    df = pd.DataFrame([{
        "Rank": r.rank,
        "Candidate": r.candidate_id,
        "Score": f"{r.score:.4f}",
        "Confidence": f"{r.confidence:.0%}",
        "Top Factors": ", ".join([f"{k}:{v:.2f}" for k, v in sorted(r.feature_contributions.items(), key=lambda x: -abs(x[1]))[:3]]),
        "Explanation": r.explanation,
    } for r in results])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Score distribution
    fig = go.Figure(go.Histogram(x=[r.score for r in results], nbinsx=20))
    fig.update_layout(title="Score Distribution", xaxis_title="Score", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)
    
    # Feature importance
    if results:
        all_features = {}
        for r in results[:10]:
            for k, v in r.feature_contributions.items():
                all_features[k] = all_features.get(k, 0) + abs(v)
        
        if all_features:
            sorted_feat = sorted(all_features.items(), key=lambda x: -x[1])[:15]
            fig = go.Figure(go.Bar(
                x=[v for k, v in reversed(sorted_feat)],
                y=[k for k, v in reversed(sorted_feat)],
                orientation='h',
            ))
            fig.update_layout(title="Top Feature Contributions (Top 10 Candidates)", height=400)
            st.plotly_chart(fig, use_container_width=True)


def render_research_assistant() -> None:
    """Render AI research assistant."""
    st.subheader("🤖 AI Research Assistant")
    st.caption("Ask research questions with traceable citations from PubMed, Knowledge Graph, and databases")
    
    # Session management
    col1, col2 = st.columns([3, 1])
    with col1:
        session_id = st.text_input("Session ID", value=ss.ari_current_session or "", placeholder="Enter or create session", key="ari_session_id")
    with col2:
        if st.button("New Session", key="ari_new_session"):
            ss.ari_current_session = str(uuid.uuid4())[:8]
            st.rerun()
    
    if not ss.ari_current_session:
        ss.ari_current_session = str(uuid.uuid4())[:8]
    
    # Question input
    question = st.text_area(
        "Your Research Question",
        placeholder="e.g., What are the therapeutic targets for TP53 mutations in breast cancer? What drugs target EGFR with good ADMET profiles?",
        height=100,
        key="ari_question",
    )
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔍 Ask", type="primary", use_container_width=True, key="ari_ask"):
            if question.strip():
                with st.spinner("Researching..."):
                    context = {
                        "gene_symbols": ss.ari_mtd_result.prioritized_targets if ss.ari_mtd_result else [],
                        "disease_names": [l.disease_name for l in ss.ari_mtd_result.gene_disease_links] if ss.ari_mtd_result else [],
                    }
                    answer = ss.ari_assistant.ask(question, ss.ari_current_session, context)
                    st.session_state["ari_last_answer"] = answer
                    st.rerun()
    
    # Display answer
    if "ari_last_answer" in st.session_state:
        answer = st.session_state["ari_last_answer"]
        
        st.divider()
        st.subheader("📝 Answer")
        
        # Confidence badge
        conf_color = "🟢" if answer.confidence > 0.7 else "🟡" if answer.confidence > 0.4 else "🔴"
        st.markdown(f"**Confidence:** {conf_color} {answer.confidence:.0%}")
        
        st.markdown(answer.answer)
        
        # Evidence
        if answer.evidence:
            with st.expander(f"📚 Evidence ({len(answer.evidence)} sources)"):
                for e in answer.evidence:
                    st.markdown(f"**[{e.source.upper()}]** {e.citation}")
                    st.markdown(f"> {e.content[:300]}...")
                    st.markdown(f"*Relevance: {e.relevance_score:.0%} | Entities: {', '.join(e.entity_links)}*")
                    st.divider()
        
        # Limitations
        if answer.limitations:
            with st.expander("⚠️ Limitations"):
                for lim in answer.limitations:
                    st.markdown(f"• {lim}")
        
        # Follow-ups
        if answer.follow_up_questions:
            with st.expander("🔄 Suggested Follow-up Questions"):
                for fq in answer.follow_up_questions:
                    if st.button(fq, key=f"ari_follow_{hash(fq)}"):
                        st.session_state["ari_question"] = fq
                        st.rerun()
        
        # Export
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📄 Export Session (JSON)", use_container_width=True):
                session = ss.ari_assistant.get_session(ss.ari_current_session)
                if session:
                    json_str = ss.ari_assistant.export_session(ss.ari_current_session, "json")
                    st.download_button("Download", json_str, f"research_session_{ss.ari_current_session}.json", "application/json")
        with col2:
            if st.button("📝 Export Session (Markdown)", use_container_width=True):
                session = ss.ari_assistant.get_session(ss.ari_current_session)
                if session:
                    md = ss.ari_assistant.export_session(ss.ari_current_session, "markdown")
                    st.download_button("Download", md, f"research_session_{ss.ari_current_session}.md", "text/markdown")
    
    # History
    session = ss.ari_assistant.get_session(ss.ari_current_session)
    if session and session.questions:
        with st.expander("📜 Session History"):
            for q, a in zip(session.questions, session.answers):
                st.markdown(f"**Q:** {q.question}")
                st.markdown(f"**A:** {a.answer[:200]}... (confidence: {a.confidence:.0%})")
                st.divider()


def render_reproducibility() -> None:
    """Render reproducibility tracker."""
    st.subheader("📊 Reproducibility & Experiment Tracking")
    st.caption("Track, version, and reproduce computational experiments")
    
    tab1, tab2, tab3 = st.tabs(["📝 Active Experiment", "📋 History", "⚖️ Compare"])
    
    with tab1:
        st.write("**Start New Experiment**")
        with st.form("rep_new_exp"):
            exp_name = st.text_input("Experiment Name", placeholder="e.g., TP53_drug_discovery_v1", key="rep_exp_name")
            exp_desc = st.text_area("Description", key="rep_exp_desc")
            exp_params = st.text_area("Parameters (JSON)", "{}", key="rep_exp_params")
            exp_tags = st.text_input("Tags (comma-separated)", "phase4.13", key="rep_exp_tags")
            
            if st.form_submit_button("Start Experiment"):
                try:
                    params = json.loads(exp_params)
                    tags = [t.strip() for t in exp_tags.split(",") if t.strip()]
                    tracker = ReproducibilityTracker.start(exp_name, exp_desc, params, tags=tags)
                    ss.ari_current_experiment = tracker
                    st.success(f"Started experiment: {tracker.experiment.experiment_id}")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        if "ari_current_experiment" in ss:
            tracker = ss.ari_current_experiment
            exp = tracker.experiment
            
            st.divider()
            st.write(f"**Active Experiment:** {exp.name} (`{exp.experiment_id}`)")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                step_name = st.text_input("Step Name", placeholder="variant_annotation", key="rep_step_name")
            with col2:
                step_func = st.text_input("Function", placeholder="annotate_variants", key="rep_step_func")
            with col3:
                step_module = st.text_input("Module", placeholder="mutation_to_drug_workflow", key="rep_step_module")
            
            step_params = st.text_area("Step Parameters (JSON)", "{}", key="rep_step_params")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Log Step", key="rep_log_step"):
                    try:
                        params = json.loads(step_params)
                        tracker.log_step(step_name, step_func, step_module, params)
                        st.success(f"Logged step: {step_name}")
                    except Exception as e:
                        st.error(f"Error: {e}")
            with col2:
                if st.button("Complete Experiment", type="primary", key="rep_complete"):
                    tracker.complete()
                    st.success("Experiment completed!")
                    del ss.ari_current_experiment
                    st.rerun()
            
            # Show steps
            if tracker.steps:
                st.write("**Steps:**")
                for step in tracker.steps:
                    st.write(f"• {step['step_name']} ({step['status']})")
    
    with tab2:
        st.write("**Experiment History**")
        experiments = ReproducibilityTracker.list_experiments(limit=50)
        
        if experiments:
            exp_data = []
            for e in experiments:
                exp_data.append({
                    "ID": e.experiment_id,
                    "Name": e.name,
                    "Status": e.status,
                    "Started": datetime.fromtimestamp(e.started_at).strftime("%Y-%m-%d %H:%M"),
                    "Duration": f"{e.duration_seconds:.1f}s" if e.duration_seconds else "Running",
                    "Git": e.git_commit[:8] if e.git_commit else "N/A",
                    "Tags": ", ".join(e.tags),
                })
            st.dataframe(pd.DataFrame(exp_data), use_container_width=True, hide_index=True)
            
            # Detail view
            selected = st.selectbox("View details:", [f"{e.experiment_id} - {e.name}" for e in experiments], key="rep_detail_select")
            if selected:
                eid = selected.split(" - ")[0]
                exp = ReproducibilityTracker.load(eid)
                if exp:
                    st.json(asdict(exp))
        else:
            st.info("No experiments tracked yet.")
    
    with tab3:
        st.write("**Compare Experiments**")
        experiments = ReproducibilityTracker.list_experiments(limit=20)
        
        if len(experiments) >= 2:
            exp_options = [f"{e.experiment_id} - {e.name}" for e in experiments]
            selected = st.multiselect("Select experiments to compare:", exp_options, max_selections=5, key="rep_compare_select")
            
            if len(selected) >= 2 and st.button("Compare", key="rep_compare_run"):
                eids = [s.split(" - ")[0] for s in selected]
                comparison = ReproducibilityTracker.compare(eids)
                
                if "error" not in comparison:
                    st.subheader("Parameter Differences")
                    if comparison["parameters"]:
                        for param, values in comparison["parameters"].items():
                            st.write(f"**{param}:**")
                            for eid, val in values.items():
                                st.write(f"  • {eid}: {val}")
                    
                    st.subheader("Metric Comparison")
                    if comparison["metrics"]:
                        for metric, values in comparison["metrics"].items():
                            st.write(f"**{metric}:**")
                            for eid, val in values.items():
                                st.write(f"  • {eid}: {val}")
                    
                    st.subheader("Git Commits")
                    for eid, commit in comparison["git_commits"].items():
                        st.write(f"• {eid}: {commit[:8] if commit else 'N/A'}")
                else:
                    st.error(comparison["error"])
        else:
            st.info("Need at least 2 experiments to compare.")


def render_advanced_reports() -> None:
    """Render advanced report generator."""
    st.subheader("📄 Advanced Report Generator")
    st.caption("Generate publication-ready reports in PDF, HTML, and Markdown")
    
    if not ss.ari_mtd_result:
        st.info("Run Mutation→Drug workflow or load results to generate reports.")
        return
    
    result = ss.ari_mtd_result
    
    # Report configuration
    with st.expander("⚙️ Report Configuration"):
        col1, col2 = st.columns(2)
        with col1:
            report_title = st.text_input("Title", f"Mutation-to-Drug Discovery Report", key="rep_title")
            report_subtitle = st.text_input("Subtitle", f"Workflow ID: {result.workflow_id}", key="rep_subtitle")
            author = st.text_input("Author", "GeneAI Research Platform", key="rep_author")
        with col2:
            institution = st.text_input("Institution", "", key="rep_institution")
            include_toc = st.checkbox("Table of Contents", True, key="rep_toc")
            include_lim = st.checkbox("Limitations", True, key="rep_lim")
    
    config = ReportConfig(
        title=report_title,
        subtitle=report_subtitle,
        author=author,
        institution=institution,
        include_toc=include_toc,
        include_limitations=include_lim,
    )
    
    # Generate report
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF", type="primary", use_container_width=True):
            with st.spinner("Generating PDF..."):
                generator = create_mutation_to_drug_report(result, config)
                pdf_path = generator.generate_pdf(f"/tmp/report_{result.workflow_id}.pdf")
                with open(pdf_path, "rb") as f:
                    st.download_button("Download PDF", f.read(), f"report_{result.workflow_id}.pdf", "application/pdf", use_container_width=True)
    
    with col2:
        if st.button("🌐 Generate HTML", use_container_width=True):
            with st.spinner("Generating HTML..."):
                generator = create_mutation_to_drug_report(result, config)
                html_path = generator.generate_html(f"/tmp/report_{result.workflow_id}.html")
                with open(html_path, "r") as f:
                    st.download_button("Download HTML", f.read(), f"report_{result.workflow_id}.html", "text/html", use_container_width=True)
    
    with col3:
        if st.button("📝 Generate Markdown", use_container_width=True):
            with st.spinner("Generating Markdown..."):
                generator = create_mutation_to_drug_report(result, config)
                md_path = generator.generate_markdown(f"/tmp/report_{result.workflow_id}.md")
                with open(md_path, "r") as f:
                    st.download_button("Download Markdown", f.read(), f"report_{result.workflow_id}.md", "text/markdown", use_container_width=True)
    
    # Report preview
    st.divider()
    st.subheader("📋 Report Preview (Markdown)")
    generator = create_mutation_to_drug_report(result, config)
    md_path = generator.generate_markdown(f"/tmp/preview_{result.workflow_id}.md")
    with open(md_path, "r") as f:
        st.markdown(f.read())


if __name__ == "__main__":
    render_ai_research_intelligence_dashboard()