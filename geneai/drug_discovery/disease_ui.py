"""Streamlit interface for disease, gene, protein, pathway, and literature research."""
from __future__ import annotations

import json
import logging
import math
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from geneai.agents.disease_analysis_agent import DiseaseAnalysisRequest, run_disease_analysis_agent
from geneai.drug_discovery import api_clients
from geneai.drug_discovery.disease_analysis import (
    DEFAULT_PRIORITY_WEIGHTS,
    answer_research_question,
    extract_vcf_gene_references,
    search_diseases,
)
from geneai.drug_discovery.reports import (
    disease_report_csv,
    disease_report_json,
    disease_report_pdf,
    report_filename,
)

logger = logging.getLogger(__name__)
DISEASE_CATEGORIES = [
    "Cancer",
    "Genetic disorders",
    "Neurological diseases",
    "Cardiovascular diseases",
    "Metabolic diseases",
    "Infectious diseases",
    "Autoimmune diseases",
    "Rare diseases",
    "Other / not specified",
]


def render_disease_analysis_page() -> None:
    """Render the single sequential Disease Analysis Agent workflow."""
    st.subheader("Disease Analysis")
    st.write(
        "Search source-linked disease, gene, protein, pathway, and publication evidence. "
        "This workspace organizes retrieved research; it does not diagnose or recommend treatment."
    )
    st.info(
        "Open Targets scores are evidence-aggregation rankings. The configurable research index is a heuristic, "
        "not a confidence, druggability, or clinical score."
    )

    vcf_result = st.session_state.get("mutation_vcf_result") or {}
    vcf_preview = vcf_result.get("preview", []) if isinstance(vcf_result, dict) else []
    vcf_genes = extract_vcf_gene_references(vcf_preview)
    if vcf_genes:
        st.caption(f"Phase 3 VCF preview is available with {len(vcf_genes)} source-annotated gene symbols.")

    with st.form("disease_search_form"):
        left, right = st.columns([2, 1], vertical_alignment="bottom")
        with left:
            disease_query = st.text_input(
                "Disease name",
                placeholder="e.g. cystic fibrosis or pancreatic cancer",
                key="disease_query",
            )
        with right:
            category = st.selectbox(
                "Research category",
                DISEASE_CATEGORIES,
                key="disease_category",
            )
        disease_id = st.text_input(
            "Disease ID (optional, Open Targets identifier)",
            placeholder="e.g. MONDO_0009061",
            key="disease_id_input",
        )
        gene_col, id_col = st.columns(2)
        with gene_col:
            gene_symbols = st.text_input(
                "Gene symbol(s), optional",
                placeholder="CFTR, TP53",
                key="disease_gene_symbols",
            )
        with id_col:
            gene_ids = st.text_input(
                "NCBI Gene ID or Ensembl ID(s), optional",
                placeholder="1080, ENSG00000001626",
                key="disease_gene_ids",
            )
        mutation_id = st.text_input(
            "Mutation / variant identifier, optional",
            placeholder="rsID, ClinVar ID, or HGVS as a literature search term",
            key="disease_mutation_id",
        )
        protein_id = st.text_input(
            "UniProt protein ID, optional",
            placeholder="e.g. P13569",
            key="disease_protein_id",
        )
        keywords = st.text_input(
            "Research keywords, optional",
            placeholder="e.g. mechanism, loss of function, treatment resistance",
            key="disease_keywords",
        )
        use_vcf = st.checkbox(
            "Include source gene symbols from the current Phase 3 VCF preview",
            value=bool(vcf_genes),
            disabled=not bool(vcf_genes),
            key="disease_use_vcf",
        )
        target_limit = st.slider("Maximum associated targets to retrieve", 5, 50, 20, 5, key="disease_target_limit")
        searched = st.form_submit_button("Find disease", type="primary")

    if searched:
        st.session_state.pop("disease_search_hits", None)
        st.session_state.pop("disease_search_error", None)
        st.session_state.pop("disease_analysis_result", None)
        st.session_state.pop("disease_rag_answer", None)
        st.session_state["disease_search_inputs"] = {
            "disease_query": disease_query.strip(),
            "disease_category": category,
            "disease_id": disease_id.strip(),
            "gene_identifiers": ",".join(value for value in (gene_symbols, gene_ids) if value.strip()),
            "mutation_id": mutation_id.strip(),
            "protein_id": protein_id.strip(),
            "research_keywords": keywords.strip(),
            "use_vcf": bool(use_vcf),
            "target_limit": int(target_limit),
            "vcf_preview": vcf_preview if use_vcf else [],
        }
        try:
            if disease_id.strip():
                if not api_clients.is_valid_external_id(disease_id):
                    raise ValueError("Disease ID contains unsupported characters.")
                hits = [
                    {
                        "disease_id": disease_id.strip(),
                        "name": disease_query.strip() or disease_id.strip(),
                        "categories": [],
                        "source": "Open Targets Platform",
                        "url": f"https://platform.opentargets.org/disease/{disease_id.strip()}/associations",
                    }
                ]
            else:
                hits = search_diseases(disease_query)
            st.session_state["disease_search_hits"] = hits
        except (ValueError, api_clients.DataSourceError) as exc:
            logger.info("Disease search was not completed: %s", exc)
            st.session_state["disease_search_error"] = str(exc)

    if st.session_state.get("disease_search_error"):
        st.error(st.session_state["disease_search_error"])
    hits = st.session_state.get("disease_search_hits", [])
    if hits:
        st.subheader("Select a disease record")
        labels = {
            item["disease_id"]: f"{item['name']} · {item['disease_id']}"
            for item in hits
        }
        selected_id = st.selectbox(
            "Matching disease records",
            options=list(labels),
            format_func=lambda value: labels.get(value, value),
            key="selected_disease_record",
            help="Start typing in this list to narrow the source database suggestions.",
        )
        selected = next(item for item in hits if item["disease_id"] == selected_id)
        if selected.get("categories"):
            st.caption("Open Targets categories: " + ", ".join(selected["categories"]))
        st.link_button("Open source disease record", selected["url"])

        with st.expander("Research-priority evidence weights", expanded=False):
            st.caption(
                "The index averages available Open Targets evidence-domain scores using these weights. "
                "Missing domains are reported and excluded; no missing value is treated as zero."
            )
            weights: dict[str, float] = {}
            weight_keys = list(DEFAULT_PRIORITY_WEIGHTS)
            for start in range(0, len(weight_keys), 3):
                cols = st.columns(3)
                for col, key in zip(cols, weight_keys[start:start + 3]):
                    with col:
                        weights[key] = st.slider(
                            key.replace("_", " ").title(),
                            min_value=0.0,
                            max_value=5.0,
                            value=float(st.session_state.get(f"weight_{key}", 1.0)),
                            step=0.5,
                            key=f"weight_{key}",
                        )
        if not weights:
            weights = dict(DEFAULT_PRIORITY_WEIGHTS)

        if st.button("Analyze disease and retrieve evidence", type="primary", key="run_disease_analysis"):
            inputs = st.session_state.get("disease_search_inputs", {})
            request = DiseaseAnalysisRequest(
                disease_id=selected_id,
                disease_category=inputs.get("disease_category", "Not specified"),
                gene_identifiers=inputs.get("gene_identifiers", ""),
                mutation_id=inputs.get("mutation_id", ""),
                protein_id=inputs.get("protein_id", ""),
                research_keywords=inputs.get("research_keywords", ""),
                target_limit=inputs.get("target_limit", 20),
                priority_weights=weights,
                vcf_preview=inputs.get("vcf_preview", []),
            )
            st.session_state.pop("disease_analysis_result", None)
            st.session_state.pop("disease_rag_answer", None)
            try:
                with st.spinner("Retrieving gene, protein, pathway, and publication evidence from public databases…"):
                    result = run_disease_analysis_agent(request, persist=True)
                st.session_state["disease_analysis_result"] = result
            except (ValueError, api_clients.DataSourceError) as exc:
                st.error(str(exc))

    result = st.session_state.get("disease_analysis_result")
    if isinstance(result, dict):
        _render_analysis_results(result)


def _render_analysis_results(result: dict[str, Any]) -> None:
    disease = result.get("disease") or {}
    genes = result.get("genes", [])
    proteins = result.get("proteins", [])
    pathways = result.get("pathways", {}).get("pathways", [])
    papers = result.get("publications", [])
    significant_pathways = sum(
        isinstance(row.get("fdr"), (int, float)) and row["fdr"] <= 0.05
        for row in pathways
    )
    st.divider()
    st.subheader(f"Disease overview: {disease.get('name', 'Selected disease')}")
    with st.container(horizontal=True):
        st.metric("Associated genes", len(genes), border=True)
        st.metric("Reviewed proteins", len(proteins), border=True)
        st.metric("Reactome pathways", len(pathways), border=True)
        st.metric("Pathways with FDR ≤ 0.05", significant_pathways, border=True)
        st.metric("PubMed records", len(papers), border=True)
    st.caption(
        f"Disease ID: {disease.get('disease_id')} · Analysis: {result.get('analysis_id')} · "
        f"Retrieved: {result.get('retrieved_at')} · Database save: {result.get('storage', {}).get('status', 'not reported')}"
    )

    overview_tab, genes_tab, proteins_tab, pathways_tab, literature_tab, report_tab = st.tabs(
        ["Overview & sources", "Genes & targets", "Proteins & structures", "Pathways & GO", "Publications & assistant", "Reports"]
    )
    with overview_tab:
        st.write(disease.get("description") or "The selected source did not return a disease description.")
        st.markdown("**Therapeutic areas:** " + (", ".join(area.get("name", "") for area in disease.get("therapeutic_areas", [])) or "Not provided"))
        st.link_button("Open disease record in Open Targets", disease.get("source_url", "https://platform.opentargets.org/"))
        if result.get("storage", {}).get("status") == "unavailable":
            st.warning("Analysis results are available for this session, but SQLite could not save the snapshot.")
        st.subheader("Data source status")
        source_frame = pd.DataFrame(
            [
                {
                    "Source": item.get("source"),
                    "Status": item.get("status"),
                    "Version": item.get("version", "not reported"),
                    "Records": item.get("record_count", 0),
                    "Details": item.get("error") or item.get("reason", ""),
                }
                for item in result.get("data_sources", [])
            ]
        )
        st.dataframe(source_frame, hide_index=True, alt="Source status, version, and retrieved record counts")
        if result.get("limitations"):
            st.subheader("Limitations and missing evidence")
            for limitation in result["limitations"]:
                st.markdown(f"- {limitation}")
        st.caption(result.get("research_only_disclaimer", "Research use only."))

    with genes_tab:
        st.caption(result.get("priority_method", "Research priority is a heuristic, not clinical evidence."))
        if genes:
            query = st.text_input("Filter genes by symbol, name, or identifier", key="disease_gene_filter")
            filtered = [
                gene for gene in genes
                if not query.strip()
                or query.casefold() in " ".join(str(gene.get(key, "")) for key in (
                    "gene_symbol", "gene_name", "ncbi_gene_id", "ensembl_gene_id"
                )).casefold()
            ]
            gene_frame = pd.DataFrame(
                [
                    {
                        "Gene": gene.get("gene_symbol"),
                        "Name": gene.get("gene_name"),
                        "Function summary": gene.get("gene_function_summary") or "Not provided by NCBI Gene",
                        "NCBI Gene ID": gene.get("ncbi_gene_id") or "Unavailable",
                        "Ensembl Gene ID": gene.get("ensembl_gene_id") or "Unavailable",
                        "Chromosome": gene.get("chromosome") or "Unavailable",
                        "Canonical transcript": gene.get("canonical_transcript") or "Unavailable",
                        "OT association score": gene.get("association_score"),
                        "Research index": gene.get("research_priority_index"),
                        "Shortlist": gene.get("research_priority_tier"),
                        "Evidence domains": ", ".join(sorted(gene.get("datatype_scores", {}))),
                        "Evidence component scores": json.dumps(gene.get("priority_components", {}), ensure_ascii=False),
                        "Missing evidence domains": ", ".join(gene.get("priority_missing_domains", [])),
                        "Evidence sources": ", ".join(gene.get("evidence_sources", [])),
                        "Open Targets record": gene.get("source_url"),
                    }
                    for gene in filtered
                ]
            )
            st.dataframe(
                gene_frame,
                hide_index=True,
                alt="Disease-associated genes and source evidence scores",
                column_config={
                    "Open Targets record": st.column_config.LinkColumn("Open Targets record"),
                },
            )
            if filtered:
                chart_frame = pd.DataFrame(
                    [
                        {"Gene": gene.get("gene_symbol"), "Research index": gene.get("research_priority_index")}
                        for gene in filtered[:20]
                        if gene.get("research_priority_index") is not None
                    ]
                )
                if not chart_frame.empty:
                    st.plotly_chart(
                        px.bar(chart_frame, x="Gene", y="Research index", title="Configurable research shortlist index"),
                        key="disease_target_priority_chart",
                    )
                chosen = st.multiselect(
                    "Compare selected genes",
                    options=[gene.get("gene_symbol") for gene in filtered],
                    max_selections=5,
                    key="compare_disease_genes",
                )
                if chosen:
                    st.dataframe(
                        pd.DataFrame([gene for gene in filtered if gene.get("gene_symbol") in chosen]),
                        hide_index=True,
                        alt="Selected gene evidence comparison",
                    )
        else:
            st.info("No associated gene matched the current input filters and selected Open Targets page.")

    with proteins_tab:
        if proteins:
            protein_frame = pd.DataFrame(
                [
                    {
                        "Gene": protein.get("gene_symbol"),
                        "Protein": protein.get("protein_name"),
                        "UniProt ID": protein.get("uniprot_id"),
                        "Length (aa)": protein.get("sequence_length"),
                        "Domains returned": len(protein.get("domains", [])),
                        "Subcellular location": protein.get("subcellular_location") or "Not annotated",
                        "PDB references in UniProt": ", ".join(protein.get("pdb_ids_from_uniprot", [])),
                    }
                    for protein in proteins
                ]
            )
            st.dataframe(protein_frame, hide_index=True, alt="Disease-associated protein annotations retrieved from UniProt")
            for protein in proteins:
                with st.expander(f"{protein.get('gene_symbol')} · {protein.get('protein_name')} · {protein.get('uniprot_id')}"):
                    st.write(protein.get("function") or "UniProt function comment unavailable.")
                    if protein.get("domains"):
                        st.dataframe(pd.DataFrame(protein["domains"]), hide_index=True, alt="Protein domains returned by UniProt")
                    st.link_button("Open UniProt record", protein.get("source_url", "https://www.uniprot.org/"))
                    if protein.get("sequence"):
                        st.caption(f"Canonical sequence ({protein.get('sequence_length')} aa); source: UniProt.")
                        st.code(protein["sequence"], language=None)
        else:
            st.info("No reviewed UniProt protein record was returned for these targets.")
        structures = result.get("structures", [])
        st.subheader("RCSB structure records")
        if structures:
            st.dataframe(pd.DataFrame(structures), hide_index=True, alt="RCSB PDB structures matching retrieved UniProt accessions")
        else:
            st.caption("No RCSB PDB structure record was returned for the retrieved accessions.")

    with pathways_tab:
        pathway_data = result.get("pathways", {})
        if pathways:
            st.caption(pathway_data.get("warning", "Reactome reports statistical enrichment for the submitted target gene set."))
            pathway_frame = pd.DataFrame(pathways)
            if "fdr" in pathway_frame and "name" in pathway_frame:
                pathway_frame["-log10(FDR)"] = pathway_frame["fdr"].map(
                    lambda value: -math.log10(max(float(value), 1e-300)) if isinstance(value, (int, float)) else None
                )
                chart = px.bar(
                    pathway_frame,
                    x="-log10(FDR)",
                    y="name",
                    orientation="h",
                    hover_data=[column for column in ("p_value", "fdr", "genes_found", "pathway_id") if column in pathway_frame],
                    title="Reactome over-representation results",
                )
                st.plotly_chart(chart, key="reactome_enrichment_chart")
            st.dataframe(
                pathway_frame,
                hide_index=True,
                alt="Reactome pathway enrichment statistics including p-value and FDR",
            )
            st.caption("FDR values are returned by Reactome for this analysis. They describe enrichment of the submitted gene list, not disease causality.")
        else:
            st.info(pathway_data.get("warning", "Reactome enrichment is unavailable for this result."))
        go_rows = result.get("go_annotations", [])
        st.subheader("Gene Ontology annotations")
        if go_rows:
            st.caption("GO annotations are evidence-linked records. This display does not claim a GO enrichment test.")
            st.dataframe(pd.DataFrame(go_rows), hide_index=True, alt="QuickGO gene ontology annotations and evidence codes")
        else:
            st.caption("QuickGO returned no annotations or was unavailable.")

    with literature_tab:
        if papers:
            for paper in papers:
                with st.container(border=True):
                    st.markdown(f"**{paper.get('title', 'Title unavailable')}**")
                    st.caption(
                        f"PMID {paper.get('pmid')} · {paper.get('year') or 'Date unavailable'} · "
                        f"{paper.get('journal') or 'Journal unavailable'}"
                    )
                    if paper.get("authors"):
                        st.caption(paper["authors"])
                    st.link_button("Open PubMed record", paper.get("url", "https://pubmed.ncbi.nlm.nih.gov/"))
                    if paper.get("abstract"):
                        with st.expander("View retrieved abstract"):
                            st.write(paper["abstract"])
        else:
            st.info("No PubMed records were returned for the constructed query, or PubMed was unavailable.")
        st.subheader("Evidence retrieval assistant")
        st.caption("Answers retrieve source records and excerpts from this analysis. No generative model or unverified web-wide knowledge is used.")
        with st.form("disease_rag_form"):
            question = st.text_input("Ask about this disease evidence", placeholder="Which genes and pathways have source evidence?")
            ask = st.form_submit_button("Retrieve evidence")
        if ask:
            try:
                answer = answer_research_question(result, question)
                st.session_state["disease_rag_answer"] = answer
            except ValueError as exc:
                st.warning(str(exc))
        answer = st.session_state.get("disease_rag_answer")
        if isinstance(answer, dict):
            st.write(answer.get("answer"))
            for evidence in answer.get("evidence", []):
                label = evidence.get("title") or evidence.get("gene_symbol") or evidence.get("name") or evidence.get("kind")
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    if evidence.get("excerpt"):
                        st.write(evidence["excerpt"])
                    if evidence.get("function"):
                        st.write(evidence["function"])
                    if evidence.get("domains"):
                        st.dataframe(pd.DataFrame(evidence["domains"]), hide_index=True, alt="Retrieved protein domain records")
                    if evidence.get("go_id"):
                        st.caption(
                            f"{evidence.get('go_id')} · {evidence.get('aspect')} · "
                            f"evidence {evidence.get('evidence_code')} · {evidence.get('reference') or 'reference not returned'}"
                        )
                    if evidence.get("variant_id"):
                        st.json({key: evidence.get(key) for key in (
                            "variant_id", "chromosome", "position", "ref", "alt",
                            "gene_annotation_from_input", "consequence_annotation_from_input",
                            "clinical_annotation_from_input",
                        )})
                    if evidence.get("association_score") is not None:
                        st.caption(f"Open Targets association score: {evidence['association_score']}")
                    if evidence.get("fdr") is not None:
                        st.caption(f"Reactome FDR: {evidence['fdr']}")
                    url = evidence.get("url") or evidence.get("source_url")
                    if url:
                        st.link_button("Open source record", url)
                    elif evidence.get("kind") == "uploaded_vcf_preview_variant":
                        st.caption("Source: uploaded Phase 3 VCF preview; this record was not externally verified.")
            st.caption(answer.get("method", ""))

    with report_tab:
        st.write("Export the retrieved evidence with database identifiers, source links, versions, and limitations.")
        st.caption(result.get("research_only_disclaimer", "Research use only."))
        name = str(disease.get("name") or "disease_analysis")
        st.download_button(
            "Download PDF report",
            data=disease_report_pdf(result),
            file_name=report_filename(name, "pdf"),
            mime="application/pdf",
            key="download_disease_pdf",
        )
        st.download_button(
            "Download gene CSV",
            data=disease_report_csv(result),
            file_name=report_filename(name, "csv"),
            mime="text/csv",
            key="download_disease_csv",
        )
        st.download_button(
            "Download complete JSON evidence",
            data=disease_report_json(result),
            file_name=report_filename(name, "json"),
            mime="application/json",
            key="download_disease_json",
        )
        with st.expander("Report method and score weights"):
            st.write(result.get("priority_method", "Priority method not available."))
            st.json(result.get("priority_weights", {}))
