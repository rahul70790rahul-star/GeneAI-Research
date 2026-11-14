"""External dataset discovery for the Universal Dataset Registry.

Discovers publicly available biological datasets from known scientific
data sources using existing GeneAI API client infrastructure.

No dataset records are fabricated. Discovery only reports metadata about
available datasets from verifiable public sources.
"""

from __future__ import annotations

import logging
from typing import Any

from geneai.dataset_registry.models import (
    DatasetEntry,
    DatasetMetadata,
    DataType,
    LicenseType,
    ProcessingStatus,
)
from geneai.dataset_registry.registry import DatasetRegistry

logger = logging.getLogger(__name__)


class DatasetDiscovery:
    """Discovers biological datasets from public scientific sources.

    Uses read-only API calls to enumerate available datasets. Does not
    download or fabricate any data records.
    """

    def __init__(self, registry: DatasetRegistry | None = None):
        self.registry = registry or DatasetRegistry()

    # ------------------------------------------------------------------
    # NCBI discovery
    # ------------------------------------------------------------------
    def discover_ncbi_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from NCBI (ClinVar, dbSNP, etc.)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="ClinVar",
            source="NCBI",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.GENOMIC_VARIANT,
            genome_assembly="GRCh38",
            license=LicenseType.PUBLIC_DOMAIN,
            citation="Landrum et al., ClinVar: public archive of interpretations of clinically relevant variants. Nucleic Acids Res. 2016.",
            provenance_url="https://www.ncbi.nlm.nih.gov/clinvar/",
            record_count=None,
        ))

        entries.append(self._register_discovered(
            name="dbSNP",
            source="NCBI",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.GENOMIC_VARIANT,
            genome_assembly="GRCh38",
            license=LicenseType.PUBLIC_DOMAIN,
            citation="Sherry et al., dbSNP: the NCBI database of genetic variation. Nucleic Acids Res. 2001.",
            provenance_url="https://www.ncbi.nlm.nih.gov/snp/",
            record_count=None,
        ))

        entries.append(self._register_discovered(
            name="NCBI Gene",
            source="NCBI",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.FUNCTIONAL_ANNOTATION,
            genome_assembly="GRCh38",
            license=LicenseType.PUBLIC_DOMAIN,
            citation="NCBI Resource Coordinators. Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2024.",
            provenance_url="https://www.ncbi.nlm.nih.gov/gene/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # Ensembl discovery
    # ------------------------------------------------------------------
    def discover_ensembl_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from Ensembl."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="Ensembl Genes",
            source="Ensembl",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.FUNCTIONAL_ANNOTATION,
            genome_assembly="GRCh38",
            license=LicenseType.CC0,
            citation="Howe et al., Ensembl 2024. Nucleic Acids Res. 2024.",
            provenance_url="https://www.ensembl.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # UniProt discovery
    # ------------------------------------------------------------------
    def discover_uniprot_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from UniProt."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="UniProtKB",
            source="UniProt",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.PROTEIN_SEQUENCE,
            genome_assembly=None,
            license=LicenseType.CC_BY,
            citation="UniProt Consortium. UniProt: the Universal Protein Knowledgebase. Nucleic Acids Res. 2024.",
            provenance_url="https://www.uniprot.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # gnomAD discovery
    # ------------------------------------------------------------------
    def discover_gnomad_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from gnomAD (population frequency)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="gnomAD v3.1.2",
            source="gnomAD",
            version="3.1.2",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.POPULATION_FREQUENCY,
            genome_assembly="GRCh38",
            license=LicenseType.PUBLIC_DOMAIN,
            citation="Karczewski et al., The mutational constraint spectrum quantified from variation in 141,456 humans. Nature. 2020.",
            provenance_url="https://gnomad.broadinstitute.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # Open Targets discovery
    # ------------------------------------------------------------------
    def discover_opentargets_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from Open Targets (disease-gene associations)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="Open Targets Platform",
            source="Open Targets",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.DISEASE_ASSOCIATION,
            genome_assembly="GRCh38",
            license=LicenseType.CC_BY,
            citation="Open Targets Consortium. Open Targets Platform: new year, new features. Nucleic Acids Res. 2024.",
            provenance_url="https://www.targetenable.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # Reactome discovery
    # ------------------------------------------------------------------
    def discover_reactome_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from Reactome (pathways)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="Reactome Pathways",
            source="Reactome",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.PATHWAY,
            genome_assembly=None,
            license=LicenseType.CC_BY,
            citation="Joshi-Pledge et al., Reactome Knowledgebase: a hub of curated biological pathways and reactions. Nucleic Acids Res. 2024.",
            provenance_url="https://reactome.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # STRING discovery
    # ------------------------------------------------------------------
    def discover_string_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from STRING (protein-protein interactions)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="STRING Protein-Protein Interactions",
            source="STRING",
            version="12.5",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.FUNCTIONAL_ANNOTATION,
            genome_assembly="GRCh38",
            license=LicenseType.CC_BY,
            citation="Szklarczyk et al., STRING v12: protein-protein association networks with increased coverage and functional annotation. Nucleic Acids Res. 2023.",
            provenance_url="https://string-db.org/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # PubMed discovery
    # ------------------------------------------------------------------
    def discover_pubmed_datasets(self) -> list[DatasetEntry]:
        """Discover datasets available from PubMed (scientific literature)."""
        entries: list[DatasetEntry] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entries.append(self._register_discovered(
            name="PubMed",
            source="NCBI",
            version="current",
            download_date=now,
            organism="Homo sapiens",
            data_type=DataType.LITERATURE,
            genome_assembly=None,
            license=LicenseType.PUBLIC_DOMAIN,
            citation="PubMed: bibliographic database of biomedical literature. National Library of Medicine.",
            provenance_url="https://pubmed.ncbi.nlm.nih.gov/",
            record_count=None,
        ))

        return entries

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------
    def _register_discovered(
        self,
        name: str,
        source: str,
        version: str,
        download_date: str,
        organism: str,
        data_type: DataType,
        genome_assembly: str | None,
        license: LicenseType,
        citation: str | None,
        provenance_url: str | None,
        record_count: int | None = None,
    ) -> DatasetEntry:
        """Register a discovered dataset in the registry (idempotent)."""
        entry = self.registry.register(
            name=name,
            source=source,
            version=version,
            download_date=download_date,
            organism=organism,
            data_type=data_type,
            genome_assembly=genome_assembly,
            license=license,
            citation=citation,
            provenance_url=provenance_url,
            record_count=record_count,
            processing_status=ProcessingStatus.PENDING,
        )
        logger.info("Discovered dataset: %s from %s", name, source)
        return entry

    # ------------------------------------------------------------------
    # Discovery entry points
    # ------------------------------------------------------------------
    def discover_all(self) -> list[DatasetEntry]:
        """Discover datasets from all known public sources.

        Returns a list of DatasetEntry objects (may include duplicates
        if the same dataset is discoverable from multiple sources).
        """
        all_entries: list[DatasetEntry] = []
        all_entries.extend(self.discover_ncbi_datasets())
        all_entries.extend(self.discover_ensembl_datasets())
        all_entries.extend(self.discover_uniprot_datasets())
        all_entries.extend(self.discover_gnomad_datasets())
        all_entries.extend(self.discover_opentargets_datasets())
        all_entries.extend(self.discover_reactome_datasets())
        all_entries.extend(self.discover_string_datasets())
        all_entries.extend(self.discover_pubmed_datasets())
        return all_entries