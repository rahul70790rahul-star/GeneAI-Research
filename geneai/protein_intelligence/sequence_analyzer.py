"""Protein sequence analysis module."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from Bio.Seq import Seq
from Bio.SeqUtils.ProtParam import ProteinAnalysis
from Bio.SeqUtils import molecular_weight

logger = logging.getLogger(__name__)


@dataclass
class ProteinFeatures:
    """Extracted protein sequence features."""
    length: int
    molecular_weight: float
    isoelectric_point: float | None
    hydrophobicity: float | None  # GRAVY
    instability_index: float | None
    aromaticity: float | None
    aliphatic_index: float | None
    charge_at_pH7: float | None
    composition: dict[str, float]
    secondary_structure_fraction: dict[str, float] | None = None
    domains: list[dict[str, Any]] = field(default_factory=list)
    motifs: list[dict[str, Any]] = field(default_factory=list)
    signal_peptide: dict[str, Any] | None = None
    transmembrane_regions: list[dict[str, Any]] = field(default_factory=list)
    glycosylation_sites: list[dict[str, Any]] = field(default_factory=list)
    phosphorylation_sites: list[dict[str, Any]] = field(default_factory=list)
    active_sites: list[dict[str, Any]] = field(default_factory=list)
    binding_sites: list[dict[str, Any]] = field(default_factory=list)
    ptm_sites: list[dict[str, Any]] = field(default_factory=list)


class ProteinSequenceAnalyzer:
    """
    Analyze protein sequences for structural and functional features.
    
    Capabilities:
    - Physicochemical properties (MW, pI, GRAVY, instability, etc.)
    - Domain identification (Pfam, InterPro patterns)
    - Motif discovery (PROSITE patterns)
    - Signal peptide prediction
    - Transmembrane region prediction
    - PTM site prediction
    - Secondary structure propensity
    """
    
    # PROSITE-like patterns for common motifs
    PROSITE_PATTERNS = {
        "n_glycosylation": r"N[^P][ST][^P]",
        "o_glycosylation": r"[ST]P",
        "phosphorylation_ser_thr": r"[RK].{0,2}[ST][^P]",
        "phosphorylation_tyr": r"[DE].{0,2}Y",
        "kinase_ck2": r"[ST][DE][DE]",
        "kinase_pka": r"[RK][RK].[ST]",
        "kinase_pkc": r"[RK].[ST][RK]",
        "kinase_mapk": r"P.[ST]P",
        "sh2_binding": r"Y.{2,4}[LIVMFYW]",
        "sh3_binding": r"P..P",
        "pdz_binding": r"[ST][VIL].$",
        "ww_binding": r"PP.Y",
        "nls_monopartite": r"[KR]{4,}",
        "nls_bipartite": r"[KR]{2,}.{10,12}[KR]{3,}",
        "nuclear_export": r"[LIVFM]{2,3}.{2,3}[LIVFM]{2,3}.{2,3}[LIVFM]",
        "caax_box": r"C[AVILMFYW]{2}[AIMFS]",
        "prenylation": r"C[AVILMFYW]{2}[AIMFS]$",
        "myristoylation": r"^MG.{6,12}[STAGCN]",
        "palmitoylation": r"C.{2,10}C",
        "sumoylation": r"[VILFP][KR].E",
        "ubiquitination": r"K.{0,20}[ST]",
    }
    
    # Transmembrane prediction (simplified Kyte-Doolittle)
    TM_WINDOW = 19
    TM_THRESHOLD = 1.6
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, sequence: str) -> ProteinFeatures:
        """
        Perform comprehensive protein sequence analysis.
        
        Args:
            sequence: Protein sequence (single letter codes)
            
        Returns:
            ProteinFeatures with all extracted features
        """
        sequence = sequence.upper().strip()
        
        # Remove any FASTA header
        if sequence.startswith(">"):
            lines = sequence.split("\n")
            sequence = "".join(lines[1:]).replace(" ", "").replace("\n", "")
        
        # Validate sequence
        valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
        if not set(sequence).issubset(valid_aa):
            invalid = set(sequence) - valid_aa
            self.logger.warning("Sequence contains non-standard amino acids: %s", invalid)
        
        # Basic properties using BioPython
        try:
            prot_analysis = ProteinAnalysis(sequence)
            mol_weight = prot_analysis.molecular_weight()
            isoelectric_point = prot_analysis.isoelectric_point()
            hydrophobicity = prot_analysis.gravy()
            instability_index = prot_analysis.instability_index()
            aromaticity = prot_analysis.aromaticity()
            aliphatic_index = self._calculate_aliphatic_index(sequence)
            charge_at_pH7 = self._calculate_charge_at_ph(sequence, 7.0)
            composition = prot_analysis.get_amino_acids_percent()
            secondary_structure = prot_analysis.secondary_structure_fraction()
        except Exception as e:
            self.logger.warning("ProteinAnalysis failed: %s", e)
            mol_weight = molecular_weight(Seq(sequence), seq_type="protein")
            isoelectric_point = None
            hydrophobicity = None
            instability_index = None
            aromaticity = None
            aliphatic_index = None
            charge_at_pH7 = None
            composition = self._get_composition(sequence)
            secondary_structure = None
        
        # Domain and motif identification
        domains = self._identify_domains(sequence)
        motifs = self._find_motifs(sequence)
        signal_peptide = self._predict_signal_peptide(sequence)
        tm_regions = self._predict_transmembrane(sequence)
        glycosylation = self._predict_glycosylation(sequence)
        phosphorylation = self._predict_phosphorylation(sequence)
        active_sites = self._predict_active_sites(sequence)
        binding_sites = self._predict_binding_sites(sequence)
        ptm_sites = self._predict_ptm_sites(sequence)
        
        return ProteinFeatures(
            length=len(sequence),
            molecular_weight=mol_weight,
            isoelectric_point=isoelectric_point,
            hydrophobicity=hydrophobicity,
            instability_index=instability_index,
            aromaticity=aromaticity,
            aliphatic_index=aliphatic_index,
            charge_at_pH7=charge_at_pH7,
            composition=composition,
            secondary_structure_fraction=secondary_structure,
            domains=domains,
            motifs=motifs,
            signal_peptide=signal_peptide,
            transmembrane_regions=tm_regions,
            glycosylation_sites=glycosylation,
            phosphorylation_sites=phosphorylation,
            active_sites=active_sites,
            binding_sites=binding_sites,
            ptm_sites=ptm_sites,
        )
    
    def _get_composition(self, sequence: str) -> dict[str, float]:
        """Calculate amino acid composition percentages."""
        total = len(sequence)
        if total == 0:
            return {}
        aa_list = "ACDEFGHIKLMNPQRSTVWY"
        return {aa: sequence.count(aa) / total * 100 for aa in aa_list if aa in sequence}
    
    def _calculate_aliphatic_index(self, sequence: str) -> float:
        """Calculate aliphatic index."""
        total = len(sequence)
        if total == 0:
            return 0.0
        # Aliphatic index = X(Ala) + 2.9*X(Val) + 3.9*(X(Ile) + X(Leu))
        ala = sequence.count("A") / total * 100
        val = sequence.count("V") / total * 100
        ile = sequence.count("I") / total * 100
        leu = sequence.count("L") / total * 100
        return ala + 2.9 * val + 3.9 * (ile + leu)
    
    def _calculate_charge_at_ph(self, sequence: str, ph: float) -> float:
        """Calculate net charge at given pH."""
        # pKa values
        pka = {
            "D": 3.9, "E": 4.3, "H": 6.0, "C": 8.3,
            "Y": 10.1, "K": 10.5, "R": 12.5,
            "N-terminus": 8.0, "C-terminus": 3.1,
        }
        
        charge = 0.0
        
        # N-terminus
        charge += 1 / (1 + 10**(pka["N-terminus"] - ph))
        
        # C-terminus
        charge += -1 / (1 + 10**(ph - pka["C-terminus"]))
        
        # Side chains
        for aa in sequence:
            if aa == "D" or aa == "E":
                charge += -1 / (1 + 10**(pka[aa] - ph))
            elif aa == "H":
                charge += 1 / (1 + 10**(pka[aa] - ph))
            elif aa == "C":
                charge += -1 / (1 + 10**(ph - pka[aa]))
            elif aa == "Y":
                charge += -1 / (1 + 10**(ph - pka[aa]))
            elif aa == "K" or aa == "R":
                charge += 1 / (1 + 10**(pka[aa] - ph))
        
        return charge
    
    def _identify_domains(self, sequence: str) -> list[dict[str, Any]]:
        """
        Identify protein domains using pattern matching.
        In production, would use Pfam HMMs via HMMER or InterProScan.
        """
        domains = []
        
        # Known domain patterns (simplified)
        domain_patterns = {
            "kinase": r"[LV]HRD[LIV]K[ST]N",
            "sh2": r"[FL]VRES[PN]P",
            "sh3": r"RT[LIV]D[DE].{2}Y",
            "ph": r"K[LIV]G[KR].{2}[FY]",
            "ptb": r"NPXY",
            "pdZ": r"[ST][VIL].$",
            "ww": r"PP.Y",
            "fyve": r"R[RK]H[CR]C[CST]",
            "pbx": r"K[TS]W[PK]",
            "homeobox": r"RR[KR]P[TS]",
            "zinc_finger_c2h2": r"C.{2,4}C.{12}H.{3,5}H",
            "zinc_finger_c4": r"C.{2}C.{13}C.{2}C",
            "leucine_zipper": r"([LIV].){6}[LIV]",
            "helix_loop_helix": r"[RK]{2,}.{5,}[LIV].{2}[LIV]",
            "wd40": r"[GH][ST]..[WD]",
            "tetratricopeptide": r"[AS][VIL][DE][AS][LIV][KR][FY]",
            "ankyrin": r"[LIV]P[LIV]A",
            "armadillo": r"[LIV][ST]..[KR]..[LIV]",
            "death_domain": r"[RK]..[LIV]..[DE]..[LIV]",
        }
        
        for domain_name, pattern in domain_patterns.items():
            for match in re.finditer(pattern, sequence):
                domains.append({
                    "domain": domain_name,
                    "start": match.start(),
                    "end": match.end(),
                    "sequence": match.group(),
                    "confidence": "predicted",
                    "source": "pattern",
                })
        
        return domains
    
    def _find_motifs(self, sequence: str) -> list[dict[str, Any]]:
        """Find known protein motifs."""
        motifs = []
        
        for motif_name, pattern in self.PROSITE_PATTERNS.items():
            for match in re.finditer(pattern, sequence):
                motifs.append({
                    "motif": motif_name,
                    "pattern": pattern,
                    "start": match.start(),
                    "end": match.end(),
                    "sequence": match.group(),
                })
        
        return motifs
    
    def _predict_signal_peptide(self, sequence: str) -> dict[str, Any] | None:
        """
        Predict signal peptide (simplified).
        In production, would use SignalP.
        """
        if len(sequence) < 30:
            return None
        
        # Check N-terminal region for signal peptide features
        n_term = sequence[:30]
        
        # Positive charge in N-region (first 5-10 aa)
        n_region = n_term[:10]
        pos_charge = n_region.count("K") + n_region.count("R")
        
        # Hydrophobic H-region
        h_region = n_term[10:25]
        hydrophobic = sum(1 for aa in h_region if aa in "AILMVFWY")
        hydrophobic_fraction = hydrophobic / len(h_region) if h_region else 0
        
        # Cleavage site (small residues at positions -3, -1)
        c_region = n_term[25:30]
        cleavage_score = sum(1 for aa in c_region if aa in "AGSC")
        
        has_signal = (
            pos_charge >= 1 and
            hydrophobic_fraction > 0.5 and
            cleavage_score >= 2
        )
        
        if has_signal:
            return {
                "predicted": True,
                "cleavage_site": 25,
                "n_region_charge": pos_charge,
                "h_region_hydrophobicity": hydrophobic_fraction,
                "probability": 0.7,
            }
        
        return {"predicted": False}
    
    def _predict_transmembrane(self, sequence: str) -> list[dict[str, Any]]:
        """
        Predict transmembrane helices using Kyte-Doolittle hydropathy.
        In production, would use TMHMM, Phobius, or DeepTMHMM.
        """
        # Kyte-Doolittle hydrophobicity scale
        kd_scale = {
            "I": 4.5, "V": 4.2, "L": 3.8, "F": 2.8, "C": 2.5, "M": 1.9,
            "A": 1.8, "G": -0.4, "T": -0.7, "S": -0.8, "W": -0.9, "Y": -1.3,
            "P": -1.6, "H": -3.2, "E": -3.5, "Q": -3.5, "D": -3.5, "N": -3.5,
            "K": -3.9, "R": -4.5,
        }
        
        regions = []
        scores = [kd_scale.get(aa, 0) for aa in sequence]
        
        # Sliding window
        for i in range(len(scores) - self.TM_WINDOW + 1):
            window_score = sum(scores[i:i+self.TM_WINDOW]) / self.TM_WINDOW
            if window_score >= self.TM_THRESHOLD:
                # Check if this overlaps with existing region
                overlaps = False
                for r in regions:
                    if not (i + self.TM_WINDOW < r["start"] or i > r["end"]):
                        overlaps = True
                        break
                if not overlaps:
                    regions.append({
                        "start": i,
                        "end": i + self.TM_WINDOW,
                        "length": self.TM_WINDOW,
                        "avg_hydropathy": window_score,
                        "sequence": sequence[i:i+self.TM_WINDOW],
                    })
        
        return regions
    
    def _predict_glycosylation(self, sequence: str) -> list[dict[str, Any]]:
        """Predict N- and O-linked glycosylation sites."""
        sites = []
        
        # N-linked: N[^P][ST][^P]
        for match in re.finditer(r"N[^P][ST][^P]", sequence):
            sites.append({
                "type": "N-linked",
                "position": match.start(),
                "sequence": match.group(),
                "asn_position": match.start(),
            })
        
        # O-linked: [ST]P (simplified)
        for match in re.finditer(r"[ST]P", sequence):
            sites.append({
                "type": "O-linked",
                "position": match.start(),
                "sequence": match.group(),
            })
        
        return sites
    
    def _predict_phosphorylation(self, sequence: str) -> list[dict[str, Any]]:
        """Predict phosphorylation sites."""
        sites = []
        
        patterns = {
            "CK2": r"[ST][DE][DE]",
            "PKA": r"[RK][RK].[ST]",
            "PKC": r"[RK].[ST][RK]",
            "MAPK": r"P.[ST]P",
            "CDK": r"[ST]P.[KR]",
            "GSK3": r"[ST].{3}[ST]",
            "Casein_kinase1": r"[ST][ST].[DE]",
            "Tyrosine_kinase": r"[DE].{0,2}Y",
        }
        
        for kinase, pattern in patterns.items():
            for match in re.finditer(pattern, sequence):
                sites.append({
                    "kinase": kinase,
                    "position": match.start(),
                    "sequence": match.group(),
                    "residue": sequence[match.start()],
                })
        
        return sites
    
    def _predict_active_sites(self, sequence: str) -> list[dict[str, Any]]:
        """Predict catalytic/active sites (simplified)."""
        sites = []
        
        # Common catalytic motifs
        catalytic_patterns = {
            "serine_protease": r"[ST]AH",
            "cysteine_protease": r"C.{2}[ST]H",
            "aspartyl_protease": r"DT[ST]G",
            "metalloprotease": r"HEXXH",
            "kinase_hrd": r"HRD",
            "kinase_dfG": r"DFG",
            "phosphatase": r"HC[AG]R",
            "esterase": r"GXSXG",
            "lipase": r"G[ST]S[AG]G",
        }
        
        for site_type, pattern in catalytic_patterns.items():
            for match in re.finditer(pattern, sequence):
                sites.append({
                    "type": site_type,
                    "position": match.start(),
                    "sequence": match.group(),
                })
        
        return sites
    
    def _predict_binding_sites(self, sequence: str) -> list[dict[str, Any]]:
        """Predict protein-protein/DNA/ligand binding sites."""
        sites = []
        
        # DNA binding
        dna_patterns = {
            "zinc_finger": r"C.{2,4}C.{12}H.{3,5}H",
            "helix_turn_helix": r"[RK]{3,}.{5}[LIV].{2}[LIV]",
            "leucine_zipper": r"([LIV].){6}[LIV]",
            "basic_region": r"[RK]{4,}",
        }
        
        # Protein binding
        protein_patterns = {
            "sh2": r"Y.{2,4}[LIVMFYW]",
            "sh3": r"P..P",
            "pdZ": r"[ST][VIL].$",
            "ww": r"PP.Y",
            "ubiquitin_binding": r"[LIV].[LIV].[LIV]",
        }
        
        all_patterns = {**dna_patterns, **protein_patterns}
        
        for site_type, pattern in all_patterns.items():
            for match in re.finditer(pattern, sequence):
                sites.append({
                    "type": site_type,
                    "category": "DNA" if site_type in dna_patterns else "protein",
                    "position": match.start(),
                    "sequence": match.group(),
                })
        
        return sites
    
    def _predict_ptm_sites(self, sequence: str) -> list[dict[str, Any]]:
        """Predict post-translational modification sites."""
        sites = []
        
        # Combine all PTM predictions
        for glycosylation in self._predict_glycosylation(sequence):
            sites.append({
                "modification": "glycosylation",
                **glycosylation,
            })
        
        for phospho in self._predict_phosphorylation(sequence):
            sites.append({
                "modification": "phosphorylation",
                **phospho,
            })
        
        # Additional PTMs
        # Acetylation: K (N-terminal or after cleavage)
        for match in re.finditer(r"^[MA]?K", sequence):
            sites.append({
                "modification": "acetylation",
                "position": match.start(),
                "sequence": "K",
            })
        
        # Methylation: K, R
        for match in re.finditer(r"[KR]", sequence):
            sites.append({
                "modification": "methylation",
                "position": match.start(),
                "residue": match.group(),
            })
        
        # Ubiquitination: K
        for match in re.finditer(r"K", sequence):
            sites.append({
                "modification": "ubiquitination",
                "position": match.start(),
                "residue": "K",
            })
        
        # Sumoylation: [VILFP]K.E
        for match in re.finditer(r"[VILFP]K.E", sequence):
            sites.append({
                "modification": "sumoylation",
                "position": match.start() + 1,
                "sequence": match.group(),
            })
        
        return sites


def analyze_protein_sequence(sequence: str) -> ProteinFeatures:
    """Convenience function for protein sequence analysis."""
    analyzer = ProteinSequenceAnalyzer()
    return analyzer.analyze(sequence)