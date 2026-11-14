"""Drug matching module for disease-gene-drug relationship analysis."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import drug_search
from geneai.drug_discovery import gene_drug_mapping
from geneai.drug_discovery import opentargets_client
from geneai.drug_repurposing import ctd_client
from geneai.drug_repurposing import dgidb_client

logger = logging.getLogger(__name__)


def match_disease_to_genes(disease_name: str, limit: int = 50) -> dict[str, Any]:
    """Match a disease to its associated genes using multiple databases."""
    result = {
        "disease_name": disease_name,
        "open_targets": [],
        "ctd": [],
        "merged_genes": [],
        "gene_scores": {},
    }

    # Open Targets
    try:
        diseases = opentargets_client.search_diseases(disease_name, limit=5)
        if diseases:
            disease = diseases[0]
            disease_id = disease.get("disease_id")
            targets = opentargets_client.get_disease_targets(disease_id, limit=limit)
            result["open_targets"] = targets
            for t in targets:
                symbol = t.get("approved_symbol")
                score = t.get("association_score")
                if symbol:
                    result["gene_scores"][symbol] = result["gene_scores"].get(symbol, 0) + (score or 0.5)
    except Exception as e:
        logger.warning("Open Targets disease-gene matching failed: %s", e)

    # CTD
    try:
        ctd_results = ctd_client.search_ctd_gene_disease(disease_name, limit=limit)
        result["ctd"] = ctd_results
        for r in ctd_results:
            symbol = r.get("gene_symbol")
            if symbol:
                # CTD inference score is 0-1, weight it
                inf_score = r.get("inference_score")
                try:
                    inf_score = float(inf_score) if inf_score else 0.5
                except (ValueError, TypeError):
                    inf_score = 0.5
                result["gene_scores"][symbol] = result["gene_scores"].get(symbol, 0) + inf_score * 0.5
    except Exception as e:
        logger.warning("CTD disease-gene matching failed: %s", e)

    # Merge and sort genes by combined score
    merged = []
    for symbol, score in sorted(result["gene_scores"].items(), key=lambda x: x[1], reverse=True):
        merged.append({
            "gene_symbol": symbol,
            "combined_score": round(min(1.0, score), 3),
            "sources": _get_gene_sources(symbol, result),
        })

    result["merged_genes"] = merged[:limit]
    return result


def _get_gene_sources(gene_symbol: str, result: dict[str, Any]) -> list[str]:
    """Determine which databases support a gene-disease association."""
    sources = []
    for t in result.get("open_targets", []):
        if t.get("approved_symbol") == gene_symbol:
            sources.append("Open Targets")
            break
    for r in result.get("ctd", []):
        if r.get("gene_symbol") == gene_symbol:
            if "CTD" not in sources:
                sources.append("CTD")
            break
    return sources


def match_genes_to_drugs(
    gene_symbols: list[str],
    disease_context: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Match a list of genes to known drug associations."""
    result = {
        "input_genes": gene_symbols,
        "disease_context": disease_context,
        "gene_drug_mappings": {},
        "all_drugs": [],
        "drug_scores": {},
    }

    # Use existing gene_drug_mapping for comprehensive mapping
    for gene in gene_symbols:
        mapping = gene_drug_mapping.map_gene_to_drugs(gene)
        result["gene_drug_mappings"][gene] = mapping

        for drug in mapping.get("target_drugs", []):
            drug_id = drug.get("drug_id")
            drug_name = drug.get("drug_name")
            if not drug_id or not drug_name:
                continue

            key = f"{drug_id}:{drug_name}"
            if key not in result["drug_scores"]:
                result["drug_scores"][key] = {
                    "drug_id": drug_id,
                    "drug_name": drug_name,
                    "genes": [],
                    "max_phase": 0,
                    "mechanisms": set(),
                    "indications": set(),
                    "score": 0.0,
                }

            entry = result["drug_scores"][key]
            entry["genes"].append(gene)
            entry["max_phase"] = max(entry["max_phase"], drug.get("phase", 0))
            if drug.get("mechanism_of_action"):
                entry["mechanisms"].add(drug["mechanism_of_action"])
            if drug.get("disease_name"):
                entry["indications"].add(drug["disease_name"])
            entry["score"] += drug.get("score", 0.5)

    # Convert to list and sort
    drugs_list = []
    for key, entry in result["drug_scores"].items():
        drugs_list.append({
            "drug_id": entry["drug_id"],
            "drug_name": entry["drug_name"],
            "target_genes": entry["genes"],
            "gene_count": len(entry["genes"]),
            "max_phase": entry["max_phase"],
            "mechanisms": list(entry["mechanisms"]),
            "indications": list(entry["indications"]),
            "repurposing_score": round(min(1.0, entry["score"] / max(1, len(entry["genes"]))), 3),
        })

    drugs_list.sort(key=lambda x: (x["gene_count"], x["max_phase"], x["repurposing_score"]), reverse=True)
    result["all_drugs"] = drugs_list[:limit]

    # Also query DGIdb for additional gene-drug interactions
    dgidb_results = dgidb_client.search_dgidb_genes(gene_symbols, limit=limit)
    result["dgidb_interactions"] = dgidb_results

    return result


def match_disease_to_drugs(
    disease_name: str,
    include_genetic: bool = True,
    include_chemical: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Comprehensive disease-to-drug matching using multiple strategies."""
    result = {
        "disease_name": disease_name,
        "genetic_based_drugs": [],
        "chemical_based_drugs": [],
        "clinical_trial_drugs": [],
        "merged_candidates": [],
    }

    # Strategy 1: Genetic - disease -> genes -> drugs
    if include_genetic:
        gene_match = match_disease_to_genes(disease_name, limit=20)
        top_genes = [g["gene_symbol"] for g in gene_match.get("merged_genes", [])[:10]]

        if top_genes:
            drug_match = match_genes_to_drugs(top_genes, disease_context=disease_name, limit=limit)
            result["genetic_based_drugs"] = drug_match.get("all_drugs", [])
            result["disease_genes"] = gene_match.get("merged_genes", [])

    # Strategy 2: Chemical - direct disease-chemical associations (CTD)
    if include_chemical:
        try:
            ctd_drugs = ctd_client.search_ctd_disease_chemical(disease_name, limit=limit)
            result["chemical_based_drugs"] = ctd_drugs
        except Exception as e:
            logger.warning("CTD disease-chemical matching failed: %s", e)

    # Strategy 3: Clinical trials for disease
    try:
        from geneai.drug_discovery import clinical_trials_client
        trials = clinical_trials_client.search_studies_by_condition(disease_name, limit=limit)
        trial_drugs = []
        for trial in trials:
            for intervention in trial.get("interventions", []):
                if intervention.get("type") == "Drug":
                    trial_drugs.append({
                        "drug_name": intervention.get("name"),
                        "nct_id": trial.get("nct_id"),
                        "phase": trial.get("phase"),
                        "status": trial.get("overall_status"),
                        "trial_title": trial.get("brief_title"),
                        "source": "ClinicalTrials.gov",
                    })
        result["clinical_trial_drugs"] = trial_drugs
    except Exception as e:
        logger.warning("Clinical trials search failed: %s", e)

    # Merge all candidates
    all_candidates = {}
    for drug in result["genetic_based_drugs"]:
        key = drug.get("drug_id", drug.get("drug_name", ""))
        if key not in all_candidates:
            all_candidates[key] = {
                "drug_id": drug.get("drug_id"),
                "drug_name": drug.get("drug_name"),
                "sources": ["genetic"],
                "max_phase": drug.get("max_phase", 0),
                "mechanisms": drug.get("mechanisms", []),
                "indications": drug.get("indications", []),
                "target_genes": drug.get("target_genes", []),
            }
        else:
            if "genetic" not in all_candidates[key]["sources"]:
                all_candidates[key]["sources"].append("genetic")

    for drug in result["chemical_based_drugs"]:
        key = drug.get("chemical_id", drug.get("chemical_name", ""))
        if key not in all_candidates:
            all_candidates[key] = {
                "drug_id": drug.get("chemical_id"),
                "drug_name": drug.get("chemical_name"),
                "sources": ["chemical"],
                "inference_score": drug.get("inference_score"),
                "direct_evidence": drug.get("direct_evidence"),
            }
        else:
            if "chemical" not in all_candidates[key]["sources"]:
                all_candidates[key]["sources"].append("chemical")

    for drug in result["clinical_trial_drugs"]:
        key = drug.get("drug_name", "")
        if key not in all_candidates:
            all_candidates[key] = {
                "drug_name": drug.get("drug_name"),
                "sources": ["clinical_trial"],
                "trial_info": {
                    "nct_id": drug.get("nct_id"),
                    "phase": drug.get("phase"),
                    "status": drug.get("status"),
                },
            }
        else:
            if "clinical_trial" not in all_candidates[key]["sources"]:
                all_candidates[key]["sources"].append("clinical_trial")

    # Convert to list and sort by evidence diversity
    merged = []
    for key, entry in all_candidates.items():
        evidence_score = len(entry.get("sources", [])) * 0.2
        phase_score = min(1.0, (entry.get("max_phase", 0) / 4.0)) * 0.3
        total_score = evidence_score + phase_score
        merged.append({
            **entry,
            "evidence_diversity": len(entry.get("sources", [])),
            "combined_score": round(total_score, 3),
        })

    merged.sort(key=lambda x: (x["evidence_diversity"], x.get("max_phase", 0), x["combined_score"]), reverse=True)
    result["merged_candidates"] = merged[:limit]

    return result


def find_repurposing_opportunities(
    disease_name: str,
    gene_symbols: list[str] | None = None,
    max_candidates: int = 20,
) -> dict[str, Any]:
    """
    Find drug repurposing opportunities for a disease.

    This is the main entry point that combines all matching strategies.
    """
    result = {
        "disease_name": disease_name,
        "input_genes": gene_symbols,
        "disease_gene_analysis": None,
        "gene_drug_analysis": None,
        "direct_disease_drugs": None,
        "clinical_trials": None,
        "ranked_opportunities": [],
    }

    # If genes provided, use them; otherwise find disease-associated genes
    if gene_symbols:
        result["disease_gene_analysis"] = {
            "provided_genes": gene_symbols,
            "source": "user_provided",
        }
    else:
        result["disease_gene_analysis"] = match_disease_to_genes(disease_name, limit=20)
        gene_symbols = [g["gene_symbol"] for g in result["disease_gene_analysis"].get("merged_genes", [])[:15]]

    # Get drugs for genes
    result["gene_drug_analysis"] = match_genes_to_drugs(gene_symbols, disease_context=disease_name, limit=50)

    # Get direct disease-drug associations
    result["direct_disease_drugs"] = ctd_client.search_ctd_disease_chemical(disease_name, limit=30)

    # Get clinical trials
    try:
        from geneai.drug_discovery import clinical_trials_client
        trials = clinical_trials_client.search_studies_by_condition(disease_name, limit=20)
        result["clinical_trials"] = trials
    except Exception as e:
        logger.warning("Clinical trials search failed: %s", e)

    # Rank opportunities
    opportunities = []

    # From gene-drug analysis
    for drug in result["gene_drug_analysis"].get("all_drugs", []):
        opportunities.append({
            "drug_name": drug.get("drug_name"),
            "drug_id": drug.get("drug_id"),
            "strategy": "genetic_target_based",
            "target_genes": drug.get("target_genes", []),
            "mechanisms": drug.get("mechanisms", []),
            "indications": drug.get("indications", []),
            "max_phase": drug.get("max_phase", 0),
            "gene_count": drug.get("gene_count", 0),
            "repurposing_score": drug.get("repurposing_score", 0),
        })

    # From direct disease-drug
    for drug in result["direct_disease_drugs"]:
        opportunities.append({
            "drug_name": drug.get("chemical_name"),
            "drug_id": drug.get("chemical_id"),
            "strategy": "disease_chemical_association",
            "inference_score": drug.get("inference_score"),
            "direct_evidence": drug.get("direct_evidence"),
            "inference_gene": drug.get("inference_gene_symbol"),
        })

    # From clinical trials
    if result["clinical_trials"]:
        for trial in result["clinical_trials"]:
            for intervention in trial.get("interventions", []):
                if intervention.get("type") == "Drug":
                    opportunities.append({
                        "drug_name": intervention.get("name"),
                        "strategy": "clinical_trial",
                        "nct_id": trial.get("nct_id"),
                        "phase": trial.get("phase"),
                        "status": trial.get("overall_status"),
                        "trial_title": trial.get("brief_title"),
                    })

    # Sort by strategy priority and score
    strategy_priority = {
        "genetic_target_based": 3,
        "clinical_trial": 2,
        "disease_chemical_association": 1,
    }

    opportunities.sort(key=lambda x: (
        strategy_priority.get(x.get("strategy", ""), 0),
        x.get("repurposing_score", 0),
        x.get("max_phase", 0),
    ), reverse=True)

    result["ranked_opportunities"] = opportunities[:max_candidates]

    return result