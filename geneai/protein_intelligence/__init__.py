"""Protein Intelligence Engine package."""
from __future__ import annotations

# Core analysis
from geneai.protein_intelligence.sequence_analyzer import (
    ProteinSequenceAnalyzer,
    ProteinFeatures,
    analyze_protein_sequence,
)
from geneai.protein_intelligence.structure_retriever import (
    StructureRetriever,
    ProteinStructure,
    retrieve_structure,
)
from geneai.protein_intelligence.structure_analyzer import (
    StructureAnalyzer,
    StructureAnalysis,
    BindingPocket,
    analyze_structure,
)
from geneai.protein_intelligence.function_predictor import (
    FunctionPredictor,
    FunctionPrediction,
    predict_function,
)
from geneai.protein_intelligence.interaction_analyzer import (
    InteractionAnalyzer,
    ProteinInteraction,
    InteractionNetwork,
    get_interactions,
    build_network,
)
from geneai.protein_intelligence.visualization import (
    ProteinVisualizer,
    Structure3DView,
    create_3d_structure_view,
    create_sequence_feature_plot,
    create_interaction_network_plot,
    create_conservation_heatmap,
)

# UI
from geneai.protein_intelligence.protein_ui import render_protein_intelligence_dashboard

__all__ = [
    # Sequence Analysis
    "ProteinSequenceAnalyzer",
    "ProteinFeatures",
    "analyze_protein_sequence",
    # Structure Retrieval
    "StructureRetriever",
    "ProteinStructure",
    "retrieve_structure",
    # Structure Analysis
    "StructureAnalyzer",
    "StructureAnalysis",
    "BindingPocket",
    "analyze_structure",
    # Function Prediction
    "FunctionPredictor",
    "FunctionPrediction",
    "predict_function",
    # Interaction Analysis
    "InteractionAnalyzer",
    "ProteinInteraction",
    "InteractionNetwork",
    "get_interactions",
    "build_network",
    # Visualization
    "ProteinVisualizer",
    "Structure3DView",
    "create_3d_structure_view",
    "create_sequence_feature_plot",
    "create_interaction_network_plot",
    "create_conservation_heatmap",
    # UI
    "render_protein_intelligence_dashboard",
]