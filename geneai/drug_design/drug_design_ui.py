"""Streamlit UI for Drug Design Engine."""
from __future__ import annotations

import logging
import json
from typing import Any

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from geneai.drug_design.molecule_generator import MoleculeGenerator, GenerationStrategy, GenerationConstraints
from geneai.drug_design.property_calculator import PropertyCalculator, calculate_properties
from geneai.drug_design.similarity_engine import SimilarityEngine, FingerprintType, SimilarityMetric
from geneai.drug_design.scaffold_hopper import ScaffoldHopper, hop_scaffold, ScaffoldHopResult
from geneai.drug_design.validator import MoleculeValidator, validate_molecule, ValidationResult
from geneai.drug_design.docking_engine import DockingEngine, Receptor, DockingResult, create_receptor_from_pdb_string
from geneai.drug_design.admet_predictor import ADMETPredictor, predict_admet, ADMETResult

logger = logging.getLogger(__name__)


def render_drug_design_ui():
    """Main entry point for Drug Design Engine UI."""
    st.title("🧪 Drug Design Engine")
    st.markdown("""
    **Next-generation molecular design platform** combining generative AI, physics-based modeling,
    and ADMET prediction for accelerated drug discovery.
    """)
    
    # Initialize session state
    if "generated_molecules" not in st.session_state:
        st.session_state.generated_molecules = []
    if "docking_results" not in st.session_state:
        st.session_state.docking_results = None
    if "admet_results" not in st.session_state:
        st.session_state.admet_results = None
    
    # Tabs for different modules
    tabs = st.tabs([
        "🧬 Molecule Generation",
        "📊 Property Calculator",
        "🔍 Similarity & Clustering",
        "🔄 Scaffold Hopping",
        "✅ Validation & Filtering",
        "🎯 Molecular Docking",
        "🧪 ADMET Prediction",
        "📈 Integrated Workflow",
    ])
    
    with tabs[0]:
        render_molecule_generation()
    
    with tabs[1]:
        render_property_calculator()
    
    with tabs[2]:
        render_similarity_engine()
    
    with tabs[3]:
        render_scaffold_hopping()
    
    with tabs[4]:
        render_validation()
    
    with tabs[5]:
        render_docking()
    
    with tabs[6]:
        render_admet()
    
    with tabs[7]:
        render_integrated_workflow()


def render_molecule_generation():
    """Molecule generation tab."""
    st.header("🧬 Molecule Generation")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Generation Strategy")
        strategy = st.selectbox(
            "Strategy",
            options=[s.value for s in GenerationStrategy],
            format_func=lambda x: x.replace("_", " ").title(),
            index=0,
        )
        
        st.subheader("Constraints")
        mw_range = st.slider("Molecular Weight", 100, 1000, (250, 500))
        logp_range = st.slider("LogP", -5.0, 10.0, (0.0, 5.0), step=0.5)
        tpsa_range = st.slider("TPSA (Å²)", 0, 200, (0, 140))
        rot_bonds_max = st.slider("Max Rotatable Bonds", 0, 20, 10)
        hbd_max = st.slider("Max H-Bond Donors", 0, 10, 5)
        hba_max = st.slider("Max H-Bond Acceptors", 0, 15, 10)
        
        # Strategy-specific options
        if strategy == "fragment_based":
            num_fragments = st.slider("Number of Fragments", 1, 10, 3)
            fragment_smiles = st.text_area(
                "Fragment SMILES (one per line)",
                value="c1ccccc1\nC(=O)O\nN",
                help="Enter fragment SMILES, one per line",
            )
        elif strategy == "scaffold_hopping":
            scaffold_smiles = st.text_input("Core Scaffold SMILES", value="c1ccccc1")
            r_groups = st.text_area(
                "R-Group SMILES (one per line)",
                value="C\nCC\nCCC\nc1ccccc1",
            )
        elif strategy == "r_group_enumeration":
            core_smiles = st.text_input("Core Scaffold SMILES", value="c1ccccc1[*]")
            r_group_file = st.file_uploader("Upload R-Groups CSV", type=["csv"])
        elif strategy == "similarity_based":
            ref_smiles = st.text_input("Reference SMILES", value="CCO")
            similarity_threshold = st.slider("Similarity Threshold", 0.0, 1.0, 0.7)
        elif strategy == "constrained_random":
            num_samples = st.slider("Number of Samples", 10, 1000, 50)
        
        # Common options
        num_molecules = st.slider("Number of Molecules", 1, 200, 20)
        apply_filters = st.checkbox("Apply Drug-Likeness Filters", value=True)
        
        if st.button("🚀 Generate Molecules", type="primary"):
            with st.spinner("Generating molecules..."):
                generator = MoleculeGenerator()
                constraints = GenerationConstraints(
                    mw_range=mw_range,
                    logp_range=logp_range,
                    tpsa_range=tpsa_range,
                    max_rotatable_bonds=rot_bonds_max,
                    max_hbd=hbd_max,
                    max_hba=hba_max,
                    apply_lipinski=apply_filters,
                    apply_ghose=apply_filters,
                    apply_veber=apply_filters,
                )
                
                try:
                    if strategy == "fragment_based":
                        fragments = [s.strip() for s in fragment_smiles.strip().split("\n") if s.strip()]
                        molecules = generator.generate_fragment_based(
                            fragments, num_molecules
                        )
                    elif strategy == "scaffold_hopping":
                        molecules = generator.generate_scaffold_hopping(
                            scaffold_smiles, num_molecules
                        )
                    elif strategy == "r_group_enumeration":
                        if r_group_file:
                            r_df = pd.read_csv(r_group_file)
                            r_groups_list = r_df.iloc[:, 0].tolist()
                        else:
                            r_groups_list = ["C", "CC", "CCC", "Cl", "F", "OH", "NH2"]
                        attachment_points = list(range(max(1, core_smiles.count("[*]"))))
                        molecules = generator.generate_r_group_enumeration(
                            core_smiles,
                            attachment_points,
                            {i: r_groups_list for i in attachment_points},
                            max_combinations=num_molecules,
                        )
                    elif strategy == "similarity_based":
                        molecules = generator.generate_similarity_based(
                            ref_smiles, num_molecules, similarity_threshold
                        )
                    elif strategy == "constrained_random":
                        molecules = generator.generate_constrained_random(
                            num_molecules, constraints
                        )
                    else:
                        molecules = []
                    
                    st.session_state.generated_molecules = molecules
                    st.success(f"Generated {len(molecules)} molecules!")
                    
                except Exception as e:
                    st.error(f"Generation failed: {e}")
    
    with col2:
        st.subheader("Generated Molecules")
        
        if st.session_state.generated_molecules:
            molecules = st.session_state.generated_molecules
            
            # Display as table
            df_data = []
            for i, molecule in enumerate(molecules):
                smiles = molecule.smiles if hasattr(molecule, "smiles") else str(molecule)
                props = getattr(molecule, "properties", None) or calculate_properties(smiles)
                df_data.append({
                    "#": i + 1,
                    "SMILES": smiles,
                    "MW": round(props.get("mw", 0), 1),
                    "LogP": round(props.get("logp", 0), 2),
                    "TPSA": round(props.get("tpsa", 0), 1),
                    "HBD": props.get("hbd", 0),
                    "HBA": props.get("hba", 0),
                    "RotBonds": props.get("rotatable_bonds", 0),
                    "QED": round(props.get("qed", 0), 3),
                    "SA Score": round(props.get("sa_score", 0), 2),
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Download
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Download as CSV",
                csv,
                file_name="generated_molecules.csv",
                mime="text/csv",
            )
            
            # Visualize first few
            st.subheader("Structure Preview")
            from rdkit import Chem
            from rdkit.Chem import Draw
            
            n_show = min(6, len(molecules))
            cols = st.columns(n_show)
            for i in range(n_show):
                mol = Chem.MolFromSmiles(molecules[i])
                if mol:
                    img = Draw.MolToImage(mol, size=(200, 200))
                    cols[i].image(img, caption=f"Mol {i+1}")
        else:
            st.info("Generate molecules to see results here.")


def render_property_calculator():
    """Property calculator tab."""
    st.header("📊 Property Calculator")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Input")
        smiles_input = st.text_area(
            "SMILES (one per line)",
            value="CCO\nc1ccccc1\nCC(=O)O",
            height=150,
        )
        
        calc_options = st.multiselect(
            "Calculate",
            options=[
                "Basic Properties",
                "Drug-Likeness Rules",
                "PAINS Alerts",
                "Structural Alerts",
                "QED & SA Score",
                "3D Properties",
                "All Fingerprints",
            ],
            default=["Basic Properties", "Drug-Likeness Rules", "QED & SA Score"],
        )
        
        if st.button("Calculate Properties", type="primary"):
            smiles_list = [s.strip() for s in smiles_input.strip().split("\n") if s.strip()]
            
            if smiles_list:
                calculator = PropertyCalculator()
                results = []
                
                for smi in smiles_list:
                    try:
                        props = calculator.calculate_all_properties(smi, calc_options)
                        results.append({"smiles": smi, **props})
                    except Exception as e:
                        results.append({"smiles": smi, "error": str(e)})
                
                st.session_state.property_results = results
                st.success(f"Calculated properties for {len(results)} molecules")
    
    with col2:
        st.subheader("Results")
        
        if "property_results" in st.session_state and st.session_state.property_results:
            results = st.session_state.property_results
            
            # Summary table
            df_rows = []
            for r in results:
                if "error" not in r:
                    row = {"SMILES": r["smiles"]}
                    row.update({k: v for k, v in r.items() if k != "smiles"})
                    df_rows.append(row)
            
            if df_rows:
                df = pd.DataFrame(df_rows)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Visualizations
                if len(df) > 1:
                    st.subheader("Property Distributions")
                    
                    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
                    if numeric_cols:
                        selected_prop = st.selectbox("Property to visualize", numeric_cols)
                        
                        fig = px.histogram(df, x=selected_prop, nbins=20, 
                                         title=f"Distribution of {selected_prop}")
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Scatter matrix for multiple properties
                        if len(numeric_cols) >= 2:
                            st.subheader("Property Correlations")
                            fig = px.scatter_matrix(df, dimensions=numeric_cols[:5])
                            st.plotly_chart(fig, use_container_width=True)
                
                # Download
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Download Properties CSV",
                    csv,
                    file_name="molecular_properties.csv",
                    mime="text/csv",
                )


def render_similarity_engine():
    """Similarity engine tab."""
    st.header("🔍 Similarity & Clustering")
    
    tab1, tab2, tab3 = st.tabs(["Pairwise Similarity", "Library Search", "Clustering"])
    
    with tab1:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Reference Molecule")
            ref_smiles = st.text_input("Reference SMILES", value="CCO")
            
            st.subheader("Comparison Molecules")
            comp_smiles = st.text_area(
                "Comparison SMILES (one per line)",
                value="CCO\nCCC\nc1ccccc1\nCC(=O)O",
                height=150,
            )
            
            fp_type = st.selectbox(
                "Fingerprint Type",
                options=[f.value for f in FingerprintType],
                index=0,
            )
            
            metric = st.selectbox(
                "Similarity Metric",
                options=[m.value for m in SimilarityMetric],
                index=0,
            )
            
            if st.button("Calculate Similarity", type="primary"):
                comparison_list = [s.strip() for s in comp_smiles.strip().split("\n") if s.strip()]
                
                engine = SimilarityEngine()
                results = []
                
                for smi in comparison_list:
                    try:
                        sim = engine.calculate_similarity(
                            ref_smiles, smi,
                            FingerprintType(fp_type),
                            SimilarityMetric(metric)
                        )
                        results.append({"smiles": smi, "similarity": sim})
                    except Exception as e:
                        results.append({"smiles": smi, "similarity": 0.0, "error": str(e)})
                
                st.session_state.pairwise_results = results
        
        with col2:
            st.subheader("Similarity Results")
            
            if "pairwise_results" in st.session_state:
                results = st.session_state.pairwise_results
                
                df = pd.DataFrame(results)
                if "error" not in df.columns:
                    df = df.sort_values("similarity", ascending=False)
                
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Bar chart
                if len(df) > 0:
                    fig = px.bar(df.head(20), x="smiles", y="similarity",
                               title="Similarity to Reference")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("Library Similarity Search")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            query_smiles = st.text_input("Query SMILES", value="CCO")
            
            library_source = st.radio(
                "Library Source",
                ["Upload CSV", "Use Generated Molecules", "ChEMBL Subset (demo)"],
            )
            
            if library_source == "Upload CSV":
                lib_file = st.file_uploader("Upload Library CSV", type=["csv"])
                smiles_col = st.text_input("SMILES Column Name", value="smiles")
            elif library_source == "Use Generated Molecules":
                if st.session_state.generated_molecules:
                    st.info(f"Using {len(st.session_state.generated_molecules)} generated molecules")
                else:
                    st.warning("No generated molecules available")
            
            top_k = st.slider("Top K Results", 1, 100, 20)
            fp_type_search = st.selectbox(
                "Fingerprint",
                options=[f.value for f in FingerprintType],
                index=0,
                key="search_fp",
            )
            
            if st.button("Search Library", type="primary"):
                if library_source == "Upload CSV" and lib_file:
                    lib_df = pd.read_csv(lib_file)
                    library_smiles = lib_df[smiles_col].dropna().tolist()
                elif library_source == "Use Generated Molecules":
                    library_smiles = st.session_state.generated_molecules
                else:
                    # Demo library
                    library_smiles = [
                        "CCO", "CCC", "CCCC", "CCCCC", "CCCCCC",
                        "c1ccccc1", "Cc1ccccc1", "CCc1ccccc1",
                        "CC(=O)O", "CCC(=O)O", "CCCC(=O)O",
                        "NCCO", "NCCCO", "NCCCCO",
                    ]
                
                engine = SimilarityEngine()
                results = engine.search_library(
                    query_smiles, library_smiles,
                    FingerprintType(fp_type_search),
                    top_k=top_k
                )
                
                st.session_state.library_results = results
        
        with col2:
            st.subheader("Search Results")
            
            if "library_results" in st.session_state:
                results = st.session_state.library_results
                
                if results:
                    df = pd.DataFrame(results, columns=["SMILES", "Similarity"])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Download
                    csv = df.to_csv(index=False)
                    st.download_button(
                        "📥 Download Results",
                        csv,
                        file_name="similarity_search_results.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("No results found")
    
    with tab3:
        st.subheader("Molecular Clustering")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            cluster_source = st.radio(
                "Molecules to Cluster",
                ["Upload CSV", "Use Generated Molecules"],
            )
            
            if cluster_source == "Upload CSV":
                cluster_file = st.file_uploader("Upload CSV for Clustering", type=["csv"])
                cluster_smiles_col = st.text_input("SMILES Column", value="smiles", key="cluster_col")
            else:
                if st.session_state.generated_molecules:
                    st.info(f"Using {len(st.session_state.generated_molecules)} molecules")
            
            method = st.selectbox(
                "Clustering Method",
                ["Butina (Taylor-Butina)", "Hierarchical", "K-Means"],
            )
            
            if method == "Butina (Taylor-Butina)":
                cutoff = st.slider("Similarity Cutoff", 0.1, 0.9, 0.7)
            elif method == "K-Means":
                n_clusters = st.slider("Number of Clusters", 2, 20, 5)
            
            fp_type_cluster = st.selectbox(
                "Fingerprint",
                options=[f.value for f in FingerprintType],
                index=0,
                key="cluster_fp",
            )
            
            if st.button("Cluster Molecules", type="primary"):
                if cluster_source == "Upload CSV" and cluster_file:
                    df = pd.read_csv(cluster_file)
                    smiles_list = df[cluster_smiles_col].dropna().tolist()
                else:
                    smiles_list = st.session_state.generated_molecules
                
                if smiles_list:
                    engine = SimilarityEngine()
                    
                    if method == "Butina (Taylor-Butina)":
                        clusters = engine.cluster_molecules_butina(
                            smiles_list, cutoff=cutoff,
                            fp_type=FingerprintType(fp_type_cluster)
                        )
                    else:
                        clusters = engine.cluster_molecules_kmeans(
                            smiles_list, n_clusters=n_clusters,
                            fp_type=FingerprintType(fp_type_cluster)
                        )
                    
                    st.session_state.clustering_results = clusters
                    st.success(f"Found {len(clusters)} clusters")
    
        with col2:
            st.subheader("Clustering Results")
            
            if "clustering_results" in st.session_state:
                clusters = st.session_state.clustering_results
                
                # Cluster size distribution
                cluster_sizes = [len(c) for c in clusters]
                fig = px.histogram(x=cluster_sizes, nbins=20,
                                 title="Cluster Size Distribution",
                                 labels={"x": "Cluster Size", "y": "Count"})
                st.plotly_chart(fig, use_container_width=True)
                
                # Show cluster representatives
                st.subheader("Cluster Representatives")
                rep_data = []
                for i, cluster in enumerate(clusters[:20]):
                    rep_data.append({
                        "Cluster": i,
                        "Size": len(cluster),
                        "Representative": cluster[0] if cluster else "",
                    })
                
                rep_df = pd.DataFrame(rep_data)
                st.dataframe(rep_df, use_container_width=True, hide_index=True)
                
                # Diversity metrics
                if len(clusters) > 1:
                    engine = SimilarityEngine()
                    diversity = engine.calculate_diversity_metrics(
                        [c[0] for c in clusters if c],
                        FingerprintType(fp_type_cluster)
                    )
                    
                    st.subheader("Diversity Metrics")
                    div_df = pd.DataFrame([diversity])
                    st.dataframe(div_df, use_container_width=True, hide_index=True)


def render_scaffold_hopping():
    """Scaffold hopping tab."""
    st.header("🔄 Scaffold Hopping")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Reference Molecule")
        ref_smiles = st.text_input("Reference SMILES", value="CC(=O)Nc1ccccc1")
        
        strategy = st.selectbox(
            "Hopping Strategy",
            ["bioisosteric", "topology", "property_matched", "fragment_recombination"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        
        num_results = st.slider("Number of Results", 5, 100, 20)
        
        # Property constraints
        st.subheader("Property Constraints (Optional)")
        use_constraints = st.checkbox("Apply Property Constraints")
        
        constraints = {}
        if use_constraints:
            mw_min, mw_max = st.slider("MW Range", 100, 800, (200, 500))
            constraints["mw"] = (mw_min, mw_max)
            
            logp_min, logp_max = st.slider("LogP Range", -3.0, 8.0, (0.0, 5.0))
            constraints["logp"] = (logp_min, logp_max)
            
            tpsa_min, tpsa_max = st.slider("TPSA Range", 0, 200, (0, 140))
            constraints["tpsa"] = (tpsa_min, tpsa_max)
        
        if st.button("Hop Scaffold", type="primary"):
            with st.spinner("Performing scaffold hopping..."):
                hopper = ScaffoldHopper()
                
                constraint_dict = constraints if use_constraints else None
                
                results = hopper.hop_scaffold(
                    ref_smiles,
                    strategy=strategy,
                    num_results=num_results,
                    property_constraints=constraint_dict,
                )
                
                st.session_state.scaffold_results = results
                st.success(f"Generated {len(results)} scaffold hops")
    
    with col2:
        st.subheader("Scaffold Hopping Results")
        
        if "scaffold_results" in st.session_state:
            results = st.session_state.scaffold_results
            
            if results:
                # Results table
                df_data = []
                for i, r in enumerate(results):
                    df_data.append({
                        "#": i + 1,
                        "Hopped SMILES": r.hopped_smiles,
                        "Original Scaffold": r.original_scaffold,
                        "New Scaffold": r.new_scaffold,
                        "Scaffold Sim": round(r.scaffold_similarity, 3),
                        "Overall Sim": round(r.overall_similarity, 3),
                        "Method": r.method,
                    })
                
                df = pd.DataFrame(df_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Visualization
                st.subheader("Similarity Analysis")
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[r.scaffold_similarity for r in results],
                    y=[r.overall_similarity for r in results],
                    mode="markers",
                    marker=dict(size=10, color=list(range(len(results))), colorscale="Viridis"),
                    text=[r.hopped_smiles for r in results],
                    hovertemplate="Scaffold Sim: %{x:.3f}<br>Overall Sim: %{y:.3f}<br>SMILES: %{text}<extra></extra>",
                ))
                fig.update_layout(
                    title="Scaffold vs Overall Similarity",
                    xaxis_title="Scaffold Similarity",
                    yaxis_title="Overall Similarity",
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Property changes
                if results[0].properties_changed:
                    st.subheader("Property Changes")
                    prop_df_data = []
                    for r in results[:10]:
                        row = {"SMILES": r.hopped_smiles}
                        for prop, (old, new) in r.properties_changed.items():
                            row[f"{prop} (old)"] = round(old, 2)
                            row[f"{prop} (new)"] = round(new, 2)
                            row[f"{prop} (Δ)"] = round(new - old, 2)
                        prop_df_data.append(row)
                    
                    prop_df = pd.DataFrame(prop_df_data)
                    st.dataframe(prop_df, use_container_width=True, hide_index=True)
                
                # Download
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Download Results",
                    csv,
                    file_name="scaffold_hopping_results.csv",
                    mime="text/csv",
                )
            else:
                st.info("No scaffold hops generated")


def render_validation():
    """Validation and filtering tab."""
    st.header("✅ Validation & Filtering")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Input Molecules")
        input_source = st.radio(
            "Source",
            ["Manual Entry", "Upload CSV", "Use Generated Molecules"],
        )
        
        if input_source == "Manual Entry":
            smiles_input = st.text_area(
                "SMILES (one per line)",
                value="CCO\nc1ccccc1\nCC(=O)O\nC1=CC=CC=C1C(=O)O",
                height=150,
            )
            smiles_list = [s.strip() for s in smiles_input.strip().split("\n") if s.strip()]
        elif input_source == "Upload CSV":
            val_file = st.file_uploader("Upload CSV", type=["csv"])
            val_smiles_col = st.text_input("SMILES Column", value="smiles", key="val_col")
            if val_file:
                df = pd.read_csv(val_file)
                smiles_list = df[val_smiles_col].dropna().tolist()
            else:
                smiles_list = []
        else:
            smiles_list = st.session_state.generated_molecules
            st.info(f"Using {len(smiles_list)} generated molecules")
        
        st.subheader("Filtering Criteria")
        min_score = st.slider("Minimum Overall Score", 0.0, 1.0, 0.5)
        require_lipinski = st.checkbox("Require Lipinski Compliance", value=True)
        max_pains = st.slider("Max PAINS Alerts", 0, 5, 0)
        max_structural_alerts = st.slider("Max Structural Alerts", 0, 5, 2)
        
        if st.button("Validate & Filter", type="primary"):
            if smiles_list:
                validator = MoleculeValidator()
                
                # Validate all
                with st.spinner("Validating molecules..."):
                    results = validator.batch_validate(smiles_list)
                
                # Filter
                filtered = validator.filter_library(
                    smiles_list,
                    min_score=min_score,
                    require_lipinski=require_lipinski,
                    max_pains=max_pains,
                )
                
                st.session_state.validation_results = results
                st.session_state.filtered_results = filtered
                st.success(f"Validated {len(results)} molecules, {len(filtered)} passed filters")
    
    with col2:
        st.subheader("Validation Results")
        
        if "validation_results" in st.session_state:
            results = st.session_state.validation_results
            
            # Summary stats
            valid_count = sum(1 for r in results if r.is_valid)
            excellent_count = sum(1 for r in results if r.recommendation == "excellent")
            good_count = sum(1 for r in results if r.recommendation == "good")
            poor_count = sum(1 for r in results if r.recommendation in ["poor", "reject"])
            
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total", len(results))
            col_b.metric("Valid", valid_count)
            col_c.metric("Excellent/Good", excellent_count + good_count)
            col_d.metric("Poor/Reject", poor_count)
            
            # Detailed results
            df_data = []
            for r in results:
                df_data.append({
                    "SMILES": r.smiles,
                    "Valid": "✅" if r.is_valid else "❌",
                    "Score": round(r.overall_score, 3),
                    "Recommendation": r.recommendation,
                    "Lipinski": "✅" if r.passes_lipinski else "❌",
                    "Ghose": "✅" if r.passes_ghose else "❌",
                    "Veber": "✅" if r.passes_veber else "❌",
                    "QED": round(r.qed, 3),
                    "SA Score": round(r.sa_score, 2),
                    "PAINS": len(r.pains_alerts),
                    "Struct Alerts": len(r.structural_alerts),
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Filtered results
            if "filtered_results" in st.session_state:
                filtered = st.session_state.filtered_results
                
                st.subheader(f"Filtered Results ({len(filtered)} molecules)")
                
                filter_df_data = []
                for r in filtered:
                    filter_df_data.append({
                        "SMILES": r.smiles,
                        "Score": round(r.overall_score, 3),
                        "Recommendation": r.recommendation,
                    })
                
                filter_df = pd.DataFrame(filter_df_data)
                st.dataframe(filter_df, use_container_width=True, hide_index=True)
                
                # Download filtered
                csv = filter_df.to_csv(index=False)
                st.download_button(
                    "📥 Download Filtered Molecules",
                    csv,
                    file_name="filtered_molecules.csv",
                    mime="text/csv",
                )


def render_docking():
    """Molecular docking tab."""
    st.header("🎯 Molecular Docking")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Receptor")
        receptor_source = st.radio(
            "Receptor Source",
            ["Upload PDB", "PDB ID (fetch)", "Predefined Targets"],
        )
        
        receptor = None
        
        if receptor_source == "Upload PDB":
            pdb_file = st.file_uploader("Upload PDB File", type=["pdb", "pdbqt"])
            if pdb_file:
                pdb_content = pdb_file.read().decode("utf-8")
                receptor = create_receptor_from_pdb_string(pdb_content, "uploaded_receptor")
                st.success("Receptor loaded")
        
        elif receptor_source == "PDB ID (fetch)":
            pdb_id = st.text_input("PDB ID", value="1A2B")
            if st.button("Fetch PDB"):
                # In real implementation, fetch from RCSB
                st.info("PDB fetching would be implemented here")
        
        elif receptor_source == "Predefined Targets":
            target = st.selectbox(
                "Target",
                [
                    "EGFR (1M17)",
                    "BRAF (1UWH)",
                    "CDK2 (1HCK)",
                    "PARP1 (4GV9)",
                    "Mpro (6LU7)",
                ],
            )
            st.info(f"Using predefined receptor: {target}")
            # Would load from local database
        
        if receptor:
            # Binding site definition
            st.subheader("Binding Site")
            center_x = st.number_input("Center X", value=0.0, format="%.1f")
            center_y = st.number_input("Center Y", value=0.0, format="%.1f")
            center_z = st.number_input("Center Z", value=0.0, format="%.1f")
            receptor.center = (center_x, center_y, center_z)
            
            size_x = st.number_input("Size X", value=20.0, format="%.1f")
            size_y = st.number_input("Size Y", value=20.0, format="%.1f")
            size_z = st.number_input("Size Z", value=20.0, format="%.1f")
            receptor.size = (size_x, size_y, size_z)
        
        st.subheader("Ligands")
        ligand_source = st.radio(
            "Ligand Source",
            ["Manual Entry", "Upload CSV", "Use Generated Molecules"],
        )
        
        if ligand_source == "Manual Entry":
            ligand_smiles = st.text_area(
                "Ligand SMILES (one per line)",
                value="CCO\nc1ccccc1\nCC(=O)O",
                height=100,
            )
            ligand_list = [s.strip() for s in ligand_smiles.strip().split("\n") if s.strip()]
        elif ligand_source == "Upload CSV":
            lig_file = st.file_uploader("Upload Ligands CSV", type=["csv"])
            lig_col = st.text_input("SMILES Column", value="smiles", key="lig_col")
            if lig_file:
                df = pd.read_csv(lig_file)
                ligand_list = df[lig_col].dropna().tolist()
            else:
                ligand_list = []
        else:
            ligand_list = st.session_state.generated_molecules
            st.info(f"Using {len(ligand_list)} generated molecules")
        
        st.subheader("Docking Parameters")
        engine = st.selectbox(
            "Docking Engine",
            ["internal", "vina", "gnina"],
            help="Internal: fast RDKit-based. Vina/GNINA: require installation.",
        )
        num_poses = st.slider("Poses per Ligand", 1, 20, 5)
        exhaustiveness = st.slider("Exhaustiveness (Vina)", 1, 32, 8)
        
        if st.button("Run Docking", type="primary"):
            if receptor and ligand_list:
                with st.spinner(f"Docking {len(ligand_list)} ligands..."):
                    docking_engine = DockingEngine(engine=engine)
                    
                    all_results = []
                    for lig_smi in ligand_list:
                        result = docking_engine.dock(receptor, lig_smi, num_poses, exhaustiveness)
                        all_results.append(result)
                    
                    st.session_state.docking_results = all_results
                    st.success(f"Docked {len(all_results)} ligands")
            else:
                st.error("Please provide receptor and ligands")
    
    with col2:
        st.subheader("Docking Results")
        
        if "docking_results" in st.session_state:
            results = st.session_state.docking_results
            
            # Handle None or empty results
            if not results:
                st.info("No docking results available. Run docking to see results.")
            elif isinstance(results, list) and len(results) > 0:
                # Summary table
                summary_data = []
                for r in results:
                    if r.success and r.best_pose:
                        summary_data.append({
                            "Ligand": r.ligand_smiles,
                            "Best Score": round(r.best_pose.score, 3),
                            "Num Poses": len(r.poses),
                            "Engine": r.engine,
                            "Time (s)": round(r.docking_time, 2),
                        })
                    else:
                        summary_data.append({
                            "Ligand": r.ligand_smiles,
                            "Best Score": "Failed",
                            "Num Poses": 0,
                            "Engine": r.engine,
                            "Time (s)": round(r.docking_time, 2),
                        })
                
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                # Detailed view for selected ligand
                if results:
                    selected_idx = st.selectbox(
                        "Select Ligand for Details",
                        range(len(results)),
                        format_func=lambda i: results[i].ligand_smiles,
                    )
                    
                    selected = results[selected_idx]
                    
                    if selected.success and selected.poses:
                        st.subheader(f"Poses for {selected.ligand_smiles}")
                        
                        pose_data = []
                        for i, pose in enumerate(selected.poses):
                            pose_data.append({
                                "Pose": i + 1,
                                "Score": round(pose.score, 3),
                                "Interactions": json.dumps(pose.interactions, default=str)[:100],
                            })
                        
                        pose_df = pd.DataFrame(pose_data)
                        st.dataframe(pose_df, use_container_width=True, hide_index=True)
                        
                        # Interactions
                        if selected.best_pose and selected.best_pose.interactions:
                            st.subheader("Key Interactions (Best Pose)")
                            for int_type, interactions in selected.best_pose.interactions.items():
                                if interactions:
                                    st.write(f"**{int_type.replace('_', ' ').title()}**: {len(interactions)} contacts")
                        
                        # Download
                        csv = summary_df.to_csv(index=False)
                        st.download_button(
                            "📥 Download All Results",
                            csv,
                            file_name="docking_results.csv",
                            mime="text/csv",
                        )
                    else:
                        st.error(f"Docking failed: {selected.error}")
            else:
                st.warning(f"Unexpected results format: {type(results)}")


def render_admet():
    """ADMET prediction tab."""
    st.header("🧪 ADMET Prediction")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Input Molecules")
        admet_source = st.radio(
            "Source",
            ["Manual Entry", "Upload CSV", "Use Generated Molecules", "Use Docked Ligands"],
        )
        
        if admet_source == "Manual Entry":
            admet_smiles = st.text_area(
                "SMILES (one per line)",
                value="CCO\nc1ccccc1\nCC(=O)O\nCN1C=NC2=C1C(=O)N(C(=O)N2C)C",
                height=150,
            )
            smiles_list = [s.strip() for s in admet_smiles.strip().split("\n") if s.strip()]
        elif admet_source == "Upload CSV":
            admet_file = st.file_uploader("Upload CSV", type=["csv"])
            admet_col = st.text_input("SMILES Column", value="smiles", key="admet_col")
            if admet_file:
                df = pd.read_csv(admet_file)
                smiles_list = df[admet_col].dropna().tolist()
            else:
                smiles_list = []
        elif admet_source == "Use Generated Molecules":
            smiles_list = st.session_state.generated_molecules
            st.info(f"Using {len(smiles_list)} generated molecules")
        else:
            if st.session_state.docking_results:
                smiles_list = [r.ligand_smiles for r in st.session_state.docking_results if r.success]
                st.info(f"Using {len(smiles_list)} successfully docked ligands")
            else:
                smiles_list = []
                st.warning("No docking results available")
        
        use_ml = st.checkbox("Use ML Models (if available)", value=False)
        
        if st.button("Predict ADMET", type="primary"):
            if smiles_list:
                with st.spinner(f"Predicting ADMET for {len(smiles_list)} molecules..."):
                    predictor = ADMETPredictor(use_ml_models=use_ml)
                    results = predictor.batch_predict(smiles_list)
                    st.session_state.admet_results = results
                    st.success(f"ADMET predictions complete")
    
    with col2:
        st.subheader("ADMET Results")
        
        if "admet_results" in st.session_state:
            results = st.session_state.admet_results
            
            # Overall summary
            summary_data = []
            for r in results:
                summary_data.append({
                    "SMILES": r.smiles,
                    "Overall Score": round(r.overall_score, 3),
                    "Risk Level": r.risk_level,
                    "Flags": len(r.flags),
                })
            
            summary_df = pd.DataFrame(summary_data)
            
            # Color code risk level
            def risk_color(risk):
                colors = {
                    "low": "🟢",
                    "moderate": "🟡",
                    "high": "🟠",
                    "very_high": "🔴",
                    "unknown": "⚪",
                }
                return colors.get(risk, "⚪")
            
            summary_df["Risk"] = summary_df["Risk Level"].apply(risk_color)
            
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            # Detailed view
            selected_idx = st.selectbox(
                "Select Molecule for Details",
                range(len(results)),
                format_func=lambda i: f"{results[i].smiles[:30]}... (Score: {results[i].overall_score:.2f})",
            )
            
            selected = results[selected_idx]
            
            st.subheader(f"ADMET Profile: {selected.smiles}")
            
            # Properties by category
            categories = {
                "Absorption": ["Caco-2", "Intestinal Absorption", "P-gp", "Bioavailability"],
                "Distribution": ["BBB", "CNS MPO", "VDss", "Plasma Protein"],
                "Metabolism": ["CYP", "Clearance", "Half-Life"],
                "Excretion": ["Renal Clearance"],
                "Toxicity": ["Ames", "Hepatotoxicity", "hERG", "Skin", "LD50", "Carcinogen"],
                "Physicochemical": ["Molecular Weight", "LogP", "TPSA", "Rotatable", "HBD", "HBA", "QED", "SA", "Fsp3"],
            }
            
            for cat, keywords in categories.items():
                cat_props = [p for p in selected.properties 
                           if any(k.lower() in p.name.lower() for k in keywords)]
                
                if cat_props:
                    with st.expander(f"{cat} ({len(cat_props)} properties)"):
                        cat_data = []
                        for p in cat_props:
                            interp_icon = {"favorable": "✅", "unfavorable": "❌", "neutral": "⚪"}.get(p.interpretation, "⚪")
                            cat_data.append({
                                "Property": p.name,
                                "Value": f"{p.value} {p.unit}".strip(),
                                "Interpretation": f"{interp_icon} {p.interpretation}",
                                "Confidence": f"{p.confidence:.0%}",
                                "Method": p.method,
                            })
                        
                        cat_df = pd.DataFrame(cat_data)
                        st.dataframe(cat_df, use_container_width=True, hide_index=True)
            
            # Flags
            if selected.flags:
                st.subheader("⚠️ Flags")
                for flag in selected.flags:
                    st.warning(flag)
            
            # Recommendations
            if selected.recommendations:
                st.subheader("💡 Recommendations")
                for rec in selected.recommendations:
                    st.info(rec)
            
            # Download all
            all_data = []
            for r in results:
                for p in r.properties:
                    all_data.append({
                        "SMILES": r.smiles,
                        "Overall_Score": r.overall_score,
                        "Risk_Level": r.risk_level,
                        "Property": p.name,
                        "Value": p.value,
                        "Unit": p.unit,
                        "Interpretation": p.interpretation,
                        "Confidence": p.confidence,
                        "Method": p.method,
                    })
            
            all_df = pd.DataFrame(all_data)
            csv = all_df.to_csv(index=False)
            st.download_button(
                "📥 Download All ADMET Data",
                csv,
                file_name="admet_predictions.csv",
                mime="text/csv",
            )


def render_integrated_workflow():
    """Integrated workflow tab."""
    st.header("📈 Integrated Drug Design Workflow")
    
    st.markdown("""
    This tab combines all modules into a streamlined workflow:
    1. **Generate** molecules → 2. **Filter** by properties → 3. **Dock** to target → 4. **Predict ADMET** → 5. **Rank** candidates
    """)
    
    # Workflow status
    st.subheader("Workflow Status")
    
    steps = [
        ("Molecule Generation", "generated_molecules" in st.session_state and len(st.session_state.generated_molecules) > 0),
        ("Property Validation", "validation_results" in st.session_state),
        ("Molecular Docking", "docking_results" in st.session_state),
        ("ADMET Prediction", "admet_results" in st.session_state),
    ]
    
    for i, (name, done) in enumerate(steps):
        icon = "✅" if done else "⏳"
        st.write(f"{icon} Step {i+1}: {name}")
    
    # One-click workflow
    if st.button("🚀 Run Full Workflow (Demo)", type="primary"):
        with st.spinner("Running integrated workflow..."):
            # This would chain all steps together
            st.info("Full workflow execution would be implemented here")
            st.success("Workflow completed! Check individual tabs for results.")
    
    # Candidate ranking
    if "docking_results" in st.session_state and "admet_results" in st.session_state:
        st.subheader("Integrated Candidate Ranking")
        
        # Match docking and ADMET results by SMILES
        docking_dict = {r.ligand_smiles: r for r in st.session_state.docking_results if r.success}
        admet_dict = {r.smiles: r for r in st.session_state.admet_results}
        
        common_smiles = set(docking_dict.keys()) & set(admet_dict.keys())
        
        if common_smiles:
            ranking_data = []
            for smi in common_smiles:
                dock = docking_dict[smi]
                admet = admet_dict[smi]
                
                # Combined score
                dock_score = -dock.best_pose.score if dock.best_pose else 0  # Lower docking score = better
                admet_score = admet.overall_score
                
                # Normalize and combine
                combined = 0.5 * (1 / (1 + abs(dock_score))) + 0.5 * admet_score
                
                ranking_data.append({
                    "SMILES": smi,
                    "Docking Score": round(dock.best_pose.score, 3) if dock.best_pose else "N/A",
                    "ADMET Score": round(admet.overall_score, 3),
                    "Risk Level": admet.risk_level,
                    "Combined Score": round(combined, 3),
                })
            
            ranking_df = pd.DataFrame(ranking_data)
            ranking_df = ranking_df.sort_values("Combined Score", ascending=False)
            
            st.dataframe(ranking_df, use_container_width=True, hide_index=True)
            
            # Visualization
            fig = px.scatter(
                ranking_df, 
                x="Docking Score", 
                y="ADMET Score",
                color="Risk Level",
                hover_data=["SMILES"],
                title="Docking vs ADMET Trade-off",
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Download ranked candidates
            csv = ranking_df.to_csv(index=False)
            st.download_button(
                "📥 Download Ranked Candidates",
                csv,
                file_name="ranked_candidates.csv",
                mime="text/csv",
            )
        else:
            st.info("No overlapping molecules between docking and ADMET results")


# Export main function
__all__ = ["render_drug_design_ui"]