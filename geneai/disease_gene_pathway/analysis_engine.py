"""Core analysis engine for disease-gene-pathway network analysis."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from geneai.disease_gene_pathway.api_clients import (
    DiseaseGeneAssociation,
    DisGeNETAssociation,
    GOAnnotation,
    KEGGPathway,
    PPIInteraction,
    ReactomePathway,
    UniProtEntry,
    fetch_disgenet_disease_genes,
    fetch_disgenet_gene_diseases,
    fetch_go_annotations,
    fetch_go_enrichment,
    fetch_kegg_pathways_for_genes,
    fetch_opentargets_disease_genes,
    fetch_opentargets_gene_diseases,
    fetch_opentargets_disease_genes,
    fetch_reactome_pathway_analysis,
    fetch_reactome_pathways_for_genes,
    fetch_string_enrichment,
    fetch_string_interactions,
    fetch_uniprot_entry,
    search_kegg_pathways,
    search_opentargets_diseases,
)
from geneai.drug_discovery.gene_identification import search_genes_by_disease as search_genes

logger = logging.getLogger(__name__)


@dataclass
class GeneNetworkNode:
    """Node in gene interaction network."""
    gene_symbol: str
    gene_id: str | None = None
    uniprot_id: str | None = None
    degree: int = 0
    betweenness_centrality: float = 0.0
    clustering_coefficient: float = 0.0
    is_hub: bool = False
    disease_associations: list[DiseaseGeneAssociation] = field(default_factory=list)
    go_terms: list[GOAnnotation] = field(default_factory=list)
    pathways: list[str] = field(default_factory=list)
    uniprot_entry: UniProtEntry | None = None


@dataclass
class GeneNetworkEdge:
    """Edge in gene interaction network."""
    source: str
    target: str
    weight: float
    interaction_types: list[str] = field(default_factory=list)
    combined_score: float = 0.0
    evidence_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class DiseaseGenePathwayResult:
    """Complete analysis result."""
    input_genes: list[str]
    input_diseases: list[str]
    gene_network: nx.Graph
    hub_genes: list[GeneNetworkNode]
    disease_gene_associations: list[DiseaseGeneAssociation]
    disgenet_associations: list[DisGeNETAssociation]
    kegg_pathways: list[KEGGPathway]
    reactome_pathways: list[ReactomePathway]
    go_enrichment: dict[str, list[dict[str, Any]]]  # aspect -> terms
    string_enrichment: list[dict[str, Any]]
    therapeutic_targets: list[dict[str, Any]]
    summary: dict[str, Any]


class DiseaseGenePathwayAnalyzer:
    """Main analyzer for disease-gene-pathway networks."""
    
    def __init__(
        self,
        min_string_score: float = 0.4,
        min_opentargets_score: float = 0.1,
        max_network_nodes: int = 500,
    ):
        self.min_string_score = min_string_score
        self.min_opentargets_score = min_opentargets_score
        self.max_network_nodes = max_network_nodes
    
    def analyze_genes(
        self,
        gene_symbols: list[str],
        diseases: list[str] | None = None,
        include_ppi: bool = True,
        include_pathways: bool = True,
        include_go: bool = True,
        include_disgenet: bool = True,
    ) -> DiseaseGenePathwayResult:
        """Analyze a set of genes for disease associations, pathways, and networks."""
        logger.info("Analyzing %d genes", len(gene_symbols))
        
        # Deduplicate and validate genes
        genes = list(dict.fromkeys([g.strip().upper() for g in gene_symbols if g.strip()]))
        
        # Fetch disease-gene associations
        disease_gene_associations = []
        disgenet_associations = []
        
        for gene in genes:
            # OpenTargets
            ot_assocs = fetch_opentargets_gene_diseases(gene, min_score=self.min_opentargets_score)
            disease_gene_associations.extend(ot_assocs)
            
            # DisGeNET
            if include_disgenet:
                dg_assocs = fetch_disgenet_gene_diseases(gene)
                disgenet_associations.extend(dg_assocs)
        
        # If diseases provided, also fetch genes for those diseases
        if diseases:
            for disease in diseases:
                ot_assocs = fetch_opentargets_disease_genes(disease, min_score=self.min_opentargets_score)
                disease_gene_associations.extend(ot_assocs)
                if include_disgenet:
                    dg_assocs = fetch_disgenet_disease_genes(disease)
                    disgenet_associations.extend(dg_assocs)
        
        # Build PPI network
        ppi_interactions = []
        if include_ppi and genes:
            ppi_interactions = fetch_string_interactions(
                genes,
                min_score=self.min_string_score,
                limit=self.max_network_nodes * 2,
            )
        
        # Create network graph
        gene_network = self._build_network(genes, ppi_interactions)
        
        # Identify hub genes
        hub_genes = self._identify_hubs(gene_network, genes, disease_gene_associations)
        
        # Pathway analysis
        kegg_pathways = []
        reactome_pathways = []
        if include_pathways and genes:
            kegg_pathways = fetch_kegg_pathways_for_genes(genes)
            reactome_pathways = fetch_reactome_pathways_for_genes(genes)
        
        # GO enrichment
        go_enrichment = {"P": [], "F": [], "C": []}
        if include_go and genes:
            for aspect in ["P", "F", "C"]:
                go_enrichment[aspect] = fetch_go_enrichment(genes, go_aspect=aspect)
        
        # STRING enrichment
        string_enrichment = []
        if include_ppi and genes:
            string_enrichment = fetch_string_enrichment(genes)
        
        # Reactome pathway enrichment analysis
        reactome_enrichment = []
        if include_pathways and genes:
            reactome_enrichment = fetch_reactome_pathway_analysis(genes)
        
        # Identify therapeutic targets
        therapeutic_targets = self._identify_therapeutic_targets(
            hub_genes, disease_gene_associations, kegg_pathways, reactome_pathways
        )
        
        # Build summary
        summary = {
            "total_input_genes": len(genes),
            "network_nodes": gene_network.number_of_nodes(),
            "network_edges": gene_network.number_of_edges(),
            "hub_genes_count": len(hub_genes),
            "disease_associations_count": len(disease_gene_associations),
            "disgenet_associations_count": len(disgenet_associations),
            "kegg_pathways_count": len(kegg_pathways),
            "reactome_pathways_count": len(reactome_pathways),
            "go_terms_enriched": sum(len(v) for v in go_enrichment.values()),
            "string_enrichment_terms": len(string_enrichment),
            "reactome_enriched_pathways": len(reactome_enrichment),
            "therapeutic_targets_count": len(therapeutic_targets),
        }
        
        return DiseaseGenePathwayResult(
            input_genes=genes,
            input_diseases=diseases or [],
            gene_network=gene_network,
            hub_genes=hub_genes,
            disease_gene_associations=disease_gene_associations,
            disgenet_associations=disgenet_associations,
            kegg_pathways=kegg_pathways,
            reactome_pathways=reactome_pathways,
            go_enrichment=go_enrichment,
            string_enrichment=string_enrichment,
            therapeutic_targets=therapeutic_targets,
            summary=summary,
        )
    
    def analyze_vcf_variants(
        self,
        variants: list[dict[str, Any]],
        diseases: list[str] | None = None,
    ) -> DiseaseGenePathwayResult:
        """Analyze genes from VCF variants."""
        # Extract gene symbols from variants
        gene_symbols = []
        for var in variants:
            gene = var.get("gene") or var.get("GENE") or var.get("SYMBOL")
            if gene:
                gene_symbols.append(gene)
        
        return self.analyze_genes(gene_symbols, diseases)
    
    def _build_network(
        self,
        genes: list[str],
        ppi_interactions: list[PPIInteraction],
    ) -> nx.Graph:
        """Build gene interaction network."""
        G = nx.Graph()
        
        # Add all input genes as nodes
        for gene in genes:
            G.add_node(gene, is_input=True)
        
        # Add PPI interactions
        for ppi in ppi_interactions:
            # Use gene symbols if available, otherwise protein IDs
            source = ppi.protein1
            target = ppi.protein2
            
            # Only add if both nodes are in our gene set or we're expanding
            if source in G or target in G or G.number_of_nodes() < self.max_network_nodes:
                G.add_edge(
                    source,
                    target,
                    weight=ppi.combined_score,
                    combined_score=ppi.combined_score,
                    experimental_score=ppi.experimental_score,
                    database_score=ppi.database_score,
                    textmining_score=ppi.textmining_score,
                    cooccurrence_score=ppi.cooccurrence_score,
                    coexpression_score=ppi.coexpression_score,
                    neighborhood_score=ppi.neighborhood_score,
                    fusion_score=ppi.fusion_score,
                    evidence_types=[
                        k for k, v in {
                            "experimental": ppi.experimental,
                            "database": ppi.database,
                            "textmining": ppi.textmining,
                            "cooccurrence": ppi.cooccurrence,
                            "coexpression": ppi.coexpression,
                            "neighborhood": ppi.neighborhood,
                            "fusion": ppi.fusion,
                        }.items() if v
                    ],
                )
        
        return G
    
    def _identify_hubs(
        self,
        network: nx.Graph,
        input_genes: list[str],
        disease_associations: list[DiseaseGeneAssociation],
    ) -> list[GeneNetworkNode]:
        """Identify hub genes in the network."""
        if network.number_of_nodes() == 0:
            return []
        
        # Calculate centrality measures
        try:
            degree_cent = nx.degree_centrality(network)
            betweenness_cent = nx.betweenness_centrality(network, k=min(100, network.number_of_nodes()))
            clustering = nx.clustering(network)
        except Exception:
            degree_cent = {n: network.degree(n) / max(1, network.number_of_nodes() - 1) for n in network.nodes()}
            betweenness_cent = {n: 0.0 for n in network.nodes()}
            clustering = {n: 0.0 for n in network.nodes()}
        
        # Get disease associations per gene
        gene_diseases: dict[str, list[DiseaseGeneAssociation]] = {}
        for assoc in disease_associations:
            gene_diseases.setdefault(assoc.gene_symbol, []).append(assoc)
        
        # Build hub gene nodes
        hub_nodes = []
        for gene in network.nodes():
            degree = network.degree(gene)
            
            # Determine if hub (top 20% by degree or high betweenness)
            degree_threshold = sorted(degree_cent.values())[int(0.8 * len(degree_cent))] if degree_cent else 0
            betweenness_threshold = sorted(betweenness_cent.values())[int(0.8 * len(betweenness_cent))] if betweenness_cent else 0
            
            is_hub = (
                degree_cent.get(gene, 0) >= degree_threshold or
                betweenness_cent.get(gene, 0) >= betweenness_threshold or
                gene in input_genes
            )
            
            # Fetch UniProt entry for additional info
            uniprot_entry = fetch_uniprot_entry(gene)
            
            hub_nodes.append(GeneNetworkNode(
                gene_symbol=gene,
                gene_id=uniprot_entry.uniprot_id if uniprot_entry else None,
                uniprot_id=uniprot_entry.uniprot_id if uniprot_entry else None,
                degree=degree,
                betweenness_centrality=betweenness_cent.get(gene, 0.0),
                clustering_coefficient=clustering.get(gene, 0.0),
                is_hub=is_hub,
                disease_associations=gene_diseases.get(gene, []),
                go_terms=fetch_go_annotations(gene) if is_hub else [],
                pathways=uniprot_entry.pathways if uniprot_entry else [],
                uniprot_entry=uniprot_entry,
            ))
        
        # Sort by hub status and degree
        hub_nodes.sort(key=lambda x: (not x.is_hub, -x.degree))
        
        return hub_nodes
    
    def _identify_therapeutic_targets(
        self,
        hub_genes: list[GeneNetworkNode],
        disease_associations: list[DiseaseGeneAssociation],
        kegg_pathways: list[KEGGPathway],
        reactome_pathways: list[ReactomePathway],
    ) -> list[dict[str, Any]]:
        """Identify potential therapeutic targets."""
        targets = []
        
        # Score each hub gene
        for hub in hub_genes:
            if not hub.is_hub:
                continue
            
            score = 0.0
            reasons = []
            
            # Network centrality
            score += hub.betweenness_centrality * 2.0
            if hub.betweenness_centrality > 0.1:
                reasons.append(f"High betweenness centrality ({hub.betweenness_centrality:.3f})")
            
            score += hub.degree * 0.1
            if hub.degree > 10:
                reasons.append(f"High connectivity ({hub.degree} interactions)")
            
            # Disease associations
            disease_count = len(hub.disease_associations)
            score += disease_count * 0.5
            if disease_count > 0:
                diseases = list(set(a.disease_name for a in hub.disease_associations))
                reasons.append(f"Associated with {disease_count} diseases: {', '.join(diseases[:3])}")
            
            # Pathway involvement
            pathway_count = len(kegg_pathways) + len(reactome_pathways)
            score += min(pathway_count, 10) * 0.3
            if pathway_count > 0:
                reasons.append(f"Involved in {pathway_count} pathways")
            
            # Drug target potential (from UniProt)
            if hub.uniprot_entry:
                # Check if known drug target
                pass
            
            targets.append({
                "gene_symbol": hub.gene_symbol,
                "uniprot_id": hub.uniprot_id,
                "score": round(score, 3),
                "reasons": reasons,
                "degree": hub.degree,
                "betweenness": hub.betweenness_centrality,
                "disease_count": disease_count,
                "pathway_count": pathway_count,
                "is_hub": hub.is_hub,
            })
        
        # Sort by score
        targets.sort(key=lambda x: x["score"], reverse=True)
        
        return targets[:50]


def run_disease_gene_pathway_analysis(
    gene_symbols: list[str],
    diseases: list[str] | None = None,
    **kwargs: Any,
) -> DiseaseGenePathwayResult:
    """Convenience function to run the full analysis."""
    if diseases is None and "disease_names" in kwargs:
        diseases = kwargs.pop("disease_names")
    analyzer = DiseaseGenePathwayAnalyzer(**kwargs)
    return analyzer.analyze_genes(gene_symbols, diseases)


def run_vcf_analysis(
    variants: list[dict[str, Any]],
    diseases: list[str] | None = None,
    **kwargs: Any,
) -> DiseaseGenePathwayResult:
    """Convenience function to run VCF-based analysis."""
    analyzer = DiseaseGenePathwayAnalyzer(**kwargs)
    return analyzer.analyze_vcf_variants(variants, diseases)