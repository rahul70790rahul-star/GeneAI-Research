"""Streamlit UI for Unified Knowledge Database - Phase 5.3."""
from __future__ import annotations

import json
import logging
import streamlit as st
import pandas as pd
from typing import Any

from geneai.unified_knowledge.database import KnowledgeDatabase, get_knowledge_db, init_knowledge_db, DatabaseConfig
from geneai.unified_knowledge.query import KnowledgeQuery, get_knowledge_query
from geneai.unified_knowledge.loaders import load_all_data, GeneLoader, ProteinLoader, DrugLoader

logger = logging.getLogger(__name__)


def render_unified_knowledge_dashboard():
    """Render the unified knowledge database dashboard."""
    st.title("🧠 GeneAI Unified Knowledge Database")
    st.caption("Integrated biological knowledge graph with genes, diseases, proteins, drugs, pathways, and literature")
    
    # Initialize database
    if "knowledge_db" not in st.session_state:
        st.session_state.knowledge_db = get_knowledge_db()
        st.session_state.query = get_knowledge_query()
    
    db: KnowledgeDatabase = st.session_state.knowledge_db
    query: KnowledgeQuery = st.session_state.query
    
    # Sidebar
    with st.sidebar:
        st.header("Database")
        
        # Database stats
        stats = query.get_database_stats()
        st.subheader("Statistics")
        for table, count in stats.items():
            st.metric(table.replace('_', ' ').title(), f"{count:,}")
        
        st.divider()
        
        # Database management
        st.subheader("Management")
        
        if st.button("🔄 Refresh Stats", use_container_width=True):
            st.rerun()
        
        if st.button("🧹 Vacuum Database", use_container_width=True):
            with st.spinner("Vacuuming..."):
                db.vacuum()
            st.success("Database vacuumed")
            st.rerun()
        
        # Data loading
        st.subheader("Data Loading")
        load_sources = st.multiselect(
            "Sources to load",
            ["genes", "diseases", "proteins", "pathways", "drugs", "literature"],
            default=["genes", "pathways", "drugs"]
        )
        
        if st.button("📥 Load Data", use_container_width=True, type="primary"):
            with st.spinner("Loading data from sources..."):
                results = load_all_data(db, load_sources)
            
            for source, load_stats in results.items():
                if load_stats.errors > 0:
                    st.error(f"{source}: {load_stats.errors} errors")
                else:
                    st.success(f"{source}: {load_stats.records_inserted} inserted in {load_stats.duration_seconds:.1f}s")
            
            st.rerun()
        
        st.divider()
        
        # Export
        st.subheader("Export")
        if st.button("📊 Export Stats as JSON", use_container_width=True):
            export_data = json.dumps(stats, indent=2)
            st.download_button(
                "Download",
                export_data,
                "knowledge_db_stats.json",
                "application/json",
                use_container_width=True,
            )
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🔍 Search", "🧬 Genes", "🏥 Diseases", "💊 Drugs", 
        "🔬 Proteins", "🛤️ Pathways", "📚 Literature"
    ])
    
    with tab1:
        render_search_tab(query)
    
    with tab2:
        render_genes_tab(query)
    
    with tab3:
        render_diseases_tab(query)
    
    with tab4:
        render_drugs_tab(query)
    
    with tab5:
        render_proteins_tab(query)
    
    with tab6:
        render_pathways_tab(query)
    
    with tab7:
        render_literature_tab(query)


def render_search_tab(query: KnowledgeQuery):
    """Render unified search tab."""
    st.subheader("Unified Search")
    st.write("Search across all entity types")
    
    search_query = st.text_input("Search query", placeholder="e.g. TP53, breast cancer, aspirin")
    search_type = st.selectbox(
        "Search in",
        ["All", "Genes", "Diseases", "Drugs", "Proteins", "Pathways", "Literature"]
    )
    
    if st.button("Search", type="primary") and search_query:
        results = {}
        
        if search_type in ["All", "Genes"]:
            results["Genes"] = query.search_genes(search_query, 10)
        if search_type in ["All", "Diseases"]:
            results["Diseases"] = query.search_diseases(search_query, 10)
        if search_type in ["All", "Drugs"]:
            results["Drugs"] = query.search_drugs(search_query, 10)
        if search_type in ["All", "Proteins"]:
            results["Proteins"] = query.search_proteins(search_query, 10)
        if search_type in ["All", "Pathways"]:
            results["Pathways"] = query.search_pathways(search_query, 10)
        if search_type in ["All", "Literature"]:
            results["Literature"] = query.search_literature(search_query, 10)
        
        # Display results
        for entity_type, result in results.items():
            if result.count > 0:
                with st.expander(f"{entity_type} ({result.count} results)", expanded=True):
                    df = pd.DataFrame(result.data)
                    # Select relevant columns
                    display_cols = [c for c in df.columns if c in [
                        'symbol', 'name', 'mondo_id', 'chembl_id', 'uniprot_id', 
                        'pathway_id', 'pmid', 'title', 'source', 'category'
                    ]]
                    if display_cols:
                        st.dataframe(df[display_cols], hide_index=True)
                    else:
                        st.dataframe(df, hide_index=True)


def render_genes_tab(query: KnowledgeQuery):
    """Render genes tab."""
    st.subheader("Gene Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        gene_symbol = st.text_input("Gene symbol", placeholder="e.g. TP53, BRCA1, EGFR").upper()
    
    with col2:
        if st.button("Lookup", type="primary") and gene_symbol:
            pass
    
    if gene_symbol:
        # Gene details
        gene = query.get_gene(gene_symbol)
        if gene:
            st.write(f"### {gene['symbol']} - {gene.get('name', 'N/A')}")
            
            cols = st.columns(4)
            cols[0].metric("Ensembl ID", gene.get('ensembl_id', 'N/A'))
            cols[1].metric("Entrez ID", gene.get('entrez_id', 'N/A'))
            cols[2].metric("Chromosome", gene.get('chromosome', 'N/A'))
            cols[3].metric("Biotype", gene.get('biotype', 'N/A'))
            
            if gene.get('description'):
                st.write("**Description:**", gene['description'])
            
            # Tabs for related data
            gtab1, gtab2, gtab3, gtab4 = st.tabs(["Diseases", "Pathways", "Proteins", "Variants"])
            
            with gtab1:
                diseases = query.get_gene_diseases(gene_symbol)
                if diseases.count > 0:
                    df = pd.DataFrame(diseases.data)
                    st.dataframe(df[['disease_name', 'mondo_id', 'association_type', 'score', 'source']], hide_index=True)
                else:
                    st.info("No disease associations found")
            
            with gtab2:
                pathways = query.get_gene_pathways(gene_symbol)
                if pathways.count > 0:
                    df = pd.DataFrame(pathways.data)
                    st.dataframe(df[['pathway_id', 'source', 'name', 'category']], hide_index=True)
                else:
                    st.info("No pathway memberships found")
            
            with gtab3:
                proteins = query.get_gene_proteins(gene_symbol)
                if proteins.count > 0:
                    df = pd.DataFrame(proteins.data)
                    st.dataframe(df[['uniprot_id', 'name', 'length', 'mass']], hide_index=True)
                else:
                    st.info("No protein entries found")
            
            with gtab4:
                variants = query.get_gene_variants(gene_symbol, 50)
                if variants.count > 0:
                    df = pd.DataFrame(variants.data)
                    st.dataframe(df[['variant_id', 'chrom', 'pos', 'ref', 'alt', 'consequence', 'impact', 'clinvar_significance']], hide_index=True)
                else:
                    st.info("No variants found")
        else:
            st.error(f"Gene {gene_symbol} not found in database")


def render_diseases_tab(query: KnowledgeQuery):
    """Render diseases tab."""
    st.subheader("Disease Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        disease_query = st.text_input("Disease name", placeholder="e.g. breast cancer, Alzheimer")
    
    with col2:
        if st.button("Search Diseases", type="primary") and disease_query:
            pass
    
    if disease_query:
        diseases = query.search_diseases(disease_query, 20)
        if diseases.count > 0:
            df = pd.DataFrame(diseases.data)
            st.dataframe(df[['name', 'mondo_id', 'description']], hide_index=True)
            
            # Select disease for details
            selected = st.selectbox(
                "Select disease for details",
                options=[d['name'] for d in diseases.data],
                format_func=lambda x: x
            )
            
            if selected:
                disease = query.get_disease(name=selected)
                if disease:
                    st.write(f"### {disease['name']}")
                    if disease.get('mondo_id'):
                        st.write(f"**MONDO ID:** {disease['mondo_id']}")
                    if disease.get('description'):
                        st.write(f"**Description:** {disease['description']}")
                    
                    # Related genes
                    st.write("#### Associated Genes")
                    genes = query.get_disease_genes(selected, 30)
                    if genes.count > 0:
                        df = pd.DataFrame(genes.data)
                        st.dataframe(df[['symbol', 'name', 'association_type', 'score', 'source']], hide_index=True)
                    
                    # Related drugs
                    st.write("#### Related Drugs")
                    drugs = query.get_disease_drugs(selected, 20)
                    if drugs.count > 0:
                        df = pd.DataFrame(drugs.data)
                        st.dataframe(df[['name', 'chembl_id', 'max_phase', 'mechanism_of_action']], hide_index=True)
        else:
            st.info("No diseases found")


def render_drugs_tab(query: KnowledgeQuery):
    """Render drugs tab."""
    st.subheader("Drug Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        drug_query = st.text_input("Drug name or ChEMBL ID", placeholder="e.g. aspirin, CHEMBL25")
    
    with col2:
        if st.button("Search Drugs", type="primary") and drug_query:
            pass
    
    if drug_query:
        drugs = query.search_drugs(drug_query, 20)
        if drugs.count > 0:
            df = pd.DataFrame(drugs.data)
            st.dataframe(df[['name', 'chembl_id', 'max_phase', 'therapeutic_area']], hide_index=True)
            
            # Select drug for details
            selected = st.selectbox(
                "Select drug for details",
                options=[d['name'] for d in drugs.data],
                format_func=lambda x: x
            )
            
            if selected:
                drug = query.get_drug(name=selected)
                if drug:
                    st.write(f"### {drug['name']}")
                    cols = st.columns(4)
                    cols[0].metric("ChEMBL ID", drug.get('chembl_id', 'N/A'))
                    cols[1].metric("Max Phase", drug.get('max_phase', 'N/A'))
                    cols[2].metric("MW", f"{drug.get('molecular_weight', 0):.1f}")
                    cols[3].metric("Formula", drug.get('molecular_formula', 'N/A'))
                    
                    if drug.get('mechanism_of_action'):
                        st.write("**Mechanism:**", drug['mechanism_of_action'])
                    
                    # Targets
                    st.write("#### Targets")
                    targets = query.get_drug_targets(drug['chembl_id'])
                    if targets.count > 0:
                        df = pd.DataFrame(targets.data)
                        st.dataframe(df[['target_name', 'target_uniprot', 'action_type', 'affinity_nM', 'affinity_type', 'confidence']], hide_index=True)
                    
                    # ADMET
                    if drug.get('smiles'):
                        st.write("#### ADMET Predictions")
                        admet = query.get_admet_predictions(drug['smiles'])
                        if admet:
                            df = pd.DataFrame(admet)
                            st.dataframe(df[['prediction_type', 'property_name', 'value', 'unit', 'confidence']], hide_index=True)
        else:
            st.info("No drugs found")


def render_proteins_tab(query: KnowledgeQuery):
    """Render proteins tab."""
    st.subheader("Protein Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        protein_query = st.text_input("Protein name or UniProt ID", placeholder="e.g. P53_HUMAN, P04637")
    
    with col2:
        if st.button("Search Proteins", type="primary") and protein_query:
            pass
    
    if protein_query:
        proteins = query.search_proteins(protein_query, 20)
        if proteins.count > 0:
            df = pd.DataFrame(proteins.data)
            st.dataframe(df[['uniprot_id', 'name', 'gene_symbol', 'length']], hide_index=True)
            
            # Select protein for details
            selected = st.selectbox(
                "Select protein for details",
                options=[f"{p['uniprot_id']} - {p['name'][:50]}" for p in proteins.data],
                format_func=lambda x: x
            )
            
            if selected:
                uniprot_id = selected.split(' - ')[0]
                protein = query.get_protein(uniprot_id)
                if protein:
                    st.write(f"### {protein['name']} ({protein['uniprot_id']})")
                    cols = st.columns(4)
                    cols[0].metric("Gene", protein.get('gene_symbol', 'N/A'))
                    cols[1].metric("Length", protein.get('length', 'N/A'))
                    cols[2].metric("Mass", f"{protein.get('mass', 0):.1f} Da")
                    
                    if protein.get('function'):
                        st.write("**Function:**", protein['function'])
                    if protein.get('subcellular_location'):
                        st.write("**Location:**", protein['subcellular_location'])
                    
                    # Interactions
                    st.write("#### Protein Interactions")
                    interactions = query.get_protein_interactions(uniprot_id, 30)
                    if interactions.count > 0:
                        df = pd.DataFrame(interactions.data)
                        st.dataframe(df[['protein_b', 'partner_name', 'partner_gene', 'interaction_type', 'confidence', 'source']], hide_index=True)
                    
                    # Domains
                    if protein.get('domains'):
                        st.write("#### Domains")
                        domains = json.loads(protein['domains'])
                        if domains:
                            df = pd.DataFrame(domains)
                            st.dataframe(df, hide_index=True)
        else:
            st.info("No proteins found")


def render_pathways_tab(query: KnowledgeQuery):
    """Render pathways tab."""
    st.subheader("Pathway Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        pathway_query = st.text_input("Pathway name", placeholder="e.g. PI3K-Akt, apoptosis")
    
    with col2:
        if st.button("Search Pathways", type="primary") and pathway_query:
            pass
    
    if pathway_query:
        pathways = query.search_pathways(pathway_query, 20)
        if pathways.count > 0:
            df = pd.DataFrame(pathways.data)
            st.dataframe(df[['pathway_id', 'source', 'name', 'category']], hide_index=True)
            
            # Select pathway for details
            selected = st.selectbox(
                "Select pathway for details",
                options=[f"{p['source']}: {p['name']}" for p in pathways.data],
                format_func=lambda x: x
            )
            
            if selected:
                parts = selected.split(': ', 1)
                source = parts[0]
                name = parts[1] if len(parts) > 1 else ""
                
                pathway = query.get_pathway(name, source)
                if pathway:
                    st.write(f"### {pathway['name']} ({pathway['source']})")
                    st.write(f"**Category:** {pathway.get('category', 'N/A')}")
                    if pathway.get('description'):
                        st.write(f"**Description:** {pathway['description']}")
                    
                    # Genes
                    st.write("#### Genes in Pathway")
                    genes = query.get_pathway_genes(pathway['pathway_id'], source)
                    if genes:
                        # Get gene details
                        gene_data = []
                        for g in genes[:50]:
                            gene = query.get_gene(g)
                            if gene:
                                gene_data.append({"symbol": gene['symbol'], "name": gene.get('name', '')})
                        
                        if gene_data:
                            df = pd.DataFrame(gene_data)
                            st.dataframe(df, hide_index=True)
        else:
            st.info("No pathways found")


def render_literature_tab(query: KnowledgeQuery):
    """Render literature tab."""
    st.subheader("Literature Browser")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        lit_query = st.text_input("Search literature", placeholder="e.g. CRISPR, immunotherapy")
    
    with col2:
        if st.button("Search Papers", type="primary") and lit_query:
            pass
    
    if lit_query:
        papers = query.search_literature(lit_query, 20)
        if papers.count > 0:
            df = pd.DataFrame(papers.data)
            st.dataframe(df[['pmid', 'title', 'journal', 'year', 'authors']], hide_index=True)
            
            # Show abstract for selected
            selected = st.selectbox(
                "Select paper for abstract",
                options=[p['title'][:100] for p in papers.data],
                format_func=lambda x: x
            )
            
            if selected:
                paper = next(p for p in papers.data if p['title'][:100] == selected)
                st.write(f"**{paper['title']}**")
                st.write(f"PMID: {paper['pmid']} | {paper['journal']} | {paper['year']}")
                if paper.get('abstract'):
                    st.write("**Abstract:**")
                    st.write(paper['abstract'])
        else:
            st.info("No papers found")


def render():
    """Main render function."""
    render_unified_knowledge_dashboard()


if __name__ == "__main__":
    render()