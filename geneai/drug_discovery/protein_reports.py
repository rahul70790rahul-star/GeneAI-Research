"""Source-attributed protein analysis CSV, JSON, and compact PDF exports."""
from __future__ import annotations

import csv
import io
import json
import re
import textwrap
import unicodedata
from datetime import datetime, timezone
from typing import Any


def _clean_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if not key.startswith("_")}


def protein_report_json(result: dict[str, Any]) -> bytes:
    """Serialize structured annotations, metrics, provenance, and limitations."""
    return json.dumps(_clean_result(result), ensure_ascii=False, indent=2, default=str).encode("utf-8")


def protein_report_csv(result: dict[str, Any]) -> bytes:
    """Export one summary row with a flattened protein and structure assessment."""
    protein = result.get("protein") or {}
    sequence = result.get("sequence_analysis") or {}
    structure = result.get("structure") or {}
    mutation = result.get("protein_mutation_comparison") or {}
    source_rows = result.get("data_sources", [])
    row = {
        "analysis_id": result.get("analysis_id"),
        "protein_id": protein.get("primary_accession"),
        "gene_symbol": protein.get("gene_symbol"),
        "protein_name": protein.get("protein_name"),
        "organism": protein.get("organism"),
        "protein_function": protein.get("function"),
        "protein_family": "; ".join(protein.get("family_annotations", [])),
        "ec_numbers": "; ".join(protein.get("ec_numbers", [])),
        "sequence_length": sequence.get("length_residues"),
        "molecular_weight_da": sequence.get("molecular_weight_da"),
        "theoretical_pi": sequence.get("theoretical_pi"),
        "instability_index": sequence.get("instability_index"),
        "aliphatic_index": sequence.get("aliphatic_index"),
        "gravy": sequence.get("gravy"),
        "structure_id": structure.get("structure_id"),
        "structure_source": structure.get("structure_source"),
        "structure_type": structure.get("structure_type"),
        "experimental_method": structure.get("experimental_method"),
        "resolution_angstrom": structure.get("resolution_angstrom"),
        "chain_count": structure.get("chain_count"),
        "protein_residue_count": structure.get("protein_residue_count"),
        "candidate_pocket_count": len(result.get("pockets", [])),
        "protein_substitution": mutation.get("notation"),
        "substitution_hydropathy_change": mutation.get("kyte_doolittle_change"),
        "substitution_metric_deltas": json.dumps(mutation.get("theoretical_sequence_metric_deltas", {}), ensure_ascii=False),
        "source_status": "; ".join(f"{item.get('source')}: {item.get('status')}" for item in source_rows),
        "source_url": protein.get("source_url"),
        "research_only_disclaimer": result.get("research_only_disclaimer"),
    }
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(row), extrasaction="ignore")
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def protein_report_text(result: dict[str, Any]) -> str:
    """Build a readable evidence report, without interpreting target validity."""
    protein = result.get("protein") or {}
    sequence = result.get("sequence_analysis") or {}
    structure = result.get("structure") or {}
    mutation = result.get("protein_mutation_comparison") or {}
    lines = [
        "GeneAI Research — Protein Structure Analysis Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Analysis ID: {result.get('analysis_id', 'Not available')}",
        "",
        result.get("research_only_disclaimer", "Research use only; computational output is not clinical or experimental validation."),
        "",
        "1. Protein record",
        f"Protein: {protein.get('protein_name', 'Not available')}",
        f"Protein ID: {protein.get('primary_accession', 'Not available')}",
        f"Gene symbol: {protein.get('gene_symbol') or 'Not available'}",
        f"Organism: {protein.get('organism') or 'Not available'}",
        f"Function: {protein.get('function') or 'Not provided by the selected source'}",
        f"Cellular location: {protein.get('subcellular_location') or 'Not provided by the selected source'}",
        f"Family annotations: {'; '.join(protein.get('family_annotations', [])) or 'Not provided'}",
        f"EC numbers: {'; '.join(protein.get('ec_numbers', [])) or 'Not provided'}",
        f"Source: {protein.get('source', 'Not available')} — {protein.get('source_url', '')}",
        "",
        "2. Sequence analysis",
        f"Length: {sequence.get('length_residues', protein.get('sequence_length', 'Not available'))} residues",
        f"Molecular weight: {sequence.get('molecular_weight_da') if sequence.get('molecular_weight_da') is not None else 'not calculated'} Da",
        f"Theoretical pI: {sequence.get('theoretical_pi') if sequence.get('theoretical_pi') is not None else 'not calculated'}",
        f"Instability index: {sequence.get('instability_index') if sequence.get('instability_index') is not None else 'not calculated'}",
        f"Aliphatic index: {sequence.get('aliphatic_index') if sequence.get('aliphatic_index') is not None else 'not calculated'}",
        f"GRAVY: {sequence.get('gravy') if sequence.get('gravy') is not None else 'not calculated'}",
        "",
        "2a. Single-residue protein substitution comparison",
        f"Substitution: {mutation.get('notation')}; reference={mutation.get('reference_residue')}; alternate={mutation.get('alternate_residue')}; reference matches sequence={mutation.get('reference_matches_sequence')}." if mutation else "No single-residue substitution comparison was provided.",
        f"Kyte-Doolittle change={mutation.get('kyte_doolittle_change')}; theoretical sequence metric deltas={mutation.get('theoretical_sequence_metric_deltas')}." if mutation else "",
        str(mutation.get("interpretation")) if mutation else "",
        *([f"- {item}" for item in mutation.get("limitations", [])] if mutation else []),
        "",
        "3. Structure information",
        f"Structure ID: {structure.get('structure_id') or 'Not loaded'}",
        f"Source/type: {structure.get('structure_source') or 'Not available'} / {structure.get('structure_type') or 'Not available'}",
        f"Format: {structure.get('format') or 'Not available'}",
        f"Experimental method: {structure.get('experimental_method') or 'Not reported'}",
        f"Resolution: {structure.get('resolution_angstrom') if structure.get('resolution_angstrom') is not None else 'Not reported'} Å",
        f"Protein residues: {structure.get('protein_residue_count', 'Not available')}; heavy atoms: {structure.get('heavy_atom_count', 'Not available')}",
        "",
        "4. Chains and candidate ligand-contact regions",
    ]
    for chain in structure.get("chains", []):
        lines.append(
            f"Chain {chain.get('chain_id')}: {chain.get('amino_acid_residues')} amino-acid residues; "
            f"{chain.get('heavy_atoms')} heavy atoms; sequence length {len(chain.get('sequence') or '')}."
        )
    pockets = result.get("pockets", [])
    if not pockets:
        lines.append("No deposited non-water ligand/cofactor neighborhood was detected in this structure.")
    for pocket in pockets:
        lines.append(
            f"{pocket.get('pocket_id')} around {pocket.get('ligand_or_cofactor')}; "
            f"{pocket.get('nearby_residue_count')} nearby residues; center={pocket.get('center_angstrom')}; "
            f"dimensions={pocket.get('dimensions_angstrom')} Å. {pocket.get('method')}"
        )
    lines.extend(["", "5. Functional annotations and interactions"])
    for annotation in result.get("go_annotations", []):
        lines.append(
            f"{annotation.get('go_id')} {annotation.get('go_name')}; aspect={annotation.get('aspect')}; "
            f"evidence={annotation.get('evidence_code')}; reference={annotation.get('reference')}; {annotation.get('source_url')}"
        )
    for interaction in protein.get("interactions", []):
        lines.append(f"UniProt interaction annotation: {interaction}")
    lines.extend(["", "6. Existing Phase 4.2 disease associations"])
    associations = result.get("disease_associations_from_phase_4_2", [])
    if not associations:
        lines.append("No matching disease association was present in the current Phase 4.2 session result.")
    for association in associations:
        lines.append(
            f"{association.get('disease_name')} ({association.get('disease_id')}); "
            f"Open Targets evidence score={association.get('association_score')}; {association.get('source_url')}"
        )
    lines.append("The disease association is source evidence, not proof of causality or target validity.")
    lines.extend(["", "7. Uploaded VCF preview matches"])
    variants = result.get("variant_records_from_phase_3_vcf_preview", [])
    if not variants:
        lines.append("No matching gene annotation was present in the current Phase 3 VCF preview.")
    for variant in variants:
        lines.append(f"{variant.get('chrom')}:{variant.get('pos')} {variant.get('ref')}>{variant.get('alt')} id={variant.get('id')}; annotations are shown as supplied in the VCF.")
    if result.get("structure_comparison"):
        lines.extend(["", "8. Structure comparison", str(result["structure_comparison"])])
    lines.extend(["", "9. Sources, versions, and retrieval status"])
    for source in result.get("data_sources", []):
        lines.append(f"{source.get('source')}: {source.get('status')}; version={source.get('version', 'not reported')}; records={source.get('record_count', 0)}")
        if source.get("error"):
            lines.append(f"  Error: {source['error']}")
    lines.extend(["", "10. Limitations"])
    for limitation in result.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.extend(["", "A structure-based contact region does not establish an active site, druggability, binding affinity, or therapeutic effect.", ""])
    return "\n".join(lines)


def protein_report_pdf(result: dict[str, Any]) -> bytes:
    """Create a compact, dependency-free text PDF."""
    text = protein_report_text(result)
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(raw_line, width=96, break_long_words=True, break_on_hyphens=False) or [""])
    pages = [wrapped[index:index + 52] for index in range(0, len(wrapped), 52)] or [["GeneAI Research Protein Report"]]
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    page_ids = [4 + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{value} 0 R" for value in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        commands = ["BT", "/F1 9 Tf", "50 756 Td", "12 TL"]
        for line in page_lines:
            safe = unicodedata.normalize("NFKD", line).encode("cp1252", errors="replace").decode("cp1252")
            safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({safe}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("cp1252", errors="replace")
        objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode("ascii"),
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ])
    pdf = bytearray(b"%PDF-1.4\n%GeneAI\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def protein_report_filename(protein_name: str, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", protein_name.lower()).strip("_") or "protein_analysis"
    extension = extension.lstrip(".").lower()
    if extension not in {"pdf", "csv", "json"}:
        raise ValueError("Report format must be PDF, CSV, or JSON.")
    return f"geneai_{slug}_protein_report.{extension}"
