"""Streamlit UI for the Phase 4.3 drug-target research workflow."""
from __future__ import annotations

import io
import logging
import math
import sqlite3
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from geneai.agents.target_identification_agent import (
    TargetIdentificationRequest,
    run_target_identification_agent,
)
from geneai.database.target_schema import store_target_ml_run
from geneai.drug_discovery import api_clients
from geneai.drug_discovery.target_identification import DEFAULT_TARGET_WEIGHTS, ML_FEATURE_COLUMNS
from geneai.drug_discovery.target_reports import (
    target_report_csv,
    target_report_filename,
    target_report_json,
    target_report_pdf,
)

logger = logging.getLogger(__name__)


def render_target_identification_page() -> None:
    """Render target ranking from the user's current Phase 4.2 disease snapshot."""
    st.subheader("AI Drug Target Identification")
    st.write(
        "Prioritize disease-associated genes using retrieved genetic, literature, protein and STRING evidence. "
        "Scores are research shortlist indices and do not establish druggability or clinical success."
    )
    st.info(
        "First run **Drug Discovery · Disease Analysis**. This page reuses that evidence snapshot and will not "
        "silently repeat or replace its disease search."
    )
    disease_result = st.session_state.get("disease_analysis_result")
    if not isinstance(disease_result, dict) or not isinstance(disease_result.get("genes"), list):
        st.warning("No disease analysis with gene results is available in this session yet.")
        return

    disease = disease_result.get("disease") or {}
    st.caption(
        f"Disease: {disease.get('name', 'Unknown')} · ID: {disease.get('disease_id', 'unavailable')} · "
        f"Source snapshot: {disease_result.get('analysis_id', 'ID unavailable')} · "
        f"retrieved {disease_result.get('retrieved_at', 'time unavailable')}"
    )
    with st.expander("Configure evidence weights and STRING network", expanded=True):
        st.caption("Weights apply only to source evidence returned for a target; missing evidence is excluded and remaining weights are renormalized.")
        left, right = st.columns(2)
        with left:
            network_type = st.selectbox("STRING network", ["functional", "physical"], key="target_network_type")
            required_score = st.slider("Minimum STRING combined score", 0, 1000, 400, 50, key="target_string_threshold")
        with right:
            disease_weight = st.slider("Disease association weight", 0.0, 10.0, float(DEFAULT_TARGET_WEIGHTS["disease_association"]), 0.25, key="target_weight_disease")
            genetic_weight = st.slider("Genetic evidence weight", 0.0, 10.0, float(DEFAULT_TARGET_WEIGHTS["genetic_evidence"]), 0.25, key="target_weight_genetic")
            literature_weight = st.slider("Literature evidence weight", 0.0, 10.0, float(DEFAULT_TARGET_WEIGHTS["literature_evidence"]), 0.25, key="target_weight_literature")
            ppi_weight = st.slider("STRING association weight", 0.0, 10.0, float(DEFAULT_TARGET_WEIGHTS["protein_interaction_support"]), 0.25, key="target_weight_ppi")
        if st.button("Identify and rank targets", type="primary", key="run_target_identification"):
            st.session_state.pop("target_identification_result", None)
            request = TargetIdentificationRequest(
                disease_analysis_result=disease_result,
                network_type=network_type,
                required_score=required_score,
                weights={
                    "disease_association": disease_weight,
                    "genetic_evidence": genetic_weight,
                    "literature_evidence": literature_weight,
                    "protein_interaction_support": ppi_weight,
                },
            )
            try:
                with st.spinner("Retrieving the STRING association network and ranking available evidence…"):
                    st.session_state["target_identification_result"] = run_target_identification_agent(request)
            except ValueError as exc:
                st.error(str(exc))
            except api_clients.DataSourceError as exc:
                st.error(f"The target analysis could not be completed: {exc}")

    result = st.session_state.get("target_identification_result")
    if isinstance(result, dict) and result.get("disease_analysis_id") != disease_result.get("analysis_id"):
        st.warning("The displayed target assessment used an older disease-analysis snapshot. Run target identification again to refresh it.")
    if isinstance(result, dict):
        _render_target_results(result)


def _render_target_results(result: dict[str, Any]) -> None:
    targets = result.get("targets", [])
    network = result.get("ppi_network") or {}
    high = sum(row.get("target_research_priority_tier") == "High research-priority shortlist" for row in targets)
    disease = result.get("disease") or {}
    with st.container(horizontal=True):
        st.metric("Disease genes assessed", len(targets), border=True)
        st.metric("Ranked shortlist (high tier)", high, border=True)
        st.metric("STRING associations", network.get("edge_count", 0), border=True)
        st.metric("Proteins with UniProt context", sum(bool((row.get("protein") or {}).get("uniprot_id")) for row in targets), border=True)
    st.caption(
        f"Assessment {result.get('analysis_id')} · Retrieved {result.get('retrieved_at')} · "
        f"Database save: {(result.get('storage') or {}).get('status', 'not reported')}"
    )
    st.warning(result.get("research_only_disclaimer", "Research use only; scores are not clinical or validated druggability conclusions."))

    overview_tab, ranking_tab, ppi_tab, evidence_tab, model_tab, report_tab = st.tabs(
        ["Overview & sources", "Target ranking", "Protein network", "Biological evidence", "Optional ML", "Research reports"]
    )
    with overview_tab:
        st.markdown(f"**Disease:** {disease.get('name', 'Unknown')} · `{disease.get('disease_id', 'ID unavailable')}`")
        st.caption(result.get("priority_method", "Evidence-weighted research index."))
        source_rows = [
            {
                "Source": item.get("source"), "Status": item.get("status"),
                "Version": item.get("version", "not reported"), "Records": item.get("record_count", 0),
                "URL": item.get("url", ""), "Details": item.get("error") or item.get("reason", ""),
            }
            for item in result.get("data_sources", [])
        ]
        if source_rows:
            st.dataframe(
                pd.DataFrame(source_rows), hide_index=True, alt="Target identification data source status",
                column_config={"URL": st.column_config.LinkColumn("Source URL")},
            )
        if result.get("limitations"):
            st.subheader("Evidence limits")
            for limitation in result["limitations"]:
                st.markdown(f"- {limitation}")

    with ranking_tab:
        if not targets:
            st.info("No target genes were present in the reused disease analysis.")
        else:
            query = st.text_input("Filter by gene, name, or identifier", key="target_gene_filter")
            tiers = sorted({str(row.get("target_research_priority_tier", "Not scored")) for row in targets})
            selected_tiers = st.multiselect("Research shortlist tier", tiers, default=tiers, key="target_tier_filter")
            visible = [
                row for row in targets
                if row.get("target_research_priority_tier") in selected_tiers
                and (not query.strip() or query.casefold() in " ".join(str(row.get(key, "")) for key in ("gene_symbol", "gene_name", "ensembl_gene_id", "ncbi_gene_id")).casefold())
            ]
            table = pd.DataFrame([_target_table_row(row) for row in visible])
            st.dataframe(table, hide_index=True, alt="Ranked disease-associated genes and evidence components")
            if visible:
                chart = pd.DataFrame([
                    {"Gene": row.get("gene_symbol"), "Research priority index": row.get("target_research_priority_index")}
                    for row in visible if row.get("target_research_priority_index") is not None
                ])
                if not chart.empty:
                    fig = px.bar(chart, x="Gene", y="Research priority index", title="Evidence-weighted research shortlist index")
                    fig.update_yaxes(range=[0, 100], title="Index (0–100; not a probability)")
                    st.plotly_chart(fig, use_container_width=True)
            if visible:
                options = [str(row.get("gene_symbol")) for row in visible]
                compare = st.multiselect("Compare target evidence", options, default=options[: min(3, len(options))], key="target_compare_genes")
                compare_rows = [row for row in visible if row.get("gene_symbol") in compare]
                if compare_rows:
                    evidence_chart = pd.DataFrame([
                        {"Gene": row.get("gene_symbol"), "Evidence": label.replace("_", " "), "Score": component.get("score")}
                        for row in compare_rows
                        for label, component in (row.get("target_priority_components") or {}).items()
                    ])
                    if not evidence_chart.empty:
                        fig = px.bar(evidence_chart, x="Gene", y="Score", color="Evidence", barmode="group", title="Available evidence components for selected genes")
                        fig.update_yaxes(range=[0, 1])
                        st.plotly_chart(fig, use_container_width=True)

    with ppi_tab:
        st.caption(network.get("interpretation", "STRING network scores describe database associations."))
        nodes = network.get("nodes", [])
        edges = network.get("edges", [])
        if edges and nodes:
            st.plotly_chart(_network_figure(nodes, edges), use_container_width=True)
            edge_frame = pd.DataFrame([
                {
                    "Protein A": edge.get("protein_a"), "Protein B": edge.get("protein_b"),
                    "Network type": edge.get("network_type"), "Combined association score": edge.get("combined_score"),
                    "Experimental channel score": edge.get("experimental_channel_score"),
                    "Source": edge.get("source_url"),
                }
                for edge in edges
            ])
            st.dataframe(edge_frame, hide_index=True, alt="STRING association edges with experimental channel retained separately")
        else:
            st.info("No STRING associations were returned for the selected symbols and threshold. Other disease evidence remains available.")

    with evidence_tab:
        st.subheader("Protein and gene context")
        protein_rows = []
        for row in targets:
            protein = row.get("protein") or {}
            protein_rows.append({
                "Gene": row.get("gene_symbol"), "UniProt ID": protein.get("uniprot_id"),
                "Protein": protein.get("protein_name"), "Function": protein.get("function"),
                "Localization": protein.get("subcellular_location"), "Domains": len(protein.get("domains", [])),
                "PDB references": ", ".join(protein.get("pdb_ids_from_uniprot", [])),
            })
        st.dataframe(pd.DataFrame(protein_rows), hide_index=True, alt="Protein context from the Phase 4.2 disease analysis")
        st.subheader("Reactome disease-gene-set context")
        pathways = (result.get("pathways") or {}).get("pathways", [])
        if pathways:
            pathway_frame = pd.DataFrame([
                {"Pathway": row.get("name"), "Reactome ID": row.get("pathway_id"), "P value": row.get("p_value"), "FDR": row.get("fdr"), "Genes found": row.get("genes_found"), "Source": row.get("source_url")}
                for row in pathways
            ])
            st.dataframe(pathway_frame, hide_index=True, alt="Reactome enrichment records for the disease-associated gene set")
            st.caption("These enrichment results apply to the disease gene set; they are not assigned as gene-specific target evidence.")
        else:
            st.info("The disease-analysis snapshot contains no Reactome pathways.")
        st.subheader("VCF preview overlaps")
        mutation_rows = result.get("mutations_from_vcf_preview", [])
        if mutation_rows:
            st.dataframe(pd.DataFrame(mutation_rows), hide_index=True, alt="Source VCF preview annotations associated with disease genes")
            st.caption("VCF preview overlap is not an inferred mutation effect or pathogenicity classification.")
        else:
            st.caption("No matching VCF preview annotations were included in the disease-analysis snapshot.")
        st.subheader("Gene Ontology annotations")
        go_rows = [annotation for row in targets for annotation in row.get("go_annotations", [])]
        if go_rows:
            st.dataframe(pd.DataFrame(go_rows), hide_index=True, alt="GO annotations already retrieved by disease analysis")
        else:
            st.caption("No GO annotations were available in the reused disease-analysis snapshot.")

    with model_tab:
        _render_optional_ml(result)

    with report_tab:
        st.write("Download a source-attributed target research snapshot. Reports include the evidence score method and known limitations.")
        name = str(disease.get("name") or "disease_targets")
        col1, col2, col3 = st.columns(3)
        col1.download_button("Download CSV", target_report_csv(result), target_report_filename(name, "csv"), "text/csv", key="target_report_csv")
        col2.download_button("Download JSON", target_report_json(result), target_report_filename(name, "json"), "application/json", key="target_report_json")
        col3.download_button("Download PDF", target_report_pdf(result), target_report_filename(name, "pdf"), "application/pdf", key="target_report_pdf")
        st.caption("Target scores are evidence summaries for research, not experimental validation or clinical advice.")


def _target_table_row(row: dict[str, Any]) -> dict[str, Any]:
    protein = row.get("protein") or {}
    components = row.get("target_priority_components") or {}
    return {
        "Rank": row.get("target_research_rank"), "Gene": row.get("gene_symbol"),
        "Gene name": row.get("gene_name"), "NCBI Gene ID": row.get("ncbi_gene_id"),
        "Ensembl Gene ID": row.get("ensembl_gene_id"), "Index (0–100)": row.get("target_research_priority_index"),
        "Shortlist tier": row.get("target_research_priority_tier"),
        "Disease association": (components.get("disease_association") or {}).get("score"),
        "Genetic evidence": (components.get("genetic_evidence") or {}).get("score"),
        "Literature evidence": (components.get("literature_evidence") or {}).get("score"),
        "STRING support": (components.get("protein_interaction_support") or {}).get("score"),
        "VCF preview rows": row.get("vcf_preview_variant_count", 0),
        "UniProt ID": protein.get("uniprot_id"),
        "Missing evidence": ", ".join(row.get("target_missing_evidence_domains", [])),
        "Source": row.get("source_url"),
    }


def _network_figure(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> go.Figure:
    """Draw a compact deterministic circular network without a graph dependency."""
    chosen = nodes[:80]
    count = len(chosen)
    positions = {
        row.get("gene_symbol"): (math.cos(2 * math.pi * index / max(count, 1)), math.sin(2 * math.pi * index / max(count, 1)))
        for index, row in enumerate(chosen)
    }
    line_x: list[float | None] = []
    line_y: list[float | None] = []
    for edge in edges:
        left, right = edge.get("protein_a"), edge.get("protein_b")
        if left not in positions or right not in positions:
            continue
        line_x.extend([positions[left][0], positions[right][0], None])
        line_y.extend([positions[left][1], positions[right][1], None])
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=line_x, y=line_y, mode="lines", line={"width": 1, "color": "#8a94a6"}, hoverinfo="skip", name="STRING association"))
    node_rows = [row for row in chosen if row.get("gene_symbol") in positions]
    figure.add_trace(go.Scatter(
        x=[positions[row["gene_symbol"]][0] for row in node_rows],
        y=[positions[row["gene_symbol"]][1] for row in node_rows],
        mode="markers+text", text=[row["gene_symbol"] for row in node_rows], textposition="top center",
        marker={"size": [12 + min(18, 3 * int(row.get("interaction_count") or 0)) for row in node_rows], "color": ["#3b82f6" if row.get("is_input_gene") else "#14b8a6" for row in node_rows], "line": {"width": 1, "color": "white"}},
        customdata=[[row.get("interaction_count"), row.get("degree_centrality"), row.get("max_experimental_channel_score")] for row in node_rows],
        hovertemplate="%{text}<br>Edges: %{customdata[0]}<br>Degree: %{customdata[1]}<br>Max experimental channel: %{customdata[2]}<extra></extra>",
        name="Proteins",
    ))
    figure.update_layout(title="STRING protein association network", showlegend=False, xaxis={"visible": False}, yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1}, margin={"l": 10, "r": 10, "t": 45, "b": 10}, height=520)
    return figure


def _render_optional_ml(result: dict[str, Any]) -> None:
    st.write(
        "Optional supervised research model. Upload a real labeled dataset with documented source, license and label definition. "
        "No built-in biological labels are supplied. Cross-validation keeps all rows for each gene in one fold."
    )
    st.caption("Accepted CSV columns: gene_symbol, label (0/1), and at least two numeric columns from the current target features.")
    uploaded = st.file_uploader("Documented target-label CSV (max 2 MB)", type=["csv"], key="target_ml_csv", max_upload_size=3)
    model_type = st.selectbox("Model", ["Logistic Regression", "Random Forest", "Gradient Boosting"], key="target_ml_model")
    source = st.text_input("Dataset publication, source URL or repository", key="target_ml_source")
    license_text = st.text_input("Dataset license or access conditions", key="target_ml_license")
    if st.button("Train and evaluate on this dataset", key="train_target_ml", type="secondary"):
        try:
            if uploaded is None:
                raise ValueError("Upload a documented labeled CSV first.")
            data = uploaded.getvalue()
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("The training CSV must be 2 MB or smaller for this laptop-friendly workflow.")
            from geneai.drug_discovery.target_ml import score_target_rows, train_evaluate_target_model
            header = list(pd.read_csv(io.BytesIO(data), nrows=0).columns)
            if len(header) > len(ML_FEATURE_COLUMNS) + 2:
                raise ValueError("The training CSV contains too many columns; keep only gene_symbol, label, and supported numeric target features.")
            if not {"gene_symbol", "label"}.issubset(header):
                raise ValueError("Training CSV must include gene_symbol and binary label columns.")
            feature_headers = [column for column in header if column in ML_FEATURE_COLUMNS]
            if len(feature_headers) < 2:
                raise ValueError("Include at least two numeric columns from the target feature set.")
            frame = pd.read_csv(io.BytesIO(data), usecols=["gene_symbol", "label", *feature_headers], nrows=50_001)
            if len(frame) > 50_000:
                raise ValueError("The training CSV is limited to 50,000 rows.")
            bundle = train_evaluate_target_model(frame, model_type=model_type, dataset_source=source, dataset_license=license_text)
            predictions = score_target_rows(bundle, result.get("target_feature_rows", []))
            public_bundle = {key: value for key, value in bundle.items() if key != "estimator"}
            result["ml_evaluation"] = public_bundle
            result["ml_predictions"] = predictions
            st.session_state["target_identification_result"] = result
            st.session_state["target_ml_bundle"] = bundle
            if (result.get("storage") or {}).get("status") == "saved":
                try:
                    run_id = store_target_ml_run(result["analysis_id"], bundle)
                    result["storage"]["ml_run_id"] = run_id
                except (sqlite3.Error, OSError, ValueError) as exc:
                    logger.exception("Could not persist target model evaluation")
                    st.warning(f"Model result is available for this session but could not be saved: {exc}")
            st.success("Model evaluation completed on the supplied dataset. Review the metrics and dataset limitations below.")
        except ImportError:
            st.error("Scikit-learn is not installed. Install the optional dependency listed in requirements.txt and restart the app.")
        except (ValueError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            st.error(str(exc))
        except Exception as exc:
            logger.exception("Target model training failed")
            st.error(f"Model evaluation stopped safely: {exc}")

    evaluation = result.get("ml_evaluation")
    if isinstance(evaluation, dict):
        st.subheader("Grouped cross-validation results")
        metrics = evaluation.get("evaluation_metrics", {})
        columns = st.columns(5)
        for col, metric in zip(columns, ("accuracy", "precision", "recall", "f1", "roc_auc")):
            col.metric(metric.replace("_", " ").upper(), metrics.get(metric, "n/a"))
        st.caption(f"{metrics.get('evaluation')} · {metrics.get('fold_count')} folds · Gene isolation verified: {metrics.get('gene_group_isolation_verified')}")
        st.write(f"Dataset: {evaluation.get('dataset_source')} · License: {evaluation.get('dataset_license')} · Model: {evaluation.get('model_type')} ({evaluation.get('model_version')})")
        importance = evaluation.get("feature_importance", [])
        if importance:
            st.dataframe(pd.DataFrame(importance), hide_index=True, alt="Descriptive model feature importance")
        if evaluation.get("limitations"):
            for limitation in evaluation["limitations"]:
                st.markdown(f"- {limitation}")
        predictions = result.get("ml_predictions", [])
        if predictions:
            st.dataframe(pd.DataFrame(predictions), hide_index=True, alt="Model output for current target rows")
            st.caption("Positive-class scores are uncalibrated outputs for the uploaded label definition, not clinical probabilities.")

