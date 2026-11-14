"""Advanced visualizations for the AI Drug Target Identification Engine.

All charts use Plotly. No biological data is fabricated -- figures are built
from the evidence dictionaries returned by the existing target identification,
druggability, PPI, and pathway modules.
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


def target_ranking_chart(targets: list[dict[str, Any]]) -> go.Figure:
    """Horizontal bar chart of target research priority index by gene."""
    if not targets:
        fig = go.Figure()
        fig.add_annotation(
            text="No targets available. Run Disease Analysis and Target Identification first.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        fig.update_layout(title="Target Research Priority Index", height=400)
        return fig

    df = pd.DataFrame(targets)
    df = df.sort_values("target_research_priority_index", na_position="last")
    df = df.tail(20)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["gene_symbol"],
        x=df["target_research_priority_index"],
        orientation="h",
        marker_color="#176C52",
        hovertemplate="<b>%{y}</b><br>Priority Index: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title="Target Research Priority Index (Top 20)",
        xaxis_title="Priority Index (0-100)",
        yaxis_title="Gene Symbol",
        height=max(300, 25 * len(df)),
        margin=dict(l=100, r=20, t=50, b=50),
    )
    fig.update_yaxes(autorange="reversed")
    return fig


def druggability_gauge(index_value: float | None) -> go.Figure:
    """Gauge chart showing druggability index for a single target."""
    value = index_value if index_value is not None else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "Druggability Research Index", "font": {"size": 16}},
        gauge={
            "axis": {"range": [None, 100]},
            "bar": {"color": "#176C52"},
            "steps": [
                {"range": [0, 34], "color": "#E8F1EA"},
                {"range": [34, 67], "color": "#B7E6C8"},
                {"range": [67, 100], "color": "#7CCDA6"},
            ],
            "threshold": {
                "line": {"color": "#172824", "width": 4},
                "thickness": 0.75,
                "value": value,
            },
        },
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=60, b=20))
    return fig


def evidence_distribution_chart(targets: list[dict[str, Any]]) -> go.Figure:
    """Box plot of evidence score distributions across targets."""
    if not targets:
        fig = go.Figure()
        fig.add_annotation(
            text="No targets available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    df = pd.DataFrame(targets)
    score_cols = [
        ("disease_association_evidence_score", "Disease Association"),
        ("genetic_evidence_score", "Genetic Evidence"),
        ("literature_evidence_score", "Literature Evidence"),
        ("ppi_network_score", "PPI Network"),
    ]
    available = [(col, label) for col, label in score_cols if col in df.columns]
    if not available:
        fig = go.Figure()
        fig.add_annotation(
            text="No evidence scores available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    fig = go.Figure()
    for col, label in available:
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(values) > 0:
            fig.add_trace(go.Box(
                y=values,
                name=label,
                boxpoints="outliers",
                marker_color="#176C52",
            ))
    fig.update_layout(
        title="Evidence Score Distribution Across Targets",
        yaxis_title="Score (0-1)",
        height=400,
        margin=dict(l=60, r=20, t=50, b=50),
    )
    return fig


def ppi_network_chart(ppi_network: dict[str, Any] | None) -> go.Figure:
    """Scatter plot of PPI network nodes sized by interaction count."""
    if not ppi_network or not ppi_network.get("nodes"):
        fig = go.Figure()
        fig.add_annotation(
            text="No PPI network data available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        fig.update_layout(title="Protein-Protein Interaction Network", height=500)
        return fig

    nodes = ppi_network["nodes"]
    edges = ppi_network.get("edges", [])

    # Build adjacency for edge traces
    import random
    random.seed(42)
    node_positions: dict[str, tuple[float, float]] = {}
    for node in nodes:
        symbol = node["gene_symbol"]
        node_positions[symbol] = (random.uniform(0, 1), random.uniform(0, 1))

    edge_x: list[float] = []
    edge_y: list[float] = []
    for edge in edges:
        a, b = edge.get("protein_a"), edge.get("protein_b")
        if a in node_positions and b in node_positions:
            x0, y0 = node_positions[a]
            x1, y1 = node_positions[b]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        showlegend=False,
    )

    node_x = [node_positions[n["gene_symbol"]][0] for n in nodes]
    node_y = [node_positions[n["gene_symbol"]][1] for n in nodes]
    node_text = [
        f"{n['gene_symbol']}<br>Interactions: {n['interaction_count']}<br>"
        f"Degree centrality: {n.get('degree_centrality', 0):.3f}"
        for n in nodes
    ]
    node_sizes = [10 + 30 * n.get("interaction_count", 0) for n in nodes]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=[n["gene_symbol"] for n in nodes],
        textposition="top center",
        hoverinfo="text",
        hovertext=node_text,
        marker=dict(
            size=node_sizes,
            color=node_sizes,
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(title="Interaction Count"),
            line=dict(width=1, color="#333"),
        ),
        showlegend=False,
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        title="Protein-Protein Interaction Network (STRING)",
        showlegend=False,
        hovermode="closest",
        margin=dict(b=20, l=20, r=20, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=500,
    )
    return fig


def variant_type_distribution(variants: list[dict[str, Any]]) -> go.Figure:
    """Pie chart of variant type distribution."""
    if not variants:
        fig = go.Figure()
        fig.add_annotation(
            text="No variants available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    df = pd.DataFrame(variants)
    if "variant_type" not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="No variant type data available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    counts = df["variant_type"].value_counts()
    fig = go.Figure(data=[go.Pie(
        labels=counts.index,
        values=counts.values,
        hole=0.4,
        marker=dict(colors=px.colors.qualitative.Set2),
    )])
    fig.update_layout(
        title="Variant Type Distribution",
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def gene_disease_network_chart(
    targets: list[dict[str, Any]],
    disease_name: str = "Disease",
) -> go.Figure:
    """Simple gene-disease association network visualization."""
    if not targets:
        fig = go.Figure()
        fig.add_annotation(
            text="No targets available.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    import math
    import random
    random.seed(42)

    # Disease at center
    disease_x, disease_y = 0.5, 0.5
    fig = go.Figure()

    # Disease node
    fig.add_trace(go.Scatter(
        x=[disease_x], y=[disease_y],
        mode="markers+text",
        text=[disease_name],
        textposition="middle center",
        marker=dict(size=30, color="#172824", symbol="square"),
        hoverinfo="text",
        hovertext=f"Disease: {disease_name}",
        showlegend=False,
    ))

    # Gene nodes arranged in a circle around disease
    n_genes = min(len(targets), 15)
    gene_x: list[float] = []
    gene_y: list[float] = []
    gene_text: list[str] = []
    gene_hover: list[str] = []
    edge_x: list[float] = []
    edge_y: list[float] = []

    for i, target in enumerate(targets[:n_genes]):
        angle = 2 * math.pi * i / n_genes
        x = disease_x + 0.35 * math.cos(angle)
        y = disease_y + 0.35 * math.sin(angle)
        gene_x.append(x)
        gene_y.append(y)
        symbol = str(target.get("gene_symbol", "Unknown"))
        gene_text.append(symbol)
        score = target.get("target_research_priority_index")
        gene_hover.append(
            f"{symbol}<br>Priority Index: {score if score is not None else 'n/a'}"
        )
        # Edge from disease to gene
        edge_x.extend([disease_x, x, None])
        edge_y.extend([disease_y, y, None])

    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=gene_x, y=gene_y,
        mode="markers+text",
        text=gene_text,
        textposition="middle center",
        hoverinfo="text",
        hovertext=gene_hover,
        marker=dict(
            size=20,
            color="#176C52",
            line=dict(width=1, color="#333"),
        ),
        showlegend=False,
    ))

    fig.update_layout(
        title=f"Gene-Disease Association Network: {disease_name}",
        showlegend=False,
        hovermode="closest",
        margin=dict(b=20, l=20, r=20, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=500,
    )
    return fig
