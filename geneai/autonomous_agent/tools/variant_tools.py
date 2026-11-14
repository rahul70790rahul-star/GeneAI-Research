"""Variant analysis tools for the Autonomous Bioinformatics Agent.

Annotations are retrieved from live public APIs:

* **Ensembl VEP** (REST) for consequence, impact, gene/transcript and SIFT/PolyPhen.
* **gnomAD** (GraphQL) for population allele frequency (exome + genome).
* **NCBI ClinVar** (E-utilities) for clinical significance.

Nothing is fabricated: when a source cannot be reached or has no record, the
annotation is reported as ``unavailable`` or ``not_found`` with the reason, and
the reason is surfaced to the caller.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from geneai.autonomous_agent.tools import Tool, ToolParameter, ToolSpec
from geneai.config import PUBMED_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

VEP_ENDPOINTS = {
    "GRCh38": "https://rest.ensembl.org",
    "GRCh37": "https://grch37.rest.ensembl.org",
}
GNOMAD_DATASETS = {
    "GRCh38": "gnomad_r4",
    "GRCh37": "gnomad_r2_1",
}
GNOMAD_URL = "https://gnomad.broadinstitute.org/api"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_RATE_INTERVALS = {
    "rest.ensembl.org": 0.15,
    "grch37.rest.ensembl.org": 0.15,
    "gnomad.broadinstitute.org": 0.25,
    "eutils.ncbi.nlm.nih.gov": 0.34,
}
_rate_lock = threading.Lock()
_last_request_at: dict[str, float] = {}

_CHROM_RE = re.compile(r"^(?:chr)?(?:[0-9]{1,2}|X|Y|MT)$", re.IGNORECASE)
_BASE_RE = re.compile(r"^[ACGTNacgtn]+$")
_VARIANT_ID_RE = re.compile(r"^(?:[0-9]{1,2}|X|Y|MT)-\d+-[ACGTN]+-[ACGTN]+$")
_IMPACT_ORDER = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "MODIFIER": 3}


class VariantAnnotationError(RuntimeError):
    """An external annotation source returned an unusable response."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rate_limit(host: str) -> None:
    interval = _RATE_INTERVALS.get(host, 0.0)
    if not interval:
        return
    with _rate_lock:
        wait = interval - (time.monotonic() - _last_request_at.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_request_at[host] = time.monotonic()


def _request(
    method: str,
    url: str,
    *,
    timeout: float = PUBMED_TIMEOUT_SECONDS,
    expect_json: bool = True,
    attempts: int = 3,
    **kwargs: Any,
) -> Any:
    """HTTP request with throttling, bounded retries and clear failures."""
    host = urlparse(url).hostname or ""
    headers = {
        "User-Agent": "GeneAIResearch/0.5 (Autonomous Agent; variant annotation)",
        **(kwargs.pop("headers", {}) or {}),
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        _rate_limit(host)
        try:
            response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
                continue
            raise VariantAnnotationError(f"Request to {host} failed: {exc}") from exc

        if response.status_code in _RETRY_STATUS and attempt + 1 < attempts:
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(5.0, max(0.0, float(retry_after)))
            except ValueError:
                delay = 0.5 * (2**attempt)
            time.sleep(delay)
            continue
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text[:240].replace("\n", " ")
            raise VariantAnnotationError(
                f"{host} returned HTTP {response.status_code}: {body or response.reason}"
            ) from exc
        if not expect_json:
            return response.text
        try:
            return response.json()
        except ValueError as exc:
            raise VariantAnnotationError(f"{host} returned invalid JSON.") from exc

    raise VariantAnnotationError(
        f"Request to {host} failed: {last_error or 'retry limit reached'}"
    )


def _normalise_variant(
    chrom: Any, pos: Any, ref: Any, alt: Any
) -> tuple[str, int, str, str]:
    """Validate and normalise the four core VCF fields."""
    chrom_s = str(chrom).strip()
    if chrom_s.lower().startswith("chr"):
        chrom_s = chrom_s[3:]
    if not _CHROM_RE.match(chrom_s):
        raise ValueError(f"Invalid chromosome: {chrom!r}")
    chrom_s = chrom_s.upper()
    try:
        pos_i = int(pos)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid position: {pos!r}") from exc
    if pos_i < 1:
        raise ValueError(f"Position must be >= 1, got {pos_i}")
    ref_s = str(ref).strip().upper()
    alt_s = str(alt).strip().upper()
    if not ref_s or not alt_s:
        raise ValueError("Both ref and alt alleles are required")
    if not _BASE_RE.match(ref_s) or not _BASE_RE.match(alt_s):
        # Multi-allelic and symbolic alleles (e.g. <DEL>) are handled upstream.
        raise ValueError(f"Unsupported allele characters: {ref_s!r}>{alt_s!r}")
    return chrom_s, pos_i, ref_s, alt_s


# ---------------------------------------------------------------------------
# Ensembl VEP
# ---------------------------------------------------------------------------

def _vep_variant_string(chrom: str, pos: int, ref: str, alt: str) -> str:
    """Build the Ensembl VEP ``region`` variant notation."""
    # Region format: chrom:start-end:strand:allele. The span covers the REF allele.
    end = pos + max(0, len(ref) - 1)
    return f"{chrom}:{pos}-{end}:1:{alt}"


def _pick_transcript(transcripts: list[dict[str, Any]]) -> dict[str, Any] | None:
    coding = [t for t in transcripts if t.get("biotype") == "protein_coding"]
    pool = coding or transcripts
    if not pool:
        return None
    canonical = [t for t in pool if t.get("canonical")]
    candidates = canonical or pool
    return min(
        candidates,
        key=lambda t: _IMPACT_ORDER.get(str(t.get("impact", "MODIFIER")), 9),
    )


def fetch_vep_annotation(
    chrom: str,
    pos: int,
    ref: str,
    alt: str,
    genome_build: str = "GRCh38",
    timeout: float = PUBMED_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Annotate one variant with Ensembl VEP."""
    base = VEP_ENDPOINTS.get(genome_build)
    if base is None:
        raise ValueError(f"Unsupported genome build: {genome_build}")

    variant = _vep_variant_string(chrom, pos, ref, alt)
    payload = _request(
        "POST",
        f"{base}/vep/human/region",
        json={"variants": [variant]},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=timeout,
    )
    if not isinstance(payload, list):
        raise VariantAnnotationError("Ensembl VEP returned an unexpected payload.")
    if not payload:
        return {
            "status": "not_found",
            "source": "Ensembl VEP",
            "assembly": genome_build,
            "retrieved_at": _now(),
        }

    entry = payload[0]
    transcript = _pick_transcript(entry.get("transcript_consequences") or [])
    annotation: dict[str, Any] = {
        "status": "ok",
        "source": "Ensembl VEP",
        "source_url": f"{base}/vep/human/region",
        "assembly": entry.get("assembly_name", genome_build),
        "consequence": entry.get("most_severe_consequence"),
        "consequence_terms": (transcript or {}).get("consequence_terms", []),
        "retrieved_at": _now(),
    }
    if transcript:
        amino_acids = transcript.get("amino_acids")
        protein_start = transcript.get("protein_start")
        protein_change = transcript.get("hgvsp")
        if not protein_change and amino_acids and protein_start:
            protein_change = f"p.{amino_acids.replace('/', '')}{protein_start}"
        annotation.update(
            {
                "impact": transcript.get("impact"),
                "gene_symbol": transcript.get("gene_symbol"),
                "gene_id": transcript.get("gene_id"),
                "transcript_id": transcript.get("transcript_id"),
                "biotype": transcript.get("biotype"),
                "canonical": bool(transcript.get("canonical")),
                "hgvsc": transcript.get("hgvsc"),
                "hgvsp": transcript.get("hgvsp"),
                "protein_change": protein_change,
                "codons": transcript.get("codons"),
                "sift_score": transcript.get("sift_score"),
                "sift_prediction": transcript.get("sift_prediction"),
                "polyphen_score": transcript.get("polyphen_score"),
                "polyphen_prediction": transcript.get("polyphen_prediction"),
                "existing_variation": entry.get("existing_variation", []),
            }
        )
    else:
        annotation["impact"] = None
        annotation["gene_symbol"] = None
    return annotation


# ---------------------------------------------------------------------------
# gnomAD
# ---------------------------------------------------------------------------

def _gnomad_populations(*datasets: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    """Combine per-population counts across exome/genome sections."""
    combined: dict[str, dict[str, float]] = {}
    for dataset in datasets:
        for population in (dataset or {}).get("populations") or []:
            # Sex-specific strata are not useful for a popmax summary.
            if not isinstance(population, dict) or str(population.get("id", "")).endswith(
                ("_XX", "_XY")
            ):
                continue
            ac = population.get("ac") or 0
            an = population.get("an") or 0
            if an <= 0:
                continue
            entry = combined.setdefault(str(population["id"]), {"ac": 0, "an": 0})
            entry["ac"] += ac
            entry["an"] += an
    for entry in combined.values():
        entry["af"] = entry["ac"] / entry["an"] if entry["an"] else 0.0
    return combined


def fetch_gnomad_frequency(
    chrom: str,
    pos: int,
    ref: str,
    alt: str,
    genome_build: str = "GRCh38",
    timeout: float = PUBMED_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fetch gnomAD allele frequency for one variant."""
    dataset = GNOMAD_DATASETS.get(genome_build)
    if dataset is None:
        raise ValueError(f"Unsupported genome build: {genome_build}")

    variant_id = f"{chrom}-{pos}-{ref}-{alt}"
    if not _VARIANT_ID_RE.match(variant_id):
        raise ValueError(f"Invalid variant id: {variant_id}")

    query = (
        "query Variant($variantId: String!) {"
        f" variant(dataset: {dataset}, variantId: $variantId) {{"
        "  variantId"
        "  exome { ac an af populations { id ac an } }"
        "  genome { ac an af populations { id ac an } }"
        " }"
        "}"
    )
    payload = _request(
        "POST",
        GNOMAD_URL,
        json={"query": query, "variables": {"variantId": variant_id}},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise VariantAnnotationError("gnomAD returned an unexpected payload.")
    if payload.get("errors") and not (payload.get("data") or {}).get("variant"):
        message = "; ".join(
            str(error.get("message", error)) for error in payload["errors"]
        )
        return {
            "status": "unavailable",
            "source": "gnomAD",
            "dataset": dataset,
            "error": message,
            "retrieved_at": _now(),
        }

    variant = (payload.get("data") or {}).get("variant")
    if not variant:
        return {
            "status": "not_found",
            "source": "gnomAD",
            "dataset": dataset,
            "retrieved_at": _now(),
        }

    exome = variant.get("exome") or {}
    genome = variant.get("genome") or {}
    ac = (exome.get("ac") or 0) + (genome.get("ac") or 0)
    an = (exome.get("an") or 0) + (genome.get("an") or 0)
    af = ac / an if an else None
    populations = _gnomad_populations(exome, genome)
    popmax = max(populations.items(), key=lambda item: item[1]["af"], default=(None, None))

    return {
        "status": "ok",
        "source": "gnomAD",
        "dataset": dataset,
        "variant_id": variant.get("variantId", variant_id),
        "af": af,
        "ac": ac,
        "an": an,
        "popmax_af": popmax[1]["af"] if popmax[1] else None,
        "popmax_population": popmax[0],
        "populations": populations,
        "retrieved_at": _now(),
    }


# ---------------------------------------------------------------------------
# ClinVar (NCBI E-utilities)
# ---------------------------------------------------------------------------

def _clinvar_relevance(record: dict[str, Any]) -> tuple[int, int]:
    """Sort key: prefer classified variation records over haplotypes."""
    classification = record.get("germline_classification") or {}
    has_classification = bool(classification.get("description"))
    is_variation = str(record.get("obj_type", "")).lower() != "haplotype"
    return (int(has_classification) + int(is_variation), int(bool(is_variation)))


def fetch_clinvar_significance(
    chrom: str,
    pos: int,
    ref: str,
    alt: str,
    genome_build: str = "GRCh38",
    timeout: float = PUBMED_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Look up clinical significance in ClinVar via NCBI E-utilities."""
    position_field = "chrpos38" if genome_build == "GRCh38" else "chrpos37"
    term = f"{chrom}[chr] AND {pos}[{position_field}] AND {ref}>{alt}"
    search = _request(
        "GET",
        f"{NCBI_EUTILS}/esearch.fcgi",
        params={"db": "clinvar", "term": term, "retmode": "json", "retmax": 10},
        timeout=timeout,
    )
    ids = ((search or {}).get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return {
            "status": "not_found",
            "source": "ClinVar",
            "assembly": genome_build,
            "query": term,
            "retrieved_at": _now(),
        }

    summary = _request(
        "GET",
        f"{NCBI_EUTILS}/esummary.fcgi",
        params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
        timeout=timeout,
    )
    result = (summary or {}).get("result") or {}
    records = [
        result[uid]
        for uid in result.get("uids", [])
        if isinstance(result.get(uid), dict)
    ]
    if not records:
        return {
            "status": "not_found",
            "source": "ClinVar",
            "assembly": genome_build,
            "query": term,
            "retrieved_at": _now(),
        }

    best = max(records, key=_clinvar_relevance)
    classification = best.get("germline_classification") or {}
    traits = [
        trait.get("trait_name")
        for trait in classification.get("trait_set") or []
        if trait.get("trait_name")
    ]
    return {
        "status": "ok",
        "source": "ClinVar",
        "assembly": genome_build,
        "variant_id": best.get("accession_version") or best.get("accession"),
        "uid": best.get("uid"),
        "title": best.get("title"),
        "clinical_significance": classification.get("description") or "not provided",
        "review_status": classification.get("review_status") or "not provided",
        "last_evaluated": classification.get("last_evaluated"),
        "conditions": traits,
        "protein_change": best.get("protein_change"),
        "record_count": len(records),
        "query": term,
        "retrieved_at": _now(),
    }


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def annotate_variant(
    variant: dict[str, Any],
    *,
    genome_build: str = "GRCh38",
    annotate_gnomad: bool = True,
    predict_effect: bool = True,
    check_clinvar: bool = True,
) -> dict[str, Any]:
    """Annotate a single variant, recording per-source failures explicitly."""
    chrom = variant.get("chr", variant.get("chrom", variant.get("chromosome", "")))
    pos = variant.get("pos", variant.get("position", variant.get("start", 0)))
    ref = variant.get("ref", variant.get("reference", ""))
    alt = variant.get("alt", variant.get("alternate", ""))

    chrom, pos, ref, alt = _normalise_variant(chrom, pos, ref, alt)
    result: dict[str, Any] = {
        "variant": variant,
        "variant_id": f"{chrom}:{pos}:{ref}>{alt}",
        "genome_build": genome_build,
        "annotations": {},
    }

    jobs: list[tuple[str, Any]] = []
    if predict_effect:
        jobs.append(("effect_prediction", lambda: fetch_vep_annotation(
            chrom, pos, ref, alt, genome_build
        )))
    if annotate_gnomad:
        jobs.append(("gnomad", lambda: fetch_gnomad_frequency(
            chrom, pos, ref, alt, genome_build
        )))
    if check_clinvar:
        jobs.append(("clinvar", lambda: fetch_clinvar_significance(
            chrom, pos, ref, alt, genome_build
        )))

    for key, job in jobs:
        try:
            result["annotations"][key] = job()
        except Exception as exc:  # network/parse failures must stay visible
            logger.warning("Variant annotation %s failed for %s: %s", key, result["variant_id"], exc)
            result["annotations"][key] = {
                "status": "unavailable",
                "error": str(exc),
                "retrieved_at": _now(),
            }
    return result


def annotate_variants(
    variants: list[dict[str, Any]],
    *,
    genome_build: str = "GRCh38",
    annotate_gnomad: bool = True,
    predict_effect: bool = True,
    check_clinvar: bool = True,
) -> dict[str, Any]:
    """Annotate a batch of variants and summarise the classifications."""
    results = []
    for variant in variants:
        try:
            results.append(
                annotate_variant(
                    variant,
                    genome_build=genome_build,
                    annotate_gnomad=annotate_gnomad,
                    predict_effect=predict_effect,
                    check_clinvar=check_clinvar,
                )
            )
        except (ValueError, TypeError) as exc:
            results.append(
                {
                    "variant": variant,
                    "variant_id": None,
                    "status": "invalid",
                    "error": str(exc),
                    "annotations": {},
                }
            )
    return {
        "variants_analyzed": sum(1 for r in results if r.get("variant_id")),
        "results": results,
        "summary": _generate_summary(results),
    }


def _generate_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise annotation outcomes without inventing values."""
    total = len(results)
    pathogenic = benign = vus = 0
    high_impact = 0
    unavailable: dict[str, int] = {}
    not_found: dict[str, int] = {}

    for result in results:
        annotations = result.get("annotations") or {}
        clinvar = annotations.get("clinvar") or {}
        significance = str(clinvar.get("clinical_significance", "")).lower()
        if clinvar.get("status") == "ok":
            if "pathogenic" in significance and "conflicting" not in significance:
                pathogenic += 1
            elif "benign" in significance:
                benign += 1
            elif "uncertain" in significance:
                vus += 1

        effect = annotations.get("effect_prediction") or {}
        if effect.get("impact") == "HIGH":
            high_impact += 1

        for source, annotation in annotations.items():
            status = annotation.get("status")
            if status == "unavailable":
                unavailable[source] = unavailable.get(source, 0) + 1
            elif status == "not_found":
                not_found[source] = not_found.get(source, 0) + 1

    return {
        "total": total,
        "pathogenic": pathogenic,
        "benign": benign,
        "vus": vus,
        "high_impact": high_impact,
        "invalid": sum(1 for r in results if r.get("status") == "invalid"),
        "unavailable_annotations": unavailable,
        "not_found_annotations": not_found,
    }


class VariantAnalysisTool(Tool):
    """Analyze genetic variants with live functional and clinical annotation."""

    def __init__(self):
        spec = ToolSpec(
            name="variant_analysis",
            description="Annotate genetic variants with Ensembl VEP consequences, gnomAD population frequencies and ClinVar clinical significance",
            category="variant",
            parameters=[
                ToolParameter("variants", "array", "List of variants with chr, pos, ref, alt", required=True),
                ToolParameter("genome_build", "string", "Genome build", required=False, default="GRCh38", enum=["GRCh37", "GRCh38"]),
                ToolParameter("annotate_gnomad", "boolean", "Annotate with gnomAD frequencies", required=False, default=True),
                ToolParameter("predict_effect", "boolean", "Predict functional effect with Ensembl VEP", required=False, default=True),
                ToolParameter("check_clinvar", "boolean", "Check ClinVar for clinical significance", required=False, default=True),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        variants = kwargs.get("variants", [])
        if not variants:
            return {"error": "No variants provided"}
        if not isinstance(variants, list):
            return {"error": "variants must be a list of objects"}

        return annotate_variants(
            variants,
            genome_build=str(kwargs.get("genome_build", "GRCh38")),
            annotate_gnomad=bool(kwargs.get("annotate_gnomad", True)),
            predict_effect=bool(kwargs.get("predict_effect", True)),
            check_clinvar=bool(kwargs.get("check_clinvar", True)),
        )


class VariantFilterTool(Tool):
    """Filter variants by various criteria.

    Filters only apply when the relevant annotation is present and available;
    variants with a missing annotation are retained so that a network failure
    is never silently converted into a biological conclusion.
    """

    def __init__(self):
        spec = ToolSpec(
            name="variant_filter",
            description="Filter variants by frequency, impact, gene, region, or custom criteria",
            category="variant",
            parameters=[
                ToolParameter("variants", "array", "List of annotated variants", required=True),
                ToolParameter("max_af", "number", "Maximum allele frequency", required=False, default=0.01),
                ToolParameter("impact", "array", "Impact levels to keep", required=False, default=["HIGH", "MODERATE"]),
                ToolParameter("genes", "array", "Gene symbols to include", required=False),
                ToolParameter("regions", "array", "Genomic regions (chr:start-end)", required=False),
                ToolParameter("clinvar_significance", "array", "ClinVar significance to include", required=False),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        variants = kwargs.get("variants", [])
        if not variants:
            return {"error": "No variants provided"}

        filtered = [variant for variant in variants if self._passes_filters(variant, kwargs)]
        return {
            "original_count": len(variants),
            "filtered_count": len(filtered),
            "variants": filtered,
        }

    def _passes_filters(self, variant: dict[str, Any], filters: dict[str, Any]) -> bool:
        if variant.get("status") == "invalid" or not variant.get("variant_id"):
            return False

        annotations = variant.get("annotations") or {}

        max_af = filters.get("max_af", 0.01)
        gnomad = annotations.get("gnomad") or {}
        af = gnomad.get("af")
        if gnomad.get("status") == "ok" and af is not None and af > max_af:
            return False

        impacts = filters.get("impact", ["HIGH", "MODERATE"])
        effect = annotations.get("effect_prediction") or {}
        if effect.get("status") == "ok" and effect.get("impact") not in impacts:
            return False

        genes = filters.get("genes")
        if genes and effect.get("status") == "ok":
            if effect.get("gene_symbol") not in genes:
                return False

        clinvar_significance = filters.get("clinvar_significance")
        clinvar = annotations.get("clinvar") or {}
        if clinvar_significance and clinvar.get("status") == "ok":
            significance = str(clinvar.get("clinical_significance", "")).lower()
            wanted = {str(item).lower() for item in clinvar_significance}
            if not any(term in significance for term in wanted):
                return False

        regions = filters.get("regions")
        if regions:
            variant_id = variant.get("variant_id") or ""
            if not any(_variant_in_region(variant_id, region) for region in regions):
                return False

        return True


def _variant_in_region(variant_id: str, region: str) -> bool:
    """Return True when ``chr:pos:ref>alt`` falls inside ``chr:start-end``."""
    match = re.match(r"^(?:chr)?([0-9]{1,2}|X|Y|MT):(\d+):", variant_id, re.IGNORECASE)
    region_match = re.match(
        r"^(?:chr)?([0-9]{1,2}|X|Y|MT):(\d+)-(\d+)$", str(region).strip(), re.IGNORECASE
    )
    if not match or not region_match:
        return False
    chrom, pos = match.group(1).upper(), int(match.group(2))
    reg_chrom, start, end = (
        region_match.group(1).upper(),
        int(region_match.group(2)),
        int(region_match.group(3)),
    )
    return chrom == reg_chrom and start <= pos <= end


def register_variant_tools(registry):
    """Register variant analysis tools."""
    registry.register(VariantAnalysisTool())
    registry.register(VariantFilterTool())
