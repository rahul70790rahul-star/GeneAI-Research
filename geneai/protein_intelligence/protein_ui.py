"""Streamlit UI for Protein Intelligence Engine."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from geneai.protein_intelligence import (
    analyze_protein_sequence,
    retrieve_structure,
    analyze_structure,
    predict_function,
    get_interactions,
    build_network,
)
from geneai.protein_intelligence.visualization import (
    ProteinVisualizer,
    create_3d_structure_view,
    create_sequence_feature_plot,
    create_interaction_network_plot,
    create_conservation_heatmap,
)


def render_protein_intelligence_dashboard() -> None:
    """Render the Protein Intelligence Engine dashboard."""
    st.set_page_config(page_title="Protein Intelligence", layout="wide")
    
    st.title("🧬 Protein Intelligence Engine")
    st.markdown("""
    Advanced protein research engine for sequence analysis, structure retrieval,
    function prediction, interaction networks, and 3D visualization.
    """)
    
    # Sidebar navigation
    with st.sidebar:
        st.header("Analysis Modules")
        module = st.radio(
            "Select Module",
            [
                "Sequence Analysis",
                "Structure Retrieval",
                "Structure Analysis",
                "Function Prediction",
                "Interaction Network",
                "3D Visualization",
            ],
            label_visibility="collapsed",
        )
        
        st.divider()
        st.caption("Data Sources")
        st.caption("• UniProt for annotations")
        st.caption("• AlphaFold DB for predictions")
        st.caption("• RCSB PDB for experimental structures")
        st.caption("• STRING for interactions")
        st.caption("• Reactome/KEGG for pathways")
        st.caption("• Pfam/InterPro for domains")
    
    # Module content
    if module == "Sequence Analysis":
        render_sequence_analysis()
    elif module == "Structure Retrieval":
        render_structure_retrieval()
    elif module == "Structure Analysis":
        render_structure_analysis()
    elif module == "Function Prediction":
        render_function_prediction()
    elif module == "Interaction Network":
        render_interaction_network()
    elif module == "3D Visualization":
        render_3d_visualization()


def render_sequence_analysis() -> None:
    """Render protein sequence analysis interface."""
    st.subheader("Protein Sequence Analysis")
    st.write("Analyze protein sequences for physicochemical properties, domains, motifs, and features.")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        uploaded = st.file_uploader(
            "Upload FASTA",
            type=["fa", "fasta", "faa", "txt"],
        )
        
        raw = st.text_area(
            "Or paste protein sequence",
            height=200,
            placeholder=">sp|P04637|TP53_HUMAN\nMEEPQSDPSVEPPLSQETFSDLWKLLPENNVLSPLPSQAMDDLMLSPDDIEQWFTEDPGPDEAPRMPEAAPPVAPAPAAPTPAAPAPAPSWPLSSSVPSQKTYQGSYGFRLGFLHSGTAKSVTCTYSPALNKMFCQLAKTCPVQLWVDSTPPPGTRVRAMAIYKQSQHMTEVVRRCPHHERCSDSDGLAPPQHLIRVEGNLRVEYLDDRNTFRHSVVVPYEPPEVGSDCTTIHYNYMCNSSCMGGMNRRPILTIITLEDSSGNLLGRNSFEVRVCACPGRDRRTEEENLRKKGEPHHELPPGSTKRALPNNTSSSPQPKKKPLDGEYFTLQIRGRERFEMFRELNEALELKDAQAGKEPGGSRAHSSHLKSKKGQSTSRHKKLMFKTEGPDSD",
        )
        
        analyze_btn = st.button("Analyze Sequence", type="primary")
    
    with col2:
        if analyze_btn:
            sequence = ""
            if uploaded:
                content = uploaded.getvalue().decode("utf-8")
                lines = content.strip().split("\n")
                sequence = "".join(l for l in lines if not l.startswith(">"))
            elif raw:
                lines = raw.strip().split("\n")
                sequence = "".join(l for l in lines if not l.startswith(">"))
            
            if sequence:
                with st.spinner("Analyzing protein sequence..."):
                    features = analyze_protein_sequence(sequence)
                
                display_protein_features(features, sequence)
            else:
                st.warning("Please provide a protein sequence")


def display_protein_features(features, sequence: str) -> None:
    """Display protein analysis results."""
    st.subheader("Analysis Results")
    
    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Length", f"{features.length:,} aa")
    m2.metric("Molecular Weight", f"{features.molecular_weight:,.0f} Da")
    m3.metric("pI", f"{features.isoelectric_point:.2f}" if features.isoelectric_point else "N/A")
    m4.metric("GRAVY", f"{features.hydrophobicity:.2f}" if features.hydrophobicity else "N/A")
    
    m5, m6, m7, m8 = st.columns(4)
    if features.instability_index is not None:
        m5.metric("Instability Index", f"{features.instability_index:.1f}")
    if features.aromaticity is not None:
        m6.metric("Aromaticity", f"{features.aromaticity:.3f}")
    if features.aliphatic_index is not None:
        m7.metric("Aliphatic Index", f"{features.aliphatic_index:.1f}")
    if features.charge_at_pH7 is not None:
        m8.metric("Charge at pH 7", f"{features.charge_at_pH7:.1f}")
    
    # Secondary structure
    if features.secondary_structure_fraction:
        with st.expander("Secondary Structure Prediction"):
            ss = features.secondary_structure_fraction
            st.write(f"Helix: {ss[0]:.1%}")
            st.write(f"Sheet: {ss[1]:.1%}")
            st.write(f"Coil: {ss[2]:.1%}")
    
    # Composition
    if features.composition:
        with st.expander("Amino Acid Composition"):
            comp_df = pd.DataFrame([
                {"Residue": k, "Percentage": f"{v:.1f}%"} 
                for k, v in sorted(features.composition.items(), key=lambda x: -x[1])
            ])
            st.dataframe(comp_df, hide_index=True)
            
            # Bar chart
            fig = go.Figure(go.Bar(
                x=list(features.composition.keys()),
                y=list(features.composition.values()),
                marker_color="#1f77b4",
            ))
            fig.update_layout(
                title="Amino Acid Composition",
                xaxis_title="Residue",
                yaxis_title="Percentage (%)",
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Domains
    if features.domains:
        with st.expander(f"Predicted Domains ({len(features.domains)})"):
            dom_df = pd.DataFrame([
                {
                    "Domain": d["domain"],
                    "Start": d["start"],
                    "End": d["end"],
                    "Sequence": d["sequence"],
                }
                for d in features.domains
            ])
            st.dataframe(dom_df, hide_index=True)
    
    # Motifs
    if features.motifs:
        with st.expander(f"Motifs ({len(features.motifs)})"):
            motif_df = pd.DataFrame([
                {
                    "Motif": m["motif"],
                    "Start": m["start"],
                    "End": m["end"],
                    "Sequence": m["sequence"],
                }
                for m in features.motifs
            ])
            st.dataframe(motif_df, hide_index=True)
    
    # Signal peptide
    if features.signal_peptide:
        with st.expander("Signal Peptide Prediction"):
            sp = features.signal_peptide
            if sp.get("predicted"):
                st.success("Signal peptide predicted")
                st.write(f"Cleavage site: ~{sp.get('cleavage_site', '?')}")
                st.write(f"N-region charge: {sp.get('n_region_charge', '?')}")
                st.write(f"H-region hydrophobicity: {sp.get('h_region_hydrophobicity', '?')}")
            else:
                st.info("No signal peptide predicted")
    
    # Transmembrane regions
    if features.transmembrane_regions:
        with st.expander(f"Transmembrane Regions ({len(features.transmembrane_regions)})"):
            tm_df = pd.DataFrame([
                {
                    "Start": r["start"],
                    "End": r["end"],
                    "Length": r["length"],
                    "Avg Hydropathy": f"{r['avg_hydropathy']:.2f}",
                    "Sequence": r["sequence"][:30] + "..." if len(r["sequence"]) > 30 else r["sequence"],
                }
                for r in features.transmembrane_regions
            ])
            st.dataframe(tm_df, hide_index=True)
    
    # PTM sites
    for ptm_type, sites, label in [
        ("glycosylation_sites", features.glycosylation_sites, "Glycosylation Sites"),
        ("phosphorylation_sites", features.phosphorylation_sites, "Phosphorylation Sites"),
        ("active_sites", features.active_sites, "Predicted Active Sites"),
        ("binding_sites", features.binding_sites, "Predicted Binding Sites"),
    ]:
        if sites:
            with st.expander(f"{label} ({len(sites)})"):
                ptm_df = pd.DataFrame([
                    {
                        "Type": s.get("type", s.get("modification", "")),
                        "Position": s.get("position", s.get("asn_position", "")),
                        "Sequence": s.get("sequence", ""),
                        "Kinase": s.get("kinase", ""),
                        "Residue": s.get("residue", ""),
                    }
                    for s in sites
                ])
                st.dataframe(ptm_df, hide_index=True)


def render_structure_retrieval() -> None:
    """Render structure retrieval interface."""
    st.subheader("Protein Structure Retrieval")
    st.write("Retrieve 3D structures from AlphaFold DB and RCSB PDB.")
    
    tab1, tab2, tab3 = st.tabs(["By UniProt ID", "By PDB ID", "Best Available"])
    
    with tab1:
        uniprot_id = st.text_input(
            "UniProt Accession",
            placeholder="P04637 (TP53)",
        )
        
        format_type = st.selectbox("Format", ["cif", "pdb"], key="af_format")
        
        if st.button("Retrieve from AlphaFold", type="primary") and uniprot_id:
            with st.spinner(f"Fetching AlphaFold structure for {uniprot_id}..."):
                structure = retrieve_structure(uniprot_id, source="alphafold")
            
            if structure:
                display_structure_info(structure)
            else:
                st.error(f"No AlphaFold structure found for {uniprot_id}")
    
    with tab2:
        pdb_id = st.text_input(
            "PDB ID",
            placeholder="1M17 (EGFR)",
        )
        
        format_type = st.selectbox("Format", ["cif", "pdb"], key="pdb_format")
        
        if st.button("Retrieve from PDB", type="primary") and pdb_id:
            with st.spinner(f"Fetching PDB structure {pdb_id}..."):
                structure = retrieve_structure(pdb_id, source="pdb")
            
            if structure:
                display_structure_info(structure)
            else:
                st.error(f"No PDB structure found for {pdb_id}")
    
    with tab3:
        uniprot_id = st.text_input(
            "UniProt Accession (Best Available)",
            placeholder="P04637",
        )
        
        prefer_experimental = st.checkbox("Prefer experimental structures", value=True)
        
        if st.button("Get Best Structure", type="primary") and uniprot_id:
            with st.spinner(f"Finding best structure for {uniprot_id}..."):
                structure = retrieve_structure(uniprot_id, source="auto", prefer_experimental=prefer_experimental)
            
            if structure:
                display_structure_info(structure)
            else:
                st.error(f"No structure found for {uniprot_id}")


def display_structure_info(structure) -> None:
    """Display structure information."""
    st.success(f"Structure retrieved: {structure.identifier} ({structure.source})")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Source", structure.source)
    col2.metric("Method", structure.method or "N/A")
    col3.metric("Resolution", f"{structure.resolution:.2f} Å" if structure.resolution else "N/A")
    
    if structure.title:
        st.write(f"**Title:** {structure.title}")
    if structure.organism:
        st.write(f"**Organism:** {structure.organism}")
    if structure.release_date:
        st.write(f"**Release Date:** {structure.release_date}")
    if structure.confidence_scores:
        st.write(f"**Confidence (pLDDT):** {len(structure.confidence_scores)} residues")
        # Show confidence distribution
        import numpy as np
        scores = structure.confidence_scores
        fig = go.Figure(go.Histogram(x=scores, nbinsx=20))
        fig.update_layout(title="pLDDT Distribution", height=200)
        st.plotly_chart(fig, use_container_width=True)
    
    if structure.chains:
        st.write(f"**Chains:** {len(structure.chains)}")
        chain_df = pd.DataFrame(structure.chains)
        st.dataframe(chain_df, hide_index=True)
    
    # Download buttons
    if structure.cif_content:
        st.download_button(
            "Download CIF",
            structure.cif_content,
            f"{structure.identifier}.cif",
            "chemical/x-cif",
        )
    if structure.pdb_content:
        st.download_button(
            "Download PDB",
            structure.pdb_content,
            f"{structure.identifier}.pdb",
            "chemical/x-pdb",
        )


def render_structure_analysis() -> None:
    """Render structure analysis interface."""
    st.subheader("Structure Analysis")
    st.write("Analyze 3D protein structures for pockets, surface properties, and quality.")
    
    st.info("Upload a CIF/PDB file or retrieve a structure first")
    
    uploaded = st.file_uploader(
        "Upload Structure File",
        type=["cif", "pdb"],
    )
    
    if uploaded:
        # Create a minimal structure object
        content = uploaded.getvalue().decode("utf-8")
        
        class SimpleStructure:
            def __init__(self, content, fmt):
                self.cif_content = content if fmt == "cif" else None
                self.pdb_content = content if fmt == "pdb" else None
                self.identifier = uploaded.name
                self.source = "upload"
        
        fmt = "cif" if uploaded.name.endswith(".cif") else "pdb"
        structure = SimpleStructure(content, fmt)
        
        if st.button("Analyze Structure", type="primary"):
            with st.spinner("Analyzing structure..."):
                analysis = analyze_structure(structure)
            
            display_structure_analysis(analysis)


def display_structure_analysis(analysis) -> None:
    """Display structure analysis results."""
    st.subheader("Structure Analysis Results")
    
    # Overview metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chains", analysis.chains)
    m2.metric("Residues", analysis.residues)
    m3.metric("Atoms", analysis.atoms)
    m4.metric("Pockets", len(analysis.binding_pockets))
    
    # Secondary structure
    if analysis.secondary_structure:
        with st.expander("Secondary Structure"):
            ss = analysis.secondary_structure
            ss_df = pd.DataFrame([
                {"Type": k, "Count": v} for k, v in ss.items()
            ])
            st.dataframe(ss_df, hide_index=True)
            
            fig = go.Figure(go.Pie(
                labels=list(ss.keys()),
                values=list(ss.values()),
            ))
            st.plotly_chart(fig, use_container_width=True)
    
    # Binding pockets
    if analysis.binding_pockets:
        with st.expander(f"Binding Pockets ({len(analysis.binding_pockets)})"):
            for pocket in analysis.binding_pockets:
                st.write(f"**Pocket {pocket.pocket_id}**")
                st.write(f"Center: ({pocket.center['x']:.1f}, {pocket.center['y']:.1f}, {pocket.center['z']:.1f})")
                st.write(f"Volume: {pocket.volume:.0f} Å³")
                st.write(f"Druggability Score: {pocket.druggability_score:.2f}")
                st.write(f"Residues: {len(pocket.residues)}")
                
                if pocket.residues:
                    res_df = pd.DataFrame([
                        {
                            "Chain": r["chain"],
                            "Residue": f"{r['residue_name']}{r['residue_num']}",
                        }
                        for r in pocket.residues[:20]
                    ])
                    st.dataframe(res_df, hide_index=True)
    
    # Surface properties
    if analysis.surface_properties:
        with st.expander("Surface Properties"):
            sp = analysis.surface_properties
            sp_df = pd.DataFrame([
                {"Property": k, "Value": f"{v:.3f}" if isinstance(v, float) else v}
                for k, v in sp.items()
            ])
            st.dataframe(sp_df, hide_index=True)
    
    # Quality metrics
    if analysis.quality_metrics:
        with st.expander("Quality Metrics"):
            qm = analysis.quality_metrics
            qm_df = pd.DataFrame([
                {"Metric": k, "Value": f"{v:.2f}" if isinstance(v, float) else v}
                for k, v in qm.items()
            ])
            st.dataframe(qm_df, hide_index=True)


def render_function_prediction() -> None:
    """Render function prediction interface."""
    st.subheader("Protein Function Prediction")
    st.write("Predict GO terms, EC numbers, pathways, domains, and interactions.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        uniprot_id = st.text_input("UniProt ID", placeholder="P04637")
        gene_symbol = st.text_input("Gene Symbol", placeholder="TP53")
        sequence = st.text_area("Sequence (optional)", height=100)
    
    with col2:
        st.write("**Prediction Options**")
        include_go = st.checkbox("GO Annotations", True)
        include_ec = st.checkbox("EC Numbers", True)
        include_pathways = st.checkbox("Pathways", True)
        include_domains = st.checkbox("Domains", True)
        include_interactions = st.checkbox("Interactions", False)
        include_localization = st.checkbox("Localization", False)
    
    if st.button("Predict Function", type="primary") and (uniprot_id or gene_symbol or sequence):
        with st.spinner("Predicting protein function..."):
            prediction = predict_function(
                sequence=sequence if sequence else None,
                uniprot_id=uniprot_id if uniprot_id else None,
                gene_symbol=gene_symbol if gene_symbol else None,
            )
        
        display_function_prediction(prediction)


def display_function_prediction(prediction) -> None:
    """Display function prediction results."""
    st.subheader("Function Prediction Results")
    
    if prediction.uniprot_id:
        st.write(f"**UniProt:** {prediction.uniprot_id}")
    if prediction.gene_symbol:
        st.write(f"**Gene:** {prediction.gene_symbol}")
    
    st.metric("Overall Confidence", f"{prediction.overall_confidence:.1%}")
    
    # GO terms
    if prediction.go_biological_process:
        with st.expander(f"GO Biological Process ({len(prediction.go_biological_process)})"):
            go_df = pd.DataFrame(prediction.go_biological_process)
            st.dataframe(go_df, hide_index=True)
    
    if prediction.go_molecular_function:
        with st.expander(f"GO Molecular Function ({len(prediction.go_molecular_function)})"):
            go_df = pd.DataFrame(prediction.go_molecular_function)
            st.dataframe(go_df, hide_index=True)
    
    if prediction.go_cellular_component:
        with st.expander(f"GO Cellular Component ({len(prediction.go_cellular_component)})"):
            go_df = pd.DataFrame(prediction.go_cellular_component)
            st.dataframe(go_df, hide_index=True)
    
    # EC numbers
    if prediction.ec_numbers:
        with st.expander("EC Numbers"):
            for ec in prediction.ec_numbers:
                st.write(f"- {ec}")
    
    # Pathways
    if prediction.reactome_pathways:
        with st.expander(f"Reactome Pathways ({len(prediction.reactome_pathways)})"):
            pw_df = pd.DataFrame(prediction.reactome_pathways)
            st.dataframe(pw_df, hide_index=True)
    
    if prediction.kegg_pathways:
        with st.expander(f"KEGG Pathways ({len(prediction.kegg_pathways)})"):
            pw_df = pd.DataFrame(prediction.kegg_pathways)
            st.dataframe(pw_df, hide_index=True)
    
    # Domains
    if prediction.pfam_domains:
        with st.expander(f"Pfam Domains ({len(prediction.pfam_domains)})"):
            dom_df = pd.DataFrame(prediction.pfam_domains)
            st.dataframe(dom_df, hide_index=True)
    
    # Interactions
    if prediction.string_interactions:
        with st.expander(f"STRING Interactions ({len(prediction.string_interactions)})"):
            int_df = pd.DataFrame(prediction.string_interactions)
            st.dataframe(int_df, hide_index=True)


def render_interaction_network() -> None:
    """Render interaction network interface."""
    st.subheader("Protein Interaction Network")
    st.write("Explore protein-protein interaction networks from STRING and BioGRID.")
    
    tab1, tab2 = st.tabs(["Network Builder", "Common Interactors"])
    
    with tab1:
        center_protein = st.text_input(
            "Center Protein (UniProt ID or Gene Symbol)",
            placeholder="TP53 or P04637",
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            min_score = st.slider("Min Score", 0.0, 1.0, 0.4, 0.1)
        with col2:
            max_interactions = st.number_input("Max Interactions", 10, 500, 50)
        with col3:
            include_second = st.checkbox("Include 2nd neighbors", False)
        
        if st.button("Build Network", type="primary") and center_protein:
            with st.spinner("Building interaction network..."):
                network = build_network(
                    center_protein=center_protein,
                    min_score=min_score,
                )
            
            display_interaction_network(network)
    
    with tab2:
        protein_list = st.text_area(
            "Protein List (one per line)",
            placeholder="TP53\nMDM2\nCDKN1A\nBAX\nBBC3",
        )
        
        if st.button("Find Common Interactors", type="primary") and protein_list:
            proteins = [p.strip() for p in protein_list.split("\n") if p.strip()]
            
            with st.spinner("Finding common interactors..."):
                # Would call find_common_interactors
                st.info("Common interactor analysis requires STRING API integration")


def display_interaction_network(network) -> None:
    """Display interaction network."""
    st.subheader(f"Network: {network.center_protein}")
    
    # Network stats
    if network.network_stats:
        stats = network.network_stats
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Nodes", stats.get("num_nodes", 0))
        m2.metric("Edges", stats.get("num_edges", 0))
        m3.metric("Avg Degree", f"{stats.get('avg_degree', 0):.1f}")
        m4.metric("Density", f"{stats.get('density', 0):.3f}")
    
    # Interactions table
    if network.interactions:
        int_df = pd.DataFrame([
            {
                "Protein A": i.protein_a,
                "Protein B": i.protein_b,
                "Score": f"{i.score:.2f}",
                "Source": i.source,
                "Evidence": ", ".join(i.evidence_types),
            }
            for i in network.interactions
        ])
        st.dataframe(int_df, hide_index=True)
        
        # Network plot
        fig = create_interaction_network_plot(
            [
                {
                    "protein_a": i.protein_a,
                    "protein_b": i.protein_b,
                    "score": i.score,
                }
                for i in network.interactions
            ],
            center_protein=network.center_protein,
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Hubs
    if network.network_stats.get("hubs"):
        with st.expander("Hub Proteins"):
            hub_df = pd.DataFrame(network.network_stats["hubs"])
            st.dataframe(hub_df, hide_index=True)


def render_3d_visualization() -> None:
    """Render 3D structure visualization interface."""
    st.subheader("3D Protein Visualization")
    st.write("Interactive 3D structure viewer with multiple representations.")
    
    st.info("Retrieve a structure first from the Structure Retrieval module")
    
    # Demo with a simple structure
    st.write("**Demo: Load a structure to visualize**")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        representation = st.selectbox(
            "Representation",
            ["cartoon", "surface", "sphere", "stick", "line"],
        )
        
        color_scheme = st.selectbox(
            "Color Scheme",
            ["element", "chain", "residue", "b_factor", "hydrophobicity"],
        )
    
    with col2:
        st.write("3D viewer would appear here with structure data")
        st.write("Features:")
        st.write("- Rotate, zoom, pan")
        st.write("- Multiple representations")
        st.write("- Color by element, chain, residue, B-factor, hydrophobicity")
        st.write("- Highlight binding pockets, mutations, domains")
        st.write("- Export high-resolution images")


# Import networkx for interaction network plot
try:
    import networkx as nx
except ImportError:
    nx = None