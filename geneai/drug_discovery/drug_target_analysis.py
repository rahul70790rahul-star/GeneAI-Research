"""Drug-target interaction analysis for GeneAI Research."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from geneai.drug_discovery import api_clients
from geneai.drug_discovery import chembl_client
from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import opentargets_client
from geneai.drug_discovery import pubchem_client
from geneai.drug_discovery import uniprot_client

logger = logging.getLogger(__name__)


EVIDENCE_LEVELS = {
    "clinical": 1.0,
    "preclinical": 0.8,
    "biochemical": 0.7,
    "cellular": 0.6,
    "genetic": 0.5,
    "predicted": 0.3,
    "literature": 0.4,
}


def analyze_drug_targets(drug_identifier: str, identifier_type: str = "auto") -> dict[str, Any]:
    """Comprehensive drug-target analysis from multiple sources."""
    result = {
        "drug_identifier": drug_identifier,
        "identifier_type": identifier_type,
        "targets": [],
        "target_summary": {},
        "mechanisms": [],
        "pathways": [],
        "evidence_breakdown": defaultdict(int),
    }

    targets_by_id = {}

    # PubChem targets
    try:
        if identifier_type in ("cid", "name", "auto"):
            pc_data = pubchem_client.get_compound_by_cid(drug_identifier) if identifier_type == "cid" else pubchem_client.get_compound_by_name(drug_identifier)
            if isinstance(pc_data, list):
                pc_data = pc_data[0] if pc_data else None
            if pc_data:
                pubchem_targets = pubchem_client.get_compound_targets(pc_data.get("cid"))
                for t in pubchem_targets:
                    target_key = f"pubchem_{t.get('target_id')}"
                    if target_key not in targets_by_id:
                        targets_by_id[target_key] = {
                            "target_id": t.get("target_id"),
                            "target_name": t.get("target_name"),
                            "gene_symbol": t.get("gene_symbol"),
                            "uniprot_id": t.get("uniprot_id"),
                            "organism": t.get("organism"),
                            "sources": ["PubChem"],
                            "evidence_level": "biochemical",
                            "confidence": 0.7,
                            "interactions": [],
                        }
                    else:
                        targets_by_id[target_key]["sources"].append("PubChem")
    except api_clients.DataSourceError as e:
        logger.warning("PubChem target fetch failed: %s", e)

    # ChEMBL targets
    try:
        if identifier_type in ("chembl_id", "name", "auto"):
            chembl_data = chembl_client.get_molecule_by_chembl_id(drug_identifier) if identifier_type == "chembl_id" else chembl_client.search_molecules_by_name(drug_identifier, limit=1)
            if isinstance(chembl_data, list):
                chembl_data = chembl_data[0] if chembl_data else None
            if chembl_data:
                chembl_id = chembl_data.get("chembl_id")
                chembl_targets = chembl_client.get_molecule_targets(chembl_id)
                for t in chembl_targets:
                    target_key = f"chembl_{t.get('target_chembl_id')}"
                    activities = t.get("activities", [])
                    if activities:
                        best_activity = max(activities, key=lambda x: x.get("pchembl") or 0)
                        pchembl = best_activity.get("pchembl")
                        evidence = "biochemical" if pchembl and pchembl > 5 else "cellular"
                        confidence = min(0.9, 0.5 + (pchembl or 0) * 0.05)
                    else:
                        evidence = "predicted"
                        confidence = 0.3

                    if target_key not in targets_by_id:
                        target_detail = chembl_client.get_target_by_chembl_id(t.get("target_chembl_id"))
                        targets_by_id[target_key] = {
                            "target_id": t.get("target_chembl_id"),
                            "target_name": t.get("target_name") or (target_detail.get("pref_name") if target_detail else None),
                            "gene_symbol": (target_detail.get("gene_symbols", [None])[0] if target_detail and target_detail.get("gene_symbols") else None),
                            "uniprot_id": (target_detail.get("uniprot_ids", [None])[0] if target_detail else None),
                            "organism": target_detail.get("organism") if target_detail else None,
                            "sources": ["ChEMBL"],
                            "evidence_level": evidence,
                            "confidence": confidence,
                            "interactions": [
                                {
                                    "type": a.get("type"),
                                    "value": a.get("value"),
                                    "units": a.get("units"),
                                    "pchembl": a.get("pchembl"),
                                    "relation": a.get("relation"),
                                }
                                for a in activities[:10]
                            ],
                        }
                    else:
                        targets_by_id[target_key]["sources"].append("ChEMBL")
                        targets_by_id[target_key]["confidence"] = max(
                            targets_by_id[target_key]["confidence"], confidence
                        )
                        if "ChEMBL" not in targets_by_id[target_key]["sources"]:
                            targets_by_id[target_key]["evidence_level"] = evidence
    except api_clients.DataSourceError as e:
        logger.warning("ChEMBL target fetch failed: %s", e)

    # Open Targets mechanisms
    try:
        if identifier_type in ("chembl_id", "auto"):
            ot_drug = opentargets_client.get_drug_by_id(drug_identifier)
            if ot_drug:
                for moa in ot_drug.get("mechanisms_of_action", []):
                    target_key = f"opentargets_{moa.get('target_id')}"
                    if target_key not in targets_by_id:
                        targets_by_id[target_key] = {
                            "target_id": moa.get("target_id"),
                            "target_symbol": moa.get("target_symbol"),
                            "gene_symbol": moa.get("target_symbol"),
                            "sources": ["Open Targets"],
                            "evidence_level": "curated",
                            "confidence": 0.85,
                            "interactions": [],
                        }
                    else:
                        targets_by_id[target_key]["sources"].append("Open Targets")
                        targets_by_id[target_key]["confidence"] = max(
                            targets_by_id[target_key]["confidence"], 0.85
                        )
                    targets_by_id[target_key]["action_type"] = moa.get("action_type")
                    targets_by_id[target_key]["mechanism"] = moa.get("mechanism")
    except api_clients.DataSourceError as e:
        logger.warning("Open Targets mechanism fetch failed: %s", e)

    # Convert to list and sort by confidence
    targets_list = list(targets_by_id.values())
    targets_list.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    # Enrich with UniProt data
    for target in targets_list:
        uniprot_id = target.get("uniprot_id")
        gene_symbol = target.get("gene_symbol")
        if uniprot_id:
            try:
                up_data = uniprot_client.get_entry_by_accession(uniprot_id)
                if up_data:
                    target["uniprot_data"] = {
                        "protein_name": up_data.get("protein_name"),
                        "functions": up_data.get("functions", [])[:3],
                        "pathways": up_data.get("pathways", [])[:5],
                        "go_terms": up_data.get("go_terms", [])[:5],
                        "pdb_entries": up_data.get("pdb_entries", [])[:5],
                        "drugbank_ids": up_data.get("drugbank_ids", []),
                    }
            except Exception:
                pass
        elif gene_symbol:
            try:
                up_results = uniprot_client.get_entry_by_gene_name(gene_symbol)
                if up_results:
                    target["uniprot_data"] = {
                        "protein_name": up_results[0].get("protein_name"),
                        "functions": up_results[0].get("functions", [])[:3],
                        "pathways": up_results[0].get("pathways", [])[:5],
                    }
            except Exception:
                pass

    # Build evidence breakdown
    for target in targets_list:
        evidence = target.get("evidence_level", "unknown")
        result["evidence_breakdown"][evidence] += 1

    # Identify pathways
    all_pathways = []
    for target in targets_list:
        up_data = target.get("uniprot_data", {})
        all_pathways.extend(up_data.get("pathways", []))
    result["pathways"] = list(set(all_pathways))[:20]

    result["targets"] = targets_list
    result["target_count"] = len(targets_list)
    result["high_confidence_targets"] = len([t for t in targets_list if t.get("confidence", 0) >= 0.7])
    result["sources_used"] = list(set().union(*[t.get("sources", []) for t in targets_list]))

    return result


def analyze_target_drugs(target_identifier: str, identifier_type: str = "auto") -> dict[str, Any]:
    """Comprehensive target-drug analysis from multiple sources."""
    result = {
        "target_identifier": target_identifier,
        "identifier_type": identifier_type,
        "target_info": {},
        "drugs": [],
        "drug_summary": {},
        "indications": [],
        "clinical_trials": [],
    }

    target_id = None
    target_info = {}

    # Get target info from Open Targets
    try:
        if identifier_type in ("ensembl_id", "auto") and target_identifier.startswith("ENSG"):
            ot_target = opentargets_client.get_target_by_id(target_identifier)
            if ot_target:
                target_info = ot_target
                target_id = target_identifier
        elif identifier_type in ("gene_symbol", "auto"):
            ot_targets = opentargets_client.search_targets(target_identifier, limit=1)
            if ot_targets:
                target_info = ot_targets[0]
                target_id = target_info.get("target_id")
                ot_target = opentargets_client.get_target_by_id(target_id)
                if ot_target:
                    target_info = ot_target
    except api_clients.DataSourceError as e:
        logger.warning("Open Targets target fetch failed: %s", e)

    # Get target info from ChEMBL
    if not target_info:
        try:
            if identifier_type in ("chembl_id", "auto") and target_identifier.upper().startswith("CHEMBL"):
                chembl_target = chembl_client.get_target_by_chembl_id(target_identifier)
                if chembl_target:
                    target_info = chembl_target
        except api_clients.DataSourceError as e:
            logger.warning("ChEMBL target fetch failed: %s", e)

    result["target_info"] = target_info

    # Get drugs from Open Targets
    drugs_by_id = {}
    if target_id:
        try:
            ot_drugs = opentargets_client.get_target_drugs(target_id, limit=50)
            for d in ot_drugs:
                drug_key = f"opentargets_{d.get('drug_id')}"
                drugs_by_id[drug_key] = {
                    "drug_id": d.get("drug_id"),
                    "drug_name": d.get("drug_name"),
                    "phase": d.get("phase"),
                    "mechanism_of_action": d.get("mechanism_of_action"),
                    "disease_name": d.get("disease_name"),
                    "score": d.get("score"),
                    "sources": ["Open Targets"],
                    "evidence_level": "curated",
                    "confidence": 0.85,
                }
        except api_clients.DataSourceError as e:
            logger.warning("Open Targets drug fetch failed: %s", e)

    # Get drugs from ChEMBL
    if target_info.get("target_chembl_id"):
        try:
            chembl_target_id = target_info["target_chembl_id"]
            # Search for molecules targeting this target
            # This would require a different API call - using activities
        except api_clients.DataSourceError as e:
            logger.warning("ChEMBL drug fetch failed: %s", e)

    # Get clinical trials for target
    gene_symbol = target_info.get("approved_symbol") or target_info.get("gene_symbols", [None])[0]
    if gene_symbol:
        try:
            trials = clinical_trials_client.get_studies_by_target_gene(gene_symbol, limit=20)
            result["clinical_trials"] = trials
        except Exception as e:
            logger.warning("Clinical trials fetch failed: %s", e)

    # Get disease associations
    if target_id:
        try:
            diseases = opentargets_client.get_target_diseases(target_id, limit=20)
            result["indications"] = diseases
        except api_clients.DataSourceError as e:
            logger.warning("Target disease fetch failed: %s", e)

    drugs_list = list(drugs_by_id.values())
    drugs_list.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    result["drugs"] = drugs_list
    result["drug_count"] = len(drugs_list)
    result["max_phase"] = max([d.get("phase", 0) for d in drugs_list] + [0])

    return result


def analyze_gene_drug_associations(gene_symbol: str) -> dict[str, Any]:
    """Analyze drug associations for a gene from VCF/mutation workflow."""
    gene_symbol = gene_symbol.strip().upper()
    result = {
        "gene_symbol": gene_symbol,
        "target_analysis": {},
        "drug_analysis": {},
        "clinical_trials": [],
        "literature": [],
        "summary": {},
    }

    # Get target info and drugs
    target_result = analyze_target_drugs(gene_symbol, identifier_type="gene_symbol")
    result["target_analysis"] = target_result

    # Get drugs for this target
    result["drug_analysis"] = {
        "drugs": target_result.get("drugs", []),
        "drug_count": target_result.get("drug_count", 0),
        "max_phase": target_result.get("max_phase", 0),
    }

    # Get clinical trials
    result["clinical_trials"] = target_result.get("clinical_trials", [])

    # Get literature from NCBI
    try:
        gene_results = ncbi_client.get_gene_by_symbol(gene_symbol)
        if gene_results:
            gene_id = gene_results[0].get("gene_id")
            if gene_id:
                pubs = ncbi_client.get_gene_publications(gene_id, limit=10)
                result["literature"] = pubs
    except Exception as e:
        logger.warning("NCBI literature fetch failed: %s", e)

    # Build summary
    drugs = target_result.get("drugs", [])
    result["summary"] = {
        "total_drugs": len(drugs),
        "approved_drugs": len([d for d in drugs if d.get("phase", 0) >= 4]),
        "clinical_drugs": len([d for d in drugs if 1 <= d.get("phase", 0) <= 3]),
        "preclinical_drugs": len([d for d in drugs if d.get("phase", 0) == 0]),
        "unique_targets": 1,
        "top_indications": list(set(d.get("disease_name") for d in drugs if d.get("disease_name")))[:5],
        "evidence_sources": list(set().union(*[d.get("sources", []) for d in drugs])),
    }

    return result


def compare_drugs(drug_identifiers: list[tuple[str, str]]) -> dict[str, Any]:
    """Compare multiple drugs side by side."""
    # Import here to allow mock patching
    from geneai.drug_discovery.drug_comparison import get_drug_details
    
    comparison = {
        "drugs": [],
        "common_targets": [],
        "common_indications": [],
        "property_comparison": {},
    }

    all_targets = defaultdict(list)
    all_indications = defaultdict(list)
    properties = {}

    for identifier, id_type in drug_identifiers:
        drug_details = get_drug_details(identifier, id_type)
        if drug_details:
            merged = drug_details.get("merged", {})
            comparison["drugs"].append({
                "identifier": identifier,
                "id_type": id_type,
                "name": merged.get("name"),
                "identifiers": merged.get("identifiers", {}),
                "properties": merged.get("molecular_properties", {}),
                "targets": merged.get("targets", []),
                "indications": merged.get("indications", []),
                "clinical_trials_count": len(merged.get("clinical_trials", [])),
                "sources": merged.get("sources_found", []),
            })

            # Collect targets
            for target in merged.get("targets", []):
                target_key = target.get("target_id") or target.get("target_symbol")
                if target_key:
                    all_targets[target_key].append(identifier)

            # Collect indications
            for ind in merged.get("indications", []):
                disease_key = ind.get("disease_id") or ind.get("disease_name")
                if disease_key:
                    all_indications[disease_key].append(identifier)

            # Collect properties for comparison
            for prop, value in merged.get("molecular_properties", {}).items():
                if prop not in properties:
                    properties[prop] = {}
                properties[prop][identifier] = value

    # Find common targets (appearing in 2+ drugs)
    comparison["common_targets"] = [
        {"target": target, "drugs": drugs}
        for target, drugs in all_targets.items()
        if len(drugs) > 1
    ]

    # Find common indications
    comparison["common_indications"] = [
        {"disease": disease, "drugs": drugs}
        for disease, drugs in all_indications.items()
        if len(drugs) > 1
    ]

    comparison["property_comparison"] = properties

    return comparison


# Import at bottom to avoid circular imports
from geneai.drug_discovery import clinical_trials_client
from geneai.drug_discovery import ncbi_client
from geneai.drug_discovery.drug_comparison import get_drug_details