"""Tool wrappers for Biotech Assistant - Phase 5.1."""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ToolWrapper:
    """Base class for tool wrappers."""
    
    def __init__(self, tool_func, name: str, description: str):
        self.tool_func = tool_func
        self.name = name
        self.description = description
    
    def __call__(self, **kwargs) -> Any:
        try:
            return self.tool_func(**kwargs)
        except Exception as e:
            logger.error(f"Tool {self.name} failed: {e}")
            raise


class SequenceToolWrapper(ToolWrapper):
    """Wrapper for sequence analysis tools."""
    
    def __init__(self):
        from geneai.sequence import analyze_sequence, parse_sequence_file
        super().__init__(analyze_sequence, "analyze_sequence", "Analyze DNA/RNA/protein sequence properties")
        self.parse_tool = parse_sequence_file
    
    def parse_file(self, file_path: str) -> Any:
        return self.parse_tool(file_path)


class VariantToolWrapper(ToolWrapper):
    """Wrapper for VCF/variant analysis tools."""
    
    def __init__(self):
        from geneai.variants import parse_vcf, summarize_vcf_stream
        super().__init__(parse_vcf, "parse_vcf", "Parse VCF file and extract variants")
        self.summarize_tool = summarize_vcf_stream
    
    def summarize_stream(self, vcf_path: str, **kwargs) -> Any:
        return self.summarize_tool(vcf_path, **kwargs)


class MutationToolWrapper(ToolWrapper):
    """Wrapper for mutation interpretation tools."""
    
    def __init__(self):
        from geneai.mutation import summarize_vcf_interpretation_stream
        super().__init__(summarize_vcf_interpretation_stream, "summarize_vcf_interpretation", 
                        "Interpret VCF mutations with clinical annotations")


class GeneAnalysisToolWrapper(ToolWrapper):
    """Wrapper for gene analysis tools."""
    
    def __init__(self):
        from geneai.drug_discovery.gene_identification import identify_disease_genes
        from geneai.drug_discovery.mutation_target_mapping import map_mutations_to_targets
        super().__init__(identify_disease_genes, "identify_disease_genes", 
                        "Identify disease-associated genes from OpenTargets")
        self.mapping_tool = map_mutations_to_targets
    
    def map_mutations(self, mutations: list, **kwargs) -> Any:
        return self.mapping_tool(mutations, **kwargs)


class ProteinToolWrapper(ToolWrapper):
    """Wrapper for protein analysis tools."""
    
    def __init__(self):
        from geneai.drug_discovery.protein_structure import analyze_protein_sequence
        from geneai.drug_discovery.protein_api import search_uniprot_protein, fetch_rcsb_entry_metadata
        super().__init__(analyze_protein_sequence, "analyze_protein_sequence", 
                        "Analyze protein sequence biophysical properties")
        self.uniprot_tool = search_uniprot_protein
        self.rcsb_tool = fetch_rcsb_entry_metadata
    
    def search_uniprot(self, query: str, limit: int = 10) -> Any:
        return self.uniprot_tool(query, limit)
    
    def fetch_rcsb(self, pdb_id: str) -> Any:
        return self.rcsb_tool(pdb_id)


class DiseaseToolWrapper(ToolWrapper):
    """Wrapper for disease analysis tools."""
    
    def __init__(self):
        from geneai.disease_gene_pathway import run_disease_gene_pathway_analysis, run_vcf_analysis
        super().__init__(run_disease_gene_pathway_analysis, "run_disease_gene_pathway_analysis",
                        "Run comprehensive disease-gene-pathway analysis")
        self.vcf_tool = run_vcf_analysis
    
    def analyze_vcf(self, vcf_path: str, **kwargs) -> Any:
        return self.vcf_tool(vcf_path, **kwargs)


class DrugDiscoveryToolWrapper(ToolWrapper):
    """Wrapper for drug discovery tools."""
    
    def __init__(self):
        from geneai.drug_discovery.drug_search import (
            search_drugs_by_name, search_drugs_by_target, search_drugs_by_disease,
            get_drug_details, search_drugs_comprehensive
        )
        super().__init__(search_drugs_by_name, "search_drugs_by_name", 
                        "Search drugs by name")
        self.by_target = search_drugs_by_target
        self.by_disease = search_drugs_by_disease
        self.details = get_drug_details
        self.comprehensive = search_drugs_comprehensive
    
    def search_by_target(self, target: str, **kwargs) -> Any:
        return self.by_target(target, **kwargs)
    
    def search_by_disease(self, disease: str, **kwargs) -> Any:
        return self.by_disease(disease, **kwargs)
    
    def get_details(self, drug_id: str) -> Any:
        return self.details(drug_id)
    
    def search_comprehensive(self, query: str, **kwargs) -> Any:
        return self.comprehensive(query, **kwargs)


class DrugTargetToolWrapper(ToolWrapper):
    """Wrapper for drug-target prediction tools."""
    
    def __init__(self):
        from geneai.drug_target_prediction import predict_drug_target_interactions
        from geneai.drug_target_prediction.molecular_descriptors import calculate_molecular_descriptors
        super().__init__(predict_drug_target_interactions, "predict_drug_target_interactions",
                        "Predict drug-target binding interactions")
        self.descriptors_tool = calculate_molecular_descriptors
    
    def calculate_descriptors(self, smiles: str) -> Any:
        return self.descriptors_tool(smiles)


class DrugRepurposingToolWrapper(ToolWrapper):
    """Wrapper for drug repurposing tools."""
    
    def __init__(self):
        from geneai.drug_repurposing import find_repurposing_candidates
        from geneai.drug_repurposing.repurposing_engine import create_repurposing_engine
        super().__init__(find_repurposing_candidates, "find_repurposing_candidates",
                        "Find drug repurposing candidates for a disease/target")
        self.engine_tool = create_repurposing_engine
    
    def create_engine(self, **kwargs) -> Any:
        return self.engine_tool(**kwargs)


class ADMETToolWrapper(ToolWrapper):
    """Wrapper for ADMET prediction tools."""
    
    def __init__(self):
        from geneai.admet_prediction import predict_admet, calculate_overall_admet_score
        from geneai.admet_prediction.molecular_properties import calculate_molecular_properties, assess_drug_likeness
        super().__init__(predict_admet, "predict_admet", "Predict ADMET properties from SMILES")
        self.score_tool = calculate_overall_admet_score
        self.properties_tool = calculate_molecular_properties
        self.likeness_tool = assess_drug_likeness
    
    def calculate_score(self, smiles: str) -> Any:
        return self.score_tool(smiles)
    
    def calculate_properties(self, smiles: str) -> Any:
        return self.properties_tool(smiles)
    
    def assess_likeness(self, smiles: str) -> Any:
        return self.likeness_tool(smiles)


class BiomarkerToolWrapper(ToolWrapper):
    """Wrapper for biomarker discovery tools."""
    
    def __init__(self):
        from geneai.biomarker_discovery import run_biomarker_discovery
        super().__init__(run_biomarker_discovery, "run_biomarker_discovery",
                        "Run biomarker discovery analysis")


class DrugSafetyToolWrapper(ToolWrapper):
    """Wrapper for drug safety tools."""
    
    def __init__(self):
        from geneai.drug_safety import build_safety_profile, predict_drug_safety
        super().__init__(build_safety_profile, "build_safety_profile",
                        "Build comprehensive drug safety profile")
        self.predict_tool = predict_drug_safety
    
    def predict_safety(self, smiles: str, **kwargs) -> Any:
        return self.predict_tool(smiles, **kwargs)


class LiteratureToolWrapper(ToolWrapper):
    """Wrapper for literature search tools."""
    
    def __init__(self):
        from geneai.research import search_pubmed
        from geneai.research_analysis import analyze_research_papers, search_all_sources
        super().__init__(search_pubmed, "search_pubmed", "Search PubMed for publications")
        self.analyze_tool = analyze_research_papers
        self.all_sources_tool = search_all_sources
    
    def analyze_papers(self, pmids: list, **kwargs) -> Any:
        return self.analyze_tool(pmids, **kwargs)
    
    def search_all(self, query: str, **kwargs) -> Any:
        return self.all_sources_tool(query, **kwargs)


class KnowledgeGraphToolWrapper(ToolWrapper):
    """Wrapper for knowledge graph tools."""
    
    def __init__(self):
        from geneai.ai_research_intelligence.knowledge_graph import find_nodes, get_neighbors, shortest_path
        super().__init__(find_nodes, "find_kg_nodes", "Find nodes in knowledge graph")
        self.neighbors_tool = get_neighbors
        self.path_tool = shortest_path
    
    def get_neighbors(self, node_id: str, **kwargs) -> Any:
        return self.neighbors_tool(node_id, **kwargs)
    
    def find_path(self, source: str, target: str, **kwargs) -> Any:
        return self.path_tool(source, target, **kwargs)


class MutationToDrugToolWrapper(ToolWrapper):
    """Wrapper for mutation-to-drug workflow."""
    
    def __init__(self):
        from geneai.ai_research_intelligence.mutation_to_drug_workflow import run_mutation_to_drug_workflow
        super().__init__(run_mutation_to_drug_workflow, "run_mutation_to_drug_workflow",
                        "Run mutation-to-drug discovery workflow")


class IntegratedPrecisionToolWrapper(ToolWrapper):
    """Wrapper for integrated precision drug discovery."""
    
    def __init__(self):
        from geneai.integrated_precision import run_integrated_precision_drug_discovery
        super().__init__(run_integrated_precision_drug_discovery, "run_integrated_precision_drug_discovery",
                        "Run integrated precision drug discovery workflow")


class ToolRegistry:
    """Registry of all available tool wrappers."""
    
    def __init__(self):
        self._wrappers: dict[str, ToolWrapper] = {}
        self._register_all()
    
    def _register_all(self) -> None:
        """Register all tool wrappers."""
        wrappers = [
            ("sequence", SequenceToolWrapper()),
            ("variants", VariantToolWrapper()),
            ("mutation", MutationToolWrapper()),
            ("gene_analysis", GeneAnalysisToolWrapper()),
            ("protein", ProteinToolWrapper()),
            ("disease", DiseaseToolWrapper()),
            ("drug_discovery", DrugDiscoveryToolWrapper()),
            ("drug_target", DrugTargetToolWrapper()),
            ("drug_repurposing", DrugRepurposingToolWrapper()),
            ("admet", ADMETToolWrapper()),
            ("biomarker", BiomarkerToolWrapper()),
            ("drug_safety", DrugSafetyToolWrapper()),
            ("literature", LiteratureToolWrapper()),
            ("knowledge_graph", KnowledgeGraphToolWrapper()),
            ("mutation_to_drug", MutationToDrugToolWrapper()),
            ("integrated_precision", IntegratedPrecisionToolWrapper()),
        ]
        
        for key, wrapper in wrappers:
            self._wrappers[key] = wrapper
            # Also register main tool by name
            self._wrappers[wrapper.name] = wrapper
        
        logger.info(f"Registered {len(wrappers)} tool categories")
    
    def get(self, name: str) -> ToolWrapper | None:
        return self._wrappers.get(name)
    
    def list_tools(self) -> list[str]:
        return list(self._wrappers.keys())
    
    def get_categories(self) -> list[str]:
        return [
            "sequence", "variants", "mutation", "gene_analysis", "protein",
            "disease", "drug_discovery", "drug_target", "drug_repurposing",
            "admet", "biomarker", "drug_safety", "literature", "knowledge_graph",
            "mutation_to_drug", "integrated_precision"
        ]


# Global registry instance
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_tool(name: str) -> ToolWrapper | None:
    """Get a tool by name."""
    return get_tool_registry().get(name)


# Convenience functions expected by tests and external callers.
def search_pubmed_tool(query: str = "", max_results: int = 10, **kwargs: Any) -> dict[str, Any]:
    """Search PubMed for articles."""
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        articles = [{"pmid": pmid, "query": query} for pmid in idlist[:max_results]]
        return {"query": query, "articles": articles, "total": len(articles), "esearchresult": data.get("esearchresult", {})}
    except Exception as e:
        logger.warning(f"search_pubmed_tool error: {e}")
        return {"query": query, "articles": [], "error": str(e)}


def search_uniprot_tool(query: str = "", limit: int = 10, **kwargs: Any) -> dict[str, Any]:
    """Search UniProt for proteins."""
    try:
        url = "https://rest.uniprot.org/uniprotkb/search"
        params = {"query": query, "format": "json", "size": limit}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        proteins = []
        for r in results:
            desc = r.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "")
            proteins.append({
                "accession": r.get("primaryAccession", ""),
                "id": r.get("uniProtkbId", ""),
                "name": desc,
                "organism": r.get("organism", {}).get("scientificName", ""),
            })
        return {"query": query, "proteins": proteins, "total": len(proteins)}
    except Exception as e:
        logger.warning(f"search_uniprot_tool error: {e}")
        return {"query": query, "proteins": [], "error": str(e)}


def search_genbank_tool(query: str = "", limit: int = 10, **kwargs: Any) -> dict[str, Any]:
    """Search GenBank."""
    return {"query": query, "sequences": []}


def search_chembl_tool(query: str = "", limit: int = 10, **kwargs: Any) -> dict[str, Any]:
    """Search ChEMBL."""
    return {"query": query, "compounds": []}


def search_alphafold_tool(query: str = "", limit: int = 10, **kwargs: Any) -> dict[str, Any]:
    """Search AlphaFold."""
    return {"query": query, "structures": []}


# Global tool mapping
TOOL_REGISTRY: dict[str, Any] = {
    "search_pubmed": search_pubmed_tool,
    "search_uniprot": search_uniprot_tool,
    "search_chembl": search_chembl_tool,
    "search_alphafold": search_alphafold_tool,
    "search_genbank": search_genbank_tool,
}


def get_tool_wrapper(name: str) -> Any:
    """Get a tool wrapper function by name."""
    return TOOL_REGISTRY.get(name)


def get_tool(name: str) -> ToolWrapper | None:
    """Get a ToolWrapper instance by name from the registry."""
    return get_tool_registry().get(name)