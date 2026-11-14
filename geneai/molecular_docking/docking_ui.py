"""Streamlit UI for Molecular Docking Engine."""
from __future__ import annotations

import logging
import tempfile
import json
from typing import Any
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from geneai.molecular_docking.protein_prep import (
    ProteinPreparator,
    BindingSite,
    prepare_protein,
    predict_binding_site,
)
from geneai.molecular_docking.ligand_prep import (
    LigandPreparator,
    prepare_ligand,
)
from geneai.molecular_docking.docking_engine import (
    DockingEngine,
    DockingConfig,
    DockingResult,
    dock,
)
from geneai.molecular_docking.pose_analyzer import (
    PoseAnalyzer,
    PoseRescorer,
    ConsensusScorer,
    analyze_poses,
    rescore_poses,
)
from geneai.molecular_docking.scoring import (
    VinaScoringFunction,
    RFScore,
    NNScore,
    ConsensusScorer as ScoringConsensusScorer,
    MMGBSARescorer,
    create_consensus_scorer,
)
from geneai.molecular_docking.visualization import (
    PoseVisualizer,
    create_3d_view,
    create_2d_diagram,
    export_pymol,
)

logger = logging.getLogger(__name__)


def render_molecular_docking_ui():
    """Main entry point for Molecular Docking Engine UI."""
    st.title("🎯 Molecular Docking Engine")
    st.markdown("""
    **Structure-based molecular docking** with AutoDock Vina, smina, GNINA, and consensus scoring.
    Supports protein/ligand preparation, binding site prediction, pose analysis, and rescoring.
    """)
    
    # Initialize session state
    if "docking_results" not in st.session_state:
        st.session_state.docking_results = None
    if "receptor_prep_result" not in st.session_state:
        st.session_state.receptor_prep_result = None
    if "ligand_prep_results" not in st.session_state:
        st.session_state.ligand_prep_results = None
    if "pose_analysis" not in st.session_state:
        st.session_state.pose_analysis = None
    
    # Tabs
    tabs = st.tabs([
        "🧬 Protein Preparation",
        "💊 Ligand Preparation", 
        "🎯 Docking",
        "📊 Pose Analysis",
        "🔬 Rescoring & Consensus",
        "🖼️ Visualization",
        "📈 Batch Docking",
    ])
    
    with tabs[0]:
        render_protein_preparation()
    
    with tabs[1]:
        render_ligand_preparation()
    
    with tabs[2]:
        render_docking()
    
    with tabs[3]:
        render_pose_analysis()
    
    with tabs[4]:
        render_rescoring()
    
    with tabs[5]:
        render_visualization()
    
    with tabs[6]:
        render_batch_docking()


def render_protein_preparation():
    """Protein preparation tab."""
    st.header("🧬 Protein Preparation")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Input Structure")
        input_method = st.radio(
            "Input Method",
            ["Upload PDB", "PDB ID (fetch)", "Predefined Targets"],
        )
        
        protein_file = None
        pdb_id = ""
        
        if input_method == "Upload PDB":
            protein_file = st.file_uploader(
                "Upload PDB/mmCIF file",
                type=["pdb", "cif", "mmcif", "ent"],
            )
        elif input_method == "PDB ID (fetch)":
            pdb_id = st.text_input("PDB ID", value="1M17", max_chars=4)
            if st.button("Fetch from RCSB"):
                st.info("PDB fetching would download from RCSB PDB")
        else:
            target = st.selectbox(
                "Predefined Target",
                [
                    "EGFR (1M17)",
                    "BRAF (1UWH)",
                    "CDK2 (1HCK)",
                    "PARP1 (4GV9)",
                    "Mpro (6LU7)",
                    "ACE2 (6M0J)",
                ],
            )
            st.info(f"Using: {target}")
        
        st.subheader("Preparation Options")
        pH = st.slider("pH for Protonation", 4.0, 9.0, 7.4, 0.1)
        add_hydrogens = st.checkbox("Add Hydrogens", value=True)
        remove_waters = st.checkbox("Remove Waters", value=True)
        remove_heterogens = st.checkbox("Remove Heterogens", value=True)
        keep_heterogens = st.text_input(
            "Keep Heterogens (comma-separated)",
            value="HEM,ZN,MG,CA",
            help="Residue names to keep even if heterogen",
        )
        assign_charges = st.selectbox(
            "Charge Assignment",
            ["gasteiger", "mmff94", "mmff94s"],
        )
        fix_missing = st.checkbox("Fix Missing Atoms/Sidechains", value=True)
        
        st.subheader("Binding Site")
        site_method = st.selectbox(
            "Binding Site Definition",
            ["Manual", "From Ligand", "Predict (fpocket)", "Predict (Geometry)"],
        )
        
        center = (0.0, 0.0, 0.0)
        size = (20.0, 20.0, 20.0)
        
        if site_method == "Manual":
            col_x, col_y, col_z = st.columns(3)
            with col_x:
                center_x = st.number_input("Center X", value=0.0, format="%.2f")
            with col_y:
                center_y = st.number_input("Center Y", value=0.0, format="%.2f")
            with col_z:
                center_z = st.number_input("Center Z", value=0.0, format="%.2f")
            center = (center_x, center_y, center_z)
            
            col_sx, col_sy, col_sz = st.columns(3)
            with col_sx:
                size_x = st.number_input("Size X", value=20.0, format="%.1f")
            with col_sy:
                size_y = st.number_input("Size Y", value=20.0, format="%.1f")
            with col_sz:
                size_z = st.number_input("Size Z", value=20.0, format="%.1f")
            size = (size_x, size_y, size_z)
        
        elif site_method == "From Ligand":
            ligand_file = st.file_uploader("Upload Co-crystallized Ligand", type=["pdb", "sdf", "mol2"])
            buffer = st.number_input("Buffer (Å)", value=5.0, format="%.1f")
        
        if st.button("🔬 Prepare Protein", type="primary"):
            with st.spinner("Preparing protein..."):
                preparator = ProteinPreparator(
                    pH=pH,
                    add_hydrogens=add_hydrogens,
                    remove_waters=remove_waters,
                    remove_heterogens=remove_heterogens,
                    keep_heterogens=[h.strip() for h in keep_heterogens.split(",") if h.strip()],
                    assign_charges=assign_charges,
                    fix_missing=fix_missing,
                )
                
                # Handle input
                if protein_file:
                    with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as tmp:
                        tmp.write(protein_file.read())
                        input_path = tmp.name
                else:
                    st.error("Please provide protein structure")
                    return
                
                # Prepare
                with tempfile.NamedTemporaryFile(suffix=".pdbqt", delete=False) as tmp_out:
                    output_path = tmp_out.name
                
                result = preparator.prepare(input_path, output_path)
                
                if result.success:
                    # Determine binding site
                    binding_site = None
                    if site_method == "Manual":
                        binding_site = BindingSite(center=center, size=size, method="manual")
                    elif site_method == "From Ligand" and ligand_file:
                        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as tmp_lig:
                            tmp_lig.write(ligand_file.read())
                            binding_site = preparator.define_binding_site_from_ligand(
                                input_path, tmp_lig.name, buffer
                            )
                    elif site_method == "Predict (fpocket)":
                        binding_site = preparator.predict_binding_site(input_path, "fpocket")
                    elif site_method == "Predict (Geometry)":
                        binding_site = preparator.predict_binding_site(input_path, "geometry")
                    
                    st.session_state.receptor_prep_result = result
                    st.session_state.binding_site = binding_site
                    st.success("Protein prepared successfully!")
                else:
                    st.error(f"Preparation failed: {result.error}")
    
    with col2:
        st.subheader("Preparation Result")
        
        if st.session_state.receptor_prep_result:
            result = st.session_state.receptor_prep_result
            
            st.metric("Status", "✅ Success" if result.success else "❌ Failed")
            
            if result.success:
                st.write(f"**Input:** {result.input_path}")
                st.write(f"**Output:** {result.output_pdbqt}")
                st.write(f"**Chains Processed:** {', '.join(result.chains_processed) if result.chains_processed else 'All'}")
                
                # Show binding site
                if "binding_site" in st.session_state and st.session_state.binding_site:
                    bs = st.session_state.binding_site
                    st.subheader("Binding Site")
                    st.write(f"**Center:** ({bs.center[0]:.2f}, {bs.center[1]:.2f}, {bs.center[2]:.2f})")
                    st.write(f"**Size:** ({bs.size[0]:.1f}, {bs.size[1]:.1f}, {bs.size[2]:.1f})")
                    st.write(f"**Method:** {bs.method}")
                    st.write(f"**Confidence:** {bs.confidence:.0%}")
                
                # Download
                if Path(result.output_pdbqt).exists():
                    with open(result.output_pdbqt, "rb") as f:
                        st.download_button(
                            "📥 Download PDBQT",
                            f.read(),
                            file_name=Path(result.output_pdbqt).name,
                            mime="chemical/x-pdbqt",
                        )
        else:
            st.info("Prepare a protein to see results here")


def render_ligand_preparation():
    """Ligand preparation tab."""
    st.header("💊 Ligand Preparation")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Input Ligands")
        input_method = st.radio(
            "Input Method",
            ["SMILES", "Upload File", "From Generated Molecules"],
        )
        
        smiles_list = []
        
        if input_method == "SMILES":
            smiles_text = st.text_area(
                "SMILES (one per line)",
                value="CCO\nc1ccccc1\nCC(=O)O\nCN1C=NC2=C1C(=O)N(C(=O)N2C)C",
                height=150,
            )
            smiles_list = [s.strip() for s in smiles_text.strip().split("\n") if s.strip()]
        
        elif input_method == "Upload File":
            ligand_file = st.file_uploader(
                "Upload Ligand File",
                type=["sdf", "mol2", "pdb", "smi", "csv"],
            )
            if ligand_file:
                # Would parse file here
                st.info("File parsing implemented in batch mode")
        
        else:
            # Would use generated molecules from drug_design
            st.info("Connect to Drug Design Engine for generated molecules")
        
        st.subheader("Preparation Options")
        pH = st.slider("pH for Tautomers", 4.0, 9.0, 7.4, 0.1)
        enumerate_tautomers = st.checkbox("Enumerate Tautomers", value=True)
        max_tautomers = st.slider("Max Tautomers per Ligand", 1, 20, 10)
        enumerate_stereoisomers = st.checkbox("Enumerate Stereoisomers", value=True)
        max_stereoisomers = st.slider("Max Stereoisomers per Ligand", 1, 64, 32)
        generate_conformers = st.checkbox("Generate 3D Conformers", value=True)
        num_conformers = st.slider("Conformers per Isomer", 1, 50, 10)
        min_rmsd = st.slider("Min RMSD Between Conformers (Å)", 0.1, 2.0, 0.5, 0.1)
        energy_minimize = st.checkbox("Energy Minimize (MMFF94)", value=True)
        force_field = st.selectbox("Force Field", ["mmff94", "mmff94s", "uff"])
        assign_charges = st.selectbox("Charge Assignment", ["gasteiger", "mmff94", "am1bcc"])
        
        if st.button("🧪 Prepare Ligands", type="primary"):
            if smiles_list:
                with st.spinner(f"Preparing {len(smiles_list)} ligands..."):
                    preparator = LigandPreparator(
                        pH=pH,
                        enumerate_tautomers=enumerate_tautomers,
                        max_tautomers=max_tautomers,
                        enumerate_stereoisomers=enumerate_stereoisomers,
                        max_stereoisomers=max_stereoisomers,
                        generate_conformers=generate_conformers,
                        num_conformers=num_conformers,
                        min_rmsd=min_rmsd,
                        energy_minimize=energy_minimize,
                        force_field=force_field,
                        assign_charges=assign_charges,
                    )
                    
                    results = []
                    for i, smi in enumerate(smiles_list):
                        with tempfile.NamedTemporaryFile(suffix=".pdbqt", delete=False) as tmp:
                            output_path = tmp.name
                        
                        result = preparator.prepare(smi, output_path, f"ligand_{i}")
                        results.append(result)
                    
                    st.session_state.ligand_prep_results = results
                    success_count = sum(1 for r in results if r.success)
                    st.success(f"Prepared {success_count}/{len(results)} ligands successfully!")
            else:
                st.warning("Please provide ligand SMILES")
    
    with col2:
        st.subheader("Preparation Results")
        
        if st.session_state.ligand_prep_results:
            results = st.session_state.ligand_prep_results
            
            # Summary table
            df_data = []
            for r in results:
                df_data.append({
                    "Input SMILES": r.input_smiles,
                    "Status": "✅" if r.success else "❌",
                    "Tautomers": r.num_tautomers,
                    "Stereoisomers": r.num_stereoisomers,
                    "Conformers": r.num_conformers,
                    "Output": Path(r.output_pdbqt).name if r.success else r.error,
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Download all
            if st.button("📥 Download All PDBQT"):
                # Would create zip file
                st.info("Batch download would create ZIP with all PDBQT files")
            
            # Show details for selected
            if results:
                selected_idx = st.selectbox(
                    "View Details",
                    range(len(results)),
                    format_func=lambda i: f"{results[i].input_smiles[:30]}...",
                )
                
                selected = results[selected_idx]
                if selected.success:
                    st.write(f"**Tautomers generated:** {selected.num_tautomers}")
                    st.write(f"**Stereoisomers generated:** {selected.num_stereoisomers}")
                    st.write(f"**Conformers per isomer:** {selected.num_conformers}")
                    st.write(f"**Total output molecules:** {selected.metadata.get('num_output_molecules', 'N/A')}")
        else:
            st.info("Prepare ligands to see results here")


def render_docking():
    """Docking tab."""
    st.header("🎯 Molecular Docking")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Receptor")
        if st.session_state.receptor_prep_result and st.session_state.receptor_prep_result.success:
            st.success(f"✅ Receptor ready: {Path(st.session_state.receptor_prep_result.output_pdbqt).name}")
            receptor_pdbqt = st.session_state.receptor_prep_result.output_pdbqt
            
            # Binding site from preparation
            if "binding_site" in st.session_state and st.session_state.binding_site:
                bs = st.session_state.binding_site
                st.write(f"Binding site: Center={bs.center}, Size={bs.size}")
        else:
            st.warning("Please prepare a protein first in the Protein Preparation tab")
            receptor_pdbqt = None
        
        st.subheader("Ligands")
        ligand_source = st.radio(
            "Ligand Source",
            ["Prepared Ligands", "Upload PDBQT", "SMILES (auto-prepare)"],
        )
        
        ligand_pdbqt_list = []
        
        if ligand_source == "Prepared Ligands":
            if st.session_state.ligand_prep_results:
                ligand_pdbqt_list = [r.output_pdbqt for r in st.session_state.ligand_prep_results if r.success]
                st.info(f"{len(ligand_pdbqt_list)} prepared ligands available")
            else:
                st.warning("No prepared ligands available")
        
        elif ligand_source == "Upload PDBQT":
            ligand_files = st.file_uploader("Upload Ligand PDBQT", type=["pdbqt"], accept_multiple_files=True)
            if ligand_files:
                for f in ligand_files:
                    with tempfile.NamedTemporaryFile(suffix=".pdbqt", delete=False) as tmp:
                        tmp.write(f.read())
                        ligand_pdbqt_list.append(tmp.name)
        
        else:
            smiles_text = st.text_area("Ligand SMILES (one per line)", value="CCO\nc1ccccc1")
            smiles_list = [s.strip() for s in smiles_text.strip().split("\n") if s.strip()]
            if smiles_list:
                # Auto-prepare
                preparator = LigandPreparator()
                for i, smi in enumerate(smiles_list):
                    with tempfile.NamedTemporaryFile(suffix=".pdbqt", delete=False) as tmp:
                        result = preparator.prepare(smi, tmp.name, f"ligand_{i}")
                        if result.success:
                            ligand_pdbqt_list.append(result.output_pdbqt)
        
        st.subheader("Docking Engine")
        engine = st.selectbox(
            "Engine",
            ["vina", "smina", "gnina", "internal"],
            help="Vina/smina/gnina require installation. Internal is RDKit-based (approximate).",
        )
        
        # Check available engines
        test_engine = DockingEngine(engine=engine)
        available = test_engine.available_engines
        if engine not in available and engine != "internal":
            st.warning(f"{engine} not found. Available: {available}. Using internal.")
            engine = "internal"
        else:
            st.success(f"✅ {engine} available")
        
        st.subheader("Docking Parameters")
        config = DockingConfig()
        
        if "binding_site" in st.session_state and st.session_state.binding_site:
            bs = st.session_state.binding_site
            config.center = bs.center
            config.size = bs.size
            st.write(f"Using binding site from protein prep: Center={bs.center}, Size={bs.size}")
        else:
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                config.center = (st.number_input("Center X", value=0.0, format="%.2f"),
                               st.number_input("Center Y", value=0.0, format="%.2f"),
                               st.number_input("Center Z", value=0.0, format="%.2f"))
            with col_c2:
                config.size = (st.number_input("Size X", value=20.0, format="%.1f"),
                              st.number_input("Size Y", value=20.0, format="%.1f"),
                              st.number_input("Size Z", value=20.0, format="%.1f"))
        
        config.exhaustiveness = st.slider("Exhaustiveness", 1, 32, 8)
        config.num_modes = st.slider("Number of Poses", 1, 20, 9)
        config.energy_range = st.slider("Energy Range (kcal/mol)", 0.5, 10.0, 3.0)
        config.seed = st.number_input("Random Seed (0=random)", value=0)
        if config.seed == 0:
            config.seed = None
        
        if engine in ["smina", "gnina"]:
            config.scoring = st.selectbox(
                "Scoring Function",
                ["vina", "ad4", "vinardo", "dkoes"] if engine == "smina" else ["vina"],
            )
            
            # Flexible residues for smina
            if engine == "smina":
                flex_residues = st.text_input(
                    "Flexible Residues (e.g., A:123,A:124)",
                    help="Residue numbers for sidechain flexibility",
                )
                if flex_residues:
                    config.flexible_residues = [r.strip() for r in flex_residues.split(",")]
        
        if st.button("🚀 Run Docking", type="primary"):
            if receptor_pdbqt and ligand_pdbqt_list:
                with st.spinner(f"Docking {len(ligand_pdbqt_list)} ligands with {engine}..."):
                    docking_engine = DockingEngine(engine=engine)
                    
                    all_results = []
                    progress_bar = st.progress(0)
                    
                    for i, lig_pdbqt in enumerate(ligand_pdbqt_list):
                        result = docking_engine.dock(receptor_pdbqt, lig_pdbqt, config)
                        all_results.append(result)
                        progress_bar.progress((i + 1) / len(ligand_pdbqt_list))
                    
                    st.session_state.docking_results = all_results
                    success_count = sum(1 for r in all_results if r.success)
                    st.success(f"Docking complete: {success_count}/{len(all_results)} successful!")
            else:
                st.error("Please provide both receptor and ligands")
    
    with col2:
        st.subheader("Docking Results")
        
        if st.session_state.docking_results:
            results = st.session_state.docking_results
            
            # Summary table
            summary_data = []
            for r in results:
                if r.success and r.best_pose:
                    summary_data.append({
                        "Ligand": r.ligand_smiles[:40] + "..." if len(r.ligand_smiles) > 40 else r.ligand_smiles,
                        "Best Score": f"{r.best_pose.score:.3f}",
                        "Poses": len(r.poses),
                        "Engine": r.engine,
                        "Time (s)": f"{r.docking_time:.2f}",
                        "Status": "✅",
                    })
                else:
                    summary_data.append({
                        "Ligand": r.ligand_smiles[:40] + "..." if len(r.ligand_smiles) > 40 else r.ligand_smiles,
                        "Best Score": "Failed",
                        "Poses": 0,
                        "Engine": r.engine,
                        "Time (s)": f"{r.docking_time:.2f}",
                        "Status": "❌",
                    })
            
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            # Detailed view
            successful_results = [r for r in results if r.success and r.poses]
            
            if successful_results:
                selected_idx = st.selectbox(
                    "Select Ligand for Details",
                    range(len(successful_results)),
                    format_func=lambda i: f"{successful_results[i].ligand_smiles[:30]}... (Score: {successful_results[i].best_pose.score:.2f})",
                )
                
                selected = successful_results[selected_idx]
                
                st.subheader(f"Poses for {selected.ligand_smiles}")
                
                pose_data = []
                for i, pose in enumerate(selected.poses):
                    pose_data.append({
                        "Pose": i + 1,
                        "Score (kcal/mol)": f"{pose.score:.3f}",
                        "Interactions": json.dumps(pose.interactions, default=str)[:80] + "..." if pose.interactions else "None",
                    })
                
                pose_df = pd.DataFrame(pose_data)
                st.dataframe(pose_df, use_container_width=True, hide_index=True)
                
                # Interaction summary
                if selected.best_pose and selected.best_pose.interactions:
                    st.subheader("Interactions (Best Pose)")
                    for int_type, interactions in selected.best_pose.interactions.items():
                        if interactions:
                            st.write(f"**{int_type.replace('_', ' ').title()}:** {len(interactions)} contacts")
                
                # Download results
                if st.button("📥 Download All Results (CSV)"):
                    # Create detailed CSV
                    detailed_data = []
                    for r in results:
                        for i, pose in enumerate(r.poses):
                            detailed_data.append({
                                "Ligand": r.ligand_smiles,
                                "Pose": i + 1,
                                "Score": pose.score,
                                "Engine": r.engine,
                            })
                    
                    detailed_df = pd.DataFrame(detailed_data)
                    csv = detailed_df.to_csv(index=False)
                    st.download_button(
                        "Download CSV",
                        csv,
                        file_name="docking_results.csv",
                        mime="text/csv",
                    )
        else:
            st.info("Run docking to see results here")


def render_pose_analysis():
    """Pose analysis tab."""
    st.header("📊 Pose Analysis")
    
    if not st.session_state.docking_results:
        st.warning("Run docking first to analyze poses")
        return
    
    successful_results = [r for r in st.session_state.docking_results if r.success and r.poses]
    
    if not successful_results:
        st.warning("No successful docking results to analyze")
        return
    
    selected_idx = st.selectbox(
        "Select Result for Analysis",
        range(len(successful_results)),
        format_func=lambda i: f"{successful_results[i].ligand_smiles[:30]}...",
    )
    
    selected = successful_results[selected_idx]
    
    st.subheader("RMSD Clustering")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        rmsd_cutoff = st.slider("RMSD Cutoff (Å)", 0.5, 5.0, 2.0, 0.1)
        method = st.selectbox("Clustering Method", ["butina", "hierarchical"])
        
        if st.button("Cluster Poses"):
            with st.spinner("Clustering..."):
                # Need ligand molecule with conformers
                # For now, use first pose coordinates
                analyzer = PoseAnalyzer()
                
                # Create dummy ligand mol with pose conformers
                from rdkit import Chem
                lig_mol = Chem.MolFromSmiles(selected.ligand_smiles)
                if lig_mol:
                    lig_mol = Chem.AddHs(lig_mol)
                    AllChem.EmbedMolecule(lig_mol)
                    
                    # Add all pose coordinates as conformers
                    for pose in selected.poses:
                        if pose.coordinates:
                            conf = Chem.Conformer(lig_mol.GetNumAtoms())
                            for i, coord in enumerate(pose.coordinates):
                                conf.SetAtomPosition(i, coord)
                            lig_mol.AddConformer(conf, assignId=True)
                    
                    cluster_result = analyzer.cluster_poses_rmsd(
                        selected.poses, lig_mol, rmsd_cutoff, method
                    )
                    
                    st.session_state.pose_analysis = {
                        "clusters": cluster_result.clusters,
                        "centroids": cluster_result.centroids,
                        "rmsd_matrix": cluster_result.rmsd_matrix,
                    }
                    
                    st.success(f"Found {len(cluster_result.clusters)} clusters")
    
    with col2:
        if "pose_analysis" in st.session_state:
            pa = st.session_state.pose_analysis
            
            # Cluster sizes
            cluster_sizes = [len(c) for c in pa["clusters"]]
            fig = px.bar(
                x=list(range(1, len(cluster_sizes) + 1)),
                y=cluster_sizes,
                labels={"x": "Cluster", "y": "Number of Poses"},
                title="Cluster Sizes",
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Cluster details
            st.subheader("Cluster Details")
            for i, (cluster, centroid) in enumerate(zip(pa["clusters"], pa["centroids"])):
                with st.expander(f"Cluster {i+1} (Size: {len(cluster)}, Centroid: Pose {centroid+1})"):
                    for pose_idx in cluster:
                        pose = selected.poses[pose_idx]
                        st.write(f"  Pose {pose_idx+1}: Score = {pose.score:.3f}")
            
            # RMSD heatmap
            if len(pa["rmsd_matrix"]) > 1:
                fig = px.imshow(
                    pa["rmsd_matrix"],
                    labels=dict(x="Pose", y="Pose", color="RMSD (Å)"),
                    title="Pairwise RMSD Matrix",
                )
                st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Interaction Fingerprints")
    
    if st.button("Generate Interaction Fingerprints"):
        with st.spinner("Generating IFPs..."):
            analyzer = PoseAnalyzer()
            
            # Would need receptor mol - for now use dummy
            from rdkit import Chem
            rec_mol = Chem.MolFromSmiles("C")  # Placeholder
            
            fps = []
            for i, pose in enumerate(selected.poses):
                fp = analyzer.generate_interaction_fingerprint(pose, rec_mol)
                fp.pose_index = i
                fps.append(fp)
            
            # Similarity matrix
            sim_matrix = analyzer.calculate_ifp_similarity_matrix(selected.poses, rec_mol)
            
            fig = px.imshow(
                sim_matrix,
                labels=dict(x="Pose", y="Pose", color="Tanimoto"),
                title="Interaction Fingerprint Similarity",
            )
            st.plotly_chart(fig, use_container_width=True)


def render_rescoring():
    """Rescoring and consensus scoring tab."""
    st.header("🔬 Rescoring & Consensus Scoring")
    
    if not st.session_state.docking_results:
        st.warning("Run docking first")
        return
    
    successful_results = [r for r in st.session_state.docking_results if r.success and r.poses]
    
    if not successful_results:
        return
    
    selected_idx = st.selectbox(
        "Select Result for Rescoring",
        range(len(successful_results)),
        format_func=lambda i: f"{successful_results[i].ligand_smiles[:30]}...",
        key="rescore_select",
    )
    
    selected = successful_results[selected_idx]
    
    st.subheader("Rescoring Methods")
    
    method = st.selectbox(
        "Rescoring Method",
        ["Interaction-based", "Consensus (Vina+RF+NN)", "MM/GBSA (approximate)"],
    )
    
    if st.button("Rescore Poses"):
        with st.spinner(f"Rescoring with {method}..."):
            from rdkit import Chem
            
            lig_mol = Chem.MolFromSmiles(selected.ligand_smiles)
            if lig_mol:
                lig_mol = Chem.AddHs(lig_mol)
                AllChem.EmbedMolecule(lig_mol)
                for pose in selected.poses:
                    if pose.coordinates:
                        conf = Chem.Conformer(lig_mol.GetNumAtoms())
                        for i, coord in enumerate(pose.coordinates):
                            conf.SetAtomPosition(i, coord)
                        lig_mol.AddConformer(conf, assignId=True)
                
                # Dummy receptor
                rec_mol = Chem.MolFromSmiles("C")
                
                if method == "Interaction-based":
                    results = rescore_poses(selected.poses, rec_mol, lig_mol, "interaction")
                elif method == "Consensus (Vina+RF+NN)":
                    results = rescore_poses(selected.poses, rec_mol, lig_mol, "consensus")
                else:
                    results = rescore_poses(selected.poses, rec_mol, lig_mol, "mm_gbsa")
                
                st.session_state.rescoring_results = results
                st.success("Rescoring complete!")
    
    if "rescoring_results" in st.session_state:
        results = st.session_state.rescoring_results
        
        # Comparison table
        comparison_data = []
        for i, res in enumerate(results):
            comparison_data.append({
                "Pose": res.pose_index + 1,
                "Original Score": f"{selected.poses[res.pose_index].score:.3f}",
                "Rescored Score": f"{res.rescored_score:.3f}",
                "Delta": f"{res.rescored_score - selected.poses[res.pose_index].score:.3f}",
                "Method": res.method,
            })
        
        comp_df = pd.DataFrame(comparison_data)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)
        
        # Plot
        fig = px.scatter(
            comp_df,
            x="Original Score",
            y="Rescored Score",
            hover_data=["Pose", "Delta"],
            title="Original vs Rescored Scores",
        )
        # Add diagonal
        fig.add_trace(go.Scatter(
            x=[comp_df["Original Score"].min(), comp_df["Original Score"].max()],
            y=[comp_df["Original Score"].min(), comp_df["Original Score"].max()],
            mode="lines",
            line=dict(dash="dash", color="gray"),
            showlegend=False,
        ))
        st.plotly_chart(fig, use_container_width=True)
        
        # Components
        if results[0].components:
            st.subheader("Score Components")
            for res in results:
                with st.expander(f"Pose {res.pose_index + 1} Components"):
                    comp_df = pd.DataFrame([res.components])
                    st.dataframe(comp_df.T, use_container_width=True)
    
    st.subheader("Consensus Scoring Across Runs")
    st.info("Run docking multiple times with different seeds to enable consensus scoring")


def render_visualization():
    """Visualization tab."""
    st.header("🖼️ Visualization")
    
    if not st.session_state.docking_results:
        st.warning("Run docking first")
        return
    
    successful_results = [r for r in st.session_state.docking_results if r.success and r.poses]
    
    if not successful_results:
        return
    
    selected_idx = st.selectbox(
        "Select Result to Visualize",
        range(len(successful_results)),
        format_func=lambda i: f"{successful_results[i].ligand_smiles[:30]}...",
        key="viz_select",
    )
    
    selected = successful_results[selected_idx]
    
    viz_type = st.radio(
        "Visualization Type",
        ["2D Interaction Diagram", "Pose Comparison Grid", "PyMOL Export"],
        horizontal=True,
    )
    
    if viz_type == "2D Interaction Diagram":
        pose_idx = st.selectbox(
            "Select Pose",
            range(len(selected.poses)),
            format_func=lambda i: f"Pose {i+1} (Score: {selected.poses[i].score:.2f})",
        )
        
        pose = selected.poses[pose_idx]
        
        st.subheader("2D Interaction Diagram")
        
        # Create visualization
        from rdkit import Chem
        lig_mol = Chem.MolFromSmiles(selected.ligand_smiles)
        rec_mol = Chem.MolFromSmiles("C")  # Placeholder
        
        if lig_mol and pose.coordinates:
            lig_mol = Chem.AddHs(lig_mol)
            AllChem.EmbedMolecule(lig_mol)
            conf = lig_mol.GetConformer()
            for i, coord in enumerate(pose.coordinates):
                conf.SetAtomPosition(i, coord)
            
            # Generate 2D diagram
            visualizer = PoseVisualizer()
            img = visualizer.create_2d_interaction_diagram(
                rec_mol, lig_mol, pose.coordinates, pose.interactions
            )
            
            st.image(img, caption=f"Pose {pose_idx+1} Interactions")
            
            # Download
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            st.download_button(
                "📥 Download PNG",
                buf.getvalue(),
                file_name=f"interaction_diagram_pose_{pose_idx+1}.png",
                mime="image/png",
            )
    
    elif viz_type == "Pose Comparison Grid":
        st.subheader("Pose Comparison Grid")
        
        n_cols = st.slider("Columns", 2, 6, 4)
        
        if st.button("Generate Grid"):
            from rdkit import Chem
            
            lig_mol = Chem.MolFromSmiles(selected.ligand_smiles)
            rec_mol = Chem.MolFromSmiles("C")
            
            if lig_mol:
                lig_mol = Chem.AddHs(lig_mol)
                AllChem.EmbedMolecule(lig_mol)
                for pose in selected.poses:
                    if pose.coordinates:
                        conf = Chem.Conformer(lig_mol.GetNumAtoms())
                        for i, coord in enumerate(pose.coordinates):
                            conf.SetAtomPosition(i, coord)
                        lig_mol.AddConformer(conf, assignId=True)
                
                visualizer = PoseVisualizer()
                grid_img = visualizer.create_pose_comparison_grid(
                    selected.poses, lig_mol, rec_mol, n_cols=n_cols
                )
                
                st.image(grid_img, caption="Pose Comparison Grid")
                
                import io
                buf = io.BytesIO()
                grid_img.save(buf, format="PNG")
                st.download_button(
                    "📥 Download Grid PNG",
                    buf.getvalue(),
                    file_name="pose_comparison_grid.png",
                    mime="image/png",
                )
    
    else:  # PyMOL Export
        st.subheader("PyMOL Session Export")
        st.info("Generates PyMOL script for interactive 3D viewing")
        
        if st.button("Export PyMOL Script"):
            from rdkit import Chem
            
            lig_mol = Chem.MolFromSmiles(selected.ligand_smiles)
            rec_mol = Chem.MolFromSmiles("C")
            
            if lig_mol:
                lig_mol = Chem.AddHs(lig_mol)
                AllChem.EmbedMolecule(lig_mol)
                for pose in selected.poses:
                    if pose.coordinates:
                        conf = Chem.Conformer(lig_mol.GetNumAtoms())
                        for i, coord in enumerate(pose.coordinates):
                            conf.SetAtomPosition(i, coord)
                        lig_mol.AddConformer(conf, assignId=True)
                
                with tempfile.NamedTemporaryFile(suffix=".pml", delete=False) as tmp:
                    output_path = tmp.name
                
                visualizer = PoseVisualizer()
                visualizer.export_pymol_session(rec_mol, lig_mol, selected.poses, output_path)
                
                with open(output_path, "r") as f:
                    script = f.read()
                
                st.code(script, language="python")
                st.download_button(
                    "📥 Download .pml",
                    script,
                    file_name="docking_session.pml",
                    mime="text/plain",
                )


def render_batch_docking():
    """Batch docking tab."""
    st.header("📈 Batch Docking")
    
    st.markdown("""
    **High-throughput docking** of large ligand libraries against a prepared receptor.
    """)
    
    if not st.session_state.receptor_prep_result or not st.session_state.receptor_prep_result.success:
        st.warning("Please prepare a protein first in the Protein Preparation tab")
        return
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Ligand Library")
        library_source = st.radio(
            "Library Source",
            ["Upload SDF/CSV", "ChEMBL Subset (demo)", "Generated Molecules"],
        )
        
        smiles_list = []
        
        if library_source == "Upload SDF/CSV":
            lib_file = st.file_uploader("Upload Library", type=["sdf", "csv", "smi"])
            if lib_file:
                if lib_file.name.endswith(".csv"):
                    df = pd.read_csv(lib_file)
                    smiles_col = st.selectbox("SMILES Column", df.columns)
                    smiles_list = df[smiles_col].dropna().tolist()
                elif lib_file.name.endswith(".sdf"):
                    # Would parse SDF
                    st.info("SDF parsing would extract SMILES")
                else:
                    # .smi file
                    content = lib_file.read().decode()
                    smiles_list = [line.split()[0] for line in content.strip().split("\n") if line.strip()]
        
        elif library_source == "ChEMBL Subset (demo)":
            # Demo library
            smiles_list = [
                "CCO", "CCC", "CCCC", "CCCCC", "CCCCCC",
                "c1ccccc1", "Cc1ccccc1", "CCc1ccccc1",
                "CC(=O)O", "CCC(=O)O", "CCCC(=O)O",
                "NCCO", "NCCCO", "NCCCCO",
                "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",  # Caffeine
                "CC(=O)OC1=CC=CC=C1C(=O)O",  # Aspirin
            ] * 5  # 80 molecules
            st.info(f"Demo library: {len(smiles_list)} molecules")
        
        else:
            if "generated_molecules" in st.session_state:
                smiles_list = st.session_state.generated_molecules
                st.info(f"Using {len(smiles_list)} generated molecules")
            else:
                st.warning("No generated molecules available")
        
        st.subheader("Docking Parameters")
        engine = st.selectbox("Engine", ["vina", "smina", "internal"], key="batch_engine")
        exhaustiveness = st.slider("Exhaustiveness", 1, 16, 4, key="batch_exh")
        num_modes = st.slider("Poses per Ligand", 1, 5, 3, key="batch_modes")
        max_ligands = st.number_input("Max Ligands (0=all)", value=0, min_value=0)
        
        if st.button("🚀 Run Batch Docking", type="primary"):
            if smiles_list:
                if max_ligands > 0:
                    smiles_list = smiles_list[:max_ligands]
                
                with st.spinner(f"Preparing and docking {len(smiles_list)} ligands..."):
                    # Prepare ligands
                    preparator = LigandPreparator()
                    
                    ligand_pdbqt_list = []
                    prep_results = []
                    
                    prep_progress = st.progress(0)
                    prep_status = st.empty()
                    
                    for i, smi in enumerate(smiles_list):
                        prep_status.text(f"Preparing ligand {i+1}/{len(smiles_list)}: {smi[:30]}")
                        with tempfile.NamedTemporaryFile(suffix=".pdbqt", delete=False) as tmp:
                            result = preparator.prepare(smi, tmp.name, f"ligand_{i}")
                            prep_results.append(result)
                            if result.success:
                                ligand_pdbqt_list.append((smi, result.output_pdbqt))
                        prep_progress.progress((i + 1) / len(smiles_list))
                    
                    prep_status.text("Preparation complete. Starting docking...")
                    
                    # Dock
                    config = DockingConfig(
                        center=st.session_state.binding_site.center if "binding_site" in st.session_state and st.session_state.binding_site else (0,0,0),
                        size=st.session_state.binding_site.size if "binding_site" in st.session_state and st.session_state.binding_site else (20,20,20),
                        exhaustiveness=exhaustiveness,
                        num_modes=num_modes,
                    )
                    
                    docking_engine = DockingEngine(engine=engine)
                    
                    dock_results = []
                    dock_progress = st.progress(0)
                    dock_status = st.empty()
                    
                    for i, (smi, lig_pdbqt) in enumerate(ligand_pdbqt_list):
                        dock_status.text(f"Docking {i+1}/{len(ligand_pdbqt_list)}: {smi[:30]}")
                        result = docking_engine.dock(
                            st.session_state.receptor_prep_result.output_pdbqt,
                            lig_pdbqt,
                            config,
                        )
                        result.ligand_smiles = smi  # Ensure SMILES stored
                        dock_results.append(result)
                        dock_progress.progress((i + 1) / len(ligand_pdbqt_list))
                    
                    dock_status.text("Batch docking complete!")
                    
                    st.session_state.batch_dock_results = dock_results
                    success_count = sum(1 for r in dock_results if r.success)
                    st.success(f"Batch docking complete: {success_count}/{len(dock_results)} successful!")
            else:
                st.error("Please provide a ligand library")
    
    with col2:
        st.subheader("Batch Results")
        
        if "batch_dock_results" in st.session_state:
            results = st.session_state.batch_dock_results
            
            # Summary
            successful = [r for r in results if r.success and r.best_pose]
            
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total", len(results))
            col_b.metric("Successful", len(successful))
            col_c.metric("Success Rate", f"{len(successful)/len(results)*100:.1f}%" if results else "0%")
            
            if successful:
                # Score distribution
                scores = [r.best_pose.score for r in successful]
                fig = px.histogram(
                    x=scores,
                    nbins=20,
                    title="Docking Score Distribution",
                    labels={"x": "Best Score (kcal/mol)", "y": "Count"},
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Top hits table
                sorted_results = sorted(successful, key=lambda r: r.best_pose.score)
                
                top_data = []
                for r in sorted_results[:50]:
                    top_data.append({
                        "Rank": len(top_data) + 1,
                        "SMILES": r.ligand_smiles,
                        "Best Score": f"{r.best_pose.score:.3f}",
                        "Poses": len(r.poses),
                    })
                
                top_df = pd.DataFrame(top_data)
                st.dataframe(top_df, use_container_width=True, hide_index=True)
                
                # Download
                csv = top_df.to_csv(index=False)
                st.download_button(
                    "📥 Download Top Hits CSV",
                    csv,
                    file_name="batch_docking_top_hits.csv",
                    mime="text/csv",
                )
                
                # All results CSV
                all_data = []
                for r in results:
                    if r.success:
                        for i, pose in enumerate(r.poses):
                            all_data.append({
                                "SMILES": r.ligand_smiles,
                                "Pose": i + 1,
                                "Score": pose.score,
                            })
                
                if all_data:
                    all_df = pd.DataFrame(all_data)
                    csv_all = all_df.to_csv(index=False)
                    st.download_button(
                        "📥 Download All Results CSV",
                        csv_all,
                        file_name="batch_docking_all_results.csv",
                        mime="text/csv",
                    )


__all__ = ["render_molecular_docking_ui"]