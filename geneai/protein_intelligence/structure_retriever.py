"""Protein structure retrieval module."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class ProteinStructure:
    """Protein structure information."""
    identifier: str
    source: str  # "alphafold", "pdb", "esmfold"
    title: str | None = None
    organism: str | None = None
    method: str | None = None
    resolution: float | None = None
    release_date: str | None = None
    pdb_url: str | None = None
    cif_url: str | None = None
    pdb_content: str | None = None
    cif_content: str | None = None
    confidence_scores: list[float] = field(default_factory=list)  # pLDDT for AlphaFold
    chains: list[dict[str, Any]] = field(default_factory=list)
    ligands: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class StructureRetriever:
    """
    Retrieve protein structures from public databases.
    
    Sources:
    - AlphaFold Protein Structure Database
    - RCSB PDB
    - ESMFold (if available)
    - UniProt structure cross-references
    """
    
    ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api"
    PDB_API = "https://data.rcsb.org/rest/v1/core"
    PDB_DOWNLOAD = "https://files.rcsb.org/download"
    UNIPROT_API = "https://rest.uniprot.org/uniprotkb"
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GeneAI-ProteinIntelligence/1.0",
        })
        self.logger = logging.getLogger(__name__)
    
    def get_alphafold_structure(
        self,
        uniprot_id: str,
        format: str = "cif",
    ) -> ProteinStructure | None:
        """
        Get predicted structure from AlphaFold DB.
        
        Args:
            uniprot_id: UniProt accession (e.g., "P04637")
            format: "cif" or "pdb"
            
        Returns:
            ProteinStructure or None if not found
        """
        # Try to get structure info
        url = f"{self.ALPHAFOLD_API}/prediction/{uniprot_id}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return None
            
            entry = data[0]
            
            # Download structure file
            cif_url = entry.get("cifUrl") or entry.get("pdbUrl")
            if not cif_url:
                return None
            
            structure = self._download_structure(cif_url, format)
            if structure:
                structure.identifier = uniprot_id
                structure.source = "alphafold"
                structure.title = entry.get("uniprotDescription")
                structure.organism = entry.get("taxonomyName")
                structure.method = "AlphaFold2"
                structure.confidence_scores = entry.get("confidenceScore", [])
                structure.metadata = entry
            
            return structure
            
        except Exception as e:
            self.logger.error("AlphaFold retrieval failed for %s: %s", uniprot_id, e)
            return None
    
    def get_pdb_structure(
        self,
        pdb_id: str,
        format: str = "cif",
    ) -> ProteinStructure | None:
        """
        Get experimental structure from RCSB PDB.
        
        Args:
            pdb_id: PDB ID (e.g., "1M17")
            format: "cif" or "pdb"
            
        Returns:
            ProteinStructure or None if not found
        """
        pdb_id = pdb_id.upper()
        
        # Get metadata
        url = f"{self.PDB_API}/entry/{pdb_id}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            
            # Download structure
            if format == "cif":
                download_url = f"{self.PDB_DOWNLOAD}/{pdb_id}.cif"
            else:
                download_url = f"{self.PDB_DOWNLOAD}/{pdb_id}.pdb"
            
            structure = self._download_structure(download_url, format)
            if structure:
                structure.identifier = pdb_id
                structure.source = "pdb"
                structure.title = data.get("struct", {}).get("title")
                structure.organism = self._extract_organism(data)
                structure.method = data.get("exptl", [{}])[0].get("method")
                structure.resolution = data.get("rcsb_entry_info", {}).get("resolution_combined")
                structure.release_date = data.get("rcsb_accession_info", {}).get("initial_release_date")
                structure.pdb_url = f"https://www.rcsb.org/structure/{pdb_id}"
                structure.metadata = data
            
            return structure
            
        except Exception as e:
            self.logger.error("PDB retrieval failed for %s: %s", pdb_id, e)
            return None
    
    def search_pdb_by_uniprot(
        self,
        uniprot_id: str,
    ) -> list[ProteinStructure]:
        """
        Search PDB for structures matching a UniProt ID.
        
        Returns:
            List of ProteinStructure objects
        """
        url = f"{self.PDB_API}/search"
        query = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                    "operator": "exact_match",
                    "value": uniprot_id,
                },
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": 20}},
        }
        
        try:
            response = self.session.post(url, json=query, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for entry in data.get("result_set", []):
                pdb_id = entry.get("identifier")
                if pdb_id:
                    struct = self.get_pdb_structure(pdb_id)
                    if struct:
                        results.append(struct)
            
            return results
            
        except Exception as e:
            self.logger.error("PDB search failed for %s: %s", uniprot_id, e)
            return []
    
    def get_uniprot_structures(self, uniprot_id: str) -> list[dict[str, Any]]:
        """
        Get structure cross-references from UniProt.
        
        Returns:
            List of structure references with PDB IDs and metadata
        """
        url = f"{self.UNIPROT_API}/{uniprot_id}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            structures = []
            for xref in data.get("uniProtKBCrossReferences", []):
                if xref.get("database") == "PDB":
                    structures.append({
                        "pdb_id": xref.get("id"),
                        "method": xref.get("properties", {}).get("method"),
                        "resolution": xref.get("properties", {}).get("resolution"),
                        "chains": xref.get("properties", {}).get("chains"),
                        "gene_name": data.get("genes", [{}])[0].get("geneName", {}).get("value"),
                    })
            
            return structures
            
        except Exception as e:
            self.logger.error("UniProt structure lookup failed for %s: %s", uniprot_id, e)
            return []
    
    def get_best_structure(
        self,
        uniprot_id: str,
        prefer_experimental: bool = True,
    ) -> ProteinStructure | None:
        """
        Get the best available structure for a protein.
        
        Args:
            uniprot_id: UniProt accession
            prefer_experimental: If True, prefer experimental over predicted
            
        Returns:
            Best ProteinStructure or None
        """
        if prefer_experimental:
            # Try PDB first
            pdb_structures = self.search_pdb_by_uniprot(uniprot_id)
            if pdb_structures:
                # Sort by resolution (best first)
                pdb_structures.sort(
                    key=lambda s: s.resolution if s.resolution else float('inf')
                )
                return pdb_structures[0]
        
        # Fall back to AlphaFold
        return self.get_alphafold_structure(uniprot_id)
    
    def _download_structure(self, url: str, format: str) -> ProteinStructure | None:
        """Download structure file from URL."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            content = response.text
            
            # Parse basic info from CIF/PDB
            structure = ProteinStructure(
                identifier="",
                source="",
            )
            
            if format == "cif":
                structure.cif_content = content
                structure.cif_url = url
            else:
                structure.pdb_content = content
                structure.pdb_url = url
            
            # Extract chains
            structure.chains = self._parse_chains(content, format)
            
            return structure
            
        except Exception as e:
            self.logger.error("Structure download failed: %s", e)
            return None
    
    def _parse_chains(self, content: str, format: str) -> list[dict[str, Any]]:
        """Parse chain information from structure file."""
        chains = []
        
        if format == "cif":
            # Simple CIF parsing for chain info
            in_entity = False
            for line in content.split("\n"):
                if line.startswith("_entity.id"):
                    in_entity = True
                elif in_entity and line.startswith("#"):
                    continue
                elif in_entity and line and not line.startswith("_"):
                    parts = line.split()
                    if parts:
                        chains.append({
                            "id": parts[0],
                            "type": "polymer",
                        })
                    in_entity = False
        
        return chains
    
    def _extract_organism(self, data: dict) -> str | None:
        """Extract organism from PDB data."""
        entities = data.get("rcsb_polymer_entity_container_identifiers", [])
        if entities:
            return entities[0].get("organism_scientific_name")
        return None
    
    def close(self):
        """Close the session."""
        self.session.close()


def retrieve_structure(
    identifier: str,
    source: str = "auto",
    prefer_experimental: bool = True,
) -> ProteinStructure | None:
    """Convenience function for structure retrieval."""
    retriever = StructureRetriever()
    try:
        if source == "alphafold" or (source == "auto" and identifier.isalnum() and len(identifier) <= 10):
            return retriever.get_alphafold_structure(identifier)
        elif source == "pdb" or (source == "auto" and len(identifier) == 4):
            return retriever.get_pdb_structure(identifier)
        elif source == "auto":
            return retriever.get_best_structure(identifier, prefer_experimental)
        return None
    finally:
        retriever.close()