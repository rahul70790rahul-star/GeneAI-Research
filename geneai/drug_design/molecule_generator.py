"""Molecule generation module for drug design."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, BRICS, Draw
from rdkit.Chem import Descriptors, rdMolDescriptors

logger = logging.getLogger(__name__)


@dataclass
class GeneratedMolecule:
    """A generated molecule with metadata."""
    smiles: str
    name: str | None = None
    generation_method: str = "unknown"
    parent_smiles: str | None = None
    properties: dict[str, float] = field(default_factory=dict)
    validity: bool = True
    synthesizability_score: float | None = None
    novelty_score: float | None = None
    diversity_score: float | None = None


class GenerationStrategy(str, Enum):
    """Supported molecule-generation strategies."""

    FRAGMENT_BASED = "fragment_based"
    SCAFFOLD_HOPPING = "scaffold_hopping"
    R_GROUP_ENUMERATION = "r_group_enumeration"
    SIMILARITY_BASED = "similarity_based"
    CONSTRAINED_RANDOM = "constrained_random"


@dataclass
class GenerationConstraints:
    """User-facing drug-likeness constraints for molecule generation."""

    mw_range: tuple[float, float] = (150.0, 500.0)
    logp_range: tuple[float, float] = (-2.0, 5.0)
    tpsa_range: tuple[float, float] = (20.0, 140.0)
    max_rotatable_bonds: int = 10
    max_hbd: int = 5
    max_hba: int = 10
    apply_lipinski: bool = True
    apply_ghose: bool = True
    apply_veber: bool = True

    def to_constraint_dict(self) -> dict[str, tuple]:
        """Convert to the ``PROPERTY_CONSTRAINTS``-style mapping used internally."""
        return {
            "mw": tuple(self.mw_range),
            "logp": tuple(self.logp_range),
            "hbd": (0, self.max_hbd),
            "hba": (0, self.max_hba),
            "tpsa": tuple(self.tpsa_range),
            "rotatable_bonds": (0, self.max_rotatable_bonds),
            "aromatic_rings": (0, 4),
            "heavy_atoms": (10, 40),
            "formal_charge": (-2, 2),
        }


class MoleculeGenerator:
    """
    Generate drug-like molecules using multiple strategies.
    
    Strategies:
    - Fragment-based (BRICS decomposition/recombination)
    - Scaffold hopping (core replacement)
    - R-group enumeration
    - Random generation with constraints
    - Template-based (reaction SMARTS)
    - Similarity-based (neighborhood exploration)
    """
    
    # Drug-like property ranges (Lipinski + extensions)
    PROPERTY_CONSTRAINTS = {
        "mw": (150, 500),
        "logp": (-2, 5),
        "hbd": (0, 5),
        "hba": (0, 10),
        "tpsa": (20, 140),
        "rotatable_bonds": (0, 10),
        "aromatic_rings": (0, 4),
        "heavy_atoms": (10, 40),
        "formal_charge": (-2, 2),
    }
    
    # Common scaffolds for drug design
    COMMON_SCAFFOLDS = {
        "benzene": "c1ccccc1",
        "pyridine": "c1ccncc1",
        "pyrimidine": "c1ncccn1",
        "imidazole": "c1c[nH]c1",
        "indole": "c1ccc2[nH]ccc2c1",
        "purine": "c1nc2ncnc2n1",
        "quinoline": "c1ccc2ccccc2n1",
        "isoquinoline": "c1ccc2cnccc2c1",
        "benzodiazepine": "C1=CC=C2N=CCN=C2C=C1",
        "piperidine": "C1CCNCC1",
        "piperazine": "C1CNCCN1",
        "morpholine": "C1COCCN1",
        "thiophene": "c1ccsc1",
        "furan": "c1ccoc1",
    }
    
    # R-groups for enumeration
    R_GROUPS = {
        "alkyl": ["C", "CC", "CCC", "CCCC", "C(C)C", "CC(C)C"],
        "aryl": ["c1ccccc1", "c1ccc(cc1)F", "c1ccc(cc1)Cl", "c1ccc(cc1)OC"],
        "heteroaryl": ["c1ccncc1", "c1ccncc1", "c1ncccn1", "c1c[nH]c1"],
        "halogen": ["F", "Cl", "Br"],
        "hydroxyl": ["O"],
        "amino": ["N", "NC", "NCC", "N(C)C"],
        "carbonyl": ["C(=O)O", "C(=O)N", "C(=O)C"],
        "sulfonyl": ["S(=O)(=O)N", "S(=O)(=O)C"],
        "cyano": ["C#N"],
        "nitro": ["N(=O)=O"],
        "trifluoromethyl": ["C(F)(F)F"],
    }
    
    def __init__(self, random_seed: int | None = None):
        if random_seed is not None:
            random.seed(random_seed)
        self.logger = logging.getLogger(__name__)
    
    def generate_fragment_based(
        self,
        seed_smiles: list[str],
        num_molecules: int = 100,
        min_fragments: int = 2,
        max_fragments: int = 4,
    ) -> list[GeneratedMolecule]:
        """
        Generate molecules by recombining BRICS fragments.
        
        Args:
            seed_smiles: List of seed molecule SMILES
            num_molecules: Number of molecules to generate
            min_fragments: Minimum fragments per molecule
            max_fragments: Maximum fragments per molecule
            
        Returns:
            List of generated molecules
        """
        # Extract fragments from seeds
        all_fragments = []
        for smi in seed_smiles:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                fragments = list(BRICS.BRICSDecompose(mol))
                all_fragments.extend(fragments)
        
        if not all_fragments:
            return []
        
        # Remove duplicates
        unique_fragments = list(set(all_fragments))
        self.logger.info(f"Extracted {len(unique_fragments)} unique fragments")
        
        generated = []
        attempts = 0
        max_attempts = num_molecules * 10
        
        while len(generated) < num_molecules and attempts < max_attempts:
            attempts += 1
            
            # Randomly select fragments
            n_frags = random.randint(min_fragments, max_fragments)
            selected = random.sample(unique_fragments, min(n_frags, len(unique_fragments)))
            
            # Try to combine
            try:
                combined = self._combine_fragments(selected)
                if combined:
                    smiles = Chem.MolToSmiles(combined)
                    if self._check_drug_likeness(smiles):
                        props = self._calculate_properties(smiles)
                        generated.append(GeneratedMolecule(
                            smiles=smiles,
                            name=f"FRAG_{len(generated):04d}",
                            generation_method="fragment_based",
                            parent_smiles=".".join(seed_smiles),
                            properties=props,
                            validity=True,
                        ))
            except Exception:
                continue
        
        return generated
    
    def _combine_fragments(self, fragments: list[str]):
        """Combine fragments using BRICS."""
        mols = [Chem.MolFromSmiles(f) for f in fragments]
        mols = [m for m in mols if m is not None]
        
        if len(mols) < 2:
            return None
        
        # Use BRICS to combine
        try:
            combined = BRICS.BRICSBuild(mols)
            for mol in combined:
                if mol:
                    Chem.SanitizeMol(mol)
                    return mol
        except Exception:
            pass
        
        return None
    
    def generate_scaffold_hopping(
        self,
        reference_smiles: str,
        num_molecules: int = 50,
        keep_substituents: bool = True,
    ) -> list[GeneratedMolecule]:
        """
        Perform scaffold hopping - replace core scaffold while keeping substituents.
        
        Args:
            reference_smiles: Reference molecule SMILES
            num_molecules: Number of molecules to generate
            keep_substituents: Whether to preserve substitution pattern
            
        Returns:
            List of generated molecules
        """
        ref_mol = Chem.MolFromSmiles(reference_smiles)
        if not ref_mol:
            return []
        
        # Extract scaffold using Murcko scaffold
        from rdkit.Chem.Scaffolds import MurckoScaffold
        scaffold = MurckoScaffold.GetScaffoldForMol(ref_mol)
        scaffold_smiles = Chem.MolToSmiles(scaffold) if scaffold else ""
        
        # Get substituents (simplified - would use more sophisticated approach)
        generated = []
        
        for scaffold_name, scaffold_smi in self.COMMON_SCAFFOLDS.items():
            if scaffold_name == "benzene" and "c1ccccc1" not in reference_smiles:
                continue  # Skip if too different
            
            for _ in range(num_molecules // len(self.COMMON_SCAFFOLDS) + 1):
                if len(generated) >= num_molecules:
                    break
                
                try:
                    new_mol = self._attach_substituents(scaffold_smi, ref_mol)
                    if new_mol:
                        smiles = Chem.MolToSmiles(new_mol)
                        if self._check_drug_likeness(smiles) and smiles != reference_smiles:
                            props = self._calculate_properties(smiles)
                            generated.append(GeneratedMolecule(
                                smiles=smiles,
                                name=f"SCAFFOLD_{scaffold_name}_{len(generated):04d}",
                                generation_method="scaffold_hopping",
                                parent_smiles=reference_smiles,
                                properties=props,
                                validity=True,
                            ))
                except Exception:
                    continue
        
        return generated
    
    def _attach_substituents(self, scaffold_smi: str, ref_mol):
        """Attach reference substituents to new scaffold (simplified)."""
        scaffold_mol = Chem.MolFromSmiles(scaffold_smi)
        if not scaffold_mol:
            return None
        
        # Find attachment points on scaffold (aromatic carbons with H)
        # This is simplified - real implementation would use more sophisticated chemistry
        try:
            # Try to substitute at available positions
            scaffold_editable = Chem.RWMol(scaffold_mol)
            
            # Add random R-groups at available positions
            num_substitutions = random.randint(1, 3)
            for _ in range(num_substitutions):
                # Find aromatic carbons
                aromatic_carbons = [
                    atom.GetIdx() for atom in scaffold_editable.GetAtoms()
                    if atom.GetIsAromatic() and atom.GetAtomicNum() == 6
                    and atom.GetTotalNumHs() > 0
                ]
                
                if not aromatic_carbons:
                    break
                
                pos = random.choice(aromatic_carbons)
                r_group = random.choice(
                    self.R_GROUPS["alkyl"] + self.R_GROUPS["halogen"] + self.R_GROUPS["heteroaryl"]
                )
                
                # Attach R-group (simplified)
                r_mol = Chem.MolFromSmiles(r_group)
                if r_mol:
                    # This is very simplified - real implementation would use proper chemistry
                    pass
            
            # For now, return scaffold with minimal modification
            return scaffold_editable.GetMol()
            
        except Exception:
            return scaffold_mol
    
    def generate_r_group_enumeration(
        self,
        core_smiles: str,
        attachment_points: list[int],
        r_groups: dict[str, list[str]] | None = None,
        max_combinations: int = 1000,
    ) -> list[GeneratedMolecule]:
        """
        Enumerate R-group combinations on a core scaffold.
        
        Args:
            core_smiles: Core scaffold SMILES with attachment points marked
            attachment_points: Atom indices for R-group attachment
            r_groups: Dict of position -> list of R-group SMILES
            max_combinations: Maximum combinations to generate
            
        Returns:
            List of generated molecules
        """
        if r_groups is None:
            r_groups = {i: self.R_GROUPS["alkyl"] + self.R_GROUPS["aryl"] + self.R_GROUPS["heteroaryl"] 
                       for i in attachment_points}
        
        core_mol = Chem.MolFromSmiles(core_smiles)
        if not core_mol:
            return []
        
        generated = []
        positions = list(r_groups.keys())
        
        # Generate combinations
        import itertools
        r_group_lists = [r_groups[pos] for pos in positions]
        
        count = 0
        for combo in itertools.product(*r_group_lists):
            if count >= max_combinations:
                break
            
            try:
                mol = self._attach_r_groups(core_mol, attachment_points, combo)
                if mol:
                    smiles = Chem.MolToSmiles(mol)
                    if self._check_drug_likeness(smiles):
                        props = self._calculate_properties(smiles)
                        generated.append(GeneratedMolecule(
                            smiles=smiles,
                            name=f"RGROUP_{len(generated):04d}",
                            generation_method="r_group_enumeration",
                            parent_smiles=core_smiles,
                            properties=props,
                            validity=True,
                        ))
                        count += 1
            except Exception:
                continue
        
        return generated
    
    def _attach_r_groups(self, core_mol, attachment_points: list[int], r_groups: tuple) -> Chem.Mol | None:
        """Attach R-groups to core at specified positions."""
        # This is a placeholder - real implementation would use proper chemistry
        # For now, return core with minimal modification
        return core_mol
    
    def generate_similarity_based(
        self,
        reference_smiles: str,
        num_molecules: int = 50,
        similarity_threshold: float = 0.7,
        method: str = "morgan",
    ) -> list[GeneratedMolecule]:
        """
        Generate molecules similar to a reference.
        
        Args:
            reference_smiles: Reference molecule SMILES
            num_molecules: Number to generate
            similarity_threshold: Minimum Tanimoto similarity
            method: Fingerprint method ("morgan", "rdkit", "maccs")
            
        Returns:
            List of generated molecules
        """
        ref_mol = Chem.MolFromSmiles(reference_smiles)
        if not ref_mol:
            return []
        
        # Get reference fingerprint
        if method == "morgan":
            ref_fp = AllChem.GetMorganFingerprintAsBitVect(ref_mol, 2, nBits=2048)
        elif method == "rdkit":
            ref_fp = Chem.RDKFingerprint(ref_mol)
        elif method == "maccs":
            from rdkit.Chem import MACCSkeys
            ref_fp = MACCSkeys.GenMACCSKeys(ref_mol)
        else:
            ref_fp = AllChem.GetMorganFingerprintAsBitVect(ref_mol, 2, nBits=2048)
        
        # Generate analogs by small modifications
        generated = []
        
        # Simple modifications: add/remove/replace small groups
        modifications = [
            ("add_methyl", "[CH3]"),
            ("add_fluoro", "[F]"),
            ("add_chloro", "[Cl]"),
            ("add_hydroxyl", "[OH]"),
            ("add_amino", "[NH2]"),
            ("replace_CH3_with_CF3", "C(F)(F)F"),
            ("add_cyano", "C#N"),
        ]
        
        for mod_name, mod_group in modifications:
            if len(generated) >= num_molecules:
                break
            
            for _ in range(num_molecules // len(modifications) + 1):
                try:
                    new_mol = self._apply_modification(ref_mol, mod_group)
                    if new_mol:
                        smiles = Chem.MolToSmiles(new_mol)
                        if smiles != reference_smiles:
                            sim = self._calculate_similarity(smiles, ref_fp, method)
                            if sim >= similarity_threshold:
                                props = self._calculate_properties(smiles)
                                generated.append(GeneratedMolecule(
                                    smiles=smiles,
                                    name=f"SIM_{mod_name}_{len(generated):04d}",
                                    generation_method=f"similarity_{method}",
                                    parent_smiles=reference_smiles,
                                    properties=props,
                                    validity=True,
                                ))
                except Exception:
                    continue
        
        return generated
    
    def _apply_modification(self, mol: Chem.Mol, mod_group: str) -> Chem.Mol | None:
        """Apply a simple modification to a molecule."""
        # Placeholder - real implementation would use reaction SMARTS
        return mol
    
    def _calculate_similarity(self, smiles: str, ref_fp, method: str) -> float:
        """Calculate Tanimoto similarity to reference."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return 0.0
        
        if method == "morgan":
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        elif method == "rdkit":
            fp = Chem.RDKFingerprint(mol)
        elif method == "maccs":
            from rdkit.Chem import MACCSkeys
            fp = MACCSkeys.GenMACCSKeys(mol)
        else:
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        
        from rdkit.DataStructs import TanimotoSimilarity
        return TanimotoSimilarity(fp, ref_fp)
    
    def generate_constrained_random(
        self,
        num_molecules: int = 100,
        constraints: "GenerationConstraints | dict[str, tuple] | None" = None,
    ) -> list[GeneratedMolecule]:
        """
        Generate random drug-like molecules within constraints.
        
        Args:
            num_molecules: Number to generate
            constraints: Property constraints (overrides defaults)
            
        Returns:
            List of generated molecules
        """
        if isinstance(constraints, GenerationConstraints):
            props = constraints.to_constraint_dict()
        else:
            props = constraints or self.PROPERTY_CONSTRAINTS
        
        generated = []
        # Start from common scaffolds
        scaffolds = list(self.COMMON_SCAFFOLDS.values())
        
        while len(generated) < num_molecules:
            scaffold = random.choice(scaffolds)
            mol = Chem.MolFromSmiles(scaffold)
            
            if not mol:
                continue
            
            # Add random decorations
            decorated = self._randomly_decorate(mol)
            if decorated:
                smiles = Chem.MolToSmiles(decorated)
                if self._check_drug_likeness(smiles, props):
                    properties = self._calculate_properties(smiles)
                    generated.append(GeneratedMolecule(
                        smiles=smiles,
                        name=f"RANDOM_{len(generated):04d}",
                        generation_method="constrained_random",
                        properties=properties,
                        validity=True,
                    ))
        
        return generated
    
    def _randomly_decorate(self, mol: Chem.Mol) -> Chem.Mol | None:
        """Randomly decorate a molecule with substituents."""
        # Placeholder
        return mol
    
    def _check_drug_likeness(
        self,
        smiles: str,
        constraints: dict[str, tuple] | None = None,
    ) -> bool:
        """Check if molecule passes drug-likeness filters."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return False
        
        constraints = constraints or self.PROPERTY_CONSTRAINTS
        
        # Calculate properties
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        heavy_atoms = mol.GetNumHeavyAtoms()
        formal_charge = Chem.GetFormalCharge(mol)
        
        # Check constraints
        if not (constraints["mw"][0] <= mw <= constraints["mw"][1]):
            return False
        if not (constraints["logp"][0] <= logp <= constraints["logp"][1]):
            return False
        if not (constraints["hbd"][0] <= hbd <= constraints["hbd"][1]):
            return False
        if not (constraints["hba"][0] <= hba <= constraints["hba"][1]):
            return False
        if not (constraints["tpsa"][0] <= tpsa <= constraints["tpsa"][1]):
            return False
        if not (constraints["rotatable_bonds"][0] <= rot_bonds <= constraints["rotatable_bonds"][1]):
            return False
        if not (constraints["aromatic_rings"][0] <= aromatic_rings <= constraints["aromatic_rings"][1]):
            return False
        if not (constraints["heavy_atoms"][0] <= heavy_atoms <= constraints["heavy_atoms"][1]):
            return False
        if not (constraints["formal_charge"][0] <= formal_charge <= constraints["formal_charge"][1]):
            return False
        
        # Additional filters
        # PAINS filter (simplified)
        if self._has_pains(mol):
            return False
        
        return True
    
    def _has_pains(self, mol: Chem.Mol) -> bool:
        """Check for PAINS (Pan-Assay Interference Compounds)."""
        # Simplified PAINS patterns
        pains_patterns = [
            "c1ccc(cc1)N=Nc2ccccc2",  # Azo dyes
            "C(=O)Nc1ccc(cc1)N",  # Anilides
            "c1ccc(cc1)S(=O)(=O)N",  # Sulfonamides (some)
        ]
        
        smiles = Chem.MolToSmiles(mol)
        for pattern in pains_patterns:
            pat_mol = Chem.MolFromSmarts(pattern)
            if pat_mol and mol.HasSubstructMatch(pat_mol):
                return True
        return False
    
    def _calculate_properties(self, smiles: str) -> dict[str, float]:
        """Calculate molecular properties."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return {}
        
        return {
            "mw": Descriptors.MolWt(mol),
            "logp": Descriptors.MolLogP(mol),
            "hbd": Descriptors.NumHDonors(mol),
            "hba": Descriptors.NumHAcceptors(mol),
            "tpsa": rdMolDescriptors.CalcTPSA(mol),
            "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "formal_charge": Chem.GetFormalCharge(mol),
            "qed": self._calculate_qed(mol),
            "sa_score": self._calculate_sa_score(mol),
        }
    
    def _calculate_qed(self, mol: Chem.Mol) -> float:
        """Calculate Quantitative Estimate of Drug-likeness (QED)."""
        try:
            from rdkit.Chem import QED
            return QED.qed(mol)
        except Exception:
            return 0.5
    
    def _calculate_sa_score(self, mol: Chem.Mol) -> float:
        """Calculate Synthetic Accessibility Score (simplified)."""
        # Simplified SA score based on complexity
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_heteroatoms = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in [1, 6])
        complexity = num_rings * 0.5 + num_heteroatoms * 0.2
        return min(1.0 + complexity, 10.0)


def generate_molecules(
    method: str,
    **kwargs,
) -> list[GeneratedMolecule]:
    """Convenience function for molecule generation."""
    generator = MoleculeGenerator()
    
    if method == "fragment_based":
        return generator.generate_fragment_based(**kwargs)
    elif method == "scaffold_hopping":
        return generator.generate_scaffold_hopping(**kwargs)
    elif method == "r_group_enumeration":
        return generator.generate_r_group_enumeration(**kwargs)
    elif method == "similarity_based":
        return generator.generate_similarity_based(**kwargs)
    elif method == "constrained_random":
        return generator.generate_constrained_random(**kwargs)
    else:
        raise ValueError(f"Unknown generation method: {method}")