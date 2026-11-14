"""Evidence-grounded disease analysis and initial target prioritisation."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from geneai.drug_discovery import api_clients
from geneai.research import search_pubmed

DEFAULT_PRIORITY_WEIGHTS = {
    "genetic_association": 1.0,
    "genetic_literature": 1.0,
    "clinical": 1.0,
    "literature": 1.0,
    "affected_pathway": 1.0,
    "animal_model": 1.0,
}
_ID_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]{1,63}$")
_SPLIT_IDENTIFIERS = re.compile(r"[,;\s]+")


def search_diseases(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return disease autocomplete records from Open Targets."""
    return api_clients.search_open_targets_diseases(query, limit)


def parse_gene_identifiers(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Split a bounded list of symbols and stable IDs supplied by a researcher."""
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple)) else _SPLIT_IDENTIFIERS.split(value)
    clean = []
    for token in raw:
        token = str(token).strip()
        if token and _ID_TOKEN.fullmatch(token) and token not in clean:
            clean.append(token)
        if len(clean) >= 50:
            break
    return clean


def extract_vcf_gene_references(preview: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Extract only gene symbol/NCBI IDs present in Phase 3 VCF INFO preview fields."""
    output: dict[str, dict[str, str]] = {}
    for row in preview or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("gene_info_source_field")
        if not isinstance(raw, str):
            continue
        for item in raw.split("|"):
            symbol, separator, gene_id = item.partition(":")
            symbol = symbol.strip().upper()
            gene_id = gene_id.strip() if separator else ""
            if re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", symbol):
                output[symbol] = {"gene_symbol": symbol, "ncbi_gene_id": gene_id}
    return list(output.values())[:50]


def _calculate_priority(target: dict[str, Any], weights: dict[str, float]) -> dict[str, Any]:
    evidence = target.get("datatype_scores", {})
    used = {
        key: (float(weights.get(key, 0.0)), float(value))
        for key, value in evidence.items()
        if key in weights and weights.get(key, 0.0) > 0 and isinstance(value, (int, float))
    }
    denominator = sum(weight for weight, _ in used.values())
    if denominator <= 0:
        return {
            "research_priority_index": None,
            "research_priority_tier": "Not scored",
            "priority_components": {},
            "priority_missing_domains": [key for key, weight in weights.items() if weight > 0],
        }
    index = sum(weight * score for weight, score in used.values()) / denominator * 100
    missing = [key for key, weight in weights.items() if weight > 0 and key not in used]
    tier = "High research shortlist" if index >= 67 else "Medium research shortlist" if index >= 34 else "Low research shortlist"
    return {
        "research_priority_index": round(index, 2),
        "research_priority_tier": tier,
        "priority_components": {key: {"weight": pair[0], "source_score": pair[1]} for key, pair in used.items()},
        "priority_missing_domains": missing,
    }


def apply_priority_weights(
    targets: list[dict[str, Any]], weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Calculate a configurable, explicitly heuristic research shortlist index."""
    normalized = dict(DEFAULT_PRIORITY_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in normalized:
                try:
                    weight = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Priority weight for {key} must be numeric.") from exc
                if not 0 <= weight <= 10:
                    raise ValueError(f"Priority weight for {key} must be between 0 and 10.")
                normalized[key] = weight
    if not any(normalized.values()):
        raise ValueError("At least one evidence weight must be greater than zero.")
    scored = []
    for target in targets:
        scored.append({**target, **_calculate_priority(target, normalized)})
    scored.sort(
        key=lambda target: (
            target.get("research_priority_index") is None,
            -(target.get("research_priority_index") or 0),
            -(target.get("association_score") or 0),
        )
    )
    return scored, normalized


def build_pubmed_query(
    disease_name: str,
    *,
    gene_symbols: list[str] | None = None,
    mutation_id: str | None = None,
    protein_id: str | None = None,
    research_keywords: str | None = None,
) -> str:
    """Build a bounded PubMed search expression from user-provided context."""
    terms = [f'"{disease_name.strip()}"[Title/Abstract]']
    extras = []
    if gene_symbols:
        extras.extend(f'{symbol}[Title/Abstract]' for symbol in gene_symbols[:5])
    for value in (mutation_id, protein_id, research_keywords):
        if value and value.strip():
            safe = " ".join(value.strip().split())[:100]
            extras.append(f'"{safe}"[Title/Abstract]')
    if extras:
        terms.append("(" + " OR ".join(extras) + ")")
    query = " AND ".join(terms)
    return query[:500]


def _attach_gene_context(
    targets: list[dict[str, Any]],
    ncbi: dict[str, dict[str, Any]],
    ensembl: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for target in targets:
        symbol = target["gene_symbol"].upper()
        ncbi_record = ncbi.get(symbol, {})
        ensembl_record = ensembl.get(symbol, {})
        target = {
            **target,
            "ncbi_gene_id": ncbi_record.get("ncbi_gene_id"),
            "gene_function_summary": ncbi_record.get("description"),
            "chromosome": ensembl_record.get("chromosome") or ncbi_record.get("chromosome"),
            "genomic_start": ensembl_record.get("start"),
            "genomic_end": ensembl_record.get("end"),
            "genomic_strand": ensembl_record.get("strand"),
            "assembly": ensembl_record.get("assembly"),
            "canonical_transcript": ensembl_record.get("canonical_transcript"),
            "ncbi_source_url": ncbi_record.get("source_url"),
            "ensembl_source_url": ensembl_record.get("source_url"),
        }
        enriched.append(target)
    return enriched


def analyze_disease(
    disease_id: str,
    *,
    disease_category: str = "Not specified",
    gene_identifiers: str | list[str] | tuple[str, ...] | None = None,
    mutation_id: str | None = None,
    protein_id: str | None = None,
    research_keywords: str | None = None,
    vcf_preview: list[dict[str, Any]] | None = None,
    target_limit: int = 20,
    priority_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Retrieve and normalize evidence for a selected Open Targets disease ID.

    API failures from optional sources are recorded in ``data_sources`` and do
    not erase data already returned by other sources. Open Targets is required
    because it supplies the selected disease and association result set.
    """
    if not isinstance(disease_id, str) or not _ID_TOKEN.fullmatch(disease_id.strip()):
        raise ValueError("Select a disease with a valid Open Targets identifier.")
    if isinstance(target_limit, bool) or not isinstance(target_limit, int) or not 1 <= target_limit <= api_clients.MAX_TARGETS:
        raise ValueError(f"Target limit must be between 1 and {api_clients.MAX_TARGETS}.")
    disease = api_clients.get_open_targets_disease(disease_id.strip(), target_limit)
    if disease is None:
        raise ValueError(f"Open Targets has no disease record for {disease_id}.")
    if not disease.get("name"):
        raise api_clients.DataSourceError("Open Targets disease record has no display name.")

    explicit_identifiers = parse_gene_identifiers(gene_identifiers)
    vcf_genes = extract_vcf_gene_references(vcf_preview)
    filter_tokens = {token.upper() for token in explicit_identifiers}
    filter_tokens.update(item["gene_symbol"] for item in vcf_genes)
    filter_tokens.update(item["ncbi_gene_id"] for item in vcf_genes if item.get("ncbi_gene_id"))

    targets = disease["targets"]
    target_symbols = [target["gene_symbol"] for target in targets]
    numeric_gene_ids = [token for token in explicit_identifiers if token.isdigit()]
    source_status: list[dict[str, Any]] = [
        {
            "source": "Open Targets Platform",
            "status": "available",
            "version": "not yet queried",
            "record_count": len(targets),
            "url": disease.get("source_url"),
        }
    ]
    limitations: list[str] = [
        "Open Targets association scores rank evidence aggregation; they are not calibrated confidence, druggability, or clinical classifications.",
        "The research priority index is a configurable heuristic over available Open Targets datatype scores, not an experimentally validated score.",
        "Genes are limited to the selected Open Targets result page; an input filter returning no rows does not prove that no association exists.",
    ]

    metadata: dict[str, str] = {"Open Targets": "not reported"}
    try:
        ot_metadata = api_clients.get_open_targets_metadata()
        metadata["Open Targets"] = ot_metadata.get("data_version", "not reported")
        metadata["Open Targets API"] = ot_metadata.get("api_version", "not reported")
        source_status[0]["version"] = f"data {metadata['Open Targets']}; API {metadata['Open Targets API']}"
    except api_clients.DataSourceError as exc:
        source_status[0]["version_error"] = str(exc)

    ncbi: dict[str, dict[str, Any]] = {}
    if target_symbols or numeric_gene_ids:
        try:
            ncbi = api_clients.fetch_ncbi_gene_summaries(target_symbols, numeric_gene_ids)
            metadata["NCBI Gene"] = "not reported by E-utilities"
            source_status.append({"source": "NCBI Gene", "status": "available", "record_count": len(ncbi), "version": metadata["NCBI Gene"], "url": "https://www.ncbi.nlm.nih.gov/gene/"})
        except api_clients.DataSourceError as exc:
            source_status.append({"source": "NCBI Gene", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        source_status.append({"source": "NCBI Gene", "status": "not run", "record_count": 0, "reason": "No gene identifiers were returned."})

    ensembl: dict[str, dict[str, Any]] = {}
    if target_symbols:
        try:
            ensembl = api_clients.lookup_ensembl_symbols(target_symbols)
            source_versions = {item.get("source_release") for item in ensembl.values() if item.get("source_release") and item.get("source_release") != "not reported"}
            metadata["Ensembl"] = ", ".join(sorted(source_versions)) if source_versions else api_clients.get_ensembl_data_version()
            source_status.append({"source": "Ensembl REST", "status": "available", "record_count": len(ensembl), "version": metadata["Ensembl"], "url": "https://rest.ensembl.org/"})
        except api_clients.DataSourceError as exc:
            if ensembl:
                metadata["Ensembl"] = "not reported"
                source_status.append({"source": "Ensembl REST", "status": "available", "error": f"Gene lookup succeeded; release lookup unavailable: {exc}", "record_count": len(ensembl), "version": metadata["Ensembl"], "url": "https://rest.ensembl.org/"})
            else:
                source_status.append({"source": "Ensembl REST", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        source_status.append({"source": "Ensembl REST", "status": "not run", "record_count": 0, "reason": "No gene symbols were returned."})

    targets = _attach_gene_context(targets, ncbi, ensembl)
    if filter_tokens:
        filtered = [
            target for target in targets
            if target.get("gene_symbol", "").upper() in filter_tokens
            or str(target.get("ensembl_gene_id", "")).upper() in filter_tokens
            or str(target.get("ncbi_gene_id", "")).upper() in filter_tokens
        ]
        targets = filtered
    scored_targets, normalized_weights = apply_priority_weights(targets, priority_weights)
    if len(scored_targets) > 20:
        limitations.append("Protein, GO, and structure lookups are capped at the first 20 ranked targets to keep public API calls bounded.")
    if scored_targets:
        limitations.append("PubMed retrieval is limited to the first 10 records for the constructed query; it is not a complete literature review.")

    proteins: dict[str, dict[str, Any]] = {}
    protein_symbols = [target["gene_symbol"] for target in scored_targets[:20]]
    if protein_symbols:
        try:
            proteins = api_clients.search_uniprot_proteins(protein_symbols, limit=min(50, len(protein_symbols) * 2))
            metadata["UniProt"] = next((record.get("source_release") for record in proteins.values() if record.get("source_release")), "not reported")
            source_status.append({"source": "UniProtKB/Swiss-Prot", "status": "available", "record_count": len(proteins), "version": metadata["UniProt"], "url": "https://www.uniprot.org/"})
        except (api_clients.DataSourceError, ValueError) as exc:
            source_status.append({"source": "UniProtKB/Swiss-Prot", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        source_status.append({"source": "UniProtKB/Swiss-Prot", "status": "not run", "record_count": 0, "reason": "No target genes were available."})

    if protein_id:
        protein_tokens = {item.strip().upper() for item in re.split(r"[,;\s]+", protein_id) if item.strip()}
        proteins = {symbol: protein for symbol, protein in proteins.items() if protein.get("uniprot_id", "").upper() in protein_tokens}
        if not proteins:
            limitations.append("The supplied protein identifier did not match a reviewed UniProt protein in the retrieved target set.")

    go_annotations: list[dict[str, Any]] = []
    if proteins:
        try:
            go_annotations = api_clients.fetch_quickgo_annotations(
                [protein.get("uniprot_id", "") for protein in proteins.values()], limit=200
            )
            source_status.append({"source": "QuickGO / GOA", "status": "available", "record_count": len(go_annotations), "version": "annotation dates are included per record", "url": "https://www.ebi.ac.uk/QuickGO/"})
        except (api_clients.DataSourceError, ValueError) as exc:
            source_status.append({"source": "QuickGO / GOA", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        source_status.append({"source": "QuickGO / GOA", "status": "not run", "record_count": 0, "reason": "No UniProt proteins were available."})

    structure_accessions = [protein.get("uniprot_id", "") for protein in proteins.values()]
    structures: list[dict[str, Any]] = []
    if structure_accessions:
        try:
            structures = api_clients.search_rcsb_structures(structure_accessions, limit=20)
            source_status.append({"source": "RCSB PDB", "status": "available", "record_count": len(structures), "version": "live archive", "url": "https://www.rcsb.org/"})
        except (api_clients.DataSourceError, ValueError) as exc:
            source_status.append({"source": "RCSB PDB", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        source_status.append({"source": "RCSB PDB", "status": "not run", "record_count": 0, "reason": "No protein accessions were available."})

    pathways: dict[str, Any] = {"pathways": [], "warning": "Pathway analysis has not returned results."}
    if len(scored_targets) >= 2:
        try:
            pathways = api_clients.analyze_reactome_pathways([target["gene_symbol"] for target in scored_targets])
            metadata["Reactome"] = api_clients.get_reactome_database_version()
            pathways["source_version"] = metadata["Reactome"]
            source_status.append({"source": "Reactome Analysis Service", "status": "available", "record_count": len(pathways.get("pathways", [])), "version": metadata["Reactome"], "url": "https://reactome.org/"})
        except (api_clients.DataSourceError, ValueError) as exc:
            pathways = {"pathways": [], "warning": "Reactome enrichment was unavailable; no pathway significance is inferred."}
            source_status.append({"source": "Reactome Analysis Service", "status": "unavailable", "error": str(exc), "record_count": 0})
    else:
        pathways = {"pathways": [], "warning": "At least two gene targets are required; no pathway enrichment was run."}
        source_status.append({"source": "Reactome Analysis Service", "status": "not run", "record_count": 0, "reason": "Fewer than two gene targets were available."})

    pubmed_query = build_pubmed_query(
        disease["name"],
        gene_symbols=[target["gene_symbol"] for target in scored_targets],
        mutation_id=mutation_id,
        protein_id=protein_id,
        research_keywords=research_keywords,
    )
    publications: list[dict[str, Any]] = []
    try:
        publications = search_pubmed(pubmed_query, limit=10)
        try:
            abstracts = api_clients.fetch_pubmed_abstracts([paper["pmid"] for paper in publications])
        except api_clients.DataSourceError:
            abstracts = {}
        publications = [{**paper, "abstract": abstracts.get(paper["pmid"], ""), "source": "NCBI PubMed"} for paper in publications]
        source_status.append({"source": "NCBI PubMed", "status": "available", "record_count": len(publications), "version": "live index", "url": "https://pubmed.ncbi.nlm.nih.gov/"})
    except (RuntimeError, ValueError, api_clients.DataSourceError) as exc:
        source_status.append({"source": "NCBI PubMed", "status": "unavailable", "error": str(exc), "record_count": 0})

    disgenet = api_clients.disgenet_access_status()
    source_status.append(disgenet)
    limitations.append("DisGeNET was not queried because its account-specific API endpoint and license have not been configured in this build.")

    vcf_rows: list[dict[str, Any]] = []
    target_symbol_set = {target["gene_symbol"].upper() for target in scored_targets}
    mutation_tokens = {token.upper() for token in re.split(r"[,;\s]+", mutation_id or "") if token}
    for row in vcf_preview or []:
        if not isinstance(row, dict):
            continue
        gene_info = row.get("gene_info_source_field") or ""
        row_id = str(row.get("id", "")).upper()
        genes_in_row = {item.partition(":")[0].strip().upper() for item in str(gene_info).split("|")}
        if (target_symbol_set & genes_in_row) or (mutation_tokens and row_id in mutation_tokens):
            vcf_rows.append({key: row.get(key) for key in (
                "chrom", "pos", "id", "ref", "alt", "variant_type", "gene_info_source_field",
                "consequence_source_field", "hgvs_source_field", "clinvar_significance_source_field", "dbsnp_rs_source_field",
            ) if key in row})
    if mutation_id and not vcf_rows:
        limitations.append("The supplied mutation identifier did not match the current Phase 3 preview; no external clinical variant assertion was inferred.")

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mechanism_evidence = []
    for target in scored_targets[:20]:
        for evidence_type, value in target.get("datatype_scores", {}).items():
            mechanism_evidence.append(
                {
                    "gene_symbol": target["gene_symbol"],
                    "evidence_type": evidence_type,
                    "source_score": value,
                    "source": "Open Targets Platform",
                    "interpretation": "Database evidence component; not a standalone causal mechanism or confidence estimate.",
                    "source_url": target["source_url"],
                }
            )

    result = {
        "schema_version": "4.2.1",
        "analysis_id": str(uuid4()),
        "retrieved_at": retrieved_at,
        "inputs": {
            "disease_id": disease_id,
            "disease_category": disease_category,
            "gene_identifiers": explicit_identifiers,
            "mutation_id": mutation_id or "",
            "protein_id": protein_id or "",
            "research_keywords": research_keywords or "",
            "target_limit": target_limit,
            "vcf_gene_count": len(vcf_genes),
        },
        "disease": disease,
        "genes": scored_targets,
        "proteins": list(proteins.values()),
        "go_annotations": go_annotations,
        "structures": structures,
        "pathways": pathways,
        "mutations": vcf_rows,
        "mechanism_evidence": mechanism_evidence,
        "publications": publications,
        "pubmed_query": pubmed_query,
        "priority_weights": normalized_weights,
        "priority_method": "Weighted mean of available Open Targets datatype scores; missing domains are excluded and remaining weights renormalized. Heuristic research shortlist only.",
        "data_sources": source_status,
        "source_versions": metadata,
        "limitations": limitations,
        "research_only_disclaimer": "Research use only. This report is not a diagnosis, treatment recommendation, or experimentally validated druggability assessment.",
    }
    return result


def answer_research_question(result: dict[str, Any], question: str) -> dict[str, Any]:
    """Answer from retrieved records using a transparent, extractive retrieval step."""
    if not isinstance(question, str):
        raise ValueError("Research question must be text containing 1 to 500 characters.")
    question = " ".join(question.strip().split())
    if not question or len(question) > 500:
        raise ValueError("Research question must contain 1 to 500 characters.")
    terms = {word.lower() for word in re.findall(r"[A-Za-z0-9_-]{3,}", question)}
    evidence: list[tuple[float, dict[str, Any]]] = []
    for paper in result.get("publications", []):
        searchable = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        overlap = sum(term in searchable for term in terms)
        if overlap:
            evidence.append(
                (
                    float(overlap),
                    {
                        "kind": "publication",
                        "title": paper.get("title"),
                        "pmid": paper.get("pmid"),
                        "url": paper.get("url"),
                        "excerpt": _first_sentences(paper.get("abstract", ""), 2),
                        "retrieval_match_terms": overlap,
                    },
                )
            )
    for target in result.get("genes", []):
        name = f"{target.get('gene_symbol', '')} {target.get('gene_name', '')} {target.get('gene_function_summary', '')}".lower()
        overlap = sum(term in name for term in terms)
        if overlap or any(word in question.lower() for word in ("gene", "target", "cause", "associated")):
            evidence.append(
                (
                    float(overlap + (0.25 if target.get("association_score") is not None else 0)),
                    {
                        "kind": "disease_gene_association",
                        "gene_symbol": target.get("gene_symbol"),
                        "gene_name": target.get("gene_name"),
                        "association_score": target.get("association_score"),
                        "function_summary": target.get("gene_function_summary"),
                        "url": target.get("source_url"),
                    },
                )
            )
    for protein in result.get("proteins", []):
        searchable = " ".join(str(protein.get(key, "")) for key in (
            "gene_symbol", "protein_name", "function", "subcellular_location", "uniprot_id",
        )).lower()
        overlap = sum(term in searchable for term in terms)
        if overlap or any(word in question.lower() for word in ("protein", "structure", "domain", "function")):
            evidence.append(
                (
                    float(overlap + 0.25),
                    {
                        "kind": "protein_annotation",
                        "gene_symbol": protein.get("gene_symbol"),
                        "protein_name": protein.get("protein_name"),
                        "uniprot_id": protein.get("uniprot_id"),
                        "function": protein.get("function"),
                        "domains": protein.get("domains", []),
                        "subcellular_location": protein.get("subcellular_location"),
                        "url": protein.get("source_url"),
                    },
                )
            )
    for annotation in result.get("go_annotations", []):
        searchable = " ".join(str(annotation.get(key, "")) for key in (
            "gene_symbol", "go_name", "go_id", "aspect", "evidence_code",
        )).lower()
        overlap = sum(term in searchable for term in terms)
        if overlap or any(word in question.lower() for word in ("ontology", "biological process", "molecular function", "cellular component")):
            evidence.append(
                (
                    float(overlap + 0.1),
                    {
                        "kind": "gene_ontology_annotation",
                        "gene_symbol": annotation.get("gene_symbol"),
                        "name": annotation.get("go_name"),
                        "go_id": annotation.get("go_id"),
                        "aspect": annotation.get("aspect"),
                        "evidence_code": annotation.get("evidence_code"),
                        "reference": annotation.get("reference"),
                        "url": annotation.get("source_url"),
                    },
                )
            )
    for variant in result.get("mutations", []):
        searchable = " ".join(str(variant.get(key, "")) for key in (
            "id", "gene_info_source_field", "consequence_source_field", "hgvs_source_field",
            "clinvar_significance_source_field", "dbsnp_rs_source_field",
        )).lower()
        overlap = sum(term in searchable for term in terms)
        if overlap or any(word in question.lower() for word in ("mutation", "variant", "hgvs", "rsid")):
            evidence.append(
                (
                    float(overlap + 0.1),
                    {
                        "kind": "uploaded_vcf_preview_variant",
                        "variant_id": variant.get("id"),
                        "chromosome": variant.get("chrom"),
                        "position": variant.get("pos"),
                        "ref": variant.get("ref"),
                        "alt": variant.get("alt"),
                        "gene_annotation_from_input": variant.get("gene_info_source_field"),
                        "consequence_annotation_from_input": variant.get("consequence_source_field"),
                        "clinical_annotation_from_input": variant.get("clinvar_significance_source_field"),
                        "url": None,
                    },
                )
            )
    for pathway in result.get("pathways", {}).get("pathways", []):
        if not isinstance(pathway, dict):
            continue
        overlap = sum(term in str(pathway.get("name", "")).lower() for term in terms)
        if overlap or "pathway" in question.lower() or "mechanism" in question.lower():
            evidence.append((float(overlap + (0.2 if pathway.get("fdr") is not None else 0)), {"kind": "pathway_enrichment", **pathway}))
    evidence.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for _, item in evidence[:8]]
    if not selected:
        answer = "No matching gene, pathway, or publication evidence was retrieved for this question. Broaden the disease or literature search and review source records."
    else:
        answer = (
            f"Retrieved {len(selected)} potentially relevant records from the current analysis. "
            "Review the linked source records below. The ranking uses word overlap and available source fields; it does not infer disease causality."
        )
    return {
        "question": question,
        "answer": answer,
        "evidence": selected,
        "method": "Local retrieval-augmented evidence selection; no external generative model was used.",
        "limitations": ["An abstract or association score alone does not establish causality.", "No unsupported research-gap or clinical conclusion is generated."],
    }


def _first_sentences(text: str, max_sentences: int = 2) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(sentences[:max_sentences])[:700]
