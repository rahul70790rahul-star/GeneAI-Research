"""Advanced scoring functions for molecular docking."""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors, Descriptors
from rdkit.Chem import rdMolAlign
from rdkit.Chem import rdFMCS

logger = logging.getLogger(__name__)


@dataclass
class ScoringComponents:
    """Individual scoring components."""
    vdw: float = 0.0
    electrostatic: float = 0.0
    hydrogen_bond: float = 0.0
    hydrophobic: float = 0.0
    desolvation: float = 0.0
    entropy: float = 0.0
    clash: float = 0.0
    pi_stacking: float = 0.0
    salt_bridge: float = 0.0
    halogen_bond: float = 0.0
    metal_coordination: float = 0.0
    water_mediated: float = 0.0
    custom: dict[str, float] = None
    
    def __post_init__(self):
        if self.custom is None:
            self.custom = {}


class ScoringFunction:
    """
    Base class for scoring functions.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(__name__)
    
    def score(
        self,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
    ) -> ScoringComponents:
        """Calculate scoring components."""
        raise NotImplementedError
    
    def total_score(self, components: ScoringComponents) -> float:
        """Calculate total score from components."""
        raise NotImplementedError


class VinaScoringFunction(ScoringFunction):
    """
    AutoDock Vina scoring function (approximation).
    
    Vina score = gauss1 + gauss2 + repulsion + hydrophobic + hydrogen_bond
    """
    
    def __init__(self):
        super().__init__("Vina")
    
    def score(
        self,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
    ) -> ScoringComponents:
        comps = ScoringComponents()
        
        if pose_coords is not None:
            # Use provided coordinates
            lig_conf = ligand_mol.GetConformer()
            # Update conformer with pose_coords
            for i, coord in enumerate(pose_coords):
                lig_conf.SetAtomPosition(i, coord)
        
        # Calculate components using simplified physics
        comps.vdw = self._calc_vdw(ligand_mol, receptor_mol)
        comps.electrostatic = self._calc_electrostatic(ligand_mol, receptor_mol)
        comps.hydrogen_bond = self._calc_hbonds(ligand_mol, receptor_mol)
        comps.hydrophobic = self._calc_hydrophobic(ligand_mol, receptor_mol)
        comps.clash = self._calc_clash(ligand_mol, receptor_mol)
        
        return comps
    
    def total_score(self, components: ScoringComponents) -> float:
        # Vina weights (approximate)
        return (
            components.vdw +
            components.electrostatic +
            components.hydrogen_bond * (-2.0) +
            components.hydrophobic * (-1.5) +
            components.clash * 10.0
        )
    
    def _calc_vdw(self, lig: Chem.Mol, rec: Chem.Mol) -> float:
        """Van der Waals (Lennard-Jones) energy."""
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        total = 0.0
        for lc in lig_coords:
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = dists.min()
            if min_dist < 4.0:
                # Simplified LJ potential
                if min_dist < 2.0:
                    total += 4.0 * ((2.0 / min_dist) ** 12 - (2.0 / min_dist) ** 6)
                else:
                    total -= 0.5 * (4.0 - min_dist)
        return total
    
    def _calc_electrostatic(self, lig: Chem.Mol, rec: Chem.Mol) -> float:
        """Electrostatic energy (Coulombic)."""
        AllChem.ComputeGasteigerCharges(lig)
        AllChem.ComputeGasteigerCharges(rec)
        
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_charges = [float(lig.GetAtomWithIdx(i).GetProp("_GasteigerCharge")) 
                       for i in range(lig.GetNumAtoms())]
        rec_charges = [float(rec.GetAtomWithIdx(i).GetProp("_GasteigerCharge")) 
                       for i in range(rec.GetNumAtoms())]
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        total = 0.0
        for i, (lc, lq) in enumerate(zip(lig_coords, lig_charges)):
            if abs(lq) < 0.01:
                continue
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            for j, (dist, rq) in enumerate(zip(dists, rec_charges)):
                if abs(rq) < 0.01 or dist > 10.0:
                    continue
                total += 332.0 * lq * rq / (dist * 4.0)  # dielectric=4
        return total
    
    def _calc_hbonds(self, lig: Chem.Mol, rec: Chem.Mol) -> float:
        """Hydrogen bond energy."""
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        hbond_count = 0
        for i in range(lig.GetNumAtoms()):
            lig_atom = lig.GetAtomWithIdx(i)
            if lig_atom.GetAtomicNum() not in [7, 8]:
                continue
            lc = lig_coords[i]
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            close = np.where(dists < 3.5)[0]
            for ri in close:
                rec_atom = rec.GetAtomWithIdx(int(ri))
                if rec_atom.GetAtomicNum() in [7, 8]:
                    hbond_count += 1
        
        return -hbond_count * 2.0  # Favorable
    
    def _calc_hydrophobic(self, lig: Chem.Mol, rec: Chem.Mol) -> float:
        """Hydrophobic contact energy."""
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        # Identify hydrophobic carbons
        lig_hydro = []
        for i in range(lig.GetNumAtoms()):
            atom = lig.GetAtomWithIdx(i)
            if atom.GetAtomicNum() == 6:
                is_hydro = True
                for nbr in atom.GetNeighbors():
                    if nbr.GetAtomicNum() in [7, 8, 16]:
                        is_hydro = False
                        break
                if is_hydro:
                    lig_hydro.append(i)
        
        rec_hydro = []
        for i in range(rec.GetNumAtoms()):
            atom = rec.GetAtomWithIdx(i)
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
            dists = np.linalg.norm(rec_coords[rec_hydro] - lc, axis=1)
            contacts += np.sum(dists < 4.5)
        
        return -contacts * 0.5  # Favorable
    
    def _calc_clash(self, lig: Chem.Mol, rec: Chem.Mol) -> float:
        """Steric clash penalty."""
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        total = 0.0
        for lc in lig_coords:
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            min_dist = dists.min()
            if min_dist < 1.5:
                total += (1.5 - min_dist) ** 2
            elif min_dist < 2.0:
                total += 0.5 * (2.0 - min_dist) ** 2
        return total


class RFScore(ScoringFunction):
    """
    RF-Score: Random Forest based scoring using interaction counts.
    
    Reference: Ballester & Mitchell, JCIM 2010
    """
    
    def __init__(self):
        super().__init__("RF-Score")
        self.model = None
        self.feature_names = [
            "hbonds", "hydrophobic", "polar", "charged",
            "vdw_contacts", "rotatable_bonds", "mw", "logp",
        ]
    
    def score(
        self,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
    ) -> ScoringComponents:
        comps = ScoringComponents()
        
        # Extract features
        features = self._extract_features(ligand_mol, receptor_mol, pose_coords)
        
        # Calculate components
        comps.custom = features
        comps.vdw = features.get("vdw_contacts", 0) * 0.1
        comps.hydrogen_bond = -features.get("hbonds", 0) * 1.5
        comps.hydrophobic = -features.get("hydrophobic", 0) * 0.5
        comps.electrostatic = -features.get("polar", 0) * 0.8
        
        return comps
    
    def total_score(self, components: ScoringComponents) -> float:
        if self.model:
            # Use trained RF model
            features = [components.custom.get(f, 0) for f in self.feature_names]
            return self.model.predict([features])[0]
        else:
            # Heuristic linear model
            f = components.custom
            return (
                -1.5 * f.get("hbonds", 0)
                - 0.5 * f.get("hydrophobic", 0)
                - 0.8 * f.get("polar", 0)
                + 0.1 * f.get("rotatable_bonds", 0)
                + 0.01 * f.get("mw", 0)
                - 0.2 * f.get("logp", 0)
            )
    
    def _extract_features(
        self,
        lig: Chem.Mol,
        rec: Chem.Mol,
        pose_coords: np.ndarray | None,
    ) -> dict[str, float]:
        """Extract RF-Score features."""
        features = {}
        
        # Ligand properties
        features["mw"] = Descriptors.MolWt(lig)
        features["logp"] = Descriptors.MolLogP(lig)
        features["rotatable_bonds"] = Descriptors.NumRotatableBonds(lig)
        
        # Interaction counts (simplified)
        if pose_coords is not None:
            lig_conf = lig.GetConformer()
            for i, coord in enumerate(pose_coords):
                lig_conf.SetAtomPosition(i, coord)
        
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        hbonds = 0
        hydrophobic = 0
        polar = 0
        charged = 0
        vdw_contacts = 0
        
        for i in range(lig.GetNumAtoms()):
            lig_atom = lig.GetAtomWithIdx(i)
            lc = lig_coords[i]
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            
            # Close contacts
            close = np.where(dists < 4.5)[0]
            vdw_contacts += len(close)
            
            for ri in close:
                rec_atom = rec.GetAtomWithIdx(int(ri))
                dist = dists[ri]
                
                if dist < 3.5 and lig_atom.GetAtomicNum() in [7, 8] and rec_atom.GetAtomicNum() in [7, 8]:
                    hbonds += 1
                
                if lig_atom.GetAtomicNum() == 6 and rec_atom.GetAtomicNum() == 6:
                    if dist > 3.0 and dist < 5.0:
                        hydrophobic += 1
                
                if lig_atom.GetAtomicNum() in [7, 8] or rec_atom.GetAtomicNum() in [7, 8]:
                    polar += 1
                
                if lig_atom.GetFormalCharge() != 0 or rec_atom.GetFormalCharge() != 0:
                    charged += 1
        
        features["hbonds"] = hbonds
        features["hydrophobic"] = hydrophobic
        features["polar"] = polar
        features["charged"] = charged
        features["vdw_contacts"] = vdw_contacts
        
        return features
    
    def train(self, training_data: list[tuple[dict[str, float], float]]):
        """Train RF model on experimental data."""
        from sklearn.ensemble import RandomForestRegressor
        
        X = []
        y = []
        for features, exp_affinity in training_data:
            X.append([features.get(f, 0) for f in self.feature_names])
            y.append(exp_affinity)
        
        self.model = RandomForestRegressor(n_estimators=500, random_state=42)
        self.model.fit(X, y)
    
    def save_model(self, path: str):
        """Save trained model."""
        with open(path, "wb") as f:
            pickle.dump(self.model, f)
    
    def load_model(self, path: str):
        """Load trained model."""
        with open(path, "rb") as f:
            self.model = pickle.load(f)


class NNScore(ScoringFunction):
    """
    NNScore: Neural network based scoring.
    
    Reference: Durrant & McCammon, JCIM 2010
    """
    
    def __init__(self):
        super().__init__("NNScore")
        self.model = None
    
    def score(
        self,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
    ) -> ScoringComponents:
        comps = ScoringComponents()
        
        # Extract distance-based features
        features = self._extract_distance_features(ligand_mol, receptor_mol, pose_coords)
        comps.custom = features
        
        # Approximate components
        comps.vdw = features.get("close_contacts", 0) * 0.1
        comps.electrostatic = -features.get("polar_close", 0) * 0.5
        comps.hydrogen_bond = -features.get("hbond_distance", 0) * 1.0
        comps.hydrophobic = -features.get("hydrophobic_close", 0) * 0.3
        
        return comps
    
    def total_score(self, components: ScoringComponents) -> float:
        if self.model:
            # Use trained NN
            features = list(components.custom.values())
            return self.model.predict([features])[0]
        else:
            # Heuristic
            f = components.custom
            return (
                -1.0 * f.get("hbond_distance", 0)
                - 0.5 * f.get("hydrophobic_close", 0)
                - 0.3 * f.get("polar_close", 0)
                + 0.1 * f.get("close_contacts", 0)
            )
    
    def _extract_distance_features(
        self,
        lig: Chem.Mol,
        rec: Chem.Mol,
        pose_coords: np.ndarray | None,
    ) -> dict[str, float]:
        """Extract distance-based features for NN."""
        features = {}
        
        if pose_coords is not None:
            lig_conf = lig.GetConformer()
            for i, coord in enumerate(pose_coords):
                lig_conf.SetAtomPosition(i, coord)
        
        lig_conf = lig.GetConformer()
        rec_conf = rec.GetConformer()
        
        lig_coords = np.array([lig_conf.GetAtomPosition(i) for i in range(lig.GetNumAtoms())])
        rec_coords = np.array([rec_conf.GetAtomPosition(i) for i in range(rec.GetNumAtoms())])
        
        # Distance histograms
        all_dists = []
        for lc in lig_coords:
            dists = np.linalg.norm(rec_coords - lc, axis=1)
            all_dists.extend(dists)
        
        all_dists = np.array(all_dists)
        
        features["close_contacts"] = np.sum(all_dists < 4.0)
        features["hbond_distance"] = np.sum((all_dists > 2.5) & (all_dists < 3.5))
        features["hydrophobic_close"] = np.sum((all_dists > 3.5) & (all_dists < 5.0))
        features["polar_close"] = np.sum((all_dists > 2.5) & (all_dists < 4.0))
        
        # Atom-type specific
        for elem in ["C", "N", "O", "S"]:
            lig_mask = np.array([lig.GetAtomWithIdx(i).GetSymbol() == elem for i in range(lig.GetNumAtoms())])
            if np.any(lig_mask):
                lig_sub = lig_coords[lig_mask]
                for lc in lig_sub:
                    dists = np.linalg.norm(rec_coords - lc, axis=1)
                    features[f"{elem}_close"] = np.sum(dists < 4.0)
        
        return features


class ConsensusScorer:
    """
    Consensus scoring combining multiple scoring functions.
    """
    
    def __init__(
        self,
        scorers: list[ScoringFunction] | None = None,
        weights: dict[str, float] | None = None,
    ):
        if scorers is None:
            scorers = [
                VinaScoringFunction(),
                RFScore(),
                NNScore(),
            ]
        
        self.scorers = {s.name: s for s in scorers}
        
        if weights is None:
            weights = {
                "Vina": 0.4,
                "RF-Score": 0.3,
                "NNScore": 0.3,
            }
        
        # Normalize weights
        total = sum(weights.values())
        self.weights = {k: v / total for k, v in weights.items()}
        self.logger = logging.getLogger(__name__)
    
    def score(
        self,
        ligand_mol: Chem.Mol,
        receptor_mol: Chem.Mol,
        pose_coords: np.ndarray | None = None,
    ) -> tuple[float, dict[str, ScoringComponents]]:
        """
        Calculate consensus score.
        
        Returns:
            (consensus_score, dict of individual scorer components)
        """
        all_components = {}
        scores = {}
        
        for name, scorer in self.scorers.items():
            try:
                components = scorer.score(ligand_mol, receptor_mol, pose_coords)
                score = scorer.total_score(components)
                
                all_components[name] = components
                scores[name] = score
            except Exception as e:
                self.logger.warning("Scorer %s failed: %s", name, e)
                scores[name] = 0.0
        
        # Weighted consensus
        consensus = sum(self.weights.get(k, 0) * v for k, v in scores.items())
        
        return consensus, all_components
    
    def rank_poses(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ) -> list[tuple[int, float, dict]]:
        """
        Rank poses by consensus score.
        
        Returns:
            List of (pose_index, consensus_score, components_dict)
        """
        results = []
        
        for i, pose in enumerate(poses):
            pose_coords = np.array(pose.coordinates) if pose.coordinates else None
            consensus, components = self.score(ligand_mol, receptor_mol, pose_coords)
            results.append((i, consensus, components))
        
        # Sort by consensus score (lower = better)
        results.sort(key=lambda x: x[1])
        
        return results


class MMGBSARescorer:
    """
    MM/GBSA (Molecular Mechanics / Generalized Born Surface Area) rescoring.
    
    Approximate implementation. For production, use AmberTools MMPBSA.py.
    """
    
    def __init__(
        self,
        dielectric: float = 4.0,
        gb_model: str = "obc",  # "obc", "gb2"
        sa_model: str = "lcp",  # "lcp", "ace"
    ):
        self.dielectric = dielectric
        self.gb_model = gb_model
        self.sa_model = sa_model
        self.logger = logging.getLogger(__name__)
    
    def rescore(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ) -> list[dict]:
        """
        Rescore poses using MM/GBSA.
        
        Returns list of dicts with energy components.
        """
        results = []
        
        for pose in poses:
            pose_coords = np.array(pose.coordinates) if pose.coordinates else None
            
            # Calculate components
            e_mm = self._calc_mm_energy(ligand_mol, receptor_mol, pose_coords)
            e_gb = self._calc_gb_energy(ligand_mol, receptor_mol, pose_coords)
            e_sa = self._calc_sa_energy(ligand_mol, receptor_mol, pose_coords)
            
            total = e_mm + e_gb + e_sa
            
            results.append({
                "pose_index": getattr(pose, "pose_index", 0),
                "total": total,
                "mm_energy": e_mm,
                "gb_energy": e_gb,
                "sa_energy": e_sa,
                "vdw": e_mm.get("vdw", 0),
                "electrostatic": e_mm.get("electrostatic", 0),
                "bond": e_mm.get("bond", 0),
                "angle": e_mm.get("angle", 0),
                "dihedral": e_mm.get("dihedral", 0),
            })
        
        return results
    
    def _calc_mm_energy(
        self,
        lig: Chem.Mol,
        rec: Chem.Mol,
        pose_coords: np.ndarray | None,
    ) -> dict[str, float]:
        """Calculate molecular mechanics energy."""
        # Simplified: use MMFF94
        try:
            if pose_coords is not None:
                lig_conf = lig.GetConformer()
                for i, coord in enumerate(pose_coords):
                    lig_conf.SetAtomPosition(i, coord)
            
            # Minimize
            AllChem.MMFFOptimizeMolecule(lig)
            
            # Get energy components
            props = AllChem.MMFFGetMoleculeProperties(lig)
            if props:
                return {
                    "total": props.GetMMFFEnergy(),
                    "bond": 0.0,
                    "angle": 0.0,
                    "dihedral": 0.0,
                    "vdw": 0.0,
                    "electrostatic": 0.0,
                }
        except Exception:
            pass
        
        return {"total": 0.0, "bond": 0.0, "angle": 0.0, "dihedral": 0.0, "vdw": 0.0, "electrostatic": 0.0}
    
    def _calc_gb_energy(
        self,
        lig: Chem.Mol,
        rec: Chem.Mol,
        pose_coords: np.ndarray | None,
    ) -> float:
        """Calculate Generalized Born solvation energy."""
        # Simplified implementation
        # Real GB requires: Born radii calculation, pairwise descreening
        return 0.0
    
    def _calc_sa_energy(
        self,
        lig: Chem.Mol,
        rec: Chem.Mol,
        pose_coords: np.ndarray | None,
    ) -> float:
        """Calculate Surface Area nonpolar solvation energy."""
        # SASA-based: gamma * SASA + beta
        # gamma ~ 0.005-0.007 kcal/mol/A^2
        try:
            sasa = rdMolDescriptors.CalcLabuteASA(lig)
            return 0.005 * sasa  # Simplified
        except Exception:
            return 0.0


def get_scoring_function(name: str) -> ScoringFunction:
    """Get scoring function by name."""
    functions = {
        "vina": VinaScoringFunction,
        "rfscore": RFScore,
        "nnscore": NNScore,
    }
    
    if name.lower() not in functions:
        raise ValueError(f"Unknown scoring function: {name}. Available: {list(functions.keys())}")
    
    return functions[name.lower()]()


def create_consensus_scorer(
    scorer_names: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> ConsensusScorer:
    """Create consensus scorer with specified functions."""
    if scorer_names is None:
        scorer_names = ["vina", "rfscore", "nnscore"]
    
    scorers = [get_scoring_function(name) for name in scorer_names]
    return ConsensusScorer(scorers, weights)