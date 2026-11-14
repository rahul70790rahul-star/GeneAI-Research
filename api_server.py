#!/usr/bin/env python
"""GeneAI Research - FastAPI ML API Entry Point for Render Deployment.

This file serves as the entry point for the FastAPI ML API when deployed to Render.
It configures the application for production with proper environment variables,
CORS settings, and database connections.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file if present (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Configure logging
import logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import and configure the FastAPI app
from geneai.mutation_ml.api import app

# ============================================================
# PRODUCTION CONFIGURATION
# ============================================================

# CORS Origins - Allow Streamlit Community Cloud and local development
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://geneai-research.streamlit.app,https://*.streamlit.app,http://localhost:8501,http://localhost:8502").split(",")

# Update CORS middleware
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in CORS_ORIGINS if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATABASE CONFIGURATION (Neon PostgreSQL)
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    logger.info("PostgreSQL database configured")
    # The unified_knowledge database will use this
    os.environ["GENEAI_DATABASE_PATH"] = DATABASE_URL
else:
    logger.warning("DATABASE_URL not set - using SQLite fallback")

# ============================================================
# REDIS CONFIGURATION (Upstash)
# ============================================================
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
    logger.info("Upstash Redis configured via REST API")
elif REDIS_URL:
    logger.info("Redis configured via standard URL")
else:
    logger.warning("Redis not configured - caching disabled")

# ============================================================
# SECURITY CONFIGURATION
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "your-32-char-secret-key-here":
    logger.warning("SECRET_KEY not properly configured!")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
API_KEY_PREFIX = os.getenv("API_KEY_PREFIX", "gai_")

# ============================================================
# ML MODEL CONFIGURATION
# ============================================================
MODEL_DIR = Path(os.getenv("MODEL_DIR", "data/models"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "best_mutation_model_real.pkl")
ENABLE_SHAP = os.getenv("ENABLE_SHAP", "true").lower() == "true"

# Ensure model directory exists
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# FEATURE FLAGS
# ============================================================
ENABLE_MUTATION_ML = os.getenv("ENABLE_MUTATION_ML", "true").lower() == "true"
ENABLE_REST_API = os.getenv("ENABLE_REST_API", "true").lower() == "true"

# ============================================================
# EXTERNAL API KEYS
# ============================================================
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
UNIPROT_API_KEY = os.getenv("UNIPROT_API_KEY", "")
OPENTARGETS_API_KEY = os.getenv("OPENTARGETS_API_KEY", "")
ALPHAFOLD_API_KEY = os.getenv("ALPHAFOLD_API_KEY", "")

if NCBI_API_KEY:
    os.environ["NCBI_API_KEY"] = NCBI_API_KEY
if UNIPROT_API_KEY:
    os.environ["UNIPROT_API_KEY"] = UNIPROT_API_KEY
if OPENTARGETS_API_KEY:
    os.environ["OPENTARGETS_API_KEY"] = OPENTARGETS_API_KEY
if ALPHAFOLD_API_KEY:
    os.environ["ALPHAFOLD_API_KEY"] = ALPHAFOLD_API_KEY

# ============================================================
# STARTUP EVENTS
# ============================================================
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting GeneAI Mutation ML API")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'production')}")
    logger.info(f"Model directory: {MODEL_DIR}")
    logger.info(f"Default model: {DEFAULT_MODEL}")
    logger.info(f"CORS origins: {CORS_ORIGINS}")
    
    # Try to load default model
    try:
        from geneai.mutation_ml.integration import MutationMLIntegration
        model_path = MODEL_DIR / DEFAULT_MODEL
        if model_path.exists():
            integration = MutationMLIntegration(model_path=str(model_path))
            if integration.load_model():
                logger.info(f"Loaded model: {DEFAULT_MODEL}")
            else:
                logger.warning(f"Failed to load model: {DEFAULT_MODEL}")
        else:
            logger.warning(f"Model file not found: {model_path}")
    except Exception as e:
        logger.error(f"Model loading error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down GeneAI Mutation ML API")

# ============================================================
# HEALTH CHECK ENDPOINT (enhanced)
# ============================================================
@app.get("/health")
async def health_check():
    """Enhanced health check with dependency status."""
    from geneai.mutation_ml.integration import MutationMLIntegration
    
    integration = MutationMLIntegration()
    model_loaded = integration.is_loaded()
    
    # Check database connectivity
    db_status = "unknown"
    if DATABASE_URL:
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
            conn.close()
            db_status = "connected"
        except Exception:
            db_status = "failed"
    else:
        db_status = "sqlite_fallback"
    
    # Check Redis connectivity
    redis_status = "unknown"
    if UPSTASH_REDIS_REST_URL:
        try:
            import requests
            response = requests.get(f"{UPSTASH_REDIS_REST_URL}/ping", 
                                  headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"},
                                  timeout=5)
            redis_status = "connected" if response.status_code == 200 else "failed"
        except Exception:
            redis_status = "failed"
    elif REDIS_URL:
        redis_status = "configured"
    else:
        redis_status = "not_configured"
    
    return {
        "status": "healthy" if model_loaded else "degraded",
        "service": "geneai-mutation-ml-api",
        "version": "1.0.0",
        "model_loaded": model_loaded,
        "model_name": integration.training_result.model_name if model_loaded else None,
        "dependencies": {
            "database": db_status,
            "redis": redis_status,
        },
        "features": {
            "mutation_ml": ENABLE_MUTATION_ML,
            "rest_api": ENABLE_REST_API,
            "shap": ENABLE_SHAP,
        }
    }

@app.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes/Render."""
    from geneai.mutation_ml.integration import MutationMLIntegration
    
    integration = MutationMLIntegration()
    model_loaded = integration.is_loaded()
    
    checks = {
        "api": "ok",
        "model": "ok" if model_loaded else "not_loaded",
    }
    
    all_ok = all(v == "ok" for v in checks.values())
    
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        workers=1,  # Free tier has limited CPU
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )