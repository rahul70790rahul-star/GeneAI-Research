"""Serial protein lookup, structure analysis, evidence normalization, and persistence."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from geneai.database.protein_schema import store_protein_analysis
from geneai.drug_discovery import api_clients, protein_api
from geneai.drug_discovery.protein_structure import (
    analyze_protein_sequence,
    compare_structure_chains,
    extract_chain_sequence,
    find_ligand_neighborhood_pockets,
    parse_structure_file,
)
from geneai.sequence import parse_sequence_file

logger = logging.getLogger(__name__)
INPUT_KINDS = {"Protein FASTA", "UniProt ID", "NCBI Protein ID", "PDB ID", "Protein name", "Gene symbol"}


@dataclass(frozen=True)
class ProteinAnalysisRequest:
    """Bounded user inputs for a single protein analysis run."""

    input_kind: str
    query: str = ""
    sequence_text: str = ""
    fasta_data: bytes | None = None
    fasta_filename: str = "protein.fasta"
    structure_data: bytes | None = None
    structure_filename: str = "structure.pdb"
    selected_record_key: str = ""
    selected_structure_key: str = ""
    selected_chain: str = ""
    highlight_residue: int | None = None
    comparison_data: bytes | None = None
    comparison_filename: str = "comparison.cif"
    comparison_chain: str = ""
    disease_context: dict[str, Any] = field(default_factory=dict)
    vcf_preview: list[dict[str, Any]] = field(default_factory=list)


def _record_key(record: dict[str, Any]) -> str:
    source = str(record.get("source") or "protein").lower().replace(" ", "_")
    identifier = str(record.get("primary_accession") or record.get("pdb_id") or record.get("ncbi_protein_id") or record.get("protein_name") or "unknown")
    return f"{source}:{identifier}"


def _fasta_records(request: ProteinAnalysisRequest) -> list[dict[str, Any]]:
    if request.fasta_data:
        records = parse_sequence_file(request.fasta_data, request.fasta_filename)
    elif request.sequence_text.strip():
        records = parse_sequence_file(request.sequence_text.encode("utf-8"), "pasted_protein.fasta")
    else:
        raise ValueError("Upload a protein FASTA file or paste a protein sequence.")
    return [
        {
            "record_key": f"user_fasta:{record['id']}",
            "primary_accession": record["id"],
            "gene_symbol": None,
            "protein_name": record["id"],
            "organism": None,
            "sequence": record["sequence"],
            "sequence_length": len(record["sequence"]),
            "function": "",
            "subcellular_location": "",
            "family_annotations": [],
            "ec_numbers": [],
            "features": [],
            "domains": [],
            "interactions": [],
            "source": "User-provided FASTA",
            "source_release": "not applicable",
            "source_url": "",
            "sequence_source": "User-provided FASTA",
        }
        for record in records
    ]


def lookup_protein_records(request: ProteinAnalysisRequest) -> dict[str, Any]:
    """Retrieve protein records and structure candidates; APIs run serially."""
    if request.input_kind not in INPUT_KINDS:
        raise ValueError("Choose a supported protein input type.")
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data_sources: list[dict[str, Any]] = []
    limitations: list[str] = []
    candidates: list[dict[str, Any]] = []
    go_annotations: list[dict[str, Any]] = []

    if request.input_kind == "Protein FASTA":
        records = _fasta_records(request)
        data_sources.append({"source": "User-provided FASTA", "status": "available", "record_count": len(records), "version": "user file"})
    elif request.input_kind == "NCBI Protein ID":
        if not request.query.strip():
            raise ValueError("Enter an NCBI Protein ID or accession.")
        try:
            record = protein_api.fetch_ncbi_protein(request.query)
            record["record_key"] = _record_key(record)
            record["sequence_source"] = "NCBI Protein FASTA"
            records = [record]
            data_sources.append({"source": "NCBI Protein E-utilities", "status": "available", "record_count": 1, "version": "not reported by E-utilities", "url": "https://www.ncbi.nlm.nih.gov/protein/"})
        except (ValueError, api_clients.DataSourceError) as exc:
            data_sources.append({"source": "NCBI Protein E-utilities", "status": "unavailable", "record_count": 0, "error": str(exc)})
            raise
    elif request.input_kind == "PDB ID":
        if not request.query.strip():
            raise ValueError("Enter a four-character PDB identifier.")
        try:
            pdb_record = protein_api.fetch_rcsb_entry_metadata(request.query)
            pdb_record["candidate_key"] = f"RCSB:{pdb_record['pdb_id']}"
            candidates.append(pdb_record)
            records = [{
                "record_key": f"rcsb_pdb:{pdb_record['pdb_id']}",
                "primary_accession": pdb_record["pdb_id"],
                "pdb_id": pdb_record["pdb_id"],
                "gene_symbol": None,
                "protein_name": pdb_record.get("title") or f"PDB entry {pdb_record['pdb_id']}",
                "organism": None,
                "sequence": "",
                "sequence_length": 0,
                "function": "",
                "subcellular_location": "",
                "family_annotations": [],
                "ec_numbers": [],
                "features": [],
                "domains": [],
                "interactions": [],
                "source": "RCSB PDB",
                "source_release": "live archive",
                "source_url": pdb_record.get("source_url", ""),
                "sequence_source": "will be extracted from the selected structure",
            }]
            data_sources.append({"source": "RCSB PDB Data API", "status": "available", "record_count": 1, "version": "live archive", "url": pdb_record.get("source_url")})
            try:
                pdbe = protein_api.fetch_pdbe_summary(pdb_record["pdb_id"])
                pdb_record["pdbe_metadata"] = pdbe
                if not pdb_record.get("experimental_method"):
                    pdb_record["experimental_method"] = pdbe.get("experimental_method")
                if pdb_record.get("resolution_angstrom") is None:
                    pdb_record["resolution_angstrom"] = pdbe.get("resolution_angstrom")
                data_sources.append({"source": "PDBe REST API", "status": "available", "record_count": 1, "version": "not reported", "url": pdbe.get("source_url")})
            except api_clients.DataSourceError as exc:
                data_sources.append({"source": "PDBe REST API", "status": "unavailable", "record_count": 0, "error": str(exc)})
        except (ValueError, api_clients.DataSourceError) as exc:
            data_sources.append({"source": "RCSB PDB Data API", "status": "unavailable", "record_count": 0, "error": str(exc)})
            raise
    else:
        if not request.query.strip():
            raise ValueError("Enter a UniProt ID, protein name, or gene symbol.")
        try:
            records = protein_api.search_uniprot_protein(request.query, request.input_kind)
            for record in records:
                record["record_key"] = _record_key(record)
            data_sources.append({"source": "UniProt REST API", "status": "available", "record_count": len(records), "version": records[0].get("source_release", "not reported") if records else "not reported", "url": "https://www.uniprot.org/"})
        except (ValueError, api_clients.DataSourceError) as exc:
            data_sources.append({"source": "UniProt REST API", "status": "unavailable", "record_count": 0, "error": str(exc)})
            raise
        if not records:
            return {
                "retrieved_at": retrieved_at,
                "request": {"input_kind": request.input_kind, "query": request.query},
                "protein_records": [], "structure_candidates": [], "go_annotations": [],
                "data_sources": data_sources,
                "limitations": ["No matching protein record was returned by the selected source."],
            }
        for record in records[:5]:
            accession = record.get("primary_accession")
            if not accession:
                continue
            pdb_records: list[dict[str, Any]] = []
            try:
                pdb_records = protein_api.search_rcsb_structures(accession, limit=5)
                for pdb in pdb_records:
                    pdb["candidate_key"] = f"RCSB:{pdb.get('pdb_id')}"
                    pdb["record_key"] = record["record_key"]
                    candidates.append(pdb)
                data_sources.append({"source": "RCSB PDB Search/Data API", "status": "available", "record_count": len(pdb_records), "version": "live archive", "url": "https://www.rcsb.org/"})
            except (ValueError, api_clients.DataSourceError) as exc:
                data_sources.append({"source": "RCSB PDB Search/Data API", "status": "unavailable", "record_count": 0, "error": str(exc)})
                limitations.append(f"RCSB structure lookup unavailable for {accession}: {exc}")
            if pdb_records:
                pdbe_records = [item.get("pdbe_metadata") for item in pdb_records if isinstance(item.get("pdbe_metadata"), dict)]
                pdbe_errors = [item.get("pdbe_error") for item in pdb_records if item.get("pdbe_error")]
                data_sources.append({
                    "source": "PDBe REST API",
                    "status": "available" if pdbe_records else "unavailable",
                    "record_count": len(pdbe_records),
                    "version": "not reported",
                    "url": "https://www.ebi.ac.uk/pdbe/",
                    "error": "; ".join(str(error) for error in pdbe_errors) if pdbe_errors else "",
                })
            else:
                data_sources.append({"source": "PDBe REST API", "status": "not queried", "record_count": 0, "details": "No matching RCSB structure references were returned."})
            try:
                alpha_records = protein_api.get_alphafold_predictions(accession)
                for alpha in alpha_records[:5]:
                    alpha["candidate_key"] = f"AlphaFold:{alpha.get('structure_id')}"
                    alpha["record_key"] = record["record_key"]
                    candidates.append(alpha)
                data_sources.append({"source": "AlphaFold Protein Structure Database", "status": "available", "record_count": len(alpha_records), "version": "model version included per record", "url": "https://alphafold.ebi.ac.uk/"})
            except (ValueError, api_clients.DataSourceError) as exc:
                data_sources.append({"source": "AlphaFold Protein Structure Database", "status": "unavailable", "record_count": 0, "error": str(exc)})
                limitations.append(f"AlphaFold lookup unavailable for {accession}: {exc}")
        accessions = [str(record.get("primary_accession")) for record in records[:5] if record.get("primary_accession")]
        if accessions:
            try:
                go_annotations = api_clients.fetch_quickgo_annotations(accessions, limit=200)
                data_sources.append({"source": "QuickGO / Gene Ontology Annotation", "status": "available", "record_count": len(go_annotations), "version": "annotation evidence included per record", "url": "https://www.ebi.ac.uk/QuickGO/"})
            except (ValueError, api_clients.DataSourceError) as exc:
                data_sources.append({"source": "QuickGO / Gene Ontology Annotation", "status": "unavailable", "record_count": 0, "error": str(exc)})
                limitations.append(f"QuickGO annotations unavailable: {exc}")

    if len(records) > 1:
        limitations.append("More than one protein record matched; select the intended record before structure analysis.")
    return {
        "retrieved_at": retrieved_at,
        "request": {"input_kind": request.input_kind, "query": request.query},
        "protein_records": records,
        "structure_candidates": candidates,
        "go_annotations": go_annotations,
        "data_sources": data_sources,
        "limitations": limitations,
    }


def _context_matches(record: dict[str, Any], request: ProteinAnalysisRequest) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gene_symbol = str(record.get("gene_symbol") or "").upper()
    disease_result = request.disease_context if isinstance(request.disease_context, dict) else {}
    disease_name = (disease_result.get("disease") or {}).get("name")
    disease_matches = [
        {
            "disease_name": disease_name,
            "disease_id": (disease_result.get("disease") or {}).get("disease_id"),
            "association_score": item.get("association_score"),
            "source": item.get("source", "Open Targets Platform"),
            "source_url": item.get("source_url"),
            "interpretation": "Existing Phase 4.2 association record; not proof of causality or target validity.",
        }
        for item in disease_result.get("genes", [])
        if gene_symbol and str(item.get("gene_symbol", "")).upper() == gene_symbol
    ]
    variant_matches = []
    for variant in request.vcf_preview:
        if not isinstance(variant, dict):
            continue
        raw_gene = str(variant.get("gene_info_source_field") or "")
        symbols = {part.partition(":")[0].strip().upper() for part in raw_gene.split("|")}
        if gene_symbol and gene_symbol in symbols:
            variant_matches.append({
                key: variant.get(key)
                for key in ("chrom", "pos", "id", "ref", "alt", "variant_type", "gene_info_source_field", "consequence_source_field", "hgvs_source_field", "clinvar_significance_source_field")
                if key in variant
            })
    return disease_matches, variant_matches


def analyze_protein_record(
    lookup: dict[str, Any],
    request: ProteinAnalysisRequest,
    *,
    structure_candidate_key: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    """Analyze sequence and optional coordinates, then persist source metadata."""
    records = lookup.get("protein_records") or []
    if not records:
        raise ValueError("No protein record is available to analyze.")
    record = next((item for item in records if item.get("record_key") == request.selected_record_key), records[0])
    record = dict(record)
    candidates = lookup.get("structure_candidates") or []
    selected_candidate = None
    if structure_candidate_key:
        selected_candidate = next((item for item in candidates if item.get("candidate_key") == structure_candidate_key), None)
        if selected_candidate is None:
            raise ValueError("Selected structure is not present in the current source results.")

    structure_data: bytes | None = request.structure_data
    structure_filename = request.structure_filename
    structure_metadata: dict[str, Any] = {}
    if structure_data:
        structure_metadata = {
            "structure_id": structure_filename,
            "structure_source": "User-uploaded structure file",
            "structure_type": "method not reported for uploaded file; user should verify source",
            "format": "PDB" if structure_filename.lower().endswith(".pdb") else "mmCIF",
            "source_url": "",
        }
    elif selected_candidate:
        structure_data = protein_api.download_structure_file(selected_candidate, selected_candidate.get("format", "mmCIF"))
        structure_filename = f"{selected_candidate.get('structure_id', 'structure')}.{'pdb' if selected_candidate.get('format') == 'PDB' else 'cif'}"
        structure_metadata = dict(selected_candidate)
        structure_metadata.setdefault("structure_id", selected_candidate.get("pdb_id"))
    structure_object = None
    structure_summary: dict[str, Any] | None = None
    pockets: list[dict[str, Any]] = []
    structure_text = None
    if structure_data:
        structure_object, structure_summary = parse_structure_file(structure_data, structure_filename)
        structure_summary.update({
            key: structure_metadata.get(key)
            for key in ("structure_id", "structure_source", "structure_type", "format", "experimental_method", "resolution_angstrom", "resolution_values_angstrom", "model_version", "source_url", "release_date", "global_plddt")
            if structure_metadata.get(key) is not None
        })
        structure_summary["metadata_resolution_angstrom"] = structure_metadata.get("resolution_angstrom")
        structure_summary["metadata_experimental_method"] = structure_metadata.get("experimental_method")
        try:
            pockets = find_ligand_neighborhood_pockets(structure_object)
        except (ValueError, KeyError) as exc:
            logger.info("Ligand-neighborhood pocket analysis was unavailable: %s", exc)
            structure_summary.setdefault("limitations", []).append(f"Candidate ligand-neighborhood analysis unavailable: {exc}")
        structure_text = structure_data.decode("utf-8", errors="replace")
        chain_id = request.selected_chain or (structure_summary.get("chains") or [{}])[0].get("chain_id", "")
        chains = {item.get("chain_id"): item for item in structure_summary.get("chains", [])}
        selected_chain_summary = chains.get(chain_id)
        if not selected_chain_summary:
            raise ValueError("Selected protein chain was not found in the loaded structure.")
        if not record.get("sequence"):
            try:
                record["sequence"] = extract_chain_sequence(structure_object[0][chain_id])
                record["sequence_length"] = len(record["sequence"])
                record["sequence_source"] = "Extracted from the selected structure chain"
            except (KeyError, IndexError):
                record["sequence"] = selected_chain_summary.get("sequence", "")
    else:
        chain_id = ""
        selected_chain_summary = None

    sequence = str(record.get("sequence") or "")
    sequence_metrics = analyze_protein_sequence(sequence) if sequence else None
    if not sequence and structure_summary:
        raise ValueError("No protein sequence could be retrieved or extracted from the selected chain.")
    limitations = list(lookup.get("limitations", []))
    if sequence_metrics:
        limitations.extend(sequence_metrics.get("limitations", []))
    if structure_summary:
        limitations.extend(structure_summary.get("limitations", []))
    disease_matches, variant_matches = _context_matches(record, request)
    source_versions = {
        item.get("source"): item.get("version", "not reported")
        for item in lookup.get("data_sources", [])
        if item.get("status") == "available"
    }
    result: dict[str, Any] = {
        "schema_version": "4.4.0",
        "analysis_id": str(uuid4()),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protein": record,
        "sequence_analysis": sequence_metrics,
        "structure": structure_summary,
        "selected_chain": selected_chain_summary,
        "selected_chain_id": chain_id,
        "_highlight_residue": request.highlight_residue,
        "pockets": pockets,
        "go_annotations": lookup.get("go_annotations", []),
        "disease_associations_from_phase_4_2": disease_matches,
        "variant_records_from_phase_3_vcf_preview": variant_matches,
        "data_sources": lookup.get("data_sources", []),
        "source_versions": source_versions,
        "limitations": list(dict.fromkeys(limitations)),
        "target_interpretation": "Protein structure and annotations are research evidence only; this analysis does not validate a therapeutic target.",
        "research_only_disclaimer": "Research use only. Predicted structures, sequence metrics, and ligand-contact regions are not experimental validation, clinical advice, or proof of druggability.",
        "drug_discovery_handoff": {
            "protein_id": record.get("primary_accession"),
            "gene_symbol": record.get("gene_symbol"),
            "protein_sequence": sequence,
            "structure_id": (structure_summary or {}).get("structure_id"),
            "structure_source": (structure_summary or {}).get("structure_source"),
            "structure_type": (structure_summary or {}).get("structure_type"),
            "chain_information": (structure_summary or {}).get("chains", []),
            "candidate_binding_pockets": pockets,
            "important_residues": [residue for pocket in pockets for residue in pocket.get("nearby_residues", [])],
            "protein_function": record.get("function"),
            "disease_associations": disease_matches,
            "data_sources": lookup.get("data_sources", []),
            "limitations": list(dict.fromkeys(limitations)),
        },
        "storage": {"status": "not requested"},
    }
    if structure_text is not None:
        result["_structure_text"] = structure_text
        result["_structure_bytes"] = structure_data
        result["_structure_filename"] = structure_filename
    if request.comparison_data and structure_object is not None:
        try:
            comparison, _ = parse_structure_file(request.comparison_data, request.comparison_filename)
            chain_options = [item.get("chain_id", "") for item in structure_summary.get("chains", [])]
            chain_a = request.selected_chain or (chain_options[0] if chain_options else "")
            chain_b_options = [str(chain.id or " ") for chain in comparison[0].get_chains()]
            chain_b = request.comparison_chain or (chain_b_options[0] if chain_b_options else "")
            result["structure_comparison"] = compare_structure_chains(structure_object, comparison, chain_a, chain_b)
        except (ValueError, KeyError, IndexError) as exc:
            result["structure_comparison"] = {"status": "unavailable", "reason": str(exc)}
            result["limitations"].append(f"Structure comparison was not calculated: {exc}")
    elif request.comparison_data:
        result["structure_comparison"] = {"status": "unavailable", "reason": "Load a primary structure before comparison."}

    if persist:
        try:
            store_protein_analysis(result)
            result["storage"] = {"status": "saved", "analysis_id": result["analysis_id"]}
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.exception("Could not save protein analysis %s", result["analysis_id"])
            result["storage"] = {"status": "unavailable", "error": str(exc)}
            result["limitations"].append("Analysis results are available in this session but were not saved to SQLite.")
    return result


def run_protein_structure_agent(
    request: ProteinAnalysisRequest,
    *,
    structure_candidate_key: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    """Run lookup followed by sequence/structure analysis in a single serial agent."""
    lookup = lookup_protein_records(request)
    return analyze_protein_record(
        lookup,
        request,
        structure_candidate_key=structure_candidate_key,
        persist=persist,
    )
