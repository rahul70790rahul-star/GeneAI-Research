"""Analysis tools for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
from typing import Any

from geneai.autonomous_agent.tools import Tool, ToolSpec, ToolParameter

logger = logging.getLogger(__name__)


class PathwayAnalysisTool(Tool):
    """Analyze pathway enrichment using Reactome and other databases."""

    def __init__(self):
        spec = ToolSpec(
            name="pathway_analysis",
            description="Perform pathway enrichment analysis for gene sets using Reactome, KEGG, and GO",
            category="analysis",
            parameters=[
                ToolParameter("genes", "array", "Gene symbols or IDs", required=True),
                ToolParameter("databases", "array", "Pathway databases", required=False, default=["reactome", "go"], enum=["reactome", "kegg", "go", "wikipathways", "pid"]),
                ToolParameter("organism", "string", "Organism", required=False, default="human", enum=["human", "mouse", "rat", "yeast"]),
                ToolParameter("pvalue_threshold", "number", "P-value threshold", required=False, default=0.05),
                ToolParameter("min_genes", "number", "Minimum genes in pathway", required=False, default=3),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        genes = kwargs.get("genes", [])
        if not genes:
            return {"error": "No genes provided"}

        databases = kwargs.get("databases", ["reactome", "go"])
        pvalue_threshold = kwargs.get("pvalue_threshold", 0.05)

        results = {
            "input_genes": genes,
            "databases": databases,
            "pathways": [],
            "go_terms": [],
            "summary": "",
        }

        # Reactome pathway analysis
        if "reactome" in databases:
            try:
                from geneai.drug_discovery.api_clients import analyze_reactome_pathways
                reactome_result = analyze_reactome_pathways(genes, limit=50)
                if reactome_result.get("pathways"):
                    for pw in reactome_result["pathways"]:
                        if pw.get("p_value") and pw["p_value"] <= pvalue_threshold:
                            results["pathways"].append({
                                "pathway_id": pw.get("pathway_id"),
                                "name": pw.get("name"),
                                "database": "Reactome",
                                "p_value": pw.get("p_value"),
                                "fdr": pw.get("fdr"),
                                "genes_in_pathway": pw.get("pathway_gene_total"),
                                "input_genes": pw.get("genes_found"),
                                "matched_genes": pw.get("entities_found", []),
                                "source_url": pw.get("source_url"),
                            })
            except Exception as exc:
                logger.warning("Reactome pathway analysis failed: %s", exc)
                results.setdefault("errors", {})["reactome"] = str(exc)

        # GO enrichment via QuickGO
        if "go" in databases:
            try:
                from geneai.drug_discovery.api_clients import search_uniprot_proteins, fetch_quickgo_annotations
                uniprot_result = search_uniprot_proteins(genes)
                accessions = [v["uniprot_id"] for v in uniprot_result.values() if v.get("uniprot_id")]
                if accessions:
                    go_annotations = fetch_quickgo_annotations(accessions, limit=500)
                    # Group by GO term and calculate enrichment
                    go_groups: dict[str, dict[str, Any]] = {}
                    for ann in go_annotations:
                        go_id = ann.get("go_id")
                        if not go_id:
                            continue
                        if go_id not in go_groups:
                            go_groups[go_id] = {
                                "go_id": go_id,
                                "name": ann.get("go_name"),
                                "ontology": ann.get("aspect"),
                                "genes": set(),
                                "evidence_codes": set(),
                            }
                        gene_sym = ann.get("gene_symbol")
                        if gene_sym:
                            go_groups[go_id]["genes"].add(gene_sym)
                        go_groups[go_id]["evidence_codes"].add(ann.get("evidence_code"))

                    # Simple enrichment: count genes per term
                    for go_id, data in go_groups.items():
                        if len(data["genes"]) >= kwargs.get("min_genes", 3):
                            results["go_terms"].append({
                                "go_id": go_id,
                                "name": data["name"],
                                "ontology": data["ontology"],
                                "genes": sorted(data["genes"]),
                                "gene_count": len(data["genes"]),
                                "evidence_codes": sorted(data["evidence_codes"]),
                            })
            except Exception as exc:
                logger.warning("GO enrichment failed: %s", exc)
                results.setdefault("errors", {})["go"] = str(exc)

        # KEGG would require separate implementation (no direct API in current codebase)
        if "kegg" in databases:
            results.setdefault("warnings", []).append(
                "KEGG pathway analysis not yet implemented; using Reactome/GO only"
            )

        total_pathways = len(results["pathways"]) + len(results["go_terms"])
        results["summary"] = f"Found {total_pathways} significantly enriched pathways/GO terms across {len(databases)} databases"

        return results


class GeneOntologyTool(Tool):
    """Gene Ontology enrichment analysis using QuickGO/UniProt."""

    def __init__(self):
        spec = ToolSpec(
            name="gene_ontology",
            description="Perform Gene Ontology (GO) enrichment analysis using UniProt and QuickGO",
            category="analysis",
            parameters=[
                ToolParameter("genes", "array", "Gene symbols or IDs", required=True),
                ToolParameter("ontology", "string", "GO ontology", required=False, default="all", enum=["BP", "MF", "CC", "all"]),
                ToolParameter("organism", "string", "Organism", required=False, default="human"),
                ToolParameter("pvalue_threshold", "number", "P-value threshold (informational; not calculated)", required=False, default=0.05),
                ToolParameter("min_genes", "number", "Minimum genes per GO term", required=False, default=3),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        genes = kwargs.get("genes", [])
        if not genes:
            return {"error": "No genes provided"}

        ontology_filter = kwargs.get("ontology", "all")
        min_genes = kwargs.get("min_genes", 3)

        try:
            from geneai.drug_discovery.api_clients import search_uniprot_proteins, fetch_quickgo_annotations
            uniprot_result = search_uniprot_proteins(genes)
            accessions = [v["uniprot_id"] for v in uniprot_result.values() if v.get("uniprot_id")]

            if not accessions:
                return {
                    "input_genes": genes,
                    "go_terms": [],
                    "warning": "No UniProt accessions found for input genes",
                }

            go_annotations = fetch_quickgo_annotations(accessions, limit=500)

            # Group by GO term
            go_groups: dict[str, dict[str, Any]] = {}
            for ann in go_annotations:
                go_id = ann.get("go_id")
                aspect = ann.get("aspect")
                if not go_id:
                    continue
                if ontology_filter != "all" and aspect != ontology_filter:
                    continue
                if go_id not in go_groups:
                    go_groups[go_id] = {
                        "go_id": go_id,
                        "name": ann.get("go_name"),
                        "ontology": aspect,
                        "genes": set(),
                        "evidence_codes": set(),
                        "references": set(),
                    }
                gene_sym = ann.get("gene_symbol")
                if gene_sym:
                    go_groups[go_id]["genes"].add(gene_sym)
                go_groups[go_id]["evidence_codes"].add(ann.get("evidence_code"))
                ref = ann.get("reference")
                if ref:
                    go_groups[go_id]["references"].add(ref)

            # Filter and format results
            go_terms = []
            for go_id, data in go_groups.items():
                if len(data["genes"]) >= min_genes:
                    go_terms.append({
                        "go_id": go_id,
                        "name": data["name"],
                        "ontology": data["ontology"],
                        "genes": sorted(data["genes"]),
                        "gene_count": len(data["genes"]),
                        "evidence_codes": sorted(data["evidence_codes"]),
                        "references": sorted(data["references"]),
                    })

            # Sort by gene count descending
            go_terms.sort(key=lambda x: x["gene_count"], reverse=True)

            return {
                "input_genes": genes,
                "go_terms": go_terms,
                "total_terms": len(go_terms),
                "note": "GO annotations from QuickGO (EBI); p-values not computed - use dedicated enrichment tools for statistical significance",
            }

        except Exception as exc:
            logger.error("GO analysis failed: %s", exc)
            return {
                "input_genes": genes,
                "error": str(exc),
                "go_terms": [],
            }


class ProteinInteractionTool(Tool):
    """Analyze protein-protein interactions using STRING database."""

    def __init__(self):
        spec = ToolSpec(
            name="protein_interactions",
            description="Find and analyze protein-protein interactions from STRING database",
            category="analysis",
            parameters=[
                ToolParameter("proteins", "array", "Protein identifiers (gene symbols, UniProt IDs)", required=True),
                ToolParameter("databases", "array", "Interaction databases", required=False, default=["string"], enum=["string", "biogrid", "intact", "mint"]),
                ToolParameter("score_threshold", "number", "Minimum interaction score (0-1)", required=False, default=0.4),
                ToolParameter("network_type", "string", "Network type", required=False, default="functional", enum=["functional", "physical"]),
                ToolParameter("limit", "number", "Maximum interactions", required=False, default=100),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        proteins = kwargs.get("proteins", [])
        if not proteins:
            return {"error": "No proteins provided"}

        score_threshold = kwargs.get("score_threshold", 0.4)
        network_type = kwargs.get("network_type", "functional")
        limit = kwargs.get("limit", 100)
        databases = kwargs.get("databases", ["string"])

        results = {
            "proteins": proteins,
            "interactions": [],
            "network_stats": {},
            "source": "STRING",
        }

        if "string" in databases:
            try:
                from geneai.drug_discovery.api_clients import fetch_string_interactions
                string_interactions = fetch_string_interactions(
                    proteins,
                    network_type=network_type,
                    required_score=int(score_threshold * 1000),
                    limit=limit,
                )
                # Filter by score
                filtered = [
                    i for i in string_interactions
                    if i.get("combined_score", 0) >= score_threshold
                ]
                results["interactions"] = filtered
                results["source"] = f"STRING {string_interactions[0].get('source', '').split()[-1] if string_interactions else 'unknown'}"
            except Exception as exc:
                logger.warning("STRING interaction fetch failed: %s", exc)
                results.setdefault("errors", {})["string"] = str(exc)

        # BioGRID, IntAct, MINT not yet implemented
        for db in databases:
            if db != "string":
                results.setdefault("warnings", []).append(
                    f"{db} interaction database not yet implemented"
                )

        # Calculate network stats
        if results["interactions"]:
            unique_proteins = set()
            for i in results["interactions"]:
                unique_proteins.add(i.get("protein_a", "").upper())
                unique_proteins.add(i.get("protein_b", "").upper())
            results["network_stats"] = {
                "nodes": len(unique_proteins),
                "edges": len(results["interactions"]),
                "avg_degree": len(results["interactions"]) * 2 / len(unique_proteins) if unique_proteins else 0,
                "density": 2 * len(results["interactions"]) / (len(unique_proteins) * (len(unique_proteins) - 1)) if len(unique_proteins) > 1 else 0,
            }

        return results


class ExpressionAnalysisTool(Tool):
    """Analyze gene expression data for differential expression (basic implementation)."""

    def __init__(self):
        spec = ToolSpec(
            name="expression_analysis",
            description="Analyze RNA-seq or microarray expression data for differential expression using basic statistical methods",
            category="analysis",
            parameters=[
                ToolParameter("expression_matrix", "object", "Gene expression matrix (genes x samples) as dict of dict or list of lists", required=True),
                ToolParameter("sample_groups", "object", "Sample to group mapping (dict: sample->group)", required=True),
                ToolParameter("contrast", "array", "Groups to compare [group1, group2]", required=True),
                ToolParameter("method", "string", "Statistical method", required=False, default="ttest", enum=["ttest", "mannwhitney", "wilcoxon"]),
                ToolParameter("fdr_threshold", "number", "FDR threshold (Benjamini-Hochberg)", required=False, default=0.05),
                ToolParameter("logfc_threshold", "number", "Log2 fold change threshold", required=False, default=1.0),
            ],
        )
        super().__init__(spec)

    def execute(self, **kwargs) -> dict[str, Any]:
        expression_matrix = kwargs.get("expression_matrix", {})
        sample_groups = kwargs.get("sample_groups", {})
        contrast = kwargs.get("contrast", ["treatment", "control"])
        method = kwargs.get("method", "ttest")
        fdr_threshold = kwargs.get("fdr_threshold", 0.05)
        logfc_threshold = kwargs.get("logfc_threshold", 1.0)

        if not expression_matrix or not sample_groups:
            return {"error": "Expression matrix and sample groups required"}

        if len(contrast) != 2:
            return {"error": "Contrast must have exactly 2 groups"}

        group1, group2 = contrast[0], contrast[1]

        # Validate groups exist
        samples_g1 = [s for s, g in sample_groups.items() if g == group1]
        samples_g2 = [s for s, g in sample_groups.items() if g == group2]

        if not samples_g1 or not samples_g2:
            return {"error": f"No samples found for one or both groups: {contrast}"}

        # Convert expression matrix to usable format
        # Expected: dict of {gene: {sample: value}} or list of lists with headers
        try:
            import numpy as np
            from scipy import stats
        except ImportError:
            return {"error": "scipy required for expression analysis; install scipy"}

        results = []

        for gene, values in expression_matrix.items():
            if isinstance(values, dict):
                vals_g1 = [values.get(s, np.nan) for s in samples_g1]
                vals_g2 = [values.get(s, np.nan) for s in samples_g2]
            elif isinstance(values, list):
                # Assume aligned with samples_g1 + samples_g2
                vals_g1 = values[:len(samples_g1)]
                vals_g2 = values[len(samples_g1):len(samples_g1)+len(samples_g2)]
            else:
                continue

            # Remove NaN
            vals_g1 = [v for v in vals_g1 if not np.isnan(v)]
            vals_g2 = [v for v in vals_g2 if not np.isnan(v)]

            if len(vals_g1) < 2 or len(vals_g2) < 2:
                continue

            # Calculate log2 fold change
            mean_g1 = np.mean(vals_g1)
            mean_g2 = np.mean(vals_g2)
            if mean_g2 == 0:
                logfc = np.inf if mean_g1 > 0 else -np.inf
            else:
                logfc = np.log2(mean_g1 / mean_g2)

            # Statistical test
            if method == "ttest":
                stat, pval = stats.ttest_ind(vals_g1, vals_g2, equal_var=False)
            elif method == "mannwhitney":
                stat, pval = stats.mannwhitneyu(vals_g1, vals_g2, alternative="two-sided")
            elif method == "wilcoxon":
                # Requires paired samples
                if len(vals_g1) == len(vals_g2):
                    stat, pval = stats.wilcoxon(vals_g1, vals_g2)
                else:
                    stat, pval = stats.mannwhitneyu(vals_g1, vals_g2, alternative="two-sided")
            else:
                stat, pval = stats.ttest_ind(vals_g1, vals_g2, equal_var=False)

            results.append({
                "gene": gene,
                "log2_fold_change": round(float(logfc), 4),
                "p_value": float(pval),
                "mean_group1": round(float(mean_g1), 4),
                "mean_group2": round(float(mean_g2), 4),
                "n_group1": len(vals_g1),
                "n_group2": len(vals_g2),
            })

        # Multiple testing correction (Benjamini-Hochberg)
        if results:
            pvals = [r["p_value"] for r in results]
            sorted_indices = np.argsort(pvals)
            n = len(pvals)
            for rank, idx in enumerate(sorted_indices, 1):
                results[idx]["padj"] = min(pvals[idx] * n / rank, 1.0)

        significant = [r for r in results if r.get("padj", 1) < fdr_threshold and abs(r.get("log2_fold_change", 0)) > logfc_threshold]

        return {
            "method": method,
            "contrast": contrast,
            "total_genes": len(results),
            "significant_genes": len(significant),
            "up_regulated": len([r for r in significant if r.get("log2_fold_change", 0) > 0]),
            "down_regulated": len([r for r in significant if r.get("log2_fold_change", 0) < 0]),
            "fdr_threshold": fdr_threshold,
            "logfc_threshold": logfc_threshold,
            "results": results,
        }


def register_analysis_tools(registry):
    """Register analysis tools."""
    registry.register(PathwayAnalysisTool())
    registry.register(GeneOntologyTool())
    registry.register(ProteinInteractionTool())
    registry.register(ExpressionAnalysisTool())