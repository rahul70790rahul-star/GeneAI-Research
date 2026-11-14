"""Runtime paths and limits for GeneAI Research."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "GeneAI Research"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("GENEAI_DATA_DIR", PROJECT_ROOT / "data")).expanduser()
DATABASE_PATH = Path(
    os.environ.get("GENEAI_DATABASE_PATH", DATA_DIR / "geneai_lab.sqlite3")
).expanduser()

# Keep in-memory parsers bounded; deployments can lower Streamlit's upload limit too.
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
# Compressed reference VCFs can expand well beyond their upload size.
MAX_VCF_DECOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_VCF_SAMPLES = 10_000
MAX_VCF_LINE_BYTES = 16 * 1024 * 1024
MAX_VCF_HEADER_BYTES = 16 * 1024 * 1024
PUBMED_TIMEOUT_SECONDS = 20.0
MAX_PUBMED_RESULTS = 100
MAX_PUBMED_QUERY_LENGTH = 500
