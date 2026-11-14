"""Evidence-preserving VCF scan utilities for mutation research.

This module reports values present in the input VCF. It does not infer a
clinical classification, validate REF alleles against a reference FASTA, or
claim that indels are normalized.
"""
from __future__ import annotations

import gzip
import io
import math
import re
import sqlite3
from collections import Counter
from typing import Any, BinaryIO

from geneai.config import (
    MAX_UPLOAD_BYTES,
    MAX_VCF_DECOMPRESSED_BYTES,
    MAX_VCF_HEADER_BYTES,
    MAX_VCF_LINE_BYTES,
    MAX_VCF_SAMPLES,
)

_VCF_COLUMNS = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
_CONSEQUENCE_KEYS = ("MC", "CSQ", "ANN")
_HGVS_KEYS = ("CLNHGVS", "HGVSc", "HGVSp", "HGVS")


def _normalise_build(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:GRCh|hg)(37|38|19)(?:\b|$)", value, flags=re.IGNORECASE)
    if not match:
        return None
    generation = "37" if match.group(1) == "19" else match.group(1)
    return f"GRCh{generation}"


def _declared_build(headers: list[str]) -> str | None:
    for header in headers:
        match = re.match(r"##(?:reference|assembly)=(.+)", header, flags=re.IGNORECASE)
        if match:
            build = _normalise_build(match.group(1).strip().strip('"'))
            if build:
                return build
    return None


def _parse_info(raw: str) -> dict[str, str | bool]:
    result: dict[str, str | bool] = {}
    if raw in {"", "."}:
        return result
    for item in raw.split(";"):
        if not item:
            continue
        key, separator, value = item.partition("=")
        if key:
            result[key] = value if separator else True
    return result


def _number(value: str | None, *, integer: bool = False) -> int | float | None:
    if value in {None, "", "."}:
        return None
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(float(parsed)) else None


def _parse_gt(value: str | None) -> tuple[list[int | None], str]:
    if not value or value == ".":
        return [None], "MISSING"
    alleles: list[int | None] = []
    for token in re.split(r"[/|]", value):
        if token == ".":
            alleles.append(None)
        elif token.isdigit():
            alleles.append(int(token))
        else:
            return [None], "INVALID"
    if not alleles or all(allele is None for allele in alleles):
        return alleles or [None], "MISSING"
    if any(allele is None for allele in alleles):
        return alleles, "PARTIAL"
    return alleles, "CALLED"


def _allele_call(alleles: list[int | None], alt_index: int) -> tuple[str, int, int]:
    called = [allele for allele in alleles if allele is not None]
    alt_copies = sum(allele == alt_index for allele in called)
    if not called:
        return "MISSING", 0, 0
    if len(called) != len(alleles):
        return "PARTIAL", alt_copies, len(called)
    if alt_copies == len(called):
        return "HOM_ALT", alt_copies, len(called)
    if alt_copies:
        return "HET", alt_copies, len(called)
    if any(allele != 0 for allele in called):
        return "OTHER_ALT", 0, len(called)
    return "HOM_REF", 0, len(called)


def _sv_type(alt: str, info: dict[str, str | bool]) -> str | None:
    value = info.get("SVTYPE")
    if isinstance(value, str) and value:
        return value.split(",", 1)[0].upper()
    symbolic = re.fullmatch(r"<([A-Za-z0-9:_-]+)>", alt)
    if symbolic:
        return symbolic.group(1).upper()
    if "[" in alt or "]" in alt:
        return "BND"
    return None


def _build_status(detected: str | None, expected: str | None) -> str:
    if not expected:
        return "not_checked"
    if not detected:
        return "not_declared"
    return "match" if detected.casefold() == expected.casefold() else "mismatch"


def summarize_vcf_interpretation_stream(
    source: BinaryIO,
    filename: str,
    *,
    preview_limit: int = 1000,
    sample_preview_limit: int = 25,
    expected_build: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Scan a plain or gzip VCF and summarize per-allele and per-sample evidence.

    Summary counts cover the full file. ``preview`` is bounded and is the only
    variant-level data retained. Genotype-derived frequencies describe the VCF
    cohort; INFO/AF is kept separately as a source-provided population value.
    """
    try:
        source.seek(0, 2)
        upload_size = source.tell()
        source.seek(0)
    except (OSError, AttributeError) as exc:
        raise ValueError("Could not read the uploaded VCF stream.") from exc
    if upload_size > MAX_UPLOAD_BYTES:
        raise ValueError(f"VCF file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    if not 1 <= preview_limit <= 10_000:
        raise ValueError("Preview limit must be between 1 and 10,000.")
    if not 0 <= sample_preview_limit <= 100:
        raise ValueError("Sample preview limit must be between 0 and 100.")

    compressed = filename.lower().endswith(".gz")
    binary = gzip.GzipFile(fileobj=source, mode="rb") if compressed else source
    text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
    meta: dict[str, Any] = {"headers": [], "columns": [], "sample_names": []}
    by_type: Counter[str] = Counter()
    by_chromosome: Counter[str] = Counter()
    by_filter: Counter[str] = Counter()
    genotype_counts: Counter[str] = Counter()
    sample_metrics: dict[str, dict[str, Any]] = {}
    preview: list[dict[str, Any]] = []
    duplicate_alleles = 0
    allele_rows_seen = 0
    source_records = 0
    variants_with_qual = 0
    qual_sum = 0.0
    qual_min: float | None = None
    qual_max: float | None = None
    variants_with_gene_field = 0
    variants_with_consequence_field = 0
    variants_with_hgvs_field = 0
    variants_with_clnsig_field = 0
    variants_with_rsid = 0
    has_column_header = False
    decompressed_bytes = 0
    header_bytes = 0
    duplicate_db = sqlite3.connect(":memory:")
    try:
        duplicate_db.execute("PRAGMA temp_store=FILE")
        duplicate_db.execute("PRAGMA cache_size=-8192")
        duplicate_db.execute("PRAGMA temp.cache_size=-8192")
        duplicate_db.execute(
            "CREATE TEMP TABLE seen_alleles (chrom TEXT, pos INTEGER, ref TEXT, alt TEXT, "
            "PRIMARY KEY (chrom, pos, ref, alt)) WITHOUT ROWID"
        )
    except sqlite3.Error as exc:
        duplicate_db.close()
        raise ValueError("Could not create temporary disk storage for exact duplicate detection.") from exc

    try:
        line_no = 0
        while True:
            raw_line = text.readline(MAX_VCF_LINE_BYTES + 1)
            if not raw_line:
                break
            line_no += 1
            encoded_length = len(raw_line.encode("utf-8"))
            if encoded_length > MAX_VCF_LINE_BYTES:
                raise ValueError(
                    f"VCF line {line_no} exceeds the {MAX_VCF_LINE_BYTES // (1024 * 1024)} MB line limit."
                )
            decompressed_bytes += encoded_length
            if decompressed_bytes > MAX_VCF_DECOMPRESSED_BYTES:
                limit_mb = MAX_VCF_DECOMPRESSED_BYTES // (1024 * 1024)
                raise ValueError(f"Decompressed VCF exceeds the {limit_mb} MB processing limit.")
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("##"):
                header_bytes += len(raw_line.encode("utf-8"))
                if header_bytes > MAX_VCF_HEADER_BYTES:
                    raise ValueError(
                        f"VCF header exceeds the {MAX_VCF_HEADER_BYTES // (1024 * 1024)} MB metadata limit."
                    )
                meta["headers"].append(line)
                continue
            if line.startswith("#CHROM"):
                columns = line[1:].split("\t")
                if columns[:8] != _VCF_COLUMNS:
                    raise ValueError("Malformed VCF header: expected the standard first eight columns.")
                if len(columns) > 8 and columns[8] != "FORMAT":
                    raise ValueError("Malformed VCF header: sample columns must follow FORMAT.")
                sample_names = columns[9:] if len(columns) > 9 else []
                if len(sample_names) > MAX_VCF_SAMPLES:
                    raise ValueError(
                        f"VCF contains {len(sample_names):,} samples; the configured limit is {MAX_VCF_SAMPLES:,}."
                    )
                if any(not name for name in sample_names) or len(set(sample_names)) != len(sample_names):
                    raise ValueError("Malformed VCF header: sample names must be present and unique.")
                meta["columns"] = columns
                meta["sample_names"] = sample_names
                for sample in sample_names:
                    sample_metrics[sample] = {
                        "allele_calls": 0,
                        "missing_calls": 0,
                        "partial_calls": 0,
                        "heterozygous_calls": 0,
                        "homozygous_alt_calls": 0,
                        "homozygous_ref_calls": 0,
                        "other_alt_calls": 0,
                        "dp_sum": 0,
                        "dp_count": 0,
                        "gq_sum": 0.0,
                        "gq_count": 0,
                    }
                has_column_header = True
                continue
            if line.startswith("#"):
                raise ValueError(f"Unexpected VCF header at line {line_no}.")
            if not has_column_header:
                raise ValueError("VCF data rows appeared before the #CHROM header.")

            fields = line.split("\t")
            if len(fields) != len(meta["columns"]):
                raise ValueError(
                    f"Malformed VCF row at line {line_no}: expected {len(meta['columns'])} tab-separated fields."
                )
            chrom, raw_pos, identifier, ref, raw_alts, raw_qual, filt, raw_info = fields[:8]
            try:
                position = int(raw_pos)
            except ValueError as exc:
                raise ValueError(f"Invalid coordinate at VCF line {line_no}.") from exc
            if position < 1 or not chrom or not ref or not raw_alts:
                raise ValueError(f"Invalid coordinate or allele at VCF line {line_no}.")
            source_records += 1
            if raw_alts == ".":
                continue

            alts = raw_alts.split(",")
            if any(not alt for alt in alts):
                raise ValueError(f"Empty alternate allele at VCF line {line_no}.")
            qual = _number(raw_qual)
            if raw_qual not in {"", "."} and qual is None:
                raise ValueError(f"Invalid quality score at VCF line {line_no}.")
            if qual is not None and qual < 0:
                raise ValueError(f"Negative quality score at VCF line {line_no}.")
            info = _parse_info(raw_info)
            format_keys = fields[8].split(":") if len(fields) > 8 else []
            if len(fields) > 8 and not format_keys:
                raise ValueError(f"Empty FORMAT field at VCF line {line_no}.")
            sample_values = fields[9:] if len(fields) > 9 else []
            parsed_samples: list[dict[str, Any]] = []
            for sample_name, raw_sample in zip(meta["sample_names"], sample_values):
                sample_map = dict(zip(format_keys, raw_sample.split(":")))
                gt = sample_map.get("GT", ".")
                genotype_alleles, genotype_status = _parse_gt(gt)
                if genotype_status == "INVALID":
                    raise ValueError(f"Invalid genotype in sample {sample_name} at VCF line {line_no}.")
                if any(allele is not None and allele > len(alts) for allele in genotype_alleles):
                    raise ValueError(f"Genotype allele index is out of range at VCF line {line_no}.")
                dp = _number(sample_map.get("DP"), integer=True)
                gq = _number(sample_map.get("GQ"))
                if (dp is not None and dp < 0) or (gq is not None and gq < 0):
                    raise ValueError(f"Negative DP or GQ value at VCF line {line_no}.")
                ad_raw = sample_map.get("AD", "")
                ad = [_number(value, integer=True) for value in ad_raw.split(",")] if ad_raw else []
                if any(value is not None and value < 0 for value in ad):
                    raise ValueError(f"Negative AD value at VCF line {line_no}.")
                parsed_samples.append(
                    {
                        "sample": sample_name,
                        "GT": gt,
                        "genotype_status": genotype_status,
                        "alleles": genotype_alleles,
                        "DP": dp,
                        "GQ": gq,
                        "AD": ad,
                    }
                )
                metrics = sample_metrics[sample_name]
                if dp is not None:
                    metrics["dp_sum"] += dp
                    metrics["dp_count"] += 1
                if gq is not None:
                    metrics["gq_sum"] += gq
                    metrics["gq_count"] += 1

            for alt_index, alt in enumerate(alts, 1):
                cursor = duplicate_db.execute(
                    "INSERT OR IGNORE INTO seen_alleles VALUES (?, ?, ?, ?)",
                    (chrom, position, ref, alt),
                )
                duplicate = cursor.rowcount == 0
                allele_rows_seen += 1
                if allele_rows_seen % 50_000 == 0:
                    duplicate_db.commit()
                if duplicate:
                    duplicate_alleles += 1

                variant_type = classify_variant_type(ref, alt, info)
                by_type[variant_type] += 1
                by_chromosome[chrom] += 1
                by_filter[filt or "."] += 1
                if qual is not None:
                    variants_with_qual += 1
                    qual_sum += float(qual)
                    qual_min = float(qual) if qual_min is None else min(qual_min, float(qual))
                    qual_max = float(qual) if qual_max is None else max(qual_max, float(qual))

                info_af_values = str(info.get("AF", "")).split(",")
                info_af = _number(info_af_values[alt_index - 1]) if alt_index <= len(info_af_values) else None
                if info_af is not None and not 0 <= info_af <= 1:
                    raise ValueError(f"Invalid INFO/AF value at VCF line {line_no}.")
                called_alleles = alt_allele_count = called_samples = 0
                call_counts: Counter[str] = Counter()
                sample_calls: list[dict[str, Any]] = []
                for sample in parsed_samples:
                    category, copies, called = _allele_call(sample["alleles"], alt_index)
                    called_alleles += called
                    alt_allele_count += copies
                    called_samples += category not in {"MISSING", "PARTIAL", "INVALID"}
                    call_counts[category] += 1
                    genotype_counts[category] += 1
                    metrics = sample_metrics[sample["sample"]]
                    metrics["allele_calls"] += 1
                    metric_key = {
                        "MISSING": "missing_calls",
                        "PARTIAL": "partial_calls",
                        "HET": "heterozygous_calls",
                        "HOM_ALT": "homozygous_alt_calls",
                        "HOM_REF": "homozygous_ref_calls",
                        "OTHER_ALT": "other_alt_calls",
                    }.get(category)
                    if metric_key:
                        metrics[metric_key] += 1
                    if len(sample_calls) < sample_preview_limit:
                        ad = sample["AD"]
                        alt_depth = ad[alt_index] if alt_index < len(ad) else None
                        ad_total = sum(value for value in ad if value is not None)
                        sample_calls.append(
                            {
                                "sample": sample["sample"],
                                "GT": sample["GT"],
                                "call": category,
                                "DP": sample["DP"],
                                "GQ": sample["GQ"],
                                "alt_depth": alt_depth,
                                "AD_frequency": (
                                    round(alt_depth / ad_total, 6)
                                    if alt_depth is not None and ad_total > 0
                                    else None
                                ),
                            }
                        )

                cohort_af = alt_allele_count / called_alleles if called_alleles else None
                gene_info = info.get("GENEINFO")
                consequence = next((info[k] for k in _CONSEQUENCE_KEYS if k in info), None)
                hgvs = next((info[k] for k in _HGVS_KEYS if k in info), None)
                clnsig = info.get("CLNSIG")
                rsid = info.get("RS")
                variants_with_gene_field += "GENEINFO" in info
                variants_with_consequence_field += any(key in info for key in _CONSEQUENCE_KEYS)
                variants_with_hgvs_field += any(key in info for key in _HGVS_KEYS)
                variants_with_clnsig_field += "CLNSIG" in info
                variants_with_rsid += "RS" in info
                svlen_values = str(info.get("SVLEN", "")).split(",")
                svlen = _number(svlen_values[alt_index - 1], integer=True) if alt_index <= len(svlen_values) else None
                end = _number(str(info.get("END", "")), integer=True)
                row = {
                    "chrom": chrom,
                    "pos": position,
                    "id": identifier,
                    "ref": ref,
                    "alt": alt,
                    "qual": qual,
                    "filter": filt,
                    "variant_type": variant_type,
                    "sv_type": _sv_type(alt, info),
                    "svlen": svlen,
                    "end": end,
                    "duplicate": duplicate,
                    "normalization_status": "not_verified_reference_required",
                    "source_af_info": info_af,
                    "cohort_af_from_genotypes": round(cohort_af, 6) if cohort_af is not None else None,
                    "called_alleles": called_alleles,
                    "called_samples": called_samples,
                    "genotype_counts": dict(call_counts),
                    "gene_info_source_field": gene_info,
                    "consequence_source_field": consequence,
                    "hgvs_source_field": hgvs,
                    "clinvar_significance_source_field": clnsig,
                    "dbsnp_rs_source_field": rsid,
                    "sample_calls": sample_calls,
                    "info": raw_info,
                }
                if len(preview) < preview_limit:
                    preview.append(row)

    except ValueError:
        raise
    except sqlite3.Error as exc:
        raise ValueError("Could not track exact duplicates in temporary SQLite storage.") from exc
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError) as exc:
        raise ValueError(
            "Could not read VCF. Check that the file is valid plain-text VCF or gzip-compressed VCF."
        ) from exc
    finally:
        if compressed:
            text.close()
        else:
            text.detach()
        duplicate_db.close()

    if not has_column_header:
        raise ValueError("VCF column header (#CHROM) is missing.")
    if not by_type:
        raise ValueError("No variant rows found in this VCF file.")

    detected_build = _declared_build(meta["headers"])
    expected = _normalise_build(expected_build)
    build_status = _build_status(detected_build, expected)
    meta.update(
        {
            "reference_build": detected_build,
            "expected_reference_build": expected,
            "reference_build_status": build_status,
            "sample_count": len(meta["sample_names"]),
        }
    )
    for metrics in sample_metrics.values():
        metrics["mean_DP"] = round(metrics.pop("dp_sum") / metrics["dp_count"], 3) if metrics["dp_count"] else None
        metrics["mean_GQ"] = round(metrics.pop("gq_sum") / metrics["gq_count"], 3) if metrics["gq_count"] else None

    summary = {
        "variant_records": sum(by_type.values()),
        "source_records": source_records,
        "by_type": dict(by_type),
        "by_chromosome": dict(by_chromosome),
        "by_filter": dict(by_filter),
        "genotype_counts": dict(genotype_counts),
        "sample_metrics": sample_metrics,
        "sample_count": len(meta["sample_names"]),
        "duplicate_alleles": duplicate_alleles,
        "variants_with_qual": variants_with_qual,
        "mean_qual": round(qual_sum / variants_with_qual, 3) if variants_with_qual else None,
        "min_qual": qual_min,
        "max_qual": qual_max,
        "embedded_annotation_counts": {
            "gene": variants_with_gene_field,
            "consequence": variants_with_consequence_field,
            "hgvs": variants_with_hgvs_field,
            "clinvar_significance": variants_with_clnsig_field,
            "dbsnp_rs": variants_with_rsid,
        },
        "decompressed_bytes": decompressed_bytes,
        "preview_limit": preview_limit,
        "normalization_note": "Not verified: reference FASTA is required for REF validation and indel normalization.",
        "classification_note": "No classification generated. Embedded source assertions, if present, are displayed as source fields.",
    }
    return summary, meta, preview


def classify_variant_type(ref: str, alt: str, info: dict[str, str | bool] | None = None) -> str:
    """Label a VCF allele by representation without inferring its consequence."""
    if info and info.get("SVTYPE"):
        return "STRUCTURAL"
    if alt == "*" or (alt.startswith("<") and alt.endswith(">")) or "[" in alt or "]" in alt:
        return "STRUCTURAL"
    if len(ref) == len(alt) == 1:
        return "SNP"
    if len(ref) != len(alt):
        return "INDEL"
    return "COMPLEX"
