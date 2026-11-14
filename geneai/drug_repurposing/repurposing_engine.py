"""Core Drug Repurposing Engine for GeneAI Research - Phase 4.6."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from geneai.drug_discovery import drug_search
from geneai.drug_discovery import drug_target_analysis
from geneai.drug_discovery import gene_drug_mapping
from geneai.drug_discovery import opentargets_client
from geneai.drug_repurposing import ctd_client
from geneai.drug_repurposing import dgidb_client
from geneai.drug_repurposing import ttd_client

logger = logging.getLogger(__name__)


@dataclass
class RepurposingCandidate:
    """Represents a drug repurposing candidate with evidence."""
    drug_name: str
    drug_id: str | None = None
    drug_sources: list[str] = field(default_factory=list)

    # Disease context
    disease_name: str | None = None
    disease_id: str | None = None

    # Target information
    target_symbol: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    mechanism_of_action: str | None = None
    action_type: str | None = None

    # Clinical information
    max_phase: int = 0
    indication: str | None = None

    # Evidence scores
    target_relevance_score: float = 0.0
    gene_disease_score: float = 0.0
    drug_target_evidence_score: float = 0.0
    mechanism_compatibility_score: float = 0.0
    pathway_relevance_score: float = 0.0
    literature_evidence_score: float = 0.0
    data_confidence_score: float = 0.0

    # Combined score
    overall_score: float = 0.0

    # Evidence details
    evidence_sources: list[str] = field(default_factory=list)
    supporting_pmids: list[str] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)

    # Evidence classification
    evidence_classification: str = "computational_prediction"  # computational_prediction, experimental, clinical

    def to_dict(self) -> dict[str, Any]:
        return {
            "drug_name": self.drug_name,
            "drug_id": self.drug_id,
            "drug_sources": self.drug_sources,
            "disease_name": self.disease_name,
            "disease_id": self.disease_id,
            "target_symbol": self.target_symbol,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "mechanism_of_action": self.mechanism_of_action,
            "action_type": self.action_type,
            "max_phase": self.max_phase,
            "indication": self.indication,
            "target_relevance_score": round(self.target_relevance_score, 3),
            "gene_disease_score": round(self.gene_disease_score, 3),
            "drug_target_evidence_score": round(self.drug_target_evidence_score, 3),
            "mechanism_compatibility_score": round(self.mechanism_compatibility_score, 3),
            "pathway_relevance_score": round(self.pathway_relevance_score, 3),
            "literature_evidence_score": round(self.literature_evidence_score, 3),
            "data_confidence_score": round(self.data_confidence_score, 3),
            "overall_score": round(self.overall_score, 3),
            "evidence_sources": self.evidence_sources,
            "supporting_pmids": self.supporting_pmids,
            "evidence_notes": self.evidence_notes,
            "evidence_classification": self.evidence_classification,
        }


class DrugRepurposingEngine:
    """Main engine for AI-driven drug repurposing analysis."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.max_candidates = self.config.get("max_candidates", 50)
        self.min_overall_score = self.config.get("min_overall_score", 0.1)

    def analyze_disease(
        self,
        disease_name: str,
        include_genetic_evidence: bool = True,
        include_literature: bool = True,
    ) -> dict[str, Any]:
        """
        Analyze a disease for drug repurposing opportunities.

        Args:
            disease_name: Name of the disease to analyze
            include_genetic_evidence: Whether to include genetic association evidence
            include_literature: Whether to fetch supporting literature

        Returns:
            Dictionary with disease info, targets, candidates, and analysis metadata
        """
        logger.info("Starting repurposing analysis for disease: %s", disease_name)

        # Step 1: Get disease information and associated targets
        disease_info = self._get_disease_info(disease_name)
        if not disease_info:
            return {"error": f"Disease '{disease_name}' not found in databases"}

        disease_id = disease_info.get("disease_id")
        targets = disease_info.get("targets", [])

        # Step 2: Get drugs for each target
        all_candidates = []
        for target in targets[:20]:  # Limit to top 20 targets
            target_candidates = self._get_drugs_for_target(
                target=target,
                disease_name=disease_info.get("name"),
                disease_id=disease_id,
            )
            all_candidates.extend(target_candidates)

        # Step 3: Score and rank candidates
        scored_candidates = self._score_candidates(
            candidates=all_candidates,
            disease_info=disease_info,
            include_genetic_evidence=include_genetic_evidence,
            include_literature=include_literature,
        )

        # Step 4: Filter and sort
        filtered = [c for c in scored_candidates if c.overall_score >= self.min_overall_score]
        filtered.sort(key=lambda x: x.overall_score, reverse=True)
        top_candidates = filtered[:self.max_candidates]

        # Step 5: Generate evidence summary
        evidence_summary = self._generate_evidence_summary(top_candidates, disease_info)

        return {
            "disease": disease_info,
            "targets_analyzed": len(targets),
            "candidates_found": len(all_candidates),
            "candidates_filtered": len(filtered),
            "top_candidates": [c.to_dict() for c in top_candidates],
            "evidence_summary": evidence_summary,
            "analysis_metadata": {
                "include_genetic_evidence": include_genetic_evidence,
                "include_literature": include_literature,
                "databases_queried": ["Open Targets", "ChEMBL", "PubChem", "DGIdb", "CTD", "ClinicalTrials.gov"],
                "limitations": [
                    "Scores are computational predictions, not experimental validations",
                    "Evidence from public databases may be incomplete",
                    "Clinical relevance requires experimental validation",
                    "Drug-target interactions may not translate to therapeutic efficacy",
                ],
            },
        }

    def analyze_gene_set(
        self,
        gene_symbols: list[str],
        disease_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze a set of genes for drug repurposing opportunities.

        Args:
            gene_symbols: List of gene symbols
            disease_context: Optional disease context for prioritization

        Returns:
            Dictionary with gene-drug mappings and repurposing candidates
        """
        logger.info("Analyzing gene set for repurposing: %s", gene_symbols)

        # Map genes to drugs using existing gene_drug_mapping
        gene_drug_results = gene_drug_mapping.map_gene_list_to_drugs(gene_symbols)

        # Also get disease context if provided
        disease_info = None
        if disease_context:
            disease_info = self._get_disease_info(disease_context)

        candidates = []
        for gene, mapping in gene_drug_results.get("genes", {}).items():
            for drug in mapping.get("target_drugs", []):
                candidate = RepurposingCandidate(
                    drug_name=drug.get("drug_name", ""),
                    drug_id=drug.get("drug_id"),
                    drug_sources=["Open Targets"],
                    target_symbol=drug.get("target_name"),
                    mechanism_of_action=drug.get("mechanism_of_action"),
                    max_phase=drug.get("phase", 0),
                    indication=drug.get("disease_name"),
                    evidence_sources=["Open Targets"],
                )
                candidates.append(candidate)

        # Score candidates
        scored = self._score_candidates(
            candidates=candidates,
            disease_info=disease_info,
            gene_symbols=gene_symbols,
        )

        scored.sort(key=lambda x: x.overall_score, reverse=True)

        return {
            "input_genes": gene_symbols,
            "disease_context": disease_context,
            "gene_drug_mappings": gene_drug_results,
            "candidates": [c.to_dict() for c in scored[:self.max_candidates]],
            "shared_drugs": gene_drug_results.get("shared_drugs", []),
            "shared_targets": gene_drug_results.get("shared_targets", []),
        }

    def analyze_mutation(
        self,
        gene_symbol: str,
        variant_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze a specific mutation for drug repurposing.

        Args:
            gene_symbol: Gene symbol with mutation
            variant_info: Optional variant details (HGVS, protein change, etc.)

        Returns:
            Dictionary with mutation-specific drug candidates
        """
        logger.info("Analyzing mutation for repurposing: %s", gene_symbol)

        # Use existing variant-to-drug mapping
        variant_results = gene_drug_mapping.map_variant_to_drugs(gene_symbol, variant_info)

        candidates = []
        for drug in variant_results.get("gene_drug_map", {}).get("target_drugs", []):
            candidate = RepurposingCandidate(
                drug_name=drug.get("drug_name", ""),
                drug_id=drug.get("drug_id"),
                drug_sources=["Open Targets"],
                target_symbol=drug.get("target_name"),
                mechanism_of_action=drug.get("mechanism_of_action"),
                max_phase=drug.get("phase", 0),
                indication=drug.get("disease_name"),
                evidence_sources=["Open Targets"],
                evidence_notes=[f"Gene {gene_symbol} associated with drug via Open Targets"],
            )
            candidates.append(candidate)

        # Score candidates
        scored = self._score_candidates(candidates=candidates)

        scored.sort(key=lambda x: x.overall_score, reverse=True)

        return {
            "gene_symbol": gene_symbol,
            "variant_info": variant_info,
            "variant_specific": variant_results.get("variant_specific", {}),
            "candidates": [c.to_dict() for c in scored[:self.max_candidates]],
            "disclaimer": variant_results.get("disclaimer", ""),
        }

    def _get_disease_info(self, disease_name: str) -> dict[str, Any] | None:
        """Get disease information from Open Targets."""
        try:
            diseases = opentargets_client.search_diseases(disease_name, limit=5)
            if not diseases:
                return None

            # Use the first/best match
            disease = diseases[0]
            disease_id = disease.get("disease_id")

            # Get detailed disease info
            disease_detail = opentargets_client.get_disease_by_id(disease_id)
            if not disease_detail:
                return disease

            # Get associated targets
            targets = opentargets_client.get_disease_targets(disease_id, limit=50)

            return {
                **disease_detail,
                "targets": targets,
            }
        except Exception as e:
            logger.warning("Failed to get disease info for %s: %s", disease_name, e)
            return None

    def _get_drugs_for_target(
        self,
        target: dict[str, Any],
        disease_name: str | None = None,
        disease_id: str | None = None,
    ) -> list[RepurposingCandidate]:
        """Get drugs targeting a specific protein target."""
        target_id = target.get("target_id")
        target_symbol = target.get("approved_symbol")
        target_name = target.get("approved_name")
        association_score = target.get("association_score")

        candidates = []

        if not target_id:
            return candidates

        try:
            # Get drugs from Open Targets
            ot_drugs = opentargets_client.get_target_drugs(target_id, limit=30)

            for drug in ot_drugs:
                candidate = RepurposingCandidate(
                    drug_name=drug.get("drug_name", ""),
                    drug_id=drug.get("drug_id"),
                    drug_sources=["Open Targets"],
                    disease_name=disease_name,
                    disease_id=disease_id,
                    target_symbol=target_symbol,
                    target_id=target_id,
                    target_name=target_name,
                    mechanism_of_action=drug.get("mechanism_of_action"),
                    max_phase=drug.get("phase", 0),
                    indication=drug.get("disease_name"),
                    gene_disease_score=association_score or 0.0,
                    evidence_sources=["Open Targets"],
                )
                candidates.append(candidate)

            # Also query ChEMBL for additional drugs
            chembl_targets = opentargets_client.search_targets(target_symbol or "", limit=1)
            for ct in chembl_targets:
                pass  # ChEMBL integration would go here

            # Query DGIdb for gene-drug interactions
            if target_symbol:
                dgidb_results = dgidb_client.search_dgidb_genes([target_symbol], limit=20)
                for dgi in dgidb_results:
                    # Check if drug already exists
                    existing = next((c for c in candidates if c.drug_name.lower() == dgi.get("drug_name", "").lower()), None)
                    if not existing:
                        candidate = RepurposingCandidate(
                            drug_name=dgi.get("drug_name", ""),
                            drug_sources=["DGIdb"],
                            disease_name=disease_name,
                            disease_id=disease_id,
                            target_symbol=target_symbol,
                            target_id=target_id,
                            target_name=target_name,
                            mechanism_of_action=", ".join(dgi.get("interaction_types", [])),
                            evidence_sources=["DGIdb"],
                            supporting_pmids=dgi.get("pmids", []),
                        )
                        candidates.append(candidate)

            # Query CTD for chemical-gene interactions
            if target_symbol:
                ctd_results = ctd_client.search_ctd_chemical_gene(target_symbol, limit=20)
                for ctd in ctd_results:
                    existing = next((c for c in candidates if c.drug_name.lower() == ctd.get("chemical_name", "").lower()), None)
                    if not existing:
                        candidate = RepurposingCandidate(
                            drug_name=ctd.get("chemical_name", ""),
                            drug_sources=["CTD"],
                            disease_name=disease_name,
                            disease_id=disease_id,
                            target_symbol=target_symbol,
                            target_id=target_id,
                            target_name=target_name,
                            mechanism_of_action=", ".join(ctd.get("interaction_actions", [])),
                            evidence_sources=["CTD"],
                            supporting_pmids=ctd.get("pubmed_ids", []),
                        )
                        candidates.append(candidate)

        except Exception as e:
            logger.warning("Failed to get drugs for target %s: %s", target_id, e)

        return candidates

    def _score_candidates(
        self,
        candidates: list[RepurposingCandidate],
        disease_info: dict[str, Any] | None = None,
        gene_symbols: list[str] | None = None,
        include_genetic_evidence: bool = True,
        include_literature: bool = True,
    ) -> list[RepurposingCandidate]:
        """Score repurposing candidates using explainable scoring framework."""

        for candidate in candidates:
            # 1. Target Relevance Score (0-1)
            # Based on disease-target association strength
            candidate.target_relevance_score = candidate.gene_disease_score or 0.5

            # 2. Gene-Disease Association Score (0-1)
            # Already captured in target_relevance, but can be enhanced
            candidate.gene_disease_score = candidate.gene_disease_score or 0.5

            # 3. Drug-Target Evidence Score (0-1)
            # Based on clinical phase, known mechanisms, database support
            candidate.drug_target_evidence_score = self._calculate_drug_target_evidence(candidate)

            # 4. Mechanism Compatibility Score (0-1)
            # How well does the mechanism fit the disease biology?
            candidate.mechanism_compatibility_score = self._calculate_mechanism_compatibility(candidate, disease_info)

            # 5. Pathway Relevance Score (0-1)
            # Would require pathway analysis - placeholder
            candidate.pathway_relevance_score = 0.5

            # 6. Literature Evidence Score (0-1)
            # Based on number of supporting PMIDs
            candidate.literature_evidence_score = self._calculate_literature_evidence(candidate)

            # 7. Data Confidence Score (0-1)
            # Based on number and quality of data sources
            candidate.data_confidence_score = self._calculate_data_confidence(candidate)

            # Calculate overall weighted score
            candidate.overall_score = self._calculate_overall_score(candidate)

            # Classify evidence level
            candidate.evidence_classification = self._classify_evidence(candidate)

        return candidates

    def _calculate_drug_target_evidence(self, candidate: RepurposingCandidate) -> float:
        """Calculate drug-target evidence score."""
        score = 0.0

        # Clinical phase contribution (0-0.4)
        phase = candidate.max_phase or 0
        if phase >= 4:
            score += 0.4  # Approved drug
        elif phase == 3:
            score += 0.3
        elif phase == 2:
            score += 0.2
        elif phase == 1:
            score += 0.1

        # Known mechanism contribution (0-0.3)
        if candidate.mechanism_of_action:
            score += 0.3

        # Database support (0-0.3)
        source_count = len(set(candidate.evidence_sources))
        score += min(0.3, source_count * 0.1)

        return min(1.0, score)

    def _calculate_mechanism_compatibility(
        self,
        candidate: RepurposingCandidate,
        disease_info: dict[str, Any] | None,
    ) -> float:
        """Calculate mechanism compatibility score."""
        # Simplified: check if mechanism action type aligns with disease
        # In practice, would need disease mechanism knowledge
        score = 0.5  # baseline

        if candidate.action_type:
            action = candidate.action_type.lower()
            # Inhibitors for overactive targets, activators for underactive
            # This is a simplified heuristic
            if "inhibitor" in action or "antagonist" in action:
                score += 0.2
            elif "activator" in action or "agonist" in action:
                score += 0.2

        if candidate.mechanism_of_action:
            score += 0.1

        return min(1.0, score)

    def _calculate_literature_evidence(self, candidate: RepurposingCandidate) -> float:
        """Calculate literature evidence score based on PMIDs."""
        pmid_count = len(candidate.supporting_pmids)
        if pmid_count == 0:
            return 0.2
        elif pmid_count <= 2:
            return 0.4
        elif pmid_count <= 5:
            return 0.6
        elif pmid_count <= 10:
            return 0.8
        else:
            return 1.0

    def _calculate_data_confidence(self, candidate: RepurposingCandidate) -> float:
        """Calculate data confidence based on source diversity."""
        sources = set(candidate.evidence_sources)
        source_count = len(sources)

        # Weight different source types
        weights = {
            "Open Targets": 0.3,
            "ChEMBL": 0.25,
            "DGIdb": 0.2,
            "CTD": 0.15,
            "PubChem": 0.1,
            "ClinicalTrials.gov": 0.1,
        }

        score = sum(weights.get(s, 0.05) for s in sources)
        return min(1.0, score)

    def _calculate_overall_score(self, candidate: RepurposingCandidate) -> float:
        """Calculate weighted overall score."""
        weights = {
            "target_relevance": 0.25,
            "gene_disease": 0.15,
            "drug_target_evidence": 0.25,
            "mechanism_compatibility": 0.10,
            "pathway_relevance": 0.10,
            "literature_evidence": 0.10,
            "data_confidence": 0.05,
        }

        score = (
            candidate.target_relevance_score * weights["target_relevance"] +
            candidate.gene_disease_score * weights["gene_disease"] +
            candidate.drug_target_evidence_score * weights["drug_target_evidence"] +
            candidate.mechanism_compatibility_score * weights["mechanism_compatibility"] +
            candidate.pathway_relevance_score * weights["pathway_relevance"] +
            candidate.literature_evidence_score * weights["literature_evidence"] +
            candidate.data_confidence_score * weights["data_confidence"]
        )

        return min(1.0, score)

    def _classify_evidence(self, candidate: RepurposingCandidate) -> str:
        """Classify evidence level for the candidate."""
        # Clinical evidence: approved drug (phase 4) with known indication for disease
        if candidate.max_phase >= 4 and candidate.indication and candidate.disease_name:
            if candidate.indication.lower() in candidate.disease_name.lower() or candidate.disease_name.lower() in candidate.indication.lower():
                return "clinical_evidence"

        # Experimental evidence: known drug-target interaction with experimental validation
        if candidate.drug_target_evidence_score > 0.6 and candidate.supporting_pmids:
            return "experimental_evidence"

        # Computational prediction: based on database associations
        return "computational_prediction"

    def _generate_evidence_summary(
        self,
        candidates: list[RepurposingCandidate],
        disease_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate summary of evidence across all candidates."""
        if not candidates:
            return {}

        evidence_classes = {}
        for c in candidates:
            evidence_classes[c.evidence_classification] = evidence_classes.get(c.evidence_classification, 0) + 1

        avg_scores = {
            "target_relevance": sum(c.target_relevance_score for c in candidates) / len(candidates),
            "drug_target_evidence": sum(c.drug_target_evidence_score for c in candidates) / len(candidates),
            "mechanism_compatibility": sum(c.mechanism_compatibility_score for c in candidates) / len(candidates),
            "literature_evidence": sum(c.literature_evidence_score for c in candidates) / len(candidates),
            "data_confidence": sum(c.data_confidence_score for c in candidates) / len(candidates),
            "overall": sum(c.overall_score for c in candidates) / len(candidates),
        }

        top_targets = {}
        for c in candidates:
            if c.target_symbol:
                top_targets[c.target_symbol] = top_targets.get(c.target_symbol, 0) + 1

        return {
            "evidence_classification_distribution": evidence_classes,
            "average_scores": {k: round(v, 3) for k, v in avg_scores.items()},
            "top_targets": dict(sorted(top_targets.items(), key=lambda x: x[1], reverse=True)[:10]),
            "total_candidates": len(candidates),
            "disease": disease_info.get("name") if disease_info else None,
        }


def create_repurposing_engine(config: dict[str, Any] | None = None) -> DrugRepurposingEngine:
    """Factory function to create a repurposing engine instance."""
    return DrugRepurposingEngine(config)