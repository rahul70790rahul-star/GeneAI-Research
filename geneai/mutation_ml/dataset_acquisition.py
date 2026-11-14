"""Dataset acquisition for mutation interpretation ML pipeline.

Downloads and caches data from:
- ClinVar: Clinical variant significance
- gnomAD: Population allele frequencies
- Ensembl: Gene/transcript annotations, VEP consequences
- dbSNP: Variant identifiers and annotations
- COSMIC: Cancer somatic mutations
- UniProt: Protein annotations and domains
- AlphaMissense: Pathogenicity predictions
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
from tqdm import tqdm

from geneai.config import DATA_DIR

logger = logging.getLogger(__name__)

# Dataset URLs and configurations
DATASET_CONFIG = {
    "clinvar": {
        "url": "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz",
        "filename": "clinvar_variant_summary.txt.gz",
        "description": "ClinVar variant clinical significance annotations",
    },
    "gnomad_v4": {
        "url": "https://storage.googleapis.com/gnomad-public/release/4.1/ht/genomes/gnomad.genomes.v4.1.sites.ht.tar",
        "filename": "gnomad_genomes_v4.1.ht.tar",
        "description": "gnomAD v4.1 genome allele frequencies (Hail table)",
        "note": "Requires Hail to process. Use VCF/TSV exports instead for pandas.",
    },
    "gnomad_v4_vcf": {
        "url": "https://storage.googleapis.com/gnomad-public/release/4.1/vcf/genomes/gnomad.genomes.v4.1.sites.chr{chr}.vcf.bgz",
        "filename": "gnomad_genomes_v4.1_chr{chr}.vcf.bgz",
        "description": "gnomAD v4.1 genome allele frequencies (per-chromosome VCF)",
        "chromosomes": list(range(1, 23)) + ["X", "Y"],
    },
    "ensembl_vep_cache": {
        "url": "https://ftp.ensembl.org/pub/release-112/variation/VEP/homo_sapiens_vep_112_GRCh38.tar.gz",
        "filename": "homo_sapiens_vep_112_GRCh38.tar.gz",
        "description": "Ensembl VEP cache for GRCh38",
    },
    "dbsnp": {
        "url": "https://ftp.ncbi.nlm.nih.gov/pub/dbSNP/GCF_000001405.40/GATK_bundle/GCF_000001405.40.gz",
        "filename": "dbsnp_GCF_000001405.40.gz",
        "description": "dbSNP VCF for GRCh38",
    },
    "cosmic": {
        "url": "https://cancer.sanger.ac.uk/cosmic/download",
        "filename": "cosmic_download",
        "description": "COSMIC cancer mutations (requires registration)",
        "note": "Requires COSMIC account. Place downloaded files manually in data/cosmic/",
    },
    "uniprot": {
        "url": "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.dat.gz",
        "filename": "uniprot_sprot.dat.gz",
        "description": "UniProt Swiss-Prot protein annotations",
    },
    "alphamissense": {
        "url": "https://storage.googleapis.com/dm_alphamissense/AlphaMissense_aa_substitutions.tsv.gz",
        "filename": "AlphaMissense_aa_substitutions.tsv.gz",
        "description": "AlphaMissense pathogenicity predictions for all missense variants",
    },
}


@dataclass
class DatasetInfo:
    """Information about a downloaded dataset."""
    name: str
    path: Path
    size_bytes: int
    downloaded_at: float
    description: str
    checksum: str | None = None


class BaseFetcher:
    """Base class for dataset fetchers."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GeneAI-Research/1.0"})

    def _download_with_progress(
        self,
        url: str,
        dest: Path,
        chunk_size: int = 8192,
        timeout: int = 300,
    ) -> Path:
        """Download file with progress bar."""
        logger.info("Downloading %s to %s", url, dest)

        try:
            response = self.session.get(url, stream=True, timeout=timeout)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            dest.parent.mkdir(parents=True, exist_ok=True)

            with open(dest, "wb") as f, tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=dest.name,
            ) as pbar:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

            logger.info("Downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / (1024 * 1024))
            return dest

        except requests.RequestException as e:
            logger.error("Download failed for %s: %s", url, e)
            if dest.exists():
                dest.unlink()
            raise

    def _extract_gzip(self, gz_path: Path, dest_path: Path | None = None) -> Path:
        """Extract gzipped file."""
        dest_path = dest_path or gz_path.with_suffix("")
        logger.info("Extracting %s to %s", gz_path, dest_path)

        with gzip.open(gz_path, "rb") as f_in:
            with open(dest_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        return dest_path

    def get_dataset_info(self, name: str) -> DatasetInfo | None:
        """Get info about a downloaded dataset."""
        config = DATASET_CONFIG.get(name)
        if not config:
            return None

        filepath = self.data_dir / config["filename"]
        if not filepath.exists():
            return None

        stat = filepath.stat()
        return DatasetInfo(
            name=name,
            path=filepath,
            size_bytes=stat.st_size,
            downloaded_at=stat.st_mtime,
            description=config["description"],
        )


class ClinVarFetcher(BaseFetcher):
    """Fetch and parse ClinVar variant summary."""

    def download(self, force: bool = False) -> Path:
        """Download ClinVar variant summary."""
        config = DATASET_CONFIG["clinvar"]
        dest = self.data_dir / config["filename"]

        if dest.exists() and not force:
            logger.info("ClinVar already downloaded at %s", dest)
            return dest

        return self._download_with_progress(config["url"], dest)

    def parse(self, filepath: Path | None = None, chunksize: int = 100_000) -> pd.DataFrame:
        """Parse ClinVar variant summary TSV."""
        filepath = filepath or self.data_dir / DATASET_CONFIG["clinvar"]["filename"]

        if not filepath.exists():
            self.download()

        # Read gzipped TSV in chunks
        logger.info("Parsing ClinVar from %s", filepath)

        # ClinVar columns of interest
        usecols = [
            "AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID",
            "ClinicalSignificance", "ClinSigSimple", "LastEvaluated",
            "ReviewStatus", "NumberSubmitters", "Guidelines",
            "TestedInGTR", "OtherIDs", "SubmitterCategories",
            "VariationID", "Accession", "ReportedClassification",
            "RCVaccession", "PhenotypeIDS", "PhenotypeList",
            "Origin", "OriginSimple", "Assembly", "Chromosome",
            "Start", "Stop", "ReferenceAllele", "AlternateAllele",
            "Cytogenetic", "MolecularConsequence", "ProteinChange",
        ]

        chunks = []
        for chunk in pd.read_csv(
            filepath,
            sep="\t",
            compression="gzip",
            usecols=lambda c: c in usecols,
            chunksize=chunksize,
            low_memory=False,
        ):
            chunks.append(chunk)

        df = pd.concat(chunks, ignore_index=True)
        logger.info("Parsed %d ClinVar variants", len(df))
        return df

    def filter_pathogenic(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter to pathogenic/likely pathogenic variants."""
        pathogenic_terms = ["Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic"]
        return df[df["ClinicalSignificance"].isin(pathogenic_terms)].copy()

    def filter_benign(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter to benign/likely benign variants."""
        benign_terms = ["Benign", "Likely benign", "Benign/Likely benign"]
        return df[df["ClinicalSignificance"].isin(benign_terms)].copy()


class GnomADFetcher(BaseFetcher):
    """Fetch and parse gnomAD allele frequencies."""

    def download_chromosome(self, chrom: str, force: bool = False) -> Path:
        """Download gnomAD VCF for a specific chromosome."""
        config = DATASET_CONFIG["gnomad_v4_vcf"]
        url = config["url"].format(chr=chrom)
        filename = config["filename"].format(chr=chrom)
        dest = self.data_dir / "gnomad" / filename

        if dest.exists() and not force:
            logger.info("gnomAD chr%s already downloaded", chrom)
            return dest

        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_with_progress(url, dest)

    def download_all(self, chromosomes: list[str] | None = None, force: bool = False) -> list[Path]:
        """Download gnomAD for all chromosomes."""
        chromosomes = chromosomes or DATASET_CONFIG["gnomad_v4_vcf"]["chromosomes"]
        files = []
        for chrom in chromosomes:
            try:
                files.append(self.download_chromosome(str(chrom), force))
            except Exception as e:
                logger.warning("Failed to download gnomAD chr%s: %s", chrom, e)
        return files

    def parse_chromosome(self, chrom: str, filepath: Path | None = None) -> pd.DataFrame:
        """Parse gnomAD VCF for a chromosome."""
        filepath = filepath or self.data_dir / "gnomad" / f"gnomad_genomes_v4.1_chr{chrom}.vcf.bgz"

        if not filepath.exists():
            self.download_chromosome(str(chrom))

        # Parse VCF - extract AF, AN, AC from INFO field
        import gzip
        
        records = []
        with gzip.open(filepath, "rt") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 8:
                    continue
                chrom_vcf, pos, id_, ref, alt, qual, filter_, info = parts[:8]
                
                # Parse INFO field for AF, AN, AC
                info_dict = {}
                for item in info.split(";"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        info_dict[k] = v
                
                records.append({
                    "chrom": chrom_vcf,
                    "pos": int(pos),
                    "ref": ref,
                    "alt": alt,
                    "AF": float(info_dict.get("AF", 0)),
                    "AN": int(info_dict.get("AN", 0)),
                    "AC": int(info_dict.get("AC", 0)),
                    "nhomalt": int(info_dict.get("nhomalt", 0)),
                })

        df = pd.DataFrame(records)
        df["chrom"] = df["chrom"].astype(str)
        return df


class EnsemblFetcher(BaseFetcher):
    """Fetch Ensembl annotations via REST API."""

    BASE_URL = "https://rest.ensembl.org"

    def fetch_vep_annotations(
        self,
        variants: list[dict[str, str]],
        species: str = "human",
        assembly: str = "GRCh38",
    ) -> list[dict[str, Any]]:
        """Fetch VEP annotations for variants via Ensembl REST API."""
        endpoint = f"/vep/{species}/region"
        url = urljoin(self.BASE_URL, endpoint)

        # Prepare variant strings
        variant_strings = [
            f"{v['chrom']}:{v['pos']}:{v['ref']}:{v['alt']}"
            for v in variants
        ]

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        data = {"variants": variant_strings}

        try:
            response = self.session.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("VEP request failed: %s", e)
            return []

    def fetch_gene_info(self, gene_symbol: str, species: str = "human") -> dict[str, Any] | None:
        """Fetch gene information from Ensembl."""
        endpoint = f"/xrefs/symbol/{species}/{gene_symbol}"
        url = urljoin(self.BASE_URL, endpoint)

        try:
            response = self.session.get(url, headers={"Accept": "application/json"}, timeout=30)
            response.raise_for_status()
            results = response.json()
            return results[0] if results else None
        except requests.RequestException as e:
            logger.error("Gene info request failed: %s", e)
            return None

    def fetch_transcript_consequences(self, variant_id: str) -> list[dict[str, Any]]:
        """Fetch transcript consequences for a variant."""
        endpoint = f"/vep/human/id/{variant_id}"
        url = urljoin(self.BASE_URL, endpoint)

        try:
            response = self.session.get(url, headers={"Accept": "application/json"}, timeout=30)
            response.raise_for_status()
            results = response.json()
            if results:
                return results[0].get("transcript_consequences", [])
            return []
        except requests.RequestException as e:
            logger.error("Transcript consequences request failed: %s", e)
            return []


class dbSNPFetcher(BaseFetcher):
    """Fetch dbSNP annotations."""

    def download(self, force: bool = False) -> Path:
        """Download dbSNP VCF (large file)."""
        config = DATASET_CONFIG["dbsnp"]
        dest = self.data_dir / config["filename"]

        if dest.exists() and not force:
            logger.info("dbSNP already downloaded at %s", dest)
            return dest

        logger.warning("dbSNP download is very large (>10GB). Consider using Ensembl REST API instead.")
        return self._download_with_progress(config["url"], dest, timeout=3600)

    def query_rsid(self, rsid: str) -> dict[str, Any] | None:
        """Query dbSNP by rsID via NCBI E-utilities."""
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params = {
            "db": "snp",
            "id": rsid.replace("rs", ""),
            "retmode": "json",
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("result", {}).get(rsid.replace("rs", ""), {})
        except requests.RequestException as e:
            logger.error("dbSNP query failed for %s: %s", rsid, e)
            return None


class COSMICFetcher(BaseFetcher):
    """Fetch COSMIC cancer mutations (requires manual download)."""

    def __init__(self, data_dir: Path | None = None):
        super().__init__(data_dir)
        self.cosmic_dir = self.data_dir / "cosmic"
        self.cosmic_dir.mkdir(parents=True, exist_ok=True)

    def list_local_files(self) -> list[Path]:
        """List locally available COSMIC files."""
        return list(self.cosmic_dir.glob("*.tsv*")) + list(self.cosmic_dir.glob("*.vcf*"))

    def parse_cosmic_tsv(self, filepath: Path) -> pd.DataFrame:
        """Parse COSMIC TSV export."""
        logger.info("Parsing COSMIC from %s", filepath)

        # COSMIC columns vary by export type
        df = pd.read_csv(filepath, sep="\t", low_memory=False, compression="gzip" if filepath.suffix == ".gz" else None)
        logger.info("Parsed %d COSMIC records", len(df))
        return df


class UniProtFetcher(BaseFetcher):
    """Fetch UniProt protein annotations."""

    BASE_URL = "https://rest.uniprot.org"

    def download_swissprot(self, force: bool = False) -> Path:
        """Download UniProt Swiss-Prot (large file)."""
        config = DATASET_CONFIG["uniprot"]
        dest = self.data_dir / config["filename"]

        if dest.exists() and not force:
            logger.info("UniProt already downloaded at %s", dest)
            return dest

        logger.warning("UniProt Swiss-Prot download is large (>3GB).")
        return self._download_with_progress(config["url"], dest, timeout=3600)

    def fetch_protein(self, uniprot_id: str) -> dict[str, Any] | None:
        """Fetch protein entry by UniProt ID."""
        url = f"{self.BASE_URL}/uniprotkb/{uniprot_id}.json"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("UniProt fetch failed for %s: %s", uniprot_id, e)
            return None

    def fetch_protein_features(self, uniprot_id: str) -> list[dict[str, Any]]:
        """Fetch protein features (domains, sites, etc.)."""
        protein = self.fetch_protein(uniprot_id)
        if not protein:
            return []

        features = []
        for feature in protein.get("features", []):
            features.append({
                "type": feature.get("type"),
                "description": feature.get("description"),
                "location": feature.get("location", {}),
                "begin": feature.get("location", {}).get("start", {}).get("value"),
                "end": feature.get("location", {}).get("end", {}).get("value"),
            })
        return features

    def map_gene_to_uniprot(self, gene_symbol: str) -> list[str]:
        """Map gene symbol to UniProt IDs."""
        url = f"{self.BASE_URL}/uniprotkb/search"
        params = {
            "query": f"gene:{gene_symbol} AND reviewed:true",
            "format": "json",
            "size": 10,
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return [entry["primaryAccession"] for entry in data.get("results", [])]
        except requests.RequestException as e:
            logger.error("UniProt search failed for %s: %s", gene_symbol, e)
            return []


class AlphaMissenseFetcher(BaseFetcher):
    """Fetch AlphaMissense pathogenicity predictions."""

    def download(self, force: bool = False) -> Path:
        """Download AlphaMissense TSV."""
        config = DATASET_CONFIG["alphamissense"]
        dest = self.data_dir / config["filename"]

        if dest.exists() and not force:
            logger.info("AlphaMissense already downloaded at %s", dest)
            return dest

        return self._download_with_progress(config["url"], dest)

    def parse(self, filepath: Path | None = None, chunksize: int = 10_000) -> pd.DataFrame:
        """Parse AlphaMissense TSV."""
        filepath = filepath or self.data_dir / DATASET_CONFIG["alphamissense"]["filename"]

        if not filepath.exists():
            self.download()

        logger.info("Parsing AlphaMissense from %s", filepath)

        usecols = ["uniprot_id", "protein_variant", "am_pathogenicity", "am_class"]

        chunks = []
        for chunk in pd.read_csv(
            filepath,
            sep="\t",
            compression="gzip",
            usecols=usecols,
            chunksize=chunksize,
            low_memory=False,
            comment="#",
        ):
            chunks.append(chunk)

        df = pd.concat(chunks, ignore_index=True)
        logger.info("Parsed %d AlphaMissense predictions", len(df))
        return df

    def query_variant(self, uniprot_id: str, protein_variant: str) -> dict[str, Any] | None:
        """Query AlphaMissense for a specific variant."""
        # Would need indexed lookup for efficiency
        # For now, return None - implement with local database
        return None


def download_all_datasets(data_dir: Path | None = None, force: bool = False) -> dict[str, Path | list[Path]]:
    """Download all available datasets."""
    data_dir = data_dir or DATA_DIR
    results = {}

    logger.info("Starting download of all datasets to %s", data_dir)

    # ClinVar
    try:
        clinvar = ClinVarFetcher(data_dir)
        results["clinvar"] = clinvar.download(force)
    except Exception as e:
        logger.error("ClinVar download failed: %s", e)
        results["clinvar"] = None

    # gnomAD (first few chromosomes for testing)
    try:
        gnomad = GnomADFetcher(data_dir)
        results["gnomad"] = gnomad.download_all(chromosomes=["1", "2", "X"], force=force)
    except Exception as e:
        logger.error("gnomAD download failed: %s", e)
        results["gnomad"] = []

    # AlphaMissense
    try:
        alphamissense = AlphaMissenseFetcher(data_dir)
        results["alphamissense"] = alphamissense.download(force)
    except Exception as e:
        logger.error("AlphaMissense download failed: %s", e)
        results["alphamissense"] = None

    # Ensembl VEP cache (optional, large)
    logger.info("Skipping Ensembl VEP cache (download manually if needed)")
    results["ensembl_vep_cache"] = None

    # COSMIC (manual)
    logger.info("COSMIC requires manual download - place files in data/cosmic/")
    results["cosmic"] = []

    # UniProt (optional, large)
    logger.info("Skipping UniProt Swiss-Prot (download manually if needed)")
    results["uniprot"] = None

    logger.info("Dataset download complete")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    download_all_datasets()