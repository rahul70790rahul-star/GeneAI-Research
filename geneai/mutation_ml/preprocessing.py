"""Preprocessing and feature engineering for mutation ML pipeline."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    StandardScaler,
    OneHotEncoder,
    OrdinalEncoder,
    LabelEncoder,
    RobustScaler,
)

logger = logging.getLogger(__name__)


# Consequence severity mapping (from variant_prioritizer.py)
CONSEQUENCE_SEVERITY = {
    "transcript_ablation": 1.0,
    "splice_acceptor_variant": 0.95,
    "splice_donor_variant": 0.95,
    "stop_gained": 0.95,
    "frameshift_variant": 0.9,
    "stop_lost": 0.85,
    "start_lost": 0.8,
    "transcript_amplification": 0.7,
    "inframe_insertion": 0.6,
    "inframe_deletion": 0.6,
    "missense_variant": 0.5,
    "protein_altering_variant": 0.5,
    "splice_region_variant": 0.4,
    "incomplete_terminal_codon_variant": 0.3,
    "start_retained_variant": 0.2,
    "stop_retained_variant": 0.2,
    "synonymous_variant": 0.1,
    "coding_sequence_variant": 0.1,
    "mature_miRNA_variant": 0.1,
    "5_prime_UTR_variant": 0.05,
    "3_prime_UTR_variant": 0.05,
    "non_coding_transcript_exon_variant": 0.05,
    "intron_variant": 0.01,
    "NMD_transcript_variant": 0.01,
    "non_coding_transcript_variant": 0.01,
    "upstream_gene_variant": 0.005,
    "downstream_gene_variant": 0.005,
    "TF_binding_site_variant": 0.005,
    "regulatory_region_variant": 0.005,
    "intergenic_variant": 0.001,
}

# ClinVar significance mapping
CLINVAR_SIGNIFICANCE_MAP = {
    "pathogenic": 1.0,
    "likely_pathogenic": 0.8,
    "pathogenic/likely_pathogenic": 0.9,
    "uncertain_significance": 0.5,
    "conflicting_interpretations": 0.4,
    "likely_benign": 0.2,
    "benign": 0.1,
    "benign/likely_benign": 0.15,
    "not_provided": 0.0,
    "drug_response": 0.0,
    "risk_factor": 0.3,
    "association": 0.3,
    "protective": 0.0,
}

# Impact severity
IMPACT_SEVERITY = {
    "HIGH": 1.0,
    "MODERATE": 0.6,
    "LOW": 0.2,
    "MODIFIER": 0.1,
}

# Variant type encoding
VARIANT_TYPE_MAP = {
    "SNP": 0,
    "INDEL": 1,
    "STRUCTURAL": 2,
    "COMPLEX": 3,
    "SYMBOLIC": 4,
}


@dataclass
class FeatureConfig:
    """Configuration for feature engineering."""
    use_gnomad: bool = True
    use_clinvar: bool = True
    use_ensembl: bool = True
    use_alphamissense: bool = True
    use_cosmic: bool = True
    use_uniprot: bool = True
    max_missing_ratio: float = 0.5
    scale_method: str = "robust"  # "standard", "robust", "none"
    encode_categorical: str = "onehot"  # "onehot", "ordinal", "label"


class VariantPreprocessor:
    """Preprocess variant annotations for ML training."""

    def __init__(self, config: FeatureConfig | None = None):
        self.config = config or FeatureConfig()
        self.scaler = None
        self.encoder = None
        self.feature_names: list[str] = []
        self.categorical_features: list[str] = []
        self.numerical_features: list[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "VariantPreprocessor":
        """Fit preprocessor on training data."""
        logger.info("Fitting VariantPreprocessor on %d samples", len(df))

        # Identify feature columns
        self._identify_features(df)

        # Build preprocessing pipeline
        self._build_pipeline()

        # Fit
        X = self._prepare_features(df)
        self.pipeline.fit(X)
        self._fitted = True

        # Get feature names after transformation
        self.feature_names = self._get_output_feature_names()
        logger.info("Fitted preprocessor with %d output features", len(self.feature_names))
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """Transform data using fitted preprocessor."""
        if not self._fitted:
            raise ValueError("Preprocessor must be fitted before transform")

        X = self._prepare_features(df)
        return self.pipeline.transform(X)

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """Fit and transform."""
        return self.fit(df).transform(df)

    def _identify_features(self, df: pd.DataFrame) -> None:
        """Identify categorical and numerical features."""
        # Define expected feature columns
        expected_numerical = [
            "gnomad_af", "gnomad_af_popmax", "gnomad_ac", "gnomad_an",
            "thousand_genomes_af", "cadd_raw", "cadd_phred", "revel_score",
            "sift_score", "polyphen_score", "splice_ai", "alphamissense_score",
            "cosmic_count", "cosmic_tumor_types",
            "consequence_severity", "impact_severity",
            "clinvar_significance_score", "clinvar_review_status_score",
            "protein_domain_count", "disorder_score",
            "conservation_phylop", "conservation_phastcons",
            "distance_to_splice_site", "exon_number", "intron_number",
        ]

        expected_categorical = [
            "variant_type", "consequence", "impact", "clinvar_significance",
            "clinvar_review_status", "sift_prediction", "polyphen_prediction",
            "gene_biotype", "strand", "chromosome",
        ]

        # Only keep columns that exist in data
        self.numerical_features = [c for c in expected_numerical if c in df.columns]
        self.categorical_features = [c for c in expected_categorical if c in df.columns]

        logger.info("Numerical features: %d, Categorical features: %d",
                    len(self.numerical_features), len(self.categorical_features))

    def _build_pipeline(self) -> None:
        """Build sklearn preprocessing pipeline."""
        transformers = []

        if self.numerical_features:
            if self.config.scale_method == "standard":
                num_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                ])
            elif self.config.scale_method == "robust":
                num_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", RobustScaler()),
                ])
            else:
                num_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                ])
            transformers.append(("num", num_pipeline, self.numerical_features))

        if self.categorical_features:
            if self.config.encode_categorical == "onehot":
                cat_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                    ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                ])
            elif self.config.encode_categorical == "ordinal":
                cat_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                    ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
                ])
            else:
                cat_pipeline = Pipeline([
                    ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                    ("encoder", LabelEncoder()),
                ])
            transformers.append(("cat", cat_pipeline, self.categorical_features))

        self.pipeline = ColumnTransformer(
            transformers=transformers,
            remainder="drop",
            sparse_threshold=0.3,
        )

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare feature matrix from variant dataframe."""
        df = df.copy()

        # Ensure required columns exist
        for col in self.numerical_features + self.categorical_features:
            if col not in df.columns:
                df[col] = np.nan

        return df[self.numerical_features + self.categorical_features]

    def _get_output_feature_names(self) -> list[str]:
        """Get feature names after transformation."""
        if not self._fitted:
            return []

        names = []
        for name, trans, cols in self.pipeline.transformers_:
            if name == "num":
                names.extend(cols)
            elif name == "cat":
                if hasattr(trans.named_steps["encoder"], "get_feature_names_out"):
                    names.extend(trans.named_steps["encoder"].get_feature_names_out(cols))
                else:
                    names.extend(cols)
        return names


class FeatureEngineer:
    """Engineer features from raw variant annotations."""

    def __init__(self, config: FeatureConfig | None = None):
        self.config = config or FeatureConfig()

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to expected conventions."""
        df = df.copy()
        # Map ClinVar column names to expected names
        column_map = {
            "Chromosome": "chrom",
            "Start": "pos",
            "ReferenceAllele": "ref",
            "AlternateAllele": "alt",
            "GeneSymbol": "gene_symbol",
            "GeneID": "gene_id",
            "ClinicalSignificance": "clinical_significance",
            "ClinSigSimple": "clin_sig_simple",
            "ReviewStatus": "review_status",
            "NumberSubmitters": "num_submitters",
            "MolecularConsequence": "consequence",
            "ProteinChange": "protein_change",
        }
        for old, new in column_map.items():
            if old in df.columns and new not in df.columns:
                df[new] = df[old]
        return df

    def engineer_features(
        self,
        variants: pd.DataFrame,
        clinvar_df: pd.DataFrame | None = None,
        gnomad_df: pd.DataFrame | None = None,
        ensembl_df: pd.DataFrame | None = None,
        alphamissense_df: pd.DataFrame | None = None,
        cosmic_df: pd.DataFrame | None = None,
        uniprot_domains: dict[str, list[dict]] | None = None,
    ) -> pd.DataFrame:
        """Engineer all features for variant dataset."""
        logger.info("Engineering features for %d variants", len(variants))
        df = variants.copy()
        df = self._normalize_columns(df)

        # Basic variant features
        df = self._add_variant_features(df)

        # Consequence severity
        df = self._add_consequence_features(df)

        # Population frequencies
        if self.config.use_gnomad and gnomad_df is not None:
            df = self._add_gnomad_features(df, gnomad_df)

        # ClinVar annotations
        if self.config.use_clinvar and clinvar_df is not None:
            df = self._add_clinvar_features(df, clinvar_df)

        # Ensembl/VEP annotations
        if self.config.use_ensembl and ensembl_df is not None:
            df = self._add_ensembl_features(df, ensembl_df)

        # AlphaMissense
        if self.config.use_alphamissense and alphamissense_df is not None:
            df = self._add_alphamissense_features(df, alphamissense_df)

        # COSMIC
        if self.config.use_cosmic and cosmic_df is not None:
            df = self._add_cosmic_features(df, cosmic_df)

        # UniProt domains
        if self.config.use_uniprot and uniprot_domains is not None:
            df = self._add_uniprot_features(df, uniprot_domains)

        # Conservation scores (placeholder - would need bigWig files)
        df = self._add_conservation_features(df)

        # Splice site distance
        df = self._add_splice_features(df)

        logger.info("Feature engineering complete: %d features", len(df.columns))
        return df

    def _add_variant_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add basic variant features."""
        # Variant type
        if "variant_type" not in df.columns and all(c in df.columns for c in ["ref", "alt"]):
            df["variant_type"] = df.apply(
                lambda row: self._classify_variant_type(row["ref"], row["alt"]), axis=1
            )

        # Variant length
        if "ref" in df.columns and "alt" in df.columns:
            df["ref_len"] = df["ref"].str.len()
            df["alt_len"] = df["alt"].str.len()
            df["length_diff"] = df["alt_len"] - df["ref_len"]
            df["is_snv"] = (df["ref_len"] == 1) & (df["alt_len"] == 1)
            df["is_indel"] = df["length_diff"] != 0

        # Chromosome encoding
        if "chrom" in df.columns:
            df["chromosome"] = df["chrom"].str.replace("chr", "", regex=False)
            # Encode X, Y, MT
            chrom_map = {str(i): i for i in range(1, 23)}
            chrom_map.update({"X": 23, "Y": 24, "MT": 25, "M": 25})
            df["chromosome_num"] = df["chromosome"].map(chrom_map).fillna(0).astype(int)

        return df

    def _classify_variant_type(self, ref: str, alt: str) -> str:
        """Classify variant type."""
        if alt == "*" or (alt.startswith("<") and alt.endswith(">")) or "[" in alt or "]" in alt:
            return "STRUCTURAL"
        if len(ref) == len(alt) == 1:
            return "SNP"
        if len(ref) != len(alt):
            return "INDEL"
        return "COMPLEX"

    def _add_consequence_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add consequence severity features."""
        if "consequence" in df.columns:
            df["consequence_severity"] = df["consequence"].map(CONSEQUENCE_SEVERITY).fillna(0.01)
            # Most severe consequence per variant
            if "all_consequences" in df.columns:
                df["max_consequence_severity"] = df["all_consequences"].apply(
                    lambda x: max([CONSEQUENCE_SEVERITY.get(c, 0.01) for c in str(x).split("&")]) if pd.notna(x) else 0.01
                )

        if "impact" in df.columns:
            df["impact_severity"] = df["impact"].map(IMPACT_SEVERITY).fillna(0.1)

        return df

    def _add_gnomad_features(self, df: pd.DataFrame, gnomad_df: pd.DataFrame) -> pd.DataFrame:
        """Add gnomAD population frequency features."""
        # Create lookup key
        gnomad_df = gnomad_df.copy()
        gnomad_df["variant_key"] = (
            gnomad_df["chrom"].astype(str) + ":" +
            gnomad_df["pos"].astype(str) + ":" +
            gnomad_df["ref"] + ":" +
            gnomad_df["alt"]
        )

        gnomad_lookup = gnomad_df.set_index("variant_key")[["AF", "AN", "AC", "nhomalt"]].to_dict("index")

        df["variant_key"] = (
            df["chrom"].astype(str).str.replace("chr", "") + ":" +
            df["pos"].astype(str) + ":" +
            df["ref"] + ":" +
            df["alt"]
        )

        def get_gnomad(key: str, field: str, default: float = 0.0) -> float:
            if key in gnomad_lookup:
                val = gnomad_lookup[key].get(field, default)
                return float(val) if pd.notna(val) else default
            return default

        df["gnomad_af"] = df["variant_key"].apply(lambda k: get_gnomad(k, "AF"))
        df["gnomad_an"] = df["variant_key"].apply(lambda k: get_gnomad(k, "AN"))
        df["gnomad_ac"] = df["variant_key"].apply(lambda k: get_gnomad(k, "AC"))
        df["gnomad_nhomalt"] = df["variant_key"].apply(lambda k: get_gnomad(k, "nhomalt"))

        # Population max AF (would need per-population data)
        df["gnomad_af_popmax"] = df["gnomad_af"]  # Placeholder

        # Frequency categories
        df["gnomad_af_category"] = pd.cut(
            df["gnomad_af"],
            bins=[-1, 0, 1e-6, 1e-4, 1e-3, 1e-2, 0.05, 1],
            labels=["absent", "ultra_rare", "rare", "low_freq", "common", "high_freq", "very_common"],
        )

        return df.drop(columns=["variant_key"])

    def _add_clinvar_features(self, df: pd.DataFrame, clinvar_df: pd.DataFrame) -> pd.DataFrame:
        """Add ClinVar clinical significance features."""
        # Create lookup efficiently - only keep needed columns
        needed_cols = ["Chromosome", "Start", "ReferenceAllele", "AlternateAllele",
                       "ClinicalSignificance", "ClinSigSimple", "ReviewStatus", "NumberSubmitters", "Guidelines"]
        clinvar_small = clinvar_df[needed_cols].copy()
        
        # Create variant_key using vectorized operations
        clinvar_small["variant_key"] = (
            clinvar_small["Chromosome"].astype(str).str.replace("chr", "") + ":" +
            clinvar_small["Start"].astype(str) + ":" +
            clinvar_small["ReferenceAllele"] + ":" +
            clinvar_small["AlternateAllele"]
        )
        
        # Deduplicate - keep first occurrence (most recent/reviewed)
        clinvar_small = clinvar_small.drop_duplicates(subset="variant_key", keep="first")
        
        # Build lookup dict directly (more memory efficient than set_index + to_dict)
        clinvar_lookup = {}
        for _, row in clinvar_small.iterrows():
            key = row["variant_key"]
            if key not in clinvar_lookup:
                clinvar_lookup[key] = {
                    "ClinicalSignificance": row["ClinicalSignificance"],
                    "ClinSigSimple": row["ClinSigSimple"],
                    "ReviewStatus": row["ReviewStatus"],
                    "NumberSubmitters": row["NumberSubmitters"],
                    "Guidelines": row["Guidelines"],
                }
        
        # Free memory
        del clinvar_small

        df["variant_key"] = (
            df.get("chrom", df.get("Chromosome", "")).astype(str).str.replace("chr", "") + ":" +
            df.get("pos", df.get("Start", "")).astype(str) + ":" +
            df.get("ref", df.get("ReferenceAllele", "")) + ":" +
            df.get("alt", df.get("AlternateAllele", ""))
        )

        def get_clinvar(key: str, field: str, default: Any = None) -> Any:
            if key in clinvar_lookup:
                val = clinvar_lookup[key].get(field, default)
                return val if pd.notna(val) else default
            return default

        df["clinvar_significance"] = df["variant_key"].apply(lambda k: get_clinvar(k, "ClinicalSignificance", "not_provided"))
        df["clinvar_significance_simple"] = df["variant_key"].apply(lambda k: str(get_clinvar(k, "ClinSigSimple", "not_provided")))
        df["clinvar_review_status"] = df["variant_key"].apply(lambda k: str(get_clinvar(k, "ReviewStatus", "no_criteria")))
        df["clinvar_submitters"] = df["variant_key"].apply(lambda k: get_clinvar(k, "NumberSubmitters", 0))
        df["clinvar_guidelines"] = df["variant_key"].apply(lambda k: get_clinvar(k, "Guidelines", False))

        # Significance score
        df["clinvar_significance_score"] = df["clinvar_significance_simple"].str.lower().map(CLINVAR_SIGNIFICANCE_MAP).fillna(0.0)

        # Review status score
        review_status_map = {
            "practice_guideline": 1.0,
            "reviewed_by_expert_panel": 0.9,
            "criteria_provided_multiple_submitters": 0.7,
            "criteria_provided_single_submitter": 0.5,
            "no_assertion_criteria": 0.3,
            "no_criteria": 0.1,
        }
        df["clinvar_review_status_score"] = df["clinvar_review_status"].str.lower().map(review_status_map).fillna(0.1)

        return df.drop(columns=["variant_key"])

    def _add_ensembl_features(self, df: pd.DataFrame, ensembl_df: pd.DataFrame) -> pd.DataFrame:
        """Add Ensembl/VEP features."""
        # Would merge on variant key
        # For now, add placeholder columns if they exist in ensembl_df
        for col in ["gene_symbol", "gene_id", "transcript_id", "biotype", "strand", "exon", "intron"]:
            if col in ensembl_df.columns and col not in df.columns:
                df[col] = np.nan

        if "gene_biotype" not in df.columns and "biotype" in df.columns:
            df["gene_biotype"] = df["biotype"]

        return df

    def _add_alphamissense_features(self, df: pd.DataFrame, am_df: pd.DataFrame) -> pd.DataFrame:
        """Add AlphaMissense pathogenicity features."""
        # Create lookup
        am_df = am_df.copy()
        am_df["variant_key"] = (
            am_df["uniprot_id"] + ":" +
            am_df["protein_variant"]
        )
        am_lookup = am_df.set_index("variant_key")[["am_pathogenicity", "am_class"]].to_dict("index")

        # Need to map from genomic to protein variant - placeholder
        df["alphamissense_score"] = np.nan
        df["alphamissense_class"] = np.nan

        return df

    def _add_cosmic_features(self, df: pd.DataFrame, cosmic_df: pd.DataFrame) -> pd.DataFrame:
        """Add COSMIC cancer mutation features."""
        # Count occurrences in COSMIC
        cosmic_df = cosmic_df.copy()
        cosmic_df["variant_key"] = (
            cosmic_df["Chromosome"].astype(str).str.replace("chr", "") + ":" +
            cosmic_df["Position"].astype(str) + ":" +
            cosmic_df["Reference_Allele"] + ":" +
            cosmic_df["Mutant_Allele"]
        )

        cosmic_counts = cosmic_df.groupby("variant_key").size().to_dict()
        cosmic_tumor_types = cosmic_df.groupby("variant_key")["Primary_site"].apply(lambda x: x.nunique()).to_dict()

        df["variant_key"] = (
            df["chrom"].astype(str).str.replace("chr", "") + ":" +
            df["pos"].astype(str) + ":" +
            df["ref"] + ":" +
            df["alt"]
        )

        df["cosmic_count"] = df["variant_key"].map(cosmic_counts).fillna(0).astype(int)
        df["cosmic_tumor_types"] = df["variant_key"].map(cosmic_tumor_types).fillna(0).astype(int)
        df["in_cosmic"] = (df["cosmic_count"] > 0).astype(int)

        return df.drop(columns=["variant_key"])

    def _add_uniprot_features(self, df: pd.DataFrame, uniprot_domains: dict[str, list[dict]]) -> pd.DataFrame:
        """Add UniProt protein domain features."""
        # Count domains overlapping variant position
        # This is a placeholder - would need genomic-to-protein coordinate mapping
        df["protein_domain_count"] = 0
        df["in_protein_domain"] = 0
        df["disorder_score"] = np.nan

        return df

    def _add_conservation_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add conservation scores (PhyloP, PhastCons)."""
        # Placeholder - would need bigWig file access
        df["conservation_phylop"] = np.nan
        df["conservation_phastcons"] = np.nan
        return df

    def _add_splice_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add splice site distance features."""
        # Placeholder - would need gene annotation
        df["distance_to_splice_site"] = np.nan
        df["exon_number"] = np.nan
        df["intron_number"] = np.nan
        return df


def prepare_training_data(
    variants: pd.DataFrame,
    labels: pd.Series | np.ndarray,
    config: FeatureConfig | None = None,
    **kwargs,
) -> tuple[np.ndarray, np.ndarray, VariantPreprocessor]:
    """Prepare complete training data with features and labels."""
    engineer = FeatureEngineer(config)
    features = engineer.engineer_features(variants, **kwargs)

    preprocessor = VariantPreprocessor(config)
    X = preprocessor.fit_transform(features)

    y = np.asarray(labels)
    if len(y) != len(X):
        raise ValueError(f"Label length {len(y)} != feature length {len(X)}")

    logger.info("Prepared training data: X=%s, y=%s", X.shape, y.shape)
    return X, y, preprocessor


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Feature engineering module ready")