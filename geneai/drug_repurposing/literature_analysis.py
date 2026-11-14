"""Literature analysis module for PubMed integration in drug repurposing."""
from __future__ import annotations

import logging
from typing import Any

from geneai.drug_discovery import api_clients
from geneai.drug_discovery.cache import ttl_cache

logger = logging.getLogger(__name__)

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_EMAIL = "geneai.research@example.com"
_TOOL = "GeneAIResearch"


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_pubmed_for_drug_disease(
    drug_name: str,
    disease_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search PubMed for drug-disease specific publications."""
    if not drug_name or not disease_name:
        return []

    query = f'"{drug_name}"[Title/Abstract] AND "{disease_name}"[Title/Abstract]'
    return _search_pubmed(query, limit)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_pubmed_for_drug_target(
    drug_name: str,
    target_symbol: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search PubMed for drug-target specific publications."""
    if not drug_name or not target_symbol:
        return []

    query = f'"{drug_name}"[Title/Abstract] AND "{target_symbol}"[Title/Abstract]'
    return _search_pubmed(query, limit)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_pubmed_for_target_disease(
    target_symbol: str,
    disease_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search PubMed for target-disease specific publications."""
    if not target_symbol or not disease_name:
        return []

    query = f'"{target_symbol}"[Title/Abstract] AND "{disease_name}"[Title/Abstract]'
    return _search_pubmed(query, limit)


@ttl_cache(ttl_seconds=86_400, max_entries=128)
def search_pubmed_for_repurposing(
    drug_name: str,
    disease_name: str,
    target_symbol: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Comprehensive PubMed search for repurposing evidence."""
    queries = []

    # Primary: drug + disease
    queries.append(f'"{drug_name}"[Title/Abstract] AND "{disease_name}"[Title/Abstract]')

    # Drug + target if available
    if target_symbol:
        queries.append(f'"{drug_name}"[Title/Abstract] AND "{target_symbol}"[Title/Abstract]')
        queries.append(f'"{target_symbol}"[Title/Abstract] AND "{disease_name}"[Title/Abstract]')

    # Broader search
    queries.append(f'("{drug_name}" OR "{target_symbol or ""}") AND "{disease_name}" AND (repurposing OR repositioning)')

    all_results = []
    seen_pmids = set()

    for query in queries:
        results = _search_pubmed(query, limit=10)
        for r in results:
            pmid = r.get("pmid")
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                all_results.append(r)

        if len(all_results) >= limit:
            break

    return all_results[:limit]


def _search_pubmed(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Internal PubMed search function."""
    import requests
    from geneai.drug_discovery import api_clients

    def _request(method: str, url: str, **kwargs: Any) -> tuple[requests.Response, Any]:
        headers = {"User-Agent": f"{_TOOL}/0.2 (mailto:{_EMAIL})"}
        try:
            response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise api_clients.DataSourceError(f"NCBI request failed: {exc}") from exc
        response.raise_for_status()
        return response, response.text

    try:
        # Search for IDs
        _, search_text = _request(
            "GET",
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": min(limit, 100),
                "retmode": "json",
                "email": _EMAIL,
                "tool": _TOOL,
            },
            expect_json=False,
        )
    except api_clients.DataSourceError:
        return []

    import json
    try:
        search_payload = json.loads(search_text)
    except json.JSONDecodeError:
        return []

    id_list = search_payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    # Fetch details
    try:
        _, fetch_text = _request(
            "GET",
            f"{NCBI_EUTILS}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(id_list[:limit]),
                "retmode": "xml",
                "email": _EMAIL,
                "tool": _TOOL,
            },
            expect_json=False,
        )
    except api_clients.DataSourceError:
        return []

    return _parse_pubmed_xml(fetch_text, limit)


def _parse_pubmed_xml(xml_text: str, limit: int) -> list[dict[str, Any]]:
    """Parse PubMed XML response."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    results = []
    for article in root.findall(".//PubmedArticle"):
        if len(results) >= limit:
            break

        pmid = article.findtext(".//PMID")
        title = article.findtext(".//ArticleTitle")

        # Authors
        authors = []
        for author in article.findall(".//Author"):
            lastname = author.findtext("LastName")
            fore = author.findtext("ForeName")
            if lastname:
                name = lastname
                if fore:
                    name += f" {fore[0]}."
                authors.append(name)

        # Journal
        journal = article.findtext(".//Journal/Title") or article.findtext(".//Journal/ISOAbbreviation")

        # Publication date
        pub_date = ""
        pub_date_elem = article.find(".//PubDate")
        if pub_date_elem is not None:
            year = pub_date_elem.findtext("Year")
            month = pub_date_elem.findtext("Month")
            day = pub_date_elem.findtext("Day")
            parts = [p for p in [year, month, day] if p]
            pub_date = " ".join(parts)

        # Abstract
        abstract = ""
        abstract_elem = article.find(".//Abstract")
        if abstract_elem is not None:
            sections = []
            for node in abstract_elem.findall(".//AbstractText"):
                label = node.attrib.get("Label") or node.attrib.get("NlmCategory")
                value = " ".join("".join(node.itertext()).split())
                if value:
                    sections.append(f"{label}: {value}" if label else value)
            abstract = " ".join(sections)

        # DOI
        doi = ""
        for id_elem in article.findall(".//ArticleId"):
            if id_elem.attrib.get("IdType") == "doi":
                doi = id_elem.text
                break

        if pmid and title:
            results.append({
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal,
                "pub_date": pub_date,
                "abstract": abstract[:2000] if abstract else "",  # Truncate long abstracts
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "PubMed",
            })

    return results


@ttl_cache(ttl_seconds=86_400, max_entries=64)
def get_publication_details(pmids: list[str]) -> dict[str, dict[str, Any]]:
    """Get detailed publication information for a list of PMIDs."""
    if not pmids:
        return {}

    import requests
    from geneai.drug_discovery import api_clients

    def _request(method: str, url: str, **kwargs: Any) -> tuple[requests.Response, Any]:
        headers = {"User-Agent": f"{_TOOL}/0.2 (mailto:{_EMAIL})"}
        try:
            response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise api_clients.DataSourceError(f"NCBI request failed: {exc}") from exc
        response.raise_for_status()
        return response, response.text

    try:
        _, fetch_text = _request(
            "GET",
            f"{NCBI_EUTILS}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids[:100]),
                "retmode": "xml",
                "email": _EMAIL,
                "tool": _TOOL,
            },
            expect_json=False,
        )
    except api_clients.DataSourceError:
        return {}

    parsed = _parse_pubmed_xml(fetch_text, len(pmids))
    return {p["pmid"]: p for p in parsed}


def extract_drug_findings(
    publications: list[dict[str, Any]],
    drug_name: str,
    disease_name: str | None = None,
) -> list[dict[str, Any]]:
    """Extract drug-related findings from publications."""
    findings = []
    drug_lower = drug_name.lower()
    disease_lower = disease_name.lower() if disease_name else None

    for pub in publications:
        title = pub.get("title", "").lower()
        abstract = pub.get("abstract", "").lower()

        # Check if drug is mentioned
        if drug_lower in title or drug_lower in abstract:
            finding = {
                "pmid": pub.get("pmid"),
                "title": pub.get("title"),
                "journal": pub.get("journal"),
                "pub_date": pub.get("pub_date"),
                "url": pub.get("url"),
                "relevance": "high" if drug_lower in title else "medium",
            }

            # Extract key sentences mentioning the drug
            sentences = _extract_relevant_sentences(abstract, drug_lower, disease_lower)
            finding["key_sentences"] = sentences[:5]

            # Classify finding type
            finding["finding_type"] = _classify_finding(title, abstract, disease_lower)
            finding["evidence_level"] = _assess_evidence_level(finding["finding_type"], finding["relevance"])

            findings.append(finding)

    return findings


def _extract_relevant_sentences(
    text: str,
    drug_term: str,
    disease_term: str | None,
) -> list[str]:
    """Extract sentences mentioning drug and optionally disease."""
    import re
    sentences = re.split(r'[.!?]+', text)
    relevant = []

    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 20:
            continue
        sent_lower = sent.lower()
        if drug_term in sent_lower:
            if disease_term is None or disease_term in sent_lower:
                relevant.append(sent)

    return relevant


def _classify_finding(title: str, abstract: str, disease_term: str | None) -> str:
    """Classify the type of finding."""
    text = f"{title} {abstract}".lower()

    if any(kw in text for kw in ["clinical trial", "phase i", "phase ii", "phase iii", "phase iv", "randomized", "controlled trial"]):
        return "clinical_trial"
    elif any(kw in text for kw in ["case report", "case series", "patient"]):
        return "case_report"
    elif any(kw in text for kw in ["in vitro", "cell line", "cultured cells"]):
        return "in_vitro"
    elif any(kw in text for kw in ["in vivo", "mouse model", "animal model", "xenograft"]):
        return "in_vivo"
    elif any(kw in text for kw in ["mechanism", "pathway", "signaling", "binding", "inhibition", "activation"]):
        return "mechanistic"
    elif any(kw in text for kw in ["review", "meta-analysis", "systematic review"]):
        return "review"
    elif disease_term and disease_term in text:
        return "disease_association"
    else:
        return "general"


def _assess_evidence_level(finding_type: str, relevance: str) -> str:
    """Assess evidence level for a finding."""
    if finding_type == "clinical_trial":
        return "clinical"
    elif finding_type in ("in_vivo", "in_vitro", "mechanistic"):
        return "experimental"
    elif finding_type == "case_report":
        return "clinical_observation"
    elif finding_type == "review":
        return "literature_review"
    else:
        return "computational" if relevance == "high" else "literature"


def build_literature_evidence_summary(
    drug_name: str,
    disease_name: str | None = None,
    target_symbol: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Build comprehensive literature evidence summary for a repurposing candidate."""
    # Search publications
    publications = search_pubmed_for_repurposing(drug_name, disease_name or "", target_symbol, limit)

    # Extract findings
    findings = extract_drug_findings(publications, drug_name, disease_name)

    # Count by type and evidence level
    type_counts = {}
    evidence_counts = {}
    for f in findings:
        ftype = f.get("finding_type", "unknown")
        elevel = f.get("evidence_level", "unknown")
        type_counts[ftype] = type_counts.get(ftype, 0) + 1
        evidence_counts[elevel] = evidence_counts.get(elevel, 0) + 1

    # Get top relevant publications
    top_pubs = sorted(findings, key=lambda x: (x.get("relevance") == "high", x.get("evidence_level")), reverse=True)[:10]

    return {
        "drug_name": drug_name,
        "disease_name": disease_name,
        "target_symbol": target_symbol,
        "total_publications": len(publications),
        "relevant_findings": len(findings),
        "finding_types": type_counts,
        "evidence_levels": evidence_counts,
        "top_findings": top_pubs,
        "all_publications": publications[:limit],
        "limitations": [
            "Publication search limited to title/abstract matching",
            "May miss relevant publications using different terminology",
            "Evidence level classification is heuristic",
            "Does not assess study quality or bias",
            "Negative results are underrepresented in literature",
        ],
    }