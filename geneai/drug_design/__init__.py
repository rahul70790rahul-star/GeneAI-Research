"""
Drug Design Engine Package

A comprehensive molecular design platform combining generative AI, physics-based modeling,
and ADMET prediction for accelerated drug discovery.

Modules:
- molecule_generator: Multi-strategy molecule generation
- property_calculator: Comprehensive molecular property calculation
- similarity_engine: Molecular similarity, search, and clustering
- scaffold_hopper: Advanced scaffold hopping with multiple strategies
- validator: Molecule validation and filtering
- docking_engine: Molecular docking with multiple backends
- admet_predictor: ADMET property prediction
- drug_design_ui: Streamlit UI for all modules
"""

from geneai.drug_design.molecule_generator import (
    MoleculeGenerator,
    GenerationStrategy,
    GenerationConstraints,
    generate_molecules,
)

from geneai.drug_design.property_calculator import (
    PropertyCalculator,
    calculate_properties,
    calculate_drug_likeness,
    calculate_pains_alerts,
    calculate_structural_alerts,
    calculate_all_properties,
)

from geneai.drug_design.similarity_engine import (
    SimilarityEngine,
    FingerprintType,
    SimilarityMetric,
    calculate_similarity,
    search_library,
    cluster_molecules_butina,
    cluster_molecules_kmeans,
    calculate_diversity_metrics,
)

from geneai.drug_design.scaffold_hopper import (
    ScaffoldHopper,
    ScaffoldHopResult,
    ScaffoldLibrary,
    hop_scaffold,
)

from geneai.drug_design.validator import (
    MoleculeValidator,
    ValidationResult,
    validate_molecule,
)

from geneai.drug_design.docking_engine import (
    DockingEngine,
    Receptor,
    DockingResult,
    DockingPose,
    create_receptor_from_pdb,
    create_receptor_from_pdb_string,
)

from geneai.drug_design.admet_predictor import (
    ADMETPredictor,
    ADMETResult,
    ADMETProperty,
    predict_admet,
)

from geneai.drug_design.drug_design_ui import render_drug_design_ui

__all__ = [
    # Molecule Generation
    "MoleculeGenerator",
    "GenerationStrategy",
    "GenerationConstraints",
    "generate_molecules",
    
    # Property Calculator
    "PropertyCalculator",
    "calculate_properties",
    "calculate_drug_likeness",
    "calculate_pains_alerts",
    "calculate_structural_alerts",
    "calculate_all_properties",
    
    # Similarity Engine
    "SimilarityEngine",
    "FingerprintType",
    "SimilarityMetric",
    "calculate_similarity",
    "search_library",
    "cluster_molecules_butina",
    "cluster_molecules_kmeans",
    "calculate_diversity_metrics",
    
    # Scaffold Hopping
    "ScaffoldHopper",
    "ScaffoldHopResult",
    "ScaffoldLibrary",
    "hop_scaffold",
    
    # Validator
    "MoleculeValidator",
    "ValidationResult",
    "validate_molecule",
    
    # Docking Engine
    "DockingEngine",
    "Receptor",
    "DockingResult",
    "DockingPose",
    "create_receptor_from_pdb",
    "create_receptor_from_pdb_string",
    
    # ADMET Predictor
    "ADMETPredictor",
    "ADMETResult",
    "ADMETProperty",
    "predict_admet",
    
    # UI
    "render_drug_design_ui",
]

__version__ = "1.0.0"