"""Drug-target interaction prediction engine integrating with existing GeneAI modules."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import chembl_client
from geneai.drug_discovery import pubchem_client
from geneai.drug_target_prediction.ml_models import (
    DrugTargetPredictor,
    train_chembl_model,
    create_sample_training_data,
)
from geneai.drug_target_prediction.molecular_descriptors import (
    calculate_molecular_descriptors,
    calculate_morgan_fingerprint,
    is_rdkit_available,
)

logger = logging.getLogger(__name__)


class DrugTargetPredictionEngine:
    """Main engine for drug-target interaction prediction."""
    
    def __init__(
        self,
        model_type: str = "random_forest",
        use_fingerprints: bool = True,
        fp_type: str = "morgan",
        auto_train: bool = True,
    ):
        """Initialize the prediction engine.
        
        Args:
            model_type: ML model type
            use_fingerprints: Whether to use molecular fingerprints
            fp_type: Fingerprint type
            auto_train: Whether to auto-train on sample data if no model exists
        """
        self.predictor = DrugTargetPredictor(
            model_type=model_type,
            use_fingerprints=use_fingerprints,
            fp_type=fp_type,
        )
        self.auto_train = auto_train
        self._chembl_cache = {}
        self._target_cache = {}
        
        if auto_train and not self.predictor.is_fitted:
            self._train_default_model()
    
    def _train_default_model(self) -> None:
        """Train a default model on sample data."""
        try:
            smiles, labels = create_sample_training_data()
            self.predictor.train(smiles, labels, validate=False)
            logger.info("Default model trained on sample data")
        except Exception as e:
            logger.warning("Failed to train default model: %s", e)
    
    def train_from_chembl(
        self,
        target_chembl_id: str,
        activity_threshold: float = 1000.0,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Train model using ChEMBL bioactivity data for a specific target.
        
        Args:
            target_chembl_id: ChEMBL target ID (e.g., CHEMBL2095)
            activity_threshold: Activity threshold in nM
            limit: Maximum number of activities to fetch
            
        Returns:
            Training results
        """
        try:
            # Fetch bioactivities from ChEMBL
            activities = chembl_client.get_target_bioactivities(
                target_chembl_id, 
                limit=limit
            )
            
            if not activities:
                raise ValueError(f"No bioactivity data found for target {target_chembl_id}")
            
            # Train model
            self.predictor = train_chembl_model(activities, activity_threshold)
            
            return {
                "target_chembl_id": target_chembl_id,
                "n_activities": len(activities),
                "activity_threshold_nm": activity_threshold,
                "training_results": self.predictor.training_history,
            }
            
        except Exception as e:
            logger.error("ChEMBL training failed for %s: %s", target_chembl_id, e)
            raise
    
    def train_from_local_database(
        self,
        min_activities: int = 50,
    ) -> dict[str, Any]:
        """Train model using data from local drug database.
        
        Args:
            min_activities: Minimum number of activities required
            
        Returns:
            Training results
        """
        conn = db.get_connection()
        try:
            # Get drug-target interactions with activity data
            query = """
                SELECT d.canonical_smiles, dti.action_type, dti.binding_affinity_nm
                FROM drugs d
                JOIN drug_target_interactions dti ON d.id = dti.drug_id
                WHERE d.canonical_smiles IS NOT NULL
                AND dti.binding_affinity_nm IS NOT NULL
            """
            df = pd.read_sql_query(query, conn)
            
            if len(df) < min_activities:
                raise ValueError(f"Insufficient data: {len(df)} interactions, need {min_activities}")
            
            # Convert binding affinity to binary labels
            # Active if affinity <= 1000 nM (1 uM)
            smiles = df["canonical_smiles"].tolist()
            labels = (df["binding_affinity_nm"] <= 1000).astype(int).tolist()
            
            # Train
            self.predictor.train(smiles, labels)
            
            return {
                "n_samples": len(df),
                "n_active": int(sum(labels)),
                "n_inactive": int(len(labels) - sum(labels)),
                "training_results": self.predictor.training_history,
            }
            
        finally:
            conn.close()
    
    def predict_drug_target(
        self,
        drug_identifier: str,
        target_identifier: str,
        identifier_type: str = "auto",
    ) -> dict[str, Any]:
        """Predict interaction between a drug and target.
        
        Args:
            drug_identifier: Drug identifier (name, CID, ChEMBL ID, SMILES)
            target_identifier: Target identifier (gene symbol, UniProt ID, ChEMBL ID)
            identifier_type: Type of identifiers
            
        Returns:
            Prediction result with probability and details
        """
        # Resolve drug to SMILES
        drug_smiles = self._resolve_drug_to_smiles(drug_identifier, identifier_type)
        if not drug_smiles:
            return {
                "success": False,
                "error": f"Could not resolve drug: {drug_identifier}",
                "drug_identifier": drug_identifier,
                "target_identifier": target_identifier,
            }
        
        # Get target features
        target_features = self._get_target_features(target_identifier)
        
        # Predict
        try:
            prediction = self.predictor.predict_single(drug_smiles, target_features)
            prediction.update({
                "success": True,
                "drug_identifier": drug_identifier,
                "target_identifier": target_identifier,
                "drug_smiles": drug_smiles,
            })
            return prediction
        except Exception as e:
            logger.error("Prediction failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "drug_identifier": drug_identifier,
                "target_identifier": target_identifier,
            }
    
    def predict_drug_target_batch(
        self,
        drug_identifiers: list[str],
        target_identifier: str,
        identifier_type: str = "auto",
    ) -> list[dict[str, Any]]:
        """Predict interactions for multiple drugs against a single target.
        
        Args:
            drug_identifiers: List of drug identifiers
            target_identifier: Target identifier
            identifier_type: Type of drug identifiers
            
        Returns:
            List of prediction results
        """
        target_features = self._get_target_features(target_identifier)
        results = []
        
        for drug_id in drug_identifiers:
            drug_smiles = self._resolve_drug_to_smiles(drug_id, identifier_type)
            if drug_smiles:
                pred = self.predictor.predict_single(drug_smiles, target_features)
                pred.update({
                    "drug_identifier": drug_id,
                    "target_identifier": target_identifier,
                    "drug_smiles": drug_smiles,
                    "success": True,
                })
            else:
                pred = {
                    "drug_identifier": drug_id,
                    "target_identifier": target_identifier,
                    "success": False,
                    "error": "Could not resolve drug to SMILES",
                }
            results.append(pred)
        
        return results
    
    def predict_target_profile(
        self,
        drug_identifier: str,
        target_list: list[str],
        identifier_type: str = "auto",
    ) -> list[dict[str, Any]]:
        """Predict interaction profile of a drug against multiple targets.
        
        Args:
            drug_identifier: Drug identifier
            target_list: List of target identifiers
            identifier_type: Type of drug identifier
            
        Returns:
            List of predictions for each target
        """
        drug_smiles = self._resolve_drug_to_smiles(drug_identifier, identifier_type)
        if not drug_smiles:
            return [{
                "success": False,
                "error": f"Could not resolve drug: {drug_identifier}",
                "drug_identifier": drug_identifier,
            }]
        
        results = []
        for target_id in target_list:
            target_features = self._get_target_features(target_id)
            try:
                pred = self.predictor.predict_single(drug_smiles, target_features)
                pred.update({
                    "drug_identifier": drug_identifier,
                    "target_identifier": target_id,
                    "drug_smiles": drug_smiles,
                    "success": True,
                })
            except Exception as e:
                pred = {
                    "drug_identifier": drug_identifier,
                    "target_identifier": target_id,
                    "success": False,
                    "error": str(e),
                }
            results.append(pred)
        
        # Sort by interaction probability (descending)
        results.sort(key=lambda x: x.get("interaction_probability", 0), reverse=True)
        return results
    
    def _resolve_drug_to_smiles(
        self,
        identifier: str,
        identifier_type: str = "auto",
    ) -> str | None:
        """Resolve various drug identifiers to SMILES."""
        identifier = identifier.strip()
        if not identifier:
            return None
        
        # Check cache
        cache_key = f"{identifier_type}:{identifier}"
        if cache_key in self._chembl_cache:
            return self._chembl_cache[cache_key]
        
        smiles = None
        
        # Auto-detect identifier type
        if identifier_type == "auto":
            if identifier.startswith("CHEMBL"):
                identifier_type = "chembl_id"
            elif identifier.isdigit():
                identifier_type = "cid"
            elif "-" in identifier and len(identifier) >= 20:
                identifier_type = "inchikey"
            elif all(c in "CNOSPFClBrIcnospfclbri()[]=#+-" for c in identifier):
                identifier_type = "smiles"
            else:
                identifier_type = "name"
        
        try:
            if identifier_type == "smiles":
                smiles = identifier
            elif identifier_type == "cid":
                result = pubchem_client.get_compound_by_cid(identifier)
                smiles = result.get("canonical_smiles") if result else None
            elif identifier_type == "inchikey":
                result = pubchem_client.get_compound_by_inchikey(identifier)
                smiles = result.get("canonical_smiles") if result else None
            elif identifier_type == "chembl_id":
                result = chembl_client.get_molecule_by_chembl_id(identifier)
                smiles = result.get("canonical_smiles") if result else None
            elif identifier_type == "name":
                results = pubchem_client.get_compound_by_name(identifier)
                smiles = results[0].get("canonical_smiles") if results else None
                if not smiles:
                    results = chembl_client.search_molecules_by_name(identifier, limit=1)
                    smiles = results[0].get("canonical_smiles") if results else None
        except Exception as e:
            logger.warning("Failed to resolve %s (%s): %s", identifier, identifier_type, e)
        
        if smiles:
            self._chembl_cache[cache_key] = smiles
        
        return smiles
    
    def _get_target_features(self, target_identifier: str) -> dict[str, float] | None:
        """Get feature vector for a target protein."""
        if target_identifier in self._target_cache:
            return self._target_cache[target_identifier]
        
        features = {}
        
        try:
            # Try to get target info from ChEMBL
            if target_identifier.startswith("CHEMBL"):
                target = chembl_client.get_target_by_chembl_id(target_identifier)
                if target:
                    features["target_chembl_id"] = 1.0
                    features["target_type_protein"] = 1.0 if target.get("target_type") == "SINGLE PROTEIN" else 0.0
                    # Organism as numeric feature
                    organism = target.get("organism", "").lower()
                    features["target_organism_human"] = 1.0 if "homo sapiens" in organism or "human" in organism else 0.0
        except Exception:
            pass
        
        # Add generic target features
        features["target_id_hash"] = hash(target_identifier) % 10000 / 10000.0
        
        self._target_cache[target_identifier] = features if features else None
        return self._target_cache[target_identifier]
    
    def get_model_info(self) -> dict[str, Any]:
        """Get information about the current model."""
        return {
            "model_type": self.predictor.model_type,
            "is_fitted": self.predictor.is_fitted,
            "use_fingerprints": self.predictor.use_fingerprints,
            "fp_type": self.predictor.fp_type,
            "n_fp_bits": self.predictor.n_fp_bits,
            "feature_count": len(self.predictor.feature_names) if self.predictor.feature_names else 0,
            "training_history": self.predictor.training_history,
        }
    
    def save_model(self, path: str) -> None:
        """Save the trained model."""
        self.predictor.save_model(path)
    
    def load_model(self, path: str) -> None:
        """Load a trained model."""
        self.predictor = DrugTargetPredictor.load_model(path)


def create_engine(
    model_type: str = "random_forest",
    use_fingerprints: bool = True,
    fp_type: str = "morgan",
) -> DrugTargetPredictionEngine:
    """Factory function to create prediction engine."""
    return DrugTargetPredictionEngine(
        model_type=model_type,
        use_fingerprints=use_fingerprints,
        fp_type=fp_type,
    )


def predict_drug_target_interactions(
    drug_smiles: str,
    target_sequence: str,
    model_type: str = "ensemble",
) -> dict[str, Any]:
    """Convenience function to predict drug-target interactions."""
    engine = create_engine()
    return engine.predict_drug_target(drug_smiles, target_sequence, model_type)