"""Molecular docking engine for drug design."""
from __future__ import annotations

import logging
import subprocess
import tempfile
import os
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign, rdDistGeom
from rdkit.Chem import rdMolDescriptors

logger = logging.getLogger(__name__)


@dataclass
class DockingPose:
    """A single docking pose."""
    smiles: str
    score: float
    coordinates: list[tuple[float, float, float]]  # 3D coordinates per atom
    rmsd_to_ref: float | None = None
    interactions: dict[str, list[dict]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DockingResult:
    """Complete docking result."""
    receptor_name: str
    ligand_smiles: str
    poses: list[DockingPose]
    best_pose: DockingPose | None = None
    docking_time: float = 0.0
    engine: str = "internal"
    success: bool = True
    error: str | None = None


@dataclass
class Receptor:
    """Protein receptor for docking."""
    name: str
    pdb_path: str | None = None
    pdb_content: str | None = None
    binding_site: dict[str, Any] | None = None
    center: tuple[float, float, float] | None = None
    size: tuple[float, float, float] = (20.0, 20.0, 20.0)
    metadata: dict[str, Any] = field(default_factory=dict)


class DockingEngine:
    """
    Molecular docking engine supporting multiple backends.
    
    Supported engines:
    - Internal (RDKit-based, fast but approximate)
    - Vina (AutoDock Vina, requires installation)
    - GNINA (CNN-based scoring, requires installation)
    - DiffDock (Diffusion-based, requires installation)
    """
    
    def __init__(self, engine: str = "internal", **engine_kwargs):
        """
        Initialize docking engine.
        
        Args:
            engine: "internal", "vina", "gnina", "diffdock"
            **engine_kwargs: Engine-specific parameters
        """
        self.engine = engine
        self.engine_kwargs = engine_kwargs
        self.logger = logging.getLogger(__name__)
        
        # Internal scoring weights
        self.vdw_weight = engine_kwargs.get("vdw_weight", 1.0)
        self.elec_weight = engine_kwargs.get("elec_weight", 1.0)
        self.hbond_weight = engine_kwargs.get("hbond_weight", 2.0)
        self.hydrophobic_weight = engine_kwargs.get("hydrophobic_weight", 1.5)
        self.clash_penalty = engine_kwargs.get("clash_penalty", 10.0)
    
    def dock(
        self,
        receptor: Receptor,
        ligand_smiles: str,
        num_poses: int = 10,
        exhaustiveness: int = 8,
    ) -> DockingResult:
        """
        Dock a ligand into a receptor.
        
        Args:
            receptor: Receptor object
            ligand_smiles: Ligand SMILES
            num_poses: Number of poses to generate
            exhaustiveness: Search exhaustiveness (Vina)
            
        Returns:
            DockingResult with poses ranked by score
        """
        import time
        start_time = time.time()
        
        if self.engine == "internal":
            return self._dock_internal(receptor, ligand_smiles, num_poses)
        elif self.engine == "vina":
            return self._dock_vina(receptor, ligand_smiles, num_poses, exhaustiveness)
        elif self.engine == "gnina":
            return self._dock_gnina(receptor, ligand_smiles, num_poses, exhaustiveness)
        else:
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=[],
                docking_time=time.time() - start_time,
                engine=self.engine,
                success=False,
                error=f"Unknown engine: {self.engine}",
            )
    
    def _dock_internal(
        self,
        receptor: Receptor,
        ligand_smiles: str,
        num_poses: int,
    ) -> DockingResult:
        """Internal RDKit-based docking (approximate)."""
        import time
        start_time = time.time()
        
        # Parse ligand
        lig_mol = Chem.MolFromSmiles(ligand_smiles)
        if not lig_mol:
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=[],
                docking_time=time.time() - start_time,
                engine="internal",
                success=False,
                error="Invalid ligand SMILES",
            )
        
        lig_mol = Chem.AddHs(lig_mol)
        
        # Generate 3D conformations
        AllChem.EmbedMolecule(lig_mol, randomSeed=42)
        AllChem.MMFFOptimizeMolecule(lig_mol)
        
        # Get receptor structure
        rec_mol = self._load_receptor(receptor)
        if not rec_mol:
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=[],
                docking_time=time.time() - start_time,
                engine="internal",
                success=False,
                error="Failed to load receptor",
            )
        
        # Simple rigid docking: place ligand at binding site center
        # and sample rotations
        poses = self._sample_poses(lig_mol, rec_mol, receptor, num_poses)
        
        # Score poses
        scored_poses = []
        for pose_mol, coords in poses:
            score = self._score_pose(pose_mol, rec_mol, receptor)
            interactions = self._analyze_interactions(pose_mol, rec_mol)
            
            scored_poses.append(DockingPose(
                smiles=Chem.MolToSmiles(pose_mol, removeHs=True),
                score=score,
                coordinates=coords,
                interactions=interactions,
            ))
        
        # Sort by score
        scored_poses.sort(key=lambda p: p.score)
        
        return DockingResult(
            receptor_name=receptor.name,
            ligand_smiles=ligand_smiles,
            poses=scored_poses,
            best_pose=scored_poses[0] if scored_poses else None,
            docking_time=time.time() - start_time,
            engine="internal",
            success=True,
        )
    
    def _load_receptor(self, receptor: Receptor) -> Chem.Mol | None:
        """Load receptor from PDB."""
        if receptor.pdb_content:
            return Chem.MolFromPDBBlock(receptor.pdb_content, removeHs=False)
        elif receptor.pdb_path and os.path.exists(receptor.pdb_path):
            return Chem.MolFromPDBFile(receptor.pdb_path, removeHs=False)
        return None
    
    def _sample_poses(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
        receptor: Receptor,
        num_poses: int,
    ) -> list[tuple[Chem.Mol, list[tuple[float, float, float]]]]:
        """Sample ligand poses in binding site."""
        import random
        import numpy as np
        
        poses = []
        center = receptor.center or self._calculate_binding_center(rec_mol)
        
        for i in range(num_poses):
            # Copy ligand
            pose_mol = Chem.Mol(lig_mol)
            
            # Random rotation
            conf = pose_mol.GetConformer()
            rot_mat = self._random_rotation_matrix()
            
            # Apply rotation
            for j in range(pose_mol.GetNumAtoms()):
                pos = np.array(conf.GetAtomPosition(j))
                new_pos = rot_mat @ pos
                conf.SetAtomPosition(j, new_pos)
            
            # Translate to binding site center
            lig_center = self._get_molecular_center(pose_mol)
            translation = np.array(center) - lig_center
            
            for j in range(pose_mol.GetNumAtoms()):
                pos = np.array(conf.GetAtomPosition(j))
                new_pos = pos + translation
                conf.SetAtomPosition(j, new_pos)
            
            # Extract coordinates
            coords = []
            for j in range(pose_mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(j)
                coords.append((pos.x, pos.y, pos.z))
            
            poses.append((pose_mol, coords))
        
        return poses
    
    def _random_rotation_matrix(self) -> "np.ndarray":
        """Generate random 3D rotation matrix."""
        import numpy as np
        
        # Random quaternion
        u1, u2, u3 = np.random.random(3)
        q = np.array([
            np.sqrt(1 - u1) * np.sin(2 * np.pi * u2),
            np.sqrt(1 - u1) * np.cos(2 * np.pi * u2),
            np.sqrt(u1) * np.sin(2 * np.pi * u3),
            np.sqrt(u1) * np.cos(2 * np.pi * u3),
        ])
        
        # Convert to rotation matrix
        R = np.array([
            [1 - 2*q[2]**2 - 2*q[3]**2, 2*q[1]*q[2] - 2*q[0]*q[3], 2*q[1]*q[3] + 2*q[0]*q[2]],
            [2*q[1]*q[2] + 2*q[0]*q[3], 1 - 2*q[1]**2 - 2*q[3]**2, 2*q[2]*q[3] - 2*q[0]*q[1]],
            [2*q[1]*q[3] - 2*q[0]*q[2], 2*q[2]*q[3] + 2*q[0]*q[1], 1 - 2*q[1]**2 - 2*q[2]**2],
        ])
        return R
    
    def _get_molecular_center(self, mol: Chem.Mol) -> "np.ndarray":
        """Get geometric center of molecule."""
        import numpy as np
        
        conf = mol.GetConformer()
        coords = np.array([conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())])
        return coords.mean(axis=0)
    
    def _calculate_binding_center(self, rec_mol: Chem.Mol) -> tuple[float, float, float]:
        """Calculate binding site center from receptor."""
        import numpy as np
        
        conf = rec_mol.GetConformer()
        coords = np.array([conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        center = coords.mean(axis=0)
        return (float(center[0]), float(center[1]), float(center[2]))
    
    def _score_pose(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
        receptor: Receptor,
    ) -> float:
        """Score a docking pose (lower = better)."""
        score = 0.0
        
        # Van der Waals
        vdw = self._calculate_vdw(lig_mol, rec_mol)
        score += self.vdw_weight * vdw
        
        # Electrostatic
        elec = self._calculate_electrostatic(lig_mol, rec_mol)
        score += self.elec_weight * elec
        
        # Hydrogen bonds
        hbond = self._calculate_hbonds(lig_mol, rec_mol)
        score -= self.hbond_weight * hbond  # Negative = favorable
        
        # Hydrophobic
        hydrophobic = self._calculate_hydrophobic(lig_mol, rec_mol)
        score -= self.hydrophobic_weight * hydrophobic
        
        # Clash penalty
        clash = self._calculate_clash(lig_mol, rec_mol)
        score += self.clash_penalty * clash
        
        return score
    
    def _calculate_vdw(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate van der Waals energy."""
        # Simplified Lennard-Jones
        import numpy as np
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        # Simple distance-based approximation
        total_vdw = 0.0
        for lc in lig_coords:
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = distances.min()
            if min_dist < 4.0:  # Only close atoms contribute
                # Repulsive at short distance, attractive at optimal
                if min_dist < 2.0:
                    total_vdw += 10.0 * (2.0 - min_dist)  # Repulsion
                else:
                    total_vdw -= 1.0 * (4.0 - min_dist)  # Attraction
        
        return total_vdw
    
    def _calculate_electrostatic(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate electrostatic energy."""
        # Simplified Coulombic
        import numpy as np
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        # Get partial charges (Gasteiger)
        AllChem.ComputeGasteigerCharges(lig_mol)
        AllChem.ComputeGasteigerCharges(rec_mol)
        
        lig_charges = [float(lig_mol.GetAtomWithIdx(i).GetProp("_GasteigerCharge")) 
                       for i in range(lig_mol.GetNumAtoms())]
        rec_charges = [float(rec_mol.GetAtomWithIdx(i).GetProp("_GasteigerCharge")) 
                       for i in range(rec_mol.GetNumAtoms())]
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        total_elec = 0.0
        for i, (lc, lq) in enumerate(zip(lig_coords, lig_charges)):
            if abs(lq) < 0.01:
                continue
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            for j, (dist, rq) in enumerate(zip(distances, rec_charges)):
                if abs(rq) < 0.01 or dist > 10.0:
                    continue
                # Coulomb's law (simplified)
                total_elec += 332.0 * lq * rq / (dist * 4.0)  # Dielectric = 4
        
        return total_elec
    
    def _calculate_hbonds(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Count hydrogen bonds."""
        from rdkit.Chem import rdMolDescriptors
        
        # Use RDKit's H-bond detection
        hbond_info = rdMolDescriptors.CalcNumHBA(lig_mol) + rdMolDescriptors.CalcNumHBD(lig_mol)
        # Simplified: return count as proxy for H-bond potential
        return float(hbond_info) * 0.5
    
    def _calculate_hydrophobic(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate hydrophobic interactions."""
        import numpy as np
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        # Identify hydrophobic atoms (C, S with no polar neighbors)
        lig_hydrophobic = []
        for i in range(lig_mol.GetNumAtoms()):
            atom = lig_mol.GetAtomWithIdx(i)
            if atom.GetAtomicNum() in [6, 16]:  # C, S
                # Check if not bonded to heteroatom
                is_hydrophobic = True
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() in [7, 8, 16]:  # N, O, S
                        is_hydrophobic = False
                        break
                if is_hydrophobic:
                    lig_hydrophobic.append(i)
        
        rec_hydrophobic = []
        for i in range(rec_mol.GetNumAtoms()):
            atom = rec_mol.GetAtomWithIdx(i)
            if atom.GetAtomicNum() in [6, 16]:
                is_hydrophobic = True
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() in [7, 8, 16]:
                        is_hydrophobic = False
                        break
                if is_hydrophobic:
                    rec_hydrophobic.append(i)
        
        # Count close hydrophobic contacts
        contacts = 0
        for li in lig_hydrophobic:
            lc = lig_coords[li]
            distances = np.linalg.norm(rec_coords[rec_hydrophobic] - lc, axis=1)
            contacts += np.sum(distances < 4.5)
        
        return float(contacts)
    
    def _calculate_clash(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate steric clash penalty."""
        import numpy as np
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        total_clash = 0.0
        for lc in lig_coords:
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = distances.min()
            if min_dist < 1.5:  # Severe clash
                total_clash += (1.5 - min_dist) ** 2
            elif min_dist < 2.0:  # Moderate clash
                total_clash += 0.5 * (2.0 - min_dist) ** 2
        
        return total_clash
    
    def _analyze_interactions(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
    ) -> dict[str, list[dict]]:
        """Analyze protein-ligand interactions."""
        import numpy as np
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        interactions = {
            "hydrogen_bonds": [],
            "hydrophobic": [],
            "pi_stacking": [],
            "salt_bridges": [],
            "halogen_bonds": [],
        }
        
        # Hydrogen bonds
        for i in range(lig_mol.GetNumAtoms()):
            lig_atom = lig_mol.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() not in [7, 8]:  # N, O
                continue
            lc = lig_coords[i]
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            close_indices = np.where(distances < 3.5)[0]
            for ri in close_indices:
                rec_atom = rec_mol.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() in [7, 8]:
                    interactions["hydrogen_bonds"].append({
                        "ligand_atom": i,
                        "receptor_atom": int(ri),
                        "distance": float(distances[ri]),
                        "ligand_element": lig_atom.GetSymbol(),
                        "receptor_element": rec_atom.GetSymbol(),
                    })
        
        # Hydrophobic contacts
        for i in range(lig_mol.GetNumAtoms()):
            lig_atom = lig_mol.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() != 6:
                continue
            lc = lig_coords[i]
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            close_indices = np.where((distances > 3.0) & (distances < 5.0))[0]
            for ri in close_indices:
                rec_atom = rec_mol.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() == 6:
                    interactions["hydrophobic"].append({
                        "ligand_atom": i,
                        "receptor_atom": int(ri),
                        "distance": float(distances[ri]),
                    })
        
        return interactions
    
    def _dock_vina(
        self,
        receptor: Receptor,
        ligand_smiles: str,
        num_poses: int,
        exhaustiveness: int,
    ) -> DockingResult:
        """Dock using AutoDock Vina."""
        import time
        start_time = time.time()
        
        # Check if Vina is available
        try:
            subprocess.run(["vina", "--help"], capture_output=True, check=False)
        except FileNotFoundError:
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=[],
                docking_time=time.time() - start_time,
                engine="vina",
                success=False,
                error="AutoDock Vina not found. Install with: conda install -c conda-forge autodock-vina",
            )
        
        # Prepare receptor and ligand files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Write receptor PDBQT
            rec_pdbqt = tmpdir / "receptor.pdbqt"
            self._write_pdbqt(receptor, rec_pdbqt)
            
            # Write ligand PDBQT
            lig_pdbqt = tmpdir / "ligand.pdbqt"
            self._write_ligand_pdbqt(ligand_smiles, lig_pdbqt)
            
            # Run Vina
            center = receptor.center or (0, 0, 0)
            size = receptor.size
            
            cmd = [
                "vina",
                "--receptor", str(rec_pdbqt),
                "--ligand", str(lig_pdbqt),
                "--center_x", str(center[0]),
                "--center_y", str(center[1]),
                "--center_z", str(center[2]),
                "--size_x", str(size[0]),
                "--size_y", str(size[1]),
                "--size_z", str(size[2]),
                "--exhaustiveness", str(exhaustiveness),
                "--num_modes", str(num_poses),
                "--out", str(tmpdir / "output.pdbqt"),
                "--log", str(tmpdir / "log.txt"),
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                return DockingResult(
                    receptor_name=receptor.name,
                    ligand_smiles=ligand_smiles,
                    poses=[],
                    docking_time=time.time() - start_time,
                    engine="vina",
                    success=False,
                    error="Vina timed out",
                )
            
            # Parse output
            poses = self._parse_vina_output(tmpdir / "output.pdbqt", ligand_smiles)
            
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=poses,
                best_pose=poses[0] if poses else None,
                docking_time=time.time() - start_time,
                engine="vina",
                success=True,
            )
    
    def _dock_gnina(
        self,
        receptor: Receptor,
        ligand_smiles: str,
        num_poses: int,
        exhaustiveness: int,
    ) -> DockingResult:
        """Dock using GNINA (CNN scoring)."""
        import time
        start_time = time.time()
        
        try:
            subprocess.run(["gnina", "--help"], capture_output=True, check=False)
        except FileNotFoundError:
            return DockingResult(
                receptor_name=receptor.name,
                ligand_smiles=ligand_smiles,
                poses=[],
                docking_time=time.time() - start_time,
                engine="gnina",
                success=False,
                error="GNINA not found. Install from: https://github.com/gnina/gnina",
            )
        
        # Similar to Vina but with CNN scoring
        # For now, fall back to Vina
        return self._dock_vina(receptor, ligand_smiles, num_poses, exhaustiveness)
    
    def _write_pdbqt(self, receptor: Receptor, output_path: Path):
        """Write receptor as PDBQT."""
        if receptor.pdb_content:
            # Convert PDB to PDBQT (simplified - just copy for now)
            with open(output_path, "w") as f:
                f.write(receptor.pdb_content)
        elif receptor.pdb_path:
            import shutil
            shutil.copy(receptor.pdb_path, output_path)
    
    def _write_ligand_pdbqt(self, smiles: str, output_path: Path):
        """Write ligand as PDBQT."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return
        
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol)
        AllChem.MMFFOptimizeMolecule(mol)
        
        # Write as PDB then convert (simplified)
        pdb_path = output_path.with_suffix(".pdb")
        Chem.MolToPDBFile(mol, str(pdb_path))
        
        # Use Open Babel or similar to convert to PDBQT
        # For now, just copy PDB
        import shutil
        shutil.copy(pdb_path, output_path)
    
    def _parse_vina_output(self, output_path: Path, ligand_smiles: str) -> list[DockingPose]:
        """Parse Vina output PDBQT."""
        poses = []
        
        if not output_path.exists():
            return poses
        
        # Simple parsing - each MODEL block is a pose
        content = output_path.read_text()
        models = content.split("MODEL")
        
        for i, model in enumerate(models[1:], 1):  # Skip first empty split
            lines = model.strip().split("\n")
            
            # Extract score from REMARK
            score = 0.0
            for line in lines:
                if line.startswith("REMARK VINA RESULT:"):
                    parts = line.split()
                    if len(parts) >= 4:
                        score = float(parts[3])
                    break
            
            # Extract coordinates
            coords = []
            for line in lines:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    coords.append((x, y, z))
            
            poses.append(DockingPose(
                smiles=ligand_smiles,
                score=score,
                coordinates=coords,
                metadata={"vina_rank": i},
            ))
        
        return poses
    
    def batch_dock(
        self,
        receptor: Receptor,
        ligand_smiles_list: list[str],
        num_poses: int = 5,
    ) -> list[DockingResult]:
        """Dock multiple ligands."""
        return [self.dock(receptor, smi, num_poses) for smi in ligand_smiles_list]


def create_receptor_from_pdb(pdb_path: str, name: str | None = None, **kwargs) -> Receptor:
    """Create Receptor from PDB file."""
    name = name or Path(pdb_path).stem
    return Receptor(name=name, pdb_path=pdb_path, **kwargs)


def create_receptor_from_pdb_string(pdb_content: str, name: str, **kwargs) -> Receptor:
    """Create Receptor from PDB string."""
    return Receptor(name=name, pdb_content=pdb_content, **kwargs)