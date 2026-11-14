"""
Molecular Docking Engine Package

Comprehensive molecular docking platform with AutoDock Vina, smina, GNINA integration,
pose analysis, rescoring, and visualization.

Modules:
- protein_prep: Protein preparation for docking (PDBQT generation, binding site prediction)
- ligand_prep: Ligand preparation (tautomers, stereoisomers, conformers, PDBQT)
- docking_engine: Multi-engine docking (Vina, smina, GNINA, internal)
- pose_analyzer: RMSD clustering, interaction fingerprints, pose rescoring
- scoring: Scoring functions (Vina, RF-Score, NNScore, MM/GBSA, consensus)
- visualization: 3D/2D visualization, PyMOL export, interaction diagrams
- docking_ui: Streamlit UI for all docking functionality
"""

from geneai.molecular_docking.protein_prep import (
    ProteinPreparator,
    BindingSite,
    ProteinPrepResult,
    prepare_protein,
    predict_binding_site,
)

from geneai.molecular_docking.ligand_prep import (
    LigandPreparator,
    LigandPrepResult,
    prepare_ligand,
)

from geneai.molecular_docking.docking_engine import (
    DockingEngine,
    DockingConfig,
    DockingResult,
    DockingPose,
    dock,
)

from geneai.molecular_docking.pose_analyzer import (
    PoseAnalyzer,
    PoseRescorer,
    ConsensusScorer,
    ClusterResult,
    InteractionFingerprint,
    RescoringResult,
    analyze_poses,
    generate_ifp,
    rescore_poses,
)

from geneai.molecular_docking.scoring import (
    ScoringFunction,
    VinaScoringFunction,
    RFScore,
    NNScore,
    ConsensusScorer as ScoringConsensusScorer,
    MMGBSARescorer,
    ScoringComponents,
    get_scoring_function,
    create_consensus_scorer,
)

from geneai.molecular_docking.visualization import (
    PoseVisualizer,
    VisualizationConfig,
    create_3d_view,
    create_2d_diagram,
    export_pymol,
)

from geneai.molecular_docking.docking_ui import render_molecular_docking_ui

__all__ = [
    # Protein Preparation
    "ProteinPreparator",
    "BindingSite",
    "ProteinPrepResult",
    "prepare_protein",
    "predict_binding_site",
    
    # Ligand Preparation
    "LigandPreparator",
    "LigandPrepResult",
    "prepare_ligand",
    
    # Docking Engine
    "DockingEngine",
    "DockingConfig",
    "DockingResult",
    "DockingPose",
    "dock",
    
    # Pose Analysis
    "PoseAnalyzer",
    "PoseRescorer",
    "ConsensusScorer",
    "ClusterResult",
    "InteractionFingerprint",
    "RescoringResult",
    "analyze_poses",
    "generate_ifp",
    "rescore_poses",
    
    # Scoring
    "ScoringFunction",
    "VinaScoringFunction",
    "RFScore",
    "NNScore",
    "ScoringConsensusScorer",
    "MMGBSARescorer",
    "ScoringComponents",
    "get_scoring_function",
    "create_consensus_scorer",
    
    # Visualization
    "PoseVisualizer",
    "VisualizationConfig",
    "create_3d_view",
    "create_2d_diagram",
    "export_pymol",
    
    # UI
    "render_molecular_docking_ui",
]

__version__ = "1.0.0"