"""Source-aware protein and structure API clients used by Phase 4.4."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

UNIPROT_REST = "https://rest.uniprot.org"
ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api"
RCSB_DATA_API = "https://data.rcsb.org/rest/v1/core"
RCSB_FILE_BASE = "https://files.rcsb.org/download"
PDBe_API = "https://www.ebi.ac.uk/pdbe/api"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MAX_STRUCTURE_BYTES = 50 * 1024 * 1024
_UNIPROT_ACCESSION = re.compile(r"^[A-Z0-9]{6,10}$")
_PDB_ID = re.compile(r"^[A-Z0-9]{4}$")
_NCBI_PROTEIN_ID = re.compile(r"^(?:\d{1,12}|[A-Z]{1,5}_\d{3,12}(?:\.\d+)?)$", re.IGNORECASE)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_resolution(value: Any) -> tuple[float | None, list[float]]:
    """Normalize the archive's scalar-or-list resolution representation."""
    raw_values = value if isinstance(value, list) else [value]
    values: list[float] = []
    for item in raw_values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            values.append(number)
    # Retain all values separately; expose a scalar only when the source is unambiguous.
    return (values[0] if len(values) == 1 else None, values)


def _uniprot_name(row: dict[str, Any]) -> str:
    description = row.get("proteinDescription")
    if not isinstance(description, dict):
        return ""
    recommended = description.get("recommendedName")
    if isinstance(recommended, dict):
        full_name = recommended.get("fullName")
        if isinstance(full_name, dict) and isinstance(full_name.get("value"), str):
            return _text(full_name["value"])
    submitted = description.get("submittedName")
    if isinstance(submitted, list) and submitted and isinstance(submitted[0], dict):
        full_name = submitted[0].get("fullName")
        if isinstance(full_name, dict) and isinstance(full_name.get("value"), str):
            return _text(full_name["value"])
    return ""


def _normalize_uniprot(row: dict[str, Any], release: str = "not reported") -> dict[str, Any]:
    """Normalize a UniProt search or entry record without inventing absent fields."""
    accession = row.get("primaryAccession")
    if not isinstance(accession, str) or not _UNIPROT_ACCESSION.fullmatch(accession):
        raise api_clients.DataSourceError("UniProt record did not contain a valid primary accession.")
    genes = row.get("genes") if isinstance(row.get("genes"), list) else []
    gene_symbol = None
    if genes and isinstance(genes[0], dict):
        gene = genes[0].get("geneName")
        if isinstance(gene, dict) and isinstance(gene.get("value"), str):
            gene_symbol = gene["value"]

    functions: list[str] = []
    locations: list[str] = []
    families: list[str] = []
    interactions: list[dict[str, Any]] = []
    for comment in row.get("comments", []) if isinstance(row.get("comments"), list) else []:
        if not isinstance(comment, dict):
            continue
        comment_type = comment.get("commentType")
        texts = comment.get("texts", [])
        values = [
            _text(item.get("value"))
            for item in texts
            if isinstance(item, dict) and isinstance(item.get("value"), str) and _text(item.get("value"))
        ] if isinstance(texts, list) else []
        if comment_type == "FUNCTION":
            functions.extend(values)
        elif comment_type == "SUBCELLULAR LOCATION":
            locations.extend(values)
        elif comment_type in {"SIMILARITY", "DOMAIN"}:
            families.extend(values)
        elif comment_type == "INTERACTION":
            for item in comment.get("interactions", []) if isinstance(comment.get("interactions"), list) else []:
                if isinstance(item, dict):
                    interactions.append({
                        "accession": item.get("interactant"),
                        "gene_name": item.get("geneName"),
                        "organism": item.get("organism"),
                        "source_note": "UniProt interaction comment; interaction type/evidence may be limited by the returned record.",
                    })

    feature_types = {"DOMAIN", "REGION", "REPEAT", "MOTIF", "ACTIVE SITE", "BINDING SITE", "SITE", "TRANSMEMBRANE"}
    features: list[dict[str, Any]] = []
    for feature in row.get("features", []) if isinstance(row.get("features"), list) else []:
        if not isinstance(feature, dict):
            continue
        feature_type = str(feature.get("type", "")).upper()
        if feature_type not in feature_types:
            continue
        location = feature.get("location") if isinstance(feature.get("location"), dict) else {}
        start = location.get("start") if isinstance(location.get("start"), dict) else {}
        end = location.get("end") if isinstance(location.get("end"), dict) else {}
        features.append({
            "type": feature_type,
            "description": feature.get("description"),
            "begin": start.get("value"),
            "end": end.get("value"),
            "evidence": feature.get("evidences", []),
        })

    cross_references = row.get("uniProtKBCrossReferences", [])
    pdb_ids = sorted({
        str(item.get("id")) for item in cross_references
        if isinstance(item, dict) and item.get("database") == "PDB" and isinstance(item.get("id"), str)
    }) if isinstance(cross_references, list) else []
    if isinstance(cross_references, list):
        families.extend(
            f"{item.get('database')}: {item.get('id')}"
            for item in cross_references
            if isinstance(item, dict) and item.get("database") in {"InterPro", "Pfam", "SUPFAM"} and item.get("id")
        )

    protein_description = row.get("proteinDescription") if isinstance(row.get("proteinDescription"), dict) else {}
    recommended = protein_description.get("recommendedName") if isinstance(protein_description.get("recommendedName"), dict) else {}
    ec_values = recommended.get("ecNumbers", []) if isinstance(recommended.get("ecNumbers"), list) else []
    sequence = row.get("sequence") if isinstance(row.get("sequence"), dict) else {}
    organism = row.get("organism") if isinstance(row.get("organism"), dict) else {}
    return {
        "primary_accession": accession,
        "uniprot_id": accession,
        "entry_name": row.get("uniProtkbId"),
        "gene_symbol": gene_symbol,
        "protein_name": _uniprot_name(row) or accession,
        "organism": organism.get("scientificName"),
        "taxon_id": organism.get("taxonId"),
        "sequence": sequence.get("value"),
        "sequence_source": "UniProtKB sequence field",
        "sequence_length": sequence.get("length"),
        "function": " ".join(dict.fromkeys(functions)),
        "subcellular_location": " ".join(dict.fromkeys(locations)),
        "family_annotations": list(dict.fromkeys(families)),
        "ec_numbers": [item.get("value") for item in ec_values if isinstance(item, dict) and item.get("value")],
        "features": features,
        "domains": [item for item in features if item["type"] == "DOMAIN"],
        "interactions": interactions,
        "pdb_ids": pdb_ids,
        "review_status": row.get("entryType", "not reported"),
        "source": "UniProtKB",
        "source_release": release,
        "source_url": f"https://www.uniprot.org/uniprotkb/{accession}/entry",
    }


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def search_uniprot_protein(query: str, input_kind: str) -> list[dict[str, Any]]:
    """Find reviewed human UniProt entries by accession, gene symbol, or protein name."""
    query = _text(query)
    if not query or len(query) > 160:
        raise ValueError("Enter a protein identifier, gene symbol, or protein name (1–160 characters).")
    if input_kind == "UniProt ID":
        accession = query.upper()
        if not _UNIPROT_ACCESSION.fullmatch(accession):
            raise ValueError("UniProt ID format is not valid.")
        response, payload = api_clients._request(
            "GET", f"{UNIPROT_REST}/uniprotkb/{accession}.json",
            headers={"Accept": "application/json"},
        )
        if not isinstance(payload, dict):
            raise api_clients.DataSourceError("UniProt returned an invalid protein entry.")
        return [_normalize_uniprot(payload, response.headers.get("x-uniprot-release", "not reported"))]
    if input_kind == "Gene symbol":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", query):
            raise ValueError("Gene symbol contains unsupported characters.")
        records = api_clients.search_uniprot_proteins([query], limit=10)
        return list(records.values())
    if input_kind != "Protein name":
        raise ValueError("Choose UniProt ID, protein name, or gene symbol for this search.")
    escaped = query.replace('"', " ")[:100]
    response, payload = api_clients._request(
        "GET", f"{UNIPROT_REST}/uniprotkb/search",
        params={"query": f'protein_name:"{escaped}" AND organism_id:9606 AND reviewed:true', "format": "json", "size": 10},
        headers={"Accept": "application/json"},
    )
    rows = payload.get("results", []) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise api_clients.DataSourceError("UniProt protein-name search returned an invalid result list.")
    result = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            record = _normalize_uniprot(row, response.headers.get("x-uniprot-release", "not reported"))
        except api_clients.DataSourceError:
            continue
        if record["primary_accession"] not in seen:
            seen.add(record["primary_accession"])
            result.append(record)
    return result


@ttl_cache(ttl_seconds=21_600, max_entries=32)
def fetch_ncbi_protein(protein_id: str) -> dict[str, Any]:
    """Retrieve one NCBI Protein record and FASTA sequence by ID/accession."""
    query = _text(protein_id)
    if not _NCBI_PROTEIN_ID.fullmatch(query):
        raise ValueError("Enter a valid NCBI Protein accession or numeric identifier.")
    term = f"{query}[UID]" if query.isdigit() else f'"{query}"[Accession]'
    _, search = api_clients._request(
        "GET", f"{NCBI_EUTILS}/esearch.fcgi",
        params={"db": "protein", "term": term, "retmode": "json", "retmax": 1},
    )
    ids = ((search.get("esearchresult") or {}).get("idlist") or []) if isinstance(search, dict) else []
    if not ids or not str(ids[0]).isdigit():
        raise ValueError(f"NCBI Protein has no record for {query}.")
    uid = str(ids[0])
    _, summary = api_clients._request(
        "GET", f"{NCBI_EUTILS}/esummary.fcgi",
        params={"db": "protein", "id": uid, "retmode": "json"},
    )
    summary_data = summary.get("result", {}) if isinstance(summary, dict) else {}
    item = summary_data.get(uid, {}) if isinstance(summary_data, dict) else {}
    if not isinstance(item, dict):
        raise api_clients.DataSourceError("NCBI Protein summary was malformed.")
    _, fasta = api_clients._request(
        "GET", f"{NCBI_EUTILS}/efetch.fcgi",
        params={"db": "protein", "id": uid, "rettype": "fasta", "retmode": "text"},
        expect_json=False,
    )
    lines = [line.strip() for line in str(fasta).splitlines() if line.strip()]
    sequence = "".join(line for line in lines if not line.startswith(">"))
    if not sequence:
        raise api_clients.DataSourceError("NCBI Protein returned no FASTA sequence.")
    accession = str(item.get("accessionversion") or item.get("caption") or query)
    organism = item.get("organism")
    return {
        "primary_accession": accession,
        "ncbi_protein_id": uid,
        "gene_symbol": None,
        "protein_name": item.get("title") or accession,
        "organism": organism if isinstance(organism, str) else None,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "function": "",
        "family_annotations": [],
        "ec_numbers": [],
        "features": [],
        "domains": [],
        "interactions": [],
        "source": "NCBI Protein",
        "source_release": "retrieval date; E-utilities does not return a release in this response",
        "source_url": f"https://www.ncbi.nlm.nih.gov/protein/{accession}",
    }


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def fetch_rcsb_entry_metadata(pdb_id: str) -> dict[str, Any]:
    """Retrieve one validated RCSB PDB entry's experiment and resolution fields."""
    entry = _text(pdb_id).upper()
    if not _PDB_ID.fullmatch(entry):
        raise ValueError("PDB identifier must be four alphanumeric characters.")
    _, payload = api_clients._request(
        "GET", f"{RCSB_DATA_API}/entry/{entry}",
        headers={"Accept": "application/json"},
    )
    if not isinstance(payload, dict):
        raise api_clients.DataSourceError("RCSB returned an invalid entry record.")
    info = payload.get("rcsb_entry_info", {}) if isinstance(payload.get("rcsb_entry_info"), dict) else {}
    methods = payload.get("exptl", []) if isinstance(payload.get("exptl"), list) else []
    citation = payload.get("struct", {}) if isinstance(payload.get("struct"), dict) else {}
    method = "; ".join(
        item.get("method", "") for item in methods if isinstance(item, dict) and item.get("method")
    )
    resolution, resolution_values = _normalize_resolution(info.get("resolution_combined"))
    accession_info = payload.get("rcsb_accession_info", {})
    return {
        "pdb_id": entry,
        "structure_id": entry,
        "title": citation.get("title"),
        "experimental_method": method,
        "resolution_angstrom": resolution,
        "resolution_values_angstrom": resolution_values,
        "release_date": accession_info.get("initial_release_date") if isinstance(accession_info, dict) else None,
        "structure_source": "RCSB PDB",
        "structure_type": "computational model in RCSB" if "THEORETICAL MODEL" in method.upper() else "experimentally determined PDB structure" if method else "PDB archive record; method unavailable",
        "format": "mmCIF",
        "download_url": f"{RCSB_FILE_BASE}/{entry}.cif",
        "source_url": f"https://www.rcsb.org/structure/{entry}",
        "metadata_source": "RCSB PDB Data API",
    }


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def search_rcsb_structures(uniprot_accession: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find PDB entries for a UniProt accession and enrich with RCSB/PDBe metadata."""
    accession = _text(uniprot_accession).upper()
    if not _UNIPROT_ACCESSION.fullmatch(accession):
        raise ValueError("A valid UniProt accession is required for structure search.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Structure result limit must be between 1 and 20.")
    references = api_clients.search_rcsb_structures([accession], limit=limit)
    structures: list[dict[str, Any]] = []
    for reference in references:
        pdb_id = str(reference.get("pdb_id", "")).upper()
        if not _PDB_ID.fullmatch(pdb_id):
            continue
        record: dict[str, Any] = {
            **reference,
            "pdb_id": pdb_id,
            "structure_id": pdb_id,
            "structure_source": "RCSB PDB",
            "structure_type": "experimental archive record; verify method in metadata",
            "format": "mmCIF",
            "download_url": f"{RCSB_FILE_BASE}/{pdb_id}.cif",
        }
        try:
            _, payload = api_clients._request(
                "GET", f"{RCSB_DATA_API}/entry/{pdb_id}",
                headers={"Accept": "application/json"},
            )
            info = payload.get("rcsb_entry_info", {}) if isinstance(payload, dict) else {}
            methods = payload.get("exptl", []) if isinstance(payload, dict) else []
            citation = payload.get("struct", {}) if isinstance(payload, dict) else {}
            record.update({
                "title": citation.get("title") if isinstance(citation, dict) else None,
                "experimental_method": "; ".join(
                    item.get("method", "") for item in methods if isinstance(item, dict) and item.get("method")
                ) if isinstance(methods, list) else "",
                "resolution_angstrom": _normalize_resolution(info.get("resolution_combined"))[0] if isinstance(info, dict) else None,
                "resolution_values_angstrom": _normalize_resolution(info.get("resolution_combined"))[1] if isinstance(info, dict) else [],
                "release_date": (payload.get("rcsb_accession_info") or {}).get("initial_release_date") if isinstance(payload, dict) and isinstance(payload.get("rcsb_accession_info"), dict) else None,
                "metadata_source": "RCSB PDB Data API",
            })
            method = str(record.get("experimental_method") or "").upper()
            record["structure_type"] = "computational model in RCSB" if "THEORETICAL MODEL" in method else "experimentally determined PDB structure" if method else "PDB archive record; method unavailable"
        except api_clients.DataSourceError as exc:
            record["metadata_error"] = str(exc)
        try:
            record["pdbe_metadata"] = fetch_pdbe_summary(pdb_id)
            pdbe = record["pdbe_metadata"]
            if not record.get("experimental_method") and pdbe.get("experimental_method"):
                record["experimental_method"] = pdbe["experimental_method"]
            if record.get("resolution_angstrom") is None and pdbe.get("resolution_angstrom") is not None:
                record["resolution_angstrom"] = pdbe["resolution_angstrom"]
        except api_clients.DataSourceError as exc:
            record["pdbe_error"] = str(exc)
        structures.append(record)
    return structures


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def fetch_pdbe_summary(pdb_id: str) -> dict[str, Any]:
    """Return PDBe summary metadata when available for an experimental PDB entry."""
    entry = _text(pdb_id).upper()
    if not _PDB_ID.fullmatch(entry):
        raise ValueError("PDB identifier must be four alphanumeric characters.")
    _, payload = api_clients._request(
        "GET", f"{PDBe_API}/pdb/entry/summary/{entry.lower()}",
        headers={"Accept": "application/json"},
    )
    rows = payload.get(entry.lower()) if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise api_clients.DataSourceError("PDBe returned no entry summary for this structure.")
    row = rows[0]
    methods = row.get("experimental_method", [])
    if isinstance(methods, str):
        method_text = methods
    elif isinstance(methods, list):
        method_text = "; ".join(str(item) for item in methods if item)
    else:
        method_text = ""
    resolution = row.get("resolution")
    if isinstance(resolution, list):
        resolution = resolution[0] if resolution else None
    try:
        resolution = float(resolution) if resolution is not None else None
    except (TypeError, ValueError):
        resolution = None
    return {
        "experimental_method": method_text,
        "resolution_angstrom": resolution,
        "release_date": row.get("release_date"),
        "source": "PDBe REST API",
        "source_url": f"https://www.ebi.ac.uk/pdbe/entry/pdb/{entry.lower()}",
    }


@ttl_cache(ttl_seconds=21_600, max_entries=128)
def get_alphafold_predictions(uniprot_accession: str) -> list[dict[str, Any]]:
    """Retrieve AlphaFold model metadata; outputs are explicitly predicted structures."""
    accession = _text(uniprot_accession).upper()
    if not _UNIPROT_ACCESSION.fullmatch(accession):
        raise ValueError("A valid UniProt accession is required for AlphaFold lookup.")
    _, payload = api_clients._request(
        "GET", f"{ALPHAFOLD_API}/prediction/{accession}",
        headers={"Accept": "application/json"},
    )
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("data", payload.get("predictions", payload.get("results", [])))
    if not isinstance(rows, list):
        raise api_clients.DataSourceError("AlphaFold API returned an invalid prediction list.")
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        returned_accession = str(row.get("uniprotAccession") or row.get("uniprot_id") or row.get("accession") or "").upper()
        if returned_accession and returned_accession != accession:
            continue
        entry_id = row.get("entryId") or row.get("modelId") or row.get("entry_id")
        cif_url = row.get("cifUrl") or row.get("cif_url")
        pdb_url = row.get("pdbUrl") or row.get("pdb_url")
        if not isinstance(entry_id, str) or not isinstance(cif_url, str):
            continue
        output.append({
            "structure_id": entry_id,
            "uniprot_accession": accession,
            "gene_symbol": row.get("gene") or row.get("gene_name"),
            "protein_name": row.get("uniprotDescription") or row.get("protein_name"),
            "model_created": row.get("modelCreatedDate") or row.get("created_at"),
            "model_version": row.get("latestVersion") or row.get("version"),
            "global_plddt": row.get("globalMetricValue") or row.get("global_plddt"),
            "cif_url": cif_url,
            "pdb_url": pdb_url,
            "confidence_url": row.get("confidenceUrl") or row.get("plddtDocUrl"),
            "pae_url": row.get("paeDocUrl") or row.get("pae_url"),
            "structure_source": "AlphaFold Protein Structure Database",
            "structure_type": "computationally predicted model; not experimentally determined",
            "format": "mmCIF",
            "source_url": f"https://alphafold.ebi.ac.uk/entry/{entry_id}",
        })
    return output


def download_structure_file(structure: dict[str, Any], file_format: str = "mmCIF") -> bytes:
    """Download an API-listed or validated archive structure in PDB/mmCIF format."""
    normalized_format = file_format.upper()
    if normalized_format not in {"PDB", "MMCIF", "CIF"}:
        raise ValueError("Structure format must be PDB or mmCIF.")
    suffix = ".pdb" if normalized_format == "PDB" else ".cif"
    url = structure.get("pdb_url") if suffix == ".pdb" else structure.get("cif_url") or structure.get("download_url")
    if not isinstance(url, str):
        structure_id = str(structure.get("pdb_id") or "").upper()
        if _PDB_ID.fullmatch(structure_id) and structure.get("structure_source") == "RCSB PDB":
            url = f"{RCSB_FILE_BASE}/{structure_id}{suffix}"
        else:
            raise ValueError("Selected structure source did not provide a coordinate file URL.")
    parsed = urlparse(url)
    allowed_hosts = {"files.rcsb.org", "alphafold.ebi.ac.uk"}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("Structure download URL is outside the supported public archive hosts.")
    response, body = api_clients._request(
        "GET", url, expect_json=False, timeout=60, attempts=2,
        headers={"Accept": "application/octet-stream, text/plain"},
    )
    data = response.content if hasattr(response, "content") and response.content else str(body).encode("utf-8")
    if len(data) > MAX_STRUCTURE_BYTES:
        raise ValueError(f"Structure file exceeds the {MAX_STRUCTURE_BYTES // (1024 * 1024)} MB limit.")
    if not data.strip() or data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise api_clients.DataSourceError("The structure archive returned an empty or non-coordinate response.")
    return data
