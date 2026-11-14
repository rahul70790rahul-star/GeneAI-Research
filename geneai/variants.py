from __future__ import annotations

import gzip
import io
from collections import Counter
from typing import Any, BinaryIO

from geneai.config import MAX_UPLOAD_BYTES, MAX_VCF_DECOMPRESSED_BYTES


def _read_vcf(data: bytes, filename: str) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"VCF file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    try:
        if filename.lower().endswith(".gz"):
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                raw = compressed.read(MAX_UPLOAD_BYTES + 1)
            if len(raw) > MAX_UPLOAD_BYTES:
                raise ValueError(f"Decompressed VCF exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
        else:
            raw = data
        return raw.decode("utf-8-sig")
    except ValueError:
        raise
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise ValueError(
            "Could not read VCF. Check that the file is valid plain-text VCF or gzip-compressed VCF."
        ) from exc


def _variant_type(ref: str, alt: str) -> str:
    if alt == "*" or (alt.startswith("<") and alt.endswith(">")) or "[" in alt or "]" in alt:
        return "SYMBOLIC"
    if len(ref) == len(alt) == 1:
        return "SNP"
    if len(ref) != len(alt):
        return "INDEL"
    return "COMPLEX"


def parse_vcf(data: bytes, filename: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse a bounded VCF and label alleles by representation, without annotation."""
    text = _read_vcf(data, filename)
    variants: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"headers": [], "columns": []}
    has_column_header = False

    for line_no, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        if line.startswith("##"):
            meta["headers"].append(line)
            continue
        if line.startswith("#CHROM"):
            columns = line[1:].split("\t")
            required = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
            if columns[:8] != required:
                raise ValueError("Malformed VCF header: expected the standard first eight columns.")
            meta["columns"] = columns
            has_column_header = True
            continue
        if line.startswith("#"):
            raise ValueError(f"Unexpected VCF header at line {line_no}.")
        if not has_column_header:
            raise ValueError("VCF data rows appeared before the #CHROM header.")

        fields = line.split("\t")
        if len(fields) != len(meta["columns"]):
            raise ValueError(
                f"Malformed VCF row at line {line_no}: expected "
                f"{len(meta['columns'])} tab-separated fields."
            )
        chrom, pos, identifier, ref, alt, qual, filt, info = fields[:8]
        try:
            position = int(pos)
        except ValueError as exc:
            raise ValueError(f"Invalid coordinate at VCF line {line_no}.") from exc
        if position < 1 or not chrom or not ref or not alt:
            raise ValueError(f"Invalid coordinate or allele at VCF line {line_no}.")
        if alt == ".":
            continue

        for allele in alt.split(","):
            if not allele:
                raise ValueError(f"Empty alternate allele at VCF line {line_no}.")
            variants.append(
                {
                    "chrom": chrom,
                    "pos": position,
                    "id": identifier,
                    "ref": ref,
                    "alt": allele,
                    "qual": qual,
                    "filter": filt,
                    "info": info,
                    "variant_type": _variant_type(ref, allele),
                }
            )

    if not has_column_header:
        raise ValueError("VCF column header (#CHROM) is missing.")
    if not variants:
        raise ValueError("No variant rows found in this VCF file.")
    return variants, meta


def summarize_vcf_stream(
    source: BinaryIO,
    filename: str,
    *,
    preview_limit: int = 1000,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Scan a large VCF incrementally; retain counts and a bounded preview."""
    try:
        source.seek(0, 2)
        upload_size = source.tell()
        source.seek(0)
    except (OSError, AttributeError) as exc:
        raise ValueError("Could not read the uploaded VCF stream.") from exc

    if upload_size > MAX_UPLOAD_BYTES:
        raise ValueError(f"VCF file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    if preview_limit < 1:
        raise ValueError("Preview limit must be at least 1.")

    compressed = filename.lower().endswith(".gz")
    binary_stream = gzip.GzipFile(fileobj=source, mode="rb") if compressed else source
    text_stream = io.TextIOWrapper(binary_stream, encoding="utf-8-sig", newline="")
    meta: dict[str, Any] = {"headers": [], "columns": []}
    by_type: Counter[str] = Counter()
    by_chromosome: Counter[str] = Counter()
    preview: list[dict[str, Any]] = []
    has_column_header = False
    decompressed_bytes = 0

    try:
        for line_no, line in enumerate(text_stream, 1):
            decompressed_bytes += len(line.encode("utf-8"))
            if decompressed_bytes > MAX_VCF_DECOMPRESSED_BYTES:
                limit_mb = MAX_VCF_DECOMPRESSED_BYTES // (1024 * 1024)
                raise ValueError(f"Decompressed VCF exceeds the {limit_mb} MB processing limit.")
            line = line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("##"):
                meta["headers"].append(line)
                continue
            if line.startswith("#CHROM"):
                columns = line[1:].split("\t")
                required = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
                if columns[:8] != required:
                    raise ValueError("Malformed VCF header: expected the standard first eight columns.")
                meta["columns"] = columns
                has_column_header = True
                continue
            if line.startswith("#"):
                raise ValueError(f"Unexpected VCF header at line {line_no}.")
            if not has_column_header:
                raise ValueError("VCF data rows appeared before the #CHROM header.")

            fields = line.split("\t")
            if len(fields) != len(meta["columns"]):
                raise ValueError(
                    f"Malformed VCF row at line {line_no}: expected "
                    f"{len(meta['columns'])} tab-separated fields."
                )
            chrom, pos, identifier, ref, alt, qual, filt, info = fields[:8]
            try:
                position = int(pos)
            except ValueError as exc:
                raise ValueError(f"Invalid coordinate at VCF line {line_no}.") from exc
            if position < 1 or not chrom or not ref or not alt:
                raise ValueError(f"Invalid coordinate or allele at VCF line {line_no}.")
            if alt == ".":
                continue

            for allele in alt.split(","):
                if not allele:
                    raise ValueError(f"Empty alternate allele at VCF line {line_no}.")
                variant_type = _variant_type(ref, allele)
                by_type[variant_type] += 1
                by_chromosome[chrom] += 1
                if len(preview) < preview_limit:
                    preview.append(
                        {
                            "chrom": chrom,
                            "pos": position,
                            "id": identifier,
                            "ref": ref,
                            "alt": allele,
                            "qual": qual,
                            "filter": filt,
                            "info": info,
                            "variant_type": variant_type,
                        }
                    )
    except ValueError:
        raise
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise ValueError(
            "Could not read VCF. Check that the file is valid plain-text VCF or gzip-compressed VCF."
        ) from exc
    finally:
        if compressed:
            text_stream.close()
        else:
            text_stream.detach()

    if not has_column_header:
        raise ValueError("VCF column header (#CHROM) is missing.")
    if not by_type:
        raise ValueError("No variant rows found in this VCF file.")

    summary = {
        "variant_records": sum(by_type.values()),
        "by_type": dict(by_type),
        "by_chromosome": dict(by_chromosome),
        "decompressed_bytes": decompressed_bytes,
        "preview_limit": preview_limit,
    }
    return summary, meta, preview
