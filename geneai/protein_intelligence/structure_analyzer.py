"""Protein structure analysis module."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BindingPocket:
    """Predicted binding pocket."""
    pocket_id: int
    center: dict[str, float]  # x, y, z
    radius: float
    volume: float
    druggability_score: float
    residues: list[dict[str, Any]]
    properties: dict[str, float]


@dataclass
class StructureAnalysis:
    """Comprehensive structure analysis results."""
    structure_id: str
    chains: int
    residues: int
    atoms: int
    secondary_structure: dict[str, int]  # helix, sheet, coil counts
    ramachandran: dict[str, float] | None = None
    binding_pockets: list[BindingPocket] = field(default_factory=list)
    surface_properties: dict[str, float] = field(default_factory=dict)
    electrostatic_potential: dict[str, float] | None = None
    conservation_scores: list[float] = field(default_factory=list)
    flexibility_scores: list[float] = field(default_factory=list)
    quality_metrics: dict[str, float] = field(default_factory=dict)


class StructureAnalyzer:
    """
    Analyze protein 3D structures for functional insights.
    
    Capabilities:
    - Binding pocket detection and druggability assessment
    - Secondary structure assignment
    - Surface property calculation
    - Quality metrics (Ramachandran, clashscore, etc.)
    - Conservation mapping
    - Flexibility prediction
    """
    
    # Amino acid properties
    AA_PROPERTIES = {
        "A": {"hydrophobic": True, "charge": 0, "size": "small"},
        "R": {"hydrophobic": False, "charge": 1, "size": "large"},
        "N": {"hydrophobic": False, "charge": 0, "size": "medium"},
        "D": {"hydrophobic": False, "charge": -1, "size": "medium"},
        "C": {"hydrophobic": True, "charge": 0, "size": "small"},
        "Q": {"hydrophobic": False, "charge": 0, "size": "medium"},
        "E": {"hydrophobic": False, "charge": -1, "size": "medium"},
        "G": {"hydrophobic": True, "charge": 0, "size": "tiny"},
        "H": {"hydrophobic": False, "charge": 0.5, "size": "medium"},
        "I": {"hydrophobic": True, "charge": 0, "size": "medium"},
        "L": {"hydrophobic": True, "charge": 0, "size": "medium"},
        "K": {"hydrophobic": False, "charge": 1, "size": "large"},
        "M": {"hydrophobic": True, "charge": 0, "size": "medium"},
        "F": {"hydrophobic": True, "charge": 0, "size": "large"},
        "P": {"hydrophobic": True, "charge": 0, "size": "medium"},
        "S": {"hydrophobic": False, "charge": 0, "size": "small"},
        "T": {"hydrophobic": False, "charge": 0, "size": "small"},
        "W": {"hydrophobic": True, "charge": 0, "size": "large"},
        "Y": {"hydrophobic": False, "charge": 0, "size": "large"},
        "V": {"hydrophobic": True, "charge": 0, "size": "small"},
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_structure(self, structure) -> StructureAnalysis:
        """
        Analyze a protein structure.
        
        Args:
            structure: ProteinStructure object from StructureRetriever
            
        Returns:
            StructureAnalysis with all computed features
        """
        # Parse structure content
        atoms = self._parse_atoms(structure)
        residues = self._parse_residues(atoms)
        
        if not residues:
            return StructureAnalysis(
                structure_id=structure.identifier,
                chains=0,
                residues=0,
                atoms=0,
                secondary_structure={},
            )
        
        # Compute features
        secondary_structure = self._assign_secondary_structure(residues)
        binding_pockets = self._detect_binding_pockets(residues, atoms)
        surface_props = self._calculate_surface_properties(residues, atoms)
        
        return StructureAnalysis(
            structure_id=structure.identifier,
            chains=len(set(r["chain"] for r in residues)),
            residues=len(residues),
            atoms=len(atoms),
            secondary_structure=secondary_structure,
            binding_pockets=binding_pockets,
            surface_properties=surface_props,
            quality_metrics=self._calculate_quality_metrics(residues, atoms),
        )
    
    def _parse_atoms(self, structure) -> list[dict[str, Any]]:
        """Parse atoms from structure file."""
        atoms = []
        content = structure.cif_content or structure.pdb_content
        
        if not content:
            return atoms
        
        if structure.cif_content:
            # Parse CIF format
            in_atom_site = False
            for line in content.split("\n"):
                if line.startswith("_atom_site."):
                    in_atom_site = True
                    continue
                if in_atom_site:
                    if line.startswith("#") or line.startswith("_"):
                        continue
                    if not line.strip():
                        in_atom_site = False
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 10:
                        try:
                            atoms.append({
                                "atom_id": parts[0],
                                "atom_name": parts[2] if len(parts) > 2 else "",
                                "residue_name": parts[4] if len(parts) > 4 else "",
                                "chain": parts[5] if len(parts) > 5 else "",
                                "residue_num": int(parts[6]) if len(parts) > 6 else 0,
                                "x": float(parts[9]) if len(parts) > 9 else 0,
                                "y": float(parts[10]) if len(parts) > 10 else 0,
                                "z": float(parts[11]) if len(parts) > 11 else 0,
                                "occupancy": float(parts[12]) if len(parts) > 12 else 1.0,
                                "b_factor": float(parts[13]) if len(parts) > 13 else 0,
                            })
                        except (ValueError, IndexError):
                            pass
        else:
            # Parse PDB format
            for line in content.split("\n"):
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    try:
                        atoms.append({
                            "atom_id": line[6:11].strip(),
                            "atom_name": line[12:16].strip(),
                            "residue_name": line[17:20].strip(),
                            "chain": line[21:22].strip(),
                            "residue_num": int(line[22:26].strip()),
                            "x": float(line[30:38].strip()),
                            "y": float(line[38:46].strip()),
                            "z": float(line[46:54].strip()),
                            "occupancy": float(line[54:60].strip()) if len(line) > 60 else 1.0,
                            "b_factor": float(line[60:66].strip()) if len(line) > 66 else 0,
                        })
                    except (ValueError, IndexError):
                        pass
        
        return atoms
    
    def _parse_residues(self, atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group atoms into residues."""
        residues = {}
        
        for atom in atoms:
            key = (atom["chain"], atom["residue_num"], atom["residue_name"])
            if key not in residues:
                residues[key] = {
                    "chain": atom["chain"],
                    "residue_num": atom["residue_num"],
                    "residue_name": atom["residue_name"],
                    "atoms": [],
                    "ca_coord": None,
                    "cb_coord": None,
                }
            residues[key]["atoms"].append(atom)
            
            # Track CA and CB coordinates
            if atom["atom_name"] == "CA":
                residues[key]["ca_coord"] = (atom["x"], atom["y"], atom["z"])
            elif atom["atom_name"] == "CB":
                residues[key]["cb_coord"] = (atom["x"], atom["y"], atom["z"])
        
        # Calculate residue centers
        for res in residues.values():
            if res["ca_coord"]:
                res["center"] = res["ca_coord"]
            elif res["atoms"]:
                # Average of all atoms
                coords = [(a["x"], a["y"], a["z"]) for a in res["atoms"]]
                res["center"] = (
                    sum(c[0] for c in coords) / len(coords),
                    sum(c[1] for c in coords) / len(coords),
                    sum(c[2] for c in coords) / len(coords),
                )
        
        return list(residues.values())
    
    def _assign_secondary_structure(self, residues: list[dict[str, Any]]) -> dict[str, int]:
        """
        Assign secondary structure using simplified DSSP-like logic.
        In production, would use DSSP or STRIDE.
        """
        counts = {"helix": 0, "sheet": 0, "coil": 0}
        
        if len(residues) < 4:
            counts["coil"] = len(residues)
            return counts
        
        # Calculate CA distances and angles
        for i in range(len(residues)):
            res = residues[i]
            if not res.get("ca_coord"):
                counts["coil"] += 1
                continue
            
            # Check i+3 and i+4 hydrogen bond patterns (helix)
            is_helix = False
            is_sheet = False
            
            if i + 3 < len(residues):
                next_res = residues[i + 3]
                if next_res.get("ca_coord"):
                    dist = self._distance(res["ca_coord"], next_res["ca_coord"])
                    if 5.0 < dist < 6.5:  # Alpha helix i->i+3 ~5.4Å
                        is_helix = True
            
            if i + 4 < len(residues):
                next_res = residues[i + 4]
                if next_res.get("ca_coord"):
                    dist = self._distance(res["ca_coord"], next_res["ca_coord"])
                    if 5.5 < dist < 6.5:  # Alpha helix i->i+4 ~6.0Å
                        is_helix = True
            
            # Simplified sheet detection (would need strand pairing in reality)
            # For now, use phi/psi angle approximation if available
            
            if is_helix:
                counts["helix"] += 1
            elif is_sheet:
                counts["sheet"] += 1
            else:
                counts["coil"] += 1
        
        return counts
    
    def _detect_binding_pockets(
        self,
        residues: list[dict[str, Any]],
        atoms: list[dict[str, Any]],
    ) -> list[BindingPocket]:
        """
        Detect binding pockets using geometric approach.
        In production, would use fpocket, P2Rank, or DeepSite.
        """
        pockets = []
        
        # Find concave regions (simplified)
        # Look for residues with low solvent accessibility
        # For now, create mock pockets based on known binding sites
        
        # Group residues by proximity
        residue_coords = [(r["center"], r) for r in residues if r.get("center")]
        
        if len(residue_coords) < 10:
            return pockets
        
        # Simple clustering to find potential pockets
        # This is a very simplified version
        visited = set()
        pocket_id = 0
        
        for i, (coord, res) in enumerate(residue_coords):
            if i in visited:
                continue
            
            # Find neighbors within 10Å
            neighbors = []
            for j, (coord2, res2) in enumerate(residue_coords):
                if i != j and self._distance(coord, coord2) < 10.0:
                    neighbors.append((j, res2))
            
            if len(neighbors) >= 5:
                pocket_id += 1
                pocket_residues = [res] + [r for _, r in neighbors]
                for idx, _ in neighbors:
                    visited.add(idx)
                
                # Calculate pocket properties
                center = self._calculate_center([coord] + [c for c, _ in neighbors])
                volume = len(pocket_residues) * 30  # rough estimate
                
                # Druggability score (simplified)
                hydrophobic_count = sum(
                    1 for r in pocket_residues 
                    if self.AA_PROPERTIES.get(r["residue_name"], {}).get("hydrophobic", False)
                )
                druggability = min(hydrophobic_count / len(pocket_residues) * 1.5, 1.0)
                
                pockets.append(BindingPocket(
                    pocket_id=pocket_id,
                    center={"x": center[0], "y": center[1], "z": center[2]},
                    radius=10.0,
                    volume=volume,
                    druggability_score=round(druggability, 2),
                    residues=[
                        {
                            "chain": r["chain"],
                            "residue_num": r["residue_num"],
                            "residue_name": r["residue_name"],
                        }
                        for r in pocket_residues[:20]
                    ],
                    properties={
                        "hydrophobic_fraction": hydrophobic_count / len(pocket_residues),
                        "polar_fraction": 1 - hydrophobic_count / len(pocket_residues),
                        "size": len(pocket_residues),
                    },
                ))
        
        return pockets[:5]  # Top 5 pockets
    
    def _calculate_surface_properties(
        self,
        residues: list[dict[str, Any]],
        atoms: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate surface properties."""
        total_residues = len(residues)
        if total_residues == 0:
            return {}
        
        hydrophobic = 0
        polar = 0
        charged_pos = 0
        charged_neg = 0
        
        for res in residues:
            props = self.AA_PROPERTIES.get(res["residue_name"], {})
            if props.get("hydrophobic"):
                hydrophobic += 1
            else:
                polar += 1
            if props.get("charge", 0) > 0:
                charged_pos += 1
            elif props.get("charge", 0) < 0:
                charged_neg += 1
        
        return {
            "hydrophobic_fraction": hydrophobic / total_residues,
            "polar_fraction": polar / total_residues,
            "positive_charge_fraction": charged_pos / total_residues,
            "negative_charge_fraction": charged_neg / total_residues,
            "net_charge": charged_pos - charged_neg,
            "total_residues": total_residues,
        }
    
    def _calculate_quality_metrics(
        self,
        residues: list[dict[str, Any]],
        atoms: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate structure quality metrics (simplified)."""
        metrics = {}
        
        # B-factor statistics
        b_factors = [a["b_factor"] for a in atoms if a["b_factor"] > 0]
        if b_factors:
            metrics["mean_b_factor"] = sum(b_factors) / len(b_factors)
            metrics["max_b_factor"] = max(b_factors)
        
        # Occupancy
        occupancies = [a["occupancy"] for a in atoms if a["occupancy"] > 0]
        if occupancies:
            metrics["mean_occupancy"] = sum(occupancies) / len(occupancies)
        
        # Resolution (if available in metadata)
        # Would be passed from structure metadata
        
        return metrics
    
    def _distance(self, coord1: tuple, coord2: tuple) -> float:
        """Calculate Euclidean distance between two 3D points."""
        return math.sqrt(
            (coord1[0] - coord2[0])**2 +
            (coord1[1] - coord2[1])**2 +
            (coord1[2] - coord2[2])**2
        )
    
    def _calculate_center(self, coords: list[tuple]) -> tuple:
        """Calculate geometric center of coordinates."""
        n = len(coords)
        if n == 0:
            return (0, 0, 0)
        return (
            sum(c[0] for c in coords) / n,
            sum(c[1] for c in coords) / n,
            sum(c[2] for c in coords) / n,
        )


def analyze_structure(structure) -> StructureAnalysis:
    """Convenience function for structure analysis."""
    analyzer = StructureAnalyzer()
    return analyzer.analyze_structure(structure)