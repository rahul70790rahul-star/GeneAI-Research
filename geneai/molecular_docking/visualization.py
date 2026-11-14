"""Visualization for docking results: 3D poses, interaction diagrams."""
from __future__ import annotations

import logging
import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, Draw, rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem import rdMolAlign

logger = logging.getLogger(__name__)


@dataclass
class VisualizationConfig:
    """Configuration for visualization."""
    width: int = 800
    height: int = 600
    background_color: str = "white"
    show_hydrogens: bool = False
    show_atom_indices: bool = False
    show_residue_labels: bool = True
    interaction_cutoff: float = 4.0


class PoseVisualizer:
    """
    Visualize docking poses in 3D and 2D.
    """
    
    def __init__(self, config: VisualizationConfig | None = None):
        self.config = config or VisualizationConfig()
        self.logger = logging.getLogger(__name__)
    
    def create_3d_view(
        self,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
        interactions: dict[str, list[dict]] | None = None,
        output_path: str | None = None,
    ) -> str:
        """
        Create 3D visualization using py3Dmol (returns HTML).
        
        Requires: pip install py3dmol
        """
        try:
            import py3Dmol
        except ImportError:
            self.logger.warning("py3Dmol not installed. Install with: pip install py3dmol")
            return self._create_3d_view_fallback(receptor_mol, ligand_mol, pose_coords, output_path)
        
        viewer = py3Dmol.view(
            width=self.config.width,
            height=self.config.height,
        )
        
        # Add receptor
        rec_pdb = Chem.MolToPDBBlock(receptor_mol)
        viewer.addModel(rec_pdb, "pdb", {"keepH": False})
        viewer.setStyle({"model": -1}, {
            "cartoon": {"color": "spectrum", "thickness": 0.5},
            "stick": {"radius": 0.2},
        })
        
        # Add ligand
        if pose_coords is not None:
            lig_mol = Chem.Mol(ligand_mol)
            conf = lig_mol.GetConformer()
            for i, coord in enumerate(pose_coords):
                conf.SetAtomPosition(i, coord)
        else:
            lig_mol = ligand_mol
        
        lig_pdb = Chem.MolToPDBBlock(lig_mol)
        viewer.addModel(lig_pdb, "pdb")
        viewer.setStyle({"model": -1, "chain": "L"}, {
            "stick": {"radius": 0.5, "colorscheme": "greenCarbon"},
            "sphere": {"radius": 0.3},
        })
        
        # Highlight interactions
        if interactions:
            self._add_interaction_visualization(viewer, interactions, receptor_mol, lig_mol)
        
        viewer.zoomTo()
        viewer.render()
        
        html = viewer._make_html()
        
        if output_path:
            Path(output_path).write_text(html)
        
        return html
    
    def _add_interaction_visualization(
        self,
        viewer,
        interactions: dict[str, list[dict]],
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ):
        """Add interaction lines and labels to 3D view."""
        # Color scheme for interactions
        colors = {
            "hydrogen_bonds": "red",
            "hydrophobic": "orange",
            "pi_stacking": "purple",
            "salt_bridges": "blue",
            "halogen_bonds": "green",
        }
        
        for int_type, int_list in interactions.items():
            color = colors.get(int_type, "gray")
            
            for inter in int_list:
                lig_atom_idx = inter.get("ligand_atom")
                rec_atom_idx = inter.get("receptor_atom")
                
                if lig_atom_idx is not None and rec_atom_idx is not None:
                    # Get coordinates
                    lig_conf = ligand_mol.GetConformer()
                    rec_conf = receptor_mol.GetConformer()
                    
                    lig_pos = lig_conf.GetAtomPosition(lig_atom_idx)
                    rec_pos = rec_conf.GetAtomPosition(rec_atom_idx)
                    
                    # Add line
                    viewer.addLine({
                        "start": {"x": lig_pos.x, "y": lig_pos.y, "z": lig_pos.z},
                        "end": {"x": rec_pos.x, "y": rec_pos.y, "z": rec_pos.z},
                        "color": color,
                        "dashed": True,
                    })
    
    def _create_3d_view_fallback(
        self,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        pose_coords: np.ndarray | None,
        output_path: str | None,
    ) -> str:
        """Fallback 3D visualization using RDKit's 2D depiction."""
        # Create 2D depiction with pose overlay
        img = self.create_2d_interaction_diagram(receptor_mol, ligand_mol, pose_coords, interactions=None)
        
        # Convert to base64 HTML
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        html = f"""
        <html>
        <body>
        <h3>Docking Pose (2D Fallback)</h3>
        <img src="data:image/png;base64,{img_str}" width="{self.config.width}" height="{self.config.height}">
        </body>
        </html>
        """
        
        if output_path:
            Path(output_path).write_text(html)
        
        return html
    
    def create_2d_interaction_diagram(
        self,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
        interactions: dict[str, list[dict]] | None = None,
        output_path: str | None = None,
    ) -> "PIL.Image.Image":
        """
        Create 2D interaction diagram (LigPlot+ style).
        
        Returns PIL Image.
        """
        from PIL import Image
        
        # Prepare ligand for 2D drawing
        lig_draw = Chem.Mol(ligand_mol)
        if pose_coords is not None:
            conf = lig_draw.GetConformer()
            for i, coord in enumerate(pose_coords):
                conf.SetAtomPosition(i, coord)
        
        # Generate 2D coordinates for ligand
        rdDepictor.Compute2DCoords(lig_draw)
        
        # Create drawing
        drawer = rdMolDraw2D.MolDraw2DCairo(
            self.config.width,
            self.config.height,
        )
        
        # Highlight interacting atoms
        highlight_atoms = []
        highlight_colors = {}
        
        if interactions:
            for int_type, int_list in interactions.items():
                for inter in int_list:
                    lig_atom = inter.get("ligand_atom")
                    if lig_atom is not None:
                        highlight_atoms.append(lig_atom)
                        # Color by interaction type
                        if int_type == "hydrogen_bonds":
                            highlight_colors[lig_atom] = (1.0, 0.0, 0.0)  # Red
                        elif int_type == "hydrophobic":
                            highlight_colors[lig_atom] = (1.0, 0.5, 0.0)  # Orange
                        elif int_type == "pi_stacking":
                            highlight_colors[lig_atom] = (0.5, 0.0, 1.0)  # Purple
                        elif int_type == "salt_bridges":
                            highlight_colors[lig_atom] = (0.0, 0.0, 1.0)  # Blue
                        else:
                            highlight_colors[lig_atom] = (0.5, 0.5, 0.5)  # Gray
        
        drawer.DrawMolecule(
            lig_draw,
            highlightAtoms=highlight_atoms,
            highlightAtomColors=highlight_colors,
        )
        drawer.FinishDrawing()
        
        # Get image
        png_data = drawer.GetDrawingText()
        img = Image.open(BytesIO(png_data))
        
        if output_path:
            img.save(output_path)
        
        return img
    
    def create_interaction_schematic(
        self,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        interactions: dict[str, list[dict]],
        output_path: str | None = None,
    ) -> "PIL.Image.Image":
        """
        Create schematic interaction diagram showing residue-level interactions.
        """
        from PIL import Image, ImageDraw, ImageFont
        
        # Create canvas
        img = Image.new("RGB", (self.config.width, self.config.height), "white")
        draw = ImageDraw.Draw(img)
        
        # Try to load font
        try:
            font = ImageFont.truetype("arial.ttf", 12)
            font_small = ImageFont.truetype("arial.ttf", 10)
        except Exception:
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Group interactions by residue
        residue_interactions = {}
        for int_type, int_list in interactions.items():
            for inter in int_list:
                rec_atom = inter.get("receptor_atom")
                if rec_atom is not None:
                    # In real implementation, map atom index to residue
                    res_id = f"RES{rec_atom}"
                    if res_id not in residue_interactions:
                        residue_interactions[res_id] = []
                    residue_interactions[res_id].append({
                        "type": int_type,
                        "details": inter,
                    })
        
        # Draw residue nodes and interactions
        y_start = 50
        x_center = self.config.width // 2
        spacing = 40
        
        # Draw ligand in center
        draw.ellipse([x_center - 50, y_start - 30, x_center + 50, y_start + 30], 
                     fill="lightgreen", outline="darkgreen", width=2)
        draw.text((x_center, y_start), "LIGAND", fill="black", font=font, anchor="mm")
        
        # Draw residues around ligand
        residues = list(residue_interactions.keys())
        for i, res_id in enumerate(residues):
            angle = 2 * np.pi * i / len(residues)
            radius = 150
            x = x_center + radius * np.cos(angle)
            y = y_start + radius * np.sin(angle)
            
            # Draw residue node
            int_types = [inter["type"] for inter in residue_interactions[res_id]]
            color = self._get_residue_color(int_types)
            
            draw.ellipse([x - 40, y - 25, x + 40, y + 25], 
                         fill=color, outline="black", width=2)
            draw.text((x, y), res_id, fill="black", font=font, anchor="mm")
            
            # Draw interaction lines to ligand
            draw.line([(x_center, y_start), (x, y)], fill="gray", width=1, joint="curve")
            
            # Draw interaction type labels
            label_y = y + 30
            for int_type in set(int_types):
                draw.text((x, label_y), int_type.replace("_", " ").title(), 
                          fill="black", font=font_small, anchor="mm")
                label_y += 15
        
        if output_path:
            img.save(output_path)
        
        return img
    
    def _get_residue_color(self, int_types: list[str]) -> str:
        """Get color for residue based on interaction types."""
        if "hydrogen_bonds" in int_types:
            return "#FFCCCC"  # Light red
        elif "salt_bridges" in int_types:
            return "#CCCCFF"  # Light blue
        elif "pi_stacking" in int_types:
            return "#E6CCFF"  # Light purple
        elif "hydrophobic" in int_types:
            return "#FFE6CC"  # Light orange
        else:
            return "#E6E6E6"  # Light gray
    
    def create_pose_comparison_grid(
        self,
        poses: list,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol | None = None,
        n_cols: int = 4,
        output_path: str | None = None,
    ) -> "PIL.Image.Image":
        """
        Create grid of pose images for comparison.
        """
        from PIL import Image
        
        n_poses = len(poses)
        n_rows = (n_poses + n_cols - 1) // n_cols
        
        cell_width = 300
        cell_height = 300
        img_width = n_cols * cell_width
        img_height = n_rows * cell_height
        
        grid_img = Image.new("RGB", (img_width, img_height), "white")
        
        for i, pose in enumerate(poses):
            row = i // n_cols
            col = i % n_cols
            
            x = col * cell_width
            y = row * cell_height
            
            # Create individual pose image
            pose_img = self._create_single_pose_image(
                pose, ligand_mol, receptor_mol,
                width=cell_width - 20, height=cell_height - 40
            )
            
            # Paste into grid
            grid_img.paste(pose_img, (x + 10, y + 10))
            
            # Add label
            draw = ImageDraw.Draw(grid_img)
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()
            
            label = f"Pose {i+1}: {pose.score:.2f} kcal/mol"
            draw.text((x + 10, y + 10), label, fill="black", font=font)
        
        if output_path:
            grid_img.save(output_path)
        
        return grid_img
    
    def _create_single_pose_image(
        self,
        pose,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol | None,
        width: int = 300,
        height: int = 300,
    ) -> "PIL.Image.Image":
        """Create image for single pose."""
        from PIL import Image
        
        lig_draw = Chem.Mol(ligand_mol)
        if pose.coordinates:
            conf = lig_draw.GetConformer()
            for i, coord in enumerate(pose.coordinates):
                conf.SetAtomPosition(i, coord)
        
        rdDepictor.Compute2DCoords(lig_draw)
        
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        
        # Highlight interacting atoms
        highlight_atoms = []
        highlight_colors = {}
        
        if pose.interactions:
            for int_type, int_list in pose.interactions.items():
                for inter in int_list:
                    lig_atom = inter.get("ligand_atom")
                    if lig_atom is not None:
                        highlight_atoms.append(lig_atom)
                        if int_type == "hydrogen_bonds":
                            highlight_colors[lig_atom] = (1.0, 0.0, 0.0)
                        elif int_type == "hydrophobic":
                            highlight_colors[lig_atom] = (1.0, 0.5, 0.0)
                        elif int_type == "pi_stacking":
                            highlight_colors[lig_atom] = (0.5, 0.0, 1.0)
                        elif int_type == "salt_bridges":
                            highlight_colors[lig_atom] = (0.0, 0.0, 1.0)
                        else:
                            highlight_colors[lig_atom] = (0.5, 0.5, 0.5)
        
        drawer.DrawMolecule(
            lig_draw,
            highlightAtoms=highlight_atoms,
            highlightAtomColors=highlight_colors,
        )
        drawer.FinishDrawing()
        
        png_data = drawer.GetDrawingText()
        return Image.open(BytesIO(png_data))
    
    def export_pymol_session(
        self,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        poses: list,
        output_path: str,
    ):
        """Export PyMOL session script for interactive viewing."""
        script_lines = []
        
        # Load receptor
        script_lines.append("# Receptor")
        script_lines.append("load receptor.pdb, receptor")
        script_lines.append("show cartoon, receptor")
        script_lines.append("color spectrum, receptor")
        
        # Load each pose
        for i, pose in enumerate(poses):
            pose_name = f"ligand_pose_{i+1}"
            script_lines.append(f"\n# Pose {i+1} (Score: {pose.score:.2f})")
            script_lines.append(f"load {pose_name}.pdb, {pose_name}")
            script_lines.append(f"show sticks, {pose_name}")
            script_lines.append(f"color green, {pose_name}")
        
        # Interaction visualization
        script_lines.append("\n# Interactions")
        for i, pose in enumerate(poses):
            pose_name = f"ligand_pose_{i+1}"
            for int_type, int_list in pose.interactions.items():
                for inter in int_list:
                    lig_atom = inter.get("ligand_atom")
                    rec_atom = inter.get("receptor_atom")
                    if lig_atom is not None and rec_atom is not None:
                        color = {"hydrogen_bonds": "red", "hydrophobic": "orange",
                                "pi_stacking": "purple", "salt_bridges": "blue"}.get(int_type, "gray")
                        script_lines.append(
                            f"distance {pose_name}_{int_type}_{lig_atom}_{rec_atom}, "
                            f"{pose_name} and index {lig_atom}, receptor and index {rec_atom}"
                        )
                        script_lines.append(f"color {color}, {pose_name}_{int_type}_{lig_atom}_{rec_atom}")
        
        script = "\n".join(script_lines)
        Path(output_path).write_text(script)


def create_3d_view(
    receptor_mol: Chem.Mol,
    ligand_mol: Chem.Mol,
    pose_coords: np.ndarray | None = None,
    interactions: dict[str, list[dict]] | None = None,
    **kwargs,
) -> str:
    """Convenience function for 3D view."""
    config = VisualizationConfig(**kwargs)
    visualizer = PoseVisualizer(config)
    return visualizer.create_3d_view(receptor_mol, ligand_mol, pose_coords, interactions)


def create_2d_diagram(
    receptor_mol: Chem.Mol,
    ligand_mol: Chem.Mol,
    pose_coords: np.ndarray | None = None,
    interactions: dict[str, list[dict]] | None = None,
    **kwargs,
) -> "PIL.Image.Image":
    """Convenience function for 2D interaction diagram."""
    config = VisualizationConfig(**kwargs)
    visualizer = PoseVisualizer(config)
    return visualizer.create_2d_interaction_diagram(receptor_mol, ligand_mol, pose_coords, interactions)


def export_pymol(
    receptor_mol: Chem.Mol,
    ligand_mol: Chem.Mol,
    poses: list,
    output_path: str,
):
    """Convenience function for PyMOL export."""
    visualizer = PoseVisualizer()
    visualizer.export_pymol_session(receptor_mol, ligand_mol, poses, output_path)