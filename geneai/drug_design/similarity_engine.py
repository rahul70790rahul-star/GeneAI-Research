"""Molecular similarity analysis module."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit.Chem import MACCSkeys
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem import rdFMCS

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Result of similarity comparison."""
    query_smiles: str
    target_smiles: str
    tanimoto_morgan: float = 0.0
    tanimoto_rdkit: float = 0.0
    tanimoto_maccs: float = 0.0
    dice_morgan: float = 0.0
    cosine_morgan: float = 0.0
    mcs_size: int = 0
    mcs_similarity: float = 0.0
    scaffold_similarity: float = 0.0
    pharmacophore_similarity: float = 0.0


@dataclass
class SimilaritySearchResult:
    """Result of similarity search."""
    query_smiles: str
    hits: list[SimilarityResult] = field(default_factory=list)
    total_searched: int = 0
    search_time_seconds: float = 0.0


class SimilarityEngine:
    """
    Molecular similarity analysis and search.
    
    Capabilities:
    - Multiple fingerprint types (Morgan, RDKit, MACCS)
    - Multiple similarity metrics (Tanimoto, Dice, Cosine)
    - Maximum Common Substructure (MCS) analysis
    - Scaffold similarity
    - Pharmacophore similarity
    - Fast similarity search with indexing
    - Scaffold hopping detection
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._fingerprint_cache: dict[str, Any] = {}
    
    def calculate_similarity(
        self,
        smiles1: str,
        smiles2: str,
        fp_types: list[str] | None = None,
        metrics: list[str] | None = None,
    ) -> SimilarityResult:
        """
        Calculate similarity between two molecules.
        
        Args:
            smiles1: Query SMILES
            smiles2: Target SMILES
            fp_types: Fingerprint types ("morgan", "rdkit", "maccs")
            metrics: Similarity metrics ("tanimoto", "dice", "cosine")
            
        Returns:
            SimilarityResult with all computed similarities
        """
        fp_types = fp_types or ["morgan", "rdkit", "maccs"]
        metrics = metrics or ["tanimoto", "dice", "cosine"]
        
        mol1 = Chem.MolFromSmiles(smiles1)
        mol2 = Chem.MolFromSmiles(smiles2)
        
        if not mol1 or not mol2:
            return SimilarityResult(query_smiles=smiles1, target_smiles=smiles2)
        
        result = SimilarityResult(query_smiles=smiles1, target_smiles=smiles2)
        
        # Compute fingerprints
        fps1 = self._get_fingerprints(mol1, fp_types)
        fps2 = self._get_fingerprints(mol2, fp_types)
        
        # Calculate similarities
        for fp_type in fp_types:
            if fp_type in fps1 and fp_type in fps2:
                fp1 = fps1[fp_type]
                fp2 = fps2[fp_type]
                
                if "tanimoto" in metrics:
                    sim = DataStructs.TanimotoSimilarity(fp1, fp2)
                    setattr(result, f"tanimoto_{fp_type}", sim)
                
                if "dice" in metrics:
                    sim = DataStructs.DiceSimilarity(fp1, fp2)
                    setattr(result, f"dice_{fp_type}", sim)
                
                if "cosine" in metrics:
                    sim = DataStructs.CosineSimilarity(fp1, fp2)
                    setattr(result, f"cosine_{fp_type}", sim)
        
        # MCS analysis
        try:
            mcs = rdFMCS.FindMCS([mol1, mol2], timeout=10)
            result.mcs_size = mcs.numAtoms
            # Normalize by smaller molecule
            min_atoms = min(mol1.GetNumAtoms(), mol2.GetNumAtoms())
            result.mcs_similarity = mcs.numAtoms / min_atoms if min_atoms > 0 else 0.0
        except Exception:
            pass
        
        # Scaffold similarity
        result.scaffold_similarity = self._calculate_scaffold_similarity(mol1, mol2)
        
        # Pharmacophore similarity (simplified)
        result.pharmacophore_similarity = self._calculate_pharmacophore_similarity(mol1, mol2)
        
        return result
    
    def _get_fingerprints(self, mol: Chem.Mol, fp_types: list[str]) -> dict[str, Any]:
        """Get fingerprints for a molecule."""
        fps = {}
        
        cache_key = Chem.MolToSmiles(mol)
        if cache_key in self._fingerprint_cache:
            cached = self._fingerprint_cache[cache_key]
            for fp_type in fp_types:
                if fp_type in cached:
                    fps[fp_type] = cached[fp_type]
        
        if "morgan" in fp_types and "morgan" not in fps:
            fps["morgan"] = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        
        if "rdkit" in fp_types and "rdkit" not in fps:
            fps["rdkit"] = Chem.RDKFingerprint(mol)
        
        if "maccs" in fp_types and "maccs" not in fps:
            fps["maccs"] = MACCSkeys.GenMACCSKeys(mol)
        
        # Update cache
        if cache_key not in self._fingerprint_cache:
            self._fingerprint_cache[cache_key] = {}
        for fp_type, fp in fps.items():
            self._fingerprint_cache[cache_key][fp_type] = fp
        
        return fps
    
    def _calculate_scaffold_similarity(self, mol1: Chem.Mol, mol2: Chem.Mol) -> float:
        """Calculate scaffold similarity using Murcko scaffolds."""
        try:
            from rdkit.Chem.Scaffolds import MurckoScaffold
            
            scaffold1 = MurckoScaffold.GetScaffoldForMol(mol1)
            scaffold2 = MurckoScaffold.GetScaffoldForMol(mol2)
            
            if not scaffold1 or not scaffold2:
                return 0.0
            
            # Compare scaffold fingerprints
            fp1 = AllChem.GetMorganFingerprintAsBitVect(scaffold1, 2, nBits=2048)
            fp2 = AllChem.GetMorganFingerprintAsBitVect(scaffold2, 2, nBits=2048)
            
            return DataStructs.TanimotoSimilarity(fp1, fp2)
        except Exception:
            return 0.0
    
    def _calculate_pharmacophore_similarity(self, mol1: Chem.Mol, mol2: Chem.Mol) -> float:
        """Calculate pharmacophore similarity (simplified)."""
        try:
            # Generate pharmacophore features
            from rdkit.Chem import ChemicalFeatures
            from rdkit import RDConfig
            import os
            
            fdef_file = os.path.join(RDConfig.RDDataDir, 'BaseFeatures.fdef')
            factory = ChemicalFeatures.BuildFeatureFactory(fdef_file)
            
            feats1 = factory.GetFeaturesForMol(mol1)
            feats2 = factory.GetFeaturesForMol(mol2)
            
            if not feats1 or not feats2:
                return 0.0
            
            # Count feature types
            type_counts1 = {}
            type_counts2 = {}
            
            for feat in feats1:
                type_counts1[feat.GetFamily()] = type_counts1.get(feat.GetFamily(), 0) + 1
            
            for feat in feats2:
                type_counts2[feat.GetFamily()] = type_counts2.get(feat.GetFamily(), 0) + 1
            
            # Compare feature type distributions
            all_types = set(type_counts1.keys()) | set(type_counts2.keys())
            
            total_diff = 0
            total_count = 0
            for ftype in all_types:
                c1 = type_counts1.get(ftype, 0)
                c2 = type_counts2.get(ftype, 0)
                total_diff += abs(c1 - c2)
                total_count += c1 + c2
            
            if total_count == 0:
                return 0.0
            
            return 1.0 - (total_diff / total_count)
            
        except Exception:
            return 0.0
    
    def search_similar(
        self,
        query_smiles: str,
        library_smiles: list[str],
        threshold: float = 0.7,
        fp_type: str = "morgan",
        metric: str = "tanimoto",
        max_results: int = 100,
    ) -> SimilaritySearchResult:
        """
        Search for similar molecules in a library.
        
        Args:
            query_smiles: Query SMILES
            library_smiles: List of library SMILES
            threshold: Minimum similarity threshold
            fp_type: Fingerprint type
            metric: Similarity metric
            max_results: Maximum results to return
            
        Returns:
            SimilaritySearchResult with hits above threshold
        """
        import time
        start_time = time.time()
        
        query_mol = Chem.MolFromSmiles(query_smiles)
        if not query_mol:
            return SimilaritySearchResult(query_smiles=query_smiles)
        
        query_fp = self._get_fingerprints(query_mol, [fp_type])[fp_type]
        
        hits = []
        
        for i, target_smiles in enumerate(library_smiles):
            target_mol = Chem.MolFromSmiles(target_smiles)
            if not target_mol:
                continue
            
            target_fp = self._get_fingerprints(target_mol, [fp_type])[fp_type]
            
            if metric == "tanimoto":
                sim = DataStructs.TanimotoSimilarity(query_fp, target_fp)
            elif metric == "dice":
                sim = DataStructs.DiceSimilarity(query_fp, target_fp)
            elif metric == "cosine":
                sim = DataStructs.CosineSimilarity(query_fp, target_fp)
            else:
                sim = DataStructs.TanimotoSimilarity(query_fp, target_fp)
            
            if sim >= threshold:
                # Full similarity calculation for hits
                full_result = self.calculate_similarity(query_smiles, target_smiles)
                hits.append(full_result)
        
        # Sort by primary similarity
        primary_attr = f"tanimoto_{fp_type}"
        hits.sort(key=lambda x: getattr(x, primary_attr, 0), reverse=True)
        
        hits = hits[:max_results]
        
        return SimilaritySearchResult(
            query_smiles=query_smiles,
            hits=hits,
            total_searched=len(library_smiles),
            search_time_seconds=time.time() - start_time,
        )
    
    def find_scaffold_hops(
        self,
        query_smiles: str,
        library_smiles: list[str],
        min_similarity: float = 0.5,
        max_scaffold_similarity: float = 0.4,
        max_results: int = 50,
    ) -> list[SimilarityResult]:
        """
        Find scaffold hops - molecules with similar activity but different scaffolds.
        
        Args:
            query_smiles: Query SMILES
            library_smiles: Library to search
            min_similarity: Minimum overall similarity
            max_scaffold_similarity: Maximum scaffold similarity (to ensure different scaffold)
            max_results: Maximum results
            
        Returns:
            List of scaffold hop candidates
        """
        results = self.search_similar(
            query_smiles,
            library_smiles,
            threshold=min_similarity,
            max_results=max_results * 3,  # Get more for filtering
        )
        
        # Filter for scaffold hops
        hops = [
            hit for hit in results.hits
            if hit.scaffold_similarity <= max_scaffold_similarity
        ]
        
        return hops[:max_results]
    
    def cluster_by_similarity(
        self,
        smiles_list: list[str],
        threshold: float = 0.7,
        fp_type: str = "morgan",
    ) -> list[list[str]]:
        """
        Cluster molecules by similarity (using Butina clustering).
        
        Args:
            smiles_list: List of SMILES
            threshold: Clustering threshold
            fp_type: Fingerprint type
            
        Returns:
            List of clusters (each cluster is a list of SMILES)
        """
        from rdkit.ML.Cluster import Butina
        
        # Calculate fingerprints
        fps = []
        valid_smiles = []
        
        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                fp = self._get_fingerprints(mol, [fp_type])[fp_type]
                fps.append(fp)
                valid_smiles.append(smi)
        
        if not fps:
            return []
        
        # Calculate distance matrix
        n = len(fps)
        dists = []
        for i in range(1, n):
            for j in range(i):
                sim = DataStructs.TanimotoSimilarity(fps[i], fps[j])
                dists.append(1.0 - sim)
        
        # Cluster
        clusters = Butina.ClusterData(dists, n, threshold, isDistData=True)
        
        # Convert to SMILES lists
        result_clusters = []
        for cluster in clusters:
            cluster_smiles = [valid_smiles[idx] for idx in cluster]
            result_clusters.append(cluster_smiles)
        
        return result_clusters
    
    def calculate_diversity(
        self,
        smiles_list: list[str],
        fp_type: str = "morgan",
    ) -> dict[str, float]:
        """
        Calculate diversity metrics for a set of molecules.
        
        Returns:
            Dict with diversity metrics
        """
        if len(smiles_list) < 2:
            return {"mean_pairwise_similarity": 1.0, "diversity": 0.0}
        
        fps = []
        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                fp = self._get_fingerprints(mol, [fp_type])[fp_type]
                fps.append(fp)
        
        if len(fps) < 2:
            return {"mean_pairwise_similarity": 1.0, "diversity": 0.0}
        
        # Pairwise similarities
        similarities = []
        n = len(fps)
        for i in range(n):
            for j in range(i + 1, n):
                sim = DataStructs.TanimotoSimilarity(fps[i], fps[j])
                similarities.append(sim)
        
        mean_sim = sum(similarities) / len(similarities)
        
        return {
            "mean_pairwise_similarity": mean_sim,
            "diversity": 1.0 - mean_sim,
            "min_similarity": min(similarities),
            "max_similarity": max(similarities),
            "num_pairs": len(similarities),
        }


def calculate_similarity(
    smiles1: str,
    smiles2: str,
    **kwargs,
) -> SimilarityResult:
    """Convenience function for similarity calculation."""
    engine = SimilarityEngine()
    return engine.calculate_similarity(smiles1, smiles2, **kwargs)


def search_similar(
    query_smiles: str,
    library_smiles: list[str],
    **kwargs,
) -> SimilaritySearchResult:
    """Convenience function for similarity search."""
    engine = SimilarityEngine()
    return engine.search_similar(query_smiles, library_smiles, **kwargs)


class FingerprintType(str, Enum):
    """Supported molecular fingerprint types."""

    MORGAN = "morgan"
    RDKIT = "rdkit"
    MACCS = "maccs"


class SimilarityMetric(str, Enum):
    """Supported similarity metrics."""

    TANIMOTO = "tanimoto"
    DICE = "dice"
    COSINE = "cosine"


def search_library(
    query_smiles: str,
    library_smiles: list[str],
    threshold: float = 0.7,
    fp_type: str = "morgan",
    metric: str = "tanimoto",
    max_results: int = 100,
) -> SimilaritySearchResult:
    """Search a SMILES library for molecules similar to ``query_smiles``."""
    engine = SimilarityEngine()
    return engine.search_similar(
        query_smiles,
        library_smiles,
        threshold=threshold,
        fp_type=str(fp_type),
        metric=str(metric),
        max_results=max_results,
    )


def cluster_molecules_butina(
    smiles_list: list[str],
    threshold: float = 0.7,
    fp_type: str = "morgan",
) -> list[list[str]]:
    """Cluster molecules with the Butina algorithm."""
    return SimilarityEngine().cluster_by_similarity(
        smiles_list, threshold=threshold, fp_type=str(fp_type)
    )


def cluster_molecules_kmeans(
    smiles_list: list[str],
    n_clusters: int = 5,
    fp_type: str = "morgan",
    random_state: int = 42,
) -> list[list[str]]:
    """Cluster molecules with k-means over bit-vector fingerprints."""
    import numpy as np

    engine = SimilarityEngine()
    valid: list[str] = []
    rows = []
    for smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if not mol:
            continue
        fp = engine._get_fingerprints(mol, [str(fp_type)])[str(fp_type)]
        arr = np.zeros((1, fp.GetNumBits()), dtype=np.uint8)
        DataStructs.ConvertToNumpyArray(fp, arr[0])
        rows.append(arr[0])
        valid.append(smi)

    if not rows:
        return []

    k = max(1, min(int(n_clusters), len(rows)))
    if k == 1:
        return [valid]

    try:
        from sklearn.cluster import KMeans

        labels = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit_predict(
            np.array(rows)
        )
    except Exception:  # pragma: no cover - optional dependency fallback
        logger.warning("k-means clustering unavailable; falling back to Butina", exc_info=True)
        return engine.cluster_by_similarity(valid, fp_type=str(fp_type))

    clusters: dict[int, list[str]] = {}
    for smi, label in zip(valid, labels):
        clusters.setdefault(int(label), []).append(smi)
    return list(clusters.values())


def calculate_diversity_metrics(
    smiles_list: list[str],
    fp_type: str = "morgan",
) -> dict[str, float]:
    """Calculate mean pairwise similarity and diversity for a molecule set."""
    return SimilarityEngine().calculate_diversity(smiles_list, fp_type=str(fp_type))
