from __future__ import annotations

import logging

import requests

from geneai.config import (
    MAX_PUBMED_QUERY_LENGTH,
    MAX_PUBMED_RESULTS,
    PUBMED_TIMEOUT_SECONDS,
)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HEADERS = {"User-Agent": "GeneAIResearch/0.1 (literature search; contact not configured)"}
logger = logging.getLogger(__name__)


def search_pubmed(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Fetch PubMed titles and citation metadata; no abstracts are summarized."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if len(query) > MAX_PUBMED_QUERY_LENGTH:
        raise ValueError(f"Search query must be {MAX_PUBMED_QUERY_LENGTH} characters or fewer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PUBMED_RESULTS:
        raise ValueError(f"Result limit must be between 1 and {MAX_PUBMED_RESULTS}.")

    try:
        response = requests.get(
            f"{EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": limit,
                "retmode": "json",
                "sort": "relevance",
            },
            headers=HEADERS,
            timeout=PUBMED_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        summary = requests.get(
            f"{EUTILS}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            headers=HEADERS,
            timeout=PUBMED_TIMEOUT_SECONDS,
        )
        summary.raise_for_status()
        payload = summary.json().get("result", {})
    except (requests.RequestException, ValueError, AttributeError) as exc:
        logger.warning("PubMed search failed: %s", exc)
        raise RuntimeError(f"PubMed request failed: {exc}") from exc

    papers = []
    for pmid in ids:
        item = payload.get(pmid, {})
        authors_data = item.get("authors", [])
        authors = ", ".join(author.get("name", "") for author in authors_data[:4])
        if len(authors_data) > 4:
            authors += ", et al."
        papers.append(
            {
                "pmid": pmid,
                "title": item.get("title", "Title not available").rstrip("."),
                "year": item.get("pubdate", "")[:4],
                "journal": item.get("fulljournalname", item.get("source", "")),
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return papers
