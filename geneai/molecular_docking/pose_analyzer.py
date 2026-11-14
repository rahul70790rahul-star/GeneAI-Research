"""Pose analysis: RMSD clustering, interaction fingerprints, consensus scoring."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign, rdMolDescriptors
from rdkit.Chem import rdDistGeom
from rdkit.Chem import rdFMCS
from rdkit.Chem import rdMolTransforms
from rdkit.Chem import rdDepictor
from rdkit.Chem import rdMolHash

logger = logging.getLogger(__name__)


@dataclass
class ClusterResult:
    """Result of pose clustering."""
    clusters: list[list[int]]  # indices of poses in each cluster
    centroids: list[int]       # representative pose index for each cluster
    rmsd_matrix: np.ndarray    # pairwise RMSD matrix


@dataclass
class InteractionFingerprint:
    """Interaction fingerprint for a pose."""
    pose_index: int
    residue_interactions: dict[str, list[str]]  # residue -> interaction types
    fingerprint_bits: np.ndarray  # binary fingerprint
    ifp_string: str  # human-readable string


@dataclass
class RescoringResult:
    """Result of pose rescoring."""
    pose_index: int
    original_score: float
    rescored_score: float
    method: str
    components: dict[str, float] = field(default_factory=dict)


class PoseAnalyzer:
    """
    Analyze docking poses: clustering, interaction fingerprints, rescoring.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def cluster_poses_rmsd(
        self,
        poses: list,
        ligand_mol: Chem.Mol,
        rmsd_cutoff: float = 2.0,
        method: str = "butina",
    ) -> ClusterResult:
        """
        Cluster poses by RMSD.
        
        Args:
            poses: List of DockingPose objects
            ligand_mol: Reference ligand molecule (with conformers)
            rmsd_cutoff: RMSD cutoff for clustering (Å)
            method: "butina" (Taylor-Butina), "hierarchical", "kmeans"
            
        Returns:
            ClusterResult
        """
        n = len(poses)
        if n == 0:
            return ClusterResult(clusters=[], centroids=[], rmsd_matrix=np.array([]))
        
        # Calculate pairwise RMSD matrix
        rmsd_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i + 1, n):
                rmsd = self._calc_rmsd(poses[i], poses[j], ligand_mol)
                rmsd_matrix[i, j] = rmsd
                rmsd_matrix[j, i] = rmsd
        
        if method == "butina":
            clusters, centroids = self._butina_clustering(rmsd_matrix, rmsd_cutoff)
        elif method == "hierarchical":
            clusters, centroids = self._hierarchical_clustering(rmsd_matrix, rmsd_cutoff)
        else:
            clusters, centroids = self._butina_clustering(rmsd_matrix, rmsd_cutoff)
        
        return ClusterResult(
            clusters=clusters,
            centroids=centroids,
            rmsd_matrix=rmsd_matrix,
        )
    
    def _calc_rmsd(
        self,
        pose1,
        pose2,
        ligand_mol: Chem.Mol,
    ) -> float:
        """Calculate RMSD between two poses."""
        coords1 = np.array(pose1.coordinates)
        coords2 = np.array(pose2.coordinates)
        
        if len(coords1) != len(coords2):
            return float('inf')
        
        # Align and calculate RMSD
        diff = coords1 - coords2
        return np.sqrt(np.mean(np.sum(diff ** 2, axis=1)))
    
    def _butina_clustering(
        self,
        rmsd_matrix: np.ndarray,
        cutoff: float,
    ) -> tuple[list[list[int]], list[int]]:
        """Taylor-Butina clustering algorithm."""
        n = rmsd_matrix.shape[0]
        
        # Calculate number of neighbors within cutoff for each pose
        neighbor_counts = np.sum(rmsd_matrix < cutoff, axis=1)
        
        # Sort by neighbor count (descending)
        sorted_indices = np.argsort(-neighbor_counts)
        
        clusters = []
        centroids = []
        assigned = np.zeros(n, dtype=bool)
        
        for idx in sorted_indices:
            if assigned[idx]:
                continue
            
            # New cluster
            cluster = [idx]
            assigned[idx] = True
            centroids.append(idx)
            
            # Find neighbors
            for j in range(n):
                if not assigned[j] and rmsd_matrix[idx, j] < cutoff:
                    cluster.append(j)
                    assigned[j] = True
            
            clusters.append(cluster)
        
        return clusters, centroids
    
    def _hierarchical_clustering(
        self,
        rmsd_matrix: np.ndarray,
        cutoff: float,
    ) -> tuple[list[list[int]], list[int]]:
        """Hierarchical agglomerative clustering."""
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        
        # Convert to condensed distance matrix
        condensed = squareform(rmsd_matrix)
        
        # Linkage
        Z = linkage(condensed, method='average')
        
        # Cluster
        labels = fcluster(Z, cutoff, criterion='distance')
        
        # Group by cluster
        clusters = {}
        for idx, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(idx)
        
        cluster_list = list(clusters.values())
        
        # Select centroids (lowest energy in each cluster)
        centroids = []
        for cluster in cluster_list:
            centroids.append(cluster[0])  # First pose (assumed lowest energy)
        
        return cluster_list, centroids
    
    def generate_interaction_fingerprint(
        self,
        pose,
        receptor_mol: Chem.Mol,
        interaction_types: list[str] | None = None,
    ) -> InteractionFingerprint:
        """
        Generate interaction fingerprint (IFP) for a pose.
        
        Based on: Deng et al. JCIM 2004 - "Interaction Fingerprint"
        """
        if interaction_types is None:
            interaction_types = [
                "hbond_donor", "hbond_acceptor", "hydrophobic",
                "pi_stacking", "cation_pi", "anion_pi",
                "salt_bridge", "halogen_bond", "metal_coord",
            ]
        
        # Get interactions from pose
        interactions = pose.interactions
        
        # Map to residue-level
        residue_interactions = {}
        
        # This is simplified - real implementation would map atom indices to residues
        # using receptor residue information
        
        # Generate binary fingerprint
        # Each residue x interaction_type = 1 bit
        # For simplicity, use a fixed-size fingerprint
        fp_bits = np.zeros(len(interaction_types) * 100, dtype=bool)  # Max 100 residues
        
        ifp_parts = []
        
        for int_type, int_list in interactions.items():
            for inter in int_list:
                # Extract residue info (simplified)
                rec_atom = inter.get("receptor_atom", 0)
                # In real implementation, map atom to residue
                res_id = f"RES{rec_atom // 10}"
                
                if res_id not in residue_interactions:
                    residue_interactions[res_id] = []
                residue_interactions[res_id].append(int_type)
                
                ifp_parts.append(f"{res_id}:{int_type}")
        
        # Create fingerprint string
        ifp_string = "|".join(sorted(ifp_parts))
        
        return InteractionFingerprint(
            pose_index=0,  # Will be set by caller
            residue_interactions=residue_interactions,
            fingerprint_bits=fp_bits,
            ifp_string=ifp_string,
        )
    
    def compare_fingerprints(
        self,
        fp1: InteractionFingerprint,
        fp2: InteractionFingerprint,
        metric: str = "tanimoto",
    ) -> float:
        """Compare two interaction fingerprints."""
        if metric == "tanimoto":
            # Tanimoto coefficient
            intersection = np.sum(fp1.fingerprint_bits & fp2.fingerprint_bits)
            union = np.sum(fp1.fingerprint_bits | fp2.fingerprint_bits)
            return intersection / union if union > 0 else 0.0
        elif metric == "dice":
            intersection = np.sum(fp1.fingerprint_bits & fp2.fingerprint_bits)
            total = np.sum(fp1.fingerprint_bits) + np.sum(fp2.fingerprint_bits)
            return 2 * intersection / total if total > 0 else 0.0
        else:
            return 0.0
    
    def calculate_ifp_similarity_matrix(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
    ) -> np.ndarray:
        """Calculate pairwise IFP similarity matrix."""
        n = len(poses)
        fps = []
        
        for i, pose in enumerate(poses):
            fp = self.generate_interaction_fingerprint(pose, receptor_mol)
            fp.pose_index = i
            fps.append(fp)
        
        sim_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i, n):
                sim = self.compare_fingerprints(fps[i], fps[j])
                sim_matrix[i, j] = sim
                sim_matrix[j, i] = sim
        
        return sim_matrix


class PoseRescorer:
    """
    Rescore docking poses using more accurate methods.
    
    Methods:
    - MM/GBSA (approximate)
    - Consensus scoring (Vina + RF-Score + NNScore)
    - Interaction-based rescoring
    - Water displacement scoring
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def rescore_mm_gbsa(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        dielectric: float = 4.0,
    ) -> list[RescoringResult]:
        """
        Approximate MM/GBSA rescoring.
        
        This is a simplified implementation. Real MM/GBSA requires:
        - Proper force field parameters
        - Solvent accessible surface area calculation
        - Generalized Born solvation model
        """
        results = []
        
        for i, pose in enumerate(poses):
            # Components
            components = {}
            
            # 1. Molecular mechanics energy (internal + vdW + electrostatic)
            mm_energy = self._calc_mm_energy(pose, receptor_mol, ligand_mol)
            components["mm_energy"] = mm_energy
            
            # 2. Polar solvation (GB)
            polar_solv = self._calc_polar_solvation(pose, receptor_mol, ligand_mol, dielectric)
            components["polar_solvation"] = polar_solv
            
            # 3. Nonpolar solvation (SA)
            nonpolar_solv = self._calc_nonpolar_solvation(pose, receptor_mol, ligand_mol)
            components["nonpolar_solvation"] = nonpolar_solv
            
            # Total MM/GBSA
            total = mm_energy + polar_solv + nonpolar_solv
            
            results.append(RescoringResult(
                pose_index=i,
                original_score=pose.score,
                rescored_score=total,
                method="MM/GBSA",
                components=components,
            ))
        
        return results
    
    def rescore_consensus(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        weights: dict[str, float] | None = None,
    ) -> list[RescoringResult]:
        """
        Consensus scoring combining multiple scoring functions.
        """
        if weights is None:
            weights = {
                "vina": 0.4,
                "rfscore": 0.2,
                "nnscore": 0.2,
                "interaction": 0.2,
            }
        
        results = []
        
        for i, pose in enumerate(poses):
            components = {}
            
            # Vina score (already in pose.score)
            components["vina"] = pose.score
            
            # RF-Score (random forest based on interaction counts)
            rf_score = self._calc_rf_score(pose)
            components["rfscore"] = rf_score
            
            # NNScore (neural network - simplified)
            nn_score = self._calc_nn_score(pose)
            components["nnscore"] = nn_score
            
            # Interaction-based score
            int_score = self._calc_interaction_score(pose)
            components["interaction"] = int_score
            
            # Weighted consensus
            total = sum(weights.get(k, 0) * v for k, v in components.items())
            
            results.append(RescoringResult(
                pose_index=i,
                original_score=pose.score,
                rescored_score=total,
                method="Consensus",
                components=components,
            ))
        
        return results
    
    def rescore_interaction_based(
        self,
        poses: list,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ) -> list[RescoringResult]:
        """
        Score based on interaction pattern quality.
        """
        results = []
        
        for i, pose in enumerate(poses):
            interactions = pose.interactions
            
            # Count interaction types
            hbonds = len(interactions.get("hydrogen_bonds", []))
            hydrophobic = len(interactions.get("hydrophobic", []))
            pi_stacking = len(interactions.get("pi_stacking", []))
            salt_bridges = len(interactions.get("salt_bridges", []))
            halogen = len(interactions.get("halogen_bonds", []))
            
            # Weighted score (lower = better)
            # Favorable interactions reduce score
            score = pose.score  # Start with docking score
            score -= hbonds * 1.5
            score -= hydrophobic * 0.5
            score -= pi_stacking * 1.0
            score -= salt_bridges * 2.0
            score -= halogen * 1.0
            
            components = {
                "hbonds": hbonds,
                "hydrophobic": hydrophobic,
                "pi_stacking": pi_stacking,
                "salt_bridges": salt_bridges,
                "halogen": halogen,
            }
            
            results.append(RescoringResult(
                pose_index=i,
                original_score=pose.score,
                rescored_score=score,
                method="Interaction-based",
                components=components,
            ))
        
        return results
    
    def _calc_mm_energy(
        self,
        pose,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ) -> float:
        """Calculate molecular mechanics energy."""
        # Simplified: use internal docking score components
        return pose.score * 0.5  # Placeholder
    
    def _calc_polar_solvation(
        self,
        pose,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
        dielectric: float,
    ) -> float:
        """Calculate polar solvation energy (GB approximation)."""
        # Simplified: based on charge burial
        return 0.0  # Placeholder
    
    def _calc_nonpolar_solvation(
        self,
        pose,
        receptor_mol: Chem.Mol,
        ligand_mol: Chem.Mol,
    ) -> float:
        """Calculate nonpolar solvation (SA-based)."""
        # Simplified: based on buried surface area
        return 0.0  # Placeholder
    
    def _calc_rf_score(self, pose) -> float:
        """Calculate RF-Score (simplified)."""
        # RF-Score uses interaction counts as features
        interactions = pose.interactions
        hbonds = len(interactions.get("hydrogen_bonds", []))
        hydrophobic = len(interactions.get("hydrophobic", []))
        
        # Simplified linear model
        return -0.5 * hbonds - 0.2 * hydrophobic
    
    def _calc_nn_score(self, pose) -> float:
        """Calculate NNScore (simplified)."""
        # NNScore uses atomic distance distributions
        return pose.score * 0.1  # Placeholder
    
    def _calc_interaction_score(self, pose) -> float:
        """Calculate interaction-based score."""
        interactions = pose.interactions
        hbonds = len(interactions.get("hydrogen_bonds", []))
        hydrophobic = len(interactions.get("hydrophobic", []))
        pi_stacking = len(interactions.get("pi_stacking", []))
        
        return -1.0 * hbonds - 0.5 * hydrophobic - 0.8 * pi_stacking


class ConsensusScorer:
    """
    Consensus scoring across multiple docking runs/engines.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def rank_by_consensus(
        self,
        results_list: list[list],  # List of pose lists from different runs
        method: str = "rank_aggregation",
    ) -> list[int]:
        """
        Rank poses by consensus across multiple docking runs.
        
        Args:
            results_list: List of pose lists (each from separate docking run)
            method: "rank_aggregation", "score_average", "borda_count"
            
        Returns:
            Indices of poses in consensus ranking order
        """
        if not results_list:
            return []
        
        n_poses = len(results_list[0])
        n_runs = len(results_list)
        
        if method == "rank_aggregation":
            # Average rank across runs
            rank_sums = np.zeros(n_poses)
            for run_poses in results_list:
                for rank, pose in enumerate(run_poses):
                    if pose.pose_index < n_poses:
                        rank_sums[pose.pose_index] += rank + 1
            
            avg_ranks = rank_sums / n_runs
            return np.argsort(avg_ranks).tolist()
        
        elif method == "score_average":
            # Average score across runs
            score_sums = np.zeros(n_poses)
            counts = np.zeros(n_poses)
            
            for run_poses in results_list:
                for pose in run_poses:
                    if pose.pose_index < n_poses:
                        score_sums[pose.pose_index] += pose.score
                        counts[pose.pose_index] += 1
            
            avg_scores = np.where(counts > 0, score_sums / counts, np.inf)
            return np.argsort(avg_scores).tolist()
        
        elif method == "borda_count":
            # Borda count voting
            borda_scores = np.zeros(n_poses)
            
            for run_poses in results_list:
                n = len(run_poses)
                for rank, pose in enumerate(run_poses):
                    if pose.pose_index < n_poses:
                        borda_scores[pose.pose_index] += (n - rank)
            
            return np.argsort(-borda_scores).tolist()
        
        return list(range(n_poses))
    
    def calculate_consensus_score(
        self,
        pose,
        all_runs: list[list],
        pose_index: int,
    ) -> float:
        """Calculate consensus score for a specific pose."""
        scores = []
        for run in all_runs:
            for p in run:
                if p.pose_index == pose_index:
                    scores.append(p.score)
                    break
        
        if not scores:
            return float('inf')
        
        return np.mean(scores)


def analyze_poses(
    poses: list,
    receptor_mol: Chem.Mol,
    ligand_mol: Chem.Mol,
    rmsd_cutoff: float = 2.0,
) -> ClusterResult:
    """Convenience function for pose clustering."""
    analyzer = PoseAnalyzer()
    return analyzer.cluster_poses_rmsd(poses, ligand_mol, rmsd_cutoff)


def generate_ifp(
    pose,
    receptor_mol: Chem.Mol,
) -> InteractionFingerprint:
    """Convenience function for interaction fingerprint."""
    analyzer = PoseAnalyzer()
    return analyzer.generate_interaction_fingerprint(pose, receptor_mol)


def rescore_poses(
    poses: list,
    receptor_mol: Chem.Mol,
    ligand_mol: Chem.Mol,
    method: str = "interaction",
) -> list[RescoringResult]:
    """Convenience function for pose rescoring."""
    rescorer = PoseRescorer()
    
    if method == "mm_gbsa":
        return rescorer.rescore_mm_gbsa(poses, receptor_mol, ligand_mol)
    elif method == "consensus":
        return rescorer.rescore_consensus(poses, receptor_mol, ligand_mol)
    else:
        return rescorer.rescore_interaction_based(poses, receptor_mol, ligand_mol)