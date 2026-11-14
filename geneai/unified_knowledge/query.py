"""Query interface for Unified Knowledge Database - Phase 5.3."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from geneai.unified_knowledge.database import KnowledgeDatabase, get_knowledge_db

logger = logging.getLogger(__name__)


class QueryResult:
    """Result of a knowledge query.

    Accepts both the historical ``data/count/execution_time_ms`` keywords and
    the result envelope used by the query API (``results/total_count/page``).
    """

    def __init__(
        self,
        data: list[dict[str, Any]] | None = None,
        count: int | None = None,
        query: str = "",
        execution_time_ms: float = 0.0,
        *,
        results: list[dict[str, Any]] | None = None,
        total_count: int | None = None,
        query_time_ms: float | None = None,
        page: int = 1,
        page_size: int = 10,
        **_: Any,
    ):
        self.results = list(results if results is not None else (data or []))
        self.data = self.results
        self.total_count = int(
            total_count if total_count is not None else (count if count is not None else len(self.results))
        )
        self.count = self.total_count
        self.query = query
        self.query_time_ms = float(
            query_time_ms if query_time_ms is not None else execution_time_ms
        )
        self.execution_time_ms = self.query_time_ms
        self.page = max(1, int(page))
        self.page_size = max(1, int(page_size))

    @property
    def has_next_page(self) -> bool:
        return self.page * self.page_size < self.total_count

    @property
    def total_pages(self) -> int:
        return (self.total_count + self.page_size - 1) // self.page_size

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self):
        return iter(self.results)


class KnowledgeQuery:
    """High-level query interface for the unified knowledge database.

    A single instance doubles as a query specification (``query_type``,
    ``filters``, ``limit``, ``offset``) and as the executor bound to a database.
    """

    _TABLES = {
        "gene": "genes",
        "genes": "genes",
        "disease": "diseases",
        "diseases": "diseases",
        "protein": "proteins",
        "proteins": "proteins",
        "pathway": "pathways",
        "pathways": "pathways",
        "drug": "drugs",
        "drugs": "drugs",
        "variant": "variants",
        "variants": "variants",
        "literature": "literature",
        "publication": "literature",
        "publications": "literature",
    }

    def __init__(
        self,
        db: KnowledgeDatabase | None = None,
        query_type: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
    ):
        self.db = db or get_knowledge_db()
        self.query_type = query_type
        self.filters = dict(filters or {})
        self.limit = int(limit)
        self.offset = int(offset)
        self.order_by = order_by

    def execute_query(self, specification: "KnowledgeQuery") -> QueryResult:
        """Execute a declarative query specification."""
        import time

        start = time.perf_counter()
        query_type = (specification.query_type or "").lower()
        table = self._TABLES.get(query_type)
        if table is None:
            raise ValueError(f"Unsupported query_type: {specification.query_type!r}")

        schema = self.db.get_table_schema(table)
        where_parts: list[str] = []
        params: list[Any] = []
        for column, value in (specification.filters or {}).items():
            if column not in schema:
                raise ValueError(f"Unknown filter column {column!r} for {table}.")
            if value is None:
                where_parts.append(f"{column} IS NULL")
            else:
                where_parts.append(f"{column} = ?")
                params.append(value)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        limit = specification.limit if specification.limit and specification.limit > 0 else 100
        offset = max(0, specification.offset)
        order_column = specification.order_by if specification.order_by in schema else "id"
        rows = self.db.fetchall(
            f"SELECT * FROM {table}{where_sql} ORDER BY {order_column} LIMIT ? OFFSET ?",
            tuple(params + [limit, offset]),
        )
        total_row = self.db.fetchone(
            f"SELECT COUNT(*) AS c FROM {table}{where_sql}", tuple(params)
        )
        total = int(total_row["c"]) if total_row else len(rows)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return QueryResult(
            results=[dict(row) for row in rows],
            total_count=total,
            query=f"{query_type}:{specification.filters}",
            query_time_ms=elapsed_ms,
            page=offset // limit + 1,
            page_size=limit,
        )

    # Gene queries
    def get_gene(self, symbol: str) -> dict[str, Any] | None:
        """Get gene by symbol."""
        row = self.db.fetchone(
            "SELECT * FROM genes WHERE symbol = ?", (symbol.upper(),)
        )
        return dict(row) if row else None
    
    def search_genes(self, query: str, limit: int = 20) -> QueryResult:
        """Search genes by symbol or name."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            """SELECT * FROM genes 
               WHERE symbol LIKE ? OR name LIKE ? OR description LIKE ?
               LIMIT ?""",
            (search_term, search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_gene_diseases(self, gene_symbol: str) -> QueryResult:
        """Get diseases associated with a gene."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT d.name as disease_name, d.mondo_id, dga.association_type, 
                      dga.score, dga.source, dga.evidence, dga.pmid
               FROM disease_gene_associations dga
               JOIN diseases d ON dga.disease_id = d.id
               WHERE dga.gene_symbol = ?
               ORDER BY dga.score DESC""",
            (gene_symbol.upper(),)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"diseases_for_gene:{gene_symbol}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_gene_pathways(self, gene_symbol: str) -> QueryResult:
        """Get pathways a gene participates in."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT p.pathway_id, p.source, p.name, p.category, p.description
               FROM pathways p
               WHERE json_extract(p.genes, '$') LIKE ?
               ORDER BY p.source, p.name""",
            (f'%"{gene_symbol.upper()}"%',)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"pathways_for_gene:{gene_symbol}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_gene_proteins(self, gene_symbol: str) -> QueryResult:
        """Get proteins for a gene."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            "SELECT * FROM proteins WHERE gene_symbol = ?",
            (gene_symbol.upper(),)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"proteins_for_gene:{gene_symbol}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Disease queries
    def get_disease(self, mondo_id: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        """Get disease by MONDO ID or name."""
        if mondo_id:
            row = self.db.fetchone("SELECT * FROM diseases WHERE mondo_id = ?", (mondo_id,))
        elif name:
            row = self.db.fetchone("SELECT * FROM diseases WHERE name = ?", (name,))
        else:
            return None
        return dict(row) if row else None
    
    def search_diseases(self, query: str, limit: int = 20) -> QueryResult:
        """Search diseases by name."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            "SELECT * FROM diseases WHERE name LIKE ? OR synonyms LIKE ? LIMIT ?",
            (search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_disease_genes(self, disease_name: str, limit: int = 50) -> QueryResult:
        """Get genes associated with a disease."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT g.symbol, g.name, g.ensembl_id, dga.association_type, dga.score, dga.source
               FROM disease_gene_associations dga
               JOIN diseases d ON dga.disease_id = d.id
               JOIN genes g ON dga.gene_symbol = g.symbol
               WHERE d.name LIKE ?
               ORDER BY dga.score DESC
               LIMIT ?""",
            (f"%{disease_name}%", limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"genes_for_disease:{disease_name}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_disease_drugs(self, disease_name: str, limit: int = 50) -> QueryResult:
        """Get drugs for a disease."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT DISTINCT dr.name, dr.chembl_id, dr.max_phase, dr.mechanism_of_action
               FROM drugs dr
               JOIN drug_targets dt ON dr.id = dt.drug_id
               JOIN disease_gene_associations dga ON dt.target_uniprot IN (
                   SELECT uniprot_id FROM proteins WHERE gene_symbol = dga.gene_symbol
               )
               JOIN diseases d ON dga.disease_id = d.id
               WHERE d.name LIKE ?
               ORDER BY dr.max_phase DESC
               LIMIT ?""",
            (f"%{disease_name}%", limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"drugs_for_disease:{disease_name}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Protein queries
    def get_protein(self, uniprot_id: str) -> dict[str, Any] | None:
        """Get protein by UniProt ID."""
        row = self.db.fetchone("SELECT * FROM proteins WHERE uniprot_id = ?", (uniprot_id,))
        return dict(row) if row else None
    
    def search_proteins(self, query: str, limit: int = 20) -> QueryResult:
        """Search proteins by name or gene."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            """SELECT * FROM proteins 
               WHERE name LIKE ? OR gene_symbol LIKE ?
               LIMIT ?""",
            (search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_protein_interactions(self, uniprot_id: str, limit: int = 50) -> QueryResult:
        """Get protein-protein interactions."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT pi.*, p2.name as partner_name, p2.gene_symbol as partner_gene
               FROM protein_interactions pi
               JOIN proteins p2 ON pi.protein_b = p2.uniprot_id
               WHERE pi.protein_a = ?
               ORDER BY pi.confidence DESC
               LIMIT ?""",
            (uniprot_id, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"interactions_for:{uniprot_id}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Drug queries
    def get_drug(self, chembl_id: str | None = None, drugbank_id: str | None = None, 
                 pubchem_cid: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        """Get drug by various identifiers."""
        if chembl_id:
            row = self.db.fetchone("SELECT * FROM drugs WHERE chembl_id = ?", (chembl_id,))
        elif drugbank_id:
            row = self.db.fetchone("SELECT * FROM drugs WHERE drugbank_id = ?", (drugbank_id,))
        elif pubchem_cid:
            row = self.db.fetchone("SELECT * FROM drugs WHERE pubchem_cid = ?", (pubchem_cid,))
        elif name:
            row = self.db.fetchone("SELECT * FROM drugs WHERE name = ?", (name,))
        else:
            return None
        return dict(row) if row else None
    
    def search_drugs(self, query: str, limit: int = 20) -> QueryResult:
        """Search drugs by name or synonyms."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            """SELECT * FROM drugs 
               WHERE name LIKE ? OR synonyms LIKE ?
               LIMIT ?""",
            (search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_drug_targets(self, drug_identifier: str, limit: int = 50) -> QueryResult:
        """Get targets for a drug."""
        import time
        start = time.time()
        
        drug = self.get_drug(chembl_id=drug_identifier) or self.get_drug(name=drug_identifier)
        if not drug:
            return QueryResult(data=[], count=0, query=drug_identifier, execution_time_ms=0)
        
        rows = self.db.fetchall(
            """SELECT dt.*, p.name as protein_name, p.gene_symbol
               FROM drug_targets dt
               LEFT JOIN proteins p ON dt.target_uniprot = p.uniprot_id
               WHERE dt.drug_id = ?
               ORDER BY dt.confidence DESC
               LIMIT ?""",
            (drug['id'], limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"targets_for_drug:{drug_identifier}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_drugs_for_target(self, target_uniprot: str, limit: int = 50) -> QueryResult:
        """Get drugs targeting a protein."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            """SELECT dr.*, dt.action_type, dt.affinity_nM, dt.affinity_type, dt.confidence
               FROM drug_targets dt
               JOIN drugs dr ON dt.drug_id = dr.id
               WHERE dt.target_uniprot = ?
               ORDER BY dt.confidence DESC, dr.max_phase DESC
               LIMIT ?""",
            (target_uniprot, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"drugs_for_target:{target_uniprot}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Pathway queries
    def get_pathway(self, pathway_id: str, source: str | None = None) -> dict[str, Any] | None:
        """Get pathway by ID."""
        if source:
            row = self.db.fetchone("SELECT * FROM pathways WHERE pathway_id = ? AND source = ?", 
                                   (pathway_id, source))
        else:
            row = self.db.fetchone("SELECT * FROM pathways WHERE pathway_id = ?", (pathway_id,))
        return dict(row) if row else None
    
    def search_pathways(self, query: str, limit: int = 20) -> QueryResult:
        """Search pathways by name."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            "SELECT * FROM pathways WHERE name LIKE ? OR description LIKE ? LIMIT ?",
            (search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    def get_pathway_genes(self, pathway_id: str, source: str | None = None) -> list[str]:
        """Get genes in a pathway."""
        pathway = self.get_pathway(pathway_id, source)
        if not pathway:
            return []
        return json.loads(pathway['genes']) if pathway['genes'] else []
    
    # Variant queries
    def get_variant(self, variant_id: str) -> dict[str, Any] | None:
        """Get variant by ID."""
        row = self.db.fetchone("SELECT * FROM variants WHERE variant_id = ?", (variant_id,))
        return dict(row) if row else None
    
    def get_gene_variants(self, gene_symbol: str, limit: int = 100) -> QueryResult:
        """Get variants for a gene."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            "SELECT * FROM variants WHERE gene_symbol = ? ORDER BY pos LIMIT ?",
            (gene_symbol.upper(), limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"variants_for_gene:{gene_symbol}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Literature queries
    def get_publication(self, pmid: str) -> dict[str, Any] | None:
        """Get publication by PMID."""
        row = self.db.fetchone("SELECT * FROM literature WHERE pmid = ?", (pmid,))
        return dict(row) if row else None
    
    def search_literature(self, query: str, limit: int = 20) -> QueryResult:
        """Search literature."""
        import time
        start = time.time()
        
        search_term = f"%{query}%"
        rows = self.db.fetchall(
            """SELECT * FROM literature 
               WHERE title LIKE ? OR abstract LIKE ? OR mesh_terms LIKE ?
               ORDER BY year DESC
               LIMIT ?""",
            (search_term, search_term, search_term, limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=query,
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # ADMET queries
    def get_admet_predictions(self, smiles: str) -> list[dict[str, Any]]:
        """Get ADMET predictions for a compound."""
        rows = self.db.fetchall(
            "SELECT * FROM admet_predictions WHERE smiles = ?",
            (smiles,)
        )
        return [dict(r) for r in rows]
    
    # Biomarker queries
    def get_biomarkers_for_disease(self, disease: str, limit: int = 50) -> QueryResult:
        """Get biomarkers for a disease."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            "SELECT * FROM biomarkers WHERE disease LIKE ? ORDER BY auc DESC LIMIT ?",
            (f"%{disease}%", limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"biomarkers_for_disease:{disease}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Clinical trial queries
    def get_trials_for_condition(self, condition: str, limit: int = 50) -> QueryResult:
        """Get clinical trials for a condition."""
        import time
        start = time.time()
        
        rows = self.db.fetchall(
            "SELECT * FROM clinical_trials WHERE condition LIKE ? ORDER BY start_date DESC LIMIT ?",
            (f"%{condition}%", limit)
        )
        
        return QueryResult(
            data=[dict(r) for r in rows],
            count=len(rows),
            query=f"trials_for_condition:{condition}",
            execution_time_ms=(time.time() - start) * 1000
        )
    
    # Graph/Network queries
    def get_gene_network(self, gene_symbol: str, depth: int = 1) -> dict[str, Any]:
        """Get gene interaction network."""
        # Get direct interactions
        gene = self.get_gene(gene_symbol)
        if not gene:
            return {"nodes": [], "edges": []}
        
        # Get protein for gene
        proteins = self.get_gene_proteins(gene_symbol).data
        if not proteins:
            return {"nodes": [], "edges": []}
        
        uniprot_id = proteins[0]['uniprot_id']
        interactions = self.get_protein_interactions(uniprot_id, limit=20).data
        
        nodes = [{"id": uniprot_id, "label": gene_symbol, "type": "protein"}]
        edges = []
        
        for inter in interactions:
            partner = inter['partner_uniprot'] if 'partner_uniprot' in inter else inter.get('protein_b')
            partner_gene = inter.get('partner_gene', '')
            nodes.append({"id": partner, "label": partner_gene, "type": "protein"})
            edges.append({"source": uniprot_id, "target": partner, "confidence": inter.get('confidence', 0)})
        
        return {"nodes": nodes, "edges": edges}
    
    def get_drug_target_disease_path(self, drug_name: str, disease_name: str) -> list[dict[str, Any]]:
        """Find paths from drug to disease via targets."""
        drug = self.get_drug(name=drug_name)
        if not drug:
            return []
        
        targets = self.get_drug_targets(drug['chembl_id']).data
        paths = []
        
        for target in targets:
            uniprot = target['target_uniprot']
            gene_symbol = target.get('gene_symbol', '')
            
            # Check if target gene is associated with disease
            diseases = self.get_gene_diseases(gene_symbol).data
            for dis in diseases:
                if disease_name.lower() in dis['disease_name'].lower():
                    paths.append({
                        "drug": drug['name'],
                        "target": target['target_name'],
                        "gene": gene_symbol,
                        "disease": dis['disease_name'],
                        "association_type": dis['association_type'],
                        "score": dis['score']
                    })
        
        return paths
    
    # Statistics
    def get_database_stats(self) -> dict[str, int]:
        """Get database statistics."""
        return self.db.get_stats()


# Global query instance
_query: KnowledgeQuery | None = None


def get_knowledge_query(db: KnowledgeDatabase | None = None) -> KnowledgeQuery:
    """Get the global knowledge query engine, rebinding it to the active DB."""
    global _query
    current = db or get_knowledge_db()
    if _query is None:
        _query = KnowledgeQuery(current)
    else:
        _query.db = current
    return _query