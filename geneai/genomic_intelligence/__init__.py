"""Genomic Intelligence Engine package."""
from __future__ import annotations

# Core analysis
from geneai.genomic_intelligence.sequence_analyzer import (
    SequenceAnalyzer,
    SequenceFeatures,
    analyze_sequence,
)
from geneai.genomic_intelligence.variant_prioritizer import (
    VariantPrioritizer,
    VariantAnnotation,
    prioritize_variants,
)
from geneai.genomic_intelligence.gene_identifier import (
    GeneIdentifier,
    GeneInfo,
    identify_genes,
)
from geneai.genomic_intelligence.disease_associator import (
    DiseaseAssociator,
    DiseaseAssociation,
    VariantDiseaseLink,
    find_disease_genes,
    find_gene_diseases,
)
from geneai.genomic_intelligence.comparative_genomics import (
    ComparativeGenomics,
    ConservationMetrics,
    OrthologGroup,
    SyntenyBlock,
    get_conservation_scores,
)
from geneai.genomic_intelligence.visualization import (
    GenomicVisualizer,
    GenomeTrack,
    create_genome_browser,
    create_variant_effect_plot,
    create_manhattan_plot,
    create_qq_plot,
)

# UI
from geneai.genomic_intelligence.genomic_ui import render_genomic_intelligence_dashboard

__all__ = [
    # Sequence Analysis
    "SequenceAnalyzer",
    "SequenceFeatures",
    "analyze_sequence",
    # Variant Prioritization
    "VariantPrioritizer",
    "VariantAnnotation",
    "prioritize_variants",
    # Gene Identification
    "GeneIdentifier",
    "GeneInfo",
    "identify_genes",
    # Disease Association
    "DiseaseAssociator",
    "DiseaseAssociation",
    "VariantDiseaseLink",
    "find_disease_genes",
    "find_gene_diseases",
    # Comparative Genomics
    "ComparativeGenomics",
    "ConservationMetrics",
    "OrthologGroup",
    "SyntenyBlock",
    "get_conservation_scores",
    # Visualization
    "GenomicVisualizer",
    "GenomeTrack",
    "create_genome_browser",
    "create_variant_effect_plot",
    "create_manhattan_plot",
    "create_qq_plot",
    # UI
    "render_genomic_intelligence_dashboard",
]