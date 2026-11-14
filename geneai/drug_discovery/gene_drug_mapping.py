"""Gene-drug mapping for GeneAI Research - connects VCF/mutation workflow to drug discovery."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import drug_search
from geneai.drug_discovery import drug_target_analysis
from geneai.drug_discovery import ncbi_client
from geneai.drug_discovery import opentargets_client
from geneai.drug_discovery import uniprot_client
from geneai.drug_discovery import clinical_trials_client

logger = logging.getLogger(__name__)


def map_gene_to_drugs(gene_symbol: str, include_predicted: bool = False) -> dict[str, Any]:
    """Map a gene symbol to known drug associations."""
    gene_symbol = gene_symbol.strip().upper()
    result = {
        "gene_symbol": gene_symbol,
        "ncbi_gene": None,
        "uniprot_entries": [],
        "opentargets_target": None,
        "direct_drugs": [],
        "target_drugs": [],
        "clinical_trials": [],
        "pathways": [],
        "evidence_summary": {},
    }

    # Get NCBI gene info
    try:
        ncbi_genes = ncbi_client.get_gene_by_symbol(gene_symbol)
        if ncbi_genes:
            result["ncbi_gene"] = ncbi_genes[0]
            gene_id = ncbi_genes[0].get("gene_id")
            if gene_id:
                pubs = ncbi_client.get_gene_publications(gene_id, limit=5)
                result["literature"] = pubs
    except Exception as e:
        logger.warning("NCBI gene fetch failed: %s", e)

    # Get UniProt entries
    try:
        up_entries = uniprot_client.get_entry_by_gene_name(gene_symbol)
        result["uniprot_entries"] = up_entries[:5]
    except Exception as e:
        logger.warning("UniProt fetch failed: %s", e)

    # Get Open Targets target
    try:
        ot_targets = opentargets_client.search_targets(gene_symbol, limit=1)
        if ot_targets:
            target = ot_targets[0]
            target_id = target.get("target_id")
            result["opentargets_target"] = target

            if target_id:
                # Get drugs for this target
                ot_drugs = opentargets_client.get_target_drugs(target_id, limit=50)
                result["target_drugs"] = ot_drugs

                # Get disease associations
                diseases = opentargets_client.get_target_diseases(target_id, limit=20)
                result["disease_associations"] = diseases
    except Exception as e:
        logger.warning("Open Targets fetch failed: %s", e)

    # Get clinical trials
    try:
        trials = clinical_trials_client.get_studies_by_target_gene(gene_symbol, limit=20)
        result["clinical_trials"] = trials
    except Exception as e:
        logger.warning("Clinical trials fetch failed: %s", e)

    # Build evidence summary
    drugs = result.get("target_drugs", [])
    result["evidence_summary"] = {
        "total_drugs": len(drugs),
        "approved": len([d for d in drugs if d.get("phase", 0) >= 4]),
        "clinical": len([d for d in drugs if 1 <= d.get("phase", 0) <= 3]),
        "preclinical": len([d for d in drugs if d.get("phase", 0) == 0]),
        "top_mechanisms": list(set(d.get("mechanism_of_action") for d in drugs if d.get("mechanism_of_action")))[:5],
        "top_indications": list(set(d.get("disease_name") for d in drugs if d.get("disease_name")))[:5],
        "sources": ["Open Targets", "ClinicalTrials.gov", "NCBI", "UniProt"],
    }

    return result


def map_variant_to_drugs(
    gene_symbol: str,
    variant_info: dict[str, Any] | None = None,
    include_predicted: bool = False,
) -> dict[str, Any]:
    """Map a variant (from VCF) to drug associations via its gene."""
    gene_symbol = gene_symbol.strip().upper()

    result = {
        "gene_symbol": gene_symbol,
        "variant_info": variant_info or {},
        "gene_drug_map": map_gene_to_drugs(gene_symbol, include_predicted),
        "variant_specific": {},
        "disclaimer": (
            "This analysis identifies known drug associations for the gene. "
            "It does not imply the variant is treatable with these drugs or that "
            "the variant affects drug response. Clinical interpretation requires "
            "professional genetic counseling and medical review."
        ),
    }

    # If variant has specific protein change, check for variant-specific drug info
    if variant_info:
        protein_change = variant_info.get("protein_change") or variant_info.get("hgvs_p")
        if protein_change:
            result["variant_specific"]["protein_change"] = protein_change
            # Could add UniProt variant annotation here
            try:
                for up_entry in result["gene_drug_map"].get("uniprot_entries", []):
                    features = uniprot_client.get_protein_features(up_entry.get("accession"))
                    variants = features.get("variants", [])
                    for v in variants:
                        if protein_change.replace("p.", "").upper() in v.get("description", "").upper():
                            result["variant_specific"]["uniprot_variant_annotation"] = v
                            break
            except Exception:
                pass

    return result


def map_gene_list_to_drugs(gene_symbols: list[str]) -> dict[str, Any]:
    """Map multiple genes to drug associations (e.g., from pathway analysis)."""
    results = {
        "genes": {},
        "shared_drugs": [],
        "shared_targets": [],
        "pathway_drugs": {},
        "summary": {},
    }

    all_drugs = {}
    all_targets = {}

    for gene in gene_symbols:
        gene = gene.strip().upper()
        if not gene:
            continue
        gene_map = map_gene_to_drugs(gene)
        results["genes"][gene] = gene_map

        # Collect drugs
        for drug in gene_map.get("target_drugs", []):
            drug_id = drug.get("drug_id")
            if drug_id:
                if drug_id not in all_drugs:
                    all_drugs[drug_id] = {
                        "drug_id": drug_id,
                        "drug_name": drug.get("drug_name"),
                        "genes": [],
                        "max_phase": drug.get("phase", 0),
                    }
                all_drugs[drug_id]["genes"].append(gene)
                all_drugs[drug_id]["max_phase"] = max(
                    all_drugs[drug_id]["max_phase"], drug.get("phase", 0)
                )

        # Collect targets
        ot_target = gene_map.get("opentargets_target")
        if ot_target:
            target_id = ot_target.get("target_id")
            if target_id:
                if target_id not in all_targets:
                    all_targets[target_id] = {
                        "target_id": target_id,
                        "target_name": ot_target.get("approved_name"),
                        "genes": [],
                    }
                all_targets[target_id]["genes"].append(gene)

    # Find shared drugs (targeting 2+ genes)
    results["shared_drugs"] = [
        {"drug_id": d["drug_id"], "drug_name": d["drug_name"], "genes": d["genes"], "max_phase": d["max_phase"]}
        for d in all_drugs.values()
        if len(d["genes"]) > 1
    ]

    # Find shared targets
    results["shared_targets"] = [
        {"target_id": t["target_id"], "target_name": t["target_name"], "genes": t["genes"]}
        for t in all_targets.values()
        if len(t["genes"]) > 1
    ]

    results["summary"] = {
        "total_genes": len(gene_symbols),
        "genes_with_drugs": len([g for g in results["genes"].values() if g.get("target_drugs")]),
        "unique_drugs": len(all_drugs),
        "shared_drug_count": len(results["shared_drugs"]),
        "shared_target_count": len(results["shared_targets"]),
        "max_phase_overall": max([d["max_phase"] for d in all_drugs.values()] + [0]),
    }

    return results


def get_drug_recommendations_for_gene(
    gene_symbol: str,
    min_phase: int = 1,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Get prioritized drug recommendations for a gene."""
    gene_map = map_gene_to_drugs(gene_symbol)
    drugs = gene_map.get("target_drugs", [])

    # Filter by phase
    filtered = [d for d in drugs if d.get("phase", 0) >= min_phase]

    # Sort by phase (highest first), then by score
    filtered.sort(key=lambda x: (x.get("phase", 0), x.get("score", 0)), reverse=True)

    recommendations = []
    for drug in filtered[:max_results]:
        recommendations.append({
            "drug_name": drug.get("drug_name"),
            "drug_id": drug.get("drug_id"),
            "phase": drug.get("phase"),
            "mechanism_of_action": drug.get("mechanism_of_action"),
            "target_name": drug.get("target_name"),
            "disease_name": drug.get("disease_name"),
            "confidence_score": drug.get("score", 0.5),
            "evidence_level": "curated" if drug.get("phase", 0) >= 4 else "clinical" if drug.get("phase", 0) >= 1 else "preclinical",
            "source": "Open Targets",
            "source_url": f"https://platform.opentargets.org/drug/{drug.get('drug_id')}",
        })

    return recommendations


def store_gene_drug_mapping(mapping: dict[str, Any]) -> None:
    """Store gene-drug mapping in database for caching."""
    gene_symbol = mapping.get("gene_symbol")
    if not gene_symbol:
        return

    # Store target info
    ot_target = mapping.get("opentargets_target")
    if ot_target:
        target_data = {
            "source": "Open Targets",
            "source_id": ot_target.get("target_id"),
            "name": ot_target.get("approved_name"),
            "gene_symbol": ot_target.get("approved_symbol"),
            "uniprot_id": ot_target.get("uniprot_ids", [None])[0],
            "organism": "Homo sapiens",
            "target_type": "protein",
            "description": " ".join(ot_target.get("function_descriptions", [])),
            "tractability_sm": ot_target.get("tractability_small_molecule"),
            "tractability_ab": ot_target.get("tractability_antibody"),
            "source_url": ot_target.get("source_url"),
        }
        target_id = db.upsert_target(target_data)

        # Store drugs
        for drug in mapping.get("target_drugs", []):
            drug_data = {
                "source": "Open Targets",
                "source_id": drug.get("drug_id"),
                "name": drug.get("drug_name"),
                "drug_type": "small molecule",
                "mechanism_of_action": drug.get("mechanism_of_action"),
                "max_phase": drug.get("phase"),
                "source_url": f"https://platform.opentargets.org/drug/{drug.get('drug_id')}",
            }
            drug_db_id = db.upsert_drug(drug_data)

            # Link drug-target
            interaction_data = {
                "drug_id": drug_db_id,
                "target_id": target_id,
                "interaction_type": "target",
                "mechanism_of_action": drug.get("mechanism_of_action"),
                "evidence_source": "Open Targets",
                "evidence_level": "curated",
                "source": "Open Targets",
                "source_url": drug_data["source_url"],
                "confidence_score": drug.get("score", 0.5),
            }
            db.upsert_drug_target_interaction(interaction_data)

            # Store disease indications
            disease_name = drug.get("disease_name")
            if disease_name:
                disease_data = {
                    "source": "Open Targets",
                    "source_id": drug.get("disease_id"),
                    "disease_name": disease_name,
                    "source_url": f"https://platform.opentargets.org/disease/{drug.get('disease_id')}",
                }
                disease_id = db.upsert_disease(disease_data)
                db.upsert_drug_disease_indication({
                    "drug_id": drug_db_id,
                    "disease_id": disease_id,
                    "max_phase_for_indication": drug.get("phase"),
                    "source": "Open Targets",
                })
                db.upsert_target_disease_association({
                    "target_id": target_id,
                    "disease_id": disease_id,
                    "association_score": drug.get("score"),
                    "evidence_type": "drug_target",
                    "source": "Open Targets",
                })


def build_vcf_to_drug_report(vcf_genes: list[str]) -> dict[str, Any]:
    """Build a comprehensive report from VCF-identified genes to drug associations."""
    report = {
        "input_genes": vcf_genes,
        "gene_mappings": {},
        "consolidated_drugs": {},
        "consolidated_targets": {},
        "pathway_analysis": {},
        "clinical_trial_opportunities": [],
        "summary": {},
        "disclaimer": (
            "This report identifies known drug-gene associations from public databases. "
            "It does not constitute medical advice or treatment recommendations. "
            "All findings require clinical validation and professional interpretation."
        ),
    }

    # Map each gene
    for gene in vcf_genes:
        mapping = map_gene_to_drugs(gene)
        report["gene_mappings"][gene] = mapping

    # Consolidate drugs across genes
    drug_map = {}
    for gene, mapping in report["gene_mappings"].items():
        for drug in mapping.get("target_drugs", []):
            drug_id = drug.get("drug_id")
            if drug_id not in drug_map:
                drug_map[drug_id] = {
                    "drug_id": drug_id,
                    "drug_name": drug.get("drug_name"),
                    "genes": [],
                    "mechanisms": [],
                    "indications": [],
                    "max_phase": 0,
                    "sources": ["Open Targets"],
                }
            drug_map[drug_id]["genes"].append(gene)
            drug_map[drug_id]["max_phase"] = max(
                drug_map[drug_id]["max_phase"], drug.get("phase", 0)
            )
            if drug.get("mechanism_of_action"):
                drug_map[drug_id]["mechanisms"].append(drug["mechanism_of_action"])
            if drug.get("disease_name"):
                drug_map[drug_id]["indications"].append(drug["disease_name"])

    report["consolidated_drugs"] = list(drug_map.values())
    report["consolidated_drugs"].sort(key=lambda x: x["max_phase"], reverse=True)

    # Clinical trial opportunities
    all_trials = []
    for gene, mapping in report["gene_mappings"].items():
        all_trials.extend(mapping.get("clinical_trials", []))

    # Deduplicate trials
    seen_nct = set()
    unique_trials = []
    for trial in all_trials:
        nct = trial.get("nct_id")
        if nct and nct not in seen_nct:
            seen_nct.add(nct)
            unique_trials.append(trial)

    report["clinical_trial_opportunities"] = unique_trials[:20]

    # Summary
    report["summary"] = {
        "total_input_genes": len(vcf_genes),
        "genes_with_drug_associations": len([
            g for g, m in report["gene_mappings"].items()
            if m.get("target_drugs")
        ]),
        "total_unique_drugs": len(drug_map),
        "approved_drugs": len([d for d in drug_map.values() if d["max_phase"] >= 4]),
        "clinical_phase_drugs": len([d for d in drug_map.values() if 1 <= d["max_phase"] <= 3]),
        "preclinical_drugs": len([d for d in drug_map.values() if d["max_phase"] == 0]),
        "total_clinical_trials": len(unique_trials),
        "recruiting_trials": len([
            t for t in unique_trials
            if t.get("overall_status") in ["Recruiting", "Not yet recruiting"]
        ]),
    }

    return report