
from __future__ import annotations

import re
from collections import Counter
from pathlib import PureWindowsPath
from typing import Any

from geneai.config import MAX_UPLOAD_BYTES

DNA = set("ACGTN")
RNA = set("ACGUN")
PROTEIN = set("ABCDEFGHIKLMNPQRSTVWXYZJUO*")
CODON_TABLE = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","TCT":"S","TCC":"S","TCA":"S","TCG":"S",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","TGT":"C","TGC":"C","TGA":"*","TGG":"W",
    "CTT":"L","CTC":"L","CTA":"L","CTG":"L","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "CAT":"H","CAC":"H","CAA":"Q","CAG":"Q","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","ACT":"T","ACC":"T","ACA":"T","ACG":"T",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","AGT":"S","AGC":"S","AGA":"R","AGG":"R",
    "GTT":"V","GTC":"V","GTA":"V","GTG":"V","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "GAT":"D","GAC":"D","GAA":"E","GAG":"E","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def parse_sequence_file(data: bytes, filename: str = "sequence.txt") -> list[dict[str, str]]:
    """Read a FASTA file, strict four-line FASTQ records, or a raw sequence."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Sequence file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Sequence file must be UTF-8 text.") from exc
    if not text.strip():
        raise ValueError("The uploaded file is empty.")

    fastq_lines = text.splitlines()
    if fastq_lines and fastq_lines[0].startswith("@"):
        if len(fastq_lines) % 4:
            raise ValueError("Malformed FASTQ file: records must contain four lines.")
        records = []
        for i in range(0, len(fastq_lines), 4):
            head, sequence, plus, quality = fastq_lines[i : i + 4]
            head, sequence, plus = head.strip(), sequence.strip(), plus.strip()
            quality = quality.strip()
            if not head.startswith("@") or not plus.startswith("+") or not sequence:
                raise ValueError(f"Malformed FASTQ record near line {i + 1}.")
            if len(sequence) != len(quality):
                raise ValueError(f"FASTQ sequence and quality lengths differ near line {i + 1}.")
            records.append({"id": head[1:].split()[0], "sequence": _clean(sequence)})
        return records

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines[0].startswith(">"):
        records, header, chunks = [], None, []
        for line in lines:
            if line.startswith(">"):
                if header is not None:
                    sequence = _clean("".join(chunks))
                    if not sequence:
                        raise ValueError(f"FASTA record '{header.split()[0]}' has no sequence.")
                    records.append({"id": header.split()[0], "sequence": sequence})
                header, chunks = line[1:].strip(), []
                if not header:
                    raise ValueError("FASTA header is empty.")
            else:
                if header is None:
                    raise ValueError("Sequence data appears before a FASTA header.")
                chunks.append(line)
        sequence = _clean("".join(chunks))
        if not sequence:
            raise ValueError(f"FASTA record '{header.split()[0]}' has no sequence.")
        records.append({"id": header.split()[0], "sequence": sequence})
        return records

    sequence = _clean(text)
    if not sequence:
        raise ValueError(f"Could not read sequence content from {filename}.")
    safe_name = PureWindowsPath(filename).name.rsplit(".", 1)[0] or "sequence"
    return [{"id": safe_name, "sequence": sequence}]


def _orfs(sequence: str, min_aa: int = 20) -> list[dict[str, int | str]]:
    seq = sequence.replace("U", "T")
    found = []
    for frame in range(3):
        start = frame
        while start + 2 < len(seq):
            if seq[start:start+3] == "ATG":
                for stop in range(start + 3, len(seq) - 2, 3):
                    if seq[stop:stop+3] in {"TAA", "TAG", "TGA"}:
                        aa_len = (stop - start) // 3
                        if aa_len >= min_aa:
                            found.append({"frame": frame + 1, "start_1based": start + 1, "end_1based": stop + 3, "amino_acids": aa_len})
                        start = stop
                        break
            start += 3
    return found


def analyze_sequence(sequence: str, kind: str) -> dict[str, Any]:
    """Return composition and simple research-level sequence statistics."""
    if kind not in {"DNA", "RNA", "Protein"}:
        raise ValueError("Sequence type must be DNA, RNA, or Protein.")
    seq = _clean(sequence)
    if not seq:
        raise ValueError("Enter or upload a sequence first.")
    allowed = DNA if kind == "DNA" else RNA if kind == "RNA" else PROTEIN
    invalid = sorted(set(seq) - allowed)
    if invalid:
        raise ValueError(f"Invalid {kind} symbol(s): {', '.join(invalid)}")
    counts = Counter(seq)
    result: dict[str, Any] = {
        "sequence_type": kind,
        "length": len(seq),
        "ambiguous_count": counts.get("N", 0) if kind != "Protein" else counts.get("X", 0),
        "composition": dict(sorted(counts.items())),
    }
    if kind in {"DNA", "RNA"}:
        gc = (counts.get("G", 0) + counts.get("C", 0)) / len(seq) * 100
        result["gc_content"] = f"{gc:.2f}%"
        result["orfs"] = _orfs(seq)
        if kind == "DNA":
            coding = seq[: len(seq) - len(seq) % 3]
            result["translation_frame_1"] = "".join(
                CODON_TABLE.get(coding[i : i + 3], "X") for i in range(0, len(coding), 3)
            )
            result["codons_frame_1"] = dict(
                Counter(coding[i : i + 3] for i in range(0, len(coding), 3))
            )
    else:
        result["gc_content"] = "Not applicable to protein sequence"
        result["molecular_weight_estimate"] = (
            "Not calculated; install a validated sequence chemistry library for this analysis"
        )
    return result
