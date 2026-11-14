"""Mutation ML Module - ML training pipeline for mutation interpretation."""
from __future__ import annotations

from geneai.mutation_ml.dataset_acquisition import (
    ClinVarFetcher,
    GnomADFetcher,
    EnsemblFetcher,
    dbSNPFetcher,
    COSMICFetcher,
    UniProtFetcher,
    AlphaMissenseFetcher,
    download_all_datasets,
)
from geneai.mutation_ml.preprocessing import (
    VariantPreprocessor,
    FeatureEngineer,
    prepare_training_data,
)
from geneai.mutation_ml.training import (
    MutationMLTrainer,
    train_mutation_classifier,
    evaluate_model,
)
from geneai.mutation_ml.explainability import (
    MutationExplainer,
    explain_prediction,
)
from geneai.mutation_ml.integration import (
    MutationMLIntegration,
    enhance_vcf_with_ml,
    create_training_dataset_from_vcf,
)
from geneai.mutation_ml.dashboard import render_ml_dashboard_page
from geneai.mutation_ml.api import app as mutation_ml_api

__all__ = [
    "ClinVarFetcher",
    "GnomADFetcher",
    "EnsemblFetcher",
    "dbSNPFetcher",
    "COSMICFetcher",
    "UniProtFetcher",
    "AlphaMissenseFetcher",
    "download_all_datasets",
    "VariantPreprocessor",
    "FeatureEngineer",
    "prepare_training_data",
    "MutationMLTrainer",
    "train_mutation_classifier",
    "evaluate_model",
    "MutationExplainer",
    "explain_prediction",
    "MutationMLIntegration",
    "enhance_vcf_with_ml",
    "create_training_dataset_from_vcf",
    "render_ml_dashboard_page",
    "mutation_ml_api",
]