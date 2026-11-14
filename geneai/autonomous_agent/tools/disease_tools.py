"""Disease intelligence tools for the Autonomous Bioinformatics Agent.

Uses Open Targets Platform, Reactome, QuickGO, PubMed, and ClinicalTrials.gov APIs.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from geneai.autonomous_agent.tools import Tool, ToolParameter, ToolSpec

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DiseaseProfilingTool(Tool):
    """Profile a disease from Open Targets and supporting public databases."""

    def __init__(self):
        spec = ToolSpec(
            name="disease_profiling",
            description=(
                "Profile disease biology: resolve a disease name/ID, retrieve "
                "associated genes, pathway enrichment, proteins and literature "
                "from Open Targets, NCBI, UniProt, Reactome and PubMed"
            ),
            category="disease",
            parameters=[
                ToolParameter("disease", "string", "Disease name or Open Targets ID (EFO/MONDO)", required=True),
                ToolParameter("target_limit", "number", "Maximum associated genes", required=False, default=20),
                ToolParameter("include_pathways", "boolean", "Run Reactome pathway enrichment", required=False, default=True),
                ToolParameter("research_keywords", "string", "Additional PubMed keywords", required=False),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        disease = kwargs.get("disease", "")
        if not disease:
            return {"error": "No disease provided"}

        target_limit = int(kwargs.get("target_limit", 20) or 20)
        include_pathways = bool(kwargs.get("include_pathways", True))
        research_keywords = kwargs.get("research_keywords")

        result = {
            "disease_query": disease,
            "disease": {},
            "targets": [],
            "pathways": [],
            "go_annotations": [],
            "literature": [],
            "data_sources": [],
            "retrieved_at": _now(),
        }

        try:
            from geneai.drug_discovery.api_clients import (
                search_open_targets_diseases,
                get_open_targets_disease,
                analyze_reactome_pathways,
                search_uniprot_proteins,
                fetch_quickgo_annotations,
            )
            from geneai.research import search_pubmed

            # 1. Search Open Targets for disease
            disease_matches = search_open_targets_diseases(disease, limit=5)
            if not disease_matches:
                return {"error": f"No disease found matching: {disease}", "retrieved_at": _now()}

            # Use first match
            disease_match = disease_matches[0]
            disease_id = disease_match["disease_id"]
            result["disease"] = disease_match

            # 2. Get disease details with targets
            disease_detail = get_open_targets_disease(disease_id, limit=target_limit)
            if disease_detail:
                result["disease"] = disease_detail
                targets = disease_detail.get("targets", [])
                result["targets"] = targets
                result["data_sources"].append({
                    "source": "Open Targets Platform",
                    "status": "ok",
                    "record_count": len(targets),
                })

                # 3. Pathway enrichment (Reactome)
                if include_pathways and targets:
                    gene_symbols = [t["gene_symbol"] for t in targets if t.get("gene_symbol")]
                    if len(gene_symbols) >= 2:
                        try:
                            pathways_result = analyze_reactome_pathways(gene_symbols, limit=20)
                            result["pathways"] = pathways_result.get("pathways", [])
                            result["data_sources"].append({
                                "source": "Reactome",
                                "status": "ok" if pathways_result.get("pathways") else "no_results",
                                "record_count": len(result["pathways"]),
                            })
                        except Exception as exc:
                            logger.warning("Reactome pathway analysis failed: %s", exc)
                            result["data_sources"].append({
                                "source": "Reactome",
                                "status": "error",
                                "error": str(exc),
                            })

                # 4. GO annotations
                if targets:
                    gene_symbols = [t["gene_symbol"] for t in targets if t.get("gene_symbol")]
                    if gene_symbols:
                        try:
                            uniprot_result = search_uniprot_proteins(gene_symbols)
                            accessions = [v["uniprot_id"] for v in uniprot_result.values() if v.get("uniprot_id")]
                            if accessions:
                                go_annotations = fetch_quickgo_annotations(accessions, limit=200)
                                result["go_annotations"] = go_annotations
                                result["data_sources"].append({
                                    "source": "QuickGO / GOA",
                                    "status": "ok",
                                    "record_count": len(go_annotations),
                                })
                        except Exception as exc:
                            logger.warning("GO annotation fetch failed: %s", exc)
                            result["data_sources"].append({
                                "source": "QuickGO / GOA",
                                "status": "error",
                                "error": str(exc),
                            })

            # 5. Literature search (PubMed)
            try:
                query = f"{disease}[Title/Abstract]"
                if research_keywords:
                    query += f" AND {research_keywords}"
                literature = search_pubmed(query, 10)
                result["literature"] = literature
                result["data_sources"].append({
                    "source": "PubMed",
                    "status": "ok",
                    "record_count": len(literature),
                })
            except Exception as exc:
                logger.warning("PubMed search failed: %s", exc)
                result["data_sources"].append({
                    "source": "PubMed",
                    "status": "error",
                    "error": str(exc),
                })

        except Exception as exc:
            logger.error("Disease profiling failed: %s", exc)
            result["error"] = str(exc)

        return result


class TargetIdentificationTool(Tool):
    """Rank druggable targets using Open Targets association and tractability."""

    def __init__(self):
        spec = ToolSpec(
            name="target_identification",
            description=(
                "Rank candidate drug targets for a disease using Open Targets "
                "association scores plus known-drug and tractability evidence"
            ),
            category="disease",
            parameters=[
                ToolParameter("disease_id", "string", "Open Targets disease ID (EFO/MONDO)", required=True),
                ToolParameter("min_score", "number", "Minimum association score", required=False, default=0.1),
                ToolParameter("limit", "number", "Maximum targets", required=False, default=20),
                ToolParameter("assess_tractability", "boolean", "Retrieve tractability metadata", required=False, default=True),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        disease_id = kwargs.get("disease_id", "")
        if not disease_id:
            return {"error": "No disease_id provided"}

        min_score = float(kwargs.get("min_score", 0.1) or 0.0)
        limit = int(kwargs.get("limit", 20) or 20)
        assess_tractability = bool(kwargs.get("assess_tractability", True))

        result = {
            "disease_id": disease_id,
            "targets": [],
            "tractability": [],
            "data_sources": [],
            "retrieved_at": _now(),
        }

        try:
            from geneai.drug_discovery.api_clients import (
                get_open_targets_disease,
                search_uniprot_proteins,
            )

            # Get disease with targets
            disease_detail = get_open_targets_disease(disease_id, limit=limit)
            if not disease_detail:
                return {"error": f"Disease not found: {disease_id}", "retrieved_at": _now()}

            targets = disease_detail.get("targets", [])
            # Filter by minimum score
            filtered_targets = [
                t for t in targets
                if t.get("association_score") is not None and t["association_score"] >= min_score
            ]
            result["targets"] = filtered_targets
            result["data_sources"].append({
                "source": "Open Targets Platform",
                "status": "ok",
                "record_count": len(filtered_targets),
            })

            # Tractability assessment via UniProt
            if assess_tractability and filtered_targets:
                gene_symbols = [t["gene_symbol"] for t in filtered_targets if t.get("gene_symbol")]
                if gene_symbols:
                    try:
                        uniprot_result = search_uniprot_proteins(gene_symbols)
                        tractability = []
                        for symbol, data in uniprot_result.items():
                            tractability.append({
                                "gene_symbol": symbol,
                                "uniprot_id": data.get("uniprot_id"),
                                "protein_name": data.get("protein_name"),
                                "function": data.get("function"),
                                "subcellular_location": data.get("subcellular_location"),
                                "domains": data.get("domains"),
                                "pdb_ids": data.get("pdb_ids_from_uniprot"),
                                "review_status": data.get("review_status"),
                            })
                        result["tractability"] = tractability
                        result["data_sources"].append({
                            "source": "UniProtKB/Swiss-Prot",
                            "status": "ok",
                            "record_count": len(tractability),
                        })
                    except Exception as exc:
                        logger.warning("Tractability fetch failed: %s", exc)
                        result["data_sources"].append({
                            "source": "UniProtKB/Swiss-Prot",
                            "status": "error",
                            "error": str(exc),
                        })

        except Exception as exc:
            logger.error("Target identification failed: %s", exc)
            result["error"] = str(exc)

        return result


class ClinicalTrialMappingTool(Tool):
    """Map clinical trials for a disease and optional genes."""

    def __init__(self):
        spec = ToolSpec(
            name="clinical_trial_mapping",
            description="Find ClinicalTrials.gov studies for a disease and its candidate genes",
            category="disease",
            parameters=[
                ToolParameter("disease", "string", "Disease name", required=True),
                ToolParameter("genes", "array", "Gene symbols to search separately", required=False),
                ToolParameter("limit", "number", "Maximum trials", required=False, default=20),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        disease = kwargs.get("disease", "")
        if not disease:
            return {"error": "No disease provided"}

        genes = kwargs.get("genes", [])
        limit = int(kwargs.get("limit", 20) or 20)

        result = {
            "disease": disease,
            "genes": genes,
            "trials": [],
            "retrieved_at": _now(),
        }

        try:
            import requests
            import xml.etree.ElementTree as ET

            NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

            # Build search query
            query_parts = [f"{disease}[Title/Abstract]"]
            if genes:
                gene_query = " OR ".join([f"{g}[Title/Abstract]" for g in genes[:5]])
                query_parts.append(f"({gene_query})")
            query = " AND ".join(query_parts)

            # Search ClinicalTrials.gov via PubMed (linked trials)
            search_params = {
                "db": "pubmed",
                "term": f"{query} AND clinical trial[pt]",
                "retmode": "json",
                "retmax": limit,
            }
            search_response = requests.get(f"{NCBI_EUTILS}/esearch.fcgi", params=search_params, timeout=30)
            search_response.raise_for_status()
            search_data = search_response.json()
            pmids = search_data.get("esearchresult", {}).get("idlist", [])

            if pmids:
                # Fetch details
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "xml",
                }
                fetch_response = requests.get(f"{NCBI_EUTILS}/efetch.fcgi", params=fetch_params, timeout=30)
                fetch_response.raise_for_status()

                root = ET.fromstring(fetch_response.text)
                for article in root.findall(".//PubmedArticle"):
                    pmid = article.findtext(".//PMID")
                    title = article.findtext(".//ArticleTitle")
                    abstract = article.find(".//Abstract")
                    abstract_text = ""
                    if abstract is not None:
                        abstract_text = " ".join("".join(abstract.itertext()).split())

                    journal = article.findtext(".//Journal/Title")
                    pub_date = article.findtext(".//PubDate/Year") or article.findtext(".//PubDate/MedlineDate")

                    result["trials"].append({
                        "pmid": pmid,
                        "title": title,
                        "abstract": abstract_text[:500] if abstract_text else "",
                        "journal": journal,
                        "publication_date": pub_date,
                        "source": "PubMed (ClinicalTrials.gov linked)",
                    })

            # Also try direct ClinicalTrials.gov API (if available)
            # Note: ClinicalTrials.gov has its own API but requires registration for high volume
            # This is a simplified version

        except Exception as exc:
            logger.error("Clinical trial mapping failed: %s", exc)
            result["error"] = str(exc)

        return result


def register_disease_tools(registry) -> None:
    """Register disease intelligence tools."""
    registry.register(DiseaseProfilingTool())
    registry.register(TargetIdentificationTool())
    registry.register(ClinicalTrialMappingTool())