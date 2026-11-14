"""Specialized agents for biotechnology research - Phase 5.2."""
from __future__ import annotations

import logging
from typing import Any

from geneai.multi_agent.core import BaseAgent, AgentCapability, AgentMessage, MessageType

logger = logging.getLogger(__name__)


class GeneAnalysisAgent(BaseAgent):
    """Agent specialized in gene analysis tasks."""
    
    def __init__(self):
        super().__init__("gene_analysis_agent", "Gene Analysis Agent",
                        "Specializes in gene identification, expression analysis, and disease associations")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.GENE_ANALYSIS,
                description="Identify genes associated with a disease using OpenTargets",
                input_types=["disease_name", "limit", "gene_symbol"],
                output_types=["genes", "count", "gene_info"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease_name": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                        "gene_symbol": {"type": "string"}
                    },
                    "required": ["disease_name"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "genes": {"type": "array"},
                        "count": {"type": "integer"}
                    }
                },
                examples=[{"disease_name": "breast cancer"}]
            ),
            AgentCapability(
                name="analyze_gene_expression",
                description="Analyze gene expression patterns across tissues",
                input_types=["gene_symbols"],
                output_types=["expression_data"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "gene_symbols": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["gene_symbols"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "expression_data": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="find_gene_pathways",
                description="Find pathways a gene participates in",
                input_types=["gene_symbol"],
                output_types=["pathways"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "gene_symbol": {"type": "string"}
                    },
                    "required": ["gene_symbol"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "pathways": {"type": "array"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "identify_disease_genes":
            return self._identify_disease_genes(task)
        elif task_type == "analyze_gene_expression":
            return self._analyze_gene_expression(task)
        elif task_type == "find_gene_pathways":
            return self._find_gene_pathways(task)
        elif task_type == "analyze_gene":
            # Support for test compatibility - delegate to analyze_gene_expression
            return self._analyze_gene_expression(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _identify_disease_genes(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.gene_identification import identify_disease_genes
        disease_name = task.get("disease_name", "")
        limit = task.get("limit", 20)
        result = identify_disease_genes(disease_name, limit=limit)
        return {"genes": result, "count": len(result)}
    
    def _analyze_gene_expression(self, task: dict[str, Any]) -> dict[str, Any]:
        # Placeholder - would integrate with expression databases
        gene_symbols = task.get("gene_symbols", [])
        return {"expression_data": {g: "data_placeholder" for g in gene_symbols}}
    
    def _find_gene_pathways(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.gene_identification import identify_disease_genes
        gene_symbol = task.get("gene_symbol", "")
        # Use disease gene identification as proxy for pathway info
        result = identify_disease_genes(gene_symbol, limit=10)
        return {"pathways": result}


class ProteinAnalysisAgent(BaseAgent):
    """Agent specialized in protein analysis tasks."""
    
    def __init__(self):
        super().__init__("protein_analysis_agent", "Protein Analysis Agent",
                        "Specializes in protein structure, function, and interaction analysis")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.PROTEIN_ANALYSIS,
                description="Analyze protein sequence biophysical properties",
                input_types=["sequence"],
                output_types=["molecular_weight", "isoelectric_point", "hydrophobicity"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "sequence": {"type": "string"}
                    },
                    "required": ["sequence"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "molecular_weight": {"type": "number"},
                        "isoelectric_point": {"type": "number"},
                        "hydrophobicity": {"type": "number"}
                    }
                }
            ),
            AgentCapability(
                name="search_uniprot",
                description="Search UniProt for protein information",
                input_types=["query", "limit"],
                output_types=["proteins"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["query"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "proteins": {"type": "array"}
                    }
                }
            ),
            AgentCapability(
                name="fetch_structure",
                description="Fetch protein structure from RCSB PDB",
                input_types=["pdb_id"],
                output_types=["structure_data"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "pdb_id": {"type": "string"}
                    },
                    "required": ["pdb_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "structure_data": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="predict_interactions",
                description="Predict protein-protein interactions",
                input_types=["protein_id"],
                output_types=["interactions"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "protein_id": {"type": "string"}
                    },
                    "required": ["protein_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "interactions": {"type": "array"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "analyze_protein_sequence":
            return self._analyze_protein_sequence(task)
        elif task_type == "search_uniprot":
            return self._search_uniprot(task)
        elif task_type == "fetch_structure":
            return self._fetch_structure(task)
        elif task_type == "predict_interactions":
            return self._predict_interactions(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _analyze_protein_sequence(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.protein_structure import analyze_protein_sequence
        sequence = task.get("sequence", "")
        return analyze_protein_sequence(sequence)
    
    def _search_uniprot(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.protein_api import search_uniprot_protein
        query = task.get("query", "")
        limit = task.get("limit", 10)
        return {"proteins": search_uniprot_protein(query, limit)}
    
    def _fetch_structure(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.protein_api import fetch_rcsb_entry_metadata
        pdb_id = task.get("pdb_id", "")
        return {"structure_data": fetch_rcsb_entry_metadata(pdb_id)}
    
    def _predict_interactions(self, task: dict[str, Any]) -> dict[str, Any]:
        # Placeholder for STRING DB integration
        protein_id = task.get("protein_id", "")
        return {"interactions": []}


class DrugDiscoveryAgent(BaseAgent):
    """Agent specialized in drug discovery tasks."""
    
    def __init__(self):
        super().__init__("drug_discovery_agent", "Drug Discovery Agent",
                        "Specializes in drug search, target identification, and compound screening")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.DRUG_DISCOVERY,
                description="Search for drugs targeting a specific protein",
                input_types=["target", "limit"],
                output_types=["drugs"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "limit": {"type": "integer", "default": 20}
                    },
                    "required": ["target"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "drugs": {"type": "array"}
                    }
                }
            ),
            AgentCapability(
                name="search_drugs_by_disease",
                description="Search for drugs treating a disease",
                input_types=["disease", "limit"],
                output_types=["drugs"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease": {"type": "string"},
                        "limit": {"type": "integer", "default": 20}
                    },
                    "required": ["disease"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "drugs": {"type": "array"}
                    }
                }
            ),
            AgentCapability(
                name="get_drug_details",
                description="Get detailed information about a drug",
                input_types=["drug_id"],
                output_types=["drug"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "drug_id": {"type": "string"}
                    },
                    "required": ["drug_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "drug": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="predict_drug_target",
                description="Predict drug-target binding interactions",
                input_types=["smiles", "target"],
                output_types=["prediction"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string"},
                        "target": {"type": "string"}
                    },
                    "required": ["smiles", "target"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "prediction": {"type": "object"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "search_drugs_by_target":
            return self._search_drugs_by_target(task)
        elif task_type == "search_drugs_by_disease":
            return self._search_drugs_by_disease(task)
        elif task_type == "get_drug_details":
            return self._get_drug_details(task)
        elif task_type == "predict_drug_target":
            return self._predict_drug_target(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _search_drugs_by_target(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.drug_search import search_drugs_by_target
        target = task.get("target", "")
        limit = task.get("limit", 20)
        return {"drugs": search_drugs_by_target(target, limit=limit)}
    
    def _search_drugs_by_disease(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.drug_search import search_drugs_by_disease
        disease = task.get("disease", "")
        limit = task.get("limit", 20)
        return {"drugs": search_drugs_by_disease(disease, limit=limit)}
    
    def _get_drug_details(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_discovery.drug_search import get_drug_details
        drug_id = task.get("drug_id", "")
        return {"drug": get_drug_details(drug_id)}
    
    def _predict_drug_target(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_target_prediction import predict_drug_target_interactions
        smiles = task.get("smiles", "")
        target = task.get("target", "")
        return {"prediction": predict_drug_target_interactions(smiles, target)}


class ADMETAgent(BaseAgent):
    """Agent specialized in ADMET prediction and drug safety."""
    
    def __init__(self):
        super().__init__("admet_agent", "ADMET & Safety Agent",
                        "Specializes in ADMET prediction, toxicity assessment, and drug safety profiling")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.ADMET_PREDICTION,
                description="Predict ADMET properties from SMILES",
                input_types=["smiles"],
                output_types=["admet"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string"}
                    },
                    "required": ["smiles"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "admet": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="calculate_properties",
                description="Calculate molecular properties",
                input_types=["smiles"],
                output_types=["properties"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string"}
                    },
                    "required": ["smiles"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "properties": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="assess_drug_likeness",
                description="Assess drug-likeness (Lipinski, Veber, etc.)",
                input_types=["smiles"],
                output_types=["drug_likeness"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string"}
                    },
                    "required": ["smiles"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "drug_likeness": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="build_safety_profile",
                description="Build comprehensive drug safety profile",
                input_types=["smiles", "drug_name"],
                output_types=["safety_profile"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string"},
                        "drug_name": {"type": "string"}
                    },
                    "required": ["smiles"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "safety_profile": {"type": "object"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "predict_admet":
            return self._predict_admet(task)
        elif task_type == "calculate_properties":
            return self._calculate_properties(task)
        elif task_type == "assess_drug_likeness":
            return self._assess_drug_likeness(task)
        elif task_type == "build_safety_profile":
            return self._build_safety_profile(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _predict_admet(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.admet_prediction import predict_admet
        smiles = task.get("smiles", "")
        return {"admet": predict_admet(smiles)}
    
    def _calculate_properties(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.admet_prediction.molecular_properties import calculate_molecular_properties
        smiles = task.get("smiles", "")
        return {"properties": calculate_molecular_properties(smiles)}
    
    def _assess_drug_likeness(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.admet_prediction.molecular_properties import assess_drug_likeness
        smiles = task.get("smiles", "")
        return {"drug_likeness": assess_drug_likeness(smiles)}
    
    def _build_safety_profile(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_safety import build_safety_profile
        smiles = task.get("smiles", "")
        drug_name = task.get("drug_name", "")
        return {"safety_profile": build_safety_profile(smiles, drug_name)}


class LiteratureAgent(BaseAgent):
    """Agent specialized in literature search and analysis."""
    
    def __init__(self):
        super().__init__("literature_agent", "Literature Research Agent",
                        "Specializes in searching and analyzing scientific literature")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.LITERATURE_SEARCH,
                description="Search PubMed for publications",
                input_types=["query", "limit"],
                output_types=["papers"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["query"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "papers": {"type": "array"}
                    }
                }
            ),
            AgentCapability(
                name="search_all_sources",
                description="Search multiple literature sources",
                input_types=["query", "sources", "limit"],
                output_types=["papers"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "default": 20}
                    },
                    "required": ["query"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "papers": {"type": "array"}
                    }
                }
            ),
            AgentCapability(
                name="analyze_papers",
                description="Analyze a set of papers for key findings",
                input_types=["pmids"],
                output_types=["analysis"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "pmids": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["pmids"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "analysis": {"type": "object"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "search_pubmed":
            return self._search_pubmed(task)
        elif task_type == "search_all_sources":
            return self._search_all_sources(task)
        elif task_type == "analyze_papers":
            return self._analyze_papers(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _search_pubmed(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.research import search_pubmed
        query = task.get("query", "")
        limit = task.get("limit", 10)
        return {"papers": search_pubmed(query, limit)}
    
    def _search_all_sources(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.research_analysis import search_all_sources
        query = task.get("query", "")
        sources = task.get("sources", ["pubmed", "europepmc", "crossref"])
        limit = task.get("limit", 20)
        return {"papers": search_all_sources(query, sources, limit)}
    
    def _analyze_papers(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.research_analysis import analyze_research_papers
        pmids = task.get("pmids", [])
        return {"analysis": analyze_research_papers(pmids)}


class DiseaseAnalysisAgent(BaseAgent):
    """Agent specialized in disease analysis."""
    
    def __init__(self):
        super().__init__("disease_analysis_agent", "Disease Analysis Agent",
                        "Specializes in disease-gene-pathway analysis and mechanism elucidation")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.DISEASE_ANALYSIS,
                description="Run comprehensive disease-gene-pathway analysis",
                input_types=["disease_name", "gene_symbols"],
                output_types=["analysis"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease_name": {"type": "string"},
                        "gene_symbols": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["disease_name"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "analysis": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="analyze_vcf",
                description="Analyze VCF file for disease associations",
                input_types=["vcf_path"],
                output_types=["analysis"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "vcf_path": {"type": "string"}
                    },
                    "required": ["vcf_path"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "analysis": {"type": "object"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "analyze_disease":
            return self._analyze_disease(task)
        elif task_type == "analyze_vcf":
            return self._analyze_vcf(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _analyze_disease(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.disease_gene_pathway import run_disease_gene_pathway_analysis
        disease_name = task.get("disease_name", "")
        gene_symbols = task.get("gene_symbols", [])
        result = run_disease_gene_pathway_analysis(disease_name, gene_symbols)
        return {"analysis": result.__dict__ if hasattr(result, '__dict__') else str(result)}
    
    def _analyze_vcf(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.disease_gene_pathway import run_vcf_analysis
        vcf_path = task.get("vcf_path", "")
        result = run_vcf_analysis(vcf_path)
        return {"analysis": result.__dict__ if hasattr(result, '__dict__') else str(result)}


class BiomarkerAgent(BaseAgent):
    """Agent specialized in biomarker discovery."""
    
    def __init__(self):
        super().__init__("biomarker_agent", "Biomarker Discovery Agent",
                        "Specializes in biomarker identification and validation")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.BIOMARKER_DISCOVERY,
                description="Run biomarker discovery analysis",
                input_types=["disease", "sample_type", "data_source"],
                output_types=["biomarkers"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease": {"type": "string"},
                        "sample_type": {"type": "string"},
                        "data_source": {"type": "string"}
                    },
                    "required": ["disease"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "biomarkers": {"type": "array"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "discover_biomarkers":
            return self._discover_biomarkers(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _discover_biomarkers(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.biomarker_discovery import run_biomarker_discovery
        disease = task.get("disease", "")
        sample_type = task.get("sample_type", "blood")
        data_source = task.get("data_source", "public")
        result = run_biomarker_discovery(disease, sample_type, data_source)
        return {"biomarkers": result.__dict__ if hasattr(result, '__dict__') else str(result)}


class DrugRepurposingAgent(BaseAgent):
    """Agent specialized in drug repurposing."""
    
    def __init__(self):
        super().__init__("drug_repurposing_agent", "Drug Repurposing Agent",
                        "Specializes in finding new uses for existing drugs")
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.DRUG_REPURPOSING,
                description="Find drug repurposing candidates for a disease/target",
                input_types=["disease", "target", "limit"],
                output_types=["candidates"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease": {"type": "string"},
                        "target": {"type": "string"},
                        "limit": {"type": "integer", "default": 20}
                    },
                    "required": ["disease"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "candidates": {"type": "array"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "find_repurposing_candidates":
            return self._find_repurposing_candidates(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _find_repurposing_candidates(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.drug_repurposing import find_repurposing_candidates
        disease = task.get("disease", "")
        target = task.get("target", "")
        limit = task.get("limit", 20)
        return {"candidates": find_repurposing_candidates(disease, target, limit)}


class WorkflowAgent(BaseAgent):
    """Agent that orchestrates complex multi-step workflows."""
    
    def __init__(self):
        super().__init__("workflow_agent", "Workflow Orchestration Agent",
                        "Orchestrates complex multi-step research workflows")
        self._sub_agents: dict[str, BaseAgent] = {}
    
    def register_sub_agent(self, agent: BaseAgent) -> None:
        self._sub_agents[agent.agent_id] = agent
    
    def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name=AgentCapability.WORKFLOW_ORCHESTRATION,
                description="Run integrated precision drug discovery workflow",
                input_types=["disease", "gene_symbols", "mutations"],
                output_types=["workflow_result"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "disease": {"type": "string"},
                        "gene_symbols": {"type": "array", "items": {"type": "string"}},
                        "mutations": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["disease"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "workflow_result": {"type": "object"}
                    }
                }
            ),
            AgentCapability(
                name="run_mutation_to_drug",
                description="Run mutation-to-drug discovery workflow",
                input_types=["mutations", "disease"],
                output_types=["workflow_result"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "mutations": {"type": "array", "items": {"type": "string"}},
                        "disease": {"type": "string"}
                    },
                    "required": ["mutations"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "workflow_result": {"type": "object"}
                    }
                }
            ),
        ]
    
    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = task.get("type", "")
        
        if task_type == "run_integrated_precision":
            return self._run_integrated_precision(task)
        elif task_type == "run_mutation_to_drug":
            return self._run_mutation_to_drug(task)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def _run_integrated_precision(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.integrated_precision import run_integrated_precision_drug_discovery
        disease = task.get("disease", "")
        gene_symbols = task.get("gene_symbols", [])
        mutations = task.get("mutations", [])
        result = run_integrated_precision_drug_discovery(disease, gene_symbols, mutations)
        return {"workflow_result": result.__dict__ if hasattr(result, '__dict__') else str(result)}
    
    def _run_mutation_to_drug(self, task: dict[str, Any]) -> dict[str, Any]:
        from geneai.ai_research_intelligence.mutation_to_drug_workflow import run_mutation_to_drug_workflow
        mutations = task.get("mutations", [])
        disease = task.get("disease", "")
        result = run_mutation_to_drug_workflow(mutations, disease)
        return {"workflow_result": result.__dict__ if hasattr(result, '__dict__') else str(result)}


def create_all_agents() -> list[BaseAgent]:
    """Create all specialized agents."""
    return [
        GeneAnalysisAgent(),
        ProteinAnalysisAgent(),
        DrugDiscoveryAgent(),
        ADMETAgent(),
        LiteratureAgent(),
        DiseaseAnalysisAgent(),
        BiomarkerAgent(),
        DrugRepurposingAgent(),
        WorkflowAgent(),
    ]


def register_all_agents(bus) -> list[BaseAgent]:
    """Register all agents with the message bus."""
    agents = create_all_agents()
    for agent in agents:
        bus.register_agent(agent)
    logger.info(f"Registered {len(agents)} agents")
    return agents