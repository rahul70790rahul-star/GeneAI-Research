"""GeneAI Deep Learning - Phase 5 Enhancement."""
from __future__ import annotations

# PyTorch/PyG are optional dependencies - import lazily
try:
    from geneai.deep_learning.molecular_gnn import (
        MolecularGraphDataset,
        GNNModel,
        MolecularMLP,
        DeepLearningTrainer,
        TrainingConfig,
        smiles_to_graph,
        create_molecular_dataloaders,
        train_gnn_model,
        train_mlp_model,
        predict_with_model,
        save_model,
        load_model,
        TORCH_AVAILABLE,
        PYG_AVAILABLE,
        RDKIT_AVAILABLE,
    )
    _DL_IMPORTED = True
except ImportError:
    MolecularGraphDataset = None
    GNNModel = None
    MolecularMLP = None
    DeepLearningTrainer = None
    TrainingConfig = None
    smiles_to_graph = None
    create_molecular_dataloaders = None
    train_gnn_model = None
    train_mlp_model = None
    predict_with_model = None
    save_model = None
    load_model = None
    TORCH_AVAILABLE = False
    PYG_AVAILABLE = False
    RDKIT_AVAILABLE = False
    _DL_IMPORTED = False

__all__ = [
    "MolecularGraphDataset",
    "GNNModel",
    "MolecularMLP",
    "DeepLearningTrainer",
    "TrainingConfig",
    "smiles_to_graph",
    "create_molecular_dataloaders",
    "train_gnn_model",
    "train_mlp_model",
    "predict_with_model",
    "save_model",
    "load_model",
    "TORCH_AVAILABLE",
    "PYG_AVAILABLE",
    "RDKIT_AVAILABLE",
]

__version__ = "5.13.0"