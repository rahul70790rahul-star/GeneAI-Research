"""Drug Discovery module for GeneAI Research - Phase 4.5."""

from .drug_database import (
    initialize_database,
    upsert_drug,
    get_drug_by_source_id,
    search_drugs,
    get_drug_by_inchikey,
    upsert_target,
    get_target_by_source_id,
    search_targets_by_gene,
    upsert_drug_target_interaction,
    get_drug_target_interactions,
    get_target_drug_interactions,
    upsert_disease,
    get_disease_by_source_id,
    upsert_clinical_trial,
    get_clinical_trial_by_nct,
    search_clinical_trials,
    upsert_literature,
    get_drug_literature,
    get_gene_literature,
)

from .drug_search import (
    search_drugs_by_name,
    search_drugs_by_target,
    search_drugs_by_disease,
    get_drug_details,
    search_by_chemical_identifier,
    search_drugs_comprehensive,
)

from .drug_target_analysis import (
    analyze_drug_targets,
    analyze_target_drugs,
    analyze_gene_drug_associations,
    compare_drugs,
)

from .gene_drug_mapping import (
    map_gene_to_drugs,
    map_variant_to_drugs,
    map_gene_list_to_drugs,
    get_drug_recommendations_for_gene,
    store_gene_drug_mapping,
    build_vcf_to_drug_report,
)

from .drug_comparison import (
    compare_drugs_detailed,
    generate_comparison_report,
    find_similar_drugs,
)

from .drug_visualization import (
    create_drug_target_network,
    create_gene_drug_network,
    create_disease_drug_network,
    create_clinical_trial_status_chart,
    create_drug_property_radar,
    create_drug_property_scatter,
    create_target_druggability_chart,
)

from .drug_report import (
    generate_drug_report_csv,
    generate_gene_drug_report_csv,
    generate_comparison_report_csv,
    generate_vcf_drug_report_json,
    generate_drug_report_pdf_content,
    export_drug_to_database,
)

from .drug_ui import render_drug_discovery_dashboard

__all__ = [
    # Database
    "initialize_database",
    "upsert_drug",
    "get_drug_by_source_id",
    "search_drugs",
    "get_drug_by_inchikey",
    "upsert_target",
    "get_target_by_source_id",
    "search_targets_by_gene",
    "upsert_drug_target_interaction",
    "get_drug_target_interactions",
    "get_target_drug_interactions",
    "upsert_disease",
    "get_disease_by_source_id",
    "upsert_clinical_trial",
    "get_clinical_trial_by_nct",
    "search_clinical_trials",
    "upsert_literature",
    "get_drug_literature",
    "get_gene_literature",
    # Search
    "search_drugs_by_name",
    "search_drugs_by_target",
    "search_drugs_by_disease",
    "get_drug_details",
    "search_by_chemical_identifier",
    "search_drugs_comprehensive",
    # Target Analysis
    "analyze_drug_targets",
    "analyze_target_drugs",
    "analyze_gene_drug_associations",
    "compare_drugs",
    # Gene-Drug Mapping
    "map_gene_to_drugs",
    "map_variant_to_drugs",
    "map_gene_list_to_drugs",
    "get_drug_recommendations_for_gene",
    "store_gene_drug_mapping",
    "build_vcf_to_drug_report",
    # Comparison
    "compare_drugs_detailed",
    "generate_comparison_report",
    "find_similar_drugs",
    # Visualization
    "create_drug_target_network",
    "create_gene_drug_network",
    "create_disease_drug_network",
    "create_clinical_trial_status_chart",
    "create_drug_property_radar",
    "create_drug_property_scatter",
    "create_target_druggability_chart",
    # Reports
    "generate_drug_report_csv",
    "generate_gene_drug_report_csv",
    "generate_comparison_report_csv",
    "generate_vcf_drug_report_json",
    "generate_drug_report_pdf_content",
    "export_drug_to_database",
    # UI
    "render_drug_discovery_dashboard",
]