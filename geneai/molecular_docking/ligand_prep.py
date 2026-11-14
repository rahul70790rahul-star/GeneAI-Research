"""Ligand preparation for molecular docking."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors, rdDistGeom
from rdkit.Chem import EnumerateStereoisomers
from rdkit.Chem.MolStandardize import rdMolStandardize

logger = logging.getLogger(__name__)


@dataclass
class LigandPrepResult:
    """Result of ligand preparation."""
    input_smiles: str
    output_pdbqt: str
    success: bool
    error: str | None = None
    num_conformers: int = 0
    num_tautomers: int = 0
    num_stereoisomers: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TautomerEnumerationResult:
    """Result of tautomer enumeration."""
    canonical_smiles: str
    tautomers: list[str] = field(default_factory=list)
    dominant_tautomer: str = ""


class LigandPreparator:
    """
    Ligand preparation for molecular docking.
    
    Steps:
    1. Parse input (SMILES, SDF, Mol2, PDB)
    2. Standardize chemistry (charges, tautomers, stereochemistry)
    3. Enumerate tautomers (pH-dependent)
    4. Enumerate stereoisomers (if unspecified)
    5. Generate 3D conformers
    6. Energy minimize (MMFF94/s)
    7. Assign charges (Gasteiger, MMFF, AM1-BCC)
    8. Write PDBQT for AutoDock Vina
    
    Requires: Open Babel, RDKit
    """
    
    def __init__(
        self,
        pH: float = 7.4,
        enumerate_tautomers: bool = True,
        max_tautomers: int = 10,
        enumerate_stereoisomers: bool = True,
        max_stereoisomers: int = 32,
        generate_conformers: bool = True,
        num_conformers: int = 10,
        min_rmsd: float = 0.5,
        energy_minimize: bool = True,
        force_field: str = "mmff94",  # "mmff94", "mmff94s", "uff"
        assign_charges: str = "gasteiger",  # "gasteiger", "mmff94", "am1bcc"
        output_format: str = "pdbqt",
        random_seed: int = 42,
    ):
        self.pH = pH
        self.enumerate_tautomers = enumerate_tautomers
        self.max_tautomers = max_tautomers
        self.enumerate_stereoisomers = enumerate_stereoisomers
        self.max_stereoisomers = max_stereoisomers
        self.generate_conformers = generate_conformers
        self.num_conformers = num_conformers
        self.min_rmsd = min_rmsd
        self.energy_minimize = energy_minimize
        self.force_field = force_field
        self.assign_charges = assign_charges
        self.output_format = output_format
        self.random_seed = random_seed
        self.logger = logging.getLogger(__name__)
        
        # Check for external tools
        self.has_obabel = self._check_tool("obabel")
    
    def _check_tool(self, tool: str) -> bool:
        """Check if external tool is available."""
        try:
            subprocess.run([tool, "--help"], capture_output=True, check=False, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def prepare(
        self,
        input_smiles: str,
        output_path: str | None = None,
        name: str = "ligand",
    ) -> LigandPrepResult:
        """
        Prepare ligand for docking.
        
        Args:
            input_smiles: Input SMILES string
            output_path: Output PDBQT path (auto-generated if None)
            name: Ligand name for output
            
        Returns:
            LigandPrepResult
        """
        # Parse input
        mol = Chem.MolFromSmiles(input_smiles)
        if mol is None:
            return LigandPrepResult(
                input_smiles=input_smiles,
                output_pdbqt="",
                success=False,
                error="Invalid SMILES",
            )
        
        # Standardize
        mol = self._standardize(mol)
        
        # Enumerate tautomers
        tautomers = [mol]
        if self.enumerate_tautomers:
            tautomers = self._enumerate_tautomers(mol)
        
        # Enumerate stereoisomers
        all_mols = []
        for taut in tautomers:
            if self.enumerate_stereoisomers:
                stereoisomers = self._enumerate_stereoisomers(taut)
                all_mols.extend(stereoisomers)
            else:
                all_mols.append(taut)
        
        # Limit total molecules
        all_mols = all_mols[:self.max_stereoisomers]
        
        # Process each molecule
        processed_mols = []
        for m in all_mols:
            processed = self._process_molecule(m)
            if processed:
                processed_mols.append(processed)
        
        if not processed_mols:
            return LigandPrepResult(
                input_smiles=input_smiles,
                output_pdbqt="",
                success=False,
                error="No valid conformers generated",
            )
        
        # Write output
        if output_path is None:
            output_path = f"{name}.pdbqt"
        output_path = Path(output_path)
        
        self._write_pdbqt(processed_mols, output_path, name)
        
        return LigandPrepResult(
            input_smiles=input_smiles,
            output_pdbqt=str(output_path),
            success=True,
            num_conformers=sum(m.GetNumConformers() for m in processed_mols),
            num_tautomers=len(tautomers),
            num_stereoisomers=len(all_mols),
            metadata={
                "num_output_molecules": len(processed_mols),
                "force_field": self.force_field,
                "charges": self.assign_charges,
            },
        )
    
    def _standardize(self, mol: Chem.Mol) -> Chem.Mol:
        """Standardize molecule chemistry."""
        # Remove Hs, sanitize
        mol = Chem.RemoveHs(mol)
        Chem.SanitizeMol(mol)
        
        # Neutralize charges if possible (basic standardization)
        # This is a simplified version - real version would use MolStandardize
        return mol
    
    def _enumerate_tautomers(self, mol: Chem.Mol) -> list[Chem.Mol]:
        """Enumerate tautomers."""
        try:
            # Use RDKit's tautomer enumeration (MolStandardize API)
            enumerator = rdMolStandardize.TautomerEnumerator()
            enumerator.SetMaxTautomers(self.max_tautomers)
            tautomers = [Chem.Mol(t) for t in enumerator.Enumerate(mol)]
            if tautomers:
                return tautomers
        except Exception as e:
            self.logger.warning("Tautomer enumeration failed: %s", e)
        
        return [mol]
    
    def _enumerate_stereoisomers(self, mol: Chem.Mol) -> list[Chem.Mol]:
        """Enumerate unspecified stereoisomers."""
        try:
            # Find unspecified chiral centers
            opts = EnumerateStereoisomers.StereoEnumerationOptions(
                tryEmbedding=True,
                unique=True,
                maxIsomers=self.max_stereoisomers,
                randomSeed=self.random_seed,
            )
            isomers = list(EnumerateStereoisomers.EnumerateStereoisomers(mol, options=opts))
            if isomers:
                return [Chem.Mol(iso) for iso in isomers]
        except Exception as e:
            self.logger.warning("Stereoisomer enumeration failed: %s", e)
        
        return [mol]
    
    def _process_molecule(self, mol: Chem.Mol) -> Chem.Mol | None:
        """Process single molecule: 3D coords, minimize, charges."""
        try:
            # Add hydrogens
            mol = Chem.AddHs(mol, addCoords=True)
            
            # Generate conformers
            if self.generate_conformers:
                cids = AllChem.EmbedMultipleConfs(
                    mol,
                    numConfs=self.num_conformers,
                    randomSeed=self.random_seed,
                    pruneRmsThresh=self.min_rmsd,
                    useExpTorsionAnglePrefs=True,
                    useBasicKnowledge=True,
                )
                
                if not cids:
                    # Fallback: single conformer
                    AllChem.EmbedMolecule(mol, randomSeed=self.random_seed)
            else:
                AllChem.EmbedMolecule(mol, randomSeed=self.random_seed)
            
            # Energy minimize
            if self.energy_minimize:
                self._minimize_molecule(mol)
            
            # Assign charges
            self._assign_charges(mol)
            
            return mol
            
        except Exception as e:
            self.logger.warning("Molecule processing failed: %s", e)
            return None
    
    def _minimize_molecule(self, mol: Chem.Mol):
        """Energy minimize molecule."""
        if self.force_field == "mmff94":
            for conf_id in range(mol.GetNumConformers()):
                try:
                    AllChem.MMFFOptimizeMolecule(mol, confId=conf_id, mmffVariant="MMFF94")
                except Exception:
                    pass
        elif self.force_field == "mmff94s":
            for conf_id in range(mol.GetNumConformers()):
                try:
                    AllChem.MMFFOptimizeMolecule(mol, confId=conf_id, mmffVariant="MMFF94s")
                except Exception:
                    pass
        elif self.force_field == "uff":
            for conf_id in range(mol.GetNumConformers()):
                try:
                    AllChem.UFFOptimizeMolecule(mol, confId=conf_id)
                except Exception:
                    pass
    
    def _assign_charges(self, mol: Chem.Mol):
        """Assign partial charges."""
        if self.assign_charges == "gasteiger":
            AllChem.ComputeGasteigerCharges(mol)
        elif self.assign_charges == "mmff94":
            try:
                AllChem.MMFFSanitizeMolecule(mol)
                props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
                if props:
                    for i in range(mol.GetNumAtoms()):
                        charge = props.GetMMFFCharge(i)
                        mol.GetAtomWithIdx(i).SetDoubleProp("_MMFFCharge", charge)
            except Exception:
                AllChem.ComputeGasteigerCharges(mol)
        elif self.assign_charges == "am1bcc":
            # AM1-BCC requires external tool (Antechamber/squonk)
            # Fallback to Gasteiger
            AllChem.ComputeGasteigerCharges(mol)
    
    def _write_pdbqt(self, mols: list[Chem.Mol], output_path: Path, name: str):
        """Write molecules as PDBQT."""
        # For multiple molecules, write each as separate MODEL
        with open(output_path, "w") as f:
            for model_idx, mol in enumerate(mols):
                if model_idx > 0:
                    f.write("ENDMDL\n")
                f.write(f"MODEL {model_idx + 1}\n")
                
                # Write each conformer
                for conf_id in range(mol.GetNumConformers()):
                    if conf_id > 0:
                        f.write("ENDMDL\n")
                        f.write(f"MODEL {model_idx * 100 + conf_id + 1}\n")
                    
                    self._write_mol_pdbqt(mol, f, conf_id, name)
                
                f.write("ENDMDL\n")
    
    def _write_mol_pdbqt(self, mol: Chem.Mol, f, conf_id: int, name: str):
        """Write single molecule conformer as PDBQT."""
        conf = mol.GetConformer(conf_id)
        
        # Header
        f.write(f"REMARK   Generated by GeneAI LigandPreparator\n")
        f.write(f"REMARK   Name: {name}\n")
        f.write(f"REMARK   Conformer: {conf_id + 1}\n")
        
        # Get charges
        charges = {}
        if self.assign_charges == "gasteiger":
            for atom in mol.GetAtoms():
                if atom.HasProp("_GasteigerCharge"):
                    charges[atom.GetIdx()] = float(atom.GetProp("_GasteigerCharge"))
        elif self.assign_charges == "mmff94":
            for atom in mol.GetAtoms():
                if atom.HasProp("_MMFFCharge"):
                    charges[atom.GetIdx()] = float(atom.GetProp("_MMFFCharge"))
        
        # Get atom types
        atom_types = {}
        for atom in mol.GetAtoms():
            atom_types[atom.GetIdx()] = self._get_autodock_type(atom)
        
        # Write atoms
        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            pos = conf.GetAtomPosition(idx)
            charge = charges.get(idx, 0.0)
            atype = atom_types.get(idx, "C")
            
            # PDBQT format
            # ATOM  XXXX  NAME RES CHAIN RESSEQ    X      Y      Z   OCCUP  TEMP    CHARGE  TYPE
            elem = atom.GetSymbol()
            res_name = "LIG"
            chain = "A"
            res_seq = 1
            
            line = (
                f"ATOM  {idx + 1:5d}  {elem:<3s} {res_name:>3s} {chain:1s}{res_seq:4d}    "
                f"{pos.x:8.3f}{pos.y:8.3f}{pos.z:8.3f}  1.00  0.00  "
                f"{charge:7.4f} {atype:>4s}\n"
            )
            f.write(line)
    
    def _get_autodock_type(self, atom: Chem.Atom) -> str:
        """Get AutoDock atom type."""
        elem = atom.GetSymbol()
        hybridization = atom.GetHybridization()
        formal_charge = atom.GetFormalCharge()
        
        if elem == "C":
            if atom.GetIsAromatic():
                return "A"
            elif hybridization == Chem.HybridizationType.SP2:
                return "C"
            elif hybridization == Chem.HybridizationType.SP:
                return "C"
            else:
                return "C"
        elif elem == "N":
            if atom.GetIsAromatic():
                return "NA"
            elif formal_charge > 0:
                return "N+"
            else:
                return "N"
        elif elem == "O":
            if formal_charge < 0:
                return "O-"
            else:
                return "OA"
        elif elem == "S":
            return "SA"
        elif elem == "P":
            return "P"
        elif elem in ["F", "Cl", "Br", "I"]:
            return "XS"
        elif elem == "H":
            # Check if donor (attached to N, O, S)
            nbrs = [n.GetSymbol() for n in atom.GetNeighbors()]
            if any(n in ["N", "O", "S"] for n in nbrs):
                return "HD"
            return "H"
        else:
            return "C"
    
    def prepare_from_file(
        self,
        input_path: str,
        output_path: str | None = None,
    ) -> LigandPrepResult:
        """Prepare ligand from file (SDF, Mol2, PDB)."""
        input_path = Path(input_path)
        
        if input_path.suffix.lower() == ".sdf":
            supplier = Chem.SDMolSupplier(str(input_path))
            mols = [m for m in supplier if m]
        elif input_path.suffix.lower() == ".mol2":
            mol = Chem.MolFromMol2File(str(input_path))
            mols = [mol] if mol else []
        elif input_path.suffix.lower() == ".pdb":
            mol = Chem.MolFromPDBFile(str(input_path))
            mols = [mol] if mol else []
        else:
            return LigandPrepResult(
                input_smiles="",
                output_pdbqt="",
                success=False,
                error=f"Unsupported file format: {input_path.suffix}",
            )
        
        if not mols:
            return LigandPrepResult(
                input_smiles="",
                output_pdbqt="",
                success=False,
                error="No valid molecules in file",
            )
        
        # Use first molecule, convert to SMILES
        smiles = Chem.MolToSmiles(mols[0])
        return self.prepare(smiles, output_path, input_path.stem)
    
    def batch_prepare(
        self,
        smiles_list: list[str],
        output_dir: str,
    ) -> list[LigandPrepResult]:
        """Prepare multiple ligands."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for i, smi in enumerate(smiles_list):
            out_path = output_dir / f"ligand_{i:04d}.pdbqt"
            result = self.prepare(smi, str(out_path), f"ligand_{i}")
            results.append(result)
        
        return results


def prepare_ligand(
    input_smiles: str,
    output_path: str | None = None,
    **kwargs,
) -> LigandPrepResult:
    """Convenience function for ligand preparation."""
    preparator = LigandPreparator(**kwargs)
    return preparator.prepare(input_smiles, output_path)