"""Data loaders for Unified Knowledge Database - Phase 5.3."""
from __future__ import annotations

import gzip
import json
import logging
import requests
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from geneai.unified_knowledge.database import KnowledgeDatabase, get_knowledge_db

logger = logging.getLogger(__name__)


@dataclass
class LoadStats:
    """Statistics for a data load operation."""

    source: str
    records_processed: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    errors: int = 0
    duration_seconds: float = 0.0

    @property
    def total(self) -> int:
        return self.records_processed

    @property
    def inserted(self) -> int:
        return self.records_inserted

    @property
    def updated(self) -> int:
        return self.records_updated

    @property
    def failed(self) -> int:
        return self.errors


class BaseLoader:
    """Base class for data loaders."""
    
    def __init__(self, db: KnowledgeDatabase | None = None):
        self.db = db or get_knowledge_db()
        self.stats = LoadStats(source=self.__class__.__name__)

    @staticmethod
    def _items(payload: Any, *keys: str) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _clean(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        """Keep only columns that exist in ``table`` and serialise structured values."""
        columns = set(self.db.get_table_schema(table))
        cleaned = {}
        for key, value in row.items():
            if key not in columns:
                continue
            if isinstance(value, (list, dict, tuple)):
                value = json.dumps(value, default=str)
            cleaned[key] = value
        return cleaned
    
    def load(self, *args, **kwargs) -> LoadStats:
        """Load data into database."""
        start = time.time()
        try:
            self._load(*args, **kwargs)
        except Exception as exc:
            logger.error("%s load failed: %s", self.__class__.__name__, exc)
            self.stats.errors += 1
        finally:
            self.stats.duration_seconds = time.time() - start
        return self.stats
    
    def _load(self, *args, **kwargs) -> None:
        """Override in subclass. The base loader accepts and ignores input."""
        return None


class GeneLoader(BaseLoader):
    """Load gene data from various sources."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "genes", "gene"):
            self.stats.records_processed += 1
            try:
                if self.db.insert_gene(item):
                    self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Gene loader skipped %s: %s", item.get("symbol"), exc)
                self.stats.errors += 1
    
    def load_from_ensembl(self, species: str = "homo_sapiens", limit: int = 0) -> LoadStats:
        """Load genes from Ensembl BioMart (via REST API)."""
        url = f"https://rest.ensembl.org/biomart/martservice?query="
        # This would require constructing a proper BioMart query
        # For now, placeholder
        logger.info("Ensembl loading not fully implemented")
        return self.stats
    
    def load_from_hgnc(self, filepath: str | Path) -> LoadStats:
        """Load genes from HGNC complete set (TSV)."""
        import csv
        
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"HGNC file not found: {filepath}")
        
        rows = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                symbol = row.get('symbol', '').strip()
                if not symbol:
                    continue
                
                data = {
                    'symbol': symbol,
                    'ensembl_id': row.get('ensembl_gene_id', '').strip() or None,
                    'entrez_id': row.get('entrez_id', '').strip() or None,
                    'name': row.get('name', '').strip() or None,
                    'description': row.get('description', '').strip() or None,
                    'chromosome': row.get('chromosome', '').strip() or None,
                    'start_pos': int(row['start']) if row.get('start', '').strip().isdigit() else None,
                    'end_pos': int(row['end']) if row.get('end', '').strip().isdigit() else None,
                    'strand': row.get('strand', '').strip() or None,
                    'biotype': row.get('locus_type', '').strip() or None,
                    'aliases': json.dumps([
                        a.strip() for a in row.get('alias_symbol', '').split('|') if a.strip()
                    ]) if row.get('alias_symbol') else '[]',
                }
                rows.append(data)
                self.stats.records_processed += 1
        
        if rows:
            self.stats.records_inserted = self.db.bulk_insert('genes', rows)
        
        logger.info(f"Loaded {self.stats.records_inserted} genes from HGNC")
        return self.stats
    
    def load_from_opentargets(self, limit: int = 10000) -> LoadStats:
        """Load gene data from OpenTargets."""
        # OpenTargets GraphQL API
        query = """
        query GetGenes($limit: Int!) {
            genes(limit: $limit) {
                rows {
                    id
                    approvedSymbol
                    approvedName
                    biotype
                    chromosome
                    start
                    end
                    strand
                    uniprotIds
                }
            }
        }
        """
        try:
            response = requests.post(
                "https://api.platform.opentargets.org/api/v4/graphql",
                json={"query": query, "variables": {"limit": limit}},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            rows = []
            for gene in data.get('data', {}).get('genes', {}).get('rows', []):
                rows.append({
                    'symbol': gene.get('approvedSymbol', ''),
                    'ensembl_id': gene.get('id', ''),
                    'name': gene.get('approvedName', ''),
                    'biotype': gene.get('biotype', ''),
                    'chromosome': gene.get('chromosome', ''),
                    'start_pos': gene.get('start'),
                    'end_pos': gene.get('end'),
                    'strand': gene.get('strand'),
                    'uniprot_ids': json.dumps(gene.get('uniprotIds', [])),
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('genes', rows)
            
        except Exception as e:
            logger.error(f"Failed to load from OpenTargets: {e}")
            self.stats.errors += 1
        
        return self.stats


class DiseaseLoader(BaseLoader):
    """Load disease data from various sources."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "diseases", "disease"):
            self.stats.records_processed += 1
            try:
                if self.db.insert_disease(item):
                    self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Disease loader skipped %s: %s", item.get("name"), exc)
                self.stats.errors += 1
    
    def load_from_mondo(self, filepath: str | Path) -> LoadStats:
        """Load diseases from MONDO OBO/JSON."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"MONDO file not found: {filepath}")
        
        # Parse OBO format or JSON
        if path.suffix == '.json':
            with open(path) as f:
                data = json.load(f)
            # Parse MONDO JSON structure
            graphs = data.get('graphs', [])
            for graph in graphs:
                for node in graph.get('nodes', []):
                    if 'MONDO_' in node.get('id', ''):
                        mondo_id = node['id'].split('/')[-1].replace('_', ':')
                        self._process_mondo_node(node, mondo_id)
        else:
            # OBO format
            self._parse_obo(path)
        
        return self.stats
    
    def _process_mondo_node(self, node: dict, mondo_id: str) -> None:
        """Process a MONDO node."""
        name = node.get('lbl', '')
        description = node.get('meta', {}).get('definition', {}).get('val', '')
        synonyms = [s.get('val', '') for s in node.get('meta', {}).get('synonyms', [])]
        
        self.db.upsert('diseases', {
            'name': name,
            'mondo_id': mondo_id,
            'description': description,
            'synonyms': json.dumps(synonyms),
        }, ['mondo_id'])
        
        self.stats.records_processed += 1
        self.stats.records_inserted += 1
    
    def _parse_obo(self, path: Path) -> None:
        """Parse OBO format file."""
        current_term = {}
        in_term = False
        
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line == '[Term]':
                    if current_term:
                        self._process_obo_term(current_term)
                    current_term = {}
                    in_term = True
                elif line == '[Typedef]':
                    if current_term:
                        self._process_obo_term(current_term)
                    current_term = {}
                    in_term = False
                elif in_term and ':' in line:
                    key, value = line.split(':', 1)
                    current_term[key.strip()] = value.strip()
        
        if current_term:
            self._process_obo_term(current_term)
    
    def _process_obo_term(self, term: dict) -> None:
        """Process an OBO term."""
        if 'id' not in term or 'MONDO' not in term['id']:
            return
        
        mondo_id = term['id']
        name = term.get('name', '')
        definition = term.get('def', '').split('"')[1] if 'def' in term and '"' in term['def'] else ''
        synonyms = []
        for key, value in term.items():
            if key == 'synonym':
                synonyms.append(value.split('"')[1] if '"' in value else value)
        
        self.db.upsert('diseases', {
            'name': name,
            'mondo_id': mondo_id,
            'description': definition,
            'synonyms': json.dumps(synonyms),
        }, ['mondo_id'])
        
        self.stats.records_processed += 1
        self.stats.records_inserted += 1


class ProteinLoader(BaseLoader):
    """Load protein data from UniProt."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "proteins", "protein"):
            self.stats.records_processed += 1
            try:
                if self.db.insert_protein(item):
                    self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Protein loader skipped %s: %s", item.get("uniprot_id"), exc)
                self.stats.errors += 1
    
    def load_from_uniprot(self, uniprot_ids: list[str], batch_size: int = 100) -> LoadStats:
        """Load proteins from UniProt REST API."""
        for i in range(0, len(uniprot_ids), batch_size):
            batch = uniprot_ids[i:i+batch_size]
            self._fetch_batch(batch)
            time.sleep(0.1)  # Rate limiting
        return self.stats
    
    def _fetch_batch(self, uniprot_ids: list[str]) -> None:
        """Fetch a batch of proteins from UniProt."""
        ids_str = ','.join(uniprot_ids)
        url = f"https://rest.uniprot.org/uniprotkb/accessions?accessions={ids_str}&format=json"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            rows = []
            for entry in data.get('results', []):
                self.stats.records_processed += 1
                
                # Extract data
                uniprot_id = entry.get('primaryAccession', '')
                gene_names = entry.get('genes', [])
                gene_symbol = gene_names[0].get('geneName', {}).get('value', '') if gene_names else ''
                
                protein_name = entry.get('proteinDescription', {}).get('recommendedName', {}).get('fullName', {}).get('value', '')
                sequence = entry.get('sequence', {}).get('value', '')
                length = entry.get('sequence', {}).get('length', 0)
                mass = entry.get('sequence', {}).get('molWeight', 0)
                
                # Function
                functions = []
                for comment in entry.get('comments', []):
                    if comment.get('commentType') == 'FUNCTION':
                        for text in comment.get('texts', []):
                            functions.append(text.get('value', ''))
                
                # Subcellular location
                locations = []
                for comment in entry.get('comments', []):
                    if comment.get('commentType') == 'SUBCELLULAR_LOCATION':
                        for loc in comment.get('subcellularLocations', []):
                            locations.append(loc.get('location', {}).get('value', ''))
                
                # Domains
                domains = []
                for feature in entry.get('features', []):
                    if feature.get('type') == 'Domain':
                        domains.append({
                            'name': feature.get('description', ''),
                            'start': feature.get('location', {}).get('start', {}).get('value'),
                            'end': feature.get('location', {}).get('end', {}).get('value'),
                        })
                
                # PDB IDs
                pdb_ids = []
                for db_ref in entry.get('uniProtKBCrossReferences', []):
                    if db_ref.get('database') == 'PDB':
                        pdb_ids.append(db_ref.get('id', ''))
                
                rows.append({
                    'uniprot_id': uniprot_id,
                    'gene_symbol': gene_symbol,
                    'name': protein_name,
                    'sequence': sequence,
                    'length': length,
                    'mass': mass,
                    'function': '; '.join(functions),
                    'subcellular_location': '; '.join(locations),
                    'domains': json.dumps(domains),
                    'pdb_ids': json.dumps(pdb_ids),
                })
            
            if rows:
                self.stats.records_inserted += self.db.bulk_insert('proteins', rows)
                
        except Exception as e:
            logger.error(f"Failed to fetch UniProt batch: {e}")
            self.stats.errors += 1


class PathwayLoader(BaseLoader):
    """Load pathway data from KEGG, Reactome, WikiPathways."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "pathways", "pathway"):
            self.stats.records_processed += 1
            row = dict(item)
            pathway_id = (
                row.get("pathway_id")
                or row.get("reactome_id")
                or row.get("kegg_id")
                or row.get("name")
            )
            if not pathway_id:
                self.stats.errors += 1
                continue
            row["pathway_id"] = str(pathway_id)
            row.setdefault(
                "source", "Reactome" if row.get("reactome_id") else ("KEGG" if row.get("kegg_id") else "manual")
            )
            try:
                self.db.upsert("pathways", self._clean("pathways", row), ["pathway_id"])
                self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Pathway loader skipped %s: %s", pathway_id, exc)
                self.stats.errors += 1
    
    def load_from_kegg(self) -> LoadStats:
        """Load pathways from KEGG REST API."""
        # Get pathway list for human
        url = "https://rest.kegg.jp/list/pathway/hsa"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            rows = []
            for line in response.text.strip().split('\n'):
                if not line:
                    continue
                pathway_id, name = line.split('\t', 1)
                pathway_id = pathway_id.replace('path:', '')
                
                # Get pathway details
                detail_url = f"https://rest.kegg.jp/get/{pathway_id}"
                detail_resp = requests.get(detail_url, timeout=30)
                
                genes = []
                description = ""
                for detail_line in detail_resp.text.split('\n'):
                    if detail_line.startswith('DESCRIPTION'):
                        description = detail_line.split('  ')[-1]
                    elif detail_line.startswith('GENE'):
                        parts = detail_line.split()
                        if len(parts) >= 2:
                            gene_id = parts[1]
                            genes.append(gene_id)
                
                rows.append({
                    'pathway_id': pathway_id,
                    'source': 'KEGG',
                    'name': name,
                    'description': description,
                    'category': 'metabolic' if 'Metabolism' in name else 'signaling',
                    'genes': json.dumps(genes),
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('pathways', rows)
                
        except Exception as e:
            logger.error(f"Failed to load KEGG pathways: {e}")
            self.stats.errors += 1
        
        return self.stats
    
    def load_from_reactome(self) -> LoadStats:
        """Load pathways from Reactome."""
        url = "https://reactome.org/ContentService/data/pathways/top/human"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            rows = []
            for pathway in data:
                pathway_id = pathway.get('stId', '')
                name = pathway.get('displayName', '')
                
                # Get genes for this pathway
                genes_url = f"https://reactome.org/ContentService/data/query/enhanced/participatingMolecules/{pathway_id}"
                genes_resp = requests.get(genes_url, timeout=30)
                genes_data = genes_resp.json() if genes_resp.ok else {}
                
                genes = []
                for mol in genes_data.get('rows', []):
                    gene_name = mol.get('geneName', '')
                    if gene_name:
                        genes.append(gene_name)
                
                rows.append({
                    'pathway_id': pathway_id,
                    'source': 'Reactome',
                    'name': name,
                    'description': '',
                    'category': 'signaling',
                    'genes': json.dumps(genes),
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('pathways', rows)
                
        except Exception as e:
            logger.error(f"Failed to load Reactome pathways: {e}")
            self.stats.errors += 1
        
        return self.stats


class DrugLoader(BaseLoader):
    """Load drug data from ChEMBL, DrugBank, PubChem."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "drugs", "drug"):
            self.stats.records_processed += 1
            row = dict(item)
            if not row.get("name") and row.get("drug_name"):
                row["name"] = row["drug_name"]
            if not row.get("name"):
                self.stats.errors += 1
                continue
            cleaned = self._clean("drugs", row)
            try:
                conflict = "chembl_id" if cleaned.get("chembl_id") else ""
                if conflict:
                    self.db.upsert("drugs", cleaned, [conflict])
                else:
                    self.db.insert("drugs", cleaned)
                self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Drug loader skipped %s: %s", row.get("name"), exc)
                self.stats.errors += 1
    
    def load_from_chembl(self, limit: int = 10000) -> LoadStats:
        """Load drugs from ChEMBL."""
        url = f"https://www.ebi.ac.uk/chembl/api/data/drug.json?limit={limit}"
        
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            rows = []
            for drug in data.get('drugs', []):
                chembl_id = drug.get('drug', {}).get('chembl_id', '')
                if not chembl_id:
                    continue
                
                rows.append({
                    'chembl_id': chembl_id,
                    'name': drug.get('drug', {}).get('pref_name', ''),
                    'synonyms': json.dumps(drug.get('drug', {}).get('synonyms', [])),
                    'smiles': drug.get('drug', {}).get('molecule_structures', {}).get('canonical_smiles', ''),
                    'inchi': drug.get('drug', {}).get('molecule_structures', {}).get('standard_inchi', ''),
                    'inchikey': drug.get('drug', {}).get('molecule_structures', {}).get('standard_inchi_key', ''),
                    'molecular_formula': drug.get('drug', {}).get('molecule_properties', {}).get('molecular_formula', ''),
                    'molecular_weight': drug.get('drug', {}).get('molecule_properties', {}).get('full_mwt', 0),
                    'max_phase': drug.get('drug', {}).get('max_phase', 0),
                    'therapeutic_area': drug.get('drug', {}).get('therapeutic_area', ''),
                    'mechanism_of_action': drug.get('drug', {}).get('mechanism_of_action', ''),
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('drugs', rows)
                
        except Exception as e:
            logger.error(f"Failed to load ChEMBL drugs: {e}")
            self.stats.errors += 1
        
        return self.stats
    
    def load_drug_targets_from_chembl(self, limit: int = 50000) -> LoadStats:
        """Load drug-target interactions from ChEMBL."""
        url = f"https://www.ebi.ac.uk/chembl/api/data/activity.json?limit={limit}&standard_type=Ki,Kd,IC50,EC50"
        
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            # First, ensure drugs exist in database
            drug_map = {}  # chembl_id -> db id
            for drug in self.db.fetchall("SELECT id, chembl_id FROM drugs WHERE chembl_id IS NOT NULL"):
                drug_map[drug['chembl_id']] = drug['id']
            
            rows = []
            for activity in data.get('activities', []):
                drug_chembl = activity.get('drug', {}).get('chembl_id', '')
                target_chembl = activity.get('target', {}).get('chembl_id', '')
                
                if drug_chembl not in drug_map:
                    continue
                
                drug_id = drug_map[drug_chembl]
                
                # Get target UniProt ID
                target_uniprot = self._get_uniprot_from_chembl_target(target_chembl)
                if not target_uniprot:
                    continue
                
                rows.append({
                    'drug_id': drug_id,
                    'target_uniprot': target_uniprot,
                    'target_name': activity.get('target', {}).get('pref_name', ''),
                    'action_type': activity.get('standard_type', ''),
                    'affinity_nM': activity.get('standard_value', 0) if activity.get('standard_value') else None,
                    'affinity_type': activity.get('standard_type', ''),
                    'source': 'ChEMBL',
                    'confidence': 0.8,
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('drug_targets', rows)
                
        except Exception as e:
            logger.error(f"Failed to load ChEMBL drug targets: {e}")
            self.stats.errors += 1
        
        return self.stats
    
    def _get_uniprot_from_chembl_target(self, target_chembl: str) -> str | None:
        """Map ChEMBL target to UniProt ID."""
        # Check cache in database
        result = self.db.fetchone(
            "SELECT target_uniprot FROM drug_targets WHERE target_uniprot LIKE ? LIMIT 1",
            (f"%{target_chembl}%",)
        )
        if result:
            return result['target_uniprot']
        
        # Would need to query ChEMBL target API
        return None


class LiteratureLoader(BaseLoader):
    """Load literature from PubMed, Europe PMC."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "literature", "publications", "papers"):
            self.stats.records_processed += 1
            row = dict(item)
            if not row.get("pmid") and row.get("pubmed_id"):
                row["pmid"] = str(row["pubmed_id"])
            if not row.get("title"):
                self.stats.errors += 1
                continue
            cleaned = self._clean("literature", row)
            try:
                if cleaned.get("pmid"):
                    self.db.upsert("literature", cleaned, ["pmid"])
                else:
                    self.db.insert("literature", cleaned)
                self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Literature loader skipped %s: %s", row.get("pmid"), exc)
                self.stats.errors += 1
    
    def load_from_pubmed(self, pmids: list[str]) -> LoadStats:
        """Load publications from PubMed."""
        # Would use Entrez API
        logger.info("PubMed loading requires Entrez API key")
        return self.stats
    
    def load_from_europe_pmc(self, query: str, limit: int = 1000) -> LoadStats:
        """Load from Europe PMC."""
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&pageSize={limit}"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            rows = []
            for hit in data.get('resultList', {}).get('result', []):
                pmid = hit.get('pmid', '')
                if not pmid:
                    continue
                
                rows.append({
                    'pmid': pmid,
                    'doi': hit.get('doi', ''),
                    'title': hit.get('title', ''),
                    'authors': json.dumps(hit.get('authorString', '').split(', ')),
                    'journal': hit.get('journalTitle', ''),
                    'year': hit.get('pubYear', 0),
                    'abstract': hit.get('abstractText', ''),
                })
                self.stats.records_processed += 1
            
            if rows:
                self.stats.records_inserted = self.db.bulk_insert('literature', rows)
                
        except Exception as e:
            logger.error(f"Failed to load Europe PMC: {e}")
            self.stats.errors += 1
        
        return self.stats


class VariantLoader(BaseLoader):
    """Load variant data from ClinVar, gnomAD."""

    def _load(self, data: Any, **_: Any) -> None:
        for item in self._items(data, "variants", "variant"):
            self.stats.records_processed += 1
            row = dict(item)
            if not row.get("variant_id") and row.get("variant"):
                row["variant_id"] = str(row["variant"])
            if not row.get("variant_id"):
                self.stats.errors += 1
                continue
            cleaned = self._clean("variants", row)
            try:
                self.db.upsert("variants", cleaned, ["variant_id"])
                self.stats.records_inserted += 1
            except Exception as exc:
                logger.warning("Variant loader skipped %s: %s", row.get("variant_id"), exc)
                self.stats.errors += 1
    
    def load_from_clinvar(self, filepath: str | Path) -> LoadStats:
        """Load variants from ClinVar VCF."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"ClinVar file not found: {filepath}")
        
        open_func = gzip.open if path.suffix == '.gz' else open
        
        rows = []
        with open_func(path, 'rt') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                parts = line.strip().split('\t')
                if len(parts) < 8:
                    continue
                
                chrom, pos, var_id, ref, alt = parts[0], parts[1], parts[2], parts[3], parts[4]
                info = parts[7]
                
                # Parse INFO field
                clinvar_sig = ''
                gene_symbol = ''
                for item in info.split(';'):
                    if item.startswith('CLNSIG='):
                        clinvar_sig = item.split('=')[1]
                    elif item.startswith('GENEINFO='):
                        gene_symbol = item.split('=')[1].split(':')[0]
                
                if var_id == '.':
                    var_id = f"{chrom}:{pos}:{ref}:{alt}"
                
                rows.append({
                    'variant_id': var_id,
                    'chrom': chrom,
                    'pos': int(pos),
                    'ref': ref,
                    'alt': alt,
                    'gene_symbol': gene_symbol,
                    'clinvar_significance': clinvar_sig,
                })
                self.stats.records_processed += 1
        
        if rows:
            self.stats.records_inserted = self.db.bulk_insert('variants', rows)
        
        return self.stats


def load_all_data(
    db: KnowledgeDatabase | None = None,
    data: dict[str, Any] | None = None,
    sources: list[str] | None = None,
) -> dict[str, LoadStats]:
    """Load data into the knowledge database.

    When ``data`` is supplied it must be a mapping of dataset name to a list of
    records (e.g. ``{"genes": [...], "diseases": [...]}``); those records are
    written through the matching loader. Without ``data`` the function performs
    the original live download workflow for the requested ``sources``.
    """
    db = db or get_knowledge_db()

    if data is not None:
        loader_classes = {
            "genes": GeneLoader,
            "diseases": DiseaseLoader,
            "proteins": ProteinLoader,
            "pathways": PathwayLoader,
            "drugs": DrugLoader,
            "literature": LiteratureLoader,
            "variants": VariantLoader,
        }
        results: dict[str, LoadStats] = {}
        for key, loader_class in loader_classes.items():
            if key in data:
                results[key] = loader_class(db).load({key: data[key]})
        return results

    sources = sources or ['genes', 'diseases', 'proteins', 'pathways', 'drugs', 'literature']
    results = {}
    
    if 'genes' in sources:
        loader = GeneLoader(db)
        results['genes'] = loader.load_from_opentargets(5000)
    
    if 'diseases' in sources:
        loader = DiseaseLoader(db)
        # Would need MONDO file
        logger.info("Disease loading requires MONDO file")
    
    if 'proteins' in sources:
        # Load proteins for known genes
        genes = db.fetchall("SELECT uniprot_ids FROM genes WHERE uniprot_ids IS NOT NULL AND uniprot_ids != '[]' LIMIT 100")
        uniprot_ids = []
        for gene in genes:
            ids = json.loads(gene['uniprot_ids']) if gene['uniprot_ids'] else []
            uniprot_ids.extend(ids)
        
        if uniprot_ids:
            loader = ProteinLoader(db)
            results['proteins'] = loader.load_from_uniprot(uniprot_ids[:100])
    
    if 'pathways' in sources:
        loader = PathwayLoader(db)
        results['kegg_pathways'] = loader.load_from_kegg()
        results['reactome_pathways'] = loader.load_from_reactome()
    
    if 'drugs' in sources:
        loader = DrugLoader(db)
        results['drugs'] = loader.load_from_chembl(2000)
        results['drug_targets'] = loader.load_drug_targets_from_chembl(5000)
    
    if 'literature' in sources:
        loader = LiteratureLoader(db)
        results['literature'] = loader.load_from_europe_pmc('cancer', 500)
    
    return results