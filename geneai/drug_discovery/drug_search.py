"""Drug search engine for GeneAI Research - unified search across multiple databases."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import api_clients
from geneai.drug_discovery import chembl_client
from geneai.drug_discovery import clinical_trials_client
from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import ncbi_client
from geneai.drug_discovery import opentargets_client
from geneai.drug_discovery import pubchem_client
from geneai.drug_discovery import uniprot_client

logger = logging.getLogger(__name__)


def search_drugs_by_name(name: str, sources: list[str] | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Search drugs by name across multiple databases."""
    sources = sources or ["pubchem", "chembl", "opentargets"]
    results = []
    seen_inchikeys = set()

    if "pubchem" in sources:
        try:
            pubchem_results = pubchem_client.get_compound_by_name(name)
            for r in pubchem_results:
                inchikey = r.get("inchikey")
                if inchikey and inchikey not in seen_inchikeys:
                    seen_inchikeys.add(inchikey)
                    r["search_source"] = "PubChem"
                    results.append(r)
        except api_clients.DataSourceError as e:
            logger.warning("PubChem search failed: %s", e)

    if "chembl" in sources:
        try:
            chembl_results = chembl_client.search_molecules_by_name(name, limit=limit)
            for r in chembl_results:
                inchikey = r.get("standard_inchikey")
                if inchikey and inchikey not in seen_inchikeys:
                    seen_inchikeys.add(inchikey)
                    r["search_source"] = "ChEMBL"
                    results.append(r)
                elif not inchikey:
                    r["search_source"] = "ChEMBL"
                    results.append(r)
        except api_clients.DataSourceError as e:
            logger.warning("ChEMBL search failed: %s", e)

    if "opentargets" in sources:
        try:
            ot_results = opentargets_client.search_diseases(name, limit=limit)
            for r in ot_results:
                r["search_source"] = "Open Targets"
                r["result_type"] = "disease"
                results.append(r)
        except api_clients.DataSourceError as e:
            logger.warning("Open Targets search failed: %s", e)

    return results[:limit]


def search_drugs_by_target(gene_symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search drugs targeting a specific gene/protein."""
    results = []

    # Open Targets: get target by gene symbol, then get drugs
    try:
        targets = opentargets_client.search_targets(gene_symbol, limit=5)
        for target in targets:
            target_id = target.get("target_id")
            if target_id:
                drugs = opentargets_client.get_target_drugs(target_id, limit=limit)
                for d in drugs:
                    d["search_source"] = "Open Targets"
                    d["target_info"] = target
                    results.append(d)
    except api_clients.DataSourceError as e:
        logger.warning("Open Targets target search failed: %s", e)

    # ChEMBL: search targets by name, then get molecules
    try:
        chembl_targets = chembl_client.search_targets_by_name(gene_symbol, limit=5)
        for target in chembl_targets:
            target_id = target.get("target_chembl_id")
            if target_id:
                target_detail = chembl_client.get_target_by_chembl_id(target_id)
                if target_detail:
                    molecules = chembl_client.get_molecule_targets(target_id)
                    for m in molecules:
                        m["search_source"] = "ChEMBL"
                        m["target_info"] = target_detail
                        results.append(m)
    except api_clients.DataSourceError as e:
        logger.warning("ChEMBL target search failed: %s", e)

    return results[:limit]


def search_drugs_by_disease(disease_name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search drugs associated with a disease."""
    results = []

    # Open Targets
    try:
        diseases = opentargets_client.search_diseases(disease_name, limit=5)
        for disease in diseases:
            disease_id = disease.get("disease_id")
            if disease_id:
                drugs = opentargets_client.get_drug_by_id(disease_id)
                if drugs:
                    drugs["search_source"] = "Open Targets"
                    drugs["disease_info"] = disease
                    results.append(drugs)
                # Also get targets for this disease
                targets = opentargets_client.get_disease_targets(disease_id, limit=limit)
                for t in targets:
                    t["search_source"] = "Open Targets"
                    t["result_type"] = "target"
                    t["disease_info"] = disease
                    results.append(t)
    except api_clients.DataSourceError as e:
        logger.warning("Open Targets disease search failed: %s", e)

    # ClinicalTrials.gov
    try:
        trials = clinical_trials_client.search_studies_by_condition(disease_name, limit=limit)
        for trial in trials:
            trial["search_source"] = "ClinicalTrials.gov"
            trial["result_type"] = "clinical_trial"
            results.append(trial)
    except api_clients.DataSourceError as e:
        logger.warning("ClinicalTrials.gov search failed: %s", e)

    return results[:limit]


def get_drug_details(identifier: str, identifier_type: str = "auto") -> dict[str, Any] | None:
    """Get comprehensive drug details from multiple sources."""
    identifier = identifier.strip()
    if not identifier:
        return None

    result = {
        "query": identifier,
        "identifier_type": identifier_type,
        "pubchem": None,
        "chembl": None,
        "opentargets": None,
        "clinical_trials": [],
        "uniprot_targets": [],
        "ncbi_gene": None,
        "merged": {},
    }

    # Auto-detect identifier type
    if identifier_type == "auto":
        if identifier.isdigit() and len(identifier) <= 10:
            identifier_type = "cid"
        elif identifier.upper().startswith("CHEMBL"):
            identifier_type = "chembl_id"
        elif identifier.upper().startswith("NCT"):
            identifier_type = "nct_id"
        elif "-" in identifier and len(identifier) == 25:
            identifier_type = "inchikey"
        elif identifier.upper().startswith("ENSG"):
            identifier_type = "ensembl_id"
        else:
            identifier_type = "name"

    # Fetch from each source
    try:
        if identifier_type in ("cid", "name"):
            if identifier_type == "cid":
                result["pubchem"] = pubchem_client.get_compound_by_cid(identifier)
            else:
                pubchem_results = pubchem_client.get_compound_by_name(identifier)
                result["pubchem"] = pubchem_results[0] if pubchem_results else None
    except api_clients.DataSourceError as e:
        logger.warning("PubChem fetch failed: %s", e)

    try:
        if identifier_type in ("chembl_id", "name", "inchikey"):
            if identifier_type == "chembl_id":
                result["chembl"] = chembl_client.get_molecule_by_chembl_id(identifier)
            elif identifier_type == "inchikey":
                result["chembl"] = chembl_client.get_molecule_by_inchikey(identifier)
            else:
                chembl_results = chembl_client.search_molecules_by_name(identifier, limit=1)
                result["chembl"] = chembl_results[0] if chembl_results else None
    except api_clients.DataSourceError as e:
        logger.warning("ChEMBL fetch failed: %s", e)

    try:
        if identifier_type in ("chembl_id", "name"):
            if identifier_type == "chembl_id":
                result["opentargets"] = opentargets_client.get_drug_by_id(identifier)
            else:
                # Search Open Targets for drug by name
                pass  # Open Targets drug search requires ChEMBL ID
    except api_clients.DataSourceError as e:
        logger.warning("Open Targets fetch failed: %s", e)

    # Get clinical trials for drug name
    drug_name = (result.get("pubchem") or {}).get("iupac_name") or (result.get("chembl") or {}).get("pref_name") or identifier
    try:
        result["clinical_trials"] = clinical_trials_client.get_studies_by_drug_name(drug_name, limit=10)
    except api_clients.DataSourceError as e:
        logger.warning("ClinicalTrials.gov fetch failed: %s", e)

    # Merge data from all sources
    result["merged"] = _merge_drug_data(result)

    return result


def _merge_drug_data(data: dict[str, Any]) -> dict[str, Any]:
    """Merge drug data from multiple sources, prioritizing validated information."""
    merged = {
        "name": None,
        "identifiers": {},
        "molecular_properties": {},
        "targets": [],
        "indications": [],
        "clinical_trials": [],
        "sources": [],
        "evidence_levels": {},
    }

    sources_found = []

    # PubChem data
    pc = data.get("pubchem")
    if pc:
        sources_found.append("PubChem")
        merged["name"] = merged["name"] or pc.get("iupac_name") or pc.get("name")
        merged["identifiers"]["pubchem_cid"] = pc.get("cid")
        merged["identifiers"]["inchikey"] = pc.get("inchikey")
        merged["identifiers"]["canonical_smiles"] = pc.get("canonical_smiles")
        merged["molecular_properties"] = {
            "molecular_formula": pc.get("molecular_formula"),
            "molecular_weight": pc.get("molecular_weight"),
            "xlogp3": pc.get("xlogp3"),
            "tpsa": pc.get("tpsa"),
            "hbond_donors": pc.get("hbond_donor_count"),
            "hbond_acceptors": pc.get("hbond_acceptor_count"),
            "rotatable_bonds": pc.get("rotatable_bond_count"),
            "exact_mass": pc.get("exact_mass"),
            "charge": pc.get("charge"),
        }
        merged["sources"].append({
            "database": "PubChem",
            "url": pc.get("source_url"),
            "data_types": ["chemical_properties", "synonyms", "assays", "targets", "patents"],
        })

    # ChEMBL data
    chembl = data.get("chembl")
    if chembl:
        sources_found.append("ChEMBL")
        merged["name"] = merged["name"] or chembl.get("pref_name")
        merged["identifiers"]["chembl_id"] = chembl.get("chembl_id")
        merged["identifiers"]["inchikey"] = merged["identifiers"].get("inchikey") or chembl.get("standard_inchikey")
        merged["identifiers"]["canonical_smiles"] = merged["identifiers"].get("canonical_smiles") or chembl.get("canonical_smiles")
        merged["molecular_properties"].update({
            "alogp": chembl.get("alogp"),
            "psa": chembl.get("psa"),
            "hba": chembl.get("hba"),
            "hbd": chembl.get("hbd"),
            "rtb": chembl.get("rtb"),
            "ro5_violations": chembl.get("num_ro5_violations"),
            "max_phase": chembl.get("max_phase"),
            "first_approval": chembl.get("first_approval"),
        })
        merged["sources"].append({
            "database": "ChEMBL",
            "url": chembl.get("source_url"),
            "data_types": ["bioactivities", "targets", "indications", "drug_metadata"],
        })

    # Open Targets data
    ot = data.get("opentargets")
    if ot:
        sources_found.append("Open Targets")
        merged["name"] = merged["name"] or ot.get("drug_name")
        merged["identifiers"]["opentargets_id"] = ot.get("drug_id")
        if ot.get("mechanisms_of_action"):
            for moa in ot["mechanisms_of_action"]:
                merged["targets"].append({
                    "target_id": moa.get("target_id"),
                    "target_symbol": moa.get("target_symbol"),
                    "action_type": moa.get("action_type"),
                    "mechanism": moa.get("mechanism"),
                    "source": "Open Targets",
                    "evidence_level": "curated",
                })
        if ot.get("indications"):
            for ind in ot["indications"]:
                merged["indications"].append({
                    "disease_id": ind.get("disease_id"),
                    "disease_name": ind.get("disease_name"),
                    "max_phase": ind.get("max_phase"),
                    "source": "Open Targets",
                })
        merged["sources"].append({
            "database": "Open Targets",
            "url": ot.get("source_url"),
            "data_types": ["mechanisms_of_action", "indications", "target_associations"],
        })

    # Clinical trials
    trials = data.get("clinical_trials", [])
    if trials:
        merged["clinical_trials"] = [
            {
                "nct_id": t.get("nct_id"),
                "title": t.get("brief_title"),
                "status": t.get("overall_status"),
                "phase": t.get("phase"),
                "conditions": t.get("conditions"),
                "interventions": t.get("interventions"),
                "source_url": t.get("source_url"),
            }
            for t in trials
        ]

    merged["sources_found"] = sources_found
    merged["completeness_score"] = len(sources_found) / 3.0  # 3 main sources

    return merged


def search_by_chemical_identifier(identifier: str, identifier_type: str) -> dict[str, Any] | None:
    """Search drug by chemical identifier (SMILES, InChIKey, InChI)."""
    identifier = identifier.strip()
    if not identifier:
        return None

    result = {"query": identifier, "identifier_type": identifier_type, "pubchem": None, "chembl": None, "merged": {}}

    try:
        if identifier_type == "inchikey":
            result["pubchem"] = pubchem_client.get_compound_by_inchikey(identifier)
            result["chembl"] = chembl_client.get_molecule_by_inchikey(identifier)
        elif identifier_type == "smiles":
            result["pubchem"] = pubchem_client.get_compound_by_smiles(identifier)
            result["chembl"] = chembl_client.get_molecule_by_smiles(identifier)
        elif identifier_type == "inchi":
            # PubChem supports InChI search
            pass
    except api_clients.DataSourceError as e:
        logger.warning("Chemical identifier search failed: %s", e)

    result["merged"] = _merge_drug_data(result)
    return result


def search_drugs_comprehensive(
    query: str,
    search_type: str = "name",
    sources: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Comprehensive drug search with multiple search strategies."""
    sources = sources or ["pubchem", "chembl", "opentargets", "clinicaltrials"]
    results = {
        "query": query,
        "search_type": search_type,
        "drugs": [],
        "targets": [],
        "diseases": [],
        "clinical_trials": [],
        "genes": [],
    }

    if search_type == "name":
        results["drugs"] = search_drugs_by_name(query, sources, limit)
    elif search_type == "target":
        results["targets"] = search_drugs_by_target(query, limit)
    elif search_type == "disease":
        results["diseases"] = search_drugs_by_disease(query, limit)
    elif search_type == "chemical":
        # Try different chemical identifier types
        for id_type in ["inchikey", "smiles", "cid"]:
            try:
                chem_result = search_by_chemical_identifier(query, id_type)
                if chem_result and (chem_result.get("pubchem") or chem_result.get("chembl")):
                    results["drugs"].append(chem_result)
                    break
            except Exception:
                continue

    # Always search for related genes
    try:
        gene_results = ncbi_client.get_gene_by_symbol(query)
        results["genes"] = gene_results[:5]
    except Exception:
        pass

    return results