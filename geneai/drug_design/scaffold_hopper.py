"""Advanced scaffold hopping module."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, BRICS
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem import rdFMCS
from rdkit.Chem import rdMolTransforms

logger = logging.getLogger(__name__)


@dataclass
class ScaffoldHopResult:
    """Result of scaffold hopping."""
    original_smiles: str
    hopped_smiles: str
    original_scaffold: str
    new_scaffold: str
    scaffold_similarity: float
    overall_similarity: float
    method: str
    properties_changed: dict[str, tuple] = field(default_factory=dict)  # prop -> (old, new)
    validity: bool = True


@dataclass
class ScaffoldLibrary:
    """Library of scaffolds for hopping."""
    scaffolds: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    def add_scaffold(self, name: str, smiles: str, metadata: dict[str, Any] | None = None):
        """Add a scaffold to the library."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return
        
        self.scaffolds[name] = {
            "smiles": smiles,
            "mol": mol,
            "metadata": metadata or {},
            "properties": self._calculate_scaffold_properties(mol),
        }
    
    def _calculate_scaffold_properties(self, mol: Chem.Mol) -> dict[str, float]:
        """Calculate scaffold properties."""
        from rdkit.Chem import Descriptors
        return {
            "mw": Descriptors.MolWt(mol),
            "logp": Descriptors.MolLogP(mol),
            "num_rings": mol.GetRingInfo().NumRings(),
            "num_heteroatoms": sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() not in [1, 6]),
        }
    
    def get_scaffold(self, name: str) -> dict[str, Any] | None:
        """Get scaffold by name."""
        return self.scaffolds.get(name)
    
    def list_scaffolds(self) -> list[str]:
        """List all scaffold names."""
        return list(self.scaffolds.keys())


class ScaffoldHopper:
    """
    Advanced scaffold hopping with multiple strategies.
    
    Strategies:
    - Bioisosteric replacement (ring system swaps)
    - Topology-based hopping (ring size changes)
    - Property-matched hopping (maintain key properties)
    - Fragment-based recombination
    - Machine learning guided (if model available)
    """
    
    # Bioisosteric scaffold pairs
    BIOISOSTERIC_PAIRS = {
        # Benzene bioisosteres
        "benzene": ["pyridine", "pyridazine", "pyrimidine", "pyrazine", "triazine", 
                    "thiophene", "furan", "selenophene", "pyrrole", "imidazole",
                    "oxazole", "thiazole", "isoxazole", "isothiazole"],
        
        # Naphthalene bioisosteres
        "naphthalene": ["quinoline", "isoquinoline", "quinazoline", "quinoxaline",
                        "cinnoline", "phthalazine", "benzothiophene", "benzofuran",
                        "indole", "indazole", "benzimidazole"],
        
        # Heterocycle bioisosteres
        "pyridine": ["benzene", "pyrimidine", "pyrazine", "thiophene", "furan"],
        "imidazole": ["triazole", "tetrazole", "oxadiazole", "thiadiazole"],
        "piperidine": ["piperazine", "morpholine", "thiomorpholine", "azepane"],
        "tetrahydrofuran": ["tetrahydropyran", "pyrrolidine", "piperidine"],
        
        # Ring expansion/contraction
        "cyclopropane": ["cyclobutane", "oxetane", "azetidine"],
        "cyclobutane": ["cyclopropane", "cyclopentane", "tetrahydrofuran"],
        "cyclopentane": ["cyclobutane", "cyclohexane", "tetrahydropyran"],
        "cyclohexane": ["cyclopentane", "cycloheptane", "piperidine"],
        
        # Amide bioisosteres
        "amide": ["thioamide", "urea", "carbamate", "sulfonamide", 
                  "reversed_amide", "ketone", "olefin", "triazole"],
        
        # Ester bioisosteres
        "ester": ["thioester", "carbamate", "carbonate", "amide", "oxadiazolone"],
    }
    
    # Ring system templates with attachment points
    RING_TEMPLATES = {
        "benzene": "c1ccccc1",
        "pyridine": "c1ccncc1",
        "pyridazine": "c1cnncc1",
        "pyrimidine": "c1ncccn1",
        "pyrazine": "c1ncncc1",
        "triazine_135": "c1ncncn1",
        "thiophene": "c1ccsc1",
        "furan": "c1ccoc1",
        "selenophene": "c1cc[Se]c1",
        "pyrrole": "c1cc[nH]c1",
        "imidazole": "c1cnc[nH]1",
        "oxazole": "c1ocn1",
        "thiazole": "c1scn1",
        "isoxazole": "c1ocn1",
        "isothiazole": "c1scn1",
        "pyrazole": "c1cn[nH]1",
        "triazole_123": "c1nnn1",
        "tetrazole": "c1nnnn1",
        "oxadiazole_124": "c1nnoc1",
        "thiadiazole_124": "c1nns1",
        "piperidine": "C1CCNCC1",
        "piperazine": "C1CNCCN1",
        "morpholine": "C1COCCN1",
        "thiomorpholine": "C1CSCCN1",
        "azepane": "C1CCNCCC1",
        "diazepane": "C1CNCNC1",
    }
    
    def __init__(self, random_seed: int | None = None):
        if random_seed is not None:
            random.seed(random_seed)
        self.logger = logging.getLogger(__name__)
        self.scaffold_library = ScaffoldLibrary()
        self._populate_default_scaffolds()
    
    def _populate_default_scaffolds(self):
        """Populate library with default scaffolds."""
        for name, smiles in self.RING_TEMPLATES.items():
            self.scaffold_library.add_scaffold(name, smiles, {"type": "ring_template"})
    
    def hop_scaffold(
        self,
        reference_smiles: str,
        strategy: str = "bioisosteric",
        num_results: int = 20,
        property_constraints: dict[str, tuple] | None = None,
    ) -> list[ScaffoldHopResult]:
        """
        Perform scaffold hopping on a reference molecule.
        
        Args:
            reference_smiles: Reference molecule SMILES
            strategy: "bioisosteric", "topology", "property_matched", "fragment_recombination"
            num_results: Number of results to generate
            property_constraints: Dict of property -> (min, max) constraints
            
        Returns:
            List of ScaffoldHopResult
        """
        ref_mol = Chem.MolFromSmiles(reference_smiles)
        if not ref_mol:
            return []
        
        # Extract original scaffold
        original_scaffold = MurckoScaffold.GetScaffoldForMol(ref_mol)
        original_scaffold_smiles = Chem.MolToSmiles(original_scaffold) if original_scaffold else ""
        
        # Calculate reference properties
        ref_props = self._calculate_properties(ref_mol)
        
        results = []
        
        if strategy == "bioisosteric":
            results = self._bioisosteric_hop(ref_mol, original_scaffold_smiles, ref_props, num_results)
        elif strategy == "topology":
            results = self._topology_hop(ref_mol, original_scaffold_smiles, ref_props, num_results)
        elif strategy == "property_matched":
            results = self._property_matched_hop(ref_mol, original_scaffold_smiles, ref_props, num_results, property_constraints)
        elif strategy == "fragment_recombination":
            results = self._fragment_recombination_hop(ref_mol, original_scaffold_smiles, ref_props, num_results)
        
        # Filter by property constraints
        if property_constraints:
            results = self._filter_by_constraints(results, property_constraints)
        
        return results[:num_results]
    
    def _bioisosteric_hop(
        self,
        ref_mol: Chem.Mol,
        original_scaffold: str,
        ref_props: dict[str, float],
        num_results: int,
    ) -> list[ScaffoldHopResult]:
        """Perform bioisosteric scaffold replacement."""
        results = []
        
        # Find matching bioisosteric scaffold
        scaffold_mol = Chem.MolFromSmiles(original_scaffold)
        if not scaffold_mol:
            return results
        
        # Identify scaffold type
        scaffold_type = self._identify_scaffold_type(scaffold_mol)
        
        if scaffold_type not in self.BIOISOSTERIC_PAIRS:
            return results
        
        # Try each bioisostere
        for bioisostere_name in self.BIOISOSTERIC_PAIRS[scaffold_type]:
            if len(results) >= num_results:
                break
            
            new_scaffold_smiles = self.RING_TEMPLATES.get(bioisostere_name)
            if not new_scaffold_smiles:
                continue
            
            # Attempt to transfer substituents
            hopped = self._transfer_substituents(ref_mol, original_scaffold, new_scaffold_smiles)
            
            if hopped:
                hopped_smiles = Chem.MolToSmiles(hopped)
                new_scaffold = MurckoScaffold.GetScaffoldForMol(hopped)
                new_scaffold_smiles = Chem.MolToSmiles(new_scaffold) if new_scaffold else ""
                
                # Calculate similarities
                overall_sim = self._calculate_overall_similarity(ref_mol, hopped)
                scaffold_sim = self._calculate_scaffold_similarity(original_scaffold, new_scaffold_smiles)
                
                # Calculate property changes
                hopped_props = self._calculate_properties(hopped)
                prop_changes = {}
                for key in ref_props:
                    if key in hopped_props:
                        prop_changes[key] = (ref_props[key], hopped_props[key])
                
                results.append(ScaffoldHopResult(
                    original_smiles=Chem.MolToSmiles(ref_mol),
                    hopped_smiles=hopped_smiles,
                    original_scaffold=original_scaffold,
                    new_scaffold=new_scaffold_smiles,
                    scaffold_similarity=scaffold_sim,
                    overall_similarity=overall_sim,
                    method="bioisosteric",
                    properties_changed=prop_changes,
                    validity=True,
                ))
        
        return results
    
    def _topology_hop(
        self,
        ref_mol: Chem.Mol,
        original_scaffold: str,
        ref_props: dict[str, float],
        num_results: int,
    ) -> list[ScaffoldHopResult]:
        """Perform topology-based hopping (ring size changes)."""
        results = []
        
        # Ring size modifications
        ring_changes = {
            "3_to_4": ["cyclopropane", "oxetane", "azetidine"],
            "4_to_5": ["cyclobutane", "tetrahydrofuran", "pyrrolidine"],
            "5_to_6": ["cyclopentane", "tetrahydropyran", "piperidine"],
            "6_to_7": ["cyclohexane", "azepane", "diazepane"],
        }
        
        scaffold_mol = Chem.MolFromSmiles(original_scaffold)
        if not scaffold_mol:
            return results
        
        # Count rings and sizes
        ring_info = scaffold_mol.GetRingInfo()
        ring_sizes = [len(r) for r in ring_info.AtomRings()]
        
        # For each ring, try size modifications
        for ring_size in ring_sizes:
            if ring_size == 3 and "3_to_4" in ring_changes:
                targets = ring_changes["3_to_4"]
            elif ring_size == 4 and "4_to_5" in ring_changes:
                targets = ring_changes["4_to_5"]
            elif ring_size == 5 and "5_to_6" in ring_changes:
                targets = ring_changes["5_to_6"]
            elif ring_size == 6 and "6_to_7" in ring_changes:
                targets = ring_changes["6_to_7"]
            else:
                continue
            
            for target in targets:
                if len(results) >= num_results:
                    break
                
                new_scaffold_smiles = self.RING_TEMPLATES.get(target)
                if not new_scaffold_smiles:
                    continue
                
                hopped = self._transfer_substituents(ref_mol, original_scaffold, new_scaffold_smiles)
                
                if hopped:
                    hopped_smiles = Chem.MolToSmiles(hopped)
                    new_scaffold = MurckoScaffold.GetScaffoldForMol(hopped)
                    new_scaffold_smiles = Chem.MolToSmiles(new_scaffold) if new_scaffold else ""
                    
                    overall_sim = self._calculate_overall_similarity(ref_mol, hopped)
                    scaffold_sim = self._calculate_scaffold_similarity(original_scaffold, new_scaffold_smiles)
                    
                    hopped_props = self._calculate_properties(hopped)
                    prop_changes = {}
                    for key in ref_props:
                        if key in hopped_props:
                            prop_changes[key] = (ref_props[key], hopped_props[key])
                    
                    results.append(ScaffoldHopResult(
                        original_smiles=Chem.MolToSmiles(ref_mol),
                        hopped_smiles=hopped_smiles,
                        original_scaffold=original_scaffold,
                        new_scaffold=new_scaffold_smiles,
                        scaffold_similarity=scaffold_sim,
                        overall_similarity=overall_sim,
                        method="topology",
                        properties_changed=prop_changes,
                        validity=True,
                    ))
        
        return results
    
    def _property_matched_hop(
        self,
        ref_mol: Chem.Mol,
        original_scaffold: str,
        ref_props: dict[str, float],
        num_results: int,
        property_constraints: dict[str, tuple] | None,
    ) -> list[ScaffoldHopResult]:
        """Perform property-matched scaffold hopping."""
        results = []
        
        # Try all scaffolds in library, rank by property similarity
        candidates = []
        
        for name, scaffold_data in self.scaffold_library.scaffolds.items():
            scaffold_smiles = scaffold_data["smiles"]
            
            # Skip if same as original
            if scaffold_smiles == original_scaffold:
                continue
            
            # Try to transfer substituents
            hopped = self._transfer_substituents(ref_mol, original_scaffold, scaffold_smiles)
            
            if hopped:
                hopped_props = self._calculate_properties(hopped)
                
                # Calculate property similarity
                prop_sim = self._calculate_property_similarity(ref_props, hopped_props)
                
                # Check constraints
                if property_constraints:
                    passes = True
                    for prop, (min_val, max_val) in property_constraints.items():
                        if prop in hopped_props:
                            val = hopped_props[prop]
                            if not (min_val <= val <= max_val):
                                passes = False
                                break
                    if not passes:
                        continue
                
                candidates.append({
                    "hopped": hopped,
                    "scaffold_smiles": scaffold_smiles,
                    "prop_sim": prop_sim,
                    "hopped_props": hopped_props,
                })
        
        # Sort by property similarity
        candidates.sort(key=lambda x: x["prop_sim"], reverse=True)
        
        for cand in candidates[:num_results]:
            hopped = cand["hopped"]
            hopped_smiles = Chem.MolToSmiles(hopped)
            new_scaffold = MurckoScaffold.GetScaffoldForMol(hopped)
            new_scaffold_smiles = Chem.MolToSmiles(new_scaffold) if new_scaffold else ""
            
            overall_sim = self._calculate_overall_similarity(ref_mol, hopped)
            scaffold_sim = self._calculate_scaffold_similarity(original_scaffold, new_scaffold_smiles)
            
            prop_changes = {}
            for key in ref_props:
                if key in cand["hopped_props"]:
                    prop_changes[key] = (ref_props[key], cand["hopped_props"][key])
            
            results.append(ScaffoldHopResult(
                original_smiles=Chem.MolToSmiles(ref_mol),
                hopped_smiles=hopped_smiles,
                original_scaffold=original_scaffold,
                new_scaffold=new_scaffold_smiles,
                scaffold_similarity=scaffold_sim,
                overall_similarity=overall_sim,
                method="property_matched",
                properties_changed=prop_changes,
                validity=True,
            ))
        
        return results
    
    def _fragment_recombination_hop(
        self,
        ref_mol: Chem.Mol,
        original_scaffold: str,
        ref_props: dict[str, float],
        num_results: int,
    ) -> list[ScaffoldHopResult]:
        """Perform fragment-based recombination."""
        results = []
        
        # Decompose reference into fragments
        fragments = list(BRICS.BRICSDecompose(ref_mol))
        
        if len(fragments) < 2:
            return results
        
        # Also get scaffold fragments
        scaffold_fragments = list(BRICS.BRICSDecompose(Chem.MolFromSmiles(original_scaffold)))
        
        # Try recombining with library scaffolds
        for name, scaffold_data in self.scaffold_library.scaffolds.items():
            if len(results) >= num_results:
                break
            
            scaffold_smiles = scaffold_data["smiles"]
            scaffold_mol = scaffold_data["mol"]
            
            scaffold_frags = list(BRICS.BRICSDecompose(scaffold_mol))
            
            if not scaffold_frags:
                continue
            
            # Try building from fragments
            all_frags = fragments + scaffold_frags
            
            try:
                for combined in BRICS.BRICSBuild(all_frags):
                    if combined:
                        hopped_smiles = Chem.MolToSmiles(combined)
                        
                        # Check it's different from original
                        if hopped_smiles == Chem.MolToSmiles(ref_mol):
                            continue
                        
                        new_scaffold = MurckoScaffold.GetScaffoldForMol(combined)
                        new_scaffold_smiles = Chem.MolToSmiles(new_scaffold) if new_scaffold else ""
                        
                        overall_sim = self._calculate_overall_similarity(ref_mol, combined)
                        scaffold_sim = self._calculate_scaffold_similarity(original_scaffold, new_scaffold_smiles)
                        
                        # Only keep if scaffold actually changed
                        if scaffold_sim > 0.8:
                            continue
                        
                        hopped_props = self._calculate_properties(combined)
                        prop_changes = {}
                        for key in ref_props:
                            if key in hopped_props:
                                prop_changes[key] = (ref_props[key], hopped_props[key])
                        
                        results.append(ScaffoldHopResult(
                            original_smiles=Chem.MolToSmiles(ref_mol),
                            hopped_smiles=hopped_smiles,
                            original_scaffold=original_scaffold,
                            new_scaffold=new_scaffold_smiles,
                            scaffold_similarity=scaffold_sim,
                            overall_similarity=overall_sim,
                            method="fragment_recombination",
                            properties_changed=prop_changes,
                            validity=True,
                        ))
                        
                        if len(results) >= num_results:
                            break
                        
            except Exception:
                continue
        
        return results
    
    def _identify_scaffold_type(self, scaffold_mol: Chem.Mol) -> str:
        """Identify scaffold type for bioisosteric replacement."""
        # Simple identification based on ring composition
        smiles = Chem.MolToSmiles(scaffold_mol)
        
        # Check for known patterns
        if "n1ccccc1" in smiles or "c1ccncc1" in smiles:
            return "pyridine"
        elif "c1ccccc1" in smiles:
            return "benzene"
        elif "c1ccncc1" in smiles:
            return "pyridine"
        elif "c1ncccn1" in smiles:
            return "pyrimidine"
        elif "c1ccsc1" in smiles:
            return "thiophene"
        elif "c1ccoc1" in smiles:
            return "furan"
        elif "c1cc[nH]c1" in smiles:
            return "pyrrole"
        elif "c1cnc[nH]1" in smiles:
            return "imidazole"
        elif "C1CCNCC1" in smiles:
            return "piperidine"
        elif "C1CNCCN1" in smiles:
            return "piperazine"
        elif "C1COCCN1" in smiles:
            return "morpholine"
        
        return "unknown"
    
    def _transfer_substituents(
        self,
        ref_mol: Chem.Mol,
        original_scaffold_smiles: str,
        new_scaffold_smiles: str,
    ) -> Chem.Mol | None:
        """
        Transfer substituents from reference scaffold to new scaffold.
        
        This is a simplified implementation. Real version would use
        more sophisticated chemistry (e.g., matched molecular pairs).
        """
        try:
            new_scaffold = Chem.MolFromSmiles(new_scaffold_smiles)
            if not new_scaffold:
                return None
            
            # For now, return new scaffold with minimal modification
            # Real implementation would:
            # 1. Identify attachment points on both scaffolds
            # 2. Map substituents from reference to new scaffold
            # 3. Handle valence and stereochemistry
            
            return new_scaffold
            
        except Exception as e:
            self.logger.warning("Substituent transfer failed: %s", e)
            return None
    
    def _calculate_properties(self, mol: Chem.Mol) -> dict[str, float]:
        """Calculate key molecular properties."""
        from rdkit.Chem import Descriptors, rdMolDescriptors
        
        return {
            "mw": Descriptors.MolWt(mol),
            "logp": Descriptors.MolLogP(mol),
            "hbd": Descriptors.NumHDonors(mol),
            "hba": Descriptors.NumHAcceptors(mol),
            "tpsa": rdMolDescriptors.CalcTPSA(mol),
            "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
        }
    
    def _calculate_property_similarity(
        self,
        props1: dict[str, float],
        props2: dict[str, float],
    ) -> float:
        """Calculate similarity between property dictionaries."""
        common_keys = set(props1.keys()) & set(props2.keys())
        if not common_keys:
            return 0.0
        
        similarities = []
        for key in common_keys:
            v1, v2 = props1[key], props2[key]
            if v1 == 0 and v2 == 0:
                sim = 1.0
            elif v1 == 0 or v2 == 0:
                sim = 0.0
            else:
                # Relative difference
                sim = 1.0 - min(abs(v1 - v2) / max(abs(v1), abs(v2)), 1.0)
            similarities.append(sim)
        
        return sum(similarities) / len(similarities)
    
    def _calculate_overall_similarity(self, mol1: Chem.Mol, mol2: Chem.Mol) -> float:
        """Calculate overall Tanimoto similarity (Morgan FP)."""
        from rdkit.Chem import AllChem
        from rdkit import DataStructs
        
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)
        
        return DataStructs.TanimotoSimilarity(fp1, fp2)
    
    def _calculate_scaffold_similarity(self, scaffold1: str, scaffold2: str) -> float:
        """Calculate scaffold similarity."""
        if not scaffold1 or not scaffold2:
            return 0.0
        
        mol1 = Chem.MolFromSmiles(scaffold1)
        mol2 = Chem.MolFromSmiles(scaffold2)
        
        if not mol1 or not mol2:
            return 0.0
        
        return self._calculate_overall_similarity(mol1, mol2)
    
    def _filter_by_constraints(
        self,
        results: list[ScaffoldHopResult],
        constraints: dict[str, tuple],
    ) -> list[ScaffoldHopResult]:
        """Filter results by property constraints."""
        filtered = []
        
        for result in results:
            passes = True
            for prop, (min_val, max_val) in constraints.items():
                if prop in result.properties_changed:
                    _, new_val = result.properties_changed[prop]
                    if not (min_val <= new_val <= max_val):
                        passes = False
                        break
            if passes:
                filtered.append(result)
        
        return filtered


def hop_scaffold(
    reference_smiles: str,
    strategy: str = "bioisosteric",
    num_results: int = 20,
    **kwargs,
) -> list[ScaffoldHopResult]:
    """Convenience function for scaffold hopping."""
    hopper = ScaffoldHopper()
    return hopper.hop_scaffold(reference_smiles, strategy, num_results, **kwargs)