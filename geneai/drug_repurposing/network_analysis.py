"""Network analysis and visualization module for drug repurposing."""
from __future__ import annotations

import logging
from typing import Any

import networkx as nx
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def create_disease_gene_drug_network(
    disease_name: str,
    gene_symbols: list[str],
    candidates: list[dict[str, Any]],
    max_nodes: int = 50,
) -> go.Figure:
    """Create Disease-Gene-Drug network visualization."""
    G = nx.Graph()

    # Add disease node
    disease_node = f"DISEASE:{disease_name}"
    G.add_node(disease_node, type="disease", label=disease_name, size=30, color="#e74c3c")

    # Add gene nodes and connect to disease
    for i, gene in enumerate(gene_symbols[:15]):
        gene_node = f"GENE:{gene}"
        G.add_node(gene_node, type="gene", label=gene, size=20, color="#3498db")
        G.add_edge(disease_node, gene_node, weight=0.8, relationship="associated_with")

    # Add drug nodes and connect to genes
    added_drugs = set()
    for candidate in candidates[:20]:
        drug_name = candidate.get("drug_name")
        if not drug_name or drug_name in added_drugs:
            continue

        target_genes = candidate.get("target_genes", [])
        if isinstance(target_genes, list):
            for gene in target_genes:
                if gene in gene_symbols:
                    drug_node = f"DRUG:{drug_name}"
                    if drug_node not in G:
                        phase = candidate.get("max_phase", candidate.get("phase", 0))
                        G.add_node(
                            drug_node,
                            type="drug",
                            label=drug_name[:25],
                            size=15 + min(phase, 4) * 3,
                            color=_phase_color(phase),
                            phase=phase,
                            mechanism=candidate.get("mechanism_of_action", "")[:50],
                        )
                    G.add_edge(
                        f"GENE:{gene}",
                        drug_node,
                        weight=0.6,
                        relationship="targets",
                        mechanism=candidate.get("mechanism_of_action", ""),
                    )
                    added_drugs.add(drug_name)

    # Also add drugs directly connected to disease (from clinical trials)
    for candidate in candidates[:10]:
        drug_name = candidate.get("drug_name")
        if not drug_name or drug_name in added_drugs:
            continue

        # Check if drug has clinical trial for this disease
        if candidate.get("ranking_strategy") == "clinical_trial" or candidate.get("nct_id"):
            drug_node = f"DRUG:{drug_name}"
            if drug_node not in G:
                phase = candidate.get("max_phase", candidate.get("phase", 0))
                G.add_node(
                    drug_node,
                    type="drug",
                    label=drug_name[:25],
                    size=15 + min(phase, 4) * 3,
                    color="#f39c12",  # Orange for clinical trial
                    phase=phase,
                )
            G.add_edge(disease_node, drug_node, weight=0.5, relationship="clinical_trial")
            added_drugs.add(drug_name)

    if len(G.nodes()) < 2:
        return _empty_figure("Insufficient data for network visualization")

    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
    return _create_network_figure(G, pos, f"Disease-Gene-Drug Network: {disease_name}")


def create_drug_target_network(
    candidates: list[dict[str, Any]],
    max_drugs: int = 15,
) -> go.Figure:
    """Create Drug-Target interaction network."""
    G = nx.Graph()

    for candidate in candidates[:max_drugs]:
        drug_name = candidate.get("drug_name")
        if not drug_name:
            continue

        drug_node = f"DRUG:{drug_name}"
        phase = candidate.get("max_phase", candidate.get("phase", 0))
        G.add_node(
            drug_node,
            type="drug",
            label=drug_name[:25],
            size=20,
            color=_phase_color(phase),
            phase=phase,
        )

        # Add target connections
        target_genes = candidate.get("target_genes", [])
        if isinstance(target_genes, list):
            for gene in target_genes[:5]:
                target_node = f"TARGET:{gene}"
                if target_node not in G:
                    G.add_node(target_node, type="target", label=gene, size=15, color="#2ecc71")

                G.add_edge(
                    drug_node,
                    target_node,
                    weight=0.7,
                    mechanism=candidate.get("mechanism_of_action", ""),
                )

        # Add indication connections
        indications = candidate.get("indications", [])
        if isinstance(indications, list):
            for ind in indications[:3]:
                ind_node = f"INDICATION:{ind}"
                if ind_node not in G:
                    G.add_node(ind_node, type="indication", label=ind[:20], size=12, color="#9b59b6")

                G.add_edge(drug_node, ind_node, weight=0.5, relationship="indication")

    if len(G.nodes()) < 2:
        return _empty_figure("Insufficient data for drug-target network")

    pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    return _create_network_figure(G, pos, "Drug-Target-Indication Network")


def create_target_disease_network(
    target_symbol: str,
    diseases: list[dict[str, Any]],
    max_diseases: int = 15,
) -> go.Figure:
    """Create Target-Disease relationship network."""
    G = nx.Graph()

    # Add target node
    target_node = f"TARGET:{target_symbol}"
    G.add_node(target_node, type="target", label=target_symbol, size=25, color="#2ecc71")

    # Add disease nodes
    for disease in diseases[:max_diseases]:
        disease_name = disease.get("disease_name", disease.get("name", "Unknown"))
        disease_id = disease.get("disease_id", "")
        score = disease.get("association_score", disease.get("score", 0))

        disease_node = f"DISEASE:{disease_id}"
        G.add_node(
            disease_node,
            type="disease",
            label=disease_name[:25],
            size=15 + (score * 10 if score else 0),
            color="#e74c3c",
            association_score=score,
        )

        G.add_edge(
            target_node,
            disease_node,
            weight=score if score else 0.5,
            association_score=score,
        )

    if len(G.nodes()) < 2:
        return _empty_figure("Insufficient data for target-disease network")

    pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    return _create_network_figure(G, pos, f"Target-Disease Network: {target_symbol}")


def create_candidate_ranking_chart(
    candidates: list[dict[str, Any]],
    top_n: int = 15,
) -> go.Figure:
    """Create horizontal bar chart of candidate rankings."""
    top_candidates = candidates[:top_n]

    if not top_candidates:
        return _empty_figure("No candidates to display")

    names = [c.get("drug_name", "Unknown")[:30] for c in top_candidates]
    scores = [c.get("overall_score", c.get("hybrid_score", c.get("repurposing_score", 0))) for c in top_candidates]
    phases = [c.get("max_phase", c.get("phase", 0)) for c in top_candidates]
    evidence = [c.get("evidence_classification", "unknown") for c in top_candidates]

    # Color by evidence class
    colors = [_evidence_color(e) for e in evidence]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names,
        x=scores,
        orientation="h",
        marker=dict(
            color=colors,
            line=dict(width=1, color="white"),
        ),
        hovertext=[
            f"Drug: {n}<br>Score: {s:.3f}<br>Phase: {p}<br>Evidence: {e}"
            for n, s, p, e in zip(names, scores, phases, evidence)
        ],
        hoverinfo="text",
    ))

    fig.update_layout(
        title="Drug Repurposing Candidate Rankings",
        xaxis_title="Overall Score",
        yaxis_title="Drug",
        height=max(400, len(names) * 30),
        template="plotly_white",
        margin=dict(l=150, r=20, t=40, b=20),
    )

    return fig


def create_evidence_comparison_chart(
    candidates: list[dict[str, Any]],
    top_n: int = 10,
) -> go.Figure:
    """Create radar chart comparing evidence components for top candidates."""
    top_candidates = candidates[:top_n]

    if not top_candidates:
        return _empty_figure("No candidates to compare")

    # Check if candidates have score breakdown
    has_breakdown = any("score_breakdown" in c or "components" in c.get("score_breakdown", {}) for c in top_candidates)

    if not has_breakdown:
        # Create simplified comparison using available scores
        categories = ["Target Relevance", "Drug-Target Evidence", "Mechanism", "Literature", "Data Confidence"]
        fig = go.Figure()

        for c in top_candidates[:5]:
            name = c.get("drug_name", "Unknown")[:25]
            values = [
                c.get("target_relevance_score", c.get("association_score", 0.5)),
                c.get("drug_target_evidence_score", 0.5),
                c.get("mechanism_compatibility_score", 0.5),
                c.get("literature_evidence_score", 0.5),
                c.get("data_confidence_score", 0.5),
            ]
            fig.add_trace(go.Scatterpolar(
                r=values,
                theta=categories,
                fill="toself",
                name=name,
                opacity=0.7,
            ))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            title="Evidence Component Comparison (Top 5 Candidates)",
            height=500,
            template="plotly_white",
        )
        return fig

    # Full breakdown available
    categories = [
        "Target Relevance",
        "Gene-Disease",
        "Drug-Target Evidence",
        "Mechanism Compatibility",
        "Pathway Relevance",
        "Literature Evidence",
        "Data Confidence",
    ]

    fig = go.Figure()

    for c in top_candidates[:5]:
        name = c.get("drug_name", "Unknown")[:25]
        breakdown = c.get("score_breakdown", {})
        components = breakdown.get("components", [])

        values = []
        for cat in categories:
            comp = next((comp for comp in components if cat.lower().replace(" ", "_") in comp.get("name", "").lower()), None)
            if comp:
                values.append(comp.get("score", 0))
            else:
                values.append(0)

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill="toself",
            name=name,
            opacity=0.7,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title="Evidence Component Comparison (Top 5 Candidates)",
        height=500,
        template="plotly_white",
    )

    return fig


def create_phase_distribution_chart(
    candidates: list[dict[str, Any]],
) -> go.Figure:
    """Create pie chart of clinical phase distribution."""
    if not candidates:
        return _empty_figure("No candidates to display")

    phase_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for c in candidates:
        phase = c.get("max_phase", c.get("phase", 0))
        if phase in phase_counts:
            phase_counts[phase] += 1

    phase_labels = ["Preclinical (0)", "Phase 1", "Phase 2", "Phase 3", "Approved (4)"]
    phase_values = [phase_counts[i] for i in range(5)]
    phase_colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71", "#27ae60"]

    fig = go.Figure(data=[go.Pie(
        labels=phase_labels,
        values=phase_values,
        hole=0.4,
        marker_colors=phase_colors,
        textinfo="label+percent+value",
    )])

    fig.update_layout(
        title="Clinical Phase Distribution of Candidates",
        height=400,
        template="plotly_white",
    )

    return fig


def create_evidence_class_distribution(
    candidates: list[dict[str, Any]],
) -> go.Figure:
    """Create bar chart of evidence classification distribution."""
    if not candidates:
        return _empty_figure("No candidates to display")

    class_counts = {}
    for c in candidates:
        cls = c.get("evidence_classification", "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    classes = list(class_counts.keys())
    counts = list(class_counts.values())
    colors = [_evidence_class_color(c) for c in classes]

    fig = go.Figure(data=[go.Bar(
        x=classes,
        y=counts,
        marker_color=colors,
        text=counts,
        textposition="auto",
    )])

    fig.update_layout(
        title="Evidence Classification Distribution",
        xaxis_title="Evidence Class",
        yaxis_title="Number of Candidates",
        height=400,
        template="plotly_white",
    )

    return fig


def _create_network_figure(G: nx.Graph, pos: dict, title: str) -> go.Figure:
    """Create Plotly figure from NetworkX graph."""
    edge_x, edge_y = [], []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        mode="lines",
        showlegend=False,
    )

    node_x, node_y = [], []
    node_text, node_color, node_size = [], [], []
    node_type = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        data = G.nodes[node]
        node_text.append(data.get("label", node))
        node_color.append(data.get("color", "#3498db"))
        node_size.append(data.get("size", 10))
        node_type.append(data.get("type", "unknown"))

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9),
        marker=dict(
            size=node_size,
            color=node_color,
            line=dict(width=2, color="white"),
            opacity=0.9,
        ),
        hovertext=[
            f"Type: {t}<br>Label: {l}<br>Size: {s}"
            for t, l, s in zip(node_type, node_text, node_size)
        ],
        hoverinfo="text",
        showlegend=False,
    )

    # Add legend traces
    legend_traces = []
    for ntype, color in [("disease", "#e74c3c"), ("gene", "#3498db"), ("target", "#2ecc71"),
                          ("drug", "#9b59b6"), ("indication", "#f39c12"), ("clinical_trial", "#e67e22")]:
        if any(data.get("type") == ntype for _, data in G.nodes(data=True)):
            legend_traces.append(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(size=15, color=color),
                name=ntype.replace("_", " ").title(),
                showlegend=True,
            ))

    fig = go.Figure(data=[edge_trace, node_trace] + legend_traces)
    fig.update_layout(
        title=title,
        showlegend=True,
        hovermode="closest",
        margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=600,
        template="plotly_white",
    )

    return fig


def _empty_figure(message: str) -> go.Figure:
    """Create empty figure with message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray"),
    )
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=400,
        template="plotly_white",
    )
    return fig


def _phase_color(phase: int) -> str:
    """Get color for clinical trial phase."""
    if phase >= 4:
        return "#27ae60"  # Approved - green
    elif phase == 3:
        return "#2ecc71"
    elif phase == 2:
        return "#3498db"
    elif phase == 1:
        return "#f39c12"
    else:
        return "#e74c3c"  # Preclinical - red


def _evidence_color(evidence_class: str) -> str:
    """Get color for evidence classification."""
    colors = {
        "clinical_evidence_same_indication": "#27ae60",
        "clinical_evidence_approved_drug": "#2ecc71",
        "strong_experimental_evidence": "#3498db",
        "moderate_experimental_evidence": "#2980b9",
        "strong_genetic_evidence": "#8e44ad",
        "computational_prediction": "#f39c12",
    }
    return colors.get(evidence_class, "#95a5a6")


def _evidence_class_color(evidence_class: str) -> str:
    """Get color for evidence class in bar chart."""
    return _evidence_color(evidence_class)


def export_network_data(
    candidates: list[dict[str, Any]],
    disease_name: str | None = None,
) -> dict[str, Any]:
    """Export network data for external visualization tools."""
    nodes = []
    edges = []
    node_ids = set()

    # Add disease node
    if disease_name:
        disease_id = f"disease:{disease_name}"
        nodes.append({"id": disease_id, "label": disease_name, "type": "disease"})
        node_ids.add(disease_id)

    for c in candidates:
        drug_name = c.get("drug_name")
        if not drug_name:
            continue

        drug_id = f"drug:{drug_name}"
        if drug_id not in node_ids:
            nodes.append({
                "id": drug_id,
                "label": drug_name,
                "type": "drug",
                "phase": c.get("max_phase", c.get("phase", 0)),
                "evidence_class": c.get("evidence_classification", "unknown"),
            })
            node_ids.add(drug_id)

        # Target genes
        target_genes = c.get("target_genes", [])
        if isinstance(target_genes, list):
            for gene in target_genes:
                gene_id = f"gene:{gene}"
                if gene_id not in node_ids:
                    nodes.append({"id": gene_id, "label": gene, "type": "gene"})
                    node_ids.add(gene_id)

                edges.append({
                    "source": gene_id,
                    "target": drug_id,
                    "relationship": "targets",
                    "mechanism": c.get("mechanism_of_action", ""),
                })

        # Disease connection
        if disease_name:
            disease_id = f"disease:{disease_name}"
            edges.append({
                "source": drug_id,
                "target": disease_id,
                "relationship": "repurposing_candidate",
                "score": c.get("overall_score", 0),
            })

    return {"nodes": nodes, "edges": edges}