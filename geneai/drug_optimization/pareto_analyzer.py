"""Pareto front analysis for multi-objective optimization."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import ConvexHull

logger = logging.getLogger(__name__)


@dataclass
class ParetoSolution:
    """A solution on the Pareto front."""
    params: dict[str, Any]
    objectives: dict[str, float]
    rank: int = 0
    crowding_distance: float = 0.0
    dominated_count: int = 0
    dominates: list[int] = field(default_factory=list)


@dataclass
class ParetoFront:
    """Pareto front with metadata."""
    solutions: list[ParetoSolution]
    n_objectives: int
    objective_names: list[str]
    hypervolume: float | None = None
    spacing: float | None = None
    spread: float | None = None


class ParetoAnalyzer:
    """
    Analyze and visualize Pareto fronts from multi-objective optimization.
    """
    
    def __init__(self, minimize: list[bool] | None = None):
        """
        Initialize analyzer.
        
        Args:
            minimize: List of booleans indicating whether each objective should be minimized
        """
        self.minimize = minimize or []
        self.logger = logging.getLogger(__name__)
    
    def compute_pareto_front(
        self,
        solutions: list[dict[str, Any]],
        objective_keys: list[str] | None = None,
    ) -> ParetoFront:
        """
        Compute Pareto front from solutions.
        
        Args:
            solutions: List of dicts with 'params' and 'objectives' keys
            objective_keys: List of objective names (in order)
            
        Returns:
            ParetoFront with non-dominated solutions
        """
        if not solutions:
            return ParetoFront(
                solutions=[],
                n_objectives=0,
                objective_names=objective_keys or [],
            )
        
        # Extract objective values
        if objective_keys is None:
            objective_keys = list(solutions[0]["objectives"].keys())
        
        n_obj = len(objective_keys)
        obj_matrix = np.array([
            [sol["objectives"].get(k, 0) for k in objective_keys]
            for sol in solutions
        ])
        
        # Apply minimization/maximization
        if self.minimize:
            for i, minimize in enumerate(self.minimize):
                if not minimize and i < n_obj:
                    obj_matrix[:, i] = -obj_matrix[:, i]
        else:
            # Default: minimize all
            pass
        
        # Fast non-dominated sorting
        pareto_indices = self._fast_non_dominated_sort(obj_matrix)
        
        # Get first front (rank 0)
        front_indices = pareto_indices[0]
        
        # Create ParetoSolution objects
        pareto_solutions = []
        for idx in front_indices:
            sol = solutions[idx]
            pareto_solutions.append(ParetoSolution(
                params=sol["params"],
                objectives=sol["objectives"],
                rank=0,
            ))
        
        # Calculate crowding distances
        if len(pareto_solutions) > 2:
            self._calculate_crowding_distance(pareto_solutions, objective_keys)
        
        # Calculate metrics
        hypervolume = self._calculate_hypervolume(obj_matrix[front_indices])
        spacing = self._calculate_spacing(obj_matrix[front_indices])
        spread = self._calculate_spread(obj_matrix[front_indices])
        
        return ParetoFront(
            solutions=pareto_solutions,
            n_objectives=n_obj,
            objective_names=objective_keys,
            hypervolume=hypervolume,
            spacing=spacing,
            spread=spread,
        )
    
    def _fast_non_dominated_sort(self, obj_matrix: np.ndarray) -> list[np.ndarray]:
        """Fast non-dominated sorting (NSGA-II)."""
        n = obj_matrix.shape[0]
        
        # Domination counts and sets
        dominated_count = np.zeros(n, dtype=int)
        dominates = [[] for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                if self._dominates(obj_matrix[i], obj_matrix[j]):
                    dominates[i].append(j)
                    dominated_count[j] += 1
                elif self._dominates(obj_matrix[j], obj_matrix[i]):
                    dominates[j].append(i)
                    dominated_count[i] += 1
        
        # Find fronts
        fronts = []
        current_front = np.where(dominated_count == 0)[0]
        
        while len(current_front) > 0:
            fronts.append(current_front)
            next_front = []
            
            for i in current_front:
                for j in dominates[i]:
                    dominated_count[j] -= 1
                    if dominated_count[j] == 0:
                        next_front.append(j)
            
            current_front = np.array(next_front)
        
        return fronts
    
    def _dominates(self, obj1: np.ndarray, obj2: np.ndarray) -> bool:
        """Check if obj1 dominates obj2 (both minimized)."""
        return np.all(obj1 <= obj2) and np.any(obj1 < obj2)
    
    def _calculate_crowding_distance(
        self,
        solutions: list[ParetoSolution],
        objective_keys: list[str],
    ):
        """Calculate crowding distance for diversity preservation."""
        n = len(solutions)
        if n <= 2:
            for s in solutions:
                s.crowding_distance = float('inf')
            return
        
        # Extract objective values
        obj_matrix = np.array([
            [s.objectives.get(k, 0) for k in objective_keys]
            for s in solutions
        ])
        
        # Normalize each objective
        obj_min = obj_matrix.min(axis=0)
        obj_max = obj_matrix.max(axis=0)
        obj_range = obj_max - obj_min
        obj_range[obj_range == 0] = 1  # Avoid division by zero
        
        normalized = (obj_matrix - obj_min) / obj_range
        
        # Calculate crowding distance
        distances = np.zeros(n)
        
        for i in range(obj_matrix.shape[1]):
            # Sort by objective i
            sorted_indices = np.argsort(normalized[:, i])
            
            # Boundary points get infinite distance
            distances[sorted_indices[0]] = float('inf')
            distances[sorted_indices[-1]] = float('inf')
            
            # Interior points
            for j in range(1, n - 1):
                distances[sorted_indices[j]] += (
                    normalized[sorted_indices[j + 1], i] - 
                    normalized[sorted_indices[j - 1], i]
                )
        
        for idx, sol in enumerate(solutions):
            sol.crowding_distance = distances[idx]
    
    def _calculate_hypervolume(self, obj_matrix: np.ndarray, ref_point: np.ndarray | None = None) -> float | None:
        """Calculate hypervolume indicator (2D/3D only for simplicity)."""
        if obj_matrix.shape[0] == 0:
            return 0.0
        
        n_obj = obj_matrix.shape[1]
        
        if n_obj > 3:
            return None  # High-dimensional hypervolume is complex
        
        if ref_point is None:
            # Use nadir point + 10% as reference
            ref_point = obj_matrix.max(axis=0) * 1.1
        
        try:
            if n_obj == 2:
                # 2D hypervolume: area dominated by front
                # Sort by first objective
                sorted_idx = np.argsort(obj_matrix[:, 0])
                sorted_pts = obj_matrix[sorted_idx]
                
                hv = 0.0
                prev_x = ref_point[0]
                for pt in sorted_pts:
                    hv += (prev_x - pt[0]) * (ref_point[1] - pt[1])
                    prev_x = pt[0]
                return float(hv)
            
            elif n_obj == 3:
                # 3D: use ConvexHull approximation
                # Add reference point
                pts = np.vstack([obj_matrix, ref_point])
                hull = ConvexHull(pts)
                return float(hull.volume)
        
        except Exception:
            return None
        
        return None
    
    def _calculate_spacing(self, obj_matrix: np.ndarray) -> float | None:
        """Calculate spacing metric (diversity)."""
        if obj_matrix.shape[0] < 2:
            return 0.0
        
        n = obj_matrix.shape[0]
        distances = []
        
        for i in range(n):
            min_dist = float('inf')
            for j in range(n):
                if i != j:
                    dist = np.linalg.norm(obj_matrix[i] - obj_matrix[j])
                    min_dist = min(min_dist, dist)
            distances.append(min_dist)
        
        mean_d = np.mean(distances)
        spacing = np.sqrt(np.sum((np.array(distances) - mean_d) ** 2) / (n - 1))
        
        return float(spacing)
    
    def _calculate_spread(self, obj_matrix: np.ndarray) -> float | None:
        """Calculate spread metric (extent of front)."""
        if obj_matrix.shape[0] < 2:
            return 0.0
        
        # Distance between extreme points
        min_vals = obj_matrix.min(axis=0)
        max_vals = obj_matrix.max(axis=0)
        
        # Diagonal of bounding box
        spread = np.linalg.norm(max_vals - min_vals)
        
        return float(spread)
    
    def find_knee_points(
        self,
        front: ParetoFront,
        n_knees: int = 3,
    ) -> list[ParetoSolution]:
        """
        Find knee points (best trade-offs) on Pareto front.
        
        Knee points are where small improvement in one objective
        requires large sacrifice in another.
        """
        if len(front.solutions) <= n_knees:
            return front.solutions
        
        # Extract objective matrix
        obj_matrix = np.array([
            [s.objectives.get(k, 0) for k in front.objective_names]
            for s in front.solutions
        ])
        
        # Normalize
        obj_min = obj_matrix.min(axis=0)
        obj_max = obj_matrix.max(axis=0)
        obj_range = obj_max - obj_min
        obj_range[obj_range == 0] = 1
        normalized = (obj_matrix - obj_min) / obj_range
        
        # For 2D, knee is point with maximum angle
        if obj_matrix.shape[1] == 2:
            angles = []
            for i in range(len(normalized)):
                # Vectors to neighbors
                prev_idx = (i - 1) % len(normalized)
                next_idx = (i + 1) % len(normalized)
                
                v1 = normalized[prev_idx] - normalized[i]
                v2 = normalized[next_idx] - normalized[i]
                
                # Angle between vectors
                cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-10)
                angle = np.arccos(np.clip(cos_angle, -1, 1))
                angles.append(angle)
            
            # Largest angle = knee
            knee_indices = np.argsort(angles)[-n_knees:]
            return [front.solutions[i] for i in knee_indices]
        
        # For higher dimensions, use distance to utopia point
        utopia = normalized.min(axis=0)
        distances = np.linalg.norm(normalized - utopia, axis=1)
        knee_indices = np.argsort(distances)[:n_knees]
        
        return [front.solutions[i] for i in knee_indices]
    
    def compare_fronts(
        self,
        front1: ParetoFront,
        front2: ParetoFront,
    ) -> dict[str, float]:
        """Compare two Pareto fronts."""
        metrics = {}
        
        # Hypervolume comparison
        if front1.hypervolume is not None and front2.hypervolume is not None:
            metrics["hypervolume_ratio"] = front1.hypervolume / (front2.hypervolume + 1e-10)
            metrics["hypervolume_diff"] = front1.hypervolume - front2.hypervolume
        
        # Spacing comparison
        if front1.spacing is not None and front2.spacing is not None:
            metrics["spacing_ratio"] = front1.spacing / (front2.spacing + 1e-10)
        
        # Spread comparison
        if front1.spread is not None and front2.spread is not None:
            metrics["spread_ratio"] = front1.spread / (front2.spread + 1e-10)
        
        # Number of solutions
        metrics["n_solutions_ratio"] = len(front1.solutions) / max(len(front2.solutions), 1)
        
        # Dominance comparison
        dominates_12 = 0
        dominates_21 = 0
        
        obj_names = front1.objective_names
        for s1 in front1.solutions:
            for s2 in front2.solutions:
                o1 = np.array([s1.objectives.get(k, 0) for k in obj_names])
                o2 = np.array([s2.objectives.get(k, 0) for k in obj_names])
                
                if self._dominates(o1, o2):
                    dominates_12 += 1
                elif self._dominates(o2, o1):
                    dominates_21 += 1
        
        metrics["dominates_1_over_2"] = dominates_12
        metrics["dominates_2_over_1"] = dominates_21
        
        return metrics


def analyze_pareto(
    solutions: list[dict[str, Any]],
    objective_keys: list[str] | None = None,
    minimize: list[bool] | None = None,
) -> ParetoFront:
    """Convenience function for Pareto analysis."""
    analyzer = ParetoAnalyzer(minimize)
    return analyzer.compute_pareto_front(solutions, objective_keys)


def find_knee_points(
    front: ParetoFront,
    n_knees: int = 3,
) -> list[ParetoSolution]:
    """Convenience function for finding knee points."""
    analyzer = ParetoAnalyzer()
    return analyzer.find_knee_points(front, n_knees)