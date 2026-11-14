"""Data models for the Intelligent Dataset Selection Engine.

Defines ResearchQuestion, SelectionCriteria, SelectionResult, and related
dataclasses used to understand research queries and select relevant datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BiologicalDomain(Enum):
    """Biological domains for research questions."""

    GENOMICS = "genomics"
    PROTEOMICS = "proteomics"
    DISEASE = "disease"
    DRUG = "drug"
    PATHWAY = "pathway"
    EXPRESSION = "expression"
    POPULATION = "population"
    CLINICAL = "clinical"
    LITERATURE = "literature"
    MULTI_DOMAIN = "multi_domain"
    UNKNOWN = "unknown"


class EntityType(Enum):
    """Types of biological entities."""

    GENE = "gene"
    PROTEIN = "protein"
    DISEASE = "disease"
    DRUG = "drug"
    VARIANT = "variant"
    PATHWAY = "pathway"
    ORGANISM = "organism"