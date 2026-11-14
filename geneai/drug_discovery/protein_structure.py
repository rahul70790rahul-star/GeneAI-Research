"""Bounded protein sequence, coordinate, pocket, and structural-comparison analysis."""
from __future__ import annotations

import io
import math
import re
from collections import Counter
from typing import Any

import numpy as np
from Bio.Align import PairwiseAligner
from Bio.PDB import MMCIFParser, NeighborSearch, PDBParser, Superimposer
from Bio.PDB.Polypeptide import is_aa
from Bio.SeqUtils import seq1, seq3
from Bio.SeqUtils.ProtParam import ProteinAnalysis

MAX_PROTEIN_SEQUENCE_LENGTH = 250_000
MAX_STRUCTURE_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_STRUCTURE_COMPARISON_RESIDUES = 5_000
_STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")
_AMBIGUOUS_AA = set("BZJXUO")
_VALID_AA = _STANDARD_AA | _AMBIGUOUS_AA
_HYDROPATHY = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
_WATER_NAMES = {"HOH", "WAT", "DOD", "H2O"}
_ONE_TO_THREE = {residue: seq3(residue).upper() for residue in _STANDARD_AA}
_THREE_TO_ONE = {three: one for one, three in _ONE_TO_THREE.items()}


def normalize_protein_sequence(sequence: str) -> str:
    """Validate and normalize one amino-acid sequence without guessing residues."""
    if not isinstance(sequence, str):
        raise ValueError("Protein sequence must be text.")
    cleaned = re.sub(r"\s+", "", sequence).upper()
    if cleaned.startswith(">"):
        raise ValueError("Select or paste the FASTA record sequence without its header.")
    if cleaned.endswith("*"):
        cleaned = cleaned[:-1]
    if not cleaned:
        raise ValueError("Enter or upload a protein sequence first.")
    if len(cleaned) > MAX_PROTEIN_SEQUENCE_LENGTH:
        raise ValueError(f"Protein sequences are limited to {MAX_PROTEIN_SEQUENCE_LENGTH:,} residues.")
    invalid = sorted(set(cleaned) - _VALID_AA)
    if invalid:
        raise ValueError(f"Unsupported protein symbol(s): {', '.join(invalid)}.")
    if "*" in cleaned:
        raise ValueError("Stop symbols are allowed only at the end of a protein sequence.")
    return cleaned


def analyze_protein_sequence(sequence: str) -> dict[str, Any]:
    """Calculate source-independent sequence properties using Biopython ProtParam.

    Biophysical metrics are left unavailable when ambiguous or non-canonical amino
    acids occur; the code does not silently remove or impute those residues.
    """
    seq = normalize_protein_sequence(sequence)
    counts = Counter(seq)
    composition = {
        amino_acid: {
            "count": counts.get(amino_acid, 0),
            "fraction": round(counts.get(amino_acid, 0) / len(seq), 6),
        }
        for amino_acid in "ACDEFGHIKLMNPQRSTVWYBZJXUO"
    }
    hydrophobic = [aa for aa, score in _HYDROPATHY.items() if score > 0]
    hydrophilic = [aa for aa, score in _HYDROPATHY.items() if score < 0]
    neutral = [aa for aa, score in _HYDROPATHY.items() if score == 0]
    hydrophobic_count = sum(counts.get(aa, 0) for aa in hydrophobic)
    hydrophilic_count = sum(counts.get(aa, 0) for aa in hydrophilic)
    neutral_count = sum(counts.get(aa, 0) for aa in neutral)
    canonical_count = sum(counts.get(aa, 0) for aa in _STANDARD_AA)
    metrics: dict[str, Any] = {
        "molecular_weight_da": None,
        "theoretical_pi": None,
        "instability_index": None,
        "aliphatic_index": None,
        "gravy": None,
    }
    limitations: list[str] = []
    if canonical_count == len(seq):
        analysis = ProteinAnalysis(seq)
        percentage_method = getattr(analysis, "get_amino_acids_percent", None)
        percentages = percentage_method() if callable(percentage_method) else analysis.amino_acids_percent
        percentage_total = sum(float(value) for value in percentages.values())
        percentage_scale = 1.0 if percentage_total > 1.5 else 100.0
        metrics.update({
            "molecular_weight_da": round(float(analysis.molecular_weight()), 3),
            "theoretical_pi": round(float(analysis.isoelectric_point()), 3),
            "instability_index": round(float(analysis.instability_index()), 3),
            "aliphatic_index": round(
                percentage_scale * (
                    percentages.get("A", 0.0)
                    + 2.9 * percentages.get("V", 0.0)
                    + 3.9 * (percentages.get("I", 0.0) + percentages.get("L", 0.0))
                ),
                3,
            ),
            "gravy": round(float(analysis.gravy()), 4),
        })
    else:
        limitations.append(
            "Biophysical metrics require only the 20 standard amino acids; this sequence contains ambiguous or non-canonical symbols, so those metrics were not calculated."
        )
    limitations.append("Theoretical sequence properties are computational estimates and are not experimental measurements.")
    return {
        "length_residues": len(seq),
        "sequence_sha256": __import__("hashlib").sha256(seq.encode("ascii")).hexdigest(),
        "composition": composition,
        **metrics,
        "hydropathy_scale": "Kyte-Doolittle; positive residues grouped as hydrophobic, negative as hydrophilic, zero as neutral.",
        "hydropathy_distribution": {
            "hydrophobic_count": hydrophobic_count,
            "hydrophobic_fraction": round(hydrophobic_count / len(seq), 6),
            "hydrophilic_count": hydrophilic_count,
            "hydrophilic_fraction": round(hydrophilic_count / len(seq), 6),
            "neutral_count": neutral_count,
            "neutral_fraction": round(neutral_count / len(seq), 6),
            "ambiguous_or_noncanonical_count": len(seq) - canonical_count,
        },
        "limitations": limitations,
    }


def compare_protein_substitution(sequence: str, notation: str) -> dict[str, Any]:
    """Validate and compare a single amino-acid substitution against a sequence.

    The comparison is sequence-level only. It does not generate a mutant structure
    or infer stability, function, pathogenicity, or binding effects.
    """
    normalized = normalize_protein_sequence(sequence)
    if not isinstance(notation, str) or len(notation.strip()) > 32:
        raise ValueError("Enter one protein substitution such as p.Gly12Asp or p.G12D.")
    match = re.fullmatch(r"(?:p\.)?\(?([A-Za-z]{1,3})(\d+)([A-Za-z]{1,3})\)?", notation.strip())
    if not match:
        raise ValueError("Use one substitution in the form p.Gly12Asp or p.G12D.")
    reference_token, position_text, alternate_token = match.groups()

    def _one_letter(token: str) -> str:
        token = token.upper()
        if len(token) == 1 and token in _STANDARD_AA:
            return token
        if len(token) == 3 and token in _THREE_TO_ONE:
            return _THREE_TO_ONE[token]
        raise ValueError("Use standard amino-acid codes for the reference and alternate residue.")

    reference = _one_letter(reference_token)
    alternate = _one_letter(alternate_token)
    position = int(position_text)
    if position < 1 or position > len(normalized):
        raise ValueError(f"Residue position must be between 1 and {len(normalized):,}.")
    observed = normalized[position - 1]
    if observed != reference:
        raise ValueError(
            f"Reference mismatch at position {position}: input sequence contains {observed}, but the variant specifies {reference}."
        )
    altered = normalized[:position - 1] + alternate + normalized[position:]
    before = analyze_protein_sequence(normalized)
    after = analyze_protein_sequence(altered)
    metric_names = ("molecular_weight_da", "theoretical_pi", "instability_index", "aliphatic_index", "gravy")
    deltas = {
        name: round(float(after[name]) - float(before[name]), 4)
        if before.get(name) is not None and after.get(name) is not None else None
        for name in metric_names
    }
    hydro_delta = _HYDROPATHY.get(alternate)
    hydro_delta = round(hydro_delta - _HYDROPATHY[reference], 3) if hydro_delta is not None else None
    return {
        "notation": notation.strip(),
        "position_1_based": position,
        "reference_residue": reference,
        "alternate_residue": alternate,
        "reference_matches_sequence": True,
        "same_amino_acid": reference == alternate,
        "kyte_doolittle_change": hydro_delta,
        "theoretical_sequence_metric_deltas": deltas,
        "interpretation": "Sequence-level reference/alternate comparison only; no mutant structure or functional effect was predicted.",
        "limitations": [
            "The reported property differences are theoretical calculations on the submitted sequence, not experimental measurements.",
            "This substitution check does not translate a nucleotide VCF record or validate transcript/protein HGVS mapping.",
            "No structural, stability, pathogenicity, drug-binding, or clinical effect is inferred.",
        ],
    }


def _structure_format(filename: str, text: str) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix in {"cif", "mmcif"}:
        return "mmcif"
    if suffix == "pdb" or text.startswith(("HEADER", "TITLE ", "ATOM  ", "MODEL ", "REMARK")):
        return "pdb"
    if text.lstrip().lower().startswith("data_"):
        return "mmcif"
    raise ValueError("Structure format must be PDB (.pdb) or mmCIF (.cif/.mmcif).")


def _chain_residues(chain: Any) -> list[Any]:
    return [residue for residue in chain.get_residues() if is_aa(residue, standard=False)]


def extract_chain_sequence(chain: Any) -> str:
    """Convert amino-acid residues in one Biopython chain to a sequence."""
    chars = []
    for residue in _chain_residues(chain):
        try:
            letter = seq1(residue.resname, custom_map={"MSE": "M", "SEC": "U", "PYL": "O"})
        except (KeyError, TypeError):
            letter = "X"
        chars.append(letter or "X")
    return "".join(chars)


def _disulfide_bonds(model: Any) -> list[dict[str, Any]]:
    sulfurs = []
    for residue in model.get_residues():
        if residue.resname == "CYS" and "SG" in residue:
            sulfurs.append((residue, residue["SG"]))
    bonds = []
    for index, (residue_a, atom_a) in enumerate(sulfurs):
        for residue_b, atom_b in sulfurs[index + 1:]:
            distance = float(atom_a - atom_b)
            if 1.8 <= distance <= 2.3:
                bonds.append({
                    "chain_a": residue_a.get_parent().id,
                    "residue_a": residue_a.id[1],
                    "chain_b": residue_b.get_parent().id,
                    "residue_b": residue_b.id[1],
                    "distance_angstrom": round(distance, 3),
                    "method": "SG–SG coordinate distance 1.8–2.3 Å; candidate disulfide bond",
                })
    return bonds


def parse_structure_file(data: bytes, filename: str) -> tuple[Any, dict[str, Any]]:
    """Parse a bounded PDB/mmCIF structure and summarize its first model."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("Structure file is empty or unreadable.")
    if len(data) > MAX_STRUCTURE_UPLOAD_BYTES:
        raise ValueError(f"Structure files are limited to {MAX_STRUCTURE_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("PDB and mmCIF files must be UTF-8 text.") from exc
    file_format = _structure_format(filename, text)
    try:
        parser = MMCIFParser(QUIET=True) if file_format == "mmcif" else PDBParser(QUIET=True)
        structure = parser.get_structure("geneai_protein", io.StringIO(text))
        models = list(structure.get_models())
        if not models:
            raise ValueError("Structure file contains no model coordinates.")
        model = models[0]
        atoms = [atom for atom in model.get_atoms() if atom.element.upper() not in {"H", "D"}]
        if not atoms:
            raise ValueError("Structure file contains no heavy-atom coordinates.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not parse this {file_format.upper()} structure: {exc}") from exc

    chains = []
    for chain in model.get_chains():
        residues = _chain_residues(chain)
        chain_atoms = [atom for atom in chain.get_atoms() if atom.element.upper() not in {"H", "D"}]
        if not residues and not chain_atoms:
            continue
        coords = np.asarray([atom.coord for atom in chain_atoms], dtype=float) if chain_atoms else np.zeros((0, 3))
        chain_id = str(chain.id or " ")
        chains.append({
            "chain_id": chain_id,
            "amino_acid_residues": len(residues),
            "heavy_atoms": len(chain_atoms),
            "sequence": extract_chain_sequence(chain),
            "residue_identifiers": [
                {"residue_name": residue.resname, "residue_number": residue.id[1], "insertion_code": str(residue.id[2] or "").strip()}
                for residue in residues
            ],
            "coordinate_bounds_angstrom": {
                "minimum": [round(float(value), 3) for value in coords.min(axis=0)] if len(coords) else None,
                "maximum": [round(float(value), 3) for value in coords.max(axis=0)] if len(coords) else None,
            },
        })
    header = getattr(structure, "header", {}) or {}
    missing = header.get("missing_residues", []) if isinstance(header, dict) else []
    structure_info = {
        "format": file_format,
        "filename": filename,
        "models": len(models),
        "analyzed_model": 0,
        "chain_count": len(chains),
        "chains": chains,
        "protein_residue_count": sum(chain["amino_acid_residues"] for chain in chains),
        "heavy_atom_count": len(atoms),
        "coordinate_bounds_angstrom": {
            "minimum": [round(float(value), 3) for value in np.asarray([atom.coord for atom in atoms]).min(axis=0)],
            "maximum": [round(float(value), 3) for value in np.asarray([atom.coord for atom in atoms]).max(axis=0)],
        },
        "header_missing_residues": missing if isinstance(missing, list) else [],
        "disulfide_bonds": _disulfide_bonds(model),
        "secondary_structure": {"status": "not calculated", "reason": "DSSP/mkdssp is not installed; secondary structure is not inferred from coordinates alone."},
        "metadata_resolution_angstrom": None,
        "metadata_experimental_method": None,
        "limitations": [
            "Only the first coordinate model is summarized.",
            "Residue numbering gaps are not labeled as missing residues unless the structure header reports them.",
            "Disulfides are coordinate-distance candidates; unusual geometry or alternate conformations may affect detection.",
        ],
    }
    return structure, structure_info


def find_ligand_neighborhood_pockets(structure: Any, *, cutoff_angstrom: float = 4.0) -> list[dict[str, Any]]:
    """Report protein neighborhoods around deposited non-water hetero residues.

    These are ligand/cofactor-contact regions observed in the structure, not a
    de novo pocket prediction or experimentally validated active-site call.
    """
    model = next(structure.get_models(), None)
    if model is None:
        return []
    protein_atoms = [
        atom for residue in model.get_residues()
        if is_aa(residue, standard=False)
        for atom in residue.get_atoms()
        if atom.element.upper() not in {"H", "D"}
    ]
    if not protein_atoms:
        return []
    search = NeighborSearch(protein_atoms)
    output = []
    for chain in model.get_chains():
        for ligand in chain.get_residues():
            if not str(ligand.id[0]).startswith("H_") or ligand.resname.upper() in _WATER_NAMES:
                continue
            ligand_atoms = [atom for atom in ligand.get_atoms() if atom.element.upper() not in {"H", "D"}]
            if len(ligand_atoms) < 4:
                continue
            contacts: dict[tuple[str, int, str, str], tuple[Any, float]] = {}
            for atom in ligand_atoms:
                for residue in search.search(atom.coord, cutoff_angstrom, "R"):
                    residue_key = (str(residue.get_parent().id), int(residue.id[1]), str(residue.id[2] or "").strip(), residue.resname)
                    min_distance = min(
                        float(atom - protein_atom)
                        for protein_atom in residue.get_atoms()
                        if protein_atom.element.upper() not in {"H", "D"}
                    )
                    if residue_key not in contacts or min_distance < contacts[residue_key][1]:
                        contacts[residue_key] = (residue, min_distance)
            coords = np.asarray([atom.coord for atom in ligand_atoms], dtype=float)
            if contacts:
                pocket_id = f"{chain.id}:{ligand.resname}:{ligand.id[1]}"
                contact_residues = [
                    {
                        "chain_id": key[0], "residue_number": key[1], "insertion_code": key[2],
                        "residue_name": key[3], "minimum_distance_angstrom": round(distance, 3),
                    }
                    for key, (_, distance) in sorted(contacts.items())
                ]
                output.append({
                    "pocket_id": pocket_id,
                    "ligand_or_cofactor": ligand.resname,
                    "ligand_residue_number": ligand.id[1],
                    "ligand_chain": chain.id,
                    "contact_cutoff_angstrom": cutoff_angstrom,
                    "nearby_residue_count": len(contact_residues),
                    "nearby_residues": contact_residues,
                    "center_angstrom": [round(float(value), 3) for value in coords.mean(axis=0)],
                    "dimensions_angstrom": [round(float(value), 3) for value in (coords.max(axis=0) - coords.min(axis=0))],
                    "method": "Deposited non-water hetero-residue contact neighborhood; not de novo pocket detection.",
                    "interpretation": "Candidate ligand-contact region only; does not establish active-site function, druggability, or binding affinity.",
                })
    return output[:50]


def compare_structure_chains(
    structure_a: Any,
    structure_b: Any,
    chain_a_id: str,
    chain_b_id: str,
    residue_range_a: tuple[int, int] | None = None,
    residue_range_b: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Sequence-map C-alpha residues, superpose, and return a defensible RMSD."""
    try:
        chain_a = structure_a[0][chain_a_id]
        chain_b = structure_b[0][chain_b_id]
    except (KeyError, IndexError) as exc:
        raise ValueError("Selected comparison chain was not found in one of the structures.") from exc
    residues_a = [residue for residue in _chain_residues(chain_a) if "CA" in residue]
    residues_b = [residue for residue in _chain_residues(chain_b) if "CA" in residue]
    sequence_a, sequence_b = extract_chain_sequence(chain_a), extract_chain_sequence(chain_b)
    if len(residues_a) != len(sequence_a) or len(residues_b) != len(sequence_b):
        raise ValueError("Could not map amino-acid residues consistently to C-alpha coordinates.")
    if max(len(sequence_a), len(sequence_b)) > MAX_STRUCTURE_COMPARISON_RESIDUES:
        raise ValueError(
            f"Structure comparison is limited to {MAX_STRUCTURE_COMPARISON_RESIDUES:,} residues per chain on this workstation-friendly workflow."
        )
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -3.0
    aligner.extend_gap_score = -0.5
    alignment = aligner.align(sequence_a, sequence_b)[0]
    indices = alignment.indices
    pairs = [
        (int(index_a), int(index_b))
        for index_a, index_b in zip(indices[0], indices[1])
        if index_a >= 0 and index_b >= 0
    ]
    for label, residue_range in (("first", residue_range_a), ("second", residue_range_b)):
        if residue_range is not None and (
            not isinstance(residue_range, tuple)
            or len(residue_range) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in residue_range)
            or residue_range[1] < residue_range[0]
        ):
            raise ValueError(f"The {label} structure residue range must contain integer start/end numbers in order.")
    if residue_range_a is not None:
        pairs = [pair for pair in pairs if residue_range_a[0] <= residues_a[pair[0]].id[1] <= residue_range_a[1]]
    if residue_range_b is not None:
        pairs = [pair for pair in pairs if residue_range_b[0] <= residues_b[pair[1]].id[1] <= residue_range_b[1]]
    if len(pairs) < 3:
        raise ValueError("At least three aligned C-alpha residue pairs are required to calculate RMSD.")
    fixed = [residues_a[index_a]["CA"] for index_a, _ in pairs]
    moving = [residues_b[index_b]["CA"] for _, index_b in pairs]
    superimposer = Superimposer()
    superimposer.set_atoms(fixed, moving)
    identical = sum(sequence_a[index_a] == sequence_b[index_b] for index_a, index_b in pairs)
    identity = identical / len(pairs)
    warning = None
    if identity < 0.5:
        warning = "Low sequence identity: residue correspondence and the resulting RMSD may be unreliable."
    elif len(pairs) < min(len(sequence_a), len(sequence_b)) * 0.5:
        warning = "Fewer than half of the shorter chain's residues aligned; RMSD describes only aligned C-alpha atoms."
    return {
        "chain_a": chain_a_id,
        "chain_b": chain_b_id,
        "residue_range_a": list(residue_range_a) if residue_range_a is not None else None,
        "residue_range_b": list(residue_range_b) if residue_range_b is not None else None,
        "sequence_length_a": len(sequence_a),
        "sequence_length_b": len(sequence_b),
        "aligned_ca_pairs": len(pairs),
        "sequence_identity_fraction": round(identity, 4),
        "rmsd_angstrom": round(float(superimposer.rms), 4),
        "method": "Global sequence alignment followed by least-squares C-alpha superposition (Biopython).",
        "warning": warning,
        "limitations": [
            "RMSD depends on the sequence alignment and selected chains; different constructs, missing residues, ligands, and conformational states can change the value.",
            "This is a research comparison, not a structural-quality or functional-equivalence score.",
        ],
    }


def build_structure_viewer_html(
    structure_text: str,
    file_format: str,
    *,
    chain_id: str | None = None,
    highlight_residue: int | None = None,
    representation: str = "Cartoon",
) -> str | None:
    """Render coordinates with the optional py3Dmol component; return None if absent."""
    try:
        import py3Dmol
    except ImportError:
        return None
    format_name = "pdb" if file_format.lower() == "pdb" else "cif"
    view = py3Dmol.view(width=850, height=560)
    view.addModel(structure_text, format_name)
    selection = {"chain": chain_id} if chain_id and chain_id.strip() else {}
    if representation.lower() == "surface":
        view.addSurface(py3Dmol.VDW, {"opacity": 0.65, "color": "white"}, selection)
    else:
        view.setStyle(selection, {"cartoon": {"color": "spectrum"}})
    if highlight_residue is not None:
        if not isinstance(highlight_residue, int) or highlight_residue < 1:
            raise ValueError("Residue highlight position must be a positive integer.")
        view.addStyle({**selection, "resi": highlight_residue}, {"stick": {"colorscheme": "Jmol"}})
    view.zoomTo(selection)
    return view._make_html()
