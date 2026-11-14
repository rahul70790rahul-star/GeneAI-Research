"""Integration with existing VCF analyzer workflow."""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from geneai.mutation import summarize_vcf_interpretation_stream
from geneai.mutation_ml.preprocessing import FeatureEngineer, VariantPreprocessor, prepare_training_data
from geneai.mutation_ml.training import MutationMLTrainer, TrainingResult
from geneai.mutation_ml.explainability import MutationExplainer, ExplanationResult

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


@dataclass
class MLEnhancedVariant:
    """VCF variant enhanced with ML predictions."""
    chrom: str
    pos: int
    ref: str
    alt: str
    variant_type: str
    gene_symbol: str | None
    consequence: str | None
    impact: str | None

    # ML predictions
    pathogenicity_probability: float | None = None
    predicted_class: str | None = None
    confidence: str | None = None
    model_used: str | None = None

    # Explainability
    shap_summary: str | None = None
    top_positive_features: list[dict] | None = None
    top_negative_features: list[dict] | None = None

    # Source evidence
    clinvar_significance: str | None = None
    gnomad_af: float | None = None
    alphamissense_score: float | None = None
    cosmic_count: int = 0


class MutationMLIntegration:
    """Integrate ML predictions with VCF analysis workflow."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        preprocessor_path: Path | str | None = None,
    ):
        self.model_path = Path(model_path) if model_path else MODEL_DIR / "best_mutation_model.pkl"
        self.preprocessor_path = Path(preprocessor_path) if preprocessor_path else MODEL_DIR / "mutation_preprocessor.pkl"

        self.training_result: TrainingResult | None = None
        self.preprocessor: VariantPreprocessor | None = None
        self.explainer: MutationExplainer | None = None
        self._loaded = False

    def load_model(self) -> bool:
        """Load trained model and preprocessor."""
        try:
            if self.model_path.exists():
                with open(self.model_path, "rb") as f:
                    model_data = pickle.load(f)

                self.training_result = TrainingResult(
                    model_name=model_data["model_name"],
                    model_type=model_data["model_type"],
                    model=model_data["model"],
                    preprocessor=model_data.get("preprocessor"),
                    cv_scores=model_data["cv_scores"],
                    cv_scores_std=model_data.get("cv_scores_std", {}),
                    test_scores=model_data["test_scores"],
                    feature_importance=model_data.get("feature_importance"),
                    training_time=model_data["training_time"],
                    n_samples=model_data["n_samples"],
                    n_features=model_data["n_features"],
                    class_distribution=model_data["class_distribution"],
                    best_params=model_data.get("best_params"),
                    calibration_curve=model_data.get("calibration_curve"),
                )

                self.preprocessor = model_data.get("preprocessor") or self.training_result.preprocessor

                # Create explainer
                self.explainer = MutationExplainer(self.training_result)

                self._loaded = True
                logger.info("Loaded ML model: %s", self.training_result.model_name)
                return True

        except Exception as e:
            logger.error("Failed to load model: %s", e)

        return False

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded and self.training_result is not None

    def enhance_vcf_preview(
        self,
        preview: list[dict[str, Any]],
        top_k_explain: int = 5,
    ) -> list[MLEnhancedVariant]:
        """Add ML predictions to VCF preview variants."""
        if not self.is_loaded():
            raise ValueError("Model not loaded. Call load_model() first.")

        enhanced = []

        for variant in preview:
            # Prepare features for this variant
            features = self._variant_to_features(variant)

            if features is not None:
                # Predict
                pred = self.training_result.model.predict_proba(
                    self.preprocessor.transform(pd.DataFrame([features]))
                )[0, 1]
                pred_class = self.training_result.model.predict(
                    self.preprocessor.transform(pd.DataFrame([features]))
                )[0]

                # Explain
                explanation = self.explainer.explain(features, top_k=top_k_explain)

                enhanced_variant = MLEnhancedVariant(
                    chrom=variant.get("chrom", ""),
                    pos=variant.get("pos", 0),
                    ref=variant.get("ref", ""),
                    alt=variant.get("alt", ""),
                    variant_type=variant.get("variant_type", ""),
                    gene_symbol=variant.get("gene_info_source_field"),
                    consequence=variant.get("consequence_source_field"),
                    impact=None,  # Would need VEP
                    pathogenicity_probability=float(pred),
                    predicted_class="pathogenic" if pred_class == 1 else "benign",
                    confidence="high" if abs(pred - 0.5) > 0.3 else "medium" if abs(pred - 0.5) > 0.1 else "low",
                    model_used=self.training_result.model_name,
                    shap_summary=explanation.summary,
                    top_positive_features=explanation.top_positive,
                    top_negative_features=explanation.top_negative,
                    clinvar_significance=variant.get("clinvar_significance_source_field"),
                    gnomad_af=variant.get("source_af_info"),
                    alphamissense_score=None,
                    cosmic_count=0,
                )
            else:
                enhanced_variant = MLEnhancedVariant(
                    chrom=variant.get("chrom", ""),
                    pos=variant.get("pos", 0),
                    ref=variant.get("ref", ""),
                    alt=variant.get("alt", ""),
                    variant_type=variant.get("variant_type", ""),
                    gene_symbol=variant.get("gene_info_source_field"),
                    consequence=variant.get("consequence_source_field"),
                    impact=None,
                )

            enhanced.append(enhanced_variant)

        return enhanced

    def _variant_to_features(self, variant: dict[str, Any]) -> np.ndarray:
        """Convert VCF variant to ML features using preprocessor."""
        # Build feature dict with available data
        features = {
            "chrom": variant.get("chrom", ""),
            "pos": variant.get("pos", 0),
            "ref": variant.get("ref", ""),
            "alt": variant.get("alt", ""),
            "variant_type": variant.get("variant_type", ""),
            "qual": variant.get("qual"),
            "filter": variant.get("filter", ""),
            "consequence": variant.get("consequence_source_field"),
            "gene_symbol": variant.get("gene_info_source_field"),
            "clinvar_significance": variant.get("clinvar_significance_source_field"),
            "gnomad_af": variant.get("source_af_info"),
            "cohort_af": variant.get("cohort_af_from_genotypes"),
            "duplicate": variant.get("duplicate", False),
        }

        # Add default values for missing features
        defaults = {
            "gnomad_af_popmax": np.nan,
            "gnomad_ac": np.nan,
            "gnomad_an": np.nan,
            "thousand_genomes_af": np.nan,
            "cadd_raw": np.nan,
            "cadd_phred": np.nan,
            "revel_score": np.nan,
            "sift_score": np.nan,
            "polyphen_score": np.nan,
            "splice_ai": np.nan,
            "alphamissense_score": np.nan,
            "cosmic_count": 0,
            "clinvar_significance_simple": variant.get("clinvar_significance", "not_provided"),
            "clinvar_review_status": "no_criteria",
            "clinvar_submitters": 0,
            "clinvar_guidelines": False,
            "clinvar_significance_score": 0.0,
            "clinvar_review_status_score": 0.1,
            "impact": "MODIFIER",
            "exon_number": np.nan,
            "intron_number": np.nan,
            "protein_domain": "none",
            "domain_position": np.nan,
            "conservation_phastcons": np.nan,
            "conservation_phyloP": np.nan,
            "splice_distance": np.nan,
            "is_snv": True,
            "is_indel": False,
            "length_diff": 0,
            "ref_len": 1,
            "alt_len": 1,
        }

        for key, val in defaults.items():
            if key not in features:
                features[key] = val

    # Use preprocessor to transform
        if self.preprocessor is not None:
            import pandas as pd
            df = pd.DataFrame([features])
            X = self.preprocessor.transform(df)
            result = X
        else:
            # Fallback: return as array in feature order
            feature_names = self.training_result.preprocessor.feature_names if self.training_result.preprocessor else list(features.keys())
            result = np.array([[features.get(f, np.nan) for f in feature_names]])

        return result

    def predict_single(
        self,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        **extra_features,
    ):
        """Predict pathogenicity for a single variant."""
        if not self.is_loaded():
            raise ValueError("Model not loaded")

        variant = {
            "chrom": chrom,
            "pos": pos,
            "ref": ref,
            "alt": alt,
            **extra_features,
        }

        features = self._variant_to_features(variant)

        # Use model's predict_proba for probability
        import numpy as np
        prob = self.training_result.model.predict_proba(features)[0, 1]

        # Determine class and confidence
        if prob >= 0.9:
            predicted_class = "pathogenic"
            confidence = "high"
        elif prob >= 0.5:
            predicted_class = "likely_pathogenic"
            confidence = "medium"
        elif prob >= 0.1:
            predicted_class = "likely_benign"
            confidence = "medium"
        else:
            predicted_class = "benign"
            confidence = "high"

        return {
            "pathogenicity_probability": float(prob),
            "predicted_class": predicted_class,
            "confidence": confidence,
            "model_used": self.training_result.model_name,
        }

    def batch_predict(
        self,
        variants: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Predict for multiple variants."""
        if not self.is_loaded():
            raise ValueError("Model not loaded")

        results = []
        for variant in variants:
            try:
                pred = self.predict_single(
                    variant["chrom"],
                    variant["pos"],
                    variant["ref"],
                    variant["alt"],
                    **{k: v for k, v in variant.items() if k not in ["chrom", "pos", "ref", "alt"]},
                )
                results.append(pred)
            except Exception as e:
                logger.warning("Prediction failed for %s:%s: %s", variant.get("chrom"), variant.get("pos"), e)
                results.append({"error": str(e)})

        return results


def enhance_vcf_with_ml(
    vcf_file: Any,  # BinaryIO
    filename: str,
    integration: MutationMLIntegration | None = None,
    expected_build: str | None = None,
    preview_limit: int = 1000,
    ) -> tuple[dict[str, Any], list[MLEnhancedVariant]]:
    """Scan VCF and enhance with ML predictions."""
    # Scan VCF
    summary, metadata, preview = summarize_vcf_interpretation_stream(
    vcf_file,
    filename,
    expected_build=expected_build,
    preview_limit=preview_limit,
    )

    # Load integration if not provided
    if integration is None:
        integration = MutationMLIntegration()
        if not integration.load_model():
            logger.warning("No ML model loaded. Returning VCF preview without ML enhancement.")
            return summary, []

    # Enhance preview with ML
    enhanced = integration.enhance_vcf_preview(preview)

    return summary, enhanced


def create_training_dataset_from_vcf(
    vcf_files: list[tuple[Any, str]],  # List of (file, filename)
    labels: list[int],  # 1=pathogenic, 0=benign
    feature_engineer: FeatureEngineer | None = None,
    preprocessor: VariantPreprocessor | None = None,
    **external_data,
    ) -> tuple[np.ndarray, np.ndarray, VariantPreprocessor]:
    """Create training dataset from labeled VCF files."""
    all_variants = []
    all_labels = []

    for (vcf_file, filename), label in zip(vcf_files, labels):
        summary, metadata, preview = summarize_vcf_interpretation_stream(
        vcf_file,
        filename,
        preview_limit=10000,  # Larger preview for training
    )

    for variant in preview:
        all_variants.append(variant)
        all_labels.append(label)

    variants_df = pd.DataFrame(all_variants)
    labels_arr = np.array(all_labels)

    logger.info("Created training dataset: %d variants, %d positive", 
            len(variants_df), sum(labels_arr))

    # Engineer features
    if feature_engineer is None:
        feature_engineer = FeatureEngineer()

    features_df = feature_engineer.engineer_features(variants_df, **external_data)

    # Preprocess
    if preprocessor is None:
        preprocessor = VariantPreprocessor()

    X, y, preprocessor = prepare_training_data(features_df, labels_arr, preprocessor=preprocessor)

    return X, y, preprocessor


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Mutation ML Integration ready")