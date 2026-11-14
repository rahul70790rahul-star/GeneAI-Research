"""Literature search tools for the Autonomous Bioinformatics Agent.

Results come from live public literature APIs (PubMed E-utilities, Europe PMC,
Crossref, OpenAlex). No records are synthesised; a failing source is reported
as ``unavailable`` with the underlying error.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from geneai.autonomous_agent.tools import Tool, ToolParameter, ToolSpec

logger = logging.getLogger(__name__)

_SOURCE_ALIASES = {
    "pubmed": "pubmed",
    "europepmc": "europe_pmc",
    "europe_pmc": "europe_pmc",
    "crossref": "crossref",
    "openalex": "openalex",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def search_literature(
    query: str,
    databases: list[str] | None = None,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search one or more literature sources and return per-source results."""
    query = str(query or "").strip()
    if not query:
        return {"error": "No query provided"}

    limit = max(1, min(int(max_results or 20), 100))
    requested = databases or ["pubmed", "europepmc"]
    sources = sorted({_SOURCE_ALIASES.get(str(name).lower(), str(name).lower()) for name in requested})

    from geneai.research_analysis.literature_clients import (
        search_crossref,
        search_europe_pmc,
        search_openalex,
    )
    from geneai.research import search_pubmed

    handlers = {
        "pubmed": lambda: search_pubmed(query, limit),
        "europe_pmc": lambda: search_europe_pmc(query, limit),
        "crossref": lambda: search_crossref(query, limit),
        "openalex": lambda: search_openalex(query, limit),
    }

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for source in sources:
        handler = handlers.get(source)
        if handler is None:
            errors[source] = "Unsupported literature source"
            continue
        try:
            results[source] = handler()
        except Exception as exc:  # network/parse failures stay explicit
            logger.warning("Literature search failed for %s: %s", source, exc)
            errors[source] = str(exc)

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, records in results.items():
        for record in records:
            key = str(
                record.get("doi")
                or record.get("pmid")
                or record.get("id")
                or record.get("title", "")
            ).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            combined.append({**record, "source": source})

    for source, message in errors.items():
        combined.append(
            {"source": source, "status": "unavailable", "error": message}
        )

    return {
        "query": query,
        "total_results": len(combined),
        "sources_queried": sources,
        "source_errors": errors,
        "results": combined[:limit],
        "retrieved_at": _now(),
    }


class LiteratureSearchTool(Tool):
    """Search scientific literature."""

    def __init__(self):
        spec = ToolSpec(
            name="literature_search",
            description="Search PubMed, Europe PMC, Crossref and OpenAlex for scientific literature",
            category="literature",
            parameters=[
                ToolParameter("query", "string", "Search query", required=True),
                ToolParameter("databases", "array", "Databases to search", required=False, default=["pubmed", "europepmc"], enum=["pubmed", "europepmc", "crossref", "openalex"]),
                ToolParameter("max_results", "number", "Maximum results", required=False, default=20),
                ToolParameter("date_range", "string", "Date range filter (informational; applied upstream)", required=False),
                ToolParameter("article_types", "array", "Article types to include (informational)", required=False),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        return search_literature(
            kwargs.get("query", ""),
            databases=kwargs.get("databases"),
            max_results=kwargs.get("max_results", 20),
        )


class GeneLiteratureTool(Tool):
    """Search literature for specific genes."""

    def __init__(self):
        spec = ToolSpec(
            name="gene_literature",
            description="Find publications associated with specific genes",
            category="literature",
            parameters=[
                ToolParameter("genes", "array", "Gene symbols", required=True),
                ToolParameter("max_per_gene", "number", "Max results per gene", required=False, default=10),
                ToolParameter("include_reviews", "boolean", "Include review articles", required=False, default=True),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        genes = kwargs.get("genes", [])
        if not genes:
            return {"error": "No genes provided"}

        from geneai.research import search_pubmed

        per_gene = max(1, min(int(kwargs.get("max_per_gene", 10)), 100))
        include_reviews = bool(kwargs.get("include_reviews", True))
        results: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for gene in genes:
            gene = str(gene).strip()
            if not gene:
                continue
            query = f"{gene}[Title/Abstract]"
            if not include_reviews:
                query += " AND review[pt] NOT review[pt]"
            try:
                results[gene] = search_pubmed(query, per_gene)
            except Exception as exc:
                logger.warning("Gene literature search failed for %s: %s", gene, exc)
                errors[gene] = str(exc)

        return {
            "genes": genes,
            "results": results,
            "errors": errors,
            "retrieved_at": _now(),
        }


class DiseaseLiteratureTool(Tool):
    """Search literature for diseases."""

    def __init__(self):
        spec = ToolSpec(
            name="disease_literature",
            description="Find publications related to diseases and phenotypes",
            category="literature",
            parameters=[
                ToolParameter("diseases", "array", "Disease names or IDs (OMIM, Orphanet)", required=True),
                ToolParameter("max_per_disease", "number", "Max results per disease", required=False, default=10),
                ToolParameter("include_genetics", "boolean", "Include genetic studies", required=False, default=True),
                ToolParameter("include_trials", "boolean", "Include clinical trials", required=False, default=False),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        diseases = kwargs.get("diseases", [])
        if not diseases:
            return {"error": "No diseases provided"}

        from geneai.research import search_pubmed

        per_disease = max(1, min(int(kwargs.get("max_per_disease", 10)), 100))
        include_genetics = bool(kwargs.get("include_genetics", True))
        include_trials = bool(kwargs.get("include_trials", False))

        results: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for disease in diseases:
            disease = str(disease).strip()
            if not disease:
                continue
            query = f"{disease}[Title/Abstract]"
            if include_genetics:
                query += " AND (genetic[Title/Abstract] OR genomic[Title/Abstract])"
            if include_trials:
                query += " AND clinical trial[pt]"
            try:
                results[disease] = search_pubmed(query, per_disease)
            except Exception as exc:
                logger.warning("Disease literature search failed for %s: %s", disease, exc)
                errors[disease] = str(exc)

        return {
            "diseases": diseases,
            "results": results,
            "errors": errors,
            "retrieved_at": _now(),
        }


def register_literature_tools(registry):
    """Register literature search tools."""
    registry.register(LiteratureSearchTool())
    registry.register(GeneLiteratureTool())
    registry.register(DiseaseLiteratureTool())
