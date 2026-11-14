"""Molecular docking engine with Vina/smina/gnina support."""
from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem import rdDistGeom

logger = logging.getLogger(__name__)


@dataclass
class DockingPose:
    """A single docking pose."""
    smiles: str
    score: float  # kcal/mol (lower = better)
    coordinates: list[tuple[float, float, float]]  # per atom
    rmsd_to_ref: float | None = None
    interactions: dict[str, list[dict]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    conformer_id: int = 0
    model_id: int = 0


@dataclass
class DockingResult:
    """Complete docking result."""
    receptor_path: str
    ligand_smiles: str
    poses: list[DockingPose]
    best_pose: DockingPose | None = None
    docking_time: float = 0.0
    engine: str = "vina"
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DockingConfig:
    """Docking configuration."""
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    size: tuple[float, float, float] = (20.0, 20.0, 20.0)
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0
    min_rmsd: float = 1.0
    seed: int | None = None
    cpu: int = 1
    # Advanced
    spacing: float = 0.375  # grid spacing
    scoring: str = "vina"   # "vina", "vinardo", "ad4", "ad4_scoring"
    # Flexible residues
    flexible_residues: list[str] = field(default_factory=list)


class DockingEngine:
    """
    Molecular docking engine supporting multiple backends.
    
    Backends:
    - AutoDock Vina (CPU)
    - smina (Vina fork with more scoring functions)
    - GNINA (CNN-based scoring, GPU)
    - QuickVina2 (accelerated)
    - Internal RDKit-based (approximate, no install needed)
    
    Workflow:
    1. Prepare receptor (PDBQT)
    2. Prepare ligand (PDBQT)
    3. Define grid box
    4. Run docking
    5. Parse poses
    6. Analyze interactions
    """
    
    def __init__(
        self,
        engine: str = "vina",
        vina_path: str | None = None,
        smina_path: str | None = None,
        gnina_path: str | None = None,
        **engine_kwargs,
    ):
        """
        Initialize docking engine.
        
        Args:
            engine: "vina", "smina", "gnina", "quickvina", "internal"
            vina_path: Path to vina executable
            smina_path: Path to smina executable
            gnina_path: Path to gnina executable
            **engine_kwargs: Engine-specific parameters
        """
        self.engine = engine
        self.vina_path = vina_path or "vina"
        self.smina_path = smina_path or "smina"
        self.gnina_path = gnina_path or "gnina"
        self.engine_kwargs = engine_kwargs
        self.logger = logging.getLogger(__name__)
        
        # Check available engines
        self.available_engines = self._detect_engines()
        
        if engine not in self.available_engines and engine != "internal":
            self.logger.warning(
                "Engine %s not found, available: %s. Falling back to internal.",
                engine, self.available_engines
            )
            self.engine = "internal"
    
    def _detect_engines(self) -> list[str]:
        """Detect available docking engines."""
        engines = ["internal"]
        
        for name, path in [
            ("vina", self.vina_path),
            ("smina", self.smina_path),
            ("gnina", self.gnina_path),
            ("quickvina", "qvina2"),
        ]:
            try:
                subprocess.run([path, "--help"], capture_output=True, check=False, timeout=5)
                engines.append(name)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        return engines
    
    def dock(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig | None = None,
    ) -> DockingResult:
        """
        Run molecular docking.
        
        Args:
            receptor_pdbqt: Path to receptor PDBQT
            ligand_pdbqt: Path to ligand PDBQT
            config: Docking configuration
            
        Returns:
            DockingResult
        """
        if config is None:
            config = DockingConfig()
        
        start_time = time.time()
        
        if self.engine == "vina":
            return self._dock_vina(receptor_pdbqt, ligand_pdbqt, config, start_time)
        elif self.engine == "smina":
            return self._dock_smina(receptor_pdbqt, ligand_pdbqt, config, start_time)
        elif self.engine == "gnina":
            return self._dock_gnina(receptor_pdbqt, ligand_pdbqt, config, start_time)
        elif self.engine == "quickvina":
            return self._dock_quickvina(receptor_pdbqt, ligand_pdbqt, config, start_time)
        else:
            return self._dock_internal(receptor_pdbqt, ligand_pdbqt, config, start_time)
    
    def _dock_vina(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig,
        start_time: float,
    ) -> DockingResult:
        """Dock using AutoDock Vina."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_pdbqt = tmpdir / "output.pdbqt"
            log_file = tmpdir / "log.txt"
            
            cmd = [
                self.vina_path,
                "--receptor", receptor_pdbqt,
                "--ligand", ligand_pdbqt,
                "--center_x", str(config.center[0]),
                "--center_y", str(config.center[1]),
                "--center_z", str(config.center[2]),
                "--size_x", str(config.size[0]),
                "--size_y", str(config.size[1]),
                "--size_z", str(config.size[2]),
                "--exhaustiveness", str(config.exhaustiveness),
                "--num_modes", str(config.num_modes),
                "--energy_range", str(config.energy_range),
                "--out", str(output_pdbqt),
                "--log", str(log_file),
            ]
            
            if config.seed is not None:
                cmd.extend(["--seed", str(config.seed)])
            
            if config.cpu > 1:
                cmd.extend(["--cpu", str(config.cpu)])
            
            if config.scoring != "vina":
                cmd.extend(["--scoring", config.scoring])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            except subprocess.TimeoutExpired:
                return DockingResult(
                    receptor_path=receptor_pdbqt,
                    ligand_smiles="",
                    poses=[],
                    docking_time=time.time() - start_time,
                    engine="vina",
                    success=False,
                    error="Docking timed out",
                )
            
            return self._parse_vina_output(
                output_pdbqt, log_file, receptor_pdbqt, ligand_pdbqt,
                time.time() - start_time, config
            )
    
    def _dock_smina(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig,
        start_time: float,
    ) -> DockingResult:
        """Dock using smina (Vina fork)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_pdbqt = tmpdir / "output.pdbqt"
            log_file = tmpdir / "log.txt"
            
            cmd = [
                self.smina_path,
                "--receptor", receptor_pdbqt,
                "--ligand", ligand_pdbqt,
                "--center_x", str(config.center[0]),
                "--center_y", str(config.center[1]),
                "--center_z", str(config.center[2]),
                "--size_x", str(config.size[0]),
                "--size_y", str(config.size[1]),
                "--size_z", str(config.size[2]),
                "--exhaustiveness", str(config.exhaustiveness),
                "--num_modes", str(config.num_modes),
                "--energy_range", str(config.energy_range),
                "--out", str(output_pdbqt),
                "--log", str(log_file),
            ]
            
            if config.seed is not None:
                cmd.extend(["--seed", str(config.seed)])
            
            # smina-specific scoring functions
            if config.scoring != "vina":
                cmd.extend(["--scoring", config.scoring])  # vina, ad4, vinardo, dkoes_scoring
            
            # Flexible residues
            if config.flexible_residues:
                flex_file = tmpdir / "flex.pdbqt"
                self._write_flexible_residues(receptor_pdbqt, config.flexible_residues, flex_file)
                cmd.extend(["--flex", str(flex_file)])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            except subprocess.TimeoutExpired:
                return DockingResult(
                    receptor_path=receptor_pdbqt,
                    ligand_smiles="",
                    poses=[],
                    docking_time=time.time() - start_time,
                    engine="smina",
                    success=False,
                    error="Docking timed out",
                )
            
            return self._parse_vina_output(
                output_pdbqt, log_file, receptor_pdbqt, ligand_pdbqt,
                time.time() - start_time, config
            )
    
    def _dock_gnina(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig,
        start_time: float,
    ) -> DockingResult:
        """Dock using GNINA (CNN scoring)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_pdbqt = tmpdir / "output.pdbqt"
            log_file = tmpdir / "log.txt"
            
            cmd = [
                self.gnina_path,
                "--receptor", receptor_pdbqt,
                "--ligand", ligand_pdbqt,
                "--center_x", str(config.center[0]),
                "--center_y", str(config.center[1]),
                "--center_z", str(config.center[2]),
                "--size_x", str(config.size[0]),
                "--size_y", str(config.size[1]),
                "--size_z", str(config.size[2]),
                "--exhaustiveness", str(config.exhaustiveness),
                "--num_modes", str(config.num_modes),
                "--out", str(output_pdbqt),
                "--log", str(log_file),
            ]
            
            if config.seed is not None:
                cmd.extend(["--seed", str(config.seed)])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            except subprocess.TimeoutExpired:
                return DockingResult(
                    receptor_path=receptor_pdbqt,
                    ligand_smiles="",
                    poses=[],
                    docking_time=time.time() - start_time,
                    engine="gnina",
                    success=False,
                    error="Docking timed out",
                )
            
            # GNINA output similar to Vina but with CNN scores
            return self._parse_vina_output(
                output_pdbqt, log_file, receptor_pdbqt, ligand_pdbqt,
                time.time() - start_time, config
            )
    
    def _dock_quickvina(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig,
        start_time: float,
    ) -> DockingResult:
        """Dock using QuickVina2."""
        # QuickVina2 uses same CLI as Vina but faster
        return self._dock_vina(receptor_pdbqt, ligand_pdbqt, config, start_time)
    
    def _dock_internal(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        config: DockingConfig,
        start_time: float,
    ) -> DockingResult:
        """
        Internal RDKit-based docking (approximate).
        Used when no external engine is available.
        """
        # Parse receptor
        rec_mol = Chem.MolFromPDBFile(receptor_pdbqt, removeHs=False)
        if rec_mol is None:
            # Try PDBQT
            rec_mol = self._parse_pdbqt(receptor_pdbqt)
        
        if rec_mol is None:
            return DockingResult(
                receptor_path=receptor_pdbqt,
                ligand_smiles="",
                poses=[],
                docking_time=time.time() - start_time,
                engine="internal",
                success=False,
                error="Could not parse receptor",
            )
        
        # Parse ligand
        lig_mol = self._parse_pdbqt(ligand_pdbqt)
        if lig_mol is None:
            return DockingResult(
                receptor_path=receptor_pdbqt,
                ligand_smiles="",
                poses=[],
                docking_time=time.time() - start_time,
                engine="internal",
                success=False,
                error="Could not parse ligand",
            )
        
        # Simple rigid docking: place ligand at center, sample rotations
        poses = self._sample_poses_internal(lig_mol, rec_mol, config)
        
        # Score poses
        scored_poses = []
        for pose_mol, coords in poses:
            score = self._score_pose_internal(pose_mol, rec_mol)
            interactions = self._analyze_interactions(pose_mol, rec_mol)
            
            scored_poses.append(DockingPose(
                smiles=Chem.MolToSmiles(pose_mol, removeHs=True),
                score=score,
                coordinates=coords,
                interactions=interactions,
            ))
        
        scored_poses.sort(key=lambda p: p.score)
        
        return DockingResult(
            receptor_path=receptor_pdbqt,
            ligand_smiles=Chem.MolToSmiles(lig_mol, removeHs=True),
            poses=scored_poses,
            best_pose=scored_poses[0] if scored_poses else None,
            docking_time=time.time() - start_time,
            engine="internal",
            success=True,
        )
    
    def _sample_poses_internal(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
        config: DockingConfig,
    ) -> list[tuple[Chem.Mol, list[tuple[float, float, float]]]]:
        """Sample ligand poses in binding site."""
        poses = []
        center = np.array(config.center)
        
        for i in range(config.num_modes):
            pose_mol = Chem.Mol(lig_mol)
            conf = pose_mol.GetConformer()
            
            # Random rotation
            rot_mat = self._random_rotation_matrix()
            
            for j in range(pose_mol.GetNumAtoms()):
                pos = np.array(conf.GetAtomPosition(j))
                new_pos = rot_mat @ pos
                conf.SetAtomPosition(j, new_pos)
            
            # Translate to binding site center
            lig_center = self._get_molecular_center(pose_mol)
            translation = center - lig_center
            
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
    
    def _random_rotation_matrix(self) -> np.ndarray:
        """Generate random 3D rotation matrix."""
        # Random quaternion
        u1, u2, u3 = np.random.random(3)
        q = np.array([
            np.sqrt(1 - u1) * np.sin(2 * np.pi * u2),
            np.sqrt(1 - u1) * np.cos(2 * np.pi * u2),
            np.sqrt(u1) * np.sin(2 * np.pi * u3),
            np.sqrt(u1) * np.cos(2 * np.pi * u3),
        ])
        
        R = np.array([
            [1 - 2*q[2]**2 - 2*q[3]**2, 2*q[1]*q[2] - 2*q[0]*q[3], 2*q[1]*q[3] + 2*q[0]*q[2]],
            [2*q[1]*q[2] + 2*q[0]*q[3], 1 - 2*q[1]**2 - 2*q[3]**2, 2*q[2]*q[3] - 2*q[0]*q[1]],
            [2*q[1]*q[3] - 2*q[0]*q[2], 2*q[2]*q[3] + 2*q[0]*q[1], 1 - 2*q[1]**2 - 2*q[2]**2],
        ])
        return R
    
    def _get_molecular_center(self, mol: Chem.Mol) -> np.ndarray:
        """Get geometric center of molecule."""
        conf = mol.GetConformer()
        coords = np.array([conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())])
        return coords.mean(axis=0)
    
    def _score_pose_internal(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
    ) -> float:
        """Score pose using simplified physics-based scoring."""
        score = 0.0
        
        # Van der Waals (Lennard-Jones)
        vdw = self._calc_vdw(lig_mol, rec_mol)
        score += vdw
        
        # Electrostatic
        elec = self._calc_electrostatic(lig_mol, rec_mol)
        score += elec
        
        # Hydrogen bonds
        hbond = self._calc_hbonds(lig_mol, rec_mol)
        score -= hbond * 2.0
        
        # Hydrophobic
        hydrophobic = self._calc_hydrophobic(lig_mol, rec_mol)
        score -= hydrophobic * 1.5
        
        # Clash penalty
        clash = self._calc_clash(lig_mol, rec_mol)
        score += clash * 10.0
        
        return score
    
    def _calc_vdw(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate van der Waals energy."""
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        total_vdw = 0.0
        for lc in lig_coords:
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = distances.min()
            if min_dist < 4.0:
                if min_dist < 2.0:
                    total_vdw += 10.0 * (2.0 - min_dist)
                else:
                    total_vdw -= 1.0 * (4.0 - min_dist)
        
        return total_vdw
    
    def _calc_electrostatic(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate electrostatic energy."""
        AllChem.ComputeGasteigerCharges(lig_mol)
        AllChem.ComputeGasteigerCharges(rec_mol)
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
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
                total_elec += 332.0 * lq * rq / (dist * 4.0)
        
        return total_elec
    
    def _calc_hbonds(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Count hydrogen bonds."""
        hbond_count = 0
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        for i in range(lig_mol.GetNumAtoms()):
            lig_atom = lig_mol.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() not in [7, 8]:
                continue
            lc = lig_coords[i]
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            close = np.where(distances < 3.5)[0]
            for ri in close:
                rec_atom = rec_mol.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() in [7, 8]:
                    hbond_count += 1
        
        return float(hbond_count)
    
    def _calc_hydrophobic(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate hydrophobic contacts."""
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        # Identify hydrophobic carbons
        lig_hydro = []
        for i in range(lig_mol.GetNumAtoms()):
            atom = lig_mol.GetAtomWithIdx(i)
            if atom.GetAtomicNum() == 6:
                is_hydro = True
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() in [7, 8, 16]:
                        is_hydro = False
                        break
                if is_hydro:
                    lig_hydro.append(i)
        
        rec_hydro = []
        for i in range(rec_mol.GetNumAtoms()):
            atom = rec_mol.GetAtomWithIdx(i)
            if atom.GetAtomicNum() == 6:
                is_hydro = True
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() in [7, 8, 16]:
                        is_hydro = False
                        break
                if is_hydro:
                    rec_hydro.append(i)
        
        contacts = 0
        for li in lig_hydro:
            lc = lig_coords[li]
            distances = np.linalg.norm(rec_coords[rec_hydro] - lc, axis=1)
            contacts += np.sum(distances < 4.5)
        
        return float(contacts)
    
    def _calc_clash(self, lig_mol: Chem.Mol, rec_mol: Chem.Mol) -> float:
        """Calculate steric clash penalty."""
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        total_clash = 0.0
        for lc in lig_coords:
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = distances.min()
            if min_dist < 1.5:
                total_clash += (1.5 - min_dist) ** 2
            elif min_dist < 2.0:
                total_clash += 0.5 * (2.0 - min_dist) ** 2
        
        return total_clash
    
    def _analyze_interactions(
        self,
        lig_mol: Chem.Mol,
        rec_mol: Chem.Mol,
    ) -> dict[str, list[dict]]:
        """Analyze protein-ligand interactions."""
        interactions = {
            "hydrogen_bonds": [],
            "hydrophobic": [],
            "pi_stacking": [],
            "salt_bridges": [],
            "halogen_bonds": [],
        }
        
        lig_conf = lig_mol.GetConformer()
        rec_conf = rec_mol.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig_mol.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec_mol.GetNumAtoms())])
        
        # Hydrogen bonds
        for i in range(lig_mol.GetNumAtoms()):
            lig_atom = lig_mol.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() not in [7, 8]:
                continue
            lc = lig_coords[i]
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            close = np.where(distances < 3.5)[0]
            for ri in close:
                rec_atom = rec_mol.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() in [7, 8]:
                    interactions["hydrogen_bonds"].append({
                        "ligand_atom": i,
                        "receptor_atom": int(ri),
                        "distance": float(distances[ri]),
                        "ligand_element": lig_atom.GetSymbol(),
                        "receptor_element": rec_atom.GetSymbol(),
                    })
        
        # Hydrophobic
        for i in range(lig_mol.GetNumAtoms()):
            lig_atom = lig_mol.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() != 6:
                continue
            lc = lig_coords[i]
            distances = np.linalg.norm(rec_coords - lc, axis=1)
            close = np.where((distances > 3.0) & (distances < 5.0))[0]
            for ri in close:
                rec_atom = rec_mol.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() == 6:
                    interactions["hydrophobic"].append({
                        "ligand_atom": i,
                        "receptor_atom": int(ri),
                        "distance": float(distances[ri]),
                    })
        
        return interactions
    
    def _parse_vina_output(
        self,
        output_pdbqt: Path,
        log_file: Path,
        receptor_pdbqt: str,
        ligand_pdbqt: str,
        docking_time: float,
        config: DockingConfig,
    ) -> DockingResult:
        """Parse Vina/smina/GNINA output."""
        poses = []
        
        if not output_pdbqt.exists():
            return DockingResult(
                receptor_path=receptor_pdbqt,
                ligand_smiles="",
                poses=[],
                docking_time=docking_time,
                engine=self.engine,
                success=False,
                error="No output file generated",
            )
        
        content = output_pdbqt.read_text()
        models = content.split("MODEL")
        
        ligand_smiles = ""
        
        for model_idx, model in enumerate(models[1:], 1):
            lines = model.strip().split("\n")
            
            # Extract score from REMARK
            score = 0.0
            cnn_score = None
            cnn_affinity = None
            
            for line in lines:
                if line.startswith("REMARK VINA RESULT:"):
                    parts = line.split()
                    if len(parts) >= 4:
                        score = float(parts[3])
                elif "CNN score" in line or "cnn_score" in line:
                    # GNINA CNN score
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if "CNN" in p or "cnn" in p.lower():
                            try:
                                cnn_score = float(parts[i + 1])
                            except (IndexError, ValueError):
                                pass
                elif "CNN affinity" in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if "affinity" in p.lower():
                            try:
                                cnn_affinity = float(parts[i + 1])
                            except (IndexError, ValueError):
                                pass
            
            # Extract coordinates
            coords = []
            atoms_info = []
            for line in lines:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    coords.append((x, y, z))
                    
                    # Get atom info
                    elem = line[76:78].strip() or line[12:16].strip()
                    atoms_info.append(elem)
            
            if coords:
                # Try to get SMILES from ligand
                if not ligand_smiles:
                    ligand_smiles = self._extract_smiles_from_pdbqt(lines)
                
                metadata = {"vina_rank": model_idx, "vina_score": score}
                if cnn_score is not None:
                    metadata["cnn_score"] = cnn_score
                if cnn_affinity is not None:
                    metadata["cnn_affinity"] = cnn_affinity
                
                poses.append(DockingPose(
                    smiles=ligand_smiles,
                    score=score,
                    coordinates=coords,
                    metadata=metadata,
                    model_id=model_idx,
                ))
        
        poses.sort(key=lambda p: p.score)
        
        return DockingResult(
            receptor_path=receptor_pdbqt,
            ligand_smiles=ligand_smiles,
            poses=poses,
            best_pose=poses[0] if poses else None,
            docking_time=docking_time,
            engine=self.engine,
            success=True,
            metadata={"config": config.__dict__},
        )
    
    def _extract_smiles_from_pdbqt(self, lines: list[str]) -> str:
        """Extract SMILES from PDBQT REMARK lines."""
        for line in lines:
            if "SMILES" in line or "smiles" in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if "SMILES" in p or "smiles" in p.lower():
                        if i + 1 < len(parts):
                            return parts[i + 1]
        return ""
    
    def _parse_pdbqt(self, pdbqt_path: str) -> Chem.Mol | None:
        """Parse PDBQT file with RDKit."""
        # Read as PDB (ignore charge/type columns)
        content = Path(pdbqt_path).read_text()
        # Remove charge/type columns for RDKit parsing
        lines = []
        for line in content.splitlines():
            if line.startswith("ATOM") or line.startswith("HETATM"):
                # Keep first 66 chars (PDB format)
                lines.append(line[:66])
            else:
                lines.append(line)
        
        pdb_block = "\n".join(lines)
        return Chem.MolFromPDBBlock(pdb_block, removeHs=False)
    
    def _write_flexible_residues(
        self,
        receptor_pdbqt: str,
        flexible_residues: list[str],
        output_path: Path,
    ):
        """Extract flexible residues from receptor."""
        # Simplified: write receptor as flex (in reality, would extract specific residues)
        import shutil
        shutil.copy(receptor_pdbqt, output_path)
    
    def batch_dock(
        self,
        receptor_pdbqt: str,
        ligand_pdbqt_list: list[str],
        config: DockingConfig | None = None,
    ) -> list[DockingResult]:
        """Dock multiple ligands."""
        return [self.dock(receptor_pdbqt, lig, config) for lig in ligand_pdbqt_list]


def dock(
    receptor_pdbqt: str,
    ligand_pdbqt: str,
    engine: str = "vina",
    **kwargs,
) -> DockingResult:
    """Convenience function for docking."""
    config = DockingConfig(**kwargs)
    docking_engine = DockingEngine(engine=engine)
    return docking_engine.dock(receptor_pdbqt, ligand_pdbqt, config)