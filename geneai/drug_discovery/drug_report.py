"""Drug report generation for GeneAI Research - PDF and CSV export."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from geneai.drug_discovery import drug_database as db

logger = logging.getLogger(__name__)


def generate_drug_report_csv(drug_data: dict[str, Any]) -> str:
    """Generate CSV report for a drug."""
    output = io.StringIO()
    writer = csv.writer(output)

    merged = drug_data.get("merged", {})

    # Header
    writer.writerow(["GeneAI Research - Drug Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Drug Name", merged.get("name", "Unknown")])
    writer.writerow([])

    # Identifiers
    writer.writerow(["IDENTIFIERS"])
    writer.writerow(["Type", "Value", "Source"])
    identifiers = merged.get("identifiers", {})
    for id_type, value in identifiers.items():
        if value:
            writer.writerow([id_type.replace("_", " ").title(), value, "Merged"])
    writer.writerow([])

    # Molecular Properties
    writer.writerow(["MOLECULAR PROPERTIES"])
    writer.writerow(["Property", "Value", "Unit"])
    props = merged.get("molecular_properties", {})
    units = {
        "molecular_weight": "g/mol",
        "xlogp3": "logP",
        "tpsa": "Å²",
        "hbond_donors": "count",
        "hbond_acceptors": "count",
        "rotatable_bonds": "count",
        "exact_mass": "Da",
        "charge": "e",
        "alogp": "logP",
        "psa": "Å²",
        "hba": "count",
        "hbd": "count",
        "rtb": "count",
        "ro5_violations": "count",
        "max_phase": "phase",
        "first_approval": "year",
    }
    for prop, value in props.items():
        if value is not None:
            writer.writerow([prop.replace("_", " ").title(), value, units.get(prop, "")])
    writer.writerow([])

    # Targets
    writer.writerow(["TARGET INTERACTIONS"])
    writer.writerow(["Target ID", "Target Name", "Gene Symbol", "Evidence Level", "Confidence", "Mechanism", "Action Type", "Source"])
    for target in merged.get("targets", []):
        writer.writerow([
            target.get("target_id", ""),
            target.get("target_name", ""),
            target.get("gene_symbol", ""),
            target.get("evidence_level", ""),
            target.get("confidence", ""),
            target.get("mechanism", ""),
            target.get("action_type", ""),
            ", ".join(target.get("sources", [])),
        ])
    writer.writerow([])

    # Indications
    writer.writerow(["DISEASE INDICATIONS"])
    writer.writerow(["Disease ID", "Disease Name", "Max Phase", "Source"])
    for ind in merged.get("indications", []):
        writer.writerow([
            ind.get("disease_id", ""),
            ind.get("disease_name", ""),
            ind.get("max_phase", ""),
            ind.get("source", ""),
        ])
    writer.writerow([])

    # Clinical Trials
    writer.writerow(["CLINICAL TRIALS"])
    writer.writerow(["NCT ID", "Title", "Status", "Phase", "Conditions", "Interventions", "Source URL"])
    for trial in merged.get("clinical_trials", []):
        writer.writerow([
            trial.get("nct_id", ""),
            trial.get("title", ""),
            trial.get("status", ""),
            ", ".join(trial.get("phase", [])) if isinstance(trial.get("phase"), list) else trial.get("phase", ""),
            "; ".join(trial.get("conditions", [])),
            "; ".join([iv.get("name", "") for iv in trial.get("interventions", [])]),
            trial.get("source_url", ""),
        ])
    writer.writerow([])

    # Sources
    writer.writerow(["DATA SOURCES"])
    writer.writerow(["Database", "URL", "Data Types"])
    for source in merged.get("sources", []):
        writer.writerow([
            source.get("database", ""),
            source.get("url", ""),
            "; ".join(source.get("data_types", [])),
        ])
    writer.writerow([])

    # Disclaimer
    writer.writerow(["DISCLAIMER"])
    writer.writerow([
        "This report is generated from public databases for research purposes only. "
        "It does not constitute medical advice or treatment recommendations. "
        "All findings require clinical validation and professional interpretation."
    ])

    return output.getvalue()


def generate_gene_drug_report_csv(gene_drug_data: dict[str, Any]) -> str:
    """Generate CSV report for gene-drug mapping."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["GeneAI Research - Gene-Drug Association Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Input Genes", ", ".join(gene_drug_data.get("input_genes", []))])
    writer.writerow([])

    # Summary
    summary = gene_drug_data.get("summary", {})
    writer.writerow(["SUMMARY"])
    writer.writerow(["Metric", "Value"])
    for key, value in summary.items():
        writer.writerow([key.replace("_", " ").title(), value])
    writer.writerow([])

    # Gene mappings
    writer.writerow(["GENE-DRUG MAPPINGS"])
    writer.writerow(["Gene", "Drug ID", "Drug Name", "Phase", "Mechanism", "Target", "Disease", "Score", "Source"])
    for gene, mapping in gene_drug_data.get("gene_mappings", {}).items():
        for drug in mapping.get("target_drugs", []):
            writer.writerow([
                gene,
                drug.get("drug_id", ""),
                drug.get("drug_name", ""),
                drug.get("phase", ""),
                drug.get("mechanism_of_action", ""),
                drug.get("target_name", ""),
                drug.get("disease_name", ""),
                drug.get("score", ""),
                "Open Targets",
            ])
    writer.writerow([])

    # Consolidated drugs
    writer.writerow(["CONSOLIDATED DRUGS (Across All Genes)"])
    writer.writerow(["Drug ID", "Drug Name", "Genes", "Max Phase", "Mechanisms", "Indications"])
    for drug in gene_drug_data.get("consolidated_drugs", []):
        writer.writerow([
            drug.get("drug_id", ""),
            drug.get("drug_name", ""),
            "; ".join(drug.get("genes", [])),
            drug.get("max_phase", ""),
            "; ".join(set(drug.get("mechanisms", []))),
            "; ".join(set(drug.get("indications", []))),
        ])
    writer.writerow([])

    # Clinical trials
    writer.writerow(["CLINICAL TRIAL OPPORTUNITIES"])
    writer.writerow(["NCT ID", "Title", "Status", "Phase", "Conditions", "Interventions", "URL"])
    for trial in gene_drug_data.get("clinical_trial_opportunities", []):
        writer.writerow([
            trial.get("nct_id", ""),
            trial.get("brief_title", ""),
            trial.get("overall_status", ""),
            ", ".join(trial.get("phase", [])) if isinstance(trial.get("phase"), list) else trial.get("phase", ""),
            "; ".join(trial.get("conditions", [])),
            "; ".join([iv.get("name", "") for iv in trial.get("interventions", [])]),
            trial.get("source_url", ""),
        ])
    writer.writerow([])

    # Shared drugs
    writer.writerow(["SHARED DRUGS (Targeting Multiple Input Genes)"])
    writer.writerow(["Drug ID", "Drug Name", "Genes", "Max Phase"])
    for drug in gene_drug_data.get("shared_drugs", []):
        writer.writerow([
            drug.get("drug_id", ""),
            drug.get("drug_name", ""),
            "; ".join(drug.get("genes", [])),
            drug.get("max_phase", ""),
        ])
    writer.writerow([])

    # Disclaimer
    writer.writerow(["DISCLAIMER"])
    writer.writerow([gene_drug_data.get("disclaimer", "")])

    return output.getvalue()


def generate_comparison_report_csv(comparison_data: dict[str, Any]) -> str:
    """Generate CSV report for drug comparison."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["GeneAI Research - Drug Comparison Report"])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow([])

    # Drug summary
    writer.writerow(["DRUG SUMMARY"])
    writer.writerow(["Identifier", "ID Type", "Name", "Targets", "Indications", "Clinical Trials", "Sources"])
    for drug in comparison_data.get("drugs", []):
        writer.writerow([
            drug.get("identifier"),
            drug.get("id_type"),
            drug.get("name"),
            len(drug.get("targets", [])),
            len(drug.get("indications", [])),
            drug.get("clinical_trials_count", 0),
            ", ".join(drug.get("sources", [])),
        ])
    writer.writerow([])

    # Property comparison
    writer.writerow(["PROPERTY COMPARISON"])
    prop_comp = comparison_data.get("property_comparison", {})
    if prop_comp:
        drug_ids = comparison_data.get("drugs", [])
        drug_ids = [d.get("identifier") for d in drug_ids]
        writer.writerow(["Property"] + drug_ids)
        for prop, values in prop_comp.items():
            row = [prop]
            for did in drug_ids:
                row.append(values.get(did, ""))
            writer.writerow(row)
    writer.writerow([])

    # Pairwise similarities
    writer.writerow(["PAIRWISE SIMILARITIES"])
    writer.writerow(["Drug 1", "Drug 2", "Overall", "Target Jaccard", "Indication Jaccard", "Property Similarity", "Shared Targets", "Shared Indications"])
    for sim in comparison_data.get("pairwise_similarity", []):
        writer.writerow([
            sim.get("drug1_name"),
            sim.get("drug2_name"),
            sim.get("overall_similarity"),
            sim.get("target_jaccard"),
            sim.get("indication_jaccard"),
            sim.get("property_similarity"),
            "; ".join(sim.get("shared_targets", [])),
            "; ".join(sim.get("shared_indications", [])),
        ])
    writer.writerow([])

    # Common targets
    writer.writerow(["COMMON TARGETS"])
    writer.writerow(["Target", "Drugs"])
    for ct in comparison_data.get("common_targets", []):
        writer.writerow([ct.get("target"), "; ".join(ct.get("drugs", []))])
    writer.writerow([])

    # Common indications
    writer.writerow(["COMMON INDICATIONS"])
    writer.writerow(["Indication", "Drugs"])
    for ci in comparison_data.get("common_indications", []):
        writer.writerow([ci.get("disease"), "; ".join(ci.get("drugs", []))])
    writer.writerow([])

    # Disclaimer
    writer.writerow(["DISCLAIMER"])
    writer.writerow(["This comparison is based on public database information for research purposes only."])

    return output.getvalue()


def generate_vcf_drug_report_json(vcf_drug_report: dict[str, Any]) -> str:
    """Generate JSON report for VCF-to-drug analysis."""
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "tool": "GeneAI Research",
            "version": "4.5",
            "report_type": "vcf_to_drug_analysis",
        },
        "input": {
            "genes": vcf_drug_report.get("input_genes", []),
        },
        "results": vcf_drug_report,
        "disclaimer": vcf_drug_report.get("disclaimer", ""),
    }
    return json.dumps(report, indent=2, default=str)


def generate_drug_report_pdf_content(drug_data: dict[str, Any]) -> dict[str, Any]:
    """Generate structured content for PDF report (to be rendered by PDF library)."""
    merged = drug_data.get("merged", {})

    return {
        "title": "Drug Research Report",
        "subtitle": f"GeneAI Research - {merged.get('name', 'Unknown Compound')}",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": [
            {
                "title": "Compound Identification",
                "content": {
                    "Name": merged.get("name"),
                    "Identifiers": merged.get("identifiers", {}),
                },
            },
            {
                "title": "Molecular Properties",
                "content": merged.get("molecular_properties", {}),
            },
            {
                "title": "Target Interactions",
                "content": {
                    "count": len(merged.get("targets", [])),
                    "targets": merged.get("targets", []),
                },
            },
            {
                "title": "Disease Indications",
                "content": {
                    "count": len(merged.get("indications", [])),
                    "indications": merged.get("indications", []),
                },
            },
            {
                "title": "Clinical Trials",
                "content": {
                    "count": len(merged.get("clinical_trials", [])),
                    "trials": merged.get("clinical_trials", []),
                },
            },
            {
                "title": "Data Sources",
                "content": merged.get("sources", []),
            },
            {
                "title": "Disclaimer",
                "content": "This report is generated from public databases for research purposes only. "
                           "It does not constitute medical advice or treatment recommendations. "
                           "All findings require clinical validation and professional interpretation.",
            },
        ],
    }


def export_drug_to_database(drug_data: dict[str, Any]) -> int:
    """Export drug data to local database."""
    merged = drug_data.get("merged", {})

    # Create drug record
    drug_record = {
        "source": "Merged",
        "source_id": merged.get("identifiers", {}).get("chembl_id") or merged.get("identifiers", {}).get("pubchem_cid") or "unknown",
        "name": merged.get("name"),
        "molecular_formula": merged.get("molecular_properties", {}).get("molecular_formula"),
        "molecular_weight": merged.get("molecular_properties", {}).get("molecular_weight"),
        "canonical_smiles": merged.get("identifiers", {}).get("canonical_smiles"),
        "inchikey": merged.get("identifiers", {}).get("inchikey"),
        "xlogp3": merged.get("molecular_properties", {}).get("xlogp3") or merged.get("molecular_properties", {}).get("alogp"),
        "tpsa": merged.get("molecular_properties", {}).get("tpsa") or merged.get("molecular_properties", {}).get("psa"),
        "hbond_donor_count": merged.get("molecular_properties", {}).get("hbond_donors") or merged.get("molecular_properties", {}).get("hbd"),
        "hbond_acceptor_count": merged.get("molecular_properties", {}).get("hbond_acceptors") or merged.get("molecular_properties", {}).get("hba"),
        "rotatable_bond_count": merged.get("molecular_properties", {}).get("rotatable_bonds") or merged.get("molecular_properties", {}).get("rtb"),
        "max_phase": merged.get("molecular_properties", {}).get("max_phase"),
        "source_url": ", ".join(s.get("url", "") for s in merged.get("sources", [])),
    }

    drug_id = db.upsert_drug(drug_record)

    # Add identifiers
    for id_type, value in merged.get("identifiers", {}).items():
        if value:
            db.add_drug_identifier(drug_id, id_type, value, "Merged")

    # Add targets and interactions
    for target in merged.get("targets", []):
        target_record = {
            "source": "Merged",
            "source_id": target.get("target_id") or target.get("target_symbol") or "unknown",
            "name": target.get("target_name"),
            "gene_symbol": target.get("gene_symbol"),
            "uniprot_id": target.get("uniprot_id"),
            "source_url": "",
        }
        target_db_id = db.upsert_target(target_record)

        interaction_record = {
            "drug_id": drug_id,
            "target_id": target_db_id,
            "interaction_type": "target",
            "mechanism_of_action": target.get("mechanism"),
            "action_type": target.get("action_type"),
            "evidence_source": ", ".join(target.get("sources", [])),
            "evidence_level": target.get("evidence_level", "unknown"),
            "confidence_score": target.get("confidence", 0.5),
            "source": "Merged",
        }
        db.upsert_drug_target_interaction(interaction_record)

    # Add indications
    for ind in merged.get("indications", []):
        disease_record = {
            "source": "Merged",
            "source_id": ind.get("disease_id") or ind.get("disease_name") or "unknown",
            "disease_name": ind.get("disease_name"),
            "source_url": "",
        }
        disease_id = db.upsert_disease(disease_record)
        db.upsert_drug_disease_indication({
            "drug_id": drug_id,
            "disease_id": disease_id,
            "max_phase_for_indication": ind.get("max_phase"),
            "source": "Merged",
        })

    return drug_id