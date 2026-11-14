"""Drug visualization module for GeneAI Research using Plotly and NetworkX."""
from __future__ import annotations

import logging
from typing import Any

import networkx as nx
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def create_drug_target_network(
    drug_data: dict[str, Any],
    max_targets: int = 20,
    include_pathways: bool = False,
) -> go.Figure:
    """Create interactive drug-target interaction network."""
    G = nx.Graph()

    drug_name = drug_data.get("merged", {}).get("name") or "Query Drug"
    drug_node = f"DRUG:{drug_name}"
    G.add_node(drug_node, type="drug", label=drug_name, size=30, color="#e74c3c")

    targets = drug_data.get("merged", {}).get("targets", [])[:max_targets]

    for i, target in enumerate(targets):
        target_id = target.get("target_id") or target.get("target_symbol") or f"TARGET_{i}"
        target_label = target.get("target_symbol") or target.get("target_name") or target_id
        confidence = target.get("confidence", 0.5)
        evidence = target.get("evidence_level", "unknown")

        target_node = f"TARGET:{target_id}"
        G.add_node(
            target_node,
            type="target",
            label=target_label,
            size=15 + confidence * 15,
            color=_evidence_color(evidence),
            evidence=evidence,
            confidence=confidence,
            mechanism=target.get("mechanism", ""),
            action_type=target.get("action_type", ""),
        )

        G.add_edge(
            drug_node,
            target_node,
            weight=confidence,
            evidence=evidence,
            mechanism=target.get("mechanism", ""),
        )

    # Add pathway nodes if requested
    if include_pathways:
        pathways = drug_data.get("merged", {}).get("pathways", [])[:10]
        for pathway in pathways:
            pathway_node = f"PATHWAY:{pathway}"
            G.add_node(pathway_node, type="pathway", label=pathway, size=10, color="#3498db")
            # Connect targets to pathways (simplified)
            for target in targets:
                target_id = target.get("target_id") or target.get("target_symbol")
                if target_id:
                    G.add_edge(f"TARGET:{target_id}", pathway_node, weight=0.3)

    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    return _create_network_figure(G, pos, "Drug-Target Interaction Network")


def create_gene_drug_network(
    gene_drug_data: dict[str, Any],
    max_drugs: int = 30,
) -> go.Figure:
    """Create gene-drug association network."""
    G = nx.Graph()

    genes = gene_drug_data.get("genes", {})
    if not genes:
        return _empty_figure("No gene-drug data available")

    for gene_symbol, gene_data in genes.items():
        gene_node = f"GENE:{gene_symbol}"
        G.add_node(gene_node, type="gene", label=gene_symbol, size=25, color="#2ecc71")

        drugs = gene_data.get("target_drugs", [])[:max_drugs]
        for drug in drugs:
            drug_id = drug.get("drug_id")
            drug_name = drug.get("drug_name")
            phase = drug.get("phase", 0)

            drug_node = f"DRUG:{drug_id}"
            if drug_node not in G:
                G.add_node(
                    drug_node,
                    type="drug",
                    label=drug_name,
                    size=10 + min(phase, 4) * 5,
                    color=_phase_color(phase),
                    phase=phase,
                    mechanism=drug.get("mechanism_of_action", ""),
                )

            G.add_edge(
                gene_node,
                drug_node,
                weight=0.5 + phase * 0.1,
                phase=phase,
                mechanism=drug.get("mechanism_of_action", ""),
            )

    pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    return _create_network_figure(G, pos, "Gene-Drug Association Network")


def create_disease_drug_network(
    disease_drug_data: dict[str, Any],
    max_drugs: int = 30,
) -> go.Figure:
    """Create disease-drug relationship graph."""
    G = nx.Graph()

    diseases = disease_drug_data.get("diseases", [])
    if not diseases:
        return _empty_figure("No disease-drug data available")

    for disease in diseases:
        disease_id = disease.get("disease_id")
        disease_name = disease.get("disease_name")
        disease_node = f"DISEASE:{disease_id}"
        G.add_node(disease_node, type="disease", label=disease_name, size=25, color="#e67e22")

        drugs = disease.get("drugs", [])[:max_drugs]
        for drug in drugs:
            drug_id = drug.get("drug_id")
            drug_name = drug.get("drug_name")
            phase = drug.get("max_phase_for_ind", 0)

            drug_node = f"DRUG:{drug_id}"
            if drug_node not in G:
                G.add_node(
                    drug_node,
                    type="drug",
                    label=drug_name,
                    size=10 + min(phase, 4) * 5,
                    color=_phase_color(phase),
                    phase=phase,
                )

            G.add_edge(disease_node, drug_node, weight=0.5, phase=phase)

    pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    return _create_network_figure(G, pos, "Disease-Drug Relationship Network")


def create_clinical_trial_status_chart(trials: list[dict[str, Any]]) -> go.Figure:
    """Create clinical trial status chart."""
    if not trials:
        return _empty_figure("No clinical trial data available")

    # Count by status
    status_counts = {}
    phase_counts = {}
    for trial in trials:
        status = trial.get("overall_status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        phases = trial.get("phase", [])
        if isinstance(phases, list):
            for phase in phases:
                phase_counts[phase] = phase_counts.get(phase, 0) + 1
        else:
            phase_str = str(phases) if phases else "Unknown"
            phase_counts[phase_str] = phase_counts.get(phase_str, 0) + 1

    fig = go.Figure()

    # Status pie chart
    fig.add_trace(go.Pie(
        labels=list(status_counts.keys()),
        values=list(status_counts.values()),
        name="Trial Status",
        domain={"x": [0, 0.45]},
        hole=0.4,
        marker_colors=["#2ecc71", "#3498db", "#f39c12", "#e74c3c", "#95a5a6", "#9b59b6"],
    ))

    # Phase bar chart
    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4", "Unknown"]
    phase_values = [phase_counts.get(p, 0) for p in phase_order]

    fig.add_trace(go.Bar(
        x=phase_order,
        y=phase_values,
        name="Phase Distribution",
        marker_color="#3498db",
        xaxis="x2",
        yaxis="y2",
    ))

    fig.update_layout(
        title="Clinical Trial Status & Phase Distribution",
        xaxis2={"domain": [0.55, 1], "title": "Phase"},
        yaxis2={"title": "Number of Trials", "anchor": "x2"},
        showlegend=True,
        height=500,
        template="plotly_white",
    )

    return fig


def create_drug_property_radar(drugs: list[dict[str, Any]], properties: list[str] | None = None) -> go.Figure:
    """Create radar chart comparing drug molecular properties."""
    if not drugs:
        return _empty_figure("No drug data available")

    default_props = [
        "molecular_weight", "xlogp3", "tpsa", "hbond_donors",
        "hbond_acceptors", "rotatable_bonds", "ro5_violations"
    ]
    properties = properties or default_props

    fig = go.Figure()

    for drug in drugs[:6]:  # Limit to 6 drugs for readability
        name = drug.get("merged", {}).get("name") or drug.get("identifier", "Unknown")
        props = drug.get("merged", {}).get("molecular_properties", {})

        values = []
        for prop in properties:
            val = props.get(prop)
            if val is not None:
                # Normalize to 0-1 range for radar
                normalized = _normalize_property(prop, val)
                values.append(normalized)
            else:
                values.append(0)

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=properties,
            fill="toself",
            name=name[:30],
            opacity=0.7,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title="Drug Molecular Property Comparison (Normalized)",
        height=500,
        template="plotly_white",
    )

    return fig


def create_drug_property_scatter(
    drugs: list[dict[str, Any]],
    x_prop: str = "molecular_weight",
    y_prop: str = "xlogp3",
    color_prop: str | None = "tpsa",
) -> go.Figure:
    """Create scatter plot of drug properties."""
    if not drugs:
        return _empty_figure("No drug data available")

    x_vals, y_vals, colors, names, hovers = [], [], [], [], []

    for drug in drugs:
        props = drug.get("merged", {}).get("molecular_properties", {})
        x = props.get(x_prop)
        y = props.get(y_prop)
        if x is not None and y is not None:
            x_vals.append(x)
            y_vals.append(y)
            names.append(drug.get("merged", {}).get("name") or drug.get("identifier", "Unknown"))
            hovers.append(
                f"Name: {names[-1]}<br>"
                f"{x_prop}: {x:.2f}<br>"
                f"{y_prop}: {y:.2f}<br>"
                f"Sources: {', '.join(drug.get('merged', {}).get('sources_found', []))}"
            )
            if color_prop:
                c = props.get(color_prop)
                colors.append(c if c is not None else 0)
            else:
                colors.append(1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="markers",
        marker=dict(
            size=12,
            color=colors,
            colorscale="Viridis" if color_prop else None,
            showscale=bool(color_prop),
            colorbar=dict(title=color_prop) if color_prop else None,
            opacity=0.8,
            line=dict(width=1, color="white"),
        ),
        text=names,
        hovertext=hovers,
        hoverinfo="text",
        name="Drugs",
    ))

    fig.update_layout(
        title=f"Drug Property Space: {x_prop} vs {y_prop}",
        xaxis_title=x_prop.replace("_", " ").title(),
        yaxis_title=y_prop.replace("_", " ").title(),
        height=500,
        template="plotly_white",
    )

    return fig


def create_target_druggability_chart(targets: list[dict[str, Any]]) -> go.Figure:
    """Create target druggability assessment chart."""
    if not targets:
        return _empty_figure("No target data available")

    names = []
    sm_scores = []
    ab_scores = []
    evidence = []

    for t in targets[:20]:
        name = t.get("target_symbol") or t.get("target_name") or t.get("target_id", "Unknown")
        names.append(name[:40])
        sm = t.get("tractability_sm")
        ab = t.get("tractability_ab")
        sm_scores.append(_tractability_score(sm))
        ab_scores.append(_tractability_score(ab))
        evidence.append(t.get("evidence_level", "unknown"))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names,
        x=sm_scores,
        name="Small Molecule Tractability",
        orientation="h",
        marker_color="#3498db",
        hovertext=[f"Small Molecule: {sm}" for sm in sm_scores],
    ))
    fig.add_trace(go.Bar(
        y=names,
        x=ab_scores,
        name="Antibody Tractability",
        orientation="h",
        marker_color="#e74c3c",
        hovertext=[f"Antibody: {ab}" for ab in ab_scores],
    ))

    fig.update_layout(
        title="Target Druggability Assessment (Open Targets)",
        xaxis_title="Tractability Score",
        yaxis_title="Target",
        barmode="group",
        height=max(400, len(names) * 25),
        template="plotly_white",
    )

    return fig


def _create_network_figure(G: nx.Graph, pos: dict, title: str) -> go.Figure:
    """Create Plotly figure from NetworkX graph."""
    if not G.nodes():
        return _empty_figure("No data to display")

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
    node_type, node_info = [], []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        data = G.nodes[node]
        node_text.append(data.get("label", node))
        node_color.append(data.get("color", "#3498db"))
        node_size.append(data.get("size", 10))
        node_type.append(data.get("type", "unknown"))
        node_info.append(data)

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
            f"Type: {info.get('type')}<br>"
            f"Label: {info.get('label')}<br>"
            f"Evidence: {info.get('evidence', 'N/A')}<br>"
            f"Confidence: {info.get('confidence', 'N/A')}<br>"
            f"Mechanism: {info.get('mechanism', 'N/A')}<br>"
            f"Phase: {info.get('phase', 'N/A')}"
            for info in node_info
        ],
        hoverinfo="text",
        showlegend=False,
    )

    # Add legend traces
    legend_traces = []
    for ntype, color in [("drug", "#e74c3c"), ("target", "#3498db"), ("gene", "#2ecc71"), ("disease", "#e67e22"), ("pathway", "#9b59b6")]:
        if any(data.get("type") == ntype for _, data in G.nodes(data=True)):
            legend_traces.append(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(size=15, color=color),
                name=ntype.capitalize(),
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


def _evidence_color(evidence: str) -> str:
    """Get color for evidence level."""
    colors = {
        "clinical": "#27ae60",
        "preclinical": "#2ecc71",
        "biochemical": "#3498db",
        "cellular": "#2980b9",
        "genetic": "#8e44ad",
        "curated": "#9b59b6",
        "predicted": "#f39c12",
        "literature": "#34495e",
    }
    return colors.get(evidence.lower(), "#95a5a6")


def _phase_color(phase: int) -> str:
    """Get color for clinical trial phase."""
    if phase >= 4:
        return "#27ae60"  # Approved
    elif phase == 3:
        return "#2ecc71"
    elif phase == 2:
        return "#3498db"
    elif phase == 1:
        return "#f39c12"
    else:
        return "#e74c3c"  # Preclinical


def _tractability_score(tractability: str | None) -> float:
    """Convert tractability string to numeric score."""
    if not tractability:
        return 0.0
    tractability = tractability.lower()
    if "high" in tractability:
        return 1.0
    elif "medium" in tractability:
        return 0.6
    elif "low" in tractability:
        return 0.2
    return 0.0


def _normalize_property(prop: str, value: float) -> float:
    """Normalize property value to 0-1 range for radar chart."""
    ranges = {
        "molecular_weight": (100, 1000),
        "xlogp3": (-3, 8),
        "tpsa": (0, 200),
        "hbond_donors": (0, 10),
        "hbond_acceptors": (0, 20),
        "rotatable_bonds": (0, 30),
        "ro5_violations": (0, 5),
        "alogp": (-3, 8),
        "psa": (0, 200),
        "hba": (0, 20),
        "hbd": (0, 10),
        "rtb": (0, 30),
    }
    min_val, max_val = ranges.get(prop, (0, 1))
    return max(0, min(1, (value - min_val) / (max_val - min_val)))