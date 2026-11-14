"""Streamlit UI for Disease-Gene-Pathway Network Analysis."""
from __future__ import annotations

import json
import uuid
from typing import Any

import networkx as nx
import plotly.graph_objects as go
import streamlit as st
from streamlit import session_state as ss

from geneai.config import APP_NAME
from geneai.disease_gene_pathway.analysis_engine import (
    DiseaseGenePathwayAnalyzer,
    run_disease_gene_pathway_analysis,
    run_vcf_analysis,
)
from geneai.disease_gene_pathway.database import (
    clear_dgp_analysis_run,
    get_dgp_analysis_run,
    get_dgp_network,
    get_dgp_therapeutic_targets,
    get_recent_dgp_runs,
    search_dgp_runs,
    store_dgp_analysis_run,
    store_dgp_disease_associations,
    store_dgp_disgenet_associations,
    store_dgp_go_enrichment,
    store_dgp_kegg_pathways,
    store_dgp_network,
    store_dgp_reactome_pathways,
    store_dgp_string_enrichment,
    store_dgp_therapeutic_targets,
)
from geneai.disease_gene_pathway.report_generator import (
    generate_dgp_csv_report,
    generate_dgp_json_report,
    generate_dgp_pdf_report,
)
from geneai.variants import parse_vcf

logger = None  # Will use st.error/warning


def render_dgp_dashboard() -> None:
    """Render the Disease-Gene-Pathway Network Analysis dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - Disease-Gene-Pathway Analysis",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🧬 Disease-Gene-Pathway Network Analysis")
    st.caption("Integrated analysis of disease-gene associations, PPI networks, pathways, and therapeutic targets")
    
    # Initialize session state
    if "dgp_results" not in ss:
        ss.dgp_results = {}
    if "dgp_current_run" not in ss:
        ss.dgp_current_run = None
    
    # Sidebar
    with st.sidebar:
        st.header("🔬 Analysis Input")
        input_method = st.radio(
            "Input Method",
            ["Gene List", "Disease Search", "VCF File", "Combined (Genes + Diseases)"],
            key="dgp_input_method",
        )
        
        st.divider()
        st.header("⚙️ Analysis Parameters")
        
        min_string_score = st.slider(
            "Minimum STRING Score",
            0.1, 1.0, 0.4, 0.05,
            help="Confidence threshold for PPI interactions",
            key="dgp_min_string",
        )
        
        min_ot_score = st.slider(
            "Minimum OpenTargets Score",
            0.0, 1.0, 0.1, 0.05,
            help="Minimum association score for disease-gene links",
            key="dgp_min_ot",
        )
        
        max_nodes = st.number_input(
            "Max Network Nodes",
            50, 1000, 500, 50,
            help="Maximum nodes in PPI network",
            key="dgp_max_nodes",
        )
        
        include_ppi = st.checkbox("Include PPI Network", value=True, key="dgp_include_ppi")
        include_pathways = st.checkbox("Include Pathway Analysis", value=True, key="dgp_include_pw")
        include_go = st.checkbox("Include GO Enrichment", value=True, key="dgp_include_go")
        include_disgenet = st.checkbox("Include DisGeNET", value=True, key="dgp_include_dg")
        
        save_to_db = st.checkbox("Save to Database", value=True, key="dgp_save_db")
        
        st.divider()
        st.header("📊 Recent Analyses")
        recent = get_recent_dgp_runs(10)
        for run in recent:
            genes_preview = ", ".join(run["input_genes"][:3])
            if len(run["input_genes"]) > 3:
                genes_preview += f" +{len(run['input_genes'])-3} more"
            if st.button(f"{genes_preview} ({run['created_at']:.0f})", key=f"recent_{run['run_id']}"):
                _load_run(run["run_id"])
    
    # Main content
    if input_method == "Gene List":
        render_gene_list_input(min_string_score, min_ot_score, max_nodes,
                              include_ppi, include_pathways, include_go, include_disgenet, save_to_db)
    elif input_method == "Disease Search":
        render_disease_search_input(min_string_score, min_ot_score, max_nodes,
                                   include_ppi, include_pathways, include_go, include_disgenet, save_to_db)
    elif input_method == "VCF File":
        render_vcf_input(min_string_score, min_ot_score, max_nodes,
                        include_ppi, include_pathways, include_go, include_disgenet, save_to_db)
    elif input_method == "Combined (Genes + Diseases)":
        render_combined_input(min_string_score, min_ot_score, max_nodes,
                             include_ppi, include_pathways, include_go, include_disgenet, save_to_db)
    
    # Display results if available
    if ss.dgp_current_run and ss.dgp_current_run in ss.dgp_results:
        display_results(ss.dgp_current_run, ss.dgp_results[ss.dgp_current_run])


def render_gene_list_input(
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Render gene list input interface."""
    st.subheader("📝 Gene List Input")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        genes_text = st.text_area(
            "Enter Gene Symbols (one per line or comma-separated)",
            placeholder="TP53\nEGFR\nBRCA1\nKRAS\nPIK3CA",
            height=150,
            key="dgp_genes_input",
        )
    with col2:
        st.write("")
        st.write("")
        st.write("**Examples:**")
        examples = {
            "Cancer Drivers": "TP53, EGFR, BRCA1, KRAS, PIK3CA, PTEN, MYC, BRAF",
            "DNA Repair": "BRCA1, BRCA2, ATM, CHEK2, PALB2, RAD51, MSH2, MLH1",
            "Immune Checkpoint": "PDCD1, CTLA4, LAG3, TIGIT, HAVCR2, CD274",
        }
        for name, genes in examples.items():
            if st.button(name, key=f"ex_{name}", use_container_width=True):
                ss.dgp_genes_input = genes
                st.rerun()
    
    if st.button("🔬 Analyze Genes", type="primary", use_container_width=True, key="dgp_analyze_genes"):
        genes = parse_gene_list(genes_text)
        if not genes:
            st.error("Please enter at least one gene symbol")
            return
        
        run_analysis(
            genes=genes,
            diseases=None,
            min_string_score=min_string_score,
            min_ot_score=min_ot_score,
            max_nodes=max_nodes,
            include_ppi=include_ppi,
            include_pathways=include_pathways,
            include_go=include_go,
            include_disgenet=include_disgenet,
            save_to_db=save_to_db,
        )


def render_disease_search_input(
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Render disease search input."""
    st.subheader("🔍 Disease Search")
    
    from geneai.disease_gene_pathway.api_clients import search_opentargets_diseases
    
    col1, col2 = st.columns([3, 1])
    with col1:
        disease_query = st.text_input(
            "Search Disease",
            placeholder="e.g., breast cancer, Alzheimer, diabetes",
            key="dgp_disease_search",
        )
    with col2:
        st.write("")
        search_btn = st.button("🔍 Search", type="primary", use_container_width=True, key="dgp_search_disease")
    
    if search_btn and disease_query.strip():
        with st.spinner("Searching OpenTargets..."):
            diseases = search_opentargets_diseases(disease_query.strip(), limit=20)
        
        if diseases:
            st.session_state["dgp_disease_results"] = diseases
            st.success(f"Found {len(diseases)} diseases")
        else:
            st.warning("No diseases found")
    
    # Display search results
    if "dgp_disease_results" in st.session_state:
        diseases = st.session_state["dgp_disease_results"]
        for i, disease in enumerate(diseases):
            with st.expander(f"{disease['name']} (ID: {disease['id']})"):
                cols = st.columns([2, 1, 1])
                cols[0].write(f"**Description:** {disease['description'] or 'N/A'}")
                if disease.get("therapeutic_areas"):
                    cols[0].write(f"**Therapeutic Areas:** {', '.join(disease['therapeutic_areas'])}")
                if cols[1].button("Analyze This Disease", key=f"analyze_dis_{i}"):
                    run_analysis(
                        genes=[],
                        diseases=[disease["id"]],
                        min_string_score=min_string_score,
                        min_ot_score=min_ot_score,
                        max_nodes=max_nodes,
                        include_ppi=include_ppi,
                        include_pathways=include_pathways,
                        include_go=include_go,
                        include_disgenet=include_disgenet,
                        save_to_db=save_to_db,
                    )
                if cols[2].button("View Details", key=f"detail_dis_{i}"):
                    st.json(disease)


def render_vcf_input(
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Render VCF file input."""
    st.subheader("📄 VCF File Analysis")
    st.write("Upload a VCF file to extract genes from variants and analyze disease-gene-pathway networks.")
    
    file = st.file_uploader(
        "VCF File",
        type=["vcf", "vcf.gz"],
        key="dgp_vcf_file",
    )
    
    disease_input = st.text_input(
        "Optional: Disease IDs (comma-separated, e.g., EFO_0000305,MONDO_0007254)",
        key="dgp_vcf_diseases",
    )
    
    if file and st.button("🔬 Analyze VCF", type="primary", key="dgp_analyze_vcf"):
        with st.spinner("Parsing VCF..."):
            try:
                variants, meta = parse_vcf(file.getvalue(), file.name)
                st.success(f"Parsed {len(variants)} variants")
                
                # Extract unique genes
                genes = list(set(v.get("gene") or v.get("SYMBOL") or v.get("GENE") for v in variants if v.get("gene") or v.get("SYMBOL") or v.get("GENE")))
                genes = [g for g in genes if g]
                
                if not genes:
                    st.warning("No genes found in VCF")
                    return
                
                st.info(f"Found {len(genes)} unique genes: {', '.join(genes[:10])}{'...' if len(genes) > 10 else ''}")
                
                diseases = [d.strip() for d in disease_input.split(",")] if disease_input else None
                
                run_vcf_analysis(
                    variants=variants,
                    diseases=diseases,
                    min_string_score=min_string_score,
                    min_ot_score=min_ot_score,
                    max_nodes=max_nodes,
                    include_ppi=include_ppi,
                    include_pathways=include_pathways,
                    include_go=include_go,
                    include_disgenet=include_disgenet,
                    save_to_db=save_to_db,
                )
            except Exception as e:
                st.error(f"VCF parsing failed: {e}")


def render_combined_input(
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Render combined genes + diseases input."""
    st.subheader("🔗 Combined Analysis (Genes + Diseases)")
    
    col1, col2 = st.columns(2)
    with col1:
        genes_text = st.text_area(
            "Gene Symbols",
            placeholder="TP53\nEGFR\nBRCA1",
            height=120,
            key="dgp_combined_genes",
        )
    with col2:
        diseases_text = st.text_area(
            "Disease IDs (one per line)",
            placeholder="EFO_0000305\nMONDO_0007254\nOrphanet_558",
            height=120,
            key="dgp_combined_diseases",
        )
    
    if st.button("🔬 Analyze Combined", type="primary", use_container_width=True, key="dgp_analyze_combined"):
        genes = parse_gene_list(genes_text)
        diseases = [d.strip() for d in diseases_text.split("\n") if d.strip()] if diseases_text else None
        
        if not genes and not diseases:
            st.error("Please enter at least genes or diseases")
            return
        
        run_analysis(
            genes=genes,
            diseases=diseases,
            min_string_score=min_string_score,
            min_ot_score=min_ot_score,
            max_nodes=max_nodes,
            include_ppi=include_ppi,
            include_pathways=include_pathways,
            include_go=include_go,
            include_disgenet=include_disgenet,
            save_to_db=save_to_db,
        )


def parse_gene_list(text: str) -> list[str]:
    """Parse gene list from text input."""
    # Replace commas with newlines, split, clean
    text = text.replace(",", "\n")
    genes = [g.strip().upper() for g in text.split("\n") if g.strip()]
    # Deduplicate preserving order
    return list(dict.fromkeys(genes))


def run_analysis(
    genes: list[str],
    diseases: list[str] | None,
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Run the DGP analysis."""
    run_id = str(uuid.uuid4())[:8]
    
    with st.spinner("Running disease-gene-pathway analysis..."):
        try:
            analyzer = DiseaseGenePathwayAnalyzer(
                min_string_score=min_string_score,
                min_opentargets_score=min_ot_score,
                max_network_nodes=max_nodes,
            )
            
            result = analyzer.analyze_genes(
                genes,
                diseases,
                include_ppi=include_ppi,
                include_pathways=include_pathways,
                include_go=include_go,
                include_disgenet=include_disgenet,
            )
            
            # Store in session
            ss.dgp_results[run_id] = result
            ss.dgp_current_run = run_id
            
            # Save to database
            if save_to_db:
                save_analysis_to_db(run_id, genes, diseases, result)
            
            st.success("Analysis complete!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            logger = st.error if hasattr(st, 'error') else print
            logger(f"DGP analysis error: {e}")


def run_vcf_analysis(
    variants: list[dict],
    diseases: list[str] | None,
    min_string_score: float,
    min_ot_score: float,
    max_nodes: int,
    include_ppi: bool,
    include_pathways: bool,
    include_go: bool,
    include_disgenet: bool,
    save_to_db: bool,
) -> None:
    """Run VCF-based analysis."""
    run_id = str(uuid.uuid4())[:8]
    
    with st.spinner("Running VCF-based analysis..."):
        try:
            analyzer = DiseaseGenePathwayAnalyzer(
                min_string_score=min_string_score,
                min_opentargets_score=min_ot_score,
                max_network_nodes=max_nodes,
            )
            
            result = analyzer.analyze_vcf_variants(variants, diseases)
            
            ss.dgp_results[run_id] = result
            ss.dgp_current_run = run_id
            
            if save_to_db:
                # Extract genes from variants
                genes = list(set(v.get("gene") or v.get("SYMBOL") or v.get("GENE") for v in variants if v.get("gene") or v.get("SYMBOL") or v.get("GENE")))
                genes = [g for g in genes if g]
                save_analysis_to_db(run_id, genes, diseases, result)
            
            st.success("VCF analysis complete!")
            st.rerun()
            
        except Exception as e:
            st.error(f"VCF analysis failed: {e}")


def save_analysis_to_db(
    run_id: str,
    genes: list[str],
    diseases: list[str] | None,
    result,
) -> None:
    """Save analysis results to database."""
    try:
        # Store run
        store_dgp_analysis_run(
            run_id,
            genes,
            diseases,
            {
                "min_string_score": 0.4,
                "min_opentargets_score": 0.1,
                "max_network_nodes": 500,
            },
            result.summary,
        )
        
        # Store network
        network_data = {
            "nodes": [
                {
                    "gene_symbol": n.gene_symbol,
                    "gene_id": n.gene_id,
                    "uniprot_id": n.uniprot_id,
                    "degree": n.degree,
                    "betweenness_centrality": n.betweenness_centrality,
                    "clustering_coefficient": n.clustering_coefficient,
                    "is_hub": n.is_hub,
                    "is_input": n.gene_symbol in genes,
                    "uniprot_data": {
                        "protein_name": n.uniprot_entry.protein_name if n.uniprot_entry else None,
                        "function": n.uniprot_entry.function if n.uniprot_entry else None,
                        "location": n.uniprot_entry.subcellular_location if n.uniprot_entry else None,
                    } if n.uniprot_entry else None,
                }
                for n in result.hub_genes
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "weight": d.get("weight", 0),
                    "combined_score": d.get("combined_score", 0),
                    "evidence_types": d.get("evidence_types", []),
                    "experimental_score": d.get("experimental_score", 0),
                    "database_score": d.get("database_score", 0),
                    "textmining_score": d.get("textmining_score", 0),
                    "cooccurrence_score": d.get("cooccurrence_score", 0),
                    "coexpression_score": d.get("coexpression_score", 0),
                    "neighborhood_score": d.get("neighborhood_score", 0),
                    "fusion_score": d.get("fusion_score", 0),
                }
                for u, v, d in result.gene_network.edges(data=True)
            ],
        }
        store_dgp_network(run_id, network_data)
        
        # Store associations
        store_dgp_disease_associations(run_id, [
            {
                "disease_id": a.disease_id,
                "disease_name": a.disease_name,
                "gene_symbol": a.gene_symbol,
                "gene_id": a.gene_id,
                "score": a.score,
                "datasources": a.datasources,
                "evidence_count": a.evidence_count,
                "source": "OpenTargets",
            }
            for a in result.disease_gene_associations
        ])
        
        store_dgp_disgenet_associations(run_id, [
            {
                "disease_id": a.disease_id,
                "disease_name": a.disease_name,
                "disease_type": a.disease_type,
                "gene_symbol": a.gene_symbol,
                "gene_id": a.gene_id,
                "score": a.score,
                "ei": a.ei,
                "year_initial": a.year_initial,
                "year_final": a.year_final,
                "n_pmids": a.n_pmids,
                "snps": a.snps,
            }
            for a in result.disgenet_associations
        ])
        
        # Store pathways
        store_dgp_kegg_pathways(run_id, [
            {
                "pathway_id": p.pathway_id,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "genes": p.genes,
                "gene_names": p.gene_names,
            }
            for p in result.kegg_pathways
        ])
        
        store_dgp_reactome_pathways(run_id, [
            {
                "pathway_id": p.pathway_id,
                "name": p.name,
                "species": p.species,
                "genes": p.genes,
                "gene_names": p.gene_names,
                "p_value": None,
                "fdr": None,
                "entities_found": None,
                "entities_total": None,
                "entities_ratio": None,
            }
            for p in result.reactome_pathways
        ])
        
        # Store GO enrichment
        store_dgp_go_enrichment(run_id, result.go_enrichment)
        
        # Store STRING enrichment
        store_dgp_string_enrichment(run_id, result.string_enrichment)
        
        # Store therapeutic targets
        store_dgp_therapeutic_targets(run_id, result.therapeutic_targets)
        
    except Exception as e:
        st.warning(f"Database save failed: {e}")


def _load_run(run_id: str) -> None:
    """Load a previous run from database."""
    run = get_dgp_analysis_run(run_id)
    if run:
        st.session_state["dgp_current_run"] = run_id
        st.info(f"Loaded run {run_id}. Re-run analysis to view results.")


def display_results(run_id: str, result) -> None:
    """Display analysis results."""
    st.divider()
    
    # Header
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Input Genes", result.summary.get("total_input_genes", 0))
    with col2:
        st.metric("Network Nodes", result.summary.get("network_nodes", 0))
    with col3:
        st.metric("Hub Genes", result.summary.get("hub_genes_count", 0))
    with col4:
        st.metric("Therapeutic Targets", result.summary.get("therapeutic_targets_count", 0))
    
    # Tabs
    tabs = st.tabs([
        "📊 Overview",
        "🕸️ Network",
        "🎯 Hub Genes",
        "💊 Therapeutic Targets",
        "🏥 Disease Associations",
        "🛤️ Pathways",
        "🧬 GO Enrichment",
        "📄 Reports",
    ])
    
    with tabs[0]:
        render_overview_tab(result)
    
    with tabs[1]:
        render_network_tab(result)
    
    with tabs[2]:
        render_hub_genes_tab(result)
    
    with tabs[3]:
        render_therapeutic_targets_tab(result)
    
    with tabs[4]:
        render_disease_associations_tab(result)
    
    with tabs[5]:
        render_pathways_tab(result)
    
    with tabs[6]:
        render_go_enrichment_tab(result)
    
    with tabs[7]:
        render_reports_tab(run_id, result)


def render_overview_tab(result) -> None:
    """Render overview tab."""
    st.subheader("Analysis Summary")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Network Statistics**")
        st.write(f"- Nodes: {result.summary.get('network_nodes', 0)}")
        st.write(f"- Edges: {result.summary.get('network_edges', 0)}")
        st.write(f"- Hub Genes: {result.summary.get('hub_genes_count', 0)}")
        st.write(f"- Input Genes: {result.summary.get('total_input_genes', 0)}")
    
    with col2:
        st.write("**Enrichment Results**")
        st.write(f"- KEGG Pathways: {result.summary.get('kegg_pathways_count', 0)}")
        st.write(f"- Reactome Pathways: {result.summary.get('reactome_pathways_count', 0)}")
        st.write(f"- GO Terms: {result.summary.get('go_terms_enriched', 0)}")
        st.write(f"- STRING Terms: {result.summary.get('string_enrichment_terms', 0)}")
    
    st.write("**Disease Associations**")
    st.write(f"- OpenTargets: {result.summary.get('disease_associations_count', 0)}")
    st.write(f"- DisGeNET: {result.summary.get('disgenet_associations_count', 0)}")
    
    if result.input_diseases:
        st.write("**Input Diseases:**")
        for d in result.input_diseases:
            st.write(f"- {d}")


def render_network_tab(result) -> None:
    """Render interactive network visualization."""
    st.subheader("Gene Interaction Network")
    
    if result.gene_network.number_of_nodes() == 0:
        st.info("No network data available. Enable PPI analysis in settings.")
        return
    
    # Network layout
    try:
        pos = nx.spring_layout(result.gene_network, k=2, iterations=50, seed=42)
    except Exception:
        pos = {n: (i % 10, i // 10) for i, n in enumerate(result.gene_network.nodes())}
    
    # Prepare edge traces
    edge_x, edge_y = [], []
    for u, v in result.gene_network.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines',
        showlegend=False,
    )
    
    # Prepare node traces
    node_x, node_y = [], []
    node_text, node_color, node_size = [], [], []
    
    for node in result.gene_network.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        
        # Find hub gene data
        hub = next((h for h in result.hub_genes if h.gene_symbol == node), None)
        is_input = node in result.input_genes
        
        if hub and hub.is_hub:
            node_color.append('#e74c3c')  # Red for hubs
            node_size.append(20)
        elif is_input:
            node_color.append('#3498db')  # Blue for input genes
            node_size.append(15)
        else:
            node_color.append('#95a5a6')  # Gray for others
            node_size.append(10)
        
        # Hover text
        text = f"<b>{node}</b>"
        if hub:
            text += f"<br>Degree: {hub.degree}"
            text += f"<br>Betweenness: {hub.betweenness_centrality:.4f}"
            if hub.disease_associations:
                text += f"<br>Diseases: {len(hub.disease_associations)}"
        if is_input:
            text += "<br>⭐ Input Gene"
        node_text.append(text)
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[n for n in result.gene_network.nodes()],
        textposition="top center",
        textfont=dict(size=8),
        hoverinfo='text',
        hovertext=node_text,
        marker=dict(
            showscale=False,
            color=node_color,
            size=node_size,
            line=dict(width=1, color='white'),
        ),
        showlegend=False,
    )
    
    # Create figure
    fig = go.Figure(data=[edge_trace, node_trace],
        layout=go.Layout(
            title=f"Gene Network ({result.gene_network.number_of_nodes()} nodes, {result.gene_network.number_of_edges()} edges)",
            titlefont_size=14,
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=600,
        ))
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Network stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Density", f"{nx.density(result.gene_network):.4f}")
    with col2:
        if result.gene_network.number_of_nodes() > 1:
            st.metric("Avg Clustering", f"{nx.average_clustering(result.gene_network):.4f}")
    with col3:
        components = list(nx.connected_components(result.gene_network))
        st.metric("Components", len(components))


def render_hub_genes_tab(result) -> None:
    """Render hub genes table."""
    st.subheader("Hub Genes & Network Centrality")
    
    if not result.hub_genes:
        st.info("No hub genes identified.")
        return
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        show_hubs_only = st.checkbox("Show Hubs Only", value=True, key="dgp_hubs_only")
    with col2:
        min_degree = st.number_input("Min Degree", 0, 100, 0, key="dgp_min_deg")
    
    # Prepare data
    hub_data = []
    for hub in result.hub_genes:
        if show_hubs_only and not hub.is_hub:
            continue
        if hub.degree < min_degree:
            continue
        
        diseases = "; ".join(set(a.disease_name for a in hub.disease_associations[:3]))
        hub_data.append({
            "Gene": hub.gene_symbol,
            "UniProt": hub.uniprot_id or "N/A",
            "Degree": hub.degree,
            "Betweenness": f"{hub.betweenness_centrality:.4f}",
            "Clustering": f"{hub.clustering_coefficient:.4f}",
            "Hub": "⭐" if hub.is_hub else "",
            "Input Gene": "✓" if hub.gene_symbol in result.input_genes else "",
            "Diseases": diseases[:100] + "..." if len(diseases) > 100 else diseases,
            "Pathways": len(hub.pathways),
        })
    
    if hub_data:
        st.dataframe(hub_data, use_container_width=True, hide_index=True)
        
        # Download button
        import pandas as pd
        df = pd.DataFrame(hub_data)
        csv = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Hub Genes CSV",
            csv,
            "hub_genes.csv",
            "text/csv",
        )
    else:
        st.info("No hub genes match the filters.")


def render_therapeutic_targets_tab(result) -> None:
    """Render therapeutic targets."""
    st.subheader("Potential Therapeutic Targets")
    
    if not result.therapeutic_targets:
        st.info("No therapeutic targets identified.")
        return
    
    target_data = []
    for target in result.therapeutic_targets:
        target_data.append({
            "Rank": target.get("rank", ""),
            "Gene": target.get("gene_symbol", ""),
            "Score": f"{target.get('score', 0):.3f}",
            "Degree": target.get("degree", 0),
            "Betweenness": f"{target.get('betweenness', 0):.4f}",
            "Diseases": target.get("disease_count", 0),
            "Pathways": target.get("pathway_count", 0),
            "Key Reasons": "; ".join(target.get("reasons", [])[:2]),
        })
    
    st.dataframe(target_data, use_container_width=True, hide_index=True)
    
    # Download
    import pandas as pd
    df = pd.DataFrame(target_data)
    csv = df.to_csv(index=False)
    st.download_button(
        "⬇️ Download Targets CSV",
        csv,
        "therapeutic_targets.csv",
        "text/csv",
    )


def render_disease_associations_tab(result) -> None:
    """Render disease associations."""
    st.subheader("Disease-Gene Associations")
    
    tab1, tab2 = st.tabs(["OpenTargets", "DisGeNET"])
    
    with tab1:
        if result.disease_gene_associations:
            assoc_data = []
            for a in sorted(result.disease_gene_associations, key=lambda x: -x.score)[:100]:
                assoc_data.append({
                    "Disease": a.disease_name,
                    "Disease ID": a.disease_id,
                    "Gene": a.gene_symbol,
                    "Score": f"{a.score:.3f}",
                    "Data Sources": ", ".join(a.datasources[:3]),
                    "Evidence": a.evidence_count,
                })
            st.dataframe(assoc_data, use_container_width=True, hide_index=True)
        else:
            st.info("No OpenTargets associations found.")
    
    with tab2:
        if result.disgenet_associations:
            assoc_data = []
            for a in sorted(result.disgenet_associations, key=lambda x: -x.score)[:100]:
                assoc_data.append({
                    "Disease": a.disease_name,
                    "Disease ID": a.disease_id,
                    "Type": a.disease_type,
                    "Gene": a.gene_symbol,
                    "Score": f"{a.score:.3f}",
                    "EI": f"{a.ei:.3f}",
                    "PMIDs": a.n_pmids,
                    "SNPs": len(a.snps),
                })
            st.dataframe(assoc_data, use_container_width=True, hide_index=True)
        else:
            st.info("No DisGeNET associations found.")


def render_pathways_tab(result) -> None:
    """Render pathway analysis."""
    st.subheader("Pathway Analysis")
    
    tab1, tab2 = st.tabs(["KEGG", "Reactome"])
    
    with tab1:
        if result.kegg_pathways:
            pw_data = []
            for p in result.kegg_pathways:
                pw_data.append({
                    "Pathway ID": p.pathway_id,
                    "Name": p.name,
                    "Category": p.category,
                    "Genes": len(p.genes),
                    "Gene List": ", ".join(p.genes[:10]) + ("..." if len(p.genes) > 10 else ""),
                })
            st.dataframe(pw_data, use_container_width=True, hide_index=True)
        else:
            st.info("No KEGG pathways found.")
    
    with tab2:
        if result.reactome_pathways:
            pw_data = []
            for p in result.reactome_pathways:
                pw_data.append({
                    "Pathway ID": p.pathway_id,
                    "Name": p.name,
                    "Species": p.species,
                    "Genes": len(p.genes),
                    "Gene List": ", ".join(p.genes[:10]) + ("..." if len(p.genes) > 10 else ""),
                })
            st.dataframe(pw_data, use_container_width=True, hide_index=True)
        else:
            st.info("No Reactome pathways found.")


def render_go_enrichment_tab(result) -> None:
    """Render GO enrichment."""
    st.subheader("Gene Ontology Enrichment")
    
    aspect_names = {"P": "Biological Process", "F": "Molecular Function", "C": "Cellular Component"}
    
    for aspect, terms in result.go_enrichment.items():
        if not terms:
            continue
        with st.expander(f"{aspect_names.get(aspect, aspect)} ({len(terms)} terms)"):
            term_data = []
            for term in terms[:30]:
                term_data.append({
                    "GO ID": term.get("go_id", ""),
                    "Term": term.get("go_name", ""),
                    "Genes": term.get("gene_count", 0),
                    "Gene List": ", ".join(term.get("genes", [])[:10]),
                })
            st.dataframe(term_data, use_container_width=True, hide_index=True)
    
    # STRING enrichment
    if result.string_enrichment:
        with st.expander("STRING Functional Enrichment"):
            str_data = []
            for term in result.string_enrichment[:30]:
                str_data.append({
                    "Category": term.get("category", ""),
                    "Term": term.get("term", ""),
                    "Description": term.get("description", ""),
                    "P-value": f"{term.get('p_value', 1):.2e}",
                    "FDR": f"{term.get('fdr', 1):.2e}",
                    "Input Genes": term.get("input_genes", 0),
                })
            st.dataframe(str_data, use_container_width=True, hide_index=True)


def render_reports_tab(run_id: str, result) -> None:
    """Render report generation."""
    st.subheader("Generate Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", use_container_width=True, key=f"dgp_pdf_{run_id}"):
            with st.spinner("Generating PDF..."):
                pdf_bytes = generate_dgp_pdf_report(result, run_id)
            st.download_button(
                "⬇️ Download PDF",
                pdf_bytes,
                f"dgp_report_{run_id}.pdf",
                "application/pdf",
                use_container_width=True,
            )
    
    with col2:
        if st.button("📊 Generate CSV Report", use_container_width=True, key=f"dgp_csv_{run_id}"):
            with st.spinner("Generating CSV..."):
                csv_str = generate_dgp_csv_report(result, run_id)
            st.download_button(
                "⬇️ Download CSV",
                csv_str,
                f"dgp_report_{run_id}.csv",
                "text/csv",
                use_container_width=True,
            )
    
    with col3:
        if st.button("📋 Generate JSON Report", use_container_width=True, key=f"dgp_json_{run_id}"):
            with st.spinner("Generating JSON..."):
                json_data = generate_dgp_json_report(result, run_id)
            st.download_button(
                "⬇️ Download JSON",
                json.dumps(json_data, indent=2),
                f"dgp_report_{run_id}.json",
                "application/json",
                use_container_width=True,
            )
    
    st.divider()
    st.write("**Quick JSON Preview**")
    json_preview = generate_dgp_json_report(result, run_id)
    st.json(json_preview, expanded=False)


if __name__ == "__main__":
    render_dgp_dashboard()