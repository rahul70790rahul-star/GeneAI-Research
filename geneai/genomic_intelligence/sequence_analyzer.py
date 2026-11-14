"""Genomic sequence analysis module."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from Bio.Seq import Seq
from Bio.SeqUtils import gc_fraction, molecular_weight
from Bio.SeqUtils.ProtParam import ProteinAnalysis

logger = logging.getLogger(__name__)


def GC(sequence: str) -> float:
    """Return GC content as a percentage.

    ``Bio.SeqUtils.GC`` was removed in Biopython 1.80; ``gc_fraction`` returns a
    fraction (0-1), so scale it to keep the historical 0-100 convention used by
    this module.
    """
    return gc_fraction(sequence) * 100.0


@dataclass
class SequenceFeatures:
    """Extracted sequence features."""
    length: int
    gc_content: float
    gc_skew: float
    at_skew: float
    cpg_islands: list[dict[str, Any]]
    orfs: list[dict[str, Any]]
    repeats: list[dict[str, Any]]
    motif_matches: dict[str, list[int]]
    composition: dict[str, float]
    molecular_weight: float
    isoelectric_point: float | None = None
    hydrophobicity: float | None = None
    instability_index: float | None = None
    aromaticity: float | None = None


class SequenceAnalyzer:
    """
    Analyze DNA, RNA, and protein sequences for genomic features.
    
    Capabilities:
    - Nucleotide composition and GC analysis
    - CpG island detection
    - Open reading frame (ORF) finding
    - Repeat identification
    - Motif searching
    - Protein property calculation
    """
    
    # Common regulatory motifs
    REGULATORY_MOTIFS = {
        "TATA_box": "TATAAA",
        "CAAT_box": "CCAAT",
        "GC_box": "GGGCGG",
        "E_box": "CANNTG",
        "Inr": "YYANWYY",
        "DPE": "RGWYVT",
        "BREu": "SSRCGCC",
        "BREd": "RTDKKKK",
        "polyA_signal": "AATAAA",
        "polyA_signal_alt": "ATTAAA",
        "splice_donor": "GT",
        "splice_acceptor": "AG",
        "kozak": "GCCRCCAUGG",
        "iron_response": "CAGUGN",
    }
    
    # Repeat patterns
    REPEAT_PATTERNS = {
        "microsatellite": r"(.{1,6})\1{5,}",
        "minisatellite": r"(.{7,100})\1{2,}",
        "telomeric": r"(TTAGGG){3,}",
        "centromeric": r"(AATGG){3,}",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, sequence: str, seq_type: str = "auto") -> SequenceFeatures:
        """
        Perform comprehensive sequence analysis.
        
        Args:
            sequence: DNA, RNA, or protein sequence
            seq_type: "dna", "rna", "protein", or "auto"
            
        Returns:
            SequenceFeatures with all extracted features
        """
        sequence = sequence.upper().strip()
        
        # Auto-detect sequence type
        if seq_type == "auto":
            seq_type = self._detect_sequence_type(sequence)
        
        if seq_type in ("dna", "rna"):
            return self._analyze_nucleotide(sequence, seq_type)
        elif seq_type == "protein":
            return self._analyze_protein(sequence)
        else:
            raise ValueError(f"Unknown sequence type: {seq_type}")
    
    def _detect_sequence_type(self, sequence: str) -> str:
        """Auto-detect sequence type from composition."""
        bases = set(sequence)
        if bases.issubset({"A", "T", "G", "C"}):
            return "dna"
        elif bases.issubset({"A", "U", "G", "C"}):
            return "rna"
        else:
            return "protein"
    
    def _analyze_nucleotide(self, sequence: str, seq_type: str) -> SequenceFeatures:
        """Analyze DNA/RNA sequence."""
        seq_obj = Seq(sequence)
        
        # Basic composition
        composition = self._get_nucleotide_composition(sequence)
        gc_content = GC(sequence)
        
        # GC skew
        gc_skew = self._calculate_gc_skew(sequence)
        at_skew = self._calculate_at_skew(sequence)
        
        # CpG islands
        cpg_islands = self._find_cpg_islands(sequence)
        
        # ORFs
        orfs = self._find_orfs(sequence)
        
        # Repeats
        repeats = self._find_repeats(sequence)
        
        # Motif matches
        motif_matches = self._find_motifs(sequence)
        
        # Molecular weight
        mol_weight = molecular_weight(seq_obj, seq_type=seq_type)
        
        return SequenceFeatures(
            length=len(sequence),
            gc_content=gc_content,
            gc_skew=gc_skew,
            at_skew=at_skew,
            cpg_islands=cpg_islands,
            orfs=orfs,
            repeats=repeats,
            motif_matches=motif_matches,
            composition=composition,
            molecular_weight=mol_weight,
        )
    
    def _analyze_protein(self, sequence: str) -> SequenceFeatures:
        """Analyze protein sequence."""
        # Composition
        composition = self._get_amino_acid_composition(sequence)
        
        # Protein properties using BioPython
        try:
            prot_analysis = ProteinAnalysis(sequence)
            mol_weight = prot_analysis.molecular_weight()
            isoelectric_point = prot_analysis.isoelectric_point()
            hydrophobicity = prot_analysis.gravy()  # Grand average of hydropathy
            instability_index = prot_analysis.instability_index()
            aromaticity = prot_analysis.aromaticity()
        except Exception as e:
            self.logger.warning("Protein analysis failed: %s", e)
            mol_weight = molecular_weight(Seq(sequence), seq_type="protein")
            isoelectric_point = None
            hydrophobicity = None
            instability_index = None
            aromaticity = None
        
        # Find motifs in protein
        motif_matches = self._find_protein_motifs(sequence)
        
        return SequenceFeatures(
            length=len(sequence),
            gc_content=0.0,
            gc_skew=0.0,
            at_skew=0.0,
            cpg_islands=[],
            orfs=[],
            repeats=[],
            motif_matches=motif_matches,
            composition=composition,
            molecular_weight=mol_weight,
            isoelectric_point=isoelectric_point,
            hydrophobicity=hydrophobicity,
            instability_index=instability_index,
            aromaticity=aromaticity,
        )
    
    def _get_nucleotide_composition(self, sequence: str) -> dict[str, float]:
        """Calculate nucleotide composition percentages."""
        total = len(sequence)
        if total == 0:
            return {}
        bases = ["A", "T", "G", "C", "U", "N"]
        return {base: sequence.count(base) / total * 100 for base in bases if base in sequence}
    
    def _get_amino_acid_composition(self, sequence: str) -> dict[str, float]:
        """Calculate amino acid composition percentages."""
        total = len(sequence)
        if total == 0:
            return {}
        aa_list = "ACDEFGHIKLMNPQRSTVWY"
        return {aa: sequence.count(aa) / total * 100 for aa in aa_list if aa in sequence}
    
    def _calculate_gc_skew(self, sequence: str) -> float:
        """Calculate GC skew: (G-C)/(G+C)."""
        g_count = sequence.count("G")
        c_count = sequence.count("C")
        total = g_count + c_count
        return (g_count - c_count) / total if total > 0 else 0.0
    
    def _calculate_at_skew(self, sequence: str) -> float:
        """Calculate AT skew: (A-T)/(A+T)."""
        a_count = sequence.count("A")
        t_count = sequence.count("T") + sequence.count("U")  # U for RNA
        total = a_count + t_count
        return (a_count - t_count) / total if total > 0 else 0.0
    
    def _find_cpg_islands(self, sequence: str, window: int = 200, 
                          min_gc: float = 0.5, min_obs_exp: float = 0.6) -> list[dict[str, Any]]:
        """Find CpG islands using sliding window."""
        islands = []
        seq_len = len(sequence)
        
        for i in range(0, seq_len - window + 1, window // 2):
            window_seq = sequence[i:i+window]
            gc = GC(window_seq)
            if gc < min_gc * 100:
                continue
            
            cpg_count = window_seq.count("CG")
            c_count = window_seq.count("C")
            g_count = window_seq.count("G")
            expected_cpg = (c_count * g_count) / window if window > 0 else 0
            obs_exp = cpg_count / expected_cpg if expected_cpg > 0 else 0
            
            if obs_exp >= min_obs_exp:
                islands.append({
                    "start": i,
                    "end": i + window,
                    "length": window,
                    "gc_content": gc,
                    "observed_expected_cpg": obs_exp,
                    "cpg_count": cpg_count,
                })
        
        # Merge overlapping islands
        return self._merge_intervals(islands)
    
    def _find_orfs(self, sequence: str, min_length: int = 30) -> list[dict[str, Any]]:
        """Find open reading frames in all 6 frames."""
        orfs = []
        seq_obj = Seq(sequence)
        
        # DNA: 6 frames (3 forward, 3 reverse complement)
        if "U" not in sequence:
            # Forward frames
            for frame in range(3):
                orfs.extend(self._find_orfs_in_frame(str(seq_obj[frame:]), frame + 1, min_length))
            
            # Reverse complement frames
            rev_comp = str(seq_obj.reverse_complement())
            for frame in range(3):
                orfs.extend(self._find_orfs_in_frame(rev_comp[frame:], -(frame + 1), min_length))
        else:
            # RNA: only 3 frames
            for frame in range(3):
                orfs.extend(self._find_orfs_in_frame(sequence[frame:], frame + 1, min_length))
        
        return sorted(orfs, key=lambda x: x["length"], reverse=True)[:50]
    
    def _find_orfs_in_frame(self, sequence: str, frame: int, min_length: int) -> list[dict[str, Any]]:
        """Find ORFs in a single reading frame."""
        orfs = []
        start_codons = {"ATG", "GTG", "TTG"}
        stop_codons = {"TAA", "TAG", "TGA"}
        
        # Convert to RNA for translation
        rna_seq = sequence.replace("T", "U")
        
        i = 0
        while i < len(rna_seq) - 2:
            codon = rna_seq[i:i+3].replace("U", "T")
            if codon in start_codons:
                # Look for stop codon
                for j in range(i, len(rna_seq) - 2, 3):
                    stop_codon = rna_seq[j:j+3].replace("U", "T")
                    if stop_codon in stop_codons:
                        orf_length = j + 3 - i
                        if orf_length >= min_length * 3:  # min_length in amino acids
                            orfs.append({
                                "frame": frame,
                                "start": i,
                                "end": j + 3,
                                "length_aa": orf_length // 3,
                                "length_nt": orf_length,
                                "sequence": sequence[i:j+3],
                                "protein": str(Seq(sequence[i:j+3]).translate(to_stop=True)),
                            })
                        break
            i += 3
        
        return orfs
    
    def _find_repeats(self, sequence: str) -> list[dict[str, Any]]:
        """Find repetitive elements."""
        repeats = []
        for repeat_type, pattern in self.REPEAT_PATTERNS.items():
            for match in re.finditer(pattern, sequence):
                repeats.append({
                    "type": repeat_type,
                    "start": match.start(),
                    "end": match.end(),
                    "sequence": match.group(),
                    "unit": match.group(1) if match.groups() else match.group(),
                    "copies": len(match.group()) // len(match.group(1)) if match.groups() else 1,
                })
        return repeats
    
    def _find_motifs(self, sequence: str) -> dict[str, list[int]]:
        """Find regulatory motifs."""
        matches = {}
        for motif_name, motif_seq in self.REGULATORY_MOTIFS.items():
            positions = []
            # Handle degenerate bases
            regex = self._degenerate_to_regex(motif_seq)
            for match in re.finditer(regex, sequence):
                positions.append(match.start())
            if positions:
                matches[motif_name] = positions
        return matches
    
    def _find_protein_motifs(self, sequence: str) -> dict[str, list[int]]:
        """Find protein motifs (simplified)."""
        # Common protein motifs
        protein_motifs = {
            "nls": r"[KR]{2,}",  # Nuclear localization signal
            "nls_bipartite": r"[KR]{2,}.*[KR]{2,}",
            "signal_peptide": r"^M[^P]{1,20}[KR]",  # Very simplified
            "transmembrane": r"[AILVFWY]{15,}",
            "glycosylation_n": r"N[^P][ST][^P]",
            "phosphorylation": r"[ST][^P]",
            "kinase_substrate": r"[RK]{2,3}.[ST]",
        }
        
        matches = {}
        for motif_name, pattern in protein_motifs.items():
            positions = [m.start() for m in re.finditer(pattern, sequence)]
            if positions:
                matches[motif_name] = positions
        return matches
    
    def _degenerate_to_regex(self, motif: str) -> str:
        """Convert IUPAC degenerate bases to regex."""
        iupac = {
            "R": "[AG]", "Y": "[CT]", "S": "[GC]", "W": "[AT]",
            "K": "[GT]", "M": "[AC]", "B": "[CGT]", "D": "[AGT]",
            "H": "[ACT]", "V": "[ACG]", "N": "[ACGT]",
        }
        regex = ""
        for char in motif:
            regex += iupac.get(char, char)
        return regex
    
    def _merge_intervals(self, intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge overlapping intervals."""
        if not intervals:
            return []
        
        sorted_intervals = sorted(intervals, key=lambda x: x["start"])
        merged = [sorted_intervals[0]]
        
        for current in sorted_intervals[1:]:
            last = merged[-1]
            if current["start"] <= last["end"]:
                last["end"] = max(last["end"], current["end"])
                last["length"] = last["end"] - last["start"]
            else:
                merged.append(current)
        
        return merged


def analyze_sequence(sequence: str, seq_type: str = "auto") -> SequenceFeatures:
    """Convenience function for sequence analysis."""
    analyzer = SequenceAnalyzer()
    return analyzer.analyze(sequence, seq_type)