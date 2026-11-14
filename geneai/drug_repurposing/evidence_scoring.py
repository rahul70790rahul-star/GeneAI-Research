"""Evidence scoring framework for drug repurposing candidates."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvidenceScore:
    """Individual evidence component score with explanation."""
    name: str
    score: float  # 0-1
    weight: float
    description: str
    evidence_details: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    limitations: list[str] = field(default_factory=list)

    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 3),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score(), 3),
            "description": self.description,
            "evidence_details": self.evidence_details,
            "source": self.source,
            "limitations": self.limitations,
        }


class EvidenceScorer:
    """Explainable scoring framework for drug repurposing candidates."""

    # Default weights for each evidence component
    DEFAULT_WEIGHTS = {
        "target_relevance": 0.25,
        "gene_disease_association": 0.15,
        "drug_target_evidence": 0.25,
        "mechanism_compatibility": 0.10,
        "pathway_relevance": 0.10,
        "literature_evidence": 0.10,
        "data_confidence": 0.05,
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        # Normalize weights
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score_candidate(
        self,
        candidate: dict[str, Any],
        disease_info: dict[str, Any] | None = None,
        gene_symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Score a repurposing candidate with full explainability.

        Args:
            candidate: Candidate dictionary with drug/target/disease info
            disease_info: Optional disease context
            gene_symbols: Optional gene context

        Returns:
            Dictionary with overall score and component breakdown
        """
        components = []

        # 1. Target Relevance
        target_rel = self._score_target_relevance(candidate, disease_info)
        components.append(target_rel)

        # 2. Gene-Disease Association
        gene_dis = self._score_gene_disease_association(candidate, disease_info)
        components.append(gene_dis)

        # 3. Drug-Target Evidence
        dt_evidence = self._score_drug_target_evidence(candidate)
        components.append(dt_evidence)

        # 4. Mechanism Compatibility
        mech_comp = self._score_mechanism_compatibility(candidate, disease_info)
        components.append(mech_comp)

        # 5. Pathway Relevance
        path_rel = self._score_pathway_relevance(candidate, disease_info)
        components.append(path_rel)

        # 6. Literature Evidence
        lit_ev = self._score_literature_evidence(candidate)
        components.append(lit_ev)

        # 7. Data Confidence
        data_conf = self._score_data_confidence(candidate)
        components.append(data_conf)

        # Calculate overall score
        overall = sum(c.weighted_score() for c in components)

        # Classify evidence level
        evidence_class = self._classify_evidence(candidate, components)

        return {
            "overall_score": round(overall, 3),
            "evidence_classification": evidence_class,
            "components": [c.to_dict() for c in components],
            "summary": self._generate_score_summary(components, overall),
        }

    def _score_target_relevance(
        self,
        candidate: dict[str, Any],
        disease_info: dict[str, Any] | None,
    ) -> EvidenceScore:
        """Score target relevance to disease."""
        score = 0.5  # baseline
        details = {}
        limitations = []

        # Use disease-target association score if available
        assoc_score = candidate.get("association_score") or candidate.get("gene_disease_score")
        if assoc_score is not None:
            try:
                score = float(assoc_score)
                details["association_score"] = score
            except (ValueError, TypeError):
                pass

        # Use target-disease association from disease_info
        if disease_info:
            targets = disease_info.get("targets", [])
            for t in targets:
                if t.get("approved_symbol") == candidate.get("target_symbol"):
                    t_score = t.get("association_score")
                    if t_score is not None:
                        score = max(score, float(t_score))
                        details["matched_disease_target_score"] = float(t_score)
                    break

        # Known drugs count as relevance indicator
        known_drugs = candidate.get("known_drugs_count", 0)
        if known_drugs > 10:
            score = min(1.0, score + 0.1)
            details["known_drugs_bonus"] = True
        elif known_drugs > 5:
            score = min(1.0, score + 0.05)
            details["known_drugs_bonus"] = True

        limitations.append("Association scores are correlation-based, not causal")
        limitations.append("Genetic association does not guarantee therapeutic relevance")

        return EvidenceScore(
            name="target_relevance",
            score=min(1.0, score),
            weight=self.weights.get("target_relevance", 0.25),
            description="Strength of target-disease association from genetic evidence",
            evidence_details=details,
            source="Open Targets Platform",
            limitations=limitations,
        )

    def _score_gene_disease_association(
        self,
        candidate: dict[str, Any],
        disease_info: dict[str, Any] | None,
    ) -> EvidenceScore:
        """Score gene-disease association strength."""
        score = 0.5
        details = {}
        limitations = []

        # Use the same association score but interpret differently
        assoc_score = candidate.get("association_score") or candidate.get("gene_disease_score")
        if assoc_score is not None:
            score = float(assoc_score)
            details["genetic_association_score"] = score

        # Check if gene is in provided gene list
        if candidate.get("target_symbol") and disease_info:
            # This would be enhanced with specific gene-disease evidence
            pass

        limitations.append("Genetic association does not establish therapeutic target validity")
        limitations.append("May reflect linkage rather than causal relationship")

        return EvidenceScore(
            name="gene_disease_association",
            score=min(1.0, score),
            weight=self.weights.get("gene_disease_association", 0.15),
            description="Genetic evidence linking target gene to disease",
            evidence_details=details,
            source="Open Targets Platform, GWAS Catalog",
            limitations=limitations,
        )

    def _score_drug_target_evidence(self, candidate: dict[str, Any]) -> EvidenceScore:
        """Score evidence for drug-target interaction."""
        score = 0.0
        details = {}
        limitations = []

        # Clinical phase (strongest evidence)
        phase = candidate.get("max_phase", candidate.get("phase", 0))
        phase_scores = {4: 1.0, 3: 0.8, 2: 0.6, 1: 0.4, 0: 0.2}
        score = phase_scores.get(phase, 0.2)
        details["max_clinical_phase"] = phase
        details["phase_score"] = score

        # Known mechanism of action
        if candidate.get("mechanism_of_action") or candidate.get("mechanism"):
            score = min(1.0, score + 0.15)
            details["has_mechanism"] = True

        # Multiple sources
        sources = candidate.get("evidence_sources", candidate.get("drug_sources", []))
        source_count = len(set(sources))
        if source_count >= 3:
            score = min(1.0, score + 0.2)
        elif source_count >= 2:
            score = min(1.0, score + 0.1)
        details["source_count"] = source_count
        details["sources"] = sources

        # DGIdb/CTD interactions
        if candidate.get("drug_interactions") or candidate.get("interaction_types"):
            score = min(1.0, score + 0.15)
            details["has_interaction_data"] = True

        # Binding affinity data (ChEMBL pChEMBL)
        if candidate.get("pchembl_value") or candidate.get("affinity_value"):
            score = min(1.0, score + 0.1)
            details["has_affinity_data"] = True

        limitations.append("Clinical phase reflects original indication, not repurposed use")
        limitations.append("In vitro binding does not guarantee cellular/tissue activity")
        limitations.append("Mechanism may differ in disease context")

        return EvidenceScore(
            name="drug_target_evidence",
            score=min(1.0, score),
            weight=self.weights.get("drug_target_evidence", 0.25),
            description="Experimental and clinical evidence for drug-target interaction",
            evidence_details=details,
            source="ChEMBL, Open Targets, DGIdb, CTD, ClinicalTrials.gov",
            limitations=limitations,
        )

    def _score_mechanism_compatibility(
        self,
        candidate: dict[str, Any],
        disease_info: dict[str, Any] | None,
    ) -> EvidenceScore:
        """Score mechanism of action compatibility with disease biology."""
        score = 0.4  # baseline uncertainty
        details = {}
        limitations = []

        action_type = (candidate.get("action_type") or "").lower()
        mechanism = (candidate.get("mechanism_of_action") or candidate.get("mechanism") or "").lower()

        # Heuristic: inhibitors for overactive targets in disease
        # This is highly simplified - real implementation would need disease mechanism knowledge
        if "inhibitor" in action_type or "antagonist" in action_type:
            score = 0.6
            details["action_type"] = "inhibitor/antagonist"
        elif "activator" in action_type or "agonist" in action_type:
            score = 0.6
            details["action_type"] = "activator/agonist"
        elif "modulator" in action_type:
            score = 0.55
            details["action_type"] = "modulator"
        else:
            details["action_type"] = action_type or "unknown"

        if mechanism:
            score = min(1.0, score + 0.1)
            details["has_mechanism_detail"] = True

        # Would ideally integrate with disease pathway knowledge
        limitations.append("Mechanism compatibility requires disease-specific pathway knowledge")
        limitations.append("Current scoring uses generic heuristics, not disease-specific models")
        limitations.append("Same mechanism may be beneficial or harmful depending on disease context")

        return EvidenceScore(
            name="mechanism_compatibility",
            score=score,
            weight=self.weights.get("mechanism_compatibility", 0.10),
            description="Compatibility of drug mechanism with disease biology",
            evidence_details=details,
            source="Heuristic based on action type",
            limitations=limitations,
        )

    def _score_pathway_relevance(
        self,
        candidate: dict[str, Any],
        disease_info: dict[str, Any] | None,
    ) -> EvidenceScore:
        """Score pathway relevance (placeholder for pathway analysis integration)."""
        score = 0.5
        details = {"status": "placeholder"}
        limitations = [
            "Pathway analysis not yet integrated",
            "Would require Reactome/KEGG pathway enrichment for disease and drug",
            "Score is a neutral placeholder",
        ]

        return EvidenceScore(
            name="pathway_relevance",
            score=score,
            weight=self.weights.get("pathway_relevance", 0.10),
            description="Relevance of drug-target pathway to disease pathways",
            evidence_details=details,
            source="Not yet implemented",
            limitations=limitations,
        )

    def _score_literature_evidence(self, candidate: dict[str, Any]) -> EvidenceScore:
        """Score literature support."""
        score = 0.2  # baseline
        details = {}
        limitations = []

        pmids = candidate.get("supporting_pmids", candidate.get("pmids", []))
        pmid_count = len(pmids) if isinstance(pmids, list) else 0
        details["pubmed_count"] = pmid_count

        if pmid_count == 0:
            score = 0.2
        elif pmid_count <= 2:
            score = 0.4
        elif pmid_count <= 5:
            score = 0.6
        elif pmid_count <= 10:
            score = 0.8
        else:
            score = 1.0

        details["score_rationale"] = f"Based on {pmid_count} supporting publications"

        limitations.append("Publication count does not equal evidence quality")
        limitations.append("May include review articles or indirect evidence")
        limitations.append("Publication bias toward positive results")

        return EvidenceScore(
            name="literature_evidence",
            score=score,
            weight=self.weights.get("literature_evidence", 0.10),
            description="Supporting scientific literature for drug-disease relationship",
            evidence_details=details,
            source="PubMed via NCBI",
            limitations=limitations,
        )

    def _score_data_confidence(self, candidate: dict[str, Any]) -> EvidenceScore:
        """Score confidence based on data source diversity and quality."""
        score = 0.0
        details = {}
        limitations = []

        sources = set(candidate.get("evidence_sources", candidate.get("drug_sources", candidate.get("sources", []))))

        # Source weights
        source_weights = {
            "Open Targets": 0.3,
            "ChEMBL": 0.25,
            "PubChem": 0.1,
            "DGIdb": 0.2,
            "CTD": 0.15,
            "ClinicalTrials.gov": 0.15,
            "UniProt": 0.1,
            "genetic": 0.2,
            "chemical": 0.15,
            "clinical_trial": 0.25,
        }

        for s in sources:
            score += source_weights.get(s, 0.05)

        score = min(1.0, score)
        details["source_count"] = len(sources)
        details["sources"] = list(sources)

        limitations.append("Source diversity does not guarantee data accuracy")
        limitations.append("Some databases share underlying primary data")
        limitations.append("Data freshness varies across sources")

        return EvidenceScore(
            name="data_confidence",
            score=score,
            weight=self.weights.get("data_confidence", 0.05),
            description="Confidence based on diversity and quality of data sources",
            evidence_details=details,
            source="Multi-database integration",
            limitations=limitations,
        )

    def _classify_evidence(
        self,
        candidate: dict[str, Any],
        components: list[EvidenceScore],
    ) -> str:
        """Classify overall evidence level."""
        # Clinical evidence: approved drug with matching indication
        if candidate.get("max_phase", 0) >= 4:
            indication = candidate.get("indication", "").lower()
            disease = candidate.get("disease_name", "").lower()
            if indication and disease and (indication in disease or disease in indication):
                return "clinical_evidence_same_indication"
            return "clinical_evidence_approved_drug"

        # Experimental evidence: strong drug-target evidence with literature
        dt_score = next((c.score for c in components if c.name == "drug_target_evidence"), 0)
        lit_score = next((c.score for c in components if c.name == "literature_evidence"), 0)
        if dt_score > 0.7 and lit_score > 0.5:
            return "strong_experimental_evidence"
        if dt_score > 0.5:
            return "moderate_experimental_evidence"

        # Genetic evidence
        gt_score = next((c.score for c in components if c.name == "target_relevance"), 0)
        if gt_score > 0.7:
            return "strong_genetic_evidence"

        return "computational_prediction"

    def _generate_score_summary(
        self,
        components: list[EvidenceScore],
        overall: float,
    ) -> dict[str, Any]:
        """Generate human-readable score summary."""
        # Find strongest and weakest components
        sorted_components = sorted(components, key=lambda x: x.score, reverse=True)

        return {
            "overall_score": round(overall, 3),
            "strongest_evidence": {
                "component": sorted_components[0].name,
                "score": round(sorted_components[0].score, 3),
            } if sorted_components else None,
            "weakest_evidence": {
                "component": sorted_components[-1].name,
                "score": round(sorted_components[-1].score, 3),
            } if sorted_components else None,
            "component_count": len(components),
            "weighted_contributions": {
                c.name: round(c.weighted_score(), 3) for c in components
            },
        }


def score_candidate(
    candidate: dict[str, Any],
    disease_info: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Convenience function to score a single candidate."""
    scorer = EvidenceScorer(weights)
    return scorer.score_candidate(candidate, disease_info)


def score_candidates_batch(
    candidates: list[dict[str, Any]],
    disease_info: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Score multiple candidates and return sorted by overall score."""
    scorer = EvidenceScorer(weights)
    scored = []
    for c in candidates:
        result = scorer.score_candidate(c, disease_info)
        c_copy = c.copy()
        c_copy["score_breakdown"] = result
        c_copy["overall_score"] = result["overall_score"]
        c_copy["evidence_classification"] = result["evidence_classification"]
        scored.append(c_copy)

    scored.sort(key=lambda x: x["overall_score"], reverse=True)
    return scored