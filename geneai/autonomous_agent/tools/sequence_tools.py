"""Sequence analysis tools for Autonomous Bioinformatics Agent."""
from __future__ import annotations

from geneai.autonomous_agent.tools import Tool, ToolSpec, ToolParameter, get_tool_registry


class SequenceAnalysisTool(Tool):
    """Analyze DNA/RNA/protein sequences."""

    def __init__(self):
        spec = ToolSpec(
            name="sequence_analysis",
            description="Analyze biological sequences for composition, ORFs, motifs, and properties",
            category="sequence",
            parameters=[
                ToolParameter("sequence", "string", "Biological sequence (DNA, RNA, or protein)", required=True),
                ToolParameter("sequence_type", "string", "Type of sequence", required=False, default="auto", enum=["dna", "rna", "protein", "auto"]),
                ToolParameter("analyze_orfs", "boolean", "Find open reading frames", required=False, default=True),
                ToolParameter("find_motifs", "boolean", "Search for known motifs", required=False, default=True),
                ToolParameter("calculate_properties", "boolean", "Calculate physicochemical properties", required=False, default=True),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        sequence = kwargs.get("sequence", "").upper().strip()
        seq_type = kwargs.get("sequence_type", "auto")

        if not sequence:
            return {"error": "No sequence provided"}

        # Auto-detect sequence type
        if seq_type == "auto":
            if set(sequence).issubset({"A", "T", "G", "C"}):
                seq_type = "dna"
            elif set(sequence).issubset({"A", "U", "G", "C"}):
                seq_type = "rna"
            else:
                seq_type = "protein"

        result = {
            "sequence_type": seq_type,
            "length": len(sequence),
            "composition": self._get_composition(sequence, seq_type),
        }

        if kwargs.get("analyze_orfs") and seq_type in ("dna", "rna"):
            result["orfs"] = self._find_orfs(sequence)

        if kwargs.get("calculate_properties"):
            result["properties"] = self._calculate_properties(sequence, seq_type)

        if kwargs.get("find_motifs"):
            result["motifs"] = self._find_motifs(sequence, seq_type)

        return result

    def _get_composition(self, sequence: str, seq_type: str) -> dict[str, Any]:
        """Calculate nucleotide/amino acid composition."""
        from collections import Counter
        counts = Counter(sequence)
        total = len(sequence)
        return {
            "counts": dict(counts),
            "percentages": {k: v / total * 100 for k, v in counts.items()},
        }

    def _find_orfs(self, sequence: str) -> list[dict[str, Any]]:
        """Find open reading frames."""
        orfs = []
        start_codons = {"ATG"}
        stop_codons = {"TAA", "TAG", "TGA"}

        for frame in range(3):
            for i in range(frame, len(sequence) - 2, 3):
                codon = sequence[i:i+3]
                if codon in start_codons:
                    for j in range(i, len(sequence) - 2, 3):
                        stop = sequence[j:j+3]
                        if stop in stop_codons:
                            orfs.append({
                                "frame": frame + 1,
                                "start": i,
                                "end": j + 3,
                                "length": j + 3 - i,
                                "sequence": sequence[i:j+3],
                            })
                            break
        return orfs[:20]  # Limit results

    def _calculate_properties(self, sequence: str, seq_type: str) -> dict[str, Any]:
        """Calculate sequence properties."""
        props = {}
        if seq_type == "protein":
            # Basic protein properties
            molecular_weight = sum(self._aa_weight(aa) for aa in sequence)
            props["molecular_weight_da"] = molecular_weight
            props["isoelectric_point"] = self._estimate_pi(sequence)
            props["hydrophobicity"] = self._calculate_hydrophobicity(sequence)
        elif seq_type in ("dna", "rna"):
            gc_content = (sequence.count("G") + sequence.count("C")) / len(sequence) * 100
            props["gc_content_percent"] = gc_content
            props["melting_temp"] = 64.9 + 41 * (sequence.count("G") + sequence.count("C") - 16.4) / len(sequence)
        return props

    def _find_motifs(self, sequence: str, seq_type: str) -> list[dict[str, Any]]:
        """Find known motifs (simplified)."""
        motifs = []
        if seq_type == "dna":
            # Common DNA motifs
            for motif, name in [("TATAAA", "TATA_box"), ("CAAT", "CAAT_box"), ("GGGCGG", "GC_box")]:
                pos = sequence.find(motif)
                while pos != -1:
                    motifs.append({"motif": motif, "name": name, "position": pos})
                    pos = sequence.find(motif, pos + 1)
        return motifs[:10]

    def _aa_weight(self, aa: str) -> float:
        weights = {
            "A": 89.1, "R": 174.2, "N": 132.1, "D": 133.1, "C": 121.2,
            "E": 147.1, "Q": 146.2, "G": 75.1, "H": 155.2, "I": 131.2,
            "L": 131.2, "K": 146.2, "M": 149.2, "F": 165.2, "P": 115.1,
            "S": 105.1, "T": 119.1, "W": 204.2, "Y": 181.2, "V": 117.1,
        }
        return weights.get(aa, 110.0)

    def _estimate_pi(self, sequence: str) -> float:
        # Simplified pI estimation
        basic = sequence.count("K") + sequence.count("R") + sequence.count("H")
        acidic = sequence.count("D") + sequence.count("E")
        return 7.0 + (basic - acidic) * 0.5

    def _calculate_hydrophobicity(self, sequence: str) -> float:
        kd_scale = {
            "I": 4.5, "V": 4.2, "L": 3.8, "F": 2.8, "C": 2.5, "M": 1.9,
            "A": 1.8, "G": -0.4, "T": -0.7, "S": -0.8, "W": -0.9, "Y": -1.3,
            "P": -1.6, "H": -3.2, "E": -3.5, "Q": -3.5, "D": -3.5, "N": -3.5,
            "K": -3.9, "R": -4.5,
        }
        return sum(kd_scale.get(aa, 0) for aa in sequence) / len(sequence) if sequence else 0


class SequenceAlignmentTool(Tool):
    """Perform sequence alignment."""

    def __init__(self):
        spec = ToolSpec(
            name="sequence_alignment",
            description="Align sequences using local or global alignment algorithms",
            category="sequence",
            requires_approval=False,
            parameters=[
                ToolParameter("query_sequence", "string", "Query sequence", required=True),
                ToolParameter("target_sequence", "string", "Target sequence", required=True),
                ToolParameter("algorithm", "string", "Alignment algorithm", required=False, default="local", enum=["local", "global", "semiglobal"]),
                ToolParameter("match_score", "number", "Match score", required=False, default=2),
                ToolParameter("mismatch_score", "number", "Mismatch score", required=False, default=-1),
                ToolParameter("gap_penalty", "number", "Gap penalty", required=False, default=-2),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        # Simplified Smith-Waterman local alignment
        query = kwargs.get("query_sequence", "").upper()
        target = kwargs.get("target_sequence", "").upper()
        match = kwargs.get("match_score", 2)
        mismatch = kwargs.get("mismatch_score", -1)
        gap = kwargs.get("gap_penalty", -2)

        if not query or not target:
            return {"error": "Both sequences required"}

        # Score matrix
        n, m = len(query), len(target)
        score_matrix = [[0] * (m + 1) for _ in range(n + 1)]
        trace_matrix = [[0] * (m + 1) for _ in range(n + 1)]

        max_score = 0
        max_pos = (0, 0)

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                match_score = match if query[i-1] == target[j-1] else mismatch
                scores = [
                    score_matrix[i-1][j-1] + match_score,
                    score_matrix[i-1][j] + gap,
                    score_matrix[i][j-1] + gap,
                    0,
                ]
                max_val = max(scores)
                score_matrix[i][j] = max_val
                trace_matrix[i][j] = scores.index(max_val)

                if max_val > max_score:
                    max_score = max_val
                    max_pos = (i, j)

        # Traceback
        align_q, align_t = [], []
        i, j = max_pos
        while i > 0 and j > 0 and score_matrix[i][j] > 0:
            trace = trace_matrix[i][j]
            if trace == 0:  # diagonal
                align_q.append(query[i-1])
                align_t.append(target[j-1])
                i -= 1
                j -= 1
            elif trace == 1:  # up
                align_q.append(query[i-1])
                align_t.append("-")
                i -= 1
            elif trace == 2:  # left
                align_q.append("-")
                align_t.append(target[j-1])
                j -= 1
            else:
                break

        return {
            "alignment_score": max_score,
            "query_aligned": "".join(reversed(align_q)),
            "target_aligned": "".join(reversed(align_t)),
            "identity_percent": sum(a == b for a, b in zip(reversed(align_q), reversed(align_t))) / max(len(align_q), 1) * 100,
        }


def register_sequence_tools(registry):
    """Register sequence analysis tools."""
    registry.register(SequenceAnalysisTool())
    registry.register(SequenceAlignmentTool())