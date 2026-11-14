"""Visualization components for drug-target interaction predictions."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)


def create_prediction_confidence_chart(
    predictions: list[dict[str, Any]],
    title: str = "Drug-Target Interaction Predictions",
) -> go.Figure:
    """Create bar chart of prediction confidence scores.
    
    Args:
        predictions: List of prediction results
        title: Chart title
        
    Returns:
        Plotly figure
    """
    if not predictions:
        return go.Figure()
    
    df = pd.DataFrame(predictions)
    
    # Filter successful predictions
    df = df[df.get("success", True) == True]
    
    if df.empty:
        return go.Figure()
    
    # Sort by probability
    df = df.sort_values("interaction_probability", ascending=True)
    
    # Color by confidence
    color_map = {"high": "#2E8B57", "medium": "#FFD700", "low": "#FF8C00", "unknown": "#808080"}
    colors = [color_map.get(c, "#808080") for c in df.get("confidence", ["unknown"] * len(df))]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=df["target_identifier"] if "target_identifier" in df.columns else df.index.astype(str),
        x=df["interaction_probability"],
        orientation="h",
        marker_color=colors,
        text=[f"{p:.2%}" for p in df["interaction_probability"]],
        textposition="auto",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Probability: %{x:.2%}<br>"
            "Prediction: %{customdata[0]}<br>"
            "Confidence: %{customdata[1]}<br>"
            "<extra></extra>"
        ),
        customdata=list(zip(
            df["predicted_interaction"].map({1: "Interacts", 0: "No Interaction"}),
            df.get("confidence", ["unknown"] * len(df)),
        )),
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Interaction Probability",
        yaxis_title="Target",
        height=max(400, len(df) * 35 + 100),
        margin=dict(l=150, r=50, t=80, b=50),
        xaxis=dict(range=[0, 1]),
        showlegend=False,
    )
    
    # Add threshold line
    fig.add_vline(x=0.5, line_dash="dash", line_color="red", opacity=0.5)
    
    return fig


def create_target_profile_heatmap(
    predictions: list[dict[str, Any]],
    title: str = "Drug-Target Interaction Profile",
) -> go.Figure:
    """Create heatmap of drug-target interaction probabilities.
    
    Args:
        predictions: List of prediction results
        title: Chart title
        
    Returns:
        Plotly figure
    """
    if not predictions:
        return go.Figure()
    
    df = pd.DataFrame(predictions)
    df = df[df.get("success", True) == True]
    
    if df.empty:
        return go.Figure()
    
    # Pivot for heatmap
    if "drug_identifier" in df.columns and "target_identifier" in df.columns:
        pivot = df.pivot_table(
            index="drug_identifier",
            columns="target_identifier",
            values="interaction_probability",
            aggfunc="mean",
        )
    else:
        return go.Figure()
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=pivot.index,
        colorscale="RdYlGn",
        zmin=0,
        zmax=1,
        colorbar=dict(title="Interaction<br>Probability"),
        hovertemplate=(
            "Drug: %{y}<br>"
            "Target: %{x}<br>"
            "Probability: %{z:.2%}<br>"
            "<extra></extra>"
        ),
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Target",
        yaxis_title="Drug",
        height=max(400, len(pivot.index) * 30 + 150),
        width=max(600, len(pivot.columns) * 80 + 200),
        margin=dict(l=150, r=50, t=80, b=100),
    )
    
    return fig


def create_affinity_scatter(
    affinity_data: list[dict[str, Any]],
    title: str = "Binding Affinity Estimates",
) -> go.Figure:
    """Create scatter plot of binding affinity estimates.
    
    Args:
        affinity_data: List of affinity estimation results
        title: Chart title
        
    Returns:
        Plotly figure
    """
    if not affinity_data:
        return go.Figure()
    
    df = pd.DataFrame(affinity_data)
    df = df[df.get("estimated_affinity_nm").notna()]
    
    if df.empty:
        return go.Figure()
    
    df["pkd"] = -np.log10(df["estimated_affinity_nm"] * 1e-9)
    df["potency_class"] = df["estimated_affinity_nm"].apply(_classify_potency)
    
    # Color by method
    method_colors = {
        "reference": "#1f77b4",
        "rule_based": "#ff7f0e",
        "ml": "#2ca02c",
    }
    
    fig = go.Figure()
    
    for method in df["method"].unique():
        mdf = df[df["method"] == method]
        fig.add_trace(go.Scatter(
            x=mdf["target_identifier"] if "target_identifier" in mdf.columns else mdf.index,
            y=mdf["pkd"],
            mode="markers",
            name=method,
            marker=dict(
                size=12,
                color=method_colors.get(method, "#808080"),
                opacity=0.7,
            ),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "pKd: %{y:.2f}<br>"
                "Affinity: %{customdata[0]:.2f} nM<br>"
                "Method: %{customdata[1]}<br>"
                "Confidence: %{customdata[2]}<br>"
                "<extra></extra>"
            ),
            customdata=list(zip(
                mdf["estimated_affinity_nm"],
                mdf["method"],
                mdf.get("confidence", ["unknown"] * len(mdf)),
            )),
        ))
    
    # Add potency threshold lines
    for pkd_val, label in [(9, "Sub-nM"), (8, "10 nM"), (7, "100 nM"), (6, "1 µM"), (5, "10 µM")]:
        fig.add_hline(
            y=pkd_val,
            line_dash="dot",
            line_color="gray",
            opacity=0.3,
            annotation_text=label,
            annotation_position="right",
        )
    
    fig.update_layout(
        title=title,
        xaxis_title="Target",
        yaxis_title="pKd (-log10 Kd)",
        height=500,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    
    return fig


def create_feature_importance_chart(
    feature_importance: list[dict[str, Any]],
    top_n: int = 20,
    title: str = "Model Feature Importance",
) -> go.Figure:
    """Create horizontal bar chart of feature importance.
    
    Args:
        feature_importance: List of feature importance dicts
        top_n: Number of top features to show
        title: Chart title
        
    Returns:
        Plotly figure
    """
    if not feature_importance:
        return go.Figure()
    
    df = pd.DataFrame(feature_importance[:top_n])
    df = df.sort_values("importance", ascending=True)
    
    # Categorize features
    def categorize(feature: str) -> str:
        if feature.startswith("desc_"):
            return "Molecular Descriptors"
        elif feature.startswith("fp_"):
            return "Fingerprints"
        elif feature.startswith("target_"):
            return "Target Features"
        return "Other"
    
    df["category"] = df["feature"].apply(categorize)
    
    category_colors = {
        "Molecular Descriptors": "#1f77b4",
        "Fingerprints": "#ff7f0e",
        "Target Features": "#2ca02c",
        "Other": "#808080",
    }
    
    fig = go.Figure()
    
    for category in df["category"].unique():
        cdf = df[df["category"] == category]
        fig.add_trace(go.Bar(
            y=cdf["feature"],
            x=cdf["importance"],
            orientation="h",
            name=category,
            marker_color=category_colors.get(category, "#808080"),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Importance: %{x:.4f}<br>"
                "Category: %{customdata}<br>"
                "<extra></extra>"
            ),
            customdata=[category] * len(cdf),
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Feature Importance",
        yaxis_title="Feature",
        height=max(400, top_n * 25 + 100),
        margin=dict(l=200, r=50, t=80, b=50),
        barmode="stack",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    
    return fig


def create_training_history_chart(
    training_history: dict[str, Any],
    title: str = "Model Training History",
) -> go.Figure:
    """Create chart showing training metrics.
    
    Args:
        training_history: Training results dictionary
        title: Chart title
        
    Returns:
        Plotly figure
    """
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Training Metrics", "CV ROC-AUC", "Class Balance", "Feature Count"),
        specs=[[{"type": "bar"}, {"type": "indicator"}],
               [{"type": "pie"}, {"type": "indicator"}]],
    )
    
    # Training metrics
    metrics = ["train_accuracy", "train_precision", "train_recall", "train_f1", "train_roc_auc"]
    metric_values = [training_history.get(m, 0) for m in metrics]
    metric_labels = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]
    
    fig.add_trace(go.Bar(
        x=metric_labels,
        y=metric_values,
        marker_color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"],
        text=[f"{v:.3f}" for v in metric_values],
        textposition="auto",
    ), row=1, col=1)
    
    # CV ROC-AUC
    cv_mean = training_history.get("cv_roc_auc_mean", 0)
    cv_std = training_history.get("cv_roc_auc_std", 0)
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=cv_mean,
        title={"text": "CV ROC-AUC"},
        gauge={
            "axis": {"range": [0, 1]},
            "bar": {"color": "#1f77b4"},
            "steps": [
                {"range": [0, 0.5], "color": "lightgray"},
                {"range": [0.5, 0.7], "color": "yellow"},
                {"range": [0.7, 0.85], "color": "orange"},
                {"range": [0.85, 1], "color": "green"},
            ],
        },
    ), row=1, col=2)
    
    # Class balance
    n_pos = training_history.get("n_positive", 0)
    n_neg = training_history.get("n_negative", 0)
    
    fig.add_trace(go.Pie(
        labels=["Positive", "Negative"],
        values=[n_pos, n_neg],
        marker_colors=["#2ca02c", "#d62728"],
        textinfo="label+percent",
    ), row=2, col=1)
    
    # Feature count
    n_features = training_history.get("feature_count", 0)
    fig.add_trace(go.Indicator(
        mode="number",
        value=n_features,
        title={"text": "Features"},
    ), row=2, col=2)
    
    fig.update_layout(
        title=title,
        height=600,
        showlegend=False,
    )
    
    return fig


def create_drug_property_radar(
    drug_smiles: str,
    title: str = "Drug Property Profile",
) -> go.Figure:
    """Create radar chart of molecular properties.
    
    Args:
        drug_smiles: Drug SMILES
        title: Chart title
        
    Returns:
        Plotly figure
    """
    from geneai.drug_target_prediction.molecular_descriptors import calculate_molecular_descriptors
    
    desc = calculate_molecular_descriptors(drug_smiles)
    
    if not desc or desc.get("molecular_weight") is None:
        return go.Figure()
    
    # Normalize properties to 0-1 scale
    properties = {
        "MW": _normalize(desc.get("molecular_weight", 0), 100, 1000),
        "LogP": _normalize(desc.get("logp", 0), -2, 6),
        "TPSA": _normalize(desc.get("tpsa", 0), 0, 200),
        "HBD": _normalize(desc.get("hbd", 0), 0, 10),
        "HBA": _normalize(desc.get("hba", 0), 0, 15),
        "RotBonds": _normalize(desc.get("rotatable_bonds", 0), 0, 20),
        "Aromatic Rings": _normalize(desc.get("aromatic_rings", 0), 0, 6),
        "Fraction CSP3": desc.get("fraction_csp3", 0) or 0,
    }
    
    # Drug-likeness score (Lipinski)
    violations = 0
    if desc.get("molecular_weight", 0) > 500: violations += 1
    if desc.get("logp", 0) > 5: violations += 1
    if desc.get("hbd", 0) > 5: violations += 1
    if desc.get("hba", 0) > 10: violations += 1
    
    properties["Drug-Likeness"] = 1 - violations / 4
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=list(properties.values()),
        theta=list(properties.keys()),
        fill="toself",
        name="Drug Properties",
        line_color="#1f77b4",
        fillcolor="rgba(31, 119, 180, 0.3)",
    ))
    
    # Add ideal range reference
    ideal = {
        "MW": _normalize(350, 100, 1000),
        "LogP": _normalize(2.5, -2, 6),
        "TPSA": _normalize(80, 0, 200),
        "HBD": _normalize(2, 0, 10),
        "HBA": _normalize(5, 0, 15),
        "RotBonds": _normalize(5, 0, 20),
        "Aromatic Rings": _normalize(2, 0, 6),
        "Fraction CSP3": 0.5,
        "Drug-Likeness": 1.0,
    }
    
    fig.add_trace(go.Scatterpolar(
        r=list(ideal.values()),
        theta=list(ideal.keys()),
        fill="toself",
        name="Ideal Range",
        line_color="#2ca02c",
        fillcolor="rgba(44, 160, 44, 0.1)",
        line_dash="dash",
    ))
    
    fig.update_layout(
        title=title,
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1]),
        ),
        height=500,
        showlegend=True,
    )
    
    return fig


def create_interaction_network(
    predictions: list[dict[str, Any]],
    threshold: float = 0.5,
    title: str = "Drug-Target Interaction Network",
) -> go.Figure:
    """Create network graph of drug-target interactions.
    
    Args:
        predictions: List of prediction results
        threshold: Probability threshold for edges
        title: Chart title
        
    Returns:
        Plotly figure
    """
    try:
        import networkx as nx
    except ImportError:
        logger.warning("NetworkX not available for network visualization")
        return go.Figure()
    
    df = pd.DataFrame(predictions)
    df = df[df.get("success", True) == True]
    df = df[df.get("interaction_probability", 0) >= threshold]
    
    if df.empty:
        return go.Figure()
    
    # Build graph
    G = nx.Graph()
    
    drugs = df["drug_identifier"].unique() if "drug_identifier" in df.columns else []
    targets = df["target_identifier"].unique() if "target_identifier" in df.columns else []
    
    for drug in drugs:
        G.add_node(drug, type="drug")
    for target in targets:
        G.add_node(target, type="target")
    
    for _, row in df.iterrows():
        drug = row.get("drug_identifier")
        target = row.get("target_identifier")
        prob = row.get("interaction_probability", 0)
        if drug and target:
            G.add_edge(drug, target, weight=prob)
    
    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
    
    # Extract edges
    edge_x, edge_y = [], []
    edge_weights = []
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_weights.append(edge[2].get("weight", 0))
    
    # Extract nodes
    node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        node_type = G.nodes[node].get("type", "unknown")
        node_color.append("#1f77b4" if node_type == "drug" else "#ff7f0e")
        node_size.append(30 if node_type == "drug" else 25)
    
    fig = go.Figure()
    
    # Edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=1, color="rgba(128,128,128,0.5)"),
        hoverinfo="none",
        showlegend=False,
    ))
    
    # Nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(
            size=node_size,
            color=node_color,
            line=dict(width=2, color="white"),
        ),
        text=node_text,
        textposition="middle center",
        textfont=dict(size=10, color="white"),
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    ))
    
    # Legend
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode="markers",
        marker=dict(size=15, color="#1f77b4"),
        name="Drug",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode="markers",
        marker=dict(size=15, color="#ff7f0e"),
        name="Target",
        showlegend=True,
    ))
    
    fig.update_layout(
        title=title,
        showlegend=True,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=600,
        margin=dict(l=50, r=50, t=80, b=50),
    )
    
    return fig


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize value to 0-1 range."""
    if max_val == min_val:
        return 0.5
    return max(0, min(1, (value - min_val) / (max_val - min_val)))


def _classify_potency(affinity_nm: float) -> str:
    """Classify potency from affinity."""
    if affinity_nm < 1:
        return "Sub-nM"
    elif affinity_nm < 10:
        return "1-10 nM"
    elif affinity_nm < 100:
        return "10-100 nM"
    elif affinity_nm < 1000:
        return "100 nM - 1 µM"
    elif affinity_nm < 10000:
        return "1-10 µM"
    else:
        return ">10 µM"


def create_comparison_chart(
    predictions_list: list[list[dict[str, Any]]],
    labels: list[str],
    title: str = "Model Comparison",
) -> go.Figure:
    """Compare predictions from multiple models.
    
    Args:
        predictions_list: List of prediction lists from different models
        labels: Labels for each model
        title: Chart title
        
    Returns:
        Plotly figure
    """
    fig = go.Figure()
    
    for preds, label in zip(predictions_list, labels):
        df = pd.DataFrame(preds)
        df = df[df.get("success", True) == True]
        if df.empty:
            continue
        
        df = df.sort_values("interaction_probability")
        
        fig.add_trace(go.Scatter(
            x=list(range(len(df))),
            y=df["interaction_probability"],
            mode="lines+markers",
            name=label,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Target: %{customdata[1]}<br>"
                "Probability: %{y:.2%}<br>"
                "<extra></extra>"
            ),
            customdata=list(zip(
                df.get("drug_identifier", [""] * len(df)),
                df.get("target_identifier", [""] * len(df)),
            )),
        ))
    
    fig.add_hline(y=0.5, line_dash="dash", line_color="red", opacity=0.5)
    
    fig.update_layout(
        title=title,
        xaxis_title="Target Rank",
        yaxis_title="Interaction Probability",
        height=500,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    
    return fig