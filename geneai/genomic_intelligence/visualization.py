"""Genomic visualization module."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)


@dataclass
class GenomeTrack:
    """Genome browser track configuration."""
    name: str
    data: list[dict[str, Any]]
    track_type: str  # "variants", "genes", "coverage", "conservation", "peaks"
    color: str = "#1f77b4"
    height: int = 100
    y_range: tuple[float, float] | None = None


class GenomicVisualizer:
    """
    Create interactive genomic visualizations.
    
    Capabilities:
    - Genome browser style tracks
    - Variant effect plots
    - Gene structure diagrams
    - Conservation tracks
    - Coverage plots
    - Manhattan/QQ plots for GWAS
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_genome_browser(
        self,
        chrom: str,
        start: int,
        end: int,
        tracks: list[GenomeTrack],
        title: str | None = None,
    ) -> go.Figure:
        """
        Create a multi-track genome browser view.
        
        Args:
            chrom: Chromosome
            start: Start position
            end: End position
            tracks: List of GenomeTrack objects
            title: Plot title
            
        Returns:
            Plotly figure
        """
        num_tracks = len(tracks)
        if num_tracks == 0:
            return go.Figure()
        
        # Calculate subplot heights
        total_height = sum(t.height for t in tracks)
        row_heights = [t.height / total_height for t in tracks]
        
        fig = make_subplots(
            rows=num_tracks,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=row_heights,
            subplot_titles=[t.name for t in tracks],
        )
        
        for i, track in enumerate(tracks, 1):
            self._add_track(fig, track, i)
        
        # Update x-axis
        fig.update_xaxes(
            range=[start, end],
            title_text=f"Position on {chrom} (bp)",
            row=num_tracks,
            col=1,
        )
        
        fig.update_layout(
            title=title or f"Genome Browser: {chrom}:{start:,}-{end:,}",
            height=total_height + 100,
            showlegend=False,
            hovermode="x unified",
        )
        
        return fig
    
    def _add_track(self, fig: go.Figure, track: GenomeTrack, row: int) -> None:
        """Add a track to the genome browser."""
        data = track.data
        
        if track.track_type == "variants":
            self._add_variant_track(fig, data, track, row)
        elif track.track_type == "genes":
            self._add_gene_track(fig, data, track, row)
        elif track.track_type == "coverage":
            self._add_coverage_track(fig, data, track, row)
        elif track.track_type == "conservation":
            self._add_conservation_track(fig, data, track, row)
        elif track.track_type == "peaks":
            self._add_peak_track(fig, data, track, row)
        elif track.track_type == "scatter":
            self._add_scatter_track(fig, data, track, row)
    
    def _add_variant_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Add variant track (vertical lines or scatter)."""
        if not data:
            return
        
        positions = [d.get("pos", d.get("position", 0)) for d in data]
        colors = []
        for d in data:
            impact = d.get("impact", "").upper()
            if impact == "HIGH":
                colors.append("#d62728")  # red
            elif impact == "MODERATE":
                colors.append("#ff7f0e")  # orange
            elif impact == "LOW":
                colors.append("#2ca02c")  # green
            else:
                colors.append(track.color)
        
        fig.add_trace(
            go.Scatter(
                x=positions,
                y=[1] * len(positions),
                mode="markers",
                marker=dict(
                    size=8,
                    color=colors,
                    symbol="line-ns",
                    line=dict(width=2),
                ),
                name=track.name,
                hovertext=[self._variant_hover(d) for d in data],
                hoverinfo="text",
            ),
            row=row,
            col=1,
        )
        
        if track.y_range:
            fig.update_yaxes(range=track.y_range, row=row, col=1)
        else:
            fig.update_yaxes(range=[0, 2], row=row, col=1, showticklabels=False)
    
    def _add_gene_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Add gene structure track."""
        shapes = []
        annotations = []
        
        for gene in data:
            gene_start = gene.get("start", 0)
            gene_end = gene.get("end", 0)
            strand = gene.get("strand", 1)
            symbol = gene.get("symbol", gene.get("name", ""))
            
            # Gene body
            shapes.append({
                "type": "rect",
                "x0": gene_start,
                "x1": gene_end,
                "y0": 0.3,
                "y1": 0.7,
                "fillcolor": track.color,
                "line": {"color": track.color, "width": 1},
                "layer": "below",
            })
            
            # Arrow for strand
            if strand == 1:
                arrow_x = gene_end
                arrow_dir = "right"
            else:
                arrow_x = gene_start
                arrow_dir = "left"
            
            shapes.append({
                "type": "path",
                "path": self._arrow_path(arrow_x, 0.5, arrow_dir, 0.02 * (gene_end - gene_start)),
                "fillcolor": track.color,
                "line": {"color": track.color},
            })
            
            # Gene label
            annotations.append({
                "x": (gene_start + gene_end) / 2,
                "y": 1.1,
                "text": symbol,
                "showarrow": False,
                "font": {"size": 10},
                "xref": f"x{row if row > 1 else ''}",
                "yref": f"y{row if row > 1 else ''}",
            })
        
        for shape in shapes:
            fig.add_shape(shape, row=row, col=1)
        
        fig.update_layout(annotations=fig.layout.annotations + tuple(annotations))
        
        if track.y_range:
            fig.update_yaxes(range=track.y_range, row=row, col=1)
        else:
            fig.update_yaxes(range=[0, 1.5], row=row, col=1, showticklabels=False)
    
    def _add_coverage_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Add coverage/read depth track."""
        if not data:
            return
        
        # Expect data as [{"pos": x, "coverage": y}, ...] or intervals
        if "coverage" in data[0]:
            x = [d["pos"] for d in data]
            y = [d["coverage"] for d in data]
        else:
            # Interval format: [{"start": s, "end": e, "value": v}, ...]
            x, y = [], []
            for d in data:
                x.extend([d["start"], d["end"]])
                y.extend([d.get("value", 1), d.get("value", 1)])
        
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                fill="tozeroy",
                line=dict(color=track.color, width=0.5),
                fillcolor=f"rgba({self._hex_to_rgb(track.color)}, 0.3)",
                name=track.name,
            ),
            row=row,
            col=1,
        )
    
    def _add_conservation_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Add conservation score track."""
        self._add_coverage_track(fig, data, track, row)
    
    def _add_peak_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Add peak track (ChIP-seq, ATAC-seq peaks)."""
        shapes = []
        for peak in data:
            shapes.append({
                "type": "rect",
                "x0": peak.get("start", 0),
                "x1": peak.get("end", 0),
                "y0": 0.2,
                "y1": 0.8,
                "fillcolor": track.color,
                "line": {"color": track.color, "width": 0.5},
                "opacity": 0.7,
            })
        
        for shape in shapes:
            fig.add_shape(shape, row=row, col=1)
        
        fig.update_yaxes(range=[0, 1], row=row, col=1, showticklabels=False)
    
    def _add_scatter_track(
        self,
        fig: go.Figure,
        data: list[dict[str, Any]],
        track: GenomeTrack,
        row: int,
    ) -> None:
        """Generic scatter track."""
        x = [d.get("x", d.get("pos", 0)) for d in data]
        y = [d.get("y", d.get("value", 0)) for d in data]
        
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                marker=dict(size=6, color=track.color),
                name=track.name,
            ),
            row=row,
            col=1,
        )
    
    def create_variant_effect_plot(
        self,
        variants: list[dict[str, Any]],
        title: str = "Variant Effect Predictions",
    ) -> go.Figure:
        """Create variant effect prediction scatter plot."""
        if not variants:
            return go.Figure()
        
        fig = go.Figure()
        
        # Group by consequence
        consequence_groups = {}
        for v in variants:
            cons = v.get("consequence", "unknown")
            if cons not in consequence_groups:
                consequence_groups[cons] = []
            consequence_groups[cons].append(v)
        
        colors = px.colors.qualitative.Set1
        for i, (cons, vars_list) in enumerate(consequence_groups.items()):
            x = [v.get("sift_score", 0.5) for v in vars_list]
            y = [v.get("polyphen_score", 0.5) for v in vars_list]
            
            fig.add_trace(go.Scatter(
                x=x,
                y=y,
                mode="markers",
                name=cons,
                marker=dict(size=8, color=colors[i % len(colors)]),
                text=[v.get("gene_symbol", "") for v in vars_list],
                hoverinfo="text+x+y",
            ))
        
        fig.update_layout(
            title=title,
            xaxis_title="SIFT Score (lower = more deleterious)",
            yaxis_title="PolyPhen Score (higher = more damaging)",
            xaxis=dict(range=[0, 1]),
            yaxis=dict(range=[0, 1]),
            hovermode="closest",
        )
        
        return fig
    
    def create_manhattan_plot(
        self,
        gwas_data: list[dict[str, Any]],
        title: str = "GWAS Manhattan Plot",
        significance_threshold: float = 5e-8,
    ) -> go.Figure:
        """Create Manhattan plot for GWAS results."""
        if not gwas_data:
            return go.Figure()
        
        # Expect: chrom, pos, pvalue, gene (optional)
        chroms = sorted(set(d.get("chrom", "1") for d in gwas_data))
        chrom_order = {c: i for i, c in enumerate(chroms)}
        
        x_positions = []
        y_values = []
        colors = []
        hover_texts = []
        
        cumulative_pos = 0
        chrom_offsets = {}
        
        for chrom in chroms:
            chrom_offsets[chrom] = cumulative_pos
            chrom_data = [d for d in gwas_data if d.get("chrom") == chrom]
            max_pos = max(d.get("pos", 0) for d in chrom_data) if chrom_data else 0
            cumulative_pos += max_pos + 1_000_000  # Gap between chromosomes
        
        for d in gwas_data:
            chrom = d.get("chrom", "1")
            pos = d.get("pos", 0)
            pval = d.get("pvalue", 1.0)
            
            x = chrom_offsets[chrom] + pos
            y = -np.log10(pval) if pval > 0 else 0
            
            x_positions.append(x)
            y_values.append(y)
            
            if pval <= significance_threshold:
                colors.append("#d62728")
            else:
                colors.append("#1f77b4" if chrom_order[chrom] % 2 == 0 else "#ff7f0e")
            
            hover_texts.append(
                f"Gene: {d.get('gene', 'N/A')}<br>"
                f"Chr: {chrom}<br>"
                f"Pos: {pos:,}<br>"
                f"P: {pval:.2e}"
            )
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x_positions,
            y=y_values,
            mode="markers",
            marker=dict(size=4, color=colors, opacity=0.7),
            hovertext=hover_texts,
            hoverinfo="text",
            showlegend=False,
        ))
        
        # Significance line
        fig.add_hline(
            y=-np.log10(significance_threshold),
            line_dash="dash",
            line_color="red",
            annotation_text=f"P = {significance_threshold:.0e}",
        )
        
        # Chromosome labels
        tick_positions = []
        tick_labels = []
        for chrom in chroms:
            chrom_data = [d for d in gwas_data if d.get("chrom") == chrom]
            if chrom_data:
                mid = chrom_offsets[chrom] + max(d.get("pos", 0) for d in chrom_data) / 2
                tick_positions.append(mid)
                tick_labels.append(chrom.replace("chr", ""))
        
        fig.update_layout(
            title=title,
            xaxis=dict(
                tickmode="array",
                tickvals=tick_positions,
                ticktext=tick_labels,
                title="Chromosome",
            ),
            yaxis_title="-log10(P-value)",
            height=500,
        )
        
        return fig
    
    def create_qq_plot(
        self,
        pvalues: list[float],
        title: str = "GWAS Q-Q Plot",
    ) -> go.Figure:
        """Create Q-Q plot for GWAS p-values."""
        import numpy as np
        
        observed = -np.log10(np.sort(pvalues))
        n = len(observed)
        expected = -np.log10(np.arange(1, n + 1) / (n + 1))
        
        fig = go.Figure()
        
        # Expected line
        fig.add_trace(go.Scatter(
            x=expected,
            y=expected,
            mode="lines",
            line=dict(color="gray", dash="dash"),
            name="Expected",
        ))
        
        # Observed
        fig.add_trace(go.Scatter(
            x=expected,
            y=observed,
            mode="markers",
            marker=dict(size=4, color="#1f77b4"),
            name="Observed",
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Expected -log10(P)",
            yaxis_title="Observed -log10(P)",
            height=500,
        )
        
        return fig
    
    def _variant_hover(self, variant: dict[str, Any]) -> str:
        """Generate hover text for variant."""
        parts = []
        if variant.get("gene_symbol"):
            parts.append(f"Gene: {variant['gene_symbol']}")
        if variant.get("consequence"):
            parts.append(f"Consequence: {variant['consequence']}")
        if variant.get("impact"):
            parts.append(f"Impact: {variant['impact']}")
        if variant.get("protein_change"):
            parts.append(f"Protein: {variant['protein_change']}")
        if variant.get("gnomad_af"):
            parts.append(f"gnomAD AF: {variant['gnomad_af']:.4f}")
        if variant.get("clinvar_significance"):
            parts.append(f"ClinVar: {variant['clinvar_significance']}")
        return "<br>".join(parts)
    
    def _arrow_path(self, x: float, y: float, direction: str, size: float) -> str:
        """Generate SVG path for arrow."""
        if direction == "right":
            return f"M {x} {y-size} L {x+size} {y} L {x} {y+size} Z"
        else:
            return f"M {x} {y-size} L {x-size} {y} L {x} {y+size} Z"
    
    def _hex_to_rgb(self, hex_color: str) -> str:
        """Convert hex color to RGB string."""
        hex_color = hex_color.lstrip("#")
        return ",".join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))


# Import numpy for Manhattan/QQ plots
import numpy as np


def create_genome_browser(
    chrom: str,
    start: int,
    end: int,
    tracks: list[GenomeTrack],
    title: str | None = None,
) -> go.Figure:
    """Convenience function for genome browser."""
    visualizer = GenomicVisualizer()
    return visualizer.create_genome_browser(chrom, start, end, tracks, title)


def create_variant_effect_plot(
    variants: list[dict[str, Any]],
    title: str = "Variant Effect Predictions",
) -> go.Figure:
    """Convenience function for a variant effect scatter plot."""
    return GenomicVisualizer().create_variant_effect_plot(variants, title)


def create_manhattan_plot(
    gwas_data: list[dict[str, Any]],
    title: str = "GWAS Manhattan Plot",
    significance_threshold: float = 5e-8,
) -> go.Figure:
    """Convenience function for a GWAS Manhattan plot."""
    return GenomicVisualizer().create_manhattan_plot(gwas_data, title, significance_threshold)


def create_qq_plot(
    pvalues: list[float],
    title: str = "GWAS Q-Q Plot",
) -> go.Figure:
    """Convenience function for a GWAS Q-Q plot."""
    return GenomicVisualizer().create_qq_plot(pvalues, title)