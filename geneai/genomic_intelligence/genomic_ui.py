"""Streamlit UI for Genomic Intelligence Engine."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from geneai.genomic_intelligence import (
    analyze_sequence,
    prioritize_variants,
    identify_genes,
    find_disease_genes,
    find_gene_diseases,
    get_conservation_scores,
)
from geneai.genomic_intelligence.visualization import (
    GenomicVisualizer,
    GenomeTrack,
    create_genome_browser,
)


def render_genomic_intelligence_dashboard() -> None:
    """Render the Genomic Intelligence Engine dashboard."""
    st.set_page_config(page_title="Genomic Intelligence", layout="wide")
    
    st.title("🧬 Genomic Intelligence Engine")
    st.markdown("""
    Advanced genomic research engine for sequence analysis, variant prioritization,
    gene identification, disease association, and comparative genomics.
    """)
    
    # Sidebar navigation
    with st.sidebar:
        st.header("Analysis Modules")
        module = st.radio(
            "Select Module",
            [
                "Sequence Analysis",
                "Variant Prioritization",
                "Gene Identification",
                "Disease Association",
                "Comparative Genomics",
                "Genome Browser",
            ],
            label_visibility="collapsed",
        )
        
        st.divider()
        st.caption("Data Sources")
        st.caption("• Ensembl/NCBI for gene annotations")
        st.caption("• gnomAD for population frequencies")
        st.caption("• ClinVar for clinical significance")
        st.caption("• GWAS Catalog for trait associations")
        st.caption("• UCSC for conservation scores")
    
    # Module content
    if module == "Sequence Analysis":
        render_sequence_analysis()
    elif module == "Variant Prioritization":
        render_variant_prioritization()
    elif module == "Gene Identification":
        render_gene_identification()
    elif module == "Disease Association":
        render_disease_association()
    elif module == "Comparative Genomics":
        render_comparative_genomics()
    elif module == "Genome Browser":
        render_genome_browser()


def render_sequence_analysis() -> None:
    """Render sequence analysis interface."""
    st.subheader("Sequence Analysis")
    st.write("Analyze DNA, RNA, or protein sequences for genomic features.")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        seq_type = st.selectbox(
            "Sequence Type",
            ["auto", "dna", "rna", "protein"],
            help="Auto-detect from sequence composition"
        )
        
        uploaded = st.file_uploader(
            "Upload FASTA/FASTQ",
            type=["fa", "fasta", "fna", "fastq", "fq", "txt"],
        )
        
        raw = st.text_area(
            "Or paste sequence",
            height=200,
            placeholder=">seq1\nATGCGTACGTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGC...",
        )
        
        analyze_btn = st.button("Analyze Sequence", type="primary")
    
    with col2:
        if analyze_btn:
            sequence = ""
            if uploaded:
                # Parse FASTA/FASTQ
                content = uploaded.getvalue().decode("utf-8")
                lines = content.strip().split("\n")
                sequence = "".join(l for l in lines if not l.startswith(">") and not l.startswith("@"))
            elif raw:
                lines = raw.strip().split("\n")
                sequence = "".join(l for l in lines if not l.startswith(">"))
            
            if sequence:
                with st.spinner("Analyzing..."):
                    features = analyze_sequence(sequence, seq_type)
                
                display_sequence_features(features)
            else:
                st.warning("Please provide a sequence")


def display_sequence_features(features) -> None:
    """Display sequence analysis results."""
    st.subheader("Analysis Results")
    
    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Length", f"{features.length:,}")
    m2.metric("GC Content", f"{features.gc_content:.1f}%")
    m3.metric("GC Skew", f"{features.gc_skew:.3f}")
    m4.metric("AT Skew", f"{features.at_skew:.3f}")
    
    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Molecular Weight", f"{features.molecular_weight:,.0f} Da")
    
    if features.isoelectric_point:
        m6.metric("pI", f"{features.isoelectric_point:.2f}")
    if features.hydrophobicity:
        m7.metric("GRAVY", f"{features.hydrophobicity:.2f}")
    if features.instability_index:
        m8.metric("Instability", f"{features.instability_index:.1f}")
    
    # Composition
    if features.composition:
        with st.expander("Nucleotide/Amino Acid Composition"):
            comp_df = pd.DataFrame(
                [{"Residue": k, "Percentage": f"{v:.1f}%"} for k, v in features.composition.items()]
            )
            st.dataframe(comp_df, hide_index=True)
            
            # Bar chart
            fig = go.Figure(go.Bar(
                x=list(features.composition.keys()),
                y=list(features.composition.values()),
                marker_color="#1f77b4",
            ))
            fig.update_layout(
                title="Composition",
                xaxis_title="Residue",
                yaxis_title="Percentage (%)",
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # CpG Islands
    if features.cpg_islands:
        with st.expander("CpG Islands"):
            cpg_df = pd.DataFrame(features.cpg_islands)
            st.dataframe(cpg_df, hide_index=True)
    
    # ORFs
    if features.orfs:
        with st.expander(f"Open Reading Frames (top {len(features.orfs)})"):
            orf_df = pd.DataFrame([
                {
                    "Frame": o["frame"],
                    "Start": o["start"],
                    "End": o["end"],
                    "Length (aa)": o["length_aa"],
                    "Protein": o["protein"][:50] + "..." if len(o["protein"]) > 50 else o["protein"],
                }
                for o in features.orfs[:20]
            ])
            st.dataframe(orf_df, hide_index=True)
    
    # Motifs
    if features.motif_matches:
        with st.expander("Motif Matches"):
            for motif, positions in features.motif_matches.items():
                st.write(f"**{motif}**: {len(positions)} matches at positions {positions[:20]}")
    
    # Repeats
    if features.repeats:
        with st.expander("Repeat Elements"):
            rep_df = pd.DataFrame(features.repeats)
            st.dataframe(rep_df, hide_index=True)


def render_variant_prioritization() -> None:
    """Render variant prioritization interface."""
    st.subheader("Variant Prioritization")
    st.write("Prioritize genetic variants for disease relevance using multiple evidence sources.")
    
    with st.form("variant_form"):
        st.write("**Input Variants**")
        input_method = st.radio(
            "Input Method",
            ["Paste VCF-like data", "Upload VCF", "Manual entry"],
            horizontal=True,
        )
        
        variants_text = ""
        if input_method == "Paste VCF-like data":
            variants_text = st.text_area(
                "Variants (TSV: chrom pos ref alt gene consequence impact)",
                height=150,
                placeholder="chr1\t12345\tA\tG\tBRCA1\tmissense_variant\tMODERATE\nchr17\t43071235\tG\tA\tTP53\tstop_gained\tHIGH",
            )
        elif input_method == "Manual entry":
            vcol1, vcol2, vcol3, vcol4 = st.columns(4)
            with vcol1:
                chrom = st.text_input("Chromosome", "chr1")
            with vcol2:
                pos = st.number_input("Position", value=12345)
            with vcol3:
                ref = st.text_input("Ref", "A")
            with vcol4:
                alt = st.text_input("Alt", "G")
            
            if st.form_submit_button("Add Variant"):
                st.session_state.setdefault("manual_variants", []).append({
                    "chrom": chrom, "pos": pos, "ref": ref, "alt": alt,
                })
                st.rerun()
        
        # Disease context
        st.write("**Disease Context (Optional)**")
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            disease_genes = st.text_input(
                "Disease Genes (comma-separated)",
                placeholder="BRCA1, TP53, PALB2",
            )
        with dcol2:
            disease_phenotypes = st.text_input(
                "Disease Phenotypes",
                placeholder="Breast cancer, Ovarian cancer",
            )
        
        max_af = st.slider("Max Allele Frequency", 0.0, 0.1, 0.01, 0.001)
        
        submitted = st.form_submit_button("Prioritize Variants", type="primary")
    
    if submitted:
        variants = []
        
        if input_method == "Paste VCF-like data" and variants_text:
            for line in variants_text.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 4:
                    variant = {
                        "chrom": parts[0],
                        "pos": int(parts[1]),
                        "ref": parts[2],
                        "alt": parts[3],
                    }
                    if len(parts) > 4:
                        variant["gene_symbol"] = parts[4]
                    if len(parts) > 5:
                        variant["consequence"] = parts[5]
                    if len(parts) > 6:
                        variant["impact"] = parts[6]
                    variants.append(variant)
        elif input_method == "Manual entry":
            variants = st.session_state.get("manual_variants", [])
        
        if variants:
            with st.spinner("Prioritizing variants..."):
                gene_list = [g.strip() for g in disease_genes.split(",")] if disease_genes else None
                pheno_list = [p.strip() for p in disease_phenotypes.split(",")] if disease_phenotypes else None
                
                results = prioritize_variants(
                    variants,
                    disease_genes=gene_list,
                    disease_phenotypes=pheno_list,
                    max_af=max_af,
                )
            
            display_prioritized_variants(results)
        else:
            st.warning("No variants provided")


def display_prioritized_variants(results: list) -> None:
    """Display prioritized variant results."""
    st.subheader(f"Results: {len(results)} variants")
    
    # Summary metrics
    tier_counts = {}
    for r in results:
        tier_counts[r.priority_tier] = tier_counts.get(r.priority_tier, 0) + 1
    
    cols = st.columns(len(tier_counts))
    for i, (tier, count) in enumerate(sorted(tier_counts.items())):
        cols[i].metric(tier, count)
    
    # Results table
    df_data = []
    for r in results:
        df_data.append({
            "Variant": f"{r.chrom}:{r.pos} {r.ref}>{r.alt}",
            "Gene": r.gene_symbol or "-",
            "Consequence": r.consequence or "-",
            "Impact": r.impact or "-",
            "Protein": r.protein_change or "-",
            "gnomAD AF": f"{r.gnomad_af:.4f}" if r.gnomad_af else "-",
            "CADD": f"{r.cadd_phred:.1f}" if r.cadd_phred else "-",
            "REVEL": f"{r.revel_score:.2f}" if r.revel_score else "-",
            "ClinVar": r.clinvar_significance or "-",
            "Score": f"{r.priority_score:.1f}",
            "Tier": r.priority_tier,
            "Evidence": "; ".join(r.evidence_tags[:3]),
        })
    
    df = pd.DataFrame(df_data)
    st.dataframe(df, hide_index=True, use_container_width=True)
    
    # Download
    st.download_button(
        "Download Results (CSV)",
        df.to_csv(index=False),
        "variant_prioritization.csv",
        "text/csv",
    )


def render_gene_identification() -> None:
    """Render gene identification interface."""
    st.subheader("Gene Identification")
    st.write("Resolve gene identifiers across databases (Ensembl, Entrez, UniProt, HGNC).")
    
    with st.form("gene_form"):
        identifiers = st.text_area(
            "Gene Identifiers (one per line)",
            height=150,
            placeholder="BRCA1\nTP53\nENSG00000141510\n7157\nP04637",
        )
        
        id_type = st.selectbox(
            "Identifier Type",
            ["auto", "symbol", "ensembl", "entrez", "uniprot", "hgnc"],
        )
        
        species = st.selectbox(
            "Species",
            ["human", "mouse", "rat", "zebrafish"],
        )
        
        submitted = st.form_submit_button("Identify Genes", type="primary")
    
    if submitted and identifiers:
        id_list = [i.strip() for i in identifiers.strip().split("\n") if i.strip()]
        
        with st.spinner("Resolving identifiers..."):
            results = identify_genes(id_list, id_type, species)
        
        if results:
            df_data = []
            for g in results:
                df_data.append({
                    "Input": g.symbol,
                    "Symbol": g.symbol,
                    "Ensembl": g.ensembl_id or "-",
                    "Entrez": g.entrez_id or "-",
                    "UniProt": g.uniprot_id or "-",
                    "HGNC": g.hgnc_id or "-",
                    "Chromosome": g.chromosome or "-",
                    "Location": f"{g.start:,}-{g.end:,}" if g.start and g.end else "-",
                    "Biotype": g.biotype or "-",
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, hide_index=True, use_container_width=True)
            
            st.download_button(
                "Download Results (CSV)",
                df.to_csv(index=False),
                "gene_identification.csv",
                "text/csv",
            )
        else:
            st.warning("No genes found")


def render_disease_association() -> None:
    """Render disease association interface."""
    st.subheader("Disease Association Analysis")
    st.write("Find disease-gene and disease-variant associations from multiple databases.")
    
    tab1, tab2, tab3 = st.tabs(["Disease → Genes", "Gene → Diseases", "Variant → Diseases"])
    
    with tab1:
        disease_query = st.text_input(
            "Disease Query",
            placeholder="Breast cancer, OMIM:114480, Orpha:99799, HP:0003002",
        )
        
        if st.button("Search Disease Genes", type="primary") and disease_query:
            with st.spinner("Searching..."):
                results = find_disease_genes(disease_query)
            
            if results:
                df = pd.DataFrame([{
                    "Disease": r.disease_name,
                    "Source": r.disease_source,
                    "Gene": r.gene_symbol,
                    "Type": r.association_type,
                    "Score": f"{r.evidence_score:.2f}",
                    "PMIDs": ", ".join(r.pmid_list[:3]),
                } for r in results])
                st.dataframe(df, hide_index=True)
            else:
                st.info("No associations found")
    
    with tab2:
        gene_query = st.text_input(
            "Gene Symbol",
            placeholder="BRCA1, TP53, CFTR",
        )
        
        if st.button("Search Gene Diseases", type="primary") and gene_query:
            with st.spinner("Searching..."):
                results = find_gene_diseases(gene_query)
            
            if results:
                df = pd.DataFrame([{
                    "Disease": r.disease_name,
                    "Source": r.disease_source,
                    "Type": r.association_type,
                    "Score": f"{r.evidence_score:.2f}",
                    "PMIDs": ", ".join(r.pmid_list[:3]),
                } for r in results])
                st.dataframe(df, hide_index=True)
            else:
                st.info("No associations found")
    
    with tab3:
        st.info("Variant-disease lookup requires ClinVar integration")


def render_comparative_genomics() -> None:
    """Render comparative genomics interface."""
    st.subheader("Comparative Genomics")
    st.write("Analyze sequence conservation, orthologs, and synteny across species.")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "Conservation Scores", "Orthologs", "Synteny", "Positive Selection"
    ])
    
    with tab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            chrom = st.text_input("Chromosome", "chr1")
        with col2:
            start = st.number_input("Start", value=1000000)
        with col3:
            end = st.number_input("End", value=1050000)
        
        species = st.multiselect(
            "Species",
            ["human", "chimp", "mouse", "rat", "dog", "cow", "chicken", "zebrafish"],
            default=["human", "chimp", "mouse"],
        )
        
        if st.button("Get Conservation", type="primary"):
            with st.spinner("Fetching conservation scores..."):
                metrics = get_conservation_scores(chrom, start, end, species)
            
            if metrics.species_scores:
                st.write(f"Mean conservation: {metrics.mean_conservation:.3f}")
                st.write(f"Max conservation: {metrics.max_conservation:.3f}")
                
                fig = go.Figure(go.Bar(
                    x=list(metrics.species_scores.keys()),
                    y=list(metrics.species_scores.values()),
                ))
                fig.update_layout(title="Conservation by Species", height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No conservation data available")
    
    with tab2:
        gene = st.text_input("Gene Symbol", "BRCA1")
        target_species = st.multiselect(
            "Target Species",
            ["chimp", "mouse", "rat", "dog", "cow", "zebrafish"],
            default=["chimp", "mouse"],
        )
        
        if st.button("Find Orthologs", type="primary"):
            st.info("Ortholog lookup requires Ensembl Compara integration")
    
    with tab3:
        st.info("Synteny analysis requires Ensembl Compara integration")
    
    with tab4:
        gene = st.text_input("Gene for Selection Analysis", "BRCA1")
        if st.button("Detect Selection", type="primary"):
            st.info("Positive selection detection requires PAML/HyPhy integration")


def render_genome_browser() -> None:
    """Render genome browser interface."""
    st.subheader("Genome Browser")
    st.write("Interactive multi-track genome browser.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        chrom = st.text_input("Chromosome", "chr17")
    with col2:
        start = st.number_input("Start", value=43044000)
    with col3:
        end = st.number_input("End", value=43170000)
    
    # Demo tracks
    tracks = []
    
    # Gene track
    gene_data = [
        {"start": 43044295, "end": 43125483, "symbol": "BRCA1", "strand": -1},
    ]
    tracks.append(GenomeTrack(
        name="Genes (RefSeq)",
        data=gene_data,
        track_type="genes",
        color="#1f77b4",
        height=100,
    ))
    
    # Variant track (demo)
    variant_data = [
        {"pos": 43045612, "impact": "HIGH", "gene_symbol": "BRCA1", "consequence": "stop_gained"},
        {"pos": 43071235, "impact": "HIGH", "gene_symbol": "BRCA1", "consequence": "frameshift_variant"},
        {"pos": 43093110, "impact": "MODERATE", "gene_symbol": "BRCA1", "consequence": "missense_variant"},
    ]
    tracks.append(GenomeTrack(
        name="Variants",
        data=variant_data,
        track_type="variants",
        height=80,
    ))
    
    # Conservation track (demo)
    import numpy as np
    cons_positions = np.linspace(start, end, 100)
    cons_scores = np.random.beta(2, 5, 100)
    cons_data = [{"pos": int(p), "coverage": float(s)} for p, s in zip(cons_positions, cons_scores)]
    tracks.append(GenomeTrack(
        name="PhastCons",
        data=cons_data,
        track_type="conservation",
        color="#2ca02c",
        height=100,
    ))
    
    if st.button("Render Browser", type="primary"):
        with st.spinner("Rendering genome browser..."):
            fig = create_genome_browser(chrom, start, end, tracks)
        st.plotly_chart(fig, use_container_width=True)


# Import numpy for genome browser demo
import numpy as np