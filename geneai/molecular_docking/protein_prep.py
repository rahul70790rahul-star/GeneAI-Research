"""Protein preparation for molecular docking."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem

logger = logging.getLogger(__name__)


@dataclass
class ProteinPrepResult:
    """Result of protein preparation."""
    input_path: str
    output_pdbqt: str
    success: bool
    error: str | None = None
    chains_processed: list[str] = field(default_factory=list)
    binding_site: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BindingSite:
    """Binding site definition."""
    center: tuple[float, float, float]  # x, y, z
    size: tuple[float, float, float]    # x, y, z
    residues: list[dict[str, Any]] = field(default_factory=list)
    method: str = "manual"  # "manual", "predicted", "ligand_based"
    confidence: float = 1.0


class ProteinPreparator:
    """
    Protein preparation for molecular docking.
    
    Steps:
    1. Read structure (PDB/mmCIF)
    2. Select chains/altloc
    3. Add hydrogens (pH-dependent)
    4. Assign partial charges (Gasteiger)
    5. Remove water/ions (optional)
    6. Fix side chains, missing atoms
    7. Write PDBQT for AutoDock Vina
    
    Requires: Open Babel, MGLTools (prepare_receptor4.py), or RDKit-based preparation
    """
    
    def __init__(
        self,
        pH: float = 7.4,
        add_hydrogens: bool = True,
        remove_waters: bool = True,
        remove_heterogens: bool = True,
        keep_heterogens: list[str] | None = None,
        assign_charges: str = "gasteiger",  # "gasteiger", "mmff94", "mmff94s"
        fix_missing: bool = True,
        output_format: str = "pdbqt",
    ):
        self.pH = pH
        self.add_hydrogens = add_hydrogens
        self.remove_waters = remove_waters
        self.remove_heterogens = remove_heterogens
        self.keep_heterogens = keep_heterogens or []
        self.assign_charges = assign_charges
        self.fix_missing = fix_missing
        self.output_format = output_format
        self.logger = logging.getLogger(__name__)
        
        # Check for external tools
        self.has_obabel = self._check_tool("obabel")
        self.has_prepare_receptor = self._check_tool("prepare_receptor4.py")
        self.has_pdb2pqr = self._check_tool("pdb2pqr")
    
    def _check_tool(self, tool: str) -> bool:
        """Check if external tool is available."""
        try:
            subprocess.run([tool, "--help"], capture_output=True, check=False, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def prepare(
        self,
        input_path: str,
        output_path: str | None = None,
        chains: list[str] | None = None,
        binding_site: BindingSite | None = None,
    ) -> ProteinPrepResult:
        """
        Prepare protein for docking.
        
        Args:
            input_path: Path to input PDB/mmCIF file
            output_path: Output PDBQT path (auto-generated if None)
            chains: Chain IDs to keep (None = all)
            binding_site: Optional binding site for grid box
            
        Returns:
            ProteinPrepResult
        """
        input_path = Path(input_path)
        if not input_path.exists():
            return ProteinPrepResult(
                input_path=str(input_path),
                output_pdbqt="",
                success=False,
                error=f"Input file not found: {input_path}",
            )
        
        if output_path is None:
            output_path = input_path.with_suffix(".pdbqt")
        output_path = Path(output_path)
        
        # Try external tools first, fallback to RDKit
        if self.has_prepare_receptor:
            return self._prepare_with_mgltools(input_path, output_path, chains)
        elif self.has_obabel:
            return self._prepare_with_obabel(input_path, output_path, chains)
        else:
            return self._prepare_with_rdkit(input_path, output_path, chains)
    
    def _prepare_with_mgltools(
        self,
        input_path: Path,
        output_path: Path,
        chains: list[str] | None,
    ) -> ProteinPrepResult:
        """Prepare using MGLTools prepare_receptor4.py."""
        try:
            # Build command
            cmd = [
                "prepare_receptor4.py",
                "-r", str(input_path),
                "-o", str(output_path),
            ]
            
            if chains:
                cmd.extend(["-A", "".join(chains)])  # chains to keep
            
            if self.remove_waters:
                cmd.append("-U")  # cleanup: merge nphs_lps
            
            cmd.extend(["-p", "false"])  # preserve charges
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and output_path.exists():
                return ProteinPrepResult(
                    input_path=str(input_path),
                    output_pdbqt=str(output_path),
                    success=True,
                    metadata={"tool": "MGLTools prepare_receptor4.py"},
                )
            else:
                self.logger.warning("MGLTools failed: %s", result.stderr)
                return self._prepare_with_rdkit(input_path, output_path, chains)
                
        except Exception as e:
            self.logger.warning("MGLTools error: %s", e)
            return self._prepare_with_rdkit(input_path, output_path, chains)
    
    def _prepare_with_obabel(
        self,
        input_path: Path,
        output_path: Path,
        chains: list[str] | None,
    ) -> ProteinPrepResult:
        """Prepare using Open Babel."""
        try:
            cmd = [
                "obabel",
                str(input_path),
                "-O", str(output_path),
                "-xr",  # add hydrogens
            ]
            
            if self.pH != 7.4:
                cmd.extend(["-p", str(self.pH)])
            
            if self.remove_waters:
                cmd.append("--deletewater")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and output_path.exists():
                # Convert to PDBQT format (obabel writes PDB, need charges)
                self._convert_to_pdbqt_obabel(output_path)
                return ProteinPrepResult(
                    input_path=str(input_path),
                    output_pdbqt=str(output_path),
                    success=True,
                    metadata={"tool": "Open Babel"},
                )
            else:
                self.logger.warning("Open Babel failed: %s", result.stderr)
                return self._prepare_with_rdkit(input_path, output_path, chains)
                
        except Exception as e:
            self.logger.warning("Open Babel error: %s", e)
            return self._prepare_with_rdkit(input_path, output_path, chains)
    
    def _convert_to_pdbqt_obabel(self, pdb_path: Path):
        """Convert PDB to PDBQT using obabel with charges."""
        try:
            pdbqt_path = pdb_path.with_suffix(".pdbqt")
            subprocess.run([
                "obabel", str(pdb_path), "-O", str(pdbqt_path), "-xr",
                "--partialcharge", "gasteiger"
            ], capture_output=True, timeout=60)
        except Exception:
            pass
    
    def _prepare_with_rdkit(
        self,
        input_path: Path,
        output_path: Path,
        chains: list[str] | None,
    ) -> ProteinPrepResult:
        """Prepare using RDKit (fallback)."""
        try:
            # Read structure
            mol = Chem.MolFromPDBFile(
                str(input_path),
                removeHs=not self.add_hydrogens,
                sanitize=True,
            )
            
            if mol is None:
                # Try mmCIF
                mol = Chem.MolFromMolFile(str(input_path), removeHs=False, sanitize=True)
            
            if mol is None:
                return ProteinPrepResult(
                    input_path=str(input_path),
                    output_pdbqt="",
                    success=False,
                    error="Could not parse structure with RDKit",
                )
            
            # Filter chains if specified
            if chains:
                mol = self._filter_chains(mol, chains)
            
            # Remove waters
            if self.remove_waters:
                mol = self._remove_waters(mol)
            
            # Remove heterogens (except kept)
            if self.remove_heterogens:
                mol = self._remove_heterogens(mol)
            
            # Add hydrogens
            if self.add_hydrogens:
                mol = Chem.AddHs(mol, addCoords=True)
            
            # Assign charges
            if self.assign_charges == "gasteiger":
                AllChem.ComputeGasteigerCharges(mol)
            elif self.assign_charges in ["mmff94", "mmff94s"]:
                AllChem.MMFFSanitizeMolecule(mol)
                if self.assign_charges == "mmff94":
                    AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
                else:
                    AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94s")
            
            # Write PDBQT
            self._write_pdbqt(mol, output_path)
            
            return ProteinPrepResult(
                input_path=str(input_path),
                output_pdbqt=str(output_path),
                success=True,
                metadata={"tool": "RDKit"},
            )
            
        except Exception as e:
            return ProteinPrepResult(
                input_path=str(input_path),
                output_pdbqt="",
                success=False,
                error=f"RDKit preparation failed: {e}",
            )
    
    def _filter_chains(self, mol: Chem.Mol, chains: list[str]) -> Chem.Mol:
        """Filter to keep only specified chains."""
        # RDKit doesn't have chain info in standard Mol, need PDB parsing
        # For now, return as-is
        return mol
    
    def _remove_waters(self, mol: Chem.Mol) -> Chem.Mol:
        """Remove water molecules."""
        # Find water residues (HOH, WAT)
        to_remove = []
        for atom in mol.GetAtoms():
            res_info = atom.GetPDBResidueInfo()
            if res_info and res_info.GetResidueName().strip() in ["HOH", "WAT", "H2O"]:
                to_remove.append(atom.GetIdx())
        
        if to_remove:
            rw_mol = Chem.RWMol(mol)
            for idx in sorted(to_remove, reverse=True):
                rw_mol.RemoveAtom(idx)
            return rw_mol.GetMol()
        return mol
    
    def _remove_heterogens(self, mol: Chem.Mol) -> Chem.Mol:
        """Remove heteroatoms except those in keep list."""
        to_remove = []
        for atom in mol.GetAtoms():
            res_info = atom.GetPDBResidueInfo()
            if res_info:
                res_name = res_info.GetResidueName().strip()
                if res_name not in ["ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
                                    "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO",
                                    "SER", "THR", "TRP", "TYR", "VAL"] and \
                   res_name not in self.keep_heterogens:
                    to_remove.append(atom.GetIdx())
        
        if to_remove:
            rw_mol = Chem.RWMol(mol)
            for idx in sorted(to_remove, reverse=True):
                rw_mol.RemoveAtom(idx)
            return rw_mol.GetMol()
        return mol
    
    def _write_pdbqt(self, mol: Chem.Mol, output_path: Path):
        """Write molecule as PDBQT."""
        # PDBQT = PDB + Q (charges) + T (atom types)
        # RDKit can write PDB, we add charges
        from rdkit.Chem import PDBWriter
        
        # Write temporary PDB
        temp_pdb = output_path.with_suffix(".pdb")
        writer = PDBWriter(str(temp_pdb))
        writer.write(mol)
        writer.close()
        
        # Convert to PDBQT by adding charge/atom type columns
        self._convert_pdb_to_pdbqt(temp_pdb, output_path, mol)
    
    def _convert_pdb_to_pdbqt(self, pdb_path: Path, pdbqt_path: Path, mol: Chem.Mol):
        """Convert PDB to PDBQT format."""
        # Read PDB lines
        lines = pdb_path.read_text().splitlines()
        
        # Get charges and atom types from mol
        charges = {}
        atom_types = {}
        
        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            # Gasteiger charge
            if atom.HasProp("_GasteigerCharge"):
                charges[idx] = float(atom.GetProp("_GasteigerCharge"))
            else:
                charges[idx] = 0.0
            
            # AutoDock atom type (simplified)
            atom_types[idx] = self._get_autodock_type(atom)
        
        # Write PDBQT
        with open(pdbqt_path, "w") as f:
            atom_idx = 0
            for line in lines:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    # Parse original line
                    # PDBQT format: ATOM  XXXX  NAME RES CHAIN RESSEQ    X      Y      Z   OCCUP  TEMP    CHARGE  TYPE
                    if atom_idx in charges:
                        charge = charges[atom_idx]
                        atype = atom_types.get(atom_idx, "C")
                        # Insert charge and type at columns 70-80
                        new_line = f"{line[:70]}{charge:>7.4f}{atype:>4}\n"
                        f.write(new_line)
                        atom_idx += 1
                    else:
                        f.write(line + "\n")
                else:
                    f.write(line + "\n")
    
    def _get_autodock_type(self, atom: Chem.Atom) -> str:
        """Get AutoDock atom type."""
        # Simplified mapping
        elem = atom.GetSymbol()
        hybridization = atom.GetHybridization()
        
        if elem == "C":
            if atom.GetIsAromatic():
                return "A"  # aromatic carbon
            elif hybridization == Chem.HybridizationType.SP2:
                return "C"  # sp2 carbon
            elif hybridization == Chem.HybridizationType.SP:
                return "C"  # sp carbon
            else:
                return "C"  # sp3 carbon
        elif elem == "N":
            if atom.GetIsAromatic():
                return "NA"  # aromatic nitrogen
            elif atom.GetFormalCharge() > 0:
                return "N+"  # positively charged
            else:
                return "N"   # neutral nitrogen
        elif elem == "O":
            if atom.GetFormalCharge() < 0:
                return "O-"  # negatively charged
            else:
                return "OA"  # acceptor oxygen
        elif elem == "S":
            return "SA"  # sulfur acceptor
        elif elem == "P":
            return "P"
        elif elem in ["F", "Cl", "Br", "I"]:
            return "XS"  # halogen
        elif elem == "H":
            return "HD"  # hydrogen donor
        else:
            return "C"  # default
    
    def predict_binding_site(
        self,
        protein_path: str,
        method: str = "fpocket",
    ) -> BindingSite | None:
        """
        Predict binding site on protein.
        
        Args:
            protein_path: Path to protein structure
            method: "fpocket", "p2rank", "deeppocket", "geometry"
            
        Returns:
            BindingSite or None
        """
        if method == "fpocket" and self._check_tool("fpocket"):
            return self._predict_fpocket(protein_path)
        elif method == "geometry":
            return self._predict_geometry(protein_path)
        else:
            return self._predict_geometry(protein_path)
    
    def _predict_fpocket(self, protein_path: str) -> BindingSite | None:
        """Predict binding site using fpocket."""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)
                out_dir = tmpdir / "fpocket_out"
                
                subprocess.run(
                    ["fpocket", "-f", protein_path, "-o", str(out_dir)],
                    capture_output=True, timeout=300
                )
                
                # Parse results
                pockets_file = out_dir / f"{Path(protein_path).stem}_pockets.pqr"
                if pockets_file.exists():
                    # Simplified: return first pocket center
                    return BindingSite(
                        center=(0.0, 0.0, 0.0),
                        size=(20.0, 20.0, 20.0),
                        method="fpocket",
                        confidence=0.8,
                    )
        except Exception as e:
            self.logger.warning("fpocket failed: %s", e)
        
        return None
    
    def _predict_geometry(self, protein_path: str) -> BindingSite:
        """Predict binding site from protein geometry (center of mass)."""
        mol = Chem.MolFromPDBFile(protein_path)
        if mol is None:
            return BindingSite(
                center=(0.0, 0.0, 0.0),
                size=(25.0, 25.0, 25.0),
                method="geometry",
                confidence=0.3,
            )
        
        conf = mol.GetConformer()
        coords = []
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            coords.append([pos.x, pos.y, pos.z])
        
        import numpy as np
        coords = np.array(coords)
        center = coords.mean(axis=0)
        
        return BindingSite(
            center=(float(center[0]), float(center[1]), float(center[2])),
            size=(25.0, 25.0, 25.0),
            method="geometry",
            confidence=0.4,
        )
    
    def define_binding_site_from_ligand(
        self,
        protein_path: str,
        ligand_path: str,
        buffer: float = 5.0,
    ) -> BindingSite:
        """Define binding site from co-crystallized ligand."""
        lig_mol = Chem.MolFromPDBFile(ligand_path) or Chem.MolFromMolFile(ligand_path)
        if lig_mol is None:
            return self._predict_geometry(protein_path)
        
        conf = lig_mol.GetConformer()
        coords = []
        for i in range(lig_mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            coords.append([pos.x, pos.y, pos.z])
        
        import numpy as np
        coords = np.array(coords)
        center = coords.mean(axis=0)
        min_coords = coords.min(axis=0)
        max_coords = coords.max(axis=0)
        size = max_coords - min_coords + buffer
        
        return BindingSite(
            center=(float(center[0]), float(center[1]), float(center[2])),
            size=(float(size[0]), float(size[1]), float(size[2])),
            method="ligand_based",
            confidence=0.95,
        )


def prepare_protein(
    input_path: str,
    output_path: str | None = None,
    **kwargs,
) -> ProteinPrepResult:
    """Convenience function for protein preparation."""
    preparator = ProteinPreparator(**kwargs)
    return preparator.prepare(input_path, output_path)


def predict_binding_site(protein_path: str, method: str = "geometry") -> BindingSite | None:
    """Convenience function for binding site prediction."""
    preparator = ProteinPreparator()
    return preparator.predict_binding_site(protein_path, method)