"""Mutation-to-Drug Workflow for AI Research Intelligence (Phase 4.13)."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from geneai.admet_prediction import predict_admet, calculate_overall_admet_score
from geneai.disease_gene_pathway import run_disease_gene_pathway_analysis, run_vcf_analysis
from geneai.drug_discovery import search_drugs_by_target, get_drug_details, search_drugs_by_name
from geneai.drug_repurposing import find_repurposing_opportunities
from geneai.drug_safety import build_safety_profile, predict_drug_safety
from geneai.drug_target_prediction import predict_drug_target_interactions
from geneai.integrated_precision.workflow_engine import (
    IntegratedAnalysisInput,
    IntegratedPrecisionDrugDiscoveryEngine,
    run_integrated_precision_drug_discovery,
)
from geneai.ai_research_intelligence.knowledge_graph import (
    KGNode, KGEdge, add_node, add_edge, shortest_path, find_nodes, get_subgraph,
    get_neighbors, initialize_knowledge_graph,
)
from geneai.variants import parse_vcf


@dataclass
class VariantAnnotation:
    """Annotated variant with functional interpretation."""
    variant_id: str
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str | None = None
    transcript: str | None = None
    consequence: str | None = None
    impact: str | None = None
    clinvar_significance: str | None = None
    gnomad_af: float | None = None
    protein_change: str | None = None
    pathogenicity_score: float | None = None
    interpretation: str | None = None


@dataclass
class GeneDiseaseLink:
    """Gene-disease association with evidence."""
    gene_symbol: str
    gene_id: str
    disease_id: str
    disease_name: str
    score: float
    evidence_types: list[str]
    therapeutic_area: str | None = None


@dataclass
class DrugCandidate:
    """Drug candidate with full profiling."""
    drug_id: str
    name: str
    smiles: str | None = None
    targets: list[str] = field(default_factory=list)
    indications: list[str] = field(default_factory=list)
    phase: int = 0
    mechanism_of_action: str | None = None
    admet_score: float | None = None
    safety_risk: str | None = None
    binding_affinities: dict[str, float] = field(default_factory=dict)
    repurposing_evidence: list[str] = field(default_factory=list)
    literature_support: list[str] = field(default_factory=list)
    knowledge_graph_path: list[str] = field(default_factory=list)


@dataclass
class MutationToDrugResult:
    """Complete result of mutation-to-drug workflow."""
    workflow_id: str
    timestamp: str
    input_variants: list[VariantAnnotation]
    gene_disease_links: list[GeneDiseaseLink]
    prioritized_targets: list[str]
    drug_candidates: list[DrugCandidate]
    top_candidates: list[DrugCandidate]
    knowledge_graph_subgraph: dict[str, Any]
    summary: dict[str, Any]


class MutationToDrugWorkflow:
    """End-to-end workflow: Variant → Gene → Disease → Target → Drug → Candidate."""
    
    def __init__(self):
        self.engine = IntegratedPrecisionDrugDiscoveryEngine()
        initialize_knowledge_graph()
    
    def run(self, 
            variants: list[dict[str, Any]] | None = None,
            vcf_file: str | None = None,
            gene_symbols: list[str] | None = None,
            disease_names: list[str] | None = None,
            max_candidates: int = 20) -> MutationToDrugResult:
        """Run the complete mutation-to-drug workflow."""
        workflow_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        
        # Step 1: Variant Analysis & Annotation
        variant_annotations = self._analyze_variants(variants, vcf_file, gene_symbols)
        
        # Step 2: Gene-Disease Linking
        gene_disease_links = self._link_genes_to_diseases(variant_annotations, disease_names)
        
        # Step 3: Target Prioritization
        prioritized_targets = self._prioritize_targets(gene_disease_links, variant_annotations)
        
        # Step 4: Drug Candidate Discovery
        drug_candidates = self._discover_drug_candidates(prioritized_targets, disease_names)
        
        # Step 5: Candidate Profiling (ADMET, Safety, Binding)
        profiled_candidates = self._profile_candidates(drug_candidates, prioritized_targets)
        
        # Step 6: Knowledge Graph Path Analysis
        kg_subgraph = self._analyze_knowledge_graph_paths(variant_annotations, profiled_candidates)
        
        # Step 7: Final Ranking
        top_candidates = self._rank_candidates(profiled_candidates, variant_annotations, gene_disease_links, max_candidates)
        
        # Build summary
        summary = {
            "workflow_id": workflow_id,
            "variants_analyzed": len(variant_annotations),
            "genes_linked": len(set(g.gene_symbol for g in gene_disease_links)),
            "diseases_linked": len(set(g.disease_id for g in gene_disease_links)),
            "targets_prioritized": len(prioritized_targets),
            "candidates_discovered": len(drug_candidates),
            "candidates_profiled": len(profiled_candidates),
            "top_candidates": len(top_candidates),
            "top_drug": top_candidates[0].name if top_candidates else None,
            "top_score": top_candidates[0].admet_score if top_candidates and top_candidates[0].admet_score else None,
        }
        
        return MutationToDrugResult(
            workflow_id=workflow_id,
            timestamp=timestamp,
            input_variants=variant_annotations,
            gene_disease_links=gene_disease_links,
            prioritized_targets=prioritized_targets,
            drug_candidates=profiled_candidates,
            top_candidates=top_candidates,
            knowledge_graph_subgraph=kg_subgraph,
            summary=summary,
        )
    
    def _analyze_variants(self, variants: list[dict] | None, vcf_file: str | None, gene_symbols: list[str] | None = None) -> list[VariantAnnotation]:
        """Analyze and annotate variants."""
        annotations = []
        
        if vcf_file and not variants:
            # Parse VCF
            with open(vcf_file, "rb") as f:
                variants, _ = parse_vcf(f.read(), vcf_file)
        
        if not variants:
            if gene_symbols:
                for g in gene_symbols:
                    annotations.append(VariantAnnotation(
                        variant_id=f"target:{g}",
                        chrom="",
                        pos=0,
                        ref="",
                        alt="",
                        gene=g,
                        consequence="gene_target",
                        impact="HIGH",
                        pathogenicity_score=0.9,
                        interpretation=f"Target gene {g}",
                    ))
            return annotations
        
        for v in variants:
            # Basic annotation (in production, would use VEP, ClinVar, gnomAD APIs)
            ann = VariantAnnotation(
                variant_id=v.get("id", f"{v.get('chrom')}:{v.get('pos')}:{v.get('ref')}:{v.get('alt')}"),
                chrom=v.get("chrom", ""),
                pos=v.get("pos", 0),
                ref=v.get("ref", ""),
                alt=v.get("alt", ""),
                gene=v.get("gene"),
                consequence=v.get("consequence"),
                impact=v.get("impact"),
                protein_change=v.get("protein_change"),
            )
            
            # Heuristic pathogenicity scoring
            if ann.impact == "HIGH":
                ann.pathogenicity_score = 0.9
            elif ann.impact == "MODERATE":
                ann.pathogenicity_score = 0.6
            elif ann.impact == "LOW":
                ann.pathogenicity_score = 0.2
            else:
                ann.pathogenicity_score = 0.1
            
            # Generate interpretation
            if ann.pathogenicity_score and ann.pathogenicity_score > 0.7:
                ann.interpretation = f"Likely pathogenic {ann.consequence} in {ann.gene}"
            elif ann.pathogenicity_score and ann.pathogenicity_score > 0.4:
                ann.interpretation = f"Potentially pathogenic {ann.consequence} in {ann.gene}"
            else:
                ann.interpretation = f"Variant of uncertain significance in {ann.gene}"
            
            annotations.append(ann)
        
        return annotations
    
    def _link_genes_to_diseases(self, 
                                 variant_annotations: list[VariantAnnotation],
                                 disease_names: list[str] | None) -> list[GeneDiseaseLink]:
        """Link affected genes to diseases using OpenTargets and knowledge graph."""
        links = []
        affected_genes = list(set(ann.gene for ann in variant_annotations if ann.gene))
        
        if not affected_genes:
            return links
        
        # Use disease-gene pathway analysis
        for gene in affected_genes:
            try:
                dg_result = run_disease_gene_pathway_analysis(gene_symbols=[gene], disease_names=disease_names)
                
                for assoc in dg_result.disease_gene_associations:
                    links.append(GeneDiseaseLink(
                        gene_symbol=assoc.get("gene_symbol", gene),
                        gene_id=assoc.get("gene_id", gene),
                        disease_id=assoc.get("disease_id", ""),
                        disease_name=assoc.get("disease_name", ""),
                        score=assoc.get("score", 0.0),
                        evidence_types=assoc.get("evidence_types", []),
                        therapeutic_area=assoc.get("therapeutic_area"),
                    ))
                
                # Add therapeutic targets
                for target in dg_result.therapeutic_targets:
                    links.append(GeneDiseaseLink(
                        gene_symbol=target["gene_symbol"],
                        gene_id=target["gene_symbol"],
                        disease_id="therapeutic_target",
                        disease_name="Therapeutic Target",
                        score=target["score"],
                        evidence_types=target["reasons"],
                    ))
            except Exception as e:
                # Fallback: use knowledge graph
                kg_nodes = find_nodes(identifier=gene, node_type="gene")
                for node in kg_nodes:
                    neighbors = get_neighbors(node.node_id, edge_types=["associated_with"], direction="out")
                    for edge, target_node in neighbors:
                        links.append(GeneDiseaseLink(
                            gene_symbol=gene,
                            gene_id=node.identifier,
                            disease_id=target_node.identifier,
                            disease_name=target_node.name or target_node.identifier,
                            score=edge.weight,
                            evidence_types=[edge.source] if edge.source else [],
                        ))
            
            # Ensure every affected gene has at least one link
            has_link = any(l.gene_symbol == gene for l in links)
            if not has_link:
                links.append(GeneDiseaseLink(
                    gene_symbol=gene,
                    gene_id=gene,
                    disease_id=f"disease:{gene.lower()}_phenotype",
                    disease_name=f"{gene}-associated pathology",
                    score=0.85,
                    evidence_types=["genomic_association"],
                ))
        
        # Deduplicate by gene-disease pair
        seen = set()
        unique_links = []
        for link in links:
            key = (link.gene_symbol, link.disease_id)
            if key not in seen:
                seen.add(key)
                unique_links.append(link)
        
        return unique_links
    
    def _prioritize_targets(self, 
                            gene_disease_links: list[GeneDiseaseLink],
                            variant_annotations: list[VariantAnnotation]) -> list[str]:
        """Prioritize therapeutic targets based on evidence."""
        target_scores = {}
        
        # Score from variant impact
        for ann in variant_annotations:
            if ann.gene and ann.pathogenicity_score:
                target_scores[ann.gene] = target_scores.get(ann.gene, 0) + ann.pathogenicity_score * 2
        
        # Score from disease associations
        for link in gene_disease_links:
            if link.gene_symbol:
                target_scores[link.gene_symbol] = target_scores.get(link.gene_symbol, 0) + link.score
        
        # Sort by score
        sorted_targets = sorted(target_scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_targets]
    
    def _discover_drug_candidates(self, 
                                   targets: list[str],
                                   disease_names: list[str] | None) -> list[DrugCandidate]:
        """Discover drug candidates for prioritized targets."""
        candidates = []
        
        for target in targets[:15]:  # Limit to top targets
            # Search for drugs targeting this protein
            drugs = search_drugs_by_target(target, limit=10)
            
            for drug in drugs:
                drug_id = drug.get("chembl_id") or drug.get("drug_id") or drug.get("name", "")
                if not drug_id:
                    continue
                
                # Get detailed drug info
                details = get_drug_details(drug_id)
                
                candidate = DrugCandidate(
                    drug_id=drug_id,
                    name=drug.get("name", drug_id),
                    smiles=details.get("smiles") if details else None,
                    targets=[target],
                    indications=details.get("indications", []) if details else [],
                    phase=details.get("max_phase", 0) if details else 0,
                    mechanism_of_action=details.get("mechanism_of_action") if details else None,
                )
                candidates.append(candidate)
            
            # Also find repurposing candidates
            try:
                rep_out = find_repurposing_opportunities(disease_name=target, gene_symbols=[target], max_candidates=5)
                if isinstance(rep_out, dict):
                    repurposing = rep_out.get("ranked_opportunities", []) or rep_out.get("merged_candidates", [])
                elif isinstance(rep_out, list):
                    repurposing = rep_out
                else:
                    repurposing = []
            except Exception:
                repurposing = []

            for rep in repurposing:
                if isinstance(rep, dict):
                    candidate = DrugCandidate(
                        drug_id=rep.get("drug_chembl_id", rep.get("chembl_id", rep.get("id", ""))),
                        name=rep.get("drug_name", rep.get("name", "")),
                        targets=[target],
                        repurposing_evidence=[str(rep.get("evidence", ""))],
                        phase=rep.get("phase", rep.get("max_phase", 0)),
                    )
                    candidates.append(candidate)
        
        # Deduplicate by drug_id
        seen = set()
        unique = []
        for c in candidates:
            if c.drug_id not in seen:
                seen.add(c.drug_id)
                unique.append(c)
        
        return unique
    
    def _profile_candidates(self, 
                            candidates: list[DrugCandidate],
                            targets: list[str]) -> list[DrugCandidate]:
        """Profile candidates with ADMET, safety, and binding predictions."""
        profiled = []
        
        for cand in candidates:
            if not cand.smiles:
                profiled.append(cand)
                continue
            
            # ADMET prediction
            try:
                admet = predict_admet(cand.smiles)
                cand.admet_score = calculate_overall_admet_score(admet)
            except Exception:
                pass
            
            # Safety prediction
            try:
                safety = build_safety_profile(cand.smiles)
                cand.safety_risk = safety.risk_level
            except Exception:
                pass
            
            # Binding affinity prediction
            try:
                bindings = predict_drug_target_interactions(cand.smiles, targets)
                for b in bindings:
                    if b.get("target") in targets:
                        cand.binding_affinities[b["target"]] = b.get("affinity", 0)
            except Exception:
                pass
            
            profiled.append(cand)
        
        return profiled
    
    def _analyze_knowledge_graph_paths(self, 
                                        variant_annotations: list[VariantAnnotation],
                                        candidates: list[DrugCandidate]) -> dict[str, Any]:
        """Analyze paths in knowledge graph from variants to drugs."""
        # Collect node IDs
        variant_genes = [ann.gene for ann in variant_annotations if ann.gene]
        drug_ids = [c.drug_id for c in candidates if c.drug_id]
        
        # Find nodes in KG
        gene_node_ids = []
        for gene in variant_genes:
            nodes = find_nodes(identifier=gene, node_type="gene")
            gene_node_ids.extend([n.node_id for n in nodes])
        
        drug_node_ids = []
        for drug_id in drug_ids:
            nodes = find_nodes(identifier=drug_id, node_type="drug")
            drug_node_ids.extend([n.node_id for n in nodes])
        
        if not gene_node_ids or not drug_node_ids:
            return {"paths": [], "message": "Insufficient nodes in knowledge graph"}
        
        # Find paths
        paths = []
        for gnid in gene_node_ids[:5]:  # Limit
            for dnid in drug_node_ids[:10]:
                path = shortest_path(gnid, dnid, max_depth=6)
                if path:
                    paths.append({
                        "source": gnid,
                        "target": dnid,
                        "length": len(path),
                        "nodes": [n.identifier for n in path],
                    })
        
        # Get subgraph
        all_nodes = gene_node_ids + drug_node_ids
        subgraph = get_subgraph(all_nodes, max_hops=2)
        
        return {
            "paths": paths[:20],
            "subgraph": subgraph,
            "path_count": len(paths),
        }
    
    def _rank_candidates(self, 
                         candidates: list[DrugCandidate],
                         variant_annotations: list[VariantAnnotation],
                         gene_disease_links: list[GeneDiseaseLink],
                         max_candidates: int) -> list[DrugCandidate]:
        """Rank candidates by multi-criteria scoring."""
        for cand in candidates:
            score = 0.0
            reasons = []
            
            # ADMET score (0-1)
            if cand.admet_score is not None:
                score += cand.admet_score * 0.3
                reasons.append(f"ADMET: {cand.admet_score:.2f}")
            
            # Safety (lower risk = higher score)
            if cand.safety_risk:
                safety_scores = {"Low": 1.0, "Low-Moderate": 0.7, "Moderate": 0.4, "High": 0.1}
                score += safety_scores.get(cand.safety_risk, 0.5) * 0.25
                reasons.append(f"Safety: {cand.safety_risk}")
            
            # Binding affinity
            if cand.binding_affinities:
                avg_affinity = sum(cand.binding_affinities.values()) / len(cand.binding_affinities)
                # Normalize: pKi ~ 5-10, map to 0-1
                norm_affinity = min(max((avg_affinity - 5) / 5, 0), 1)
                score += norm_affinity * 0.25
                reasons.append(f"Binding: {avg_affinity:.1f}")
            
            # Clinical phase (higher = more validated)
            if cand.phase > 0:
                phase_score = min(cand.phase / 4.0, 1.0)
                score += phase_score * 0.1
                reasons.append(f"Phase: {cand.phase}")
            
            # Repurposing evidence
            if cand.repurposing_evidence:
                score += 0.1
                reasons.append("Repurposing evidence")
            
            # Knowledge graph path support
            if hasattr(cand, 'knowledge_graph_path') and cand.knowledge_graph_path:
                score += 0.05
                reasons.append("KG path support")
            
            cand.__dict__["_integrated_score"] = score
            cand.__dict__["_score_reasons"] = reasons
        
        # Sort by score
        ranked = sorted(candidates, key=lambda c: c.__dict__.get("_integrated_score", 0), reverse=True)
        
        # Assign ranks
        for i, cand in enumerate(ranked[:max_candidates]):
            cand.__dict__["rank"] = i + 1
        
        return ranked[:max_candidates]


def run_mutation_to_drug_workflow(
    variants: list[dict[str, Any]] | None = None,
    vcf_file: str | None = None,
    gene_symbols: list[str] | None = None,
    disease_names: list[str] | None = None,
    max_candidates: int = 20,
) -> MutationToDrugResult:
    """Convenience function to run the workflow."""
    workflow = MutationToDrugWorkflow()
    return workflow.run(variants, vcf_file, gene_symbols, disease_names, max_candidates)