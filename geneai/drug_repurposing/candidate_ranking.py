"""Candidate ranking module for drug repurposing."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_repurposing import evidence_scoring

logger = logging.getLogger(__name__)


class CandidateRanker:
    """Rank drug repurposing candidates using multiple strategies."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.scorer = evidence_scoring.EvidenceScorer(
            weights=self.config.get("scoring_weights")
        )

    def rank_candidates(
        self,
        candidates: list[dict[str, Any]],
        disease_info: dict[str, Any] | None = None,
        strategy: str = "evidence_based",
    ) -> list[dict[str, Any]]:
        """
        Rank candidates using specified strategy.

        Strategies:
        - evidence_based: Use full evidence scoring framework
        - phase_based: Prioritize by clinical phase
        - target_based: Prioritize by target relevance
        - literature_based: Prioritize by literature support
        - hybrid: Combine multiple strategies
        """
        if not candidates:
            return []

        if strategy == "evidence_based":
            return self._rank_by_evidence(candidates, disease_info)
        elif strategy == "phase_based":
            return self._rank_by_phase(candidates)
        elif strategy == "target_based":
            return self._rank_by_target(candidates, disease_info)
        elif strategy == "literature_based":
            return self._rank_by_literature(candidates)
        elif strategy == "hybrid":
            return self._rank_hybrid(candidates, disease_info)
        else:
            logger.warning("Unknown ranking strategy: %s, using evidence_based", strategy)
            return self._rank_by_evidence(candidates, disease_info)

    def _rank_by_evidence(
        self,
        candidates: list[dict[str, Any]],
        disease_info: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Rank using full evidence scoring."""
        scored = evidence_scoring.score_candidates_batch(candidates, disease_info)

        # Add ranking metadata
        for i, c in enumerate(scored):
            c["rank"] = i + 1
            c["ranking_strategy"] = "evidence_based"

        return scored

    def _rank_by_phase(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank by clinical phase (approved first)."""
        scored = []
        for c in candidates:
            c_copy = c.copy()
            phase = c.get("max_phase", c.get("phase", 0))
            c_copy["phase_score"] = phase / 4.0  # Normalize 0-1
            c_copy["ranking_strategy"] = "phase_based"
            scored.append(c_copy)

        scored.sort(key=lambda x: (x.get("phase_score", 0), x.get("repurposing_score", 0)), reverse=True)

        for i, c in enumerate(scored):
            c["rank"] = i + 1

        return scored

    def _rank_by_target(
        self,
        candidates: list[dict[str, Any]],
        disease_info: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Rank by target relevance to disease."""
        scored = []
        for c in candidates:
            c_copy = c.copy()
            assoc_score = c.get("association_score", c.get("gene_disease_score", 0.5))
            try:
                c_copy["target_relevance_score"] = float(assoc_score)
            except (ValueError, TypeError):
                c_copy["target_relevance_score"] = 0.5
            c_copy["ranking_strategy"] = "target_based"
            scored.append(c_copy)

        scored.sort(key=lambda x: x.get("target_relevance_score", 0), reverse=True)

        for i, c in enumerate(scored):
            c["rank"] = i + 1

        return scored

    def _rank_by_literature(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank by literature support (PMID count)."""
        scored = []
        for c in candidates:
            c_copy = c.copy()
            pmids = c.get("supporting_pmids", c.get("pmids", []))
            pmid_count = len(pmids) if isinstance(pmids, list) else 0
            # Log scale for diminishing returns
            import math
            c_copy["literature_score"] = min(1.0, math.log(pmid_count + 1) / math.log(50)) if pmid_count > 0 else 0
            c_copy["pmid_count"] = pmid_count
            c_copy["ranking_strategy"] = "literature_based"
            scored.append(c_copy)

        scored.sort(key=lambda x: x.get("literature_score", 0), reverse=True)

        for i, c in enumerate(scored):
            c["rank"] = i + 1

        return scored

    def _rank_hybrid(
        self,
        candidates: list[dict[str, Any]],
        disease_info: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Hybrid ranking combining multiple strategies."""
        # Get evidence-based scores
        evidence_ranked = self._rank_by_evidence(candidates, disease_info)

        # Also compute phase and literature scores for comparison
        for c in evidence_ranked:
            phase = c.get("max_phase", c.get("phase", 0))
            c["phase_score"] = phase / 4.0

            pmids = c.get("supporting_pmids", c.get("pmids", []))
            pmid_count = len(pmids) if isinstance(pmids, list) else 0
            import math
            c["literature_score"] = min(1.0, math.log(pmid_count + 1) / math.log(50)) if pmid_count > 0 else 0

        # Hybrid score: 60% evidence, 20% phase, 20% literature
        for c in evidence_ranked:
            hybrid = (
                0.6 * c.get("overall_score", 0) +
                0.2 * c.get("phase_score", 0) +
                0.2 * c.get("literature_score", 0)
            )
            c["hybrid_score"] = round(hybrid, 3)

        evidence_ranked.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        for i, c in enumerate(evidence_ranked):
            c["rank"] = i + 1
            c["ranking_strategy"] = "hybrid"

        return evidence_ranked


def rank_candidates(
    candidates: list[dict[str, Any]],
    disease_info: dict[str, Any] | None = None,
    strategy: str = "evidence_based",
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convenience function to rank candidates."""
    ranker = CandidateRanker(config)
    return ranker.rank_candidates(candidates, disease_info, strategy)


def get_top_candidates(
    candidates: list[dict[str, Any]],
    top_n: int = 10,
    strategy: str = "evidence_based",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Get top N candidates after ranking."""
    ranked = rank_candidates(candidates, strategy=strategy, **kwargs)
    return ranked[:top_n]


def filter_candidates(
    candidates: list[dict[str, Any]],
    min_score: float = 0.0,
    min_phase: int = 0,
    evidence_classes: list[str] | None = None,
    require_mechanism: bool = False,
    require_literature: bool = False,
) -> list[dict[str, Any]]:
    """Filter candidates based on criteria."""
    filtered = []

    for c in candidates:
        # Score filter
        if c.get("overall_score", 0) < min_score:
            continue

        # Phase filter
        if c.get("max_phase", c.get("phase", 0)) < min_phase:
            continue

        # Evidence class filter
        if evidence_classes and c.get("evidence_classification") not in evidence_classes:
            continue

        # Mechanism filter
        if require_mechanism and not (c.get("mechanism_of_action") or c.get("mechanism")):
            continue

        # Literature filter
        if require_literature:
            pmids = c.get("supporting_pmids", c.get("pmids", []))
            if not pmids or (isinstance(pmids, list) and len(pmids) == 0):
                continue

        filtered.append(c)

    return filtered


def deduplicate_candidates(
    candidates: list[dict[str, Any]],
    key_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Remove duplicate candidates based on key fields."""
    key_fields = key_fields or ["drug_name", "drug_id"]
    seen = set()
    unique = []

    for c in candidates:
        key_parts = []
        for field in key_fields:
            val = c.get(field)
            if val:
                key_parts.append(str(val).lower().strip())

        if not key_parts:
            # Fallback: use all string fields
            key_parts = [str(v).lower().strip() for v in c.values() if isinstance(v, str)]

        key = "|".join(key_parts)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def group_candidates_by_target(
    candidates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group candidates by their target protein."""
    groups = {}

    for c in candidates:
        target = c.get("target_symbol") or c.get("target_name") or "Unknown"
        if target not in groups:
            groups[target] = []
        groups[target].append(c)

    # Sort each group by score
    for target in groups:
        groups[target].sort(key=lambda x: x.get("overall_score", 0), reverse=True)

    return groups


def group_candidates_by_mechanism(
    candidates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group candidates by mechanism of action."""
    groups = {}

    for c in candidates:
        mechanisms = c.get("mechanisms", [])
        if isinstance(mechanisms, list) and mechanisms:
            for mech in mechanisms:
                if mech not in groups:
                    groups[mech] = []
                groups[mech].append(c)
        else:
            mech = c.get("mechanism_of_action", "Unknown")
            if mech not in groups:
                groups[mech] = []
            groups[mech].append(c)

    return groups


def compare_candidates(
    candidates: list[dict[str, Any]],
    indices: list[int],
) -> dict[str, Any]:
    """Compare selected candidates side by side."""
    if not indices or len(indices) < 2:
        return {}

    selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
    if len(selected) < 2:
        return {}

    comparison = {
        "candidates": [c.get("drug_name") for c in selected],
        "comparison": {},
    }

    # Compare key attributes
    attributes = [
        "drug_name", "target_symbol", "mechanism_of_action", "max_phase",
        "overall_score", "evidence_classification", "indication",
    ]

    for attr in attributes:
        values = [c.get(attr) for c in selected]
        comparison["comparison"][attr] = values

    # Find common/different attributes
    common = {}
    different = {}
    for attr in attributes:
        values = [c.get(attr) for c in selected]
        unique = set(v for v in values if v is not None)
        if len(unique) == 1:
            common[attr] = list(unique)[0]
        else:
            different[attr] = list(unique)

    comparison["common_attributes"] = common
    comparison["differing_attributes"] = different

    return comparison