"""AI Research Assistant for interactive paper analysis."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AssistantResponse:
    """Response from the research assistant."""
    answer: str
    citations: list[dict[str, Any]] = None
    excerpts: list[str] = None
    confidence: str = "medium"
    evidence_available: bool = True

    def __post_init__(self):
        if self.citations is None:
            self.citations = []
        if self.excerpts is None:
            self.excerpts = []


class ResearchAssistant:
    """Interactive research assistant for paper analysis."""

    def __init__(self, analyzed_papers: list[dict[str, Any]]):
        self.papers = analyzed_papers
        self._build_context()

    def _build_context(self):
        """Build searchable context from papers."""
        self.context = {
            "papers": [],
            "all_text": "",
            "entities": {
                "genes": set(),
                "proteins": set(),
                "diseases": set(),
                "drugs": set(),
                "pathways": set(),
                "mutations": set(),
            },
        }

        for paper in self.papers:
            metadata = paper.get("metadata", {})
            entities = paper.get("entities", {})
            summary = paper.get("summary", {})

            paper_context = {
                "pmid": metadata.get("pmid"),
                "doi": metadata.get("doi"),
                "title": metadata.get("title", ""),
                "abstract": metadata.get("abstract", ""),
                "full_text": metadata.get("full_text", ""),
                "summary": summary,
                "entities": entities,
            }
            self.context["papers"].append(paper_context)

            # Aggregate text
            text_parts = [metadata.get("title", ""), metadata.get("abstract", ""), metadata.get("full_text", "")]
            self.context["all_text"] += " ".join(filter(None, text_parts)) + " "

            # Aggregate entities
            for gene in entities.get("genes", []):
                self.context["entities"]["genes"].add(gene.get("symbol", "").upper())
            for protein in entities.get("proteins", []):
                self.context["entities"]["proteins"].add(protein.get("name", "").upper())
            for disease in entities.get("diseases", []):
                self.context["entities"]["diseases"].add(disease.get("name", "").lower())
            for drug in entities.get("drugs", []):
                self.context["entities"]["drugs"].add(drug.get("name", "").lower())
            for pathway in entities.get("pathways", []):
                self.context["entities"]["pathways"].add(pathway.get("name", "").upper())
            for mutation in entities.get("mutations", []):
                self.context["entities"]["mutations"].add(mutation.get("variant", "").upper())

    def ask(self, question: str) -> AssistantResponse:
        """Answer a research question based on paper content."""
        question_lower = question.lower()

        # Route to appropriate handler
        if any(kw in question_lower for kw in ["main finding", "key finding", "primary result", "main result"]):
            return self._answer_main_findings()
        elif any(kw in question_lower for kw in ["gene", "genes"]):
            return self._answer_genes(question)
        elif any(kw in question_lower for kw in ["protein", "proteins"]):
            return self._answer_proteins(question)
        elif any(kw in question_lower for kw in ["drug", "drugs", "compound", "compounds", "treatment", "therapy"]):
            return self._answer_drugs(question)
        elif any(kw in question_lower for kw in ["disease", "diseases", "condition", "disorder"]):
            return self._answer_diseases(question)
        elif any(kw in question_lower for kw in ["limitation", "limitations", "weakness", "caveat"]):
            return self._answer_limitations()
        elif any(kw in question_lower for kw in ["gap", "gaps", "future", "future work", "next step", "unanswered"]):
            return self._answer_gaps()
        elif any(kw in question_lower for kw in ["method", "methodology", "approach", "technique", "experiment"]):
            return self._answer_methodology()
        elif any(kw in question_lower for kw in ["conclusion", "conclude", "implication"]):
            return self._answer_conclusions()
        else:
            return self._answer_general(question)

    def _answer_main_findings(self) -> AssistantResponse:
        """Answer about main findings."""
        findings = []
        citations = []
        excerpts = []

        for paper in self.context["papers"]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            summary = paper.get("summary", {})

            for finding in summary.get("key_findings", []) + summary.get("results", []):
                findings.append(finding)
                citations.append({"pmid": pmid, "doi": doi, "title": title})
                excerpts.append(finding[:200])

            if not findings and summary.get("conclusions"):
                for conc in summary.get("conclusions", [])[:2]:
                    findings.append(conc)
                    citations.append({"pmid": pmid, "doi": doi, "title": title})
                    excerpts.append(conc[:200])

        if not findings:
            return AssistantResponse(
                answer="No specific findings could be extracted from the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = "Main findings across the analyzed papers:\n\n" + "\n\n".join(
            f"{i+1}. {f}" for i, f in enumerate(findings[:10])
        )
        return AssistantResponse(
            answer=answer,
            citations=citations[:10],
            excerpts=excerpts[:10],
            confidence="high",
            evidence_available=True,
        )

    def _answer_genes(self, question: str) -> AssistantResponse:
        """Answer about genes."""
        genes = sorted(self.context["entities"]["genes"])
        gene_details = []

        for paper in self.context["papers"]:
            for gene in paper.get("entities", {}).get("genes", []):
                symbol = gene.get("symbol", "")
                if symbol:
                    gene_details.append({
                        "gene": symbol,
                        "paper_title": paper.get("title", ""),
                        "pmid": paper.get("pmid"),
                        "doi": paper.get("doi"),
                        "context": gene.get("source_text", ""),
                    })

        if not gene_details:
            return AssistantResponse(
                answer="No genes were identified in the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        # Filter by question if specific gene mentioned
        question_upper = question.upper()
        if any(g in question_upper for g in genes):
            gene_details = [g for g in gene_details if g["gene"] in question_upper]

        answer = f"Genes identified in the analyzed papers ({len(genes)} unique):\n\n"
        for g in gene_details[:15]:
            answer += f"- **{g['gene']}**: Mentioned in \"{g['paper_title'][:60]}...\" (PMID: {g['pmid'] or 'N/A'})\n"

        citations = [{"pmid": g["pmid"], "doi": g["doi"], "title": g["paper_title"]} for g in gene_details[:15]]
        excerpts = [g["context"][:200] for g in gene_details[:15]]

        return AssistantResponse(
            answer=answer,
            citations=citations,
            excerpts=excerpts,
            confidence="high",
            evidence_available=True,
        )

    def _answer_proteins(self, question: str) -> AssistantResponse:
        """Answer about proteins."""
        proteins = sorted(self.context["entities"]["proteins"])
        protein_details = []

        for paper in self.context["papers"]:
            for protein in paper.get("entities", {}).get("proteins", []):
                name = protein.get("name", "")
                if name:
                    protein_details.append({
                        "protein": name,
                        "paper_title": paper.get("title", ""),
                        "pmid": paper.get("pmid"),
                        "doi": paper.get("doi"),
                        "context": protein.get("source_text", ""),
                    })

        if not protein_details:
            return AssistantResponse(
                answer="No proteins were identified in the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = f"Proteins identified in the analyzed papers ({len(proteins)} unique):\n\n"
        for p in protein_details[:15]:
            answer += f"- **{p['protein']}**: Mentioned in \"{p['paper_title'][:60]}...\" (PMID: {p['pmid'] or 'N/A'})\n"

        citations = [{"pmid": p["pmid"], "doi": p["doi"], "title": p["paper_title"]} for p in protein_details[:15]]
        excerpts = [p["context"][:200] for p in protein_details[:15]]

        return AssistantResponse(
            answer=answer,
            citations=citations,
            excerpts=excerpts,
            confidence="medium",
            evidence_available=True,
        )

    def _answer_drugs(self, question: str) -> AssistantResponse:
        """Answer about drugs."""
        drugs = sorted(self.context["entities"]["drugs"])
        drug_details = []

        for paper in self.context["papers"]:
            for drug in paper.get("entities", {}).get("drugs", []):
                name = drug.get("name", "")
                if name:
                    drug_details.append({
                        "drug": name,
                        "paper_title": paper.get("title", ""),
                        "pmid": paper.get("pmid"),
                        "doi": paper.get("doi"),
                        "context": drug.get("source_text", ""),
                    })

            # Also check drug-target relationships
            for rel in paper.get("drug_target_relationships", []):
                drug_details.append({
                    "drug": rel.get("drug_name", ""),
                    "target": rel.get("target_name", ""),
                    "relationship": rel.get("relationship_type", ""),
                    "paper_title": paper.get("title", ""),
                    "pmid": paper.get("pmid"),
                    "doi": paper.get("doi"),
                    "context": rel.get("source_text", ""),
                })

        if not drug_details:
            return AssistantResponse(
                answer="No drugs or compounds were identified in the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = f"Drugs/Compounds identified in the analyzed papers ({len(drugs)} unique):\n\n"
        for d in drug_details[:15]:
            target_info = f" → targets **{d['target']}** ({d['relationship']})" if d.get("target") else ""
            answer += f"- **{d['drug']}**{target_info}: Mentioned in \"{d['paper_title'][:60]}...\" (PMID: {d['pmid'] or 'N/A'})\n"

        citations = [{"pmid": d["pmid"], "doi": d["doi"], "title": d["paper_title"]} for d in drug_details[:15]]
        excerpts = [d["context"][:200] for d in drug_details[:15]]

        return AssistantResponse(
            answer=answer,
            citations=citations,
            excerpts=excerpts,
            confidence="medium",
            evidence_available=True,
        )

    def _answer_diseases(self, question: str) -> AssistantResponse:
        """Answer about diseases."""
        diseases = sorted(self.context["entities"]["diseases"])
        disease_details = []

        for paper in self.context["papers"]:
            for disease in paper.get("entities", {}).get("diseases", []):
                name = disease.get("name", "")
                if name:
                    disease_details.append({
                        "disease": name,
                        "paper_title": paper.get("title", ""),
                        "pmid": paper.get("pmid"),
                        "doi": paper.get("doi"),
                        "context": disease.get("source_text", ""),
                    })

        if not disease_details:
            return AssistantResponse(
                answer="No diseases were identified in the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = f"Diseases/Conditions identified in the analyzed papers ({len(diseases)} unique):\n\n"
        for d in disease_details[:15]:
            answer += f"- **{d['disease']}**: Mentioned in \"{d['paper_title'][:60]}...\" (PMID: {d['pmid'] or 'N/A'})\n"

        citations = [{"pmid": d["pmid"], "doi": d["doi"], "title": d["paper_title"]} for d in disease_details[:15]]
        excerpts = [d["context"][:200] for d in disease_details[:15]]

        return AssistantResponse(
            answer=answer,
            citations=citations,
            excerpts=excerpts,
            confidence="medium",
            evidence_available=True,
        )

    def _answer_limitations(self) -> AssistantResponse:
        """Answer about limitations."""
        limitations = []
        citations = []
        excerpts = []

        for paper in self.context["papers"]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            summary = paper.get("summary", {})

            for lim in summary.get("limitations", []):
                limitations.append(lim)
                citations.append({"pmid": pmid, "doi": doi, "title": title})
                excerpts.append(lim[:200])

        if not limitations:
            return AssistantResponse(
                answer="No explicit limitations were mentioned in the analyzed papers.",
                confidence="medium",
                evidence_available=False,
            )

        answer = "Limitations reported in the analyzed papers:\n\n" + "\n\n".join(
            f"{i+1}. {l}" for i, l in enumerate(limitations[:10])
        )
        return AssistantResponse(
            answer=answer,
            citations=citations[:10],
            excerpts=excerpts[:10],
            confidence="high",
            evidence_available=True,
        )

    def _answer_gaps(self) -> AssistantResponse:
        """Answer about research gaps."""
        future_work = []
        citations = []

        for paper in self.context["papers"]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            summary = paper.get("summary", {})

            for fw in summary.get("future_work", []):
                future_work.append(fw)
                citations.append({"pmid": pmid, "doi": doi, "title": title})

        if not future_work:
            return AssistantResponse(
                answer="No explicit future work or research gaps were mentioned in the analyzed papers.",
                confidence="medium",
                evidence_available=False,
            )

        answer = "Research gaps and future directions mentioned in the papers:\n\n" + "\n\n".join(
            f"{i+1}. {fw}" for i, fw in enumerate(future_work[:10])
        )
        return AssistantResponse(
            answer=answer,
            citations=citations[:10],
            excerpts=future_work[:10],
            confidence="high",
            evidence_available=True,
        )

    def _answer_methodology(self) -> AssistantResponse:
        """Answer about methodology."""
        methods = []
        citations = []
        excerpts = []

        for paper in self.context["papers"]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            summary = paper.get("summary", {})

            for method in summary.get("methodology", []):
                methods.append(method)
                citations.append({"pmid": pmid, "doi": doi, "title": title})
                excerpts.append(method[:200])

            # Also include experimental models and statistical methods
            for model in summary.get("experimental_models", []):
                methods.append(f"Experimental model: {model}")
                citations.append({"pmid": pmid, "doi": doi, "title": title})

            for stat in summary.get("statistical_methods", []):
                methods.append(f"Statistical method: {stat}")
                citations.append({"pmid": pmid, "doi": doi, "title": title})

        if not methods:
            return AssistantResponse(
                answer="No methodology details could be extracted from the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = "Methodologies used in the analyzed papers:\n\n" + "\n\n".join(
            f"{i+1}. {m}" for i, m in enumerate(methods[:15])
        )
        return AssistantResponse(
            answer=answer,
            citations=citations[:15],
            excerpts=excerpts[:15],
            confidence="high",
            evidence_available=True,
        )

    def _answer_conclusions(self) -> AssistantResponse:
        """Answer about conclusions."""
        conclusions = []
        citations = []
        excerpts = []

        for paper in self.context["papers"]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            summary = paper.get("summary", {})

            for conc in summary.get("conclusions", []):
                conclusions.append(conc)
                citations.append({"pmid": pmid, "doi": doi, "title": title})
                excerpts.append(conc[:200])

        if not conclusions:
            return AssistantResponse(
                answer="No explicit conclusions could be extracted from the analyzed papers.",
                confidence="low",
                evidence_available=False,
            )

        answer = "Conclusions from the analyzed papers:\n\n" + "\n\n".join(
            f"{i+1}. {c}" for i, c in enumerate(conclusions[:10])
        )
        return AssistantResponse(
            answer=answer,
            citations=citations[:10],
            excerpts=excerpts[:10],
            confidence="high",
            evidence_available=True,
        )

    def _answer_general(self, question: str) -> AssistantResponse:
        """Answer general questions using keyword search."""
        # Simple keyword-based search in paper content
        keywords = [w for w in question.lower().split() if len(w) > 3]
        matches = []

        for paper in self.context["papers"]:
            text = " ".join(filter(None, [
                paper.get("title", ""),
                paper.get("abstract", ""),
                paper.get("full_text", ""),
            ])).lower()

            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                matches.append((score, paper))

        matches.sort(reverse=True, key=lambda x: x[0])

        if not matches:
            return AssistantResponse(
                answer=f"No relevant information found for your question: \"{question}\"",
                confidence="low",
                evidence_available=False,
            )

        answer = f"Based on the analyzed papers, here's what I found for: \"{question}\"\n\n"
        citations = []
        excerpts = []

        for score, paper in matches[:5]:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            title = paper.get("title", "")
            abstract = paper.get("abstract", "") or paper.get("full_text", "")

            # Find relevant excerpt
            sentences = re.split(r'(?<=[.!?])\s+', abstract)
            relevant = []
            for sent in sentences:
                if any(kw in sent.lower() for kw in keywords):
                    relevant.append(sent.strip())
                    if len(relevant) >= 3:
                        break

            if relevant:
                answer += f"**{title[:80]}...** (PMID: {pmid or 'N/A'})\n"
                for r in relevant:
                    answer += f"- {r}\n"
                answer += "\n"

            citations.append({"pmid": pmid, "doi": doi, "title": title})
            excerpts.extend(relevant[:3])

        return AssistantResponse(
            answer=answer,
            citations=citations,
            excerpts=excerpts[:10],
            confidence="medium",
            evidence_available=True,
        )


def create_research_assistant(analyzed_papers: list[dict[str, Any]]) -> ResearchAssistant:
    """Factory function to create a research assistant."""
    return ResearchAssistant(analyzed_papers)