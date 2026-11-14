"""Target matching module for protein target analysis in drug repurposing."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import opentargets_client
from geneai.drug_discovery import uniprot_client
from geneai.drug_repurposing import dgidb_client

logger = logging.getLogger(__name__)


def get_target_profile(target_id: str | None = None, gene_symbol: str | None = None) -> dict[str, Any] | None:
    """Get comprehensive target profile from multiple databases."""
    if not target_id and not gene_symbol:
        return None

    result = {
        "target_id": target_id,
        "gene_symbol": gene_symbol,
        "open_targets": None,
        "uniprot": None,
        "dgidb": None,
        "merged": {},
    }

    # Open Targets
    if target_id and target_id.startswith("ENSG"):
        try:
            ot_target = opentargets_client.get_target_by_id(target_id)
            result["open_targets"] = ot_target
            if ot_target and not gene_symbol:
                result["gene_symbol"] = ot_target.get("approved_symbol")
                gene_symbol = result["gene_symbol"]
        except Exception as e:
            logger.warning("Open Targets target fetch failed: %s", e)

    # Search by gene symbol if no target_id
    if gene_symbol and not target_id:
        try:
            targets = opentargets_client.search_targets(gene_symbol, limit=1)
            if targets:
                target = targets[0]
                result["target_id"] = target.get("target_id")
                ot_target = opentargets_client.get_target_by_id(result["target_id"])
                result["open_targets"] = ot_target
        except Exception as e:
            logger.warning("Open Targets target search failed: %s", e)

    # UniProt
    if gene_symbol:
        try:
            up_results = uniprot_client.get_entry_by_gene_name(gene_symbol)
            if up_results:
                result["uniprot"] = up_results[0]
        except Exception as e:
            logger.warning("UniProt fetch failed: %s", e)

    # DGIdb
    if gene_symbol:
        try:
            dgi_results = dgidb_client.search_dgidb_genes([gene_symbol], limit=20)
            result["dgidb"] = dgi_results
        except Exception as e:
            logger.warning("DGIdb fetch failed: %s", e)

    # Merge data
    result["merged"] = _merge_target_data(result)

    return result


def _merge_target_data(data: dict[str, Any]) -> dict[str, Any]:
    """Merge target data from multiple sources."""
    merged = {
        "target_id": data.get("target_id"),
        "gene_symbol": data.get("gene_symbol"),
        "target_name": None,
        "protein_name": None,
        "uniprot_ids": [],
        "function": None,
        "subcellular_location": None,
        "domains": [],
        "tractability": {},
        "known_drugs_count": 0,
        "associated_diseases_count": 0,
        "drug_interactions": [],
        "sources": [],
    }

    # Open Targets
    ot = data.get("open_targets")
    if ot:
        merged["target_id"] = merged["target_id"] or ot.get("target_id")
        merged["gene_symbol"] = merged["gene_symbol"] or ot.get("approved_symbol")
        merged["target_name"] = ot.get("approved_name")
        merged["uniprot_ids"] = ot.get("uniprot_ids", [])
        merged["function"] = " ".join(ot.get("function_descriptions", []))
        merged["tractability"] = {
            "small_molecule": ot.get("tractability_small_molecule"),
            "antibody": ot.get("tractability_antibody"),
        }
        merged["known_drugs_count"] = ot.get("known_drugs_count", 0)
        merged["associated_diseases_count"] = ot.get("associated_diseases_count", 0)
        merged["sources"].append("Open Targets")

    # UniProt
    up = data.get("uniprot")
    if up:
        merged["protein_name"] = up.get("protein_name")
        merged["function"] = merged["function"] or up.get("function")
        merged["subcellular_location"] = up.get("subcellular_location")
        merged["domains"] = up.get("domains", [])
        merged["uniprot_ids"] = list(set(merged["uniprot_ids"] + [up.get("uniprot_id")]))
        merged["sources"].append("UniProt")

    # DGIdb - extract drug interactions
    dgi = data.get("dgidb")
    if dgi:
        for interaction in dgi:
            merged["drug_interactions"].append({
                "drug_name": interaction.get("drug_name"),
                "interaction_types": interaction.get("interaction_types", []),
                "sources": interaction.get("sources", []),
                "pmids": interaction.get("pmids", []),
            })
        merged["sources"].append("DGIdb")

    return merged


def find_targets_for_disease(
    disease_name: str,
    min_association_score: float = 0.3,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find protein targets associated with a disease."""
    try:
        diseases = opentargets_client.search_diseases(disease_name, limit=5)
        if not diseases:
            return []

        disease = diseases[0]
        disease_id = disease.get("disease_id")
        targets = opentargets_client.get_disease_targets(disease_id, limit=limit)

        filtered = []
        for t in targets:
            score = t.get("association_score")
            if score is not None and score >= min_association_score:
                # Get full target profile
                profile = get_target_profile(target_id=t.get("target_id"))
                if profile:
                    filtered.append({
                        "target_id": t.get("target_id"),
                        "gene_symbol": t.get("approved_symbol"),
                        "target_name": t.get("approved_name"),
                        "association_score": score,
                        "biotype": t.get("biotype"),
                        "tractability": profile.get("merged", {}).get("tractability", {}),
                        "known_drugs": profile.get("merged", {}).get("known_drugs_count", 0),
                        "drug_interactions": profile.get("merged", {}).get("drug_interactions", [])[:5],
                    })

        return filtered
    except Exception as e:
        logger.warning("Failed to find targets for disease %s: %s", disease_name, e)
        return []


def find_diseases_for_target(
    target_id: str | None = None,
    gene_symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find diseases associated with a target."""
    if not target_id and not gene_symbol:
        return []

    try:
        if gene_symbol and not target_id:
            targets = opentargets_client.search_targets(gene_symbol, limit=1)
            if targets:
                target_id = targets[0].get("target_id")

        if not target_id:
            return []

        diseases = opentargets_client.get_target_diseases(target_id, limit=limit)
        return diseases
    except Exception as e:
        logger.warning("Failed to find diseases for target: %s", e)
        return []


def get_target_drugs_comprehensive(
    target_id: str | None = None,
    gene_symbol: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Get all known drugs for a target from multiple databases."""
    result = {
        "target_id": target_id,
        "gene_symbol": gene_symbol,
        "open_targets_drugs": [],
        "dgidb_interactions": [],
        "merged_drugs": [],
    }

    # Resolve target_id if needed
    if gene_symbol and not target_id:
        try:
            targets = opentargets_client.search_targets(gene_symbol, limit=1)
            if targets:
                target_id = targets[0].get("target_id")
                result["target_id"] = target_id
        except Exception:
            pass

    if not target_id and not gene_symbol:
        return result

    # Open Targets drugs
    if target_id:
        try:
            ot_drugs = opentargets_client.get_target_drugs(target_id, limit=limit)
            result["open_targets_drugs"] = ot_drugs
        except Exception as e:
            logger.warning("Open Targets drug fetch failed: %s", e)

    # DGIdb interactions
    if gene_symbol:
        try:
            dgi_results = dgidb_client.search_dgidb_genes([gene_symbol], limit=limit)
            result["dgidb_interactions"] = dgi_results
        except Exception as e:
            logger.warning("DGIdb fetch failed: %s", e)

    # Merge drugs
    drug_map = {}
    for drug in result["open_targets_drugs"]:
        key = drug.get("drug_id")
        if key:
            drug_map[key] = {
                "drug_id": key,
                "drug_name": drug.get("drug_name"),
                "phase": drug.get("phase"),
                "mechanism": drug.get("mechanism_of_action"),
                "indication": drug.get("disease_name"),
                "source": "Open Targets",
                "score": drug.get("score"),
            }

    for interaction in result["dgidb_interactions"]:
        drug_name = interaction.get("drug_name")
        key = f"dgidb:{drug_name}"
        if key not in drug_map:
            drug_map[key] = {
                "drug_id": interaction.get("drug_concept_id"),
                "drug_name": drug_name,
                "interaction_types": interaction.get("interaction_types", []),
                "sources": interaction.get("sources", []),
                "pmids": interaction.get("pmids", []),
                "source": "DGIdb",
            }
        else:
            drug_map[key]["source"] += ", DGIdb"
            drug_map[key]["dgidb_interaction_types"] = interaction.get("interaction_types", [])
            drug_map[key]["dgidb_pmids"] = interaction.get("pmids", [])

    result["merged_drugs"] = list(drug_map.values())
    result["merged_drugs"].sort(
        key=lambda x: (x.get("phase", 0), x.get("score", 0)),
        reverse=True
    )

    return result


def assess_target_druggability(
    target_id: str | None = None,
    gene_symbol: str | None = None,
) -> dict[str, Any]:
    """Assess the druggability of a target."""
    profile = get_target_profile(target_id=target_id, gene_symbol=gene_symbol)
    if not profile:
        return {"error": "Target not found"}

    merged = profile.get("merged", {})
    tractability = merged.get("tractability", {})

    assessment = {
        "target_id": profile.get("target_id"),
        "gene_symbol": profile.get("gene_symbol"),
        "target_name": merged.get("target_name"),
        "overall_druggability": "unknown",
        "small_molecule_tractability": tractability.get("small_molecule"),
        "antibody_tractability": tractability.get("antibody"),
        "known_drugs_count": merged.get("known_drugs_count", 0),
        "has_drug_interactions": len(merged.get("drug_interactions", [])) > 0,
        "drug_interaction_count": len(merged.get("drug_interactions", [])),
        "function": merged.get("function"),
        "subcellular_location": merged.get("subcellular_location"),
        "domains_count": len(merged.get("domains", [])),
        "sources": merged.get("sources", []),
        "recommendations": [],
    }

    # Determine overall druggability
    sm_tract = tractability.get("small_molecule", "").lower()
    ab_tract = tractability.get("antibody", "").lower()

    if "high" in sm_tract or "high" in ab_tract:
        assessment["overall_druggability"] = "high"
    elif "medium" in sm_tract or "medium" in ab_tract:
        assessment["overall_druggability"] = "medium"
    elif "low" in sm_tract or "low" in ab_tract:
        assessment["overall_druggability"] = "low"
    elif merged.get("known_drugs_count", 0) > 0:
        assessment["overall_druggability"] = "drugged"
    else:
        assessment["overall_druggability"] = "unknown"

    # Add recommendations
    if assessment["overall_druggability"] == "high":
        assessment["recommendations"].append("High tractability - suitable for small molecule or antibody development")
    elif assessment["overall_druggability"] == "drugged":
        assessment["recommendations"].append("Already has known drugs - strong repurposing candidate")
    elif assessment["overall_druggability"] == "medium":
        assessment["recommendations"].append("Moderate tractability - may require specialized approaches")
    else:
        assessment["recommendations"].append("Low or unknown tractability - consider alternative targets")

    if assessment["has_drug_interactions"]:
        assessment["recommendations"].append(f"Has {assessment['drug_interaction_count']} known drug interactions in DGIdb")

    return assessment