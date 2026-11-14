"""Variant prioritization module for genomic intelligence."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VariantAnnotation:
    """Annotated variant with prioritization scores."""
    chrom: str
    pos: int
    ref: str
    alt: str
    gene_symbol: str | None = None
    gene_id: str | None = None
    transcript_id: str | None = None
    consequence: str | None = None
    impact: str | None = None  # HIGH, MODERATE, LOW, MODIFIER
    protein_change: str | None = None
    
    # Population frequencies
    gnomad_af: float | None = None
    gnomad_af_popmax: float | None = None
    gnomad_ac: int | None = None
    gnomad_an: int | None = None
    thousand_genomes_af: float | None = None
    
    # Functional predictions
    sift_score: float | None = None
    sift_prediction: str | None = None
    polyphen_score: float | None = None
    polyphen_prediction: str | None = None
    cadd_raw: float | None = None
    cadd_phred: float | None = None
    revel_score: float | None = None
    splice_ai: float | None = None
    
    # Clinical significance
    clinvar_significance: str | None = None
    clinvar_review_status: str | None = None
    clinvar_diseases: list[str] = field(default_factory=list)
    
    # Database IDs
    rsid: str | None = None
    cosmic_id: str | None = None
    
    # Prioritization scores
    priority_score: float = 0.0
    priority_tier: str = "Tier 5"  # Tier 1-5
    
    # Evidence
    evidence_tags: list[str] = field(default_factory=list)


class VariantPrioritizer:
    """
    Prioritize genetic variants for disease relevance.
    
    Integrates:
    - Population frequency (gnomAD, 1000 Genomes)
    - Functional predictions (SIFT, PolyPhen, CADD, REVEL, SpliceAI)
    - Clinical significance (ClinVar)
    - Gene-disease associations
    - Pathway context
    """
    
    # Impact severity weights
    IMPACT_WEIGHTS = {
        "HIGH": 1.0,
        "MODERATE": 0.6,
        "LOW": 0.2,
        "MODIFIER": 0.1,
    }
    
    # Consequence severity
    CONSEQUENCE_WEIGHTS = {
        "transcript_ablation": 1.0,
        "splice_acceptor_variant": 0.95,
        "splice_donor_variant": 0.95,
        "stop_gained": 0.95,
        "frameshift_variant": 0.9,
        "stop_lost": 0.85,
        "start_lost": 0.8,
        "transcript_amplification": 0.7,
        "inframe_insertion": 0.6,
        "inframe_deletion": 0.6,
        "missense_variant": 0.5,
        "protein_altering_variant": 0.5,
        "splice_region_variant": 0.4,
        "incomplete_terminal_codon_variant": 0.3,
        "start_retained_variant": 0.2,
        "stop_retained_variant": 0.2,
        "synonymous_variant": 0.1,
        "coding_sequence_variant": 0.1,
        "mature_miRNA_variant": 0.1,
        "5_prime_UTR_variant": 0.05,
        "3_prime_UTR_variant": 0.05,
        "non_coding_transcript_exon_variant": 0.05,
        "intron_variant": 0.01,
        "NMD_transcript_variant": 0.01,
        "non_coding_transcript_variant": 0.01,
        "upstream_gene_variant": 0.005,
        "downstream_gene_variant": 0.005,
        "TF_binding_site_variant": 0.005,
        "regulatory_region_variant": 0.005,
        "intergenic_variant": 0.001,
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def prioritize_variants(
        self,
        variants: list[dict[str, Any]],
        disease_genes: list[str] | None = None,
        disease_phenotypes: list[str] | None = None,
        max_af: float = 0.01,
    ) -> list[VariantAnnotation]:
        """
        Prioritize a list of variants.
        
        Args:
            variants: List of variant dicts with chrom, pos, ref, alt
            disease_genes: Optional list of disease-associated genes
            disease_phenotypes: Optional list of HPO terms or disease names
            max_af: Maximum allele frequency for rare variant filtering
            
        Returns:
            List of annotated and prioritized variants
        """
        annotated = []
        
        for variant in variants:
            annotated_variant = self._annotate_variant(variant)
            annotated.append(annotated_variant)
        
        # Filter by allele frequency
        filtered = [v for v in annotated if self._passes_frequency_filter(v, max_af)]
        
        # Score and rank
        scored = self._score_variants(filtered, disease_genes, disease_phenotypes)
        
        # Sort by priority score
        scored.sort(key=lambda v: v.priority_score, reverse=True)
        
        # Assign tiers
        self._assign_tiers(scored)
        
        return scored
    
    def _annotate_variant(self, variant: dict[str, Any]) -> VariantAnnotation:
        """Annotate a single variant with all available data."""
        # This would integrate with external APIs in production
        # For now, create a structured annotation object
        
        return VariantAnnotation(
            chrom=variant.get("chrom", variant.get("chr", "")),
            pos=variant.get("pos", variant.get("position", 0)),
            ref=variant.get("ref", ""),
            alt=variant.get("alt", ""),
            gene_symbol=variant.get("gene_symbol"),
            gene_id=variant.get("gene_id"),
            transcript_id=variant.get("transcript_id"),
            consequence=variant.get("consequence"),
            impact=variant.get("impact"),
            protein_change=variant.get("protein_change"),
            gnomad_af=variant.get("gnomad_af"),
            gnomad_af_popmax=variant.get("gnomad_af_popmax"),
            gnomad_ac=variant.get("gnomad_ac"),
            gnomad_an=variant.get("gnomad_an"),
            thousand_genomes_af=variant.get("thousand_genomes_af"),
            sift_score=variant.get("sift_score"),
            sift_prediction=variant.get("sift_prediction"),
            polyphen_score=variant.get("polyphen_score"),
            polyphen_prediction=variant.get("polyphen_prediction"),
            cadd_raw=variant.get("cadd_raw"),
            cadd_phred=variant.get("cadd_phred"),
            revel_score=variant.get("revel_score"),
            splice_ai=variant.get("splice_ai"),
            clinvar_significance=variant.get("clinvar_significance"),
            clinvar_review_status=variant.get("clinvar_review_status"),
            clinvar_diseases=variant.get("clinvar_diseases", []),
            rsid=variant.get("rsid"),
            cosmic_id=variant.get("cosmic_id"),
        )
    
    def _passes_frequency_filter(self, variant: VariantAnnotation, max_af: float) -> bool:
        """Check if variant passes allele frequency filter."""
        # Use the most conservative frequency
        frequencies = [
            variant.gnomad_af,
            variant.gnomad_af_popmax,
            variant.thousand_genomes_af,
        ]
        valid_freqs = [f for f in frequencies if f is not None]
        
        if not valid_freqs:
            return True  # No frequency data, don't filter
        
        return min(valid_freqs) <= max_af
    
    def _score_variants(
        self,
        variants: list[VariantAnnotation],
        disease_genes: list[str] | None,
        disease_phenotypes: list[str] | None,
    ) -> list[VariantAnnotation]:
        """Calculate priority scores for variants."""
        
        for variant in variants:
            score = 0.0
            evidence = []
            
            # 1. Consequence severity
            if variant.consequence:
                cons_weight = self.CONSEQUENCE_WEIGHTS.get(variant.consequence, 0.01)
                score += cons_weight * 30  # Max 30 points
                evidence.append(f"consequence:{variant.consequence}")
            
            # 2. Impact
            if variant.impact:
                impact_weight = self.IMPACT_WEIGHTS.get(variant.impact, 0.1)
                score += impact_weight * 20  # Max 20 points
                evidence.append(f"impact:{variant.impact}")
            
            # 3. Functional predictions
            # CADD
            if variant.cadd_phred is not None:
                cadd_score = min(variant.cadd_phred / 40.0, 1.0)  # Normalize to 40
                score += cadd_score * 15
                evidence.append(f"cadd:{variant.cadd_phred:.1f}")
            
            # REVEL
            if variant.revel_score is not None:
                score += variant.revel_score * 10
                evidence.append(f"revel:{variant.revel_score:.2f}")
            
            # SIFT (deleterious if < 0.05)
            if variant.sift_score is not None:
                if variant.sift_score < 0.05:
                    score += 10
                    evidence.append("sift:deleterious")
            
            # PolyPhen (probably damaging if > 0.9)
            if variant.polyphen_score is not None:
                if variant.polyphen_score > 0.9:
                    score += 10
                    evidence.append("polyphen:damaging")
            
            # SpliceAI
            if variant.splice_ai is not None:
                if variant.splice_ai > 0.5:
                    score += 15
                    evidence.append(f"spliceai:{variant.splice_ai:.2f}")
            
            # 4. Clinical significance
            if variant.clinvar_significance:
                sig = variant.clinvar_significance.lower()
                if "pathogenic" in sig:
                    score += 25
                    evidence.append("clinvar:pathogenic")
                elif "likely pathogenic" in sig:
                    score += 20
                    evidence.append("clinvar:likely_pathogenic")
                elif "uncertain" in sig:
                    score += 5
                    evidence.append("clinvar:vus")
                elif "benign" in sig:
                    score -= 10
                    evidence.append("clinvar:benign")
            
            # 5. Disease gene match
            if disease_genes and variant.gene_symbol in disease_genes:
                score += 20
                evidence.append(f"disease_gene:{variant.gene_symbol}")
            
            # 6. Known disease associations from ClinVar
            if variant.clinvar_diseases and disease_phenotypes:
                for disease in variant.clinvar_diseases:
                    if any(pheno.lower() in disease.lower() for pheno in disease_phenotypes):
                        score += 15
                        evidence.append(f"clinvar_disease:{disease}")
            
            # 7. Protein change severity
            if variant.protein_change:
                # Truncating variants
                if any(x in variant.protein_change for x in ["*", "fs", "del", "ins", "dup"]):
                    score += 10
                    evidence.append("truncating")
                # Missense at conserved residue (simplified)
                elif "missense" in str(variant.consequence).lower():
                    score += 5
                    evidence.append("missense")
            
            # 8. Population frequency (rarer = higher score)
            if variant.gnomad_af is not None:
                if variant.gnomad_af == 0:
                    score += 10
                    evidence.append("gnomad:absent")
                elif variant.gnomad_af < 0.0001:
                    score += 8
                    evidence.append("gnomad:ultra_rare")
                elif variant.gnomad_af < 0.001:
                    score += 5
                    evidence.append("gnomad:rare")
            
            # 9. COSMIC (cancer mutations)
            if variant.cosmic_id:
                score += 10
                evidence.append(f"cosmic:{variant.cosmic_id}")
            
            variant.priority_score = round(score, 2)
            variant.evidence_tags = evidence
        
        return variants
    
    def _assign_tiers(self, variants: list[VariantAnnotation]) -> None:
        """Assign priority tiers based on scores."""
        for variant in variants:
            if variant.priority_score >= 60:
                variant.priority_tier = "Tier 1"  # High confidence pathogenic
            elif variant.priority_score >= 40:
                variant.priority_tier = "Tier 2"  # Likely pathogenic
            elif variant.priority_score >= 25:
                variant.priority_tier = "Tier 3"  # VUS with supporting evidence
            elif variant.priority_score >= 15:
                variant.priority_tier = "Tier 4"  # Low evidence
            else:
                variant.priority_tier = "Tier 5"  # Likely benign


def prioritize_variants(
    variants: list[dict[str, Any]],
    disease_genes: list[str] | None = None,
    disease_phenotypes: list[str] | None = None,
    max_af: float = 0.01,
) -> list[VariantAnnotation]:
    """Convenience function for variant prioritization."""
    prioritizer = VariantPrioritizer()
    return prioritizer.prioritize_variants(variants, disease_genes, disease_phenotypes, max_af)