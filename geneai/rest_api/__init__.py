"""GeneAI Advanced REST API - Phase 5.7."""
from __future__ import annotations

from geneai.rest_api.core import (
    GeneAIAPI,
    APIKey,
    APIResponse,
    APIVersion,
    get_api,
    create_api,
    FLASK_LIMITER_AVAILABLE,
)
from geneai.rest_api.ui import (
    render_rest_api_dashboard,
    render as render_rest_api,
)

__all__ = [
    # Core
    "GeneAIAPI",
    "APIKey",
    "APIResponse",
    "APIVersion",
    "get_api",
    "create_api",
    "FLASK_LIMITER_AVAILABLE",
    # UI
    "render_rest_api_dashboard",
    "render_rest_api",
]

__version__ = "5.7.0"