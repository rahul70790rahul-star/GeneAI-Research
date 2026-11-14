"""Streamlit UI for Integrated Precision Drug Discovery (Phase 4.12)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import session_state as ss

from geneai.config import APP_NAME
from geneai.integrated_precision.workflow_engine import (
    IntegratedAnalysisInput,
    IntegratedPrecisionDrugDiscoveryEngine,
    run_integrated_precision_drug_discovery,
)
from geneai.integrated_precision.database import (
    clear_ipdd_analysis_run,
    get_ipdd_analysis_run,
    get_ipdd_candidate_rankings,
    get_recent_ipdd_runs,
    search_ipdd_runs,
    store_ipdd_analysis_run,
)
from geneai.variants import parse_vcf

def render_integrated_precision_dashboard() -> None:
    """Render the Integrated Precision Drug Discovery dashboard."""
    st.set_page_config(
        page_title=f"{APP_NAME} - Integrated Precision Drug Discovery",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🎯 Integrated Precision Drug Discovery Engine")
    st.caption("Unified workflow: Variants → Genes → Pathways → Targets → Drugs → ADMET → Safety → Ranking")
    
    # Initialize session state
    if "ipdd_results" not in ss:
        ss.ipdd_results = {}
    if "ipdd_current_run" not in ss:
        ss.ipdd_current_run = None
    if "ipdd_engine" not in ss:
        ss.ipdd_engine = IntegratedPrecisionDrugDiscoveryEngine()
    
    # Sidebar
    with st.sidebar:
        st.header("🔬 Input Data")
        input_method = st.radio(
            "Primary Input",
            ["VCF File", "Gene List", "Disease Name", "Drug/Compound", "Combined"],
            key="ipdd_input_method",
        )
        
        st.divider()
        st.header("⚙️ Analysis Pipeline")
        
        # Pipeline steps
        steps = {
            "run_mutation_analysis": "1. Mutation Analysis",
            "run_disease_gene_analysis": "2. Disease-Gene-Pathway",
            "run_target_identification": "3. Target Identification",
            "run_drug_search": "4. Drug Search",
            "run_drug_target_prediction": "5. Drug-Target Prediction",
            "run_repurposing": "6. Drug Repurposing",
            "run_admet": "7. ADMET Prediction",
            "run_safety": "8. Safety/Toxicity",
            "run_literature": "9. Literature Analysis",
        }
        
        enabled_steps = {}
        for key, label in steps.items():
            enabled_steps[key] = st.checkbox(label, value=True, key=f"ipdd_{key}")
        
        st.divider()
        st.header("📊 Parameters")
        
        max_targets = st.number_input("Max Targets", 5, 100, 20, key="ipdd_max_targets")
        max_drugs = st.number_input("Max Drugs", 10, 200, 50, key="ipdd_max_drugs")
        min_affinity = st.number_input("Min Binding Affinity (pKi/pIC50)", 0.0, 15.0, 5.0, 0.5, key="ipdd_min_affinity")
        
        st.divider()
        st.header("💾 Database")
        save_to_db = st.checkbox("Save to Database", value=True, key="ipdd_save_db")
        
        st.divider()
        st.header("📈 Recent Runs")
        recent = get_recent_ipdd_runs(10)
        for run in recent:
            summary = run.get("summary", {})
            top = summary.get("top_candidate", {})
            top_name = top.get("drug", "N/A") if top else "N/A"
            if st.button(f"{run['run_id']} → {top_name} ({run['timestamp'][:16]})", key=f"recent_{run['run_id']}"):
                _load_ipdd_run(run["run_id"])
    
    # Main content based on input method
    if input_method == "VCF File":
        render_vcf_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db)
    elif input_method == "Gene List":
        render_gene_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db)
    elif input_method == "Disease Name":
        render_disease_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db)
    elif input_method == "Drug/Compound":
        render_drug_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db)
    elif input_method == "Combined":
        render_combined_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db)
    
    # Display results
    if ss.ipdd_current_run and ss.ipdd_current_run in ss.ipdd_results:
        display_ipdd_results(ss.ipdd_current_run, ss.ipdd_results[ss.ipdd_current_run])


def render_vcf_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db) -> None:
    st.subheader("📄 VCF File Analysis")
    st.write("Upload a VCF file to start the integrated drug discovery pipeline from variants.")
    
    file = st.file_uploader("VCF File", type=["vcf", "vcf.gz"], key="ipdd_vcf_file")
    
    col1, col2 = st.columns(2)
    with col1:
        disease_names = st.text_input("Disease Names (optional, comma-separated)", placeholder="breast cancer, lung adenocarcinoma", key="ipdd_vcf_diseases")
    with col2:
        drug_names = st.text_input("Known Drugs (optional, comma-separated)", placeholder="tamoxifen, trastuzumab", key="ipdd_vcf_drugs")
    
    if file and st.button("🚀 Run Integrated Pipeline", type="primary", use_container_width=True, key="ipdd_run_vcf"):
        with st.spinner("Parsing VCF..."):
            try:
                variants, meta = parse_vcf(file.getvalue(), file.name)
                st.success(f"Parsed {len(variants)} variants")
                
                # Build input
                input_data = IntegratedAnalysisInput(
                    vcf_file=file.name,
                    variants=variants,
                    disease_names=[d.strip() for d in disease_names.split(",") if d.strip()] if disease_names else None,
                    drug_names=[d.strip() for d in drug_names.split(",") if d.strip()] if drug_names else None,
                    **enabled_steps,
                    max_targets=max_targets,
                    max_drugs=max_drugs,
                    min_binding_affinity=min_affinity,
                )
                
                run_ipdd_analysis(input_data, save_to_db)
                
            except Exception as e:
                st.error(f"VCF parsing failed: {e}")


def render_gene_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db) -> None:
    st.subheader("🧬 Gene List Analysis")
    st.write("Enter gene symbols to analyze disease associations, pathways, and find drugs.")
    
    genes_text = st.text_area(
        "Gene Symbols (one per line or comma-separated)",
        placeholder="TP53\nEGFR\nBRCA1\nKRAS\nPIK3CA",
        height=150,
        key="ipdd_genes_input",
    )
    
    col1, col2 = st.columns(2)
    with col1:
        disease_names = st.text_input("Disease Names (optional)", placeholder="breast cancer, melanoma", key="ipdd_genes_diseases")
    with col2:
        drug_names = st.text_input("Drug Names (optional)", placeholder="erlotinib, vemurafenib", key="ipdd_genes_drugs")
    
    # Examples
    with st.expander("📋 Example Gene Sets"):
        examples = {
            "Lung Cancer": "EGFR, KRAS, ALK, ROS1, BRAF, MET, RET, NTRK1",
            "Breast Cancer": "BRCA1, BRCA2, ERBB2, ESR1, PIK3CA, TP53, PALB2",
            "Colorectal": "APC, KRAS, TP53, PIK3CA, BRAF, SMAD4, NRAS",
            "Melanoma": "BRAF, NRAS, NF1, KIT, PTEN, CDKN2A",
        }
        cols = st.columns(len(examples))
        for i, (name, genes) in enumerate(examples.items()):
            if cols[i].button(name, key=f"ipdd_ex_{name}"):
                ss.ipdd_genes_input = genes
                st.rerun()
    
    if st.button("🚀 Run Integrated Pipeline", type="primary", use_container_width=True, key="ipdd_run_genes"):
        genes = [g.strip().upper() for g in genes_text.replace(",", "\n").split("\n") if g.strip()]
        if not genes:
            st.error("Please enter at least one gene symbol")
            return
        
        input_data = IntegratedAnalysisInput(
            gene_symbols=genes,
            disease_names=[d.strip() for d in disease_names.split(",") if d.strip()] if disease_names else None,
            drug_names=[d.strip() for d in drug_names.split(",") if d.strip()] if drug_names else None,
            **enabled_steps,
            max_targets=max_targets,
            max_drugs=max_drugs,
            min_binding_affinity=min_affinity,
        )
        
        run_ipdd_analysis(input_data, save_to_db)


def render_disease_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db) -> None:
    st.subheader("🏥 Disease-Centric Analysis")
    st.write("Enter disease names/IDs to find associated genes, pathways, targets, and drugs.")
    
    from geneai.disease_gene_pathway.api_clients import search_opentargets_diseases
    
    col1, col2 = st.columns([3, 1])
    with col1:
        disease_query = st.text_input("Search Disease", placeholder="e.g., breast cancer, Alzheimer, type 2 diabetes", key="ipdd_disease_search")
    with col2:
        st.write("")
        if st.button("🔍 Search", key="ipdd_search_disease"):
            with st.spinner("Searching OpenTargets..."):
                diseases = search_opentargets_diseases(disease_query.strip(), limit=15)
                if diseases:
                    ss.ipdd_disease_results = diseases
                    st.success(f"Found {len(diseases)} diseases")
                else:
                    st.warning("No diseases found")
    
    if "ipdd_disease_results" in ss:
        diseases = ss.ipdd_disease_results
        for i, d in enumerate(diseases):
            with st.expander(f"{d['name']} (ID: {d['id']})"):
                cols = st.columns([2, 1, 1])
                cols[0].write(f"**Description:** {d['description'] or 'N/A'}")
                if d.get("therapeutic_areas"):
                    cols[0].write(f"**Areas:** {', '.join(d['therapeutic_areas'])}")
                if cols[1].button("Analyze This Disease", key=f"ipdd_analyze_dis_{i}"):
                    input_data = IntegratedAnalysisInput(
                        disease_ids=[d["id"]],
                        disease_names=[d["name"]],
                        **enabled_steps,
                        max_targets=max_targets,
                        max_drugs=max_drugs,
                        min_binding_affinity=min_affinity,
                    )
                    run_ipdd_analysis(input_data, save_to_db)
                if cols[2].button("View Details", key=f"ipdd_detail_dis_{i}"):
                    st.json(d)
    
    # Manual disease ID entry
    st.divider()
    manual_ids = st.text_input("Or enter Disease IDs manually (EFO, MONDO, Orphanet)", placeholder="EFO_0000305, MONDO_0007254", key="ipdd_manual_diseases")
    if st.button("🚀 Analyze Disease IDs", key="ipdd_run_manual_diseases"):
        ids = [d.strip() for d in manual_ids.split(",") if d.strip()]
        if ids:
            input_data = IntegratedAnalysisInput(
                disease_ids=ids,
                **enabled_steps,
                max_targets=max_targets,
                max_drugs=max_drugs,
                min_binding_affinity=min_affinity,
            )
            run_ipdd_analysis(input_data, save_to_db)


def render_drug_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db) -> None:
    st.subheader("💊 Drug-Centric Analysis")
    st.write("Enter drug names or SMILES to analyze targets, interactions, ADMET, and repurposing.")
    
    drug_input = st.text_area(
        "Drug Names or SMILES (one per line)",
        placeholder="aspirin\nimatinib\nCC(=O)OC1=CC=CC=C1C(=O)O",
        height=120,
        key="ipdd_drugs_input",
    )
    
    target_input = st.text_input("Target Proteins (optional, gene symbols)", placeholder="EGFR, BRAF, ABL1", key="ipdd_drug_targets")
    
    if st.button("🚀 Analyze Drugs", type="primary", key="ipdd_run_drugs"):
        drugs = [d.strip() for d in drug_input.split("\n") if d.strip()]
        targets = [t.strip().upper() for t in target_input.split(",") if t.strip()] if target_input else None
        
        if not drugs:
            st.error("Please enter at least one drug")
            return
        
        # Separate names and SMILES
        drug_names = []
        drug_smiles = []
        for d in drugs:
            if any(c in d for c in "=#()[]@"):
                drug_smiles.append(d)
            else:
                drug_names.append(d)
        
        input_data = IntegratedAnalysisInput(
            drug_names=drug_names if drug_names else None,
            drug_smiles=drug_smiles if drug_smiles else None,
            target_proteins=targets,
            **enabled_steps,
            max_targets=max_targets,
            max_drugs=max_drugs,
            min_binding_affinity=min_affinity,
        )
        
        run_ipdd_analysis(input_data, save_to_db)


def render_combined_input(enabled_steps, max_targets, max_drugs, min_affinity, save_to_db) -> None:
    st.subheader("🔗 Combined Multi-Input Analysis")
    st.write("Provide multiple input types for comprehensive analysis.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Genetic Input**")
        vcf_file = st.file_uploader("VCF File (optional)", type=["vcf", "vcf.gz"], key="ipdd_combined_vcf")
        genes_text = st.text_area("Gene Symbols (optional)", placeholder="TP53, EGFR, BRCA1", height=80, key="ipdd_combined_genes")
        
        st.write("**Disease Input**")
        disease_names = st.text_input("Disease Names (optional)", placeholder="breast cancer, NSCLC", key="ipdd_combined_diseases")
        disease_ids = st.text_input("Disease IDs (optional)", placeholder="EFO_0000305, MONDO_0007254", key="ipdd_combined_disease_ids")
    
    with col2:
        st.write("**Drug Input**")
        drug_names = st.text_input("Drug Names (optional)", placeholder="tamoxifen, trastuzumab", key="ipdd_combined_drug_names")
        drug_smiles = st.text_area("Drug SMILES (optional)", placeholder="CC(=O)OC1=CC=CC=C1C(=O)O", height=80, key="ipdd_combined_drug_smiles")
        target_proteins = st.text_input("Target Proteins (optional)", placeholder="EGFR, ERBB2, ESR1", key="ipdd_combined_targets")
    
    if st.button("🚀 Run Full Integrated Analysis", type="primary", use_container_width=True, key="ipdd_run_combined"):
        # Parse all inputs
        variants = None
        if vcf_file:
            with st.spinner("Parsing VCF..."):
                variants, _ = parse_vcf(vcf_file.getvalue(), vcf_file.name)
        
        genes = [g.strip().upper() for g in genes_text.replace(",", "\n").split("\n") if g.strip()] if genes_text else None
        diseases = [d.strip() for d in disease_names.split(",") if d.strip()] if disease_names else None
        d_ids = [d.strip() for d in disease_ids.split(",") if d.strip()] if disease_ids else None
        d_names = [d.strip() for d in drug_names.split(",") if d.strip()] if drug_names else None
        d_smi = [d.strip() for d in drug_smiles.split("\n") if d.strip()] if drug_smiles else None
        targets = [t.strip().upper() for t in target_proteins.split(",") if t.strip()] if target_proteins else None
        
        # Check at least one input
        if not any([variants, genes, diseases, d_ids, d_names, d_smi, targets]):
            st.error("Please provide at least one input type")
            return
        
        input_data = IntegratedAnalysisInput(
            vcf_file=vcf_file.name if vcf_file else None,
            variants=variants,
            gene_symbols=genes,
            disease_names=diseases,
            disease_ids=d_ids,
            drug_names=d_names,
            drug_smiles=d_smi,
            target_proteins=targets,
            **enabled_steps,
            max_targets=max_targets,
            max_drugs=max_drugs,
            min_binding_affinity=min_affinity,
        )
        
        run_ipdd_analysis(input_data, save_to_db)


def run_ipdd_analysis(input_data: IntegratedAnalysisInput, save_to_db: bool) -> None:
    """Run the integrated analysis."""
    run_id = str(uuid.uuid4())[:8]
    
    with st.spinner("Running integrated precision drug discovery pipeline..."):
        try:
            result = ss.ipdd_engine.run_integrated_analysis(input_data)
            
            ss.ipdd_results[run_id] = result
            ss.ipdd_current_run = run_id
            
            if save_to_db:
                save_ipdd_to_db(run_id, result)
            
            st.success(f"Pipeline complete! Run ID: {run_id}")
            st.rerun()
            
        except Exception as e:
            st.error(f"Pipeline failed: {e}")
            import traceback
            st.code(traceback.format_exc())


def save_ipdd_to_db(run_id: str, result) -> None:
    """Save integrated analysis to database."""
    try:
        store_ipdd_analysis_run(
            run_id,
            result.timestamp,
            asdict(result.input),
            asdict(result.mutation_analysis) if result.mutation_analysis else None,
            asdict(result.disease_gene_analysis) if result.disease_gene_analysis else None,
            asdict(result.target_identification) if result.target_identification else None,
            asdict(result.drug_discovery) if result.drug_discovery else None,
            asdict(result.safety_admet) if result.safety_admet else None,
            asdict(result.literature_analysis) if result.literature_analysis else None,
            result.candidate_ranking,
            result.summary,
        )
    except Exception as e:
        st.warning(f"Database save failed: {e}")


def _load_ipdd_run(run_id: str) -> None:
    run = get_ipdd_analysis_run(run_id)
    if run:
        ss.ipdd_current_run = run_id
        st.info(f"Loaded run {run_id}. Re-run to view full results.")


def display_ipdd_results(run_id: str, result) -> None:
    """Display integrated analysis results."""
    st.divider()
    
    # Header with summary metrics
    summary = result.summary
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Variants", summary.get("variants_analyzed", 0))
    with col2:
        st.metric("Targets", summary.get("druggable_targets", 0))
    with col3:
        st.metric("Drugs Found", summary.get("drugs_found", 0))
    with col4:
        st.metric("Candidates", summary.get("candidates_ranked", 0))
    with col5:
        top = summary.get("top_candidate")
        if top:
            st.metric("Top Score", f"{top.get('score', 0):.2f}")
    
    # Pipeline steps completed
    steps = summary.get("steps_completed", [])
    st.caption(f"Pipeline Steps: {' → '.join(steps)} | Run ID: {run_id}")
    
    # Tabs for each pipeline step
    tab_names = [
        "📋 Summary",
        "🧬 Mutations",
        "🏥 Disease-Gene",
        "🎯 Targets",
        "💊 Drugs",
        "🔬 ADMET/Safety",
        "🏆 Ranked Candidates",
        "📄 Reports",
    ]
    
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        render_summary_tab(result)
    
    with tabs[1]:
        render_mutations_tab(result)
    
    with tabs[2]:
        render_disease_gene_tab(result)
    
    with tabs[3]:
        render_targets_tab(result)
    
    with tabs[4]:
        render_drugs_tab(result)
    
    with tabs[5]:
        render_admet_safety_tab(result)
    
    with tabs[6]:
        render_candidates_tab(result)
    
    with tabs[7]:
        render_ipdd_reports_tab(run_id, result)


def render_summary_tab(result) -> None:
    st.subheader("Pipeline Summary")
    
    summary = result.summary
    
    # Create a visual pipeline
    steps_info = [
        ("Mutation Analysis", "variants_analyzed", "pathogenic_variants"),
        ("Disease-Gene-Pathway", "disease_associations", "therapeutic_targets"),
        ("Target Identification", "targets_identified", "druggable_targets"),
        ("Drug Discovery", "drugs_found", "binding_affinities"),
        ("ADMET/Safety", "admet_predictions", "safety_profiles"),
        ("Literature", "papers_analyzed", ""),
    ]
    
    for i, (name, metric1, metric2) in enumerate(steps_info):
        completed = name.lower().replace(" ", "_").replace("-", "_") in [s.lower().replace(" ", "_").replace("-", "_") for s in summary.get("steps_completed", [])]
        
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            icon = "✅" if completed else "⏳"
            cols[0].write(f"{icon} **Step {i+1}: {name}**")
            if metric1 and metric1 in summary:
                cols[1].metric(metric1.replace("_", " ").title(), summary[metric1])
            if metric2 and metric2 in summary:
                cols[2].metric(metric2.replace("_", " ").title(), summary[metric2])
    
    # Top candidate highlight
    top = summary.get("top_candidate")
    if top:
        st.divider()
        st.subheader("🏆 Top Ranked Candidate")
        cols = st.columns([2, 1, 1, 1])
        cols[0].write(f"**{top.get('drug', 'Unknown')}**")
        cols[1].metric("Score", f"{top.get('score', 0):.3f}")
        cols[2].metric("ADMET", f"{top.get('admet_score', 0):.2f}" if top.get('admet_score') else "N/A")
        cols[3].metric("Safety", top.get('safety_risk', 'N/A'))
        
        if top.get("reasons"):
            st.write("**Key Reasons:**")
            for r in top["reasons"][:5]:
                st.write(f"• {r}")


def render_mutations_tab(result) -> None:
    st.subheader("Mutation Analysis")
    
    if not result.mutation_analysis:
        st.info("Mutation analysis not run or no VCF input provided.")
        return
    
    ma = result.mutation_analysis
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Variants Analyzed", ma.variants_analyzed)
    col2.metric("Pathogenic", len(ma.pathogenic_variants))
    col3.metric("Affected Genes", len(ma.affected_genes))
    
    if ma.affected_genes:
        st.write("**Affected Genes:**")
        st.write(", ".join(sorted(ma.affected_genes)))
    
    if ma.mutation_interpretations:
        st.subheader("Variant Interpretations")
        interp_data = []
        for interp in ma.mutation_interpretations:
            interp_data.append({
                "Variant": interp.get("variant", ""),
                "Gene": interp.get("gene", ""),
                "Impact": interp.get("impact", "").capitalize(),
                "Consequence": interp.get("consequence", ""),
                "Interpretation": interp.get("interpretation", ""),
            })
        st.dataframe(interp_data, use_container_width=True, hide_index=True)


def render_disease_gene_tab(result) -> None:
    st.subheader("Disease-Gene-Pathway Analysis")
    
    if not result.disease_gene_analysis:
        st.info("Disease-gene analysis not run.")
        return
    
    dg = result.disease_gene_analysis
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Disease Associations", len(dg.disease_gene_associations))
    col2.metric("Hub Genes", len(dg.hub_genes))
    col3.metric("Pathways", len(dg.pathways))
    col4.metric("Therapeutic Targets", len(dg.therapeutic_targets))
    
    # Therapeutic targets
    if dg.therapeutic_targets:
        st.subheader("🎯 Therapeutic Targets")
        target_data = []
        for t in dg.therapeutic_targets:
            target_data.append({
                "Gene": t["gene_symbol"],
                "Score": f"{t['score']:.3f}",
                "Reasons": "; ".join(t["reasons"][:2]),
            })
        st.dataframe(target_data, use_container_width=True, hide_index=True)
    
    # Hub genes
    if dg.hub_genes:
        with st.expander("🔗 Hub Genes"):
            hub_data = []
            for h in dg.hub_genes:
                hub_data.append({
                    "Gene": h["gene_symbol"],
                    "Degree": h["degree"],
                    "Betweenness": f"{h['betweenness']:.4f}",
                    "Hub": "⭐" if h["is_hub"] else "",
                    "Diseases": h["disease_count"],
                    "Pathways": h["pathways"],
                })
            st.dataframe(hub_data, use_container_width=True, hide_index=True)
    
    # Pathways
    if dg.pathways:
        with st.expander("🛤️ Pathways"):
            pw_data = []
            for p in dg.pathways:
                pw_data.append({
                    "Source": p.get("source", ""),
                    "ID": p.get("id", ""),
                    "Name": p.get("name", ""),
                    "Genes": len(p.get("genes", [])),
                })
            st.dataframe(pw_data, use_container_width=True, hide_index=True)


def render_targets_tab(result) -> None:
    st.subheader("Target Identification")
    
    if not result.target_identification:
        st.info("Target identification not run.")
        return
    
    ti = result.target_identification
    
    col1, col2 = st.columns(2)
    col1.metric("Targets Identified", len(ti.targets))
    col2.metric("Druggable Targets", len(ti.druggable_targets))
    
    if ti.target_ranking:
        st.subheader("Target Ranking")
        rank_data = []
        for i, t in enumerate(ti.target_ranking):
            rank_data.append({
                "Rank": i + 1,
                "Gene": t["gene_symbol"],
                "Druggability": f"{t.get('druggability_score', 0):.2f}",
                "Type": t.get("target_type", ""),
                "Druggable": "✅" if t in ti.druggable_targets else "",
            })
        st.dataframe(rank_data, use_container_width=True, hide_index=True)


def render_drugs_tab(result) -> None:
    st.subheader("Drug Discovery & Target Prediction")
    
    if not result.drug_discovery:
        st.info("Drug discovery not run.")
        return
    
    dd = result.drug_discovery
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Drugs Found", len(dd.drugs_found))
    col2.metric("Interactions", len(dd.drug_target_interactions))
    col3.metric("Binding Affinities", len(dd.binding_affinities))
    col4.metric("Repurposing", len(dd.repurposing_candidates))
    
    # Drugs found
    if dd.drugs_found:
        with st.expander("💊 Drugs Found"):
            drug_data = []
            for d in dd.drugs_found:
                drug_data.append({
                    "Name": d.get("name", ""),
                    "SMILES": d.get("smiles", "")[:50] + "..." if d.get("smiles", "") and len(d.get("smiles", "")) > 50 else d.get("smiles", ""),
                    "Source": d.get("source", ""),
                })
            st.dataframe(drug_data, use_container_width=True, hide_index=True)
    
    # Binding affinities
    if dd.binding_affinities:
        st.subheader("🔬 Predicted Binding Affinities")
        ba_data = []
        for ba in dd.binding_affinities:
            ba_data.append({
                "Drug": ba.get("drug", ""),
                "Target": ba.get("target", ""),
                "Affinity": f"{ba.get('affinity', 0):.2f}",
            })
        st.dataframe(ba_data, use_container_width=True, hide_index=True)
    
    # Repurposing
    if dd.repurposing_candidates:
        with st.expander("🔄 Repurposing Candidates"):
            rep_data = []
            for r in dd.repurposing_candidates:
                rep_data.append({
                    "Target": r.get("target", ""),
                    "Drug": r.get("drug", ""),
                    "Evidence": r.get("evidence", "")[:60],
                    "Phase": r.get("phase", 0),
                })
            st.dataframe(rep_data, use_container_width=True, hide_index=True)


def render_admet_safety_tab(result) -> None:
    st.subheader("ADMET & Safety Analysis")
    
    if not result.safety_admet:
        st.info("ADMET/Safety analysis not run.")
        return
    
    sa = result.safety_admet
    
    col1, col2 = st.columns(2)
    col1.metric("ADMET Predictions", len(sa.admet_predictions))
    col2.metric("Safety Profiles", len(sa.safety_profiles))
    
    # ADMET
    if sa.admet_predictions:
        st.subheader("🧪 ADMET Predictions")
        admet_data = []
        for a in sa.admet_predictions:
            admet_data.append({
                "SMILES": a.get("smiles", "")[:40] + "..." if a.get("smiles", "") else "N/A",
                "Overall Score": f"{a.get('overall_score', 0):.3f}",
                "Risk": a.get("risk_classification", ""),
                **{f"{k}": f"{v:.2f}" for k, v in a.get("category_scores", {}).items()},
            })
        st.dataframe(admet_data, use_container_width=True, hide_index=True)
    
    # Safety
    if sa.safety_profiles:
        st.subheader("🛡️ Safety Profiles")
        safety_data = []
        for s in sa.safety_profiles:
            safety_data.append({
                "SMILES": s.get("smiles", "")[:40] + "..." if s.get("smiles", "") else "N/A",
                "Risk Level": s.get("risk_level", ""),
                "Risk Score": f"{s.get('risk_score', 0):.3f}",
                "Risk Factors": s.get("risk_factors", 0),
                "Structural Alerts": s.get("structural_alerts", 0),
            })
        st.dataframe(safety_data, use_container_width=True, hide_index=True)
        
        # Highlight high risk
        high_risk = [s for s in sa.safety_profiles if s.get("risk_level") == "High"]
        if high_risk:
            st.error(f"⚠️ {len(high_risk)} compound(s) with HIGH risk level")


def render_candidates_tab(result) -> None:
    st.subheader("🏆 Ranked Drug Candidates")
    
    if not result.candidate_ranking:
        st.info("No candidates ranked. Run the full pipeline with drug discovery and ADMET/Safety enabled.")
        return
    
    # Filter
    col1, col2 = st.columns(2)
    with col1:
        min_score = st.number_input("Min Score", 0.0, 1.0, 0.0, 0.1, key="ipdd_cand_min_score")
    with col2:
        safety_filter = st.multiselect("Safety Risk", ["High", "Moderate", "Low-Moderate", "Low"], default=["High", "Moderate", "Low-Moderate", "Low"], key="ipdd_cand_safety")
    
    filtered = [
        c for c in result.candidate_ranking
        if c.get("score", 0) >= min_score and c.get("safety_risk") in safety_filter
    ]
    
    if not filtered:
        st.info("No candidates match the filters.")
        return
    
    # Table
    cand_data = []
    for c in filtered:
        cand_data.append({
            "Rank": c.get("rank", 0),
            "Drug": c.get("drug", ""),
            "Score": f"{c.get('score', 0):.3f}",
            "ADMET": f"{c.get('admet_score', 0):.2f}" if c.get("admet_score") else "N/A",
            "Safety": c.get("safety_risk", "N/A"),
            "Reasons": "; ".join(c.get("reasons", [])[:3]),
        })
    
    st.dataframe(cand_data, use_container_width=True, hide_index=True)
    
    # Visualization
    if filtered:
        fig = go.Figure(go.Bar(
            x=[c.get("score", 0) for c in reversed(filtered[:15])],
            y=[c.get("drug", "") for c in reversed(filtered[:15])],
            orientation='h',
            marker_color=['#c00000' if c.get("safety_risk") == "High" else '#bf8f00' if c.get("safety_risk") == "Moderate" else '#548235' for c in reversed(filtered[:15])],
        ))
        fig.update_layout(
            title="Top 15 Candidates by Score",
            xaxis_title="Integrated Score",
            height=max(400, len(filtered[:15]) * 30),
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Download
    df = pd.DataFrame(cand_data)
    csv = df.to_csv(index=False)
    st.download_button("⬇️ Download Candidates CSV", csv, "ranked_candidates.csv", "text/csv")


def render_ipdd_reports_tab(run_id: str, result) -> None:
    st.subheader("Generate Integrated Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", use_container_width=True, key=f"ipdd_pdf_{run_id}"):
            pdf_bytes = generate_ipdd_pdf_report(result, run_id)
            st.download_button(
                "⬇️ Download PDF", pdf_bytes,
                f"integrated_drug_discovery_{run_id}.pdf", "application/pdf",
                use_container_width=True,
            )
    
    with col2:
        if st.button("📊 Generate CSV Report", use_container_width=True, key=f"ipdd_csv_{run_id}"):
            csv_str = generate_ipdd_csv_report(result, run_id)
            st.download_button(
                "⬇️ Download CSV", csv_str,
                f"integrated_drug_discovery_{run_id}.csv", "text/csv",
                use_container_width=True,
            )
    
    with col3:
        if st.button("📋 Generate JSON Report", use_container_width=True, key=f"ipdd_json_{run_id}"):
            json_data = generate_ipdd_json_report(result, run_id)
            st.download_button(
                "⬇️ Download JSON", json.dumps(json_data, indent=2),
                f"integrated_drug_discovery_{run_id}.json", "application/json",
                use_container_width=True,
            )
    
    st.divider()
    st.write("**JSON Preview**")
    st.json(generate_ipdd_json_report(result, run_id), expanded=False)


def generate_ipdd_pdf_report(result, run_id: str) -> bytes:
    """Generate PDF report for integrated analysis."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from datetime import datetime
    import io
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []
    
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=18, spaceAfter=6, alignment=TA_CENTER, textColor=colors.HexColor("#1f4e79"))
    heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#1f4e79"))
    normal_style = styles["Normal"]
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666666"))
    
    elements.append(Spacer(1, 30*mm))
    elements.append(Paragraph("Integrated Precision Drug Discovery Report", title_style))
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(f"Run ID: {run_id}", styles["Normal"]))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    elements.append(Spacer(1, 10*mm))
    
    # Summary table
    summary = result.summary
    summary_data = [["Pipeline Step", "Key Metrics"]]
    for step in ["mutation_analysis", "disease_gene_analysis", "target_identification", "drug_discovery", "safety_admet", "literature_analysis"]:
        completed = step in summary.get("steps_completed", [])
        status = "✅ Completed" if completed else "⏭️ Skipped"
        metrics = []
        if step == "mutation_analysis":
            metrics.append(f"Variants: {summary.get('variants_analyzed', 0)}")
            metrics.append(f"Pathogenic: {summary.get('pathogenic_variants', 0)}")
        elif step == "disease_gene_analysis":
            metrics.append(f"Associations: {summary.get('disease_associations', 0)}")
            metrics.append(f"Targets: {summary.get('therapeutic_targets', 0)}")
        elif step == "target_identification":
            metrics.append(f"Identified: {summary.get('targets_identified', 0)}")
            metrics.append(f"Druggable: {summary.get('druggable_targets', 0)}")
        elif step == "drug_discovery":
            metrics.append(f"Drugs: {summary.get('drugs_found', 0)}")
            metrics.append(f"Affinities: {summary.get('binding_affinities', 0)}")
        elif step == "safety_admet":
            metrics.append(f"ADMET: {summary.get('admet_predictions', 0)}")
            metrics.append(f"Safety: {summary.get('safety_profiles', 0)}")
        summary_data.append([step.replace("_", " ").title(), status + (" - " + ", ".join(metrics) if metrics else "")])
    
    t = Table(summary_data, colWidths=[60*mm, 100*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")])]))
    elements.append(t)
    elements.append(PageBreak())
    
    # Top candidates
    elements.append(Paragraph("Top Ranked Candidates", heading_style))
    cand_data = [["Rank", "Drug", "Score", "ADMET", "Safety", "Key Reasons"]]
    for c in result.candidate_ranking[:20]:
        cand_data.append([str(c.get("rank","")), c.get("drug",""), f"{c.get('score',0):.3f}", 
                         f"{c.get('admet_score',0):.2f}" if c.get("admet_score") else "N/A",
                         c.get("safety_risk","N/A"), "; ".join(c.get("reasons",[])[:2])])
    t = Table(cand_data, colWidths=[10*mm, 25*mm, 15*mm, 15*mm, 15*mm, 70*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e79")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b4c6e7")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f2f7fb")]), ("FONTSIZE", (0,0), (-1,-1), 8)]))
    elements.append(t)
    
    # Limitations
    elements.append(PageBreak())
    elements.append(Paragraph("Limitations", heading_style))
    for lim in [
        "Computational predictions require experimental validation",
        "Drug-target interactions predicted from structure, not confirmed experimentally",
        "ADMET/Safety models trained on limited chemical space",
        "Literature analysis uses automated text mining",
        "Candidate ranking uses heuristic weights, not clinical outcomes",
    ]:
        elements.append(Paragraph(f"• {lim}", small_style))
    
    doc.build(elements)
    return buffer.getvalue()


def generate_ipdd_csv_report(result, run_id: str) -> str:
    import io, csv
    from datetime import datetime
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Integrated Precision Drug Discovery Report"])
    writer.writerow(["Run ID", run_id])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow([])
    
    writer.writerow(["Pipeline Summary"])
    for k, v in result.summary.items():
        writer.writerow([k, v])
    writer.writerow([])
    
    writer.writerow(["Ranked Candidates"])
    writer.writerow(["Rank", "Drug", "Score", "ADMET", "Safety", "Reasons"])
    for c in result.candidate_ranking:
        writer.writerow([c.get("rank"), c.get("drug"), f"{c.get('score',0):.3f}",
                        f"{c.get('admet_score',0):.3f}" if c.get("admet_score") else "",
                        c.get("safety_risk"), "; ".join(c.get("reasons",[]))])
    
    return output.getvalue()


def generate_ipdd_json_report(result, run_id: str) -> dict[str, Any]:
    from datetime import datetime
    return {
        "metadata": {"run_id": run_id, "generated_at": datetime.now().isoformat()},
        "summary": result.summary,
        "candidate_ranking": result.candidate_ranking,
        "mutation_analysis": asdict(result.mutation_analysis) if result.mutation_analysis else None,
        "disease_gene_analysis": asdict(result.disease_gene_analysis) if result.disease_gene_analysis else None,
        "target_identification": asdict(result.target_identification) if result.target_identification else None,
        "drug_discovery": asdict(result.drug_discovery) if result.drug_discovery else None,
        "safety_admet": asdict(result.safety_admet) if result.safety_admet else None,
        "literature_analysis": asdict(result.literature_analysis) if result.literature_analysis else None,
    }


if __name__ == "__main__":
    render_integrated_precision_dashboard()