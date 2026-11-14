"""Protein visualization module."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import plotly.graph_objects as go
import plotly.express as px
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Structure3DView:
    """3D structure view configuration."""
    structure_id: str
    atoms: list[dict[str, Any]]
    bonds: list[tuple[int, int]] = field(default_factory=list)
    color_scheme: str = "element"  # element, chain, residue, b_factor, hydrophobicity
    representation: str = "cartoon"  # cartoon, surface, sphere, stick, line
    highlight_residues: list[dict[str, Any]] = field(default_factory=list)


class ProteinVisualizer:
    """
    Create interactive protein visualizations.
    
    Capabilities:
    - 3D structure viewer (cartoon, surface, stick)
    - Sequence feature mapping
    - Binding pocket visualization
    - Conservation mapping
    - Mutation mapping
    - Interaction network plots
    """
    
    # CPK color scheme
    ELEMENT_COLORS = {
        "C": "#909090", "N": "#3050F8", "O": "#FF0D0D", "S": "#FFFF30",
        "P": "#FF8000", "H": "#FFFFFF", "Fe": "#E06633", "Zn": "#7D80B0",
        "Mg": "#8AFF00", "Ca": "#3DFF00", "Mn": "#9C7AC7", "Cu": "#C88033",
    }
    
    # Residue hydrophobicity colors (Kyte-Doolittle)
    HYDROPHOBICITY_COLORS = {
        "I": "#FF0000", "V": "#FF4000", "L": "#FF8000", "F": "#FFC000",
        "C": "#FFFF00", "M": "#C0FF00", "A": "#80FF00", "G": "#40FF00",
        "T": "#00FF00", "S": "#00FF40", "W": "#00FF80", "Y": "#00FFC0",
        "P": "#00FFFF", "H": "#00C0FF", "E": "#0080FF", "Q": "#0040FF",
        "D": "#0000FF", "N": "#4000FF", "K": "#8000FF", "R": "#C000FF",
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_3d_structure_view(
        self,
        atoms: list[dict[str, Any]],
        color_scheme: str = "element",
        representation: str = "cartoon",
    ) -> go.Figure:
        """
        Create 3D structure visualization.
        
        Args:
            atoms: List of atom dictionaries with x, y, z, element, residue_name, chain
            color_scheme: "element", "chain", "residue", "b_factor", "hydrophobicity"
            representation: "cartoon", "surface", "sphere", "stick", "line"
            
        Returns:
            Plotly 3D figure
        """
        if not atoms:
            return go.Figure()
        
        fig = go.Figure()
        
        if representation == "cartoon":
            self._add_cartoon_representation(fig, atoms, color_scheme)
        elif representation == "surface":
            self._add_surface_representation(fig, atoms, color_scheme)
        elif representation == "sphere":
            self._add_sphere_representation(fig, atoms, color_scheme)
        elif representation == "stick":
            self._add_stick_representation(fig, atoms, color_scheme)
        elif representation == "line":
            self._add_line_representation(fig, atoms, color_scheme)
        
        fig.update_layout(
            title=f"3D Structure ({representation})",
            scene=dict(
                xaxis_title="X (Å)",
                yaxis_title="Y (Å)",
                zaxis_title="Z (Å)",
                aspectmode="data",
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.5)
                ),
            ),
            height=600,
            showlegend=True,
        )
        
        return fig
    
    def _add_cartoon_representation(
        self,
        fig: go.Figure,
        atoms: list[dict[str, Any]],
        color_scheme: str,
    ) -> None:
        """Add cartoon (secondary structure) representation."""
        # Group by chain and residue
        chains = {}
        for atom in atoms:
            chain = atom.get("chain", "A")
            res_num = atom.get("residue_num", 0)
            res_name = atom.get("residue_name", "")
            
            key = (chain, res_num, res_name)
            if key not in chains:
                chains[key] = []
            chains[key].append(atom)
        
        # Simple CA trace
        for (chain, res_num, res_name), res_atoms in chains.items():
            ca_atoms = [a for a in res_atoms if a.get("atom_name") == "CA"]
            if not ca_atoms:
                continue
            
            ca = ca_atoms[0]
            x, y, z = ca["x"], ca["y"], ca["z"]
            
            # Determine color
            color = self._get_color(ca, color_scheme)
            
            fig.add_trace(go.Scatter3d(
                x=[x], y=[y], z=[z],
                mode="markers",
                marker=dict(size=6, color=color),
                name=f"Chain {chain}",
                showlegend=False,
                hovertext=f"{res_name}{res_num} ({chain})",
                hoverinfo="text",
            ))
        
        # Add trace lines connecting CA atoms per chain
        for chain in set(a.get("chain", "A") for a in atoms):
            chain_atoms = [a for a in atoms if a.get("chain") == chain and a.get("atom_name") == "CA"]
            chain_atoms.sort(key=lambda a: a.get("residue_num", 0))
            
            if len(chain_atoms) > 1:
                x = [a["x"] for a in chain_atoms]
                y = [a["y"] for a in chain_atoms]
                z = [a["z"] for a in chain_atoms]
                
                fig.add_trace(go.Scatter3d(
                    x=x, y=y, z=z,
                    mode="lines",
                    line=dict(width=4, color="#888888"),
                    showlegend=False,
                    hoverinfo="skip",
                ))
    
    def _add_surface_representation(
        self,
        fig: go.Figure,
        atoms: list[dict[str, Any]],
        color_scheme: str,
    ) -> None:
        """Add surface representation (simplified as dense spheres)."""
        # Sample atoms for surface
        sample = atoms[::3]  # Every 3rd atom
        
        x = [a["x"] for a in sample]
        y = [a["y"] for a in sample]
        z = [a["z"] for a in sample]
        colors = [self._get_color(a, color_scheme) for a in sample]
        
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="markers",
            marker=dict(
                size=3,
                color=colors,
                opacity=0.6,
            ),
            showlegend=False,
            hoverinfo="skip",
        ))
    
    def _add_sphere_representation(
        self,
        fig: go.Figure,
        atoms: list[dict[str, Any]],
        color_scheme: str,
    ) -> None:
        """Add sphere (CPK) representation."""
        x = [a["x"] for a in atoms]
        y = [a["y"] for a in atoms]
        z = [a["z"] for a in atoms]
        colors = [self._get_color(a, color_scheme) for a in atoms]
        sizes = [self._get_vdw_radius(a.get("element", "C")) * 2 for a in atoms]
        
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="markers",
            marker=dict(
                size=sizes,
                color=colors,
                opacity=0.8,
            ),
            showlegend=False,
            hovertext=[f"{a.get('residue_name','')}{a.get('residue_num','')} {a.get('atom_name','')}" for a in atoms],
            hoverinfo="text",
        ))
    
    def _add_stick_representation(
        self,
        fig: go.Figure,
        atoms: list[dict[str, Any]],
        color_scheme: str,
    ) -> None:
        """Add stick representation (bonds)."""
        # Simple: connect nearby atoms
        # In reality, would use bond information from structure
        pass
    
    def _add_line_representation(
        self,
        fig: go.Figure,
        atoms: list[dict[str, Any]],
        color_scheme: str,
    ) -> None:
        """Add line (backbone trace) representation."""
        self._add_cartoon_representation(fig, atoms, color_scheme)
    
    def _get_color(self, atom: dict[str, Any], scheme: str) -> str:
        """Get color for atom based on scheme."""
        if scheme == "element":
            element = atom.get("element", "C")
            return self.ELEMENT_COLORS.get(element, "#909090")
        elif scheme == "chain":
            chain = atom.get("chain", "A")
            chain_colors = {"A": "#1f77b4", "B": "#ff7f0e", "C": "#2ca02c", "D": "#d62728"}
            return chain_colors.get(chain, "#888888")
        elif scheme == "residue":
            res = atom.get("residue_name", "")
            return self.HYDROPHOBICITY_COLORS.get(res, "#888888")
        elif scheme == "hydrophobicity":
            res = atom.get("residue_name", "")
            return self.HYDROPHOBICITY_COLORS.get(res, "#888888")
        elif scheme == "b_factor":
            b = atom.get("b_factor", 0)
            # Blue (low) to Red (high)
            intensity = min(b / 100, 1.0)
            r = int(255 * intensity)
            b = int(255 * (1 - intensity))
            return f"rgb({r},0,{b})"
        return "#909090"
    
    def _get_vdw_radius(self, element: str) -> float:
        """Get van der Waals radius for element."""
        radii = {"H": 1.2, "C": 1.7, "N": 1.55, "O": 1.52, "S": 1.8, "P": 1.8}
        return radii.get(element, 1.5)
    
    def create_sequence_feature_plot(
        self,
        sequence: str,
        features: dict[str, list[dict[str, Any]]],
        title: str = "Protein Sequence Features",
    ) -> go.Figure:
        """
        Create linear sequence feature plot.
        
        Args:
            sequence: Protein sequence
            features: Dict of feature_type -> list of {start, end, name, color}
            title: Plot title
            
        Returns:
            Plotly figure
        """
        fig = go.Figure()
        
        seq_len = len(sequence)
        
        # Sequence track
        fig.add_shape(
            type="rect",
            x0=0, x1=seq_len,
            y0=0.8, y1=1.0,
            fillcolor="#E0E0E0",
            line=dict(color="#999999"),
        )
        
        # Add residue letters (every 10th)
        for i in range(0, seq_len, 10):
            fig.add_annotation(
                x=i + 0.5, y=0.9,
                text=sequence[i],
                showarrow=False,
                font=dict(size=8, family="monospace"),
            )
        
        # Feature tracks
        y_positions = {
            "domains": 0.6,
            "motifs": 0.4,
            "ptm": 0.2,
            "transmembrane": 0.0,
        }
        
        track_height = 0.15
        
        for feature_type, feature_list in features.items():
            y_base = y_positions.get(feature_type, 0)
            
            for feat in feature_list:
                start = feat.get("start", 0)
                end = feat.get("end", start + 1)
                name = feat.get("name", feature_type)
                color = feat.get("color", "#1f77b4")
                
                fig.add_shape(
                    type="rect",
                    x0=start, x1=end,
                    y0=y_base, y1=y_base + track_height,
                    fillcolor=color,
                    line=dict(color=color),
                    opacity=0.8,
                )
                
                # Label
                if end - start > 10:
                    fig.add_annotation(
                        x=(start + end) / 2,
                        y=y_base + track_height / 2,
                        text=name,
                        showarrow=False,
                        font=dict(size=8, color="white"),
                    )
        
        fig.update_layout(
            title=title,
            xaxis=dict(title="Residue Position", range=[-1, seq_len + 1]),
            yaxis=dict(
                range=[-0.2, 1.2],
                showticklabels=False,
                showgrid=False,
            ),
            height=300,
            showlegend=False,
        )
        
        return fig
    
    def create_interaction_network_plot(
        self,
        interactions: list[dict[str, Any]],
        center_protein: str | None = None,
        layout: str = "spring",
    ) -> go.Figure:
        """
        Create protein interaction network plot.
        
        Args:
            interactions: List of interaction dicts with protein_a, protein_b, score
            center_protein: Center protein to highlight
            layout: "spring", "circular", "kamada_kawai"
            
        Returns:
            Plotly figure
        """
        if not interactions:
            return go.Figure()
        
        # Build network
        import networkx as nx
        
        G = nx.Graph()
        for inter in interactions:
            a = inter.get("protein_a", "")
            b = inter.get("protein_b", "")
            score = inter.get("score", 0.5)
            if a and b:
                G.add_edge(a, b, weight=score)
        
        if len(G.nodes()) == 0:
            return go.Figure()
        
        # Layout
        if layout == "spring":
            pos = nx.spring_layout(G, k=1, iterations=50)
        elif layout == "circular":
            pos = nx.circular_layout(G)
        elif layout == "kamada_kawai":
            pos = nx.kamada_kawai_layout(G)
        else:
            pos = nx.spring_layout(G)
        
        # Node trace
        node_x = [pos[node][0] for node in G.nodes()]
        node_y = [pos[node][1] for node in G.nodes()]
        
        node_colors = []
        node_sizes = []
        node_text = []
        
        for node in G.nodes():
            if node == center_protein:
                node_colors.append("#d62728")
                node_sizes.append(20)
            else:
                degree = G.degree(node)
                node_colors.append("#1f77b4")
                node_sizes.append(10 + degree * 2)
            
            node_text.append(f"{node}<br>Degree: {G.degree(node)}")
        
        # Edge trace
        edge_x = []
        edge_y = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        fig = go.Figure()
        
        # Edges
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=0.5, color="#888888"),
            hoverinfo="none",
            showlegend=False,
        ))
        
        # Nodes
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            marker=dict(
                size=node_sizes,
                color=node_colors,
                line=dict(width=2, color="white"),
            ),
            text=[n for n in G.nodes()],
            textposition="top center",
            hovertext=node_text,
            hoverinfo="text",
            showlegend=False,
        ))
        
        fig.update_layout(
            title=f"Protein Interaction Network{f' (Center: {center_protein})' if center_protein else ''}",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=600,
            showlegend=False,
        )
        
        return fig
    
    def create_conservation_heatmap(
        self,
        sequence: str,
        conservation_scores: list[float],
        title: str = "Sequence Conservation",
    ) -> go.Figure:
        """Create conservation heatmap along sequence."""
        if len(sequence) != len(conservation_scores):
            # Interpolate or truncate
            min_len = min(len(sequence), len(conservation_scores))
            sequence = sequence[:min_len]
            conservation_scores = conservation_scores[:min_len]
        
        # Create 10-residue windows
        window = 10
        n_windows = len(sequence) // window
        
        window_scores = []
        window_labels = []
        
        for i in range(n_windows):
            start = i * window
            end = start + window
            window_seq = sequence[start:end]
            window_score = np.mean(conservation_scores[start:end])
            window_scores.append(window_score)
            window_labels.append(f"{start+1}-{end}")
        
        fig = go.Figure(go.Heatmap(
            z=[window_scores],
            x=window_labels,
            y=["Conservation"],
            colorscale="RdYlGn",
            zmin=0, zmax=1,
            colorbar=dict(title="Score"),
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Residue Window",
            height=200,
        )
        
        return fig


def create_3d_structure_view(
    atoms: list[dict[str, Any]],
    color_scheme: str = "element",
    representation: str = "cartoon",
) -> go.Figure:
    """Convenience function for 3D structure view."""
    visualizer = ProteinVisualizer()
    return visualizer.create_3d_structure_view(atoms, color_scheme, representation)


def create_sequence_feature_plot(
    sequence: str,
    features: dict[str, list[dict[str, Any]]],
    title: str = "Protein Sequence Features",
) -> go.Figure:
    """Convenience function for a linear protein sequence feature plot."""
    return ProteinVisualizer().create_sequence_feature_plot(sequence, features, title)


def create_interaction_network_plot(
    interactions: list[dict[str, Any]],
    center_protein: str | None = None,
    layout: str = "spring",
) -> go.Figure:
    """Convenience function for a protein interaction network plot."""
    return ProteinVisualizer().create_interaction_network_plot(interactions, center_protein, layout)


def create_conservation_heatmap(
    sequence: str,
    conservation_scores: list[float],
    title: str = "Sequence Conservation",
) -> go.Figure:
    """Convenience function for a sequence conservation heatmap."""
    return ProteinVisualizer().create_conservation_heatmap(sequence, conservation_scores, title)