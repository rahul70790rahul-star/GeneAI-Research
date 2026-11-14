"""Integrated Precision Drug Discovery - Phase 4.12: Master workflow engine."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from geneai.admet_prediction import predict_admet, calculate_overall_admet_score
from geneai.biomarker_discovery import run_biomarker_discovery
from geneai.disease_gene_pathway import run_disease_gene_pathway_analysis, run_vcf_analysis
from geneai.drug_discovery import (
    search_drugs_by_target,
    get_drug_details,
    search_drugs_by_name,
)
from geneai.drug_repurposing import find_repurposing_opportunities
from geneai.drug_safety import build_safety_profile, predict_drug_safety
from geneai.drug_target_prediction import predict_drug_target_interactions
from geneai.research_analysis import analyze_paper
from geneai.variants import parse_vcf


@dataclass
class IntegratedAnalysisInput:
    """Input for integrated drug discovery analysis."""
    # Genetic input
    vcf_file: str | None = None
    variants: list[dict[str, Any]] | None = None
    gene_symbols: list[str] | None = None
    mutations: list[dict[str, Any]] | None = None
    
    # Disease input
    disease_names: list[str] | None = None
    disease_ids: list[str] | None = None  # EFO, MONDO, etc.
    
    # Drug input
    drug_names: list[str] | None = None
    drug_smiles: list[str] | None = None
    target_proteins: list[str] | None = None
    
    # Analysis options
    run_mutation_analysis: bool = True
    run_disease_gene_analysis: bool = True
    run_pathway_analysis: bool = True
    run_target_identification: bool = True
    run_drug_search: bool = True
    run_drug_target_prediction: bool = True
    run_repurposing: bool = True
    run_admet: bool = True
    run_safety: bool = True
    run_biomarker: bool = False
    run_literature: bool = True
    
    # Parameters
    max_targets: int = 20
    max_drugs: int = 50
    min_binding_affinity: float = 5.0
    admet_threshold: float = 0.5


@dataclass
class MutationAnalysisResult:
    """Results from mutation analysis step."""
    variants_analyzed: int
    pathogenic_variants: list[dict[str, Any]]
    affected_genes: list[str]
    mutation_interpretations: list[dict[str, Any]]


@dataclass
class DiseaseGeneResult:
    """Results from disease-gene analysis."""
    disease_gene_associations: list[dict[str, Any]]
    hub_genes: list[dict[str, Any]]
    pathways: list[dict[str, Any]]
    go_enrichment: dict[str, list[dict[str, Any]]]
    therapeutic_targets: list[dict[str, Any]]


@dataclass
class TargetIdentificationResult:
    """Results from target identification."""
    targets: list[dict[str, Any]]
    druggable_targets: list[dict[str, Any]]
    target_ranking: list[dict[str, Any]]


@dataclass
class DrugDiscoveryResult:
    """Results from drug search and target prediction."""
    drugs_found: list[dict[str, Any]]
    drug_target_interactions: list[dict[str, Any]]
    binding_affinities: list[dict[str, Any]]
    repurposing_candidates: list[dict[str, Any]]


@dataclass
class SafetyAdmetResult:
    """Results from ADMET and safety analysis."""
    admet_predictions: list[dict[str, Any]]
    safety_profiles: list[dict[str, Any]]
    toxicity_predictions: list[dict[str, Any]]


@dataclass
class LiteratureResult:
    """Results from literature analysis."""
    papers_analyzed: int
    key_findings: list[dict[str, Any]]
    evidence_summary: dict[str, Any]


@dataclass
class IntegratedDrugDiscoveryResult:
    """Complete integrated drug discovery result."""
    run_id: str
    timestamp: str
    input: IntegratedAnalysisInput
    mutation_analysis: MutationAnalysisResult | None = None
    disease_gene_analysis: DiseaseGeneResult | None = None
    target_identification: TargetIdentificationResult | None = None
    drug_discovery: DrugDiscoveryResult | None = None
    safety_admet: SafetyAdmetResult | None = None
    literature_analysis: LiteratureResult | None = None
    candidate_ranking: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class IntegratedPrecisionDrugDiscoveryEngine:
    """Master engine connecting all drug discovery modules."""
    
    def __init__(self):
        self.run_history: list[IntegratedDrugDiscoveryResult] = []
    
    def run_integrated_analysis(
        self,
        input_data: IntegratedAnalysisInput,
    ) -> IntegratedDrugDiscoveryResult:
        """Run the complete integrated drug discovery workflow."""
        run_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        
        result = IntegratedDrugDiscoveryResult(
            run_id=run_id,
            timestamp=timestamp,
            input=input_data,
        )
        
        # Step 1: Mutation Analysis (from VCF or variants)
        if input_data.run_mutation_analysis and (input_data.vcf_file or input_data.variants):
            result.mutation_analysis = self._run_mutation_analysis(input_data)
        
        # Step 2: Disease-Gene-Pathway Analysis
        if input_data.run_disease_gene_analysis:
            genes = input_data.gene_symbols or []
            if result.mutation_analysis:
                genes.extend(result.mutation_analysis.affected_genes)
            genes = list(set(genes))
            
            disease_ids = input_data.disease_ids or []
            disease_names = input_data.disease_names or []
            
            if genes or disease_ids or disease_names:
                result.disease_gene_analysis = self._run_disease_gene_analysis(
                    genes, disease_ids + disease_names
                )
        
        # Step 3: Target Identification
        if input_data.run_target_identification:
            target_genes = []
            if result.disease_gene_analysis:
                target_genes = [t["gene_symbol"] for t in result.disease_gene_analysis.therapeutic_targets[:input_data.max_targets]]
            elif result.mutation_analysis:
                target_genes = result.mutation_analysis.affected_genes[:input_data.max_targets]
            elif input_data.target_proteins:
                target_genes = input_data.target_proteins
            
            if target_genes:
                result.target_identification = self._run_target_identification(target_genes)
        
        # Step 4: Drug Discovery & Target Prediction
        if input_data.run_drug_search or input_data.run_drug_target_prediction or input_data.run_repurposing:
            drugs_to_analyze = []
            targets_to_analyze = []
            
            if input_data.drug_names:
                drugs_to_analyze.extend(input_data.drug_names)
            if input_data.drug_smiles:
                drugs_to_analyze.extend(input_data.drug_smiles)
            if result.target_identification:
                targets_to_analyze = [t["gene_symbol"] for t in result.target_identification.druggable_targets]
            if input_data.target_proteins:
                targets_to_analyze.extend(input_data.target_proteins)
            
            result.drug_discovery = self._run_drug_discovery(
                drugs_to_analyze, targets_to_analyze,
                input_data.run_drug_target_prediction,
                input_data.run_repurposing,
                input_data.min_binding_affinity,
            )
        
        # Step 5: ADMET & Safety
        if input_data.run_admet or input_data.run_safety:
            compounds = []
            if input_data.drug_smiles:
                compounds.extend(input_data.drug_smiles)
            if result.drug_discovery:
                for drug in result.drug_discovery.drugs_found:
                    if drug.get("smiles"):
                        compounds.append(drug["smiles"])
            
            # Deduplicate
            compounds = list(dict.fromkeys(compounds))
            
            if compounds:
                result.safety_admet = self._run_safety_admet(
                    compounds, input_data.run_admet, input_data.run_safety
                )
        
        # Step 6: Literature Analysis
        if input_data.run_literature:
            query_terms = []
            if input_data.disease_names:
                query_terms.extend(input_data.disease_names)
            if result.mutation_analysis:
                query_terms.extend(result.mutation_analysis.affected_genes[:5])
            if result.target_identification:
                query_terms.extend([t["gene_symbol"] for t in result.target_identification.targets[:5]])
            
            if query_terms:
                result.literature_analysis = self._run_literature_analysis(query_terms)
        
        # Step 7: Candidate Ranking
        result.candidate_ranking = self._rank_candidates(result)
        
        # Generate summary
        result.summary = self._generate_summary(result)
        
        # Store in history
        self.run_history.append(result)
        
        return result
    
    def _run_mutation_analysis(self, input_data: IntegratedAnalysisInput) -> MutationAnalysisResult:
        """Run mutation analysis from VCF or variant list."""
        variants = input_data.variants or []
        
        if input_data.vcf_file:
            # Parse VCF file
            try:
                with open(input_data.vcf_file, 'rb') as f:
                    variants, _ = parse_vcf(f.read(), input_data.vcf_file)
            except Exception as e:
                return MutationAnalysisResult(
                    variants_analyzed=0,
                    pathogenic_variants=[],
                    affected_genes=[],
                    mutation_interpretations=[{"error": str(e)}],
                )
        
        # Analyze variants
        affected_genes = []
        pathogenic = []
        interpretations = []
        
        for var in variants:
            gene = var.get("gene") or var.get("SYMBOL") or var.get("GENE")
            if gene:
                affected_genes.append(gene)
            
            # Simple pathogenicity assessment
            impact = var.get("IMPACT", "").lower()
            if impact in ("high", "moderate"):
                pathogenic.append(var)
                interpretations.append({
                    "variant": f"{var.get('CHROM', '')}:{var.get('POS', '')} {var.get('REF', '')}>{var.get('ALT', '')}",
                    "gene": gene,
                    "impact": impact,
                    "consequence": var.get("Consequence", ""),
                    "interpretation": f"Potential {impact} impact variant in {gene or 'unknown gene'}",
                })
        
        return MutationAnalysisResult(
            variants_analyzed=len(variants),
            pathogenic_variants=pathogenic,
            affected_genes=list(set(affected_genes)),
            mutation_interpretations=interpretations,
        )
    
    def _run_disease_gene_analysis(
        self, genes: list[str], diseases: list[str]
    ) -> DiseaseGeneResult:
        """Run disease-gene-pathway analysis."""
        if not genes and not diseases:
            return DiseaseGeneResult(
                disease_gene_associations=[],
                hub_genes=[],
                pathways=[],
                go_enrichment={},
                therapeutic_targets=[],
            )
        
        dgp_result = run_disease_gene_pathway_analysis(genes, diseases)
        
        # Convert to serializable format
        hub_genes = []
        for h in dgp_result.hub_genes:
            hub_genes.append({
                "gene_symbol": h.gene_symbol,
                "degree": h.degree,
                "betweenness": h.betweenness_centrality,
                "is_hub": h.is_hub,
                "disease_count": len(h.disease_associations),
                "pathways": h.pathways,
            })
        
        pathways = []
        for p in dgp_result.kegg_pathways:
            pathways.append({
                "source": "KEGG",
                "id": p.pathway_id,
                "name": p.name,
                "genes": p.genes,
            })
        for p in dgp_result.reactome_pathways:
            pathways.append({
                "source": "Reactome",
                "id": p.pathway_id,
                "name": p.name,
                "genes": p.genes,
            })
        
        therapeutic_targets = []
        for t in dgp_result.therapeutic_targets:
            therapeutic_targets.append({
                "gene_symbol": t["gene_symbol"],
                "score": t["score"],
                "reasons": t["reasons"],
            })
        
        disease_associations = []
        for a in dgp_result.disease_gene_associations:
            disease_associations.append({
                "disease": a.disease_name,
                "gene": a.gene_symbol,
                "score": a.score,
            })
        
        return DiseaseGeneResult(
            disease_gene_associations=disease_associations,
            hub_genes=hub_genes,
            pathways=pathways,
            go_enrichment=dgp_result.go_enrichment,
            therapeutic_targets=therapeutic_targets,
        )
    
    def _run_target_identification(self, genes: list[str]) -> TargetIdentificationResult:
        """Run target identification and druggability analysis."""
        # This would integrate with drug_discovery.target_identification
        # For now, return structured results based on gene list
        
        targets = []
        druggable = []
        
        for gene in genes:
            target_info = {
                "gene_symbol": gene,
                "target_type": "protein",
                "druggability_score": 0.5,  # Placeholder
            }
            targets.append(target_info)
            
            # Simple heuristic: known drug targets are more druggable
            known_targets = {"EGFR", "BRAF", "ALK", "HER2", "VEGFR", "PDGFR", "BTK", "JAK2", "BCR-ABL"}
            if gene in known_targets:
                target_info["druggability_score"] = 0.9
                druggable.append(target_info)
        
        # Rank by druggability
        targets.sort(key=lambda x: x["druggability_score"], reverse=True)
        
        return TargetIdentificationResult(
            targets=targets,
            druggable_targets=druggable,
            target_ranking=targets,
        )
    
    def _run_drug_discovery(
        self,
        drugs: list[str],
        targets: list[str],
        run_target_prediction: bool,
        run_repurposing: bool,
        min_affinity: float,
    ) -> DrugDiscoveryResult:
        """Run drug search, target prediction, and repurposing."""
        drugs_found = []
        interactions = []
        binding_affinities = []
        repurposing = []
        
        # Search drugs by name
        for drug in drugs:
            if any(c.isalpha() for c in drug) and not all(c in "CNOSPFClBrI()[]=#-+@" for c in drug):
                # Looks like a name
                results = search_drugs_by_name(drug)
                for r in results[:5]:
                    drugs_found.append({
                        "name": r.get("name", drug),
                        "smiles": r.get("canonical_smiles"),
                        "cid": r.get("cid"),
                        "source": "PubChem search",
                    })
            else:
                # Looks like SMILES
                drugs_found.append({
                    "smiles": drug,
                    "source": "Direct SMILES input",
                })
        
        # Drug-target prediction
        if run_target_prediction and drugs_found and targets:
            for drug in drugs_found[:10]:  # Limit
                smiles = drug.get("smiles")
                if smiles:
                    for target in targets[:10]:
                        try:
                            pred = predict_drug_target_interactions(smiles, target)
                            if pred:
                                interactions.append({
                                    "drug": drug.get("name", drug.get("smiles", "")[:20]),
                                    "target": target,
                                    "binding_affinity": pred.get("predicted_affinity"),
                                    "confidence": pred.get("confidence"),
                                })
                                if pred.get("predicted_affinity", 0) >= min_affinity:
                                    binding_affinities.append({
                                        "drug": drug.get("name", "Unknown"),
                                        "target": target,
                                        "affinity": pred.get("predicted_affinity"),
                                    })
                        except Exception:
                            pass
        
        # Repurposing
        if run_repurposing and targets:
            for target in targets[:5]:
                try:
                    candidates = find_repurposing_candidates(target)
                    for c in candidates[:5]:
                        repurposing.append({
                            "target": target,
                            "drug": c.get("drug_name", ""),
                            "evidence": c.get("evidence", ""),
                            "phase": c.get("max_phase", 0),
                        })
                except Exception:
                    pass
        
        return DrugDiscoveryResult(
            drugs_found=drugs_found,
            drug_target_interactions=interactions,
            binding_affinities=binding_affinities,
            repurposing_candidates=repurposing,
        )
    
    def _run_safety_admet(
        self, compounds: list[str], run_admet: bool, run_safety: bool
    ) -> SafetyAdmetResult:
        """Run ADMET and safety predictions."""
        admet_predictions = []
        safety_profiles = []
        toxicity_predictions = []
        
        for smiles in compounds[:10]:  # Limit for performance
            # ADMET
            if run_admet:
                try:
                    admet = predict_admet(smiles)
                    score = calculate_overall_admet_score(admet)
                    admet_predictions.append({
                        "smiles": smiles,
                        "overall_score": score.overall_score,
                        "risk_classification": score.risk_classification,
                        "category_scores": {k: v.score for k, v in score.category_scores.items()},
                    })
                except Exception as e:
                    admet_predictions.append({"smiles": smiles, "error": str(e)})
            
            # Safety
            if run_safety:
                try:
                    safety = build_safety_profile(smiles=smiles)
                    safety_profiles.append({
                        "smiles": smiles,
                        "risk_level": safety.risk_assessment.get("risk_level"),
                        "risk_score": safety.risk_assessment.get("risk_score"),
                        "risk_factors": safety.risk_assessment.get("risk_factors", []),
                        "structural_alerts": sum(1 for v in safety.structural_alerts.values() if v > 0),
                    })
                    
                    # ML toxicity predictions would go here
                    toxicity_predictions.append({
                        "smiles": smiles,
                        "endpoints_available": len(safety.molecular_properties),
                    })
                except Exception as e:
                    safety_profiles.append({"smiles": smiles, "error": str(e)})
        
        return SafetyAdmetResult(
            admet_predictions=admet_predictions,
            safety_profiles=safety_profiles,
            toxicity_predictions=toxicity_predictions,
        )
    
    def _run_literature_analysis(self, query_terms: list[str]) -> LiteratureResult:
        """Run literature analysis."""
        # This would integrate with research_analysis
        # For now, return placeholder
        return LiteratureResult(
            papers_analyzed=0,
            key_findings=[],
            evidence_summary={"query_terms": query_terms},
        )
    
    def _rank_candidates(self, result: IntegratedDrugDiscoveryResult) -> list[dict[str, Any]]:
        """Rank drug candidates based on all evidence."""
        candidates = []
        
        if not result.drug_discovery or not result.drug_discovery.drugs_found:
            return candidates
        
        for drug in result.drug_discovery.drugs_found:
            score = 0.0
            reasons = []
            
            # Binding affinity evidence
            for ba in result.drug_discovery.binding_affinities:
                if ba.get("drug") == drug.get("name") or ba.get("drug") == drug.get("smiles", "")[:20]:
                    affinity = ba.get("affinity", 0)
                    score += min(affinity / 10.0, 1.0) * 0.3
                    reasons.append(f"Binding affinity: {affinity:.1f}")
            
            # ADMET score
            for admet in result.safety_admet.admet_predictions if result.safety_admet else []:
                if admet.get("smiles") == drug.get("smiles"):
                    score += admet.get("overall_score", 0) * 0.25
                    reasons.append(f"ADMET: {admet.get('overall_score', 0):.2f}")
            
            # Safety profile
            for safety in result.safety_admet.safety_profiles if result.safety_admet else []:
                if safety.get("smiles") == drug.get("smiles"):
                    risk_score = safety.get("risk_score", 0)
                    score += (1 - risk_score) * 0.2
                    if risk_score > 0.5:
                        reasons.append(f"Safety concern: {risk_score:.2f}")
            
            # Repurposing evidence
            for rep in result.drug_discovery.repurposing_candidates:
                if rep.get("drug") == drug.get("name"):
                    score += 0.15
                    reasons.append(f"Repurposing evidence for {rep.get('target')}")
            
            # Target relevance
            if result.target_identification:
                for target in result.target_identification.druggable_targets:
                    for ba in result.drug_discovery.binding_affinities:
                        if ba.get("target") == target.get("gene_symbol"):
                            score += target.get("druggability_score", 0) * 0.1
            
            candidates.append({
                "drug": drug.get("name", drug.get("smiles", "Unknown")[:30]),
                "smiles": drug.get("smiles"),
                "score": round(score, 3),
                "reasons": reasons,
                "admet_score": next((a.get("overall_score") for a in (result.safety_admet.admet_predictions if result.safety_admet else []) if a.get("smiles") == drug.get("smiles")), None),
                "safety_risk": next((s.get("risk_level") for s in (result.safety_admet.safety_profiles if result.safety_admet else []) if s.get("smiles") == drug.get("smiles")), None),
                "binding_affinities": [ba for ba in result.drug_discovery.binding_affinities if ba.get("drug") == drug.get("name") or ba.get("drug") == drug.get("smiles", "")[:20]],
            })
        
        # Sort by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Add ranks
        for i, c in enumerate(candidates):
            c["rank"] = i + 1
        
        return candidates
    
    def _generate_summary(self, result: IntegratedDrugDiscoveryResult) -> dict[str, Any]:
        """Generate analysis summary."""
        summary = {
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "steps_completed": [],
        }
        
        if result.mutation_analysis:
            summary["steps_completed"].append("mutation_analysis")
            summary["variants_analyzed"] = result.mutation_analysis.variants_analyzed
            summary["pathogenic_variants"] = len(result.mutation_analysis.pathogenic_variants)
            summary["affected_genes"] = len(result.mutation_analysis.affected_genes)
        
        if result.disease_gene_analysis:
            summary["steps_completed"].append("disease_gene_analysis")
            summary["disease_associations"] = len(result.disease_gene_analysis.disease_gene_associations)
            summary["hub_genes"] = len(result.disease_gene_analysis.hub_genes)
            summary["pathways"] = len(result.disease_gene_analysis.pathways)
            summary["therapeutic_targets"] = len(result.disease_gene_analysis.therapeutic_targets)
        
        if result.target_identification:
            summary["steps_completed"].append("target_identification")
            summary["targets_identified"] = len(result.target_identification.targets)
            summary["druggable_targets"] = len(result.target_identification.druggable_targets)
        
        if result.drug_discovery:
            summary["steps_completed"].append("drug_discovery")
            summary["drugs_found"] = len(result.drug_discovery.drugs_found)
            summary["interactions_predicted"] = len(result.drug_discovery.drug_target_interactions)
            summary["binding_affinities"] = len(result.drug_discovery.binding_affinities)
            summary["repurposing_candidates"] = len(result.drug_discovery.repurposing_candidates)
        
        if result.safety_admet:
            summary["steps_completed"].append("safety_admet")
            summary["admet_predictions"] = len(result.safety_admet.admet_predictions)
            summary["safety_profiles"] = len(result.safety_admet.safety_profiles)
        
        if result.literature_analysis:
            summary["steps_completed"].append("literature_analysis")
        
        summary["candidates_ranked"] = len(result.candidate_ranking)
        summary["top_candidate"] = result.candidate_ranking[0] if result.candidate_ranking else None
        
        return summary
    
    def get_run_history(self) -> list[dict[str, Any]]:
        """Get history of all runs."""
        return [
            {
                "run_id": r.run_id,
                "timestamp": r.timestamp,
                "summary": r.summary,
            }
            for r in self.run_history
        ]
    
    def export_run(self, run_id: str, format: str = "json") -> str | bytes:
        """Export a run result."""
        run = next((r for r in self.run_history if r.run_id == run_id), None)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        # Convert to dict
        run_dict = {
            "run_id": run.run_id,
            "timestamp": run.timestamp,
            "input": asdict(run.input),
            "mutation_analysis": asdict(run.mutation_analysis) if run.mutation_analysis else None,
            "disease_gene_analysis": asdict(run.disease_gene_analysis) if run.disease_gene_analysis else None,
            "target_identification": asdict(run.target_identification) if run.target_identification else None,
            "drug_discovery": asdict(run.drug_discovery) if run.drug_discovery else None,
            "safety_admet": asdict(run.safety_admet) if run.safety_admet else None,
            "literature_analysis": asdict(run.literature_analysis) if run.literature_analysis else None,
            "candidate_ranking": run.candidate_ranking,
            "summary": run.summary,
        }
        
        if format == "json":
            return json.dumps(run_dict, indent=2)
        elif format == "csv":
            # Flatten for CSV
            import io
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Field", "Value"])
            for key, value in run_dict.items():
                writer.writerow([key, json.dumps(value) if value else ""])
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")


def run_integrated_precision_drug_discovery(
    input_data: IntegratedAnalysisInput,
) -> IntegratedDrugDiscoveryResult:
    """Convenience function to run integrated analysis."""
    engine = IntegratedPrecisionDrugDiscoveryEngine()
    return engine.run_integrated_analysis(input_data)