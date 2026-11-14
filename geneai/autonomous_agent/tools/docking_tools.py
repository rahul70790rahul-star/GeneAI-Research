"""Molecular docking tools for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from geneai.autonomous_agent.tools import Tool, ToolSpec, ToolParameter

logger = logging.getLogger(__name__)


def _prepare_receptor_pdbqt(pdb_id: str, binding_site: str | None = None) -> str:
    """Download and prepare receptor PDBQT from PDB ID."""
    import requests
    from rdkit import Chem
    from rdkit.Chem import AllChem

    # Try to download PDB
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        pdb_content = response.text
    except Exception as exc:
        raise RuntimeError(f"Failed to download PDB {pdb_id}: {exc}")

    # Parse with RDKit
    mol = Chem.MolFromPDBBlock(pdb_content, removeHs=False)
    if mol is None:
        raise RuntimeError(f"Could not parse PDB {pdb_id}")

    # Add hydrogens
    mol = Chem.AddHs(mol)

    # Write to temporary PDBQT
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pdbqt", delete=False) as f:
        # Simple PDBQT conversion (in production, use AutoDockTools prepare_receptor4.py)
        # For now, write as PDB and let docking engine handle conversion
        pdb_block = Chem.MolToPDBBlock(mol)
        f.write(pdb_block)
        return f.name


def _prepare_ligand_pdbqt(smiles: str) -> str:
    """Prepare ligand PDBQT from SMILES."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise RuntimeError(f"Invalid SMILES: {smiles}")

    # Add hydrogens and generate 3D coordinates
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)

    # Write to temporary PDBQT
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pdbqt", delete=False) as f:
        # Write as PDB (docking engine will convert)
        pdb_block = Chem.MolToPDBBlock(mol)
        f.write(pdb_block)
        return f.name


class MolecularDockingTool(Tool):
    """Perform molecular docking using Vina/smina/gnina or internal engine."""

    def __init__(self):
        spec = ToolSpec(
            name="molecular_docking",
            description="Perform molecular docking of ligands to protein targets using AutoDock Vina, smina, GNINA, or internal RDKit engine",
            category="docking",
            requires_approval=True,
            parameters=[
                ToolParameter("ligand_smiles", "string", "Ligand SMILES", required=True),
                ToolParameter("protein_pdb", "string", "Protein PDB ID or path to PDBQT file", required=True),
                ToolParameter("binding_site", "string", "Binding site specification (e.g., 'center_x,center_y,center_z' or 'auto')", required=False),
                ToolParameter("exhaustiveness", "number", "Search exhaustiveness", required=False, default=8),
                ToolParameter("num_modes", "number", "Number of binding modes", required=False, default=9),
                ToolParameter("engine", "string", "Docking engine", required=False, default="internal", enum=["vina", "smina", "gnina", "quickvina", "internal"]),
                ToolParameter("center", "array", "Grid center [x, y, z]", required=False),
                ToolParameter("size", "array", "Grid size [x, y, z]", required=False, default=[20, 20, 20]),
                ToolParameter("energy_range", "number", "Energy range for poses", required=False, default=3.0),
                ToolParameter("cpu", "number", "CPU threads", required=False, default=1),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        ligand_smiles = kwargs.get("ligand_smiles", "")
        protein_pdb = kwargs.get("protein_pdb", "")
        engine = kwargs.get("engine", "internal")

        if not ligand_smiles or not protein_pdb:
            return {"error": "Both ligand SMILES and protein PDB required"}

        try:
            # Prepare receptor and ligand files
            receptor_path = _prepare_receptor_pdbqt(protein_pdb, kwargs.get("binding_site"))
            ligand_path = _prepare_ligand_pdbqt(ligand_smiles)

            # Configure docking
            from geneai.molecular_docking.docking_engine import DockingEngine, DockingConfig

            # Parse center from binding_site if provided
            center = kwargs.get("center", (0.0, 0.0, 0.0))
            if isinstance(center, list):
                center = tuple(center)
            elif kwargs.get("binding_site"):
                # Try to parse binding_site as coordinates
                try:
                    parts = [float(x.strip()) for x in kwargs["binding_site"].split(",")]
                    if len(parts) == 3:
                        center = tuple(parts)
                except (ValueError, AttributeError):
                    pass

            size = kwargs.get("size", [20.0, 20.0, 20.0])
            if isinstance(size, list):
                size = tuple(size)

            config = DockingConfig(
                center=center,
                size=size,
                exhaustiveness=kwargs.get("exhaustiveness", 8),
                num_modes=kwargs.get("num_modes", 9),
                energy_range=kwargs.get("energy_range", 3.0),
                cpu=kwargs.get("cpu", 1),
            )

            # Run docking
            docking_engine = DockingEngine(engine=engine)
            result = docking_engine.dock(receptor_path, ligand_path, config)

            # Clean up temp files
            try:
                Path(receptor_path).unlink(missing_ok=True)
                Path(ligand_path).unlink(missing_ok=True)
            except Exception:
                pass

            if not result.success:
                return {
                    "ligand_smiles": ligand_smiles,
                    "protein_pdb": protein_pdb,
                    "engine": engine,
                    "success": False,
                    "error": result.error,
                }

            # Format poses
            poses = []
            for pose in result.poses:
                pose_data = {
                    "mode": pose.model_id,
                    "affinity_kcal_mol": round(pose.score, 2),
                    "rmsd_lb": 0.0,
                    "rmsd_ub": 0.0,
                    "coordinates": pose.coordinates,
                    "interactions": pose.interactions,
                }
                if pose.metadata:
                    pose_data.update(pose.metadata)
                poses.append(pose_data)

            return {
                "ligand_smiles": ligand_smiles,
                "protein_pdb": protein_pdb,
                "engine": engine,
                "success": True,
                "best_affinity": result.best_pose.score if result.best_pose else None,
                "poses": poses,
                "docking_time": round(result.docking_time, 2),
                "binding_site": kwargs.get("binding_site", "auto"),
                "config": {
                    "center": config.center,
                    "size": config.size,
                    "exhaustiveness": config.exhaustiveness,
                    "num_modes": config.num_modes,
                },
            }

        except Exception as exc:
            logger.error("Docking failed: %s", exc)
            return {
                "ligand_smiles": ligand_smiles,
                "protein_pdb": protein_pdb,
                "engine": engine,
                "success": False,
                "error": str(exc),
            }


class BindingSitePredictionTool(Tool):
    """Predict binding sites on proteins using geometry-based methods."""

    def __init__(self):
        spec = ToolSpec(
            name="binding_site_prediction",
            description="Predict potential binding sites on protein structures using geometric cavity detection",
            category="docking",
            parameters=[
                ToolParameter("protein_pdb", "string", "Protein PDB ID or structure", required=True),
                ToolParameter("method", "string", "Prediction method", required=False, default="geometry", enum=["geometry", "fpocket", "p2rank", "deepsite"]),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        protein_pdb = kwargs.get("protein_pdb", "")
        if not protein_pdb:
            return {"error": "Protein PDB required"}

        method = kwargs.get("method", "geometry")

        try:
            import requests
            from rdkit import Chem
            import numpy as np

            # Download PDB
            url = f"https://files.rcsb.org/download/{protein_pdb.upper()}.pdb"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            pdb_content = response.text

            # Parse with RDKit
            mol = Chem.MolFromPDBBlock(pdb_content, removeHs=False)
            if mol is None:
                raise RuntimeError(f"Could not parse PDB {protein_pdb}")

            # Simple geometry-based cavity detection
            conf = mol.GetConformer()
            coords = np.array([conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())])

            # Find cavities by looking for concave regions
            # This is a simplified implementation - in production use fpocket/p2rank
            from scipy.spatial import ConvexHull

            try:
                hull = ConvexHull(coords)
                # Find interior points (potential binding sites)
                # Simplified: use k-means on surface atoms to find pockets
                from sklearn.cluster import KMeans

                # Get surface atoms (simplified: atoms with fewer neighbors)
                surface_indices = []
                for i in range(mol.GetNumAtoms()):
                    atom = mol.GetAtomWithIdx(i)
                    nbrs = [n.GetIdx() for n in atom.GetNeighbors()]
                    if len(nbrs) < 4:  # Surface atom heuristic
                        surface_indices.append(i)

                if len(surface_indices) > 10:
                    surface_coords = coords[surface_indices]
                    n_clusters = min(5, len(surface_indices) // 10)
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    labels = kmeans.fit_predict(surface_coords)

                    sites = []
                    for cluster_id in range(n_clusters):
                        cluster_points = surface_coords[labels == cluster_id]
                        center = cluster_points.mean(axis=0)
                        # Estimate volume as sphere around center
                        distances = np.linalg.norm(cluster_points - center, axis=1)
                        radius = float(distances.max())
                        volume = (4/3) * np.pi * radius**3

                        # Get nearby residues
                        residues = set()
                        for idx in surface_indices[labels == cluster_id]:
                            atom = mol.GetAtomWithIdx(idx)
                            residue = atom.GetPDBResidueInfo()
                            if residue:
                                res_name = residue.GetResidueName()
                                res_num = residue.GetResidueNumber()
                                residues.add(f"{res_name}{res_num}")

                        sites.append({
                            "site_id": cluster_id + 1,
                            "center": {"x": float(center[0]), "y": float(center[1]), "z": float(center[2])},
                            "volume": round(float(volume), 1),
                            "druggability_score": min(1.0, len(cluster_points) / 50.0),
                            "residues": sorted(residues),
                            "method": "geometry_clustering",
                        })

                    return {
                        "protein_pdb": protein_pdb,
                        "method": method,
                        "sites": sites,
                        "note": "Geometry-based prediction; for production use fpocket, P2Rank, or DeepSite",
                    }
                else:
                    return {
                        "protein_pdb": protein_pdb,
                        "method": method,
                        "sites": [],
                        "note": "Insufficient surface atoms for cavity detection",
                    }

            except Exception as exc:
                logger.warning("Cavity detection failed: %s", exc)
                return {
                    "protein_pdb": protein_pdb,
                    "method": method,
                    "sites": [],
                    "error": f"Cavity detection failed: {exc}",
                }

        except Exception as exc:
            logger.error("Binding site prediction failed: %s", exc)
            return {
                "protein_pdb": protein_pdb,
                "method": method,
                "error": str(exc),
                "sites": [],
            }


def register_docking_tools(registry):
    """Register docking tools."""
    registry.register(MolecularDockingTool())
    registry.register(BindingSitePredictionTool())